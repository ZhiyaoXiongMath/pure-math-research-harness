"""Persistent Codex MAIN, native Goal state, and pre-sampling turn admission.

The separately built native app-server has one small root-turn admission hook.
The hook never applies to native subagents. A native continuation consumes one
already authorized PMRS request before sampling; Goal status is not a budget.
"""
from copy import deepcopy
from pathlib import Path
import fcntl,json,os,queue,secrets,signal,socket,subprocess,tempfile,threading,time
from .util import canonical,identity,immutable,now,read,require,sha,PMRSError

SCHEMA='pmrs.native-main/1'
GATE_REVISION='pmrs.native-admission/1'
MAPS=frozenset({'native_main_bindings','native_main_events','native_main_turns'})
EVENT_TYPES={'NATIVE_MAIN_BOUND','NATIVE_GOAL_SYNCED','NATIVE_GOAL_ERROR','NATIVE_TURN_BOUND','NATIVE_CONTINUATION_BLOCKED','NATIVE_USAGE_SNAPSHOT'}
_SERVICES={}
_SERVICES_LOCK=threading.RLock()


def event(kind,payload):
    p=deepcopy(payload);p.setdefault('observed_at',now())
    e={'actor':'host','capability_ref':'CAP-HOST','event_type':kind,'payload':p}
    e['event_id']=identity(e,'NATIVE-MAIN-EVENT-');return e


def desired(snapshot,iid):
    i=snapshot['instances'][iid];c=i.get('run_control',{});mid=i.get('current_mission_id')
    mission=snapshot.get('missions',{}).get(mid)
    from .scheduler import budget_remaining,project_remaining
    remaining=min(budget_remaining(snapshot,mission['budget_grant_id']),project_remaining(snapshot)) if mission else 0
    reason=(c.get('waiting_reason') or c.get('pause_reason') or i.get('pause_reason') or i.get('status'))
    if i.get('status')=='COMPLETE':
        decision=snapshot.get('main_decisions',{}).get(c.get('last_decision_ref'),{})
        if decision.get('action')=='COMPLETE' and decision.get('qualified_evidence'):return 'complete','QUALIFIED_SCIENTIFIC_COMPLETION'
    if i.get('status')!='ACTIVE' or not mission:return 'paused',str(reason or 'NO_ACTIVE_AUTHORIZATION')
    prepaid=any(r['instance_id']==iid and r.get('mission_id')==mid and r['execution_state'] in {'RESERVED','SENT'} and not r.get('fenced') and snapshot['tasks'][r['task_id']].get('actor_kind')=='MAIN' for r in snapshot.get('requests',{}).values())
    if remaining<=0 and not prepaid:return 'paused','BUDGET_EXHAUSTED'
    return 'active',None


def apply_event(snapshot,e):
    require(e.get('actor')=='host' and snapshot.get('capabilities',{}).get(e.get('capability_ref'),{}).get('actor')=='host',
            'AUTHORIZATION_REQUIRED','Native MAIN observations require host authority.')
    require(e.get('event_type') in EVENT_TYPES,'NATIVE_MAIN_EVENT_INVALID','Unsupported native event')
    prior=snapshot.get('native_main_events',{}).get(e['event_id'])
    if prior:require(prior==e,'NATIVE_MAIN_IDENTITY_CONFLICT','Native event differs');return deepcopy(snapshot)
    s=deepcopy(snapshot);p=e['payload'];iid=p['instance_id'];i=s['instances'].get(iid)
    require(i and i['kind'] in {'TRH','FDH'},'MAIN_NOT_APPLICABLE','Native MAIN belongs to a harness instance')
    kind=e['event_type'];b=s.setdefault('native_main_bindings',{}).get(iid)
    if kind=='NATIVE_MAIN_BOUND':
        incoming=p['binding'];require(incoming['instance_id']==iid and incoming['thread_id'],'NATIVE_MAIN_IDENTITY_CONFLICT','Exact native thread required')
        if b:require(b['thread_id']==incoming['thread_id'] and b['objective_sha256']==incoming['objective_sha256'],'NATIVE_MAIN_IDENTITY_CONFLICT','Do not replace persistent MAIN or Goal')
        else:
            require(not any(x['thread_id']==incoming['thread_id'] for x in s['native_main_bindings'].values()),'NATIVE_MAIN_IDENTITY_CONFLICT','Native thread cannot be shared')
            b=deepcopy(incoming);s['native_main_bindings'][iid]=b
    elif kind=='NATIVE_TURN_BOUND':
        from . import execution,scheduler
        require(b and p['thread_id']==b['thread_id'],'NATIVE_MAIN_IDENTITY_CONFLICT','Exact persistent thread required')
        r=s['requests'][p['request_id']];t=s['tasks'][r['task_id']]
        require(t.get('actor_kind')=='MAIN' and r['instance_id']==iid and r['execution_state']=='RESERVED','NATIVE_TURN_UNAUTHORIZED','One reserved MAIN request required')
        require(i['status']=='ACTIVE' and r['mission_id']==i.get('current_mission_id') and not r.get('fenced'),'TASK_FENCED','Current control does not admit research')
        scheduler.validate_task_control(s,t)
        require(p['control_version']==i.get('run_control',{}).get('control_version',0),'TASK_FENCED','Control changed before native admission')
        key=identity([p['thread_id'],p['turn_id']],'NATIVE-TURN-')
        require(key not in s.setdefault('native_main_turns',{}) and not any(x['request_id']==r['request_id'] for x in s['native_main_turns'].values()),'NATIVE_TURN_UNAUTHORIZED','A request admits exactly one native root turn')
        s=execution.apply_event(s,execution.event('SENT',{'request_id':r['request_id'],'execution_id':r['execution_id'],'issued_at':p['observed_at']}))
        s['native_main_turns'][key]=deepcopy(p);b=s['native_main_bindings'][iid];b['last_turn']=deepcopy(p)
    elif kind=='NATIVE_USAGE_SNAPSHOT':
        require(b and p['thread_id']==b['thread_id'],'NATIVE_MAIN_IDENTITY_CONFLICT','Usage belongs to bound MAIN thread')
        b['last_token_usage']=deepcopy(p)
    elif kind in {'NATIVE_GOAL_SYNCED','NATIVE_GOAL_ERROR','NATIVE_CONTINUATION_BLOCKED'}:
        if b:
            if p.get('thread_id'):require(p['thread_id']==b['thread_id'],'NATIVE_MAIN_IDENTITY_CONFLICT','Wrong observed native thread')
            b['last_sync']=deepcopy(p);b['last_sync']['event_type']=kind
            if kind=='NATIVE_GOAL_ERROR' and p.get('code') in {'NATIVE_GOAL_SCOPE_CHANGED','NATIVE_GOAL_MISSING'}:b['scope_error']=deepcopy(p)
            if kind=='NATIVE_GOAL_SYNCED':
                goal=p.get('goal')
                require(goal is None or (goal.get('threadId')==b['thread_id'] and sha(goal['objective'].encode())==b['objective_sha256']),
                        'NATIVE_GOAL_SCOPE_CHANGED','The original Goal objective changed')
                if goal:
                    require(b.get('goal_created_at',goal.get('createdAt'))==goal.get('createdAt'),'NATIVE_GOAL_SCOPE_CHANGED','Do not replace the original Goal identity')
                    b.setdefault('goal_created_at',goal.get('createdAt'))
                b['observed_goal']=deepcopy(goal);b['last_observation']=deepcopy(p);b['control_revision']=p.get('control_version')
    s.setdefault('native_main_events',{})[e['event_id']]=deepcopy(e);return s


