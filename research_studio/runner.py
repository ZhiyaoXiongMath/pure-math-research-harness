"""Bounded request executor; never advances workflow stages or manufactures duties."""
from pathlib import Path
from contextlib import contextmanager,ExitStack
from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
import base64,fcntl,json,os,shutil,signal,subprocess,tempfile,time
from .util import require,read,sha,canonical,immutable,PMRSError,safe_path
from . import tasks,execution,scheduler,resources,host_pool

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
        if r['execution_state']=='CAPTURED':return _recover_clean(store,rid)
        require(r['execution_state']=='PREPARED','EXISTING_REQUEST','Fake executors also cannot repeat uncertain sends')
        self._fault('AFTER_FREEZE')
        result=execution.reserve(store,rid,execution_kind='SYNTHETIC_TEST_ONLY')
        self._fault('AFTER_RESERVATION_BEFORE_SEND')
        if t.get('report_context',{}).get('statement_refs'):
            from copy import deepcopy
            t=deepcopy(t);t['report_context']['statement_bodies']={ref:store.read_blob(h).decode() for ref,h in t['report_context']['statement_refs'].items()}
        self.calls+=1;raw=self.response_factory(t,store.read_snapshot())
        require(isinstance(raw,bytes),'RESPONSE_SCHEMA_INVALID','Fake returns exact response bytes')
        self._fault('AFTER_SEND_BEFORE_SENT')
        store.commit_execution(execution.event('SENT',{'request_id':rid,'execution_id':result['execution_id']}))
        execution.seal_capture(store,rid,raw,execution_id=result['execution_id'],usage={'calls':1,'test_only':True})
        self._fault('AFTER_CAPTURE_BLOB_BEFORE_RECEIPT')
        execution.capture(store,rid,raw,execution_id=result['execution_id'],usage={'calls':1,'test_only':True})
        self._fault('AFTER_CAPTURE_RECEIPT_BEFORE_ADMISSION')
        return _recover_clean(store,rid)


def materialize_task_inputs(store, task, work, *, reserved=False):
    if reserved:return _materialize_task_inputs(store,task,work)
    with resources.reserve(store.root,owner='materialize-'+task['task_id'],temporary_bytes=256*resources.MIB,memory_bytes=resources.MAX_PREPARATION_MEMORY,max_preparations=min(2,store.read_snapshot().get('max_workers',1))):
        return _materialize_task_inputs(store,task,work)

def input_files(task):
    """One immutable work file per new material hash; preserve legacy layouts."""
    files={'packet.json':task['input_packet_ref'],'prompt.md':task['prompt_ref']}
    material_refs=task.get('material_refs',{})
    for digest,item in material_refs.items():
        path=item['path']
        require(item.get('sha256')==digest and path.startswith('materials/') and len(Path(path).parts)==2
                and Path(path).name not in {'.','..'},'PATH_INVALID','Frozen material needs a bounded relative path.')
        files[path]=digest
    for name,digest in task.get('report_context',{}).get('files',{}).items():
        require('/' not in name and '\\' not in name and name not in {'.','..'},'PATH_INVALID','Report input must be a basename')
        if digest not in material_refs:files['report-inputs/'+name]=digest
    return files


def report_input_path(task,name):
    digest=task.get('report_context',{}).get('files',{}).get(name)
    return task.get('material_refs',{}).get(digest,{}).get('path','report-inputs/'+name)


def input_manifest(store,task):
    body=resources.bounded_canonical(task,resources.METADATA_BYTES,code='CONTEXT_LIMIT')
    result={'task.json':{'sha256':sha(body),'bytes':len(body)}}
    for path,digest in input_files(task).items():result[path]={'sha256':digest,'bytes':resources.blob_info(store,digest)['bytes']}
    return result


