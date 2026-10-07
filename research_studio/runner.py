"""Bounded request executor; never advances workflow stages or manufactures duties."""
from pathlib import Path
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
import base64,fcntl,json,os,shutil,signal,subprocess,tempfile,time
from .util import require,read,sha,canonical,immutable,PMRSError
from . import tasks,execution,scheduler

def environment():
    env=dict(os.environ)
    for key in ('CODEX_PERMISSION_PROFILE','CODEX_SESSION_ID','CODEX_THREAD_ID','CODEX_INTERNAL_ORIGINATOR_OVERRIDE','CODEX_APP_TOOLS_PIPE_PATH'):
        env.pop(key,None)
    for key in list(env):
        if key.startswith(('CODEX_APP_','CODEX_TASK_','CODEX_REPL_','BROWSER_USE_')):env.pop(key,None)
    return env


def permissions(binary,work):
    fs={':minimal':'read',':workspace_roots':'write',str(Path(binary).resolve().parent):'read'}
    for p in work.iterdir():fs[str(p.absolute())]='read'
    # A single named permission profile isolates other projects and old reviews.
    filesystem='{'+','.join(json.dumps(k)+'='+json.dumps(v) for k,v in fs.items())+'}'
    values=['default_permissions="research-task"','permissions.research-task.filesystem='+filesystem,
      'permissions.research-task.network.enabled=false','approval_policy="never"','web_search="disabled"',
      'project_doc_max_bytes=0','features.multi_agent=false','features.memories=false','memories.use_memories=false',
      'features.hooks=false','features.apps=false','features.plugins=false','features.shell_snapshot=false']
    return [x for v in values for x in ('-c',v)]


def doctor(binary='codex'):
    from .setup import resolve_binary
    binary=resolve_binary('codex',binary);result={'available':bool(binary),'binary':binary,'model_calls':0,'ready':False}
    if not binary:return result
    with tempfile.TemporaryDirectory(prefix='pmrs-doctor-') as tmp:
        root=Path(tmp);work=root/'work';work.mkdir();(work/'input').write_text('input');(root/'secret').write_text('secret')
        code="""from pathlib import Path
import json
checks={'read':Path('input').read_text()=='input'}
try:Path('input').write_text('bad');checks['write_blocked']=False
except OSError:checks['write_blocked']=True
try:Path('../secret').read_text();checks['outside_blocked']=False
except OSError:checks['outside_blocked']=True
Path('scratch').write_text('ok');checks['scratch']=True
print(json.dumps(checks))
"""
        command=[binary,'--no-daemon','sandbox','-P','research-task','-C',str(work),*permissions(binary,work),'--','/usr/bin/python3','-c',code]
        try:
            p=subprocess.run(command,capture_output=True,text=True,timeout=30,env=environment())
            checks=json.loads(p.stdout) if p.returncode==0 else {}
            result.update(ready=checks=={'read':True,'write_blocked':True,'outside_blocked':True,'scratch':True},checks=checks,error=p.stderr[-3000:])
        except (OSError,ValueError,subprocess.TimeoutExpired) as exc:result['error']=str(exc)
    return result


class SimulatedCrash(RuntimeError):
    pass

class FakeExecutor:
    """A deterministic transport that still passes through capture and admission."""
    def __init__(self,response_factory,*,fault_at=None):
        self.response_factory=response_factory;self.fault_at=fault_at;self.calls=0;self.network_calls=0;self.spawn_calls=0
    def _fault(self,name):
        if self.fault_at==name:raise SimulatedCrash(name)
    def execute(self,store,task_id):
        t=tasks.load(store,task_id);rid=t['request_id'];s=store.read_snapshot();r=s['requests'][rid]
        if r['execution_state']=='CAPTURED':return execution.recover(store,rid)
        require(r['execution_state']=='PREPARED','EXISTING_REQUEST','Fake executors also cannot repeat uncertain sends')
        self._fault('AFTER_FREEZE')
        result=execution.reserve(store,rid,execution_kind='SYNTHETIC_TEST_ONLY')
        self._fault('AFTER_RESERVATION_BEFORE_SEND')
        self.calls+=1;raw=self.response_factory(t,store.read_snapshot())
        require(isinstance(raw,bytes),'RESPONSE_SCHEMA_INVALID','Fake returns exact response bytes')
        self._fault('AFTER_SEND_BEFORE_SENT')
        store.commit_execution(execution.event('SENT',{'request_id':rid,'execution_id':result['execution_id']}))
        execution.seal_capture(store,rid,raw,execution_id=result['execution_id'],usage={'calls':1,'test_only':True})
        self._fault('AFTER_CAPTURE_BLOB_BEFORE_RECEIPT')
        execution.capture(store,rid,raw,execution_id=result['execution_id'],usage={'calls':1,'test_only':True})
        self._fault('AFTER_CAPTURE_RECEIPT_BEFORE_ADMISSION')
        return execution.recover(store,rid)