def view(snapshot,iid):
    b=deepcopy(snapshot.get('native_main_bindings',{}).get(iid));want,reason=desired(snapshot,iid)
    g=(b or {}).get('observed_goal') or {}
    last_sync=(b or {}).get('last_sync')
    if not last_sync:
        observations=[e['payload'] for e in snapshot.get('native_main_events',{}).values() if e['payload'].get('instance_id')==iid and e['event_type']=='NATIVE_GOAL_ERROR']
        last_sync=max(observations,key=lambda x:x.get('observed_at',''),default=None)
    return {'schema':SCHEMA,'binding':b,'thread_id':(b or {}).get('thread_id'),'goal_id':None,
        'goal_identity':{'thread_id':g.get('threadId'),'created_at':g.get('createdAt'),'objective_sha256':(b or {}).get('objective_sha256')} if g else None,
        'desired_status':want,'observed_status':g.get('status','UNOBSERVED'),'observed_goal':g or None,
        'last_sync':last_sync,'last_observation':(b or {}).get('last_observation'),'control_revision':snapshot['instances'][iid].get('run_control',{}).get('control_version',0),
        'wait_reason':reason,'continuation_gate':{'revision':GATE_REVISION,'required':True,'scope':'ROOT_MAIN_ONLY','native_internal_limits':None},
        'goal_id_semantics':'Native API exposes threadId and createdAt, not an opaque Goal ID.',
        'turns':[deepcopy(t) for t in snapshot.get('native_main_turns',{}).values() if t['instance_id']==iid]}


def native_binary():
    path=Path(os.environ.get('PMRS_NATIVE_MAIN_BINARY',str(Path(__file__).parent/'native'/'codex-app-server')))
    require(path.is_file() and os.access(path,os.X_OK),'NATIVE_CLIENT_UNAVAILABLE','The isolated PMRS native app-server build is required; no exec fallback.')
    manifest=path.parent/'manifest.json';require(manifest.is_file(),'NATIVE_CLIENT_UNVERIFIED','Native build manifest is required')
    m=json.loads(read(manifest));require(m.get('gate_revision')==GATE_REVISION and m.get('binary_sha256')==sha(path.read_bytes()),'NATIVE_CLIENT_UNVERIFIED','Native app-server or admission patch differs from build manifest')
    host=path.parent/'codex-code-mode-host'
    require(host.is_file() and os.access(host,os.X_OK),'NATIVE_TOOL_HOST_UNAVAILABLE','The matching isolated codex-code-mode-host is required before any MAIN request admission')
    require(m.get('code_mode_host_sha256')==sha(host.read_bytes()),'NATIVE_CLIENT_UNVERIFIED','Native code-mode host differs from the separately recorded official sidecar manifest')
    return str(path.resolve()),m