def _materialize_task_inputs(store, task, work):
    """Prepare only frozen role inputs, one bounded independent file at a time."""
    work=Path(work)
    require(not work.exists(),'EXISTING_REQUEST','Do not replace prior execution work')
    body=resources.bounded_canonical(task,resources.METADATA_BYTES,code='CONTEXT_LIMIT')
    files=input_files(task)
    size=len(body);largest=len(body)
    for digest in files.values():
        info=resources.blob_info(store,digest);size+=info['bytes'];largest=max(largest,info['bytes'])
        require(info['bytes']<=resources.SERIALIZED_BYTES and size<=256*resources.MIB,'RESOURCE_LIMIT','Task working inputs exceed their bounded disk budget.')
    require(size+largest<=256*resources.MIB,'RESOURCE_LIMIT','Task input copies and atomic staging exceed the reserved disk budget.')
    resources.disk_preflight(store.root,size+largest)
    manifest={'task.json':{'sha256':sha(body),'bytes':len(body)}}
    work.mkdir(parents=True,mode=0o700)
    try:
        immutable(work/'task.json',body)
        for name,digest in files.items():
            copied=resources.copy_blob(store,digest,work/name)
            manifest[name]={'sha256':digest,'bytes':copied['bytes']}
        return {'files':manifest,'copied_bytes':size,'peak_copy_chunk_bytes':resources.CHUNK_BYTES}
    except BaseException:
        # This directory was newly created by this preparation, before any
        # reservation or remote send. It contains no capture evidence.
        shutil.rmtree(work)
        raise


def verify_task_inputs(work, manifest):
    for name,item in manifest.items():
        require(resources.hash_file(Path(work)/name,item['bytes'])==item['sha256'],
                'ORIGINAL_BYTES_MISMATCH','Frozen task material changed during execution.')


def cleanup_task_inputs(store,task_id):
    """Reclaim named reconstructible input copies only after sealed settlement."""
    from .util import safe_path,loads
    snapshot=store.read_snapshot();task=snapshot.get('tasks',{}).get(task_id)
    if not task:return {'removed_files':0,'removed_bytes':0,'protected':True}
    request=snapshot['requests'][task['request_id']]
    if request['execution_state']!='SETTLED' or not request.get('capture_ref'):
        return {'removed_files':0,'removed_bytes':0,'protected':True}
    work=safe_path(store.root,'runs/'+task_id+'/work')
    if not work.exists():return {'removed_files':0,'removed_bytes':0,'protected':False}
    seal_path=safe_path(store.root,'execution/captures/'+task['request_id']+'.json')
    if not seal_path.exists():return {'removed_files':0,'removed_bytes':0,'protected':True}
    seal=loads(read(seal_path))
    require(seal.get('task_id')==task_id and seal.get('request_id')==task['request_id']
            and seal.get('execution_id')==request['execution_id'] and seal.get('capture_ref')==request['capture_ref']
            and seal.get('task_digest')==sha(canonical(task)) and seal.get('input_manifest_hash')==task['input_manifest_hash'],
            'ORIGINAL_BYTES_MISMATCH','Settled task input cleanup requires its exact capture seal.')
    require(resources.hash_file(store.root/'blobs'/request['capture_ref'],16*resources.MIB)==request['capture_ref'],
            'ORIGINAL_BYTES_MISMATCH','Settled capture must remain intact before input cleanup.')
    files={'task.json':sha(canonical(task)),**input_files(task)}
    removed=0;size=0
    for name,digest in files.items():
        path=safe_path(store.root,'runs/'+task_id+'/work/'+name)
        if path.exists():
            require(resources.hash_file(path,resources.SERIALIZED_BYTES)==digest,'ORIGINAL_BYTES_MISMATCH','Do not delete changed task inputs as if they were a verified cache.')
            size+=resources.file_info(path)['bytes'];path.unlink();removed+=1
    folder=safe_path(store.root,'runs/'+task_id+'/work/report-inputs')
    if folder.exists():
        try:folder.rmdir()
        except OSError:pass  # Unknown user/task output is not an input cache.
    resources.release_owner(store.root,'work-'+task_id)
    return {'removed_files':removed,'removed_bytes':size,'protected':False}


def cleanup_task_inputs_safely(store,task_id):
    try:return cleanup_task_inputs(store,task_id)
    except (PMRSError,OSError,ValueError,KeyError):
        return {'state':'PRESERVED','warning':'Input cache cleanup was not completed; captured evidence and the original request outcome are preserved. No request was repeated.'}

def _recover_clean(store,request_id):
    return execution.recover(store,request_id)