class CodexExecutor:
    def __init__(self,binary='codex',timeout=1800):
        require(isinstance(timeout,(int,float)) and 0<timeout<=14400,'TIMEOUT_INVALID','Bounded timeout required')
        self.binary=binary;self.timeout=timeout
    def execute(self,store,task_id):
        t=tasks.load(store,task_id);rid=t['request_id'];s=store.read_snapshot();r=s['requests'][rid]
        if r['execution_state']=='CAPTURED':return execution.recover(store,rid)
        require(r['execution_state']=='PREPARED','EXISTING_REQUEST','Inspect uncertain requests; no automatic resend')
        require(t['executor_contract'].get('executor')=='codex' and t['executor_contract'].get('sandbox')=='required',
                'SAFETY_BOUNDARY_UNAVAILABLE','The frozen executor contract must explicitly select isolated Codex')
        probe=doctor(self.binary);require(probe['ready'],'SAFETY_BOUNDARY_UNAVAILABLE',str(probe.get('error','Codex is missing')))
        binary=probe['binary'];work=store.root/'runs'/task_id/'work'
        require(not work.exists(),'EXISTING_REQUEST','Do not replace prior execution work')
        work.mkdir(parents=True,mode=0o700)
        packet=store.read_blob(t['input_packet_ref']);prompt=store.read_blob(t['prompt_ref'])
        files={'task.json':canonical(t),'packet.json':packet,'prompt.md':prompt}
        context=t.get('report_context')
        if context:
            for name,h in context['files'].items():
                require('/' not in name and '\\' not in name and name not in {'.','..'},'PATH_INVALID','Report file name must be a basename')
                files['report-inputs/'+name]=store.read_blob(h)
        for name,data in files.items():immutable(work/name,data)
        response=work/'response.json';m=t['model_policy']
        from .model_policy import codex_arguments
        command=[binary,'--no-daemon','exec','--ignore-user-config','--ignore-rules','--skip-git-repo-check','--ephemeral','--json','--color','never',
                 '-C',str(work),*codex_arguments(t['model_policy_resolution']),'-o',str(response),*permissions(binary,work)]
        if context and context['role']=='REPORT_VISUAL':
            for page in context['pages']+context.get('context_pages',[]):
                command+=['--image',str(work/'report-inputs'/(page['id']+'.png'))]
        command+=['-']
        immutable(work.parent/'command.json',canonical(command))
        reservation=execution.reserve(store,rid,execution_kind='MODEL');eid=reservation['execution_id'];process=None;start=time.monotonic()
        try:
            with (work.parent/'events.jsonl').open('wb') as log,(work.parent/'stderr.log').open('wb') as err:
                process=subprocess.Popen(command,cwd=work,stdin=subprocess.PIPE,stdout=log,stderr=err,env=environment(),start_new_session=True)
                store.commit_execution(execution.event('SENT',{'request_id':rid,'execution_id':eid}))
                process.stdin.write(b'Read prompt.md, task.json and packet.json with every exact frozen source and body. Perform only this request and return the complete JSON contract.\n');process.stdin.close()
                while process.poll() is None:
                    require(time.monotonic()-start<self.timeout,'MODEL_TIMEOUT','Uncertain requests retain their reservations')
                    require(all(p.stat().st_size<=64*1024**2 for p in (work.parent/'events.jsonl',work.parent/'stderr.log')),'MODEL_LOG_LIMIT','Bounded output exceeded')
                    time.sleep(.1)
            require(process.returncode==0,'MODEL_PROCESS_FAILED',read(work.parent/'stderr.log',64*1024**2)[-3000:].decode(errors='replace'))
            for name,data in files.items():require(read(work/name,128*1024**2)==data,'ORIGINAL_BYTES_MISMATCH',name)
            raw=read(response,16*1024**2)
            immutable(work.parent/'capture.json',canonical({'task_id':task_id,'request_id':rid,'execution_id':eid,'response_sha256':sha(raw),
                'elapsed_seconds':time.monotonic()-start,'task_sha256':sha(canonical(t)),'command_sha256':sha(canonical(command))}))
            execution.capture(store,rid,raw,execution_id=eid,usage=None)
        except BaseException as exc:
            if process and process.poll() is None:
                try:os.killpg(process.pid,signal.SIGTERM);process.wait(timeout=3)
                except (ProcessLookupError,subprocess.TimeoutExpired):
                    if process.poll() is None:os.killpg(process.pid,signal.SIGKILL);process.wait()
            current=store.read_snapshot()['requests'][rid]
            if current['execution_state'] in {'RESERVED','SENT'}:
                store.commit_execution(execution.event('UNKNOWN',{'request_id':rid,'execution_id':eid,'reason':str(exc)}))
            raise
        return execution.recover(store,rid)