def _objective(snapshot,task):
    i=snapshot['instances'][task['instance_id']];target=i.get('target_ref');record=snapshot.get('records',{}).get(target,{})
    method=task.get('method_manual') or task.get('strategy_context',{}).get('method_manual',{})
    require(method,'NATIVE_METHOD_MISSING','Full MAIN method identity is required')
    binding={'instance_id':task['instance_id'],'main_actor_id':'MAIN-'+task['instance_id'],'workflow_kind':i['kind'],
        'target_ref':target,'target_record_sha256':sha(canonical(record)),'original_mission_id':task['mission_id'],
        'budget_grant_id':snapshot.get('missions',{}).get(task.get('mission_id'),{}).get('budget_grant_id'),'authorization_ledger':'PMRS native instance controls and grants: '+task['instance_id'],'method_sha256':sha(canonical(method))}
    if i['kind']=='FDH':
        from .workflow_instances import validate_discovery_scope
        scope=validate_discovery_scope(snapshot,i)
        binding['d0_scope']={k:{'source_ref':ref,'record_sha256':sha(canonical(snapshot['sources'][ref]))} for k,ref in scope.items()}
    scope='Prove or strictly refute the exact original TRH target under its original hypotheses' if i['kind']=='TRH' else 'Explore the exact D0 scope and produce evidenced candidate formulations and comparisons for human choice'
    objective=(scope+'. Acceptance requires the native PMRS scientific qualifications and exact supporting records, not a progress summary or stage completion. '
        'Read the full original objective, authorized materials and full current method handbook supplied in every PMRS turn. '
        'MAIN owns dynamic scientific planning and may freely use native internal delegation. Original authorization and cumulative PMRS top-level budget remain binding. '
        'TRH automatic P14 continues this same Goal; human P14/stop-next arrival and formal FDH D5 human choice pause until explicit human continuation. '
        'User ending, unresolved mathematics, software failure and budget exhaustion do not mean successful completion. '
        'Do not replace this Goal or its objective; the host synchronizes control from native research evidence. Exact original scope and authorization bindings: '+canonical(binding).decode())
    require(len(objective)<=4000,'NATIVE_GOAL_SCOPE_TOO_LARGE','Goal scope binding exceeds native limit')
    return objective,binding


def _workspace_permissions(binary,scratch,input_root):
    from . import runner
    args=runner.permissions(binary,scratch,'MAIN')
    fs={':minimal':'read',':workspace_roots':'write',str(Path(binary).resolve().parent):'read',str(input_root.resolve()):'read'}
    value='permissions.research-task.filesystem={'+','.join(json.dumps(k)+'='+json.dumps(v) for k,v in fs.items())+'}'
    return [value if item.startswith('permissions.research-task.filesystem=') else item for item in args]