def _paused_result(store,task_id):
    snapshot=store.read_snapshot();task=snapshot['tasks'][task_id];request=snapshot['requests'][task['request_id']]
    if task.get('purpose')=='PROJECT_ASSISTANT':return None
    if snapshot['instances'][task['instance_id']]['status']!='PAUSED' or request.get('fenced'):return None
    return {'state':'PAUSED','code':'TASK_FENCED','task_id':task_id,'request_id':task['request_id'],
            'capture_ref':request.get('capture_ref'),'requires_resume':True,'model_calls':0}


class CodexExecutor:
    def __init__(self,binary='codex',timeout=1800):
        require(isinstance(timeout,(int,float)) and 0<timeout<=14400,'TIMEOUT_INVALID','Bounded timeout required')
        self.binary=binary;self.timeout=timeout
    def execute(self,store,task_id):
        initial=store.read_snapshot();require(task_id in initial['tasks'],'TASK_UNKNOWN','Select an original frozen task.')
        initial_state=initial['requests'][initial['tasks'][task_id]['request_id']]['execution_state']
        try:
            with task_executor_lock(store,task_id):return self._execute(store,task_id)
        except PMRSError as exc:
            if exc.code=='TASK_FENCED':
                paused=_paused_result(store,task_id)
                if paused:
                    paused['model_calls']=int(initial_state=='PREPARED' and bool(paused.get('capture_ref')))
                    return paused
            if exc.code not in {'RESOURCE_WAIT','RESOURCE_DISK_LOW'}:raise
            snapshot=store.read_snapshot();task=snapshot['tasks'][task_id];request=snapshot['requests'][task['request_id']]
            busy=getattr(exc,'resource',None)=='ORIGINAL_EXECUTOR'
            retryable=busy or request['execution_state'] in {'PREPARED','CAPTURED'}
            calls=int(not busy and initial_state=='PREPARED' and request['execution_state'] in {'CAPTURED','SETTLED'})
            return {'state':'RESOURCE_WAIT' if retryable else request['execution_state'],'code':exc.code,
                    'message':str(exc),'request_id':task['request_id'],'task_id':task_id,'model_calls':calls,'retryable':retryable,
                    'resource':getattr(exc,'resource','PHYSICAL')}

    def _execute(self,store,task_id):
        snapshot=store.read_snapshot();frozen=snapshot['tasks'][task_id];rid=frozen['request_id'];request=snapshot['requests'][rid]
        if request['execution_state'] in {'CAPTURED','SETTLED'}:return _recover_clean(store,rid)
        require(request['execution_state']=='PREPARED','EXISTING_REQUEST','Inspect uncertain requests; no automatic resend')
        work=store.root/'runs'/task_id/'work';created=False;acquired=False
        with ExitStack() as physical:
            disk=physical.enter_context(resources.reserve(store.root,owner='work-'+task_id,temporary_bytes=256*resources.MIB,memory_bytes=0,phase='disk'))
            try:
                with resources.reserve(store.root,owner='prepare-'+task_id,temporary_bytes=0,memory_bytes=resources.MAX_PREPARATION_MEMORY,
                                       max_preparations=min(2,snapshot.get('max_workers',1))):
                    t=tasks.load(store,task_id)
                    require(t['executor_contract'].get('executor')=='codex' and t['executor_contract'].get('sandbox')=='required',
                            'SAFETY_BOUNDARY_UNAVAILABLE','The frozen executor contract must explicitly select isolated Codex')
                    probe=doctor(self.binary);require(probe['ready'],'SAFETY_BOUNDARY_UNAVAILABLE',str(probe.get('error','Codex is missing')))
                    binary=probe['binary']
                    if work.exists():
                        inputs={'files':input_manifest(store,t)};verify_task_inputs(work,inputs['files'])
                    else:inputs=materialize_task_inputs(store,t,work,reserved=True)
                    created=True
                    context=t.get('report_context');response=work/'response.json'
                    from .model_policy import codex_arguments
                    command=[binary,'--no-daemon','exec','--ignore-user-config','--ignore-rules','--skip-git-repo-check','--ephemeral','--json','--color','never',
                             '-C',str(work),*codex_arguments(t['model_policy_resolution']),'-o',str(response),*permissions(binary,work)]
                    if context and context['role']=='REPORT_VISUAL':
                        paths=dict.fromkeys(report_input_path(t,page['id']+'.png') for page in context['pages']+context.get('context_pages',[]))
                        for path in paths:command+=['--image',str(work/path)]
                    command+=['-'];immutable(work.parent/'command.json',canonical(command))
                # The expensive preparation objects are gone before waiting on a
                # model share. The client has a distinct, much smaller estimate.
                physical.enter_context(resources.reserve(store.root,owner='client-'+task_id,temporary_bytes=0,
                                      memory_bytes=resources.PHASE_MEMORY['client'],phase='client'))
                host_pool.acquire(store,rid);acquired=True
                with resources.reserve(store.root,owner='validate-'+task_id,temporary_bytes=0,memory_bytes=resources.MAX_PREPARATION_MEMORY):
                    reservation=execution.reserve(store,rid,execution_kind='MODEL')
                eid=reservation['execution_id'];host_pool.mark(store,rid,'RESERVED')
                process=None;start=time.monotonic();last_resource_check=start
                try:
                    with (work.parent/'events.jsonl').open('wb') as log,(work.parent/'stderr.log').open('wb') as err:
                        process=subprocess.Popen(command,cwd=work,stdin=subprocess.PIPE,stdout=log,stderr=err,env=environment(),start_new_session=True)
                        store.commit_execution(execution.event('SENT',{'request_id':rid,'execution_id':eid}));host_pool.mark(store,rid,'SENT')
                        process.stdin.write(tasks.INPUT_BOOTSTRAP.encode());process.stdin.close()
                        while process.poll() is None:
                            require(time.monotonic()-start<self.timeout,'MODEL_TIMEOUT','Uncertain requests retain their reservations')
                            require(all(p.stat().st_size<=64*1024**2 for p in (work.parent/'events.jsonl',work.parent/'stderr.log')),'MODEL_LOG_LIMIT','Bounded output exceeded')
                            if time.monotonic()-last_resource_check>=1:
                                resources.directory_usage(work.parent,max_bytes=256*resources.MIB,max_files=4096);last_resource_check=time.monotonic()
                            time.sleep(.1)
                    require(process.returncode==0,'MODEL_PROCESS_FAILED',read(work.parent/'stderr.log',64*1024**2)[-3000:].decode(errors='replace'))
                    verify_task_inputs(work,inputs['files'])
                    response_digest=resources.hash_file(response,16*1024**2)
                    immutable(work.parent/'capture.json',canonical({'task_id':task_id,'request_id':rid,'execution_id':eid,'response_sha256':response_digest,
                        'elapsed_seconds':time.monotonic()-start,'task_sha256':sha(canonical(t)),'command_sha256':sha(canonical(command))}))
                    with resources.reserve(store.root,owner='capture-'+task_id,temporary_bytes=0,
                                           memory_bytes=resources.PHASE_MEMORY['capture'],phase='capture'):
                        raw=read(response,16*1024**2)
                        require(sha(raw)==response_digest,'ORIGINAL_BYTES_MISMATCH','Completed response differs from its transport seal.')
                        execution.capture(store,rid,raw,execution_id=eid,usage=None)
                        del raw
                except BaseException as exc:
                    if process and process.poll() is None:
                        try:os.killpg(process.pid,signal.SIGTERM);process.wait(timeout=3)
                        except (ProcessLookupError,subprocess.TimeoutExpired):
                            if process.poll() is None:os.killpg(process.pid,signal.SIGKILL);process.wait()
                    current=store.read_snapshot()['requests'][rid]
                    if current['execution_state'] in {'RESERVED','SENT'}:
                        store.commit_execution(execution.event('UNKNOWN',{'request_id':rid,'execution_id':eid,'reason':str(exc)}));host_pool.mark(store,rid,'UNKNOWN')
                    raise
                # Capture has released the model slot. Admission uses its own
                # lease, and can be resumed later without a new model call.
                return {**_recover_clean(store,rid),'model_calls':1}
            finally:
                current=store.read_snapshot()['requests'][rid]
                if current['execution_state']=='PREPARED':
                    if acquired:host_pool.release(store,rid,before_send=True)
                    if created:shutil.rmtree(work)
                elif current['execution_state']!='SETTLED':disk['retain']=True