def recover_transport(store,task_id):
    t=tasks.load(store,task_id);s=store.read_snapshot();r=s['requests'][t['request_id']]
    if r['capture_ref']:return execution.recover(store,t['request_id'])
    root=store.root/'runs'/task_id;seal=json.loads(read(root/'capture.json'));raw=read(root/'work/response.json',16*1024**2)
    require(seal.get('execution_id')==r['execution_id'] and seal.get('task_id')==task_id
            and seal.get('task_sha256')==sha(canonical(t)) and seal.get('response_sha256')==sha(raw)
            and seal.get('command_sha256')==sha(read(root/'command.json')),'ORIGINAL_BYTES_MISMATCH','Original transport seal differs')
    for name,expected in {'task.json':canonical(t),'packet.json':store.read_blob(t['input_packet_ref']),'prompt.md':store.read_blob(t['prompt_ref'])}.items():
        require(read(root/'work'/name,128*1024**2)==expected,'ORIGINAL_BYTES_MISMATCH',name)
    execution.capture(store,t['request_id'],raw,execution_id=r['execution_id']);return execution.recover(store,t['request_id'])


@contextmanager
def coordinator(store):
    folder=store.root/'execution';folder.mkdir(exist_ok=True)
    fd=os.open(folder/'coordinator.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise PMRSError('COORDINATOR_BUSY','Another coordinator owns this project')
        yield
    finally:os.close(fd)


def run(store,*,instance_ids=None,instance_id=None,executor=None,max_tasks=32,policy=None):
    require(type(max_tasks) is int and 1<=max_tasks<=1000,'BATCH_INVALID','Explicit bounded task batch required')
    selected=instance_ids or ([instance_id] if instance_id else [])
    require(selected,'INSTANCE_SELECTOR_REQUIRED','Select authorized workflow instances')
    executor=executor or CodexExecutor();performed=[]
    policy=policy if policy is not None else {'max_workers':store.read_snapshot().get('max_workers',1),'mission_policies':True}
    with coordinator(store):
        while len(performed)<max_tasks:
            s=store.read_snapshot();plan=scheduler.plan(s,selected,policy)
            recovered=False
            for action in plan['actions']:
                if action['action']=='RECOVER':execution.recover(store,action['request_id']);recovered=True
            if recovered:continue
            reuse=[a['request_id'] for a in plan['actions'] if a['action']=='REUSE']
            if not reuse and plan['selected']:
                bounded=deepcopy_plan(plan,max_tasks-len(performed));made=scheduler.commit_dispatch(store,bounded,policy=policy)
                reuse=[r['request_id'] for r in made['prepared']]
            if not reuse:return {'state':'WAIT','tasks':performed,'reasons':plan['waits'],'model_calls':len(performed)}
            s=store.read_snapshot();tids=[s['requests'][rid]['task_id'] for rid in reuse[:max_tasks-len(performed)]]
            workers=min(policy.get('max_workers',1),len(tids))
            if workers==1:
                for tid in tids:executor.execute(store,tid);performed.append(tid)
            else:
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures={tid:pool.submit(executor.execute,store,tid) for tid in tids}
                    for tid,future in futures.items():future.result();performed.append(tid)
    return {'state':'BATCH_LIMIT','tasks':performed,'model_calls':len(performed)}

def deepcopy_plan(plan,limit):
    from copy import deepcopy
    p=deepcopy(plan);p['selected']=p['selected'][:limit];return p