class Rpc:
    def __init__(self,command,env,cwd,log_path,stderr_path,callback,lock_fd):
        self.callback=callback;self.waiters={};self.serial=0;self.lock=threading.RLock();self.log_lock=threading.Lock()
        self.log=Path(log_path).open('ab',buffering=0);self.err=Path(stderr_path).open('ab',buffering=0)
        self.process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.err,cwd=cwd,env=env,pass_fds=(lock_fd,),start_new_session=True)
        threading.Thread(target=self._read,daemon=True).start()
    def _record(self,direction,value):
        with self.log_lock:self.log.write(canonical({'direction':direction,'at':now(),'message':value})+b'\n')
    def send(self,row):
        with self.lock:
            self._record('OUT',row);self.process.stdin.write(canonical(row)+b'\n');self.process.stdin.flush()
    def _read(self):
        try:
            for raw in self.process.stdout:
                row=json.loads(raw);self._record('IN',row)
                if 'id' in row and 'method' not in row:
                    waiter=self.waiters.get(row['id'])
                    if waiter:waiter.put(row)
                else:self.callback(row)
        except Exception as exc:
            self.callback({'method':'pmrs/transportError','params':{'message':str(exc)}})
        finally:
            for waiter in list(self.waiters.values()):waiter.put({'error':{'message':'Native app-server transport closed'}})
    def call(self,method,params,timeout=45):
        with self.lock:
            self.serial+=1;mid=self.serial;q=queue.Queue();self.waiters[mid]=q
            self.send({'jsonrpc':'2.0','id':mid,'method':method,'params':params})
        try:row=q.get(timeout=timeout)
        except queue.Empty:raise PMRSError('NATIVE_RPC_TIMEOUT',method)
        finally:self.waiters.pop(mid,None)
        require('error' not in row,'NATIVE_RPC_ERROR',method+': '+str(row.get('error'))[:1500]);return row.get('result',{})


    def close_unstarted(self):
        """Dispose only a failed/control-only process that never resumed research."""
        try:
            try:self.process.stdin.close()
            except (OSError,ValueError):pass
            try:self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # This private process group has never admitted a root turn;
                # it cannot own live research or native internal agents.
                try:os.killpg(self.process.pid,signal.SIGTERM)
                except ProcessLookupError:pass
                try:self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:os.killpg(self.process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    self.process.wait(timeout=5)
        finally:
            self.err.close()


class Service:
    def __init__(self,store,iid,task,work):
        from . import runner,task_tools
        binary,manifest=native_binary()
        self.store=store;self.iid=iid;self.active=None;self.turns={};self.delegates={};self.thread_id=None;self.done=threading.Event();self.result=None;self.gate_lock=threading.Lock();self.closing=threading.Event();self.last_usage={}
        self.folder=store.root/'execution'/'native-main'/iid;self.folder.mkdir(parents=True,exist_ok=True)
        self.input_root=self.folder/'inputs';self.input_root.mkdir(exist_ok=True)
        self.work=self.folder/'scratch';self.work.mkdir(exist_ok=True)
        work=self.work
        self.lock_fd=os.open(self.folder/'owner.lock',os.O_CREAT|os.O_RDWR,0o600)
        try:fcntl.flock(self.lock_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:os.close(self.lock_fd);raise PMRSError('NATIVE_MAIN_BUSY','Original native MAIN process retains the instance ownership lock')
        try:
            self.socket_dir=tempfile.TemporaryDirectory(prefix='pmrs-main-');self.socket_path=str(Path(self.socket_dir.name)/'gate.sock')
            self.gate=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.gate.bind(self.socket_path);os.chmod(self.socket_path,0o600);self.gate.listen(8);self.gate.settimeout(1)
            threading.Thread(target=self._gate_loop,daemon=True).start()
            self.manifest=manifest
            env=runner.environment();env['PMRS_NATIVE_MAIN_GATE']=self.socket_path
            command=[binary,'--ignore-user-config','--ignore-rules','--session-source','exec',*_workspace_permissions(binary,work,self.input_root),
                '-c','model="gpt-6-astra"','-c','model_reasoning_effort="ultra"','-c','model_context_window='+str(task['executor_contract']['model_context_window']),'-c','mcp_servers={}']
            self.command=command
            self.rpc=Rpc(command,env,work,self.folder/'protocol.jsonl',self.folder/'stderr.log',self._notification,self.lock_fd)
            self.rpc.call('initialize',{'clientInfo':{'name':'pmrs422_native_main','version':'4.2.2'},'capabilities':{'experimentalApi':True}})
            self.rpc.send({'jsonrpc':'2.0','method':'initialized','params':{}})
            b=store.read_snapshot().get('native_main_bindings',{}).get(iid)
            if b:
                self.thread_id=b['thread_id'];self.last_usage=deepcopy(b.get('last_token_usage',{}).get('counts',{}))
            else:
                defs=[{'type':'function',**d} for d in task_tools.tool_definitions('MAIN')]
                result=self.rpc.call('thread/start',{'model':'gpt-6-astra','cwd':str(work),'approvalPolicy':'never','permissions':'research-task',
                    'ephemeral':False,'runtimeWorkspaceRoots':[str(work)],'dynamicTools':defs,'developerInstructions':runner.client_profile_body('MAIN').decode(),
                    'config':{'model_reasoning_effort':'ultra','model_context_window':task['executor_contract']['model_context_window']}})
                self.thread_id=result['thread']['id'];objective,scope=_objective(store.read_snapshot(),task)
                binding={**scope,'thread_id':self.thread_id,'objective':objective,'objective_sha256':sha(objective.encode()),'created_at':now(),
                    'native_client':manifest,'thread_start_evidence_ref':store.put_blob(canonical(result)),'observed_goal':None}
                store.commit_native_main(event('NATIVE_MAIN_BOUND',{'instance_id':iid,'binding':binding}))
                # No active Goal until a PMRS request has acquired its single-use gate.
                answer=self.rpc.call('thread/goal/set',{'threadId':self.thread_id,'objective':objective,'status':'paused'})
                self._goal_observed(answer.get('goal'),'CREATE_PAUSED')
        except BaseException:
            # Startup has not admitted any research turn. Close only this failed
            # control transport; never interrupt an existing native MAIN owner.
            self.closing.set()
            try:
                if hasattr(self,'gate'):self.gate.close()
                if hasattr(self,'rpc'):self.rpc.close_unstarted()
            finally:
                # No research turn was admitted by this failed constructor.
                # Unlock the shared description even if a control child is
                # still exiting, so its inherited fd cannot poison retries.
                fcntl.flock(self.lock_fd,fcntl.LOCK_UN);os.close(self.lock_fd)
                if hasattr(self,'socket_dir'):self.socket_dir.cleanup()
            raise
    def _goal_observed(self,goal,operation):
        s=self.store.read_snapshot();binding=s.get('native_main_bindings',{}).get(self.iid)
        if goal and binding and (sha(goal.get('objective','').encode())!=binding['objective_sha256'] or binding.get('goal_created_at',goal.get('createdAt'))!=goal.get('createdAt')):
            self.store.commit_native_main(event('NATIVE_GOAL_ERROR',{'instance_id':self.iid,'thread_id':self.thread_id,'code':'NATIVE_GOAL_SCOPE_CHANGED','operation':operation,'actual_goal':goal,'evidence_ref':self.store.put_blob(canonical({'goal':goal})),'message':'Native Goal objective differs from the original scope; do not reset or silently continue.'}))
            return
        p={'instance_id':self.iid,'thread_id':self.thread_id,'goal':goal,'operation':operation,
            'control_version':s['instances'][self.iid].get('run_control',{}).get('control_version',0),'evidence_ref':self.store.put_blob(canonical({'goal':goal}))}
        self.store.commit_native_main(event('NATIVE_GOAL_SYNCED',p))
    def _error(self,code,message):
        self.store.commit_native_main(event('NATIVE_GOAL_ERROR',{'instance_id':self.iid,'thread_id':self.thread_id,'code':code,'message':str(message)[:4000]}))
    def _gate_loop(self):
        while not self.closing.is_set():
            try:conn,_=self.gate.accept()
            except socket.timeout:continue
            except OSError:return
            with conn:
                try:
                    incoming=json.loads(conn.makefile('rb').readline(65536));answer=self._admit(incoming)
                except Exception as exc:answer={'allow':False,'reason':str(exc)}
                conn.sendall(canonical(answer)+b'\n')
    def _admit(self,p):
        from . import execution
        with self.gate_lock:
            a=self.active
            require(p.get('gate_revision')==GATE_REVISION and p.get('thread_id')==self.thread_id,'NATIVE_TURN_UNAUTHORIZED','Root thread/admission revision mismatch')
            if not a or a.get('admitted'):
                self.store.commit_native_main(event('NATIVE_CONTINUATION_BLOCKED',{'instance_id':self.iid,'thread_id':self.thread_id,'turn_id':p.get('turn_id'),'reason':'NO_UNUSED_PMRS_RESERVATION','goal_kept_active':True}))
                return {'allow':False,'reason':'No unused PMRS top-level request; wait for the product event admission.'}
            s=self.store.read_snapshot();r=s['requests'][a['request_id']]
            require(not s['native_main_bindings'][self.iid].get('scope_error'),'NATIVE_GOAL_SCOPE_CHANGED','Native Goal scope drift blocks new root turns')
            require(r['execution_state']=='RESERVED','NATIVE_TURN_UNAUTHORIZED','Original reserved request required')
            payload={'instance_id':self.iid,'thread_id':self.thread_id,'turn_id':p['turn_id'],'request_id':a['request_id'],
                'execution_id':r['execution_id'],'control_version':s['instances'][self.iid].get('run_control',{}).get('control_version',0),
                'turn_trigger':p.get('turn_trigger'),'gate_revision':GATE_REVISION,'input_ref':a['input_ref']}
            self.store.commit_native_main(event('NATIVE_TURN_BOUND',payload));a['admitted']=True;a['turn_id']=p['turn_id'];self.turns[p['turn_id']]=a;a['admission'].set()
            return {'allow':True,'request_id':a['request_id'],'additional_context':self.store.read_blob(a['input_ref']).decode()}
    def _notification(self,row):
        method=row.get('method');p=row.get('params',{})
        if method=='thread/started':
            child=p.get('thread',{});parent=child.get('parentThreadId')
            if parent==self.thread_id or parent in self.delegates:self.delegates[child['id']]={'parent_thread_id':parent,'evidence_ref':self.store.put_blob(canonical(row))}
        if method in {'item/started','item/completed'}:
            item=p.get('item',{});sender=item.get('senderThreadId')
            if item.get('type')=='collabAgentToolCall' and item.get('tool')=='spawnAgent' and (sender==self.thread_id or sender in self.delegates):
                for child in item.get('receiverThreadIds',[]):self.delegates[child]={'parent_thread_id':sender,'evidence_ref':self.store.put_blob(canonical(row))}
        if 'id' in row:
            threading.Thread(target=self._tool,args=(row,),daemon=True).start();return
        if method=='thread/goal/updated' and p.get('threadId')==self.thread_id:
            self._goal_observed(p.get('goal'),'NOTIFICATION')
        if method=='thread/tokenUsage/updated' and p.get('threadId')==self.thread_id:
            self.last_usage=deepcopy(p.get('tokenUsage',{}).get('total',{}))
            self.store.commit_native_main(event('NATIVE_USAGE_SNAPSHOT',{'instance_id':self.iid,'thread_id':self.thread_id,'counts':self.last_usage,'evidence_ref':self.store.put_blob(canonical(row))}))
        turn=p.get('turnId') or p.get('turn',{}).get('id');a=self.turns.get(turn)
        if a:
            with a['log_lock']:
                with a['event_path'].open('ab') as f:f.write(canonical(row)+b'\n')
            if method=='item/completed':
                item=p.get('item',{})
                if item.get('type')=='agentMessage' and item.get('phase') in {None,'final_answer'}:a['messages'].append(item.get('text',''))
            if method=='turn/completed':
                a['completion']=deepcopy(p.get('turn',{}));a['done'].set()
        if method=='pmrs/transportError':
            self._error('NATIVE_TRANSPORT_ERROR',p.get('message'));a=self.active
            if a:a['error']=p.get('message');a['done'].set()
    def _tool(self,row):
        from . import task_tools,input_delivery
        p=row.get('params',{});caller=p.get('threadId');a=self.turns.get(p.get('turnId')) if caller==self.thread_id else self.active if caller in self.delegates else None;delivery=None
        try:
            require(row.get('method')=='item/tool/call' and a and a.get('admitted') and not a['done'].is_set(),'NATIVE_TOOL_UNAUTHORIZED','A currently admitted MAIN or its native verified descendant must own the tool request')
            with a['log_lock']:
                with a['event_path'].open('ab') as f:f.write(canonical(row)+b'\n')
            service=task_tools.TaskTools(self.store,a['request_id'],a['execution_id'])
            delivery,answer=service.call(p.get('tool'),p.get('arguments',{}))
            result={'contentItems':[{'type':'inputText','text':x.get('text','')} for x in answer.get('content',[]) if x.get('type')=='text'],'success':not answer.get('isError',False)}
        except Exception as exc:result={'contentItems':[{'type':'inputText','text':str(exc)[:1000]}],'success':False}
        self.rpc.send({'jsonrpc':'2.0','id':row['id'],'result':result})
        if delivery:input_delivery.confirm(self.store,a['request_id'],a['execution_id'],delivery)
    def _signals(self,s):
        signals={}
        for d in s.get('human_directions',{}).values():
            if d['instance_id']==self.iid and d.get('status') in {'QUEUED','DELIVERED'}:signals['direction:'+d['direction_id']]={'kind':'HUMAN_DIRECTION','ref':d['direction_id']}
        for e in s.get('research_audit_events',{}).values():
            if e['instance_id']==self.iid and e.get('kind')=='FULL_STRATEGIC_AUDIT_DUE' and e.get('status')=='PENDING':signals['audit:'+e['event_id']]={'kind':'STRATEGIC_AUDIT_DUE','ref':e['event_id']}
        for r in s.get('requests',{}).values():
            if r['instance_id']==self.iid and s['tasks'][r['task_id']].get('actor_kind')!='MAIN' and r['execution_state'] in {'CAPTURED','SETTLED','UNKNOWN'}:
                key='stage:'+identity([r['request_id'],r['execution_state'],r.get('capture_ref'),r.get('acceptance_state')])
                signals[key]={'kind':'STAGE_STATE_CHANGED','request_id':r['request_id'],'state':r['execution_state'],'acceptance_state':r.get('acceptance_state')}
        for m in s.get('research_messages',{}).values():
            if m.get('instance_id')==self.iid and m.get('recipient',{}).get('kind')=='MAIN':signals['message:'+m['message_id']]={'kind':'MAIN_INBOX','ref':m['message_id']}
        return signals
    def steer_pending(self,a):
        from . import input_delivery
        if a['done'].is_set() or not a.get('turn_id'):return
        s=self.store.read_snapshot();i=s['instances'][self.iid]
        if i.get('status')!='ACTIVE' or i.get('run_control',{}).get('state') in {'WAITING_HUMAN_AT_P14','WAITING_HUMAN_AT_D5','PAUSED','ENDED','COMPLETE'}:return
        pending=self._signals(s);new=[k for k in pending if k not in a['signal_seen']][:16]
        if not new:return
        navigation={'source':'PMRS_HOST_EVENT_NAVIGATION','not_user_authorization':True,
            'instruction':'New persisted events are available. Read their exact current contents with main_runtime_context, main_tasks_list, knowledge_get or research_messages_read before relying on them. This navigation contains no scientific verdict and does not change scope, budget or human controls.',
            'events':[pending[k] for k in new]}
        delivery,answer=input_delivery.prepare(self.store,a['request_id'],a['execution_id'],'native_runtime_signal',navigation,trajectory_bytes=128)
        text=answer['content'][0]['text']
        try:
            self.rpc.call('turn/steer',{'threadId':self.thread_id,'expectedTurnId':a['turn_id'],'input':[{'type':'text','text':text}],
                'clientUserMessageId':delivery,'responsesapiClientMetadata':{'pmrs_delivery_id':delivery,'pmrs_signal':'host_event_navigation'}})
            input_delivery.confirm(self.store,a['request_id'],a['execution_id'],delivery);a['signal_seen'].update(new)
        except PMRSError as exc:
            if not a['done'].is_set():self._error('NATIVE_SIGNAL_NOT_DELIVERED',str(exc))
            # Preserve the prepared evidence without claiming model receipt.
            a['signal_seen'].update(new)
    def run(self,task,work,inputs):
        from . import execution,runner,usage_ledger,resources
        rid=task['request_id'];s=self.store.read_snapshot();r=s['requests'][rid]
        require(self.active is None or self.active['done'].is_set(),'NATIVE_MAIN_BUSY','One native root stream per instance')
        mirror=self.input_root/rid
        resources.disk_preflight(self.store.root,sum(x['bytes'] for x in inputs['files'].values()))
        for name,item in inputs['files'].items():resources.copy_file(work/name,mirror/name,item['bytes'],item['sha256'])
        runner.verify_task_inputs(mirror,inputs['files'])
        mapping={'schema':'pmrs.native-input-mapping/1','request_id':rid,'task_id':task['task_id'],
            'original_directory':str(work),'native_input_directory':str(mirror),'native_scratch_directory':str(self.work),
            'files':deepcopy(inputs['files']),'access':'READ_ONLY_INPUT_TREE','native_thread_id':self.thread_id}
        immutable(work.parent/'native-input-mapping.json',canonical(mapping))
        reserve=execution.reserve(self.store,rid,execution_kind='MODEL');eid=reserve['execution_id']
        bootstrap=('The current frozen PMRS request directory is '+str(mirror)+'. Read task.json, prompt.md and packet.json, then follow the frozen material access instructions. Resolve all relative frozen input/material paths against this directory; the fixed native cwd '+str(self.work)+' is writable scratch only. Persistent native Goal and earlier messages do not replace the current full method/input. Current PMRS request: '+rid+'.\n'+runner.tasks.input_bootstrap(task))
        input_ref=self.store.put_blob(bootstrap.encode());immutable(work.parent/'bootstrap.txt',bootstrap.encode())
        a={'request_id':rid,'execution_id':eid,'input_ref':input_ref,'admitted':False,'admission':threading.Event(),'done':threading.Event(),'messages':[],
            'signal_seen':set(self._signals(self.store.read_snapshot())),'event_path':work.parent/'events.jsonl','log_lock':threading.Lock(),'usage_baseline':deepcopy(self.last_usage),'baseline_known':bool(self.last_usage) or not self.store.read_snapshot()['native_main_bindings'][self.iid].get('last_turn')};self.active=a
        immutable(work.parent/'command.json',canonical(self.command))
        immutable(work.parent/'execution-profile.json',canonical({'requested_policy':task['model_policy_resolution'],'client_mode':'ultra','native_client':self.manifest,'native_thread_id':self.thread_id,'model_context_window':task['executor_contract']['model_context_window'],'internal_delegation':{'allowed':True,'pmrs_limits':None},'observed_transport':None}))
        immutable(work.parent/'native-request.json',canonical({'thread_id':self.thread_id,'request_id':rid,'execution_id':eid,'native_client':self.manifest,'input_ref':input_ref,'usage_baseline':a['usage_baseline'],'baseline_known':a['baseline_known'],'input_mapping_ref':self.store.put_blob(canonical(mapping))}))
        try:
            # A loaded native thread ignores resume configuration overrides.
            # Keep one fixed scratch cwd/profile; each exact request input is
            # mirrored under its permanently read-only MAIN input tree.
            config={}
            import tomllib
            args=_workspace_permissions(native_binary()[0],self.work,self.input_root)
            for value in args[1::2]:
                key,raw=value.split('=',1);config[key]=tomllib.loads('value='+raw)['value']
            resume_params={'threadId':self.thread_id,'cwd':str(self.work),'model':'gpt-6-astra','approvalPolicy':'never','permissions':'research-task',
                'developerInstructions':runner.client_profile_body('MAIN').decode(),'config':config,'runtimeWorkspaceRoots':[str(self.work)],'excludeTurns':True}
            immutable(work.parent/'thread-resume.json',canonical(resume_params))
            goal=self.rpc.call('thread/goal/get',{'threadId':self.thread_id}).get('goal');self._goal_observed(goal,'BEFORE_RESUME')
            require(goal,'NATIVE_GOAL_MISSING','Persistent Goal disappeared; do not silently recreate or reset usage')
            require(sha(goal.get('objective','').encode())==self.store.read_snapshot()['native_main_bindings'][self.iid]['objective_sha256'],'NATIVE_GOAL_SCOPE_CHANGED','Original Goal scope must match before any resume')
            result=self.rpc.call('thread/resume',resume_params)
            immutable(work.parent/'thread-resume-result.json',canonical(result))
            require(result.get('cwd')==str(self.work),'NATIVE_MAIN_WORKSPACE_MISMATCH','Persistent native workspace differs from the verified fixed scratch directory')
            require(result.get('model')=='gpt-6-astra' and result.get('reasoningEffort') in {'ultra','xhigh'},'NATIVE_MAIN_POLICY_INVALID','Native thread must retain Astra with the requested Ultra mode; native xhigh reasoning transport is permitted by the Ultra client mapping')
            goal=self.rpc.call('thread/goal/get',{'threadId':self.thread_id}).get('goal');self._goal_observed(goal,'BEFORE_CONTINUATION')
            require(goal,'NATIVE_GOAL_MISSING','Persistent Goal disappeared; do not silently recreate or reset usage')
            if not a['admitted']:
                s=self.store.read_snapshot();want,_=desired(s,self.iid)
                require(want=='active','TASK_FENCED','Control forbids native activation')
                if goal.get('status')=='complete':self._error('NATIVE_COMPLETION_UNQUALIFIED','Native complete alone is not PMRS mathematical qualification; host preserves evidence before status-only correction.')
                self.rpc.call('thread/goal/set',{'threadId':self.thread_id,'status':'active'})
            require(a['admission'].wait(45),'NATIVE_TURN_NOT_ADMITTED','No native continuation admission acknowledgement arrived')
            while not a['done'].wait(1):
                require(self.rpc.process.poll() is None,'NATIVE_TRANSPORT_ERROR','Native app-server exited; original request must be recovered without resend')
                usage_ledger.ingest_safely(self.store,rid,eid)
                try:self.steer_pending(a)
                except PMRSError as exc:
                    if exc.code not in {'TASK_FENCED','DYNAMIC_INPUT_LIMIT','DYNAMIC_TRAJECTORY_LIMIT'}:self._error('NATIVE_SIGNAL_FAILED',str(exc))
            require(not a.get('error'),'NATIVE_TRANSPORT_ERROR',a.get('error',''))
            require(a.get('completion',{}).get('status')=='completed','NATIVE_TURN_FAILED',str(a.get('completion')))
            runner.verify_task_inputs(work,inputs['files']);runner.verify_task_inputs(mirror,inputs['files']);raw=(a['messages'][-1] if a['messages'] else '').encode()
            # Only final-channel agent messages should occur for a JSON task;
            # completion items remain the original evidence when validation fails.
            require(raw,'NATIVE_OUTPUT_MISSING','Native completed turn has no agent output')
            immutable(work/'response.json',raw)
            usage_ledger.ingest_safely(self.store,rid,eid,final=True)
            execution.capture(self.store,rid,raw,execution_id=eid,usage=usage_ledger.request_usage(self.store.read_snapshot(),rid))
            result=execution.recover(self.store,rid)
            self.sync_pause_only();return {**result,'model_calls':1,'native_thread_id':self.thread_id,'native_turn_id':a['turn_id']}
        except BaseException as exc:
            self._error(getattr(exc,'code','NATIVE_MAIN_ERROR'),str(exc));r=self.store.read_snapshot()['requests'][rid]
            if r['execution_state'] in {'RESERVED','SENT'}:self.store.commit_execution(execution.event('UNKNOWN',{'request_id':rid,'execution_id':eid,'reason':str(exc)}))
            # Never terminate native internal agents to clean up a root turn.
            raise
    def sync_pause_only(self):
        want,reason=desired(self.store.read_snapshot(),self.iid)
        goal=self.rpc.call('thread/goal/get',{'threadId':self.thread_id}).get('goal');self._goal_observed(goal,'CONTROL_READ')
        if goal and want in {'paused','complete'} and goal.get('status')!=want:
            answer=self.rpc.call('thread/goal/set',{'threadId':self.thread_id,'status':want});self._goal_observed(answer.get('goal'),'CONTROL_'+want.upper()+':'+str(reason))
        return {'state':'OBSERVED','desired_status':want,'model_calls':0}


def execute(store,task,binary='codex'):
    from . import runner
    runner._preflight_dispatch(store,task);native_binary()
    require(task.get('actor_kind')=='MAIN' and task['model_policy_resolution'].get('model')=='gpt-6-astra' and task['model_policy_resolution'].get('reasoning_effort')=='ultra','NATIVE_MAIN_POLICY_INVALID','Persistent MAIN requires exact Astra Ultra; no fallback')
    require(task['executor_contract'].get('executor')=='codex' and task['executor_contract'].get('sandbox')=='required','SAFETY_BOUNDARY_UNAVAILABLE','Native MAIN requires the explicit isolated Codex contract')
    work=store.root/'runs'/task['task_id']/'work'
    if work.exists():inputs={'files':runner.input_manifest(store,task)};runner.verify_task_inputs(work,inputs['files'])
    else:inputs=runner.materialize_task_inputs(store,task,work)
    immutable(work.parent/'client-system.md',runner.client_profile_body('MAIN'))
    key=(str(store.root.resolve()),task['instance_id'])
    with _SERVICES_LOCK:
        service=_SERVICES.get(key)
        if service is None:
            service=Service(store,task['instance_id'],task,work);_SERVICES[key]=service
    return service.run(task,work,inputs)


def _sync_unloaded(store,iid):
    """Read/set a persisted Goal without loading a research thread or resuming it."""
    from . import runner
    s=store.read_snapshot();b=s.get('native_main_bindings',{}).get(iid)
    if not b:return {'state':'UNBOUND','model_calls':0}
    folder=store.root/'execution'/'native-main'/iid;folder.mkdir(parents=True,exist_ok=True)
    fd=os.open(folder/'owner.lock',os.O_CREAT|os.O_RDWR,0o600)
    rpc=None
    try:
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return {'state':'OWNER_BUSY','model_calls':0}
        binary,_=native_binary();work=folder/'control';work.mkdir(exist_ok=True)
        command=[binary,'--ignore-user-config','--ignore-rules','--session-source','exec',*runner.permissions(binary,work,'MAIN'),'-c','mcp_servers={}']
        def callback(row):
            if 'id' in row:rpc.send({'jsonrpc':'2.0','id':row['id'],'error':{'code':-32601,'message':'Control-only owner cannot call research tools'}})
        rpc=Rpc(command,runner.environment(),work,folder/'protocol.jsonl',folder/'stderr.log',callback,fd)
        rpc.call('initialize',{'clientInfo':{'name':'pmrs422_native_control','version':'4.2.2'},'capabilities':{'experimentalApi':True}})
        rpc.send({'jsonrpc':'2.0','method':'initialized','params':{}})
        goal=rpc.call('thread/goal/get',{'threadId':b['thread_id']}).get('goal')
        want,reason=desired(store.read_snapshot(),iid)
        if goal and want in {'paused','complete'} and goal.get('status')!=want:
            goal=rpc.call('thread/goal/set',{'threadId':b['thread_id'],'status':want}).get('goal')
        snapshot=store.read_snapshot()
        store.commit_native_main(event('NATIVE_GOAL_SYNCED',{'instance_id':iid,'thread_id':b['thread_id'],'goal':goal,
            'operation':'CONTROL_ONLY_NO_RESUME','control_version':snapshot['instances'][iid].get('run_control',{}).get('control_version',0),
            'evidence_ref':store.put_blob(canonical({'goal':goal}))}))
        return {'state':'OBSERVED','desired_status':want,'reason':reason,'model_calls':0}
    finally:
        try:
            if rpc:rpc.close_unstarted()
        finally:os.close(fd)


def sync_pending(store,instance_id=None,binary='codex'):
    # Never resume or activate from a passive control observer. Existing Goals
    # can be read/paused/completed directly while their thread stays unloaded.
    result=[];root=str(store.root.resolve());s=store.read_snapshot()
    iids=[iid for iid,i in s.get('instances',{}).items() if i.get('kind') in {'TRH','FDH'} and (not instance_id or iid==instance_id)]
    for iid in iids:
        with _SERVICES_LOCK:service=_SERVICES.get((root,iid))
        try:
            from .usage_ledger import ingest_native_internal_safely
            ingest_native_internal_safely(store,iid)
            if not s.get('native_main_bindings',{}).get(iid):
                from .harness_methods import manual
                from .workflow_instances import validate_discovery_scope
                i=s['instances'][iid]
                if i['kind']=='FDH':validate_discovery_scope(s,i)
                else:require(i.get('target_ref') in s.get('records',{}),'TARGET_REQUIRED','Exact target scope is required before creating Goal')
                work=store.root/'execution'/'native-main'/iid/'bootstrap';work.mkdir(parents=True,exist_ok=True)
                specification={'instance_id':iid,'mission_id':i.get('current_mission_id'),'method_manual':manual(i['kind']),'executor_contract':{'model_context_window':872000}}
                with _SERVICES_LOCK:
                    service=_SERVICES.get((root,iid))
                    if service is None:
                        service=Service(store,iid,specification,work);_SERVICES[(root,iid)]=service
                result.append({'state':'CREATED_PAUSED','instance_id':iid,'model_calls':0})
            else:result.append(service.sync_pause_only() if service else _sync_unloaded(store,iid))
        except Exception as exc:
            store.commit_native_main(event('NATIVE_GOAL_ERROR',{'instance_id':iid,'thread_id':s.get('native_main_bindings',{}).get(iid,{}).get('thread_id'),
                'code':getattr(exc,'code','NATIVE_SYNC_FAILED'),'message':str(exc)[:4000]}))
            result.append({'state':'SYNC_FAILED','model_calls':0})
    return {'state':'OBSERVED' if result else 'UNBOUND','results':result,'model_calls':0}