def recover_transport(store,task_id):
    with task_executor_lock(store,task_id):
        with resources.reserve(store.root,owner='transport-recovery-'+task_id,temporary_bytes=0,
                               memory_bytes=resources.PHASE_MEMORY['capture'],phase='capture'):
            t=tasks.load(store,task_id);s=store.read_snapshot();r=s['requests'][t['request_id']]
            if not r['capture_ref']:
                root=store.root/'runs'/task_id;seal=json.loads(read(root/'capture.json'));raw=read(root/'work/response.json',16*1024**2)
                require(seal.get('execution_id')==r['execution_id'] and seal.get('task_id')==task_id
                        and seal.get('task_sha256')==sha(canonical(t)) and seal.get('response_sha256')==sha(raw)
                        and seal.get('command_sha256')==sha(read(root/'command.json')),'ORIGINAL_BYTES_MISMATCH','Original transport seal differs')
                verify_task_inputs(root/'work',input_manifest(store,t))
                execution.capture(store,t['request_id'],raw,execution_id=r['execution_id']);del raw
        return _recover_clean(store,t['request_id'])


@contextmanager
def task_executor_lock(store,task_id):
    folder=safe_path(store.root,'runs/'+task_id);folder.mkdir(parents=True,exist_ok=True)
    fd=os.open(folder/'executor.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            exc=PMRSError('RESOURCE_WAIT','Another local executor is continuing this exact original request.')
            exc.resource='ORIGINAL_EXECUTOR';raise exc
        yield
    finally:os.close(fd)


@contextmanager
def coordinator(store):
    folder=store.root/'execution';folder.mkdir(exist_ok=True)
    fd=os.open(folder/'coordinator.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise PMRSError('COORDINATOR_BUSY','Another coordinator owns this project')
        yield
    finally:os.close(fd)


def run(store,*,instance_ids=None,instance_id=None,executor=None,max_tasks=32,policy=None,
        on_result=None,on_idle=None,on_tick=None):
    """Completion-driven bounded driver; waits never allocate a new request."""
    require(type(max_tasks) is int and 1<=max_tasks<=1000,'BATCH_INVALID','Explicit bounded task batch required')
    require(instance_ids is not None or instance_id is not None,'INSTANCE_SELECTOR_REQUIRED','Select authorized workflow instances')
    selected=instance_ids if instance_ids is not None else [instance_id]
    if not selected:return {'state':'PAUSED','tasks':[],'reasons':[],'waiting_requests':[],'model_calls':0}
    executor=executor or CodexExecutor();performed=[];attempted=set();pending_waits={};retry_at={};inflight={};last_tick=0;plan_retries=0
    initial=store.read_snapshot()
    initial_sent={rid for rid,r in initial.get('requests',{}).items() if r['execution_state']!='PREPARED'}
    policy=policy if policy is not None else {'max_workers':initial.get('max_workers',1),'mission_policies':True}
    workers=min(host_pool.PROJECT_LIMIT,policy.get('max_workers',1))
    def result(state,reasons=()):
        snapshot=store.read_snapshot()
        sent=sum(rid not in initial_sent and r['task_id'] in attempted and r['execution_state']!='PREPARED' for rid,r in snapshot.get('requests',{}).items())
        return {'state':state,'tasks':performed,'reasons':list(reasons),'model_calls':sent,
                'waiting_requests':[x for x in pending_waits.values()]}
    try:
        with coordinator(store),ThreadPoolExecutor(max_workers=workers) as pool:
            while True:
                now=time.monotonic()
                if on_tick and now-last_tick>=.5:on_tick(store);last_tick=now
                snapshot=store.read_snapshot();plan=scheduler.plan(snapshot,selected,policy)
                for tid,row in list(pending_waits.items()):
                    if tid not in snapshot['tasks']:continue
                    request=snapshot['requests'][snapshot['tasks'][tid]['request_id']]
                    if request['execution_state']=='SETTLED':
                        pending_waits.pop(tid,None)
                        if tid not in performed:performed.append(tid)
                        if on_result:on_result(store,tid,{'state':request['acceptance_state'],'model_calls':0,'recovered_elsewhere':True})
                    elif request.get('fenced') or snapshot['instances'][request['instance_id']]['status']!='ACTIVE':pending_waits.pop(tid,None)
                host_pool.update_demand(store,int(plan.get('ready_demand',workers)),project_limit=workers)
                active_tids=set(inflight.values());ready=[];queued=0
                for action in plan['actions']:
                    if action['action'] not in {'REUSE','RECOVER'}:continue
                    tid=snapshot['requests'][action['request_id']]['task_id']
                    if tid in active_tids:continue
                    if tid not in attempted and len(attempted)>=max_tasks:continue
                    queued+=1
                    if now<retry_at.get(tid,0):continue
                    ready.append(tid)
                capacity=max(0,workers-len(inflight)-queued)
                fresh=min(capacity,max_tasks-len(attempted)-sum(t not in attempted for t in ready))
                if fresh>0 and plan['selected'] and plan_retries<=3:
                    try:
                        made=scheduler.commit_dispatch(store,deepcopy_plan(plan,fresh),policy=policy)
                        ready.extend(row['task_id'] for row in made['prepared'])
                        plan_retries=0
                    except PMRSError as exc:
                        if exc.code in {'STALE_READ','STALE_OBLIGATION_DEFINITION','WRITE_CAS_CONFLICT'}:
                            # An admission may finish between the read-only plan
                            # and PREPARE CAS. Re-read; any already frozen rows
                            # remain original REUSE requests, never new attempts.
                            plan_retries+=1
                            if plan_retries<=3:continue
                            pending_waits['prepare']={'state':'RESOURCE_WAIT','code':exc.code,'message':str(exc),
                                                      'model_calls':0,'resource':'PLAN_CONTENTION'}
                            continue
                        if exc.code not in {'RESOURCE_WAIT','RESOURCE_DISK_LOW'}:raise
                        pending_waits['prepare']={'state':'RESOURCE_WAIT','code':exc.code,'message':str(exc),'model_calls':0,
                                                  'resource':getattr(exc,'resource','PHYSICAL')}
                for tid in ready[:max(0,workers-len(inflight))]:
                    inflight[pool.submit(executor.execute,store,tid)]=tid;attempted.add(tid)
                if not inflight:
                    if not any(snapshot['instances'][iid]['status']=='ACTIVE' for iid in selected):return result('PAUSED')
                    if on_idle and on_idle(store):continue
                    if pending_waits and all(row.get('resource') in {'MODEL_SLOT','PREPARATION_SLOT','ORIGINAL_EXECUTOR'} for row in pending_waits.values()):
                        status=host_pool.status()
                        if not status['slots'] or any(row['state']!='UNKNOWN' and host_pool.alive(row) for row in status['slots']):
                            time.sleep(.5);continue
                    if pending_waits:return result('RESOURCE_WAIT',plan['waits'])
                    return result('BATCH_LIMIT' if len(attempted)>=max_tasks else 'WAIT',plan['waits'])
                completed,_=wait(inflight,timeout=.5,return_when=FIRST_COMPLETED)
                if not completed:continue
                progressed=False
                for future in completed:
                    tid=inflight.pop(future)
                    try:value=future.result()
                    except PMRSError as exc:
                        value=_paused_result(store,tid) if exc.code=='TASK_FENCED' else None
                        if value is None:raise
                    if value.get('state')=='RESOURCE_WAIT':
                        pending_waits[tid]=value;retry_at[tid]=time.monotonic()+.5;continue
                    pending_waits.pop(tid,None);pending_waits.pop('prepare',None)
                    if tid not in performed:performed.append(tid)
                    progressed=True
                    plan_retries=0
                    if on_result:on_result(store,tid,value)
                # No active client can free this transient resource here. Yield
                # to the owning Web/CLI/report driver rather than spin or resend.
                if not inflight and not progressed and pending_waits and any(row.get('resource') not in {'MODEL_SLOT','PREPARATION_SLOT','ORIGINAL_EXECUTOR'} for row in pending_waits.values()):
                    return result('RESOURCE_WAIT')
    finally:host_pool.clear_demand(store)


def deepcopy_plan(plan,limit):
    from copy import deepcopy
    p=deepcopy(plan);p['selected']=p['selected'][:limit];return p
