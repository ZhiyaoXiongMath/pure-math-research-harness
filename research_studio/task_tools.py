"""Request-scoped stdio MCP adapter.  All native authority stays in the host.

Codex starts this process outside the worker shell sandbox.  Its private binding
file is outside the worker's readable roots; tool arguments never supply paths,
identity, permissions, arbitrary commands, SQL, or a replacement capability.
"""
from copy import deepcopy
from pathlib import Path
import json
import os
import secrets
import subprocess
import sys
from .util import canonical,immutable,loads,read,require,sha,PMRSError

INSTRUCTIONS='''PMRS native task tools. Identity and authorization are bound by HOST.
Use research_messages_list at the start, a useful intermediate result/blocker, and before final submission.
Cooperating workers may send bounded candidate hints to exact authorized peers; all tasks may address "main".
MAIN has a durable instance inbox across turns and may contact every owned stage task. Use neutral status/frozen-material replies to preserve review independence. Explicit scientific sharing records lost independent-vote eligibility. MAIN controls peer links with main_communication_revise.
Inspect a message with research_messages_read before relying on it. A message and ACK never grant scientific support.
Use knowledge_search for navigation, then knowledge_get for the exact record/source and knowledge_dependencies for premises.
Do not equate an excerpt, accepted record, or main's preference with an independently supported theorem.
Every returned summary, body and error is additional recorded input and consumes the frozen dynamic allowance.
Finish without circular waiting. Messages arriving after the input seal belong to a later authorized task.
In the final payload message_dispositions list actual viewed/used/rejected messages with reasons and resulting record_refs.
Required new premises still obey the frozen scientific contract; a hint may be reconstructed or retained as an explicit open condition.
Missing optional tools are environment limitations, not mathematical refutations. Do not change native files. MAIN may freely use Codex native internal delegation; PMRS does not limit its number, models, concurrency, depth, token use or methods. main_stage_dispatch creates distinct PMRS stage CLI tasks under instance 8/global 20 admission. MAIN and its native delegates do not occupy those stage slots.'''


def _schema(properties,required=()):return {'type':'object','properties':properties,'required':list(required),'additionalProperties':False}
def _text():return {'type':'string'}
def _refs():return {'type':'array','items':_text(),'maxItems':16}


def tool_definitions(actor_kind=None):
    defs=[
      ('research_messages_list','Get this request authorized inbox and pending withdrawal notices.',_schema({'cursor':{'type':'integer','minimum':0},'limit':{'type':'integer','minimum':1,'maximum':16}})),
      ('research_messages_read','Read the exact message or one exact native attachment, recording its delivery.',_schema({'message_id':_text(),'attachment_ref':_text()},['message_id'])),
      ('research_messages_send','Publish a candidate hint or question. Use to="main" or an exact permitted task/request. Reuse idempotency_key only for the same send.',
       _schema({'to':_text(),'body':{'type':'string','maxLength':4096},'kind':{'type':'string','enum':['QUESTION','LEAD','INTERMEDIATE_RESULT','COUNTEREVIDENCE','SOURCE_POINTER','STATUS_REQUEST']},'idempotency_key':{'type':'string','maxLength':128},'record_refs':_refs(),'reply_to':_text(),'allow_independence_loss':{'type':'boolean'}},['to','body','idempotency_key'])),
      ('research_messages_ack','Record viewing, adoption, rejection or a clarification need. USED requires resulting native record refs.',
       _schema({'message_id':_text(),'disposition':{'type':'string','enum':['VIEWED','USED','REJECTED','NEEDS_CLARIFICATION']},'reason':_text(),'record_refs':_refs()},['message_id','disposition','reason'])),
      ('research_messages_withdraw','Append a withdrawal of your original candidate message; never delete its evidence.',_schema({'message_id':_text(),'reason':_text()},['message_id','reason'])),
      ('knowledge_search','Search exact authorized bodies with bounded continuation and explicit per-call coverage.',
       _schema({'query':{'type':'string','maxLength':512},'kind':_text(),'target_ref':_text(),'route_ref':_text(),
                'limit':{'type':'integer','minimum':1,'maximum':20},'cursor':{'type':'integer','minimum':0},
                'continuation':{'type':'string','maxLength':4096},'as_of_commit':_text()})),
      ('knowledge_get','Read an exact authorized native or fast revision; assurance is claim-scoped.',
       _schema({'ref':_text(),'as_of_commit':_text(),'body_range':_schema({'start':{'type':'integer','minimum':0,'maximum':4294967295},'end':{'type':'integer','minimum':1,'maximum':4294967296},'unit':{'type':'string','enum':['UTF8_BYTE']}},['start','end','unit'])},['ref'])),
      ('knowledge_dependencies','Read exact authorized dependencies with bounded continuation.',
       _schema({'ref':_text(),'as_of_commit':_text(),'continuation':{'type':'string','maxLength':4096},
                'cursor':{'type':'integer','minimum':0},'limit':{'type':'integer','minimum':1,'maximum':32}},['ref'])),
      ('knowledge_history','Read exact revision history without replacing historical identities.',
       _schema({'ref':_text(),'as_of_commit':_text(),'continuation':{'type':'string','maxLength':4096},
                'cursor':{'type':'integer','minimum':0},'limit':{'type':'integer','minimum':1,'maximum':32}},['ref']))]
    if actor_kind=='MAIN':
        from .incidents import OPTIONS
        defs.extend([
          ('main_runtime_context','Read current exact human guidance, pending audit events, strategy and stage frontier in this authorized MAIN instance. This records the actual delivered runtime input; it does not grant new scope or scientific qualification.',_schema({})),
          ('main_tasks_list','Inspect owned stage tasks, actual request status, MAIN decision sources and dynamic communication links.',_schema({'cursor':{'type':'integer','minimum':0},'limit':{'type':'integer','minimum':1,'maximum':32}})),
          ('main_stage_dispatch','Atomically apply this MAIN decision and queue at most 8 stage CLI duties. Use the complete StrategyProposal contract in task input. Reuse the same idempotency key for retries; final response must not repeat already applied work.',
            _schema({'proposal':{'type':'object'},'idempotency_key':{'type':'string','maxLength':128}},['proposal','idempotency_key'])),
          ('main_communication_revise','Create, disable or amend directed/bidirectional communication links between exact owned stage task IDs. Enabling isolated scientific contact requires allow_independence_loss=true; exposure remains recorded after revocation.',
            _schema({'links':{'type':'array','maxItems':32,'items':{'type':'object','properties':{'from_task_id':_text(),'to_task_id':_text(),'bidirectional':{'type':'boolean'},'enabled':{'type':'boolean'},'shared_refs':_refs(),'reason':_text(),'allow_independence_loss':{'type':'boolean'}},'required':['from_task_id','to_task_id','enabled','reason'],'additionalProperties':False}},
              'reason':_text(),'idempotency_key':{'type':'string','maxLength':128}},['links','reason','idempotency_key'])),
          ('runtime_inspect_incident','Inspect this authorized mission native incidents, or one exact incident. Does not alter science or call a model.',_schema({'incident_id':_text()})),
          ('runtime_list_recovery_options','List currently legal, bounded recovery actions for the original request.',_schema({'incident_id':_text()},['incident_id'])),
          ('runtime_propose_recovery','Submit an idempotent host-validated recovery proposal. No shell, SQL, new grant or altered science.',
           _schema({'incident_id':_text(),'option':{'type':'string','enum':sorted(OPTIONS)},'expected_revision':{'type':'integer','minimum':1},
                    'idempotency_key':{'type':'string','maxLength':128},
                    'arguments':_schema({'binding_id':_text(),'input_refs':_refs(),'source_refs':_refs(),
                                         'source_selections':{'type':'object'},'reason':_text()})},
                   ['incident_id','option','expected_revision','idempotency_key']))])
    return [{'name':name,'description':desc,'inputSchema':schema} for name,desc,schema in defs]


def _validate_args(schema,args):
    require(isinstance(args,dict) and set(args)<=set(schema['properties']) and set(schema['required'])<=set(args),
            'TOOL_ARGUMENT_INVALID','Only the documented bounded tool arguments are accepted.')
    for key,value in args.items():
        prop=schema['properties'][key];typ=prop.get('type')
        valid={'string':isinstance(value,str),'integer':type(value) is int,'array':isinstance(value,list),'object':isinstance(value,dict),'boolean':type(value) is bool}.get(typ,False)
        require(valid,'TOOL_ARGUMENT_INVALID','Wrong argument type: '+key)
        if 'enum' in prop:require(value in prop['enum'],'TOOL_ARGUMENT_INVALID','Unknown enum: '+key)
        if typ=='string':require(len(value)<=prop.get('maxLength',8192),'TOOL_ARGUMENT_INVALID','Argument exceeds bound: '+key)
        if typ=='integer':require(prop.get('minimum',0)<=value<=prop.get('maximum',2**31),'TOOL_ARGUMENT_INVALID','Integer outside bound: '+key)
        if typ=='array':
            require(len(value)<=prop.get('maxItems',32),'TOOL_ARGUMENT_INVALID','Array exceeds limit.')
            if prop.get('items',{}).get('type')=='object':
                for item in value:_validate_args(prop['items'],item)
            else:require(all(isinstance(x,str) for x in value),'TOOL_ARGUMENT_INVALID','Invalid reference array.')


class TaskTools:
    def __init__(self,store,request_id,execution_id):
        self.store=store;self.request_id=request_id;self.execution_id=execution_id
        from .communication import bound_request
        _,self.task=bound_request(store.read_snapshot(),request_id,execution_id,active=False)
        self.definitions=tool_definitions(self.task.get('actor_kind'))

    def call(self,name,args):
        from . import communication as comm,knowledge_access as knowledge,input_delivery
        definitions={d['name']:d for d in self.definitions};mids=[];error=False
        # Charge the exact submitted logical call plus a bounded native
        # transport frame allowance before any mutation. A depleted server
        # closes without fabricating a delivered response or repeating work.
        trajectory_bytes=len(canonical({'name':name,'arguments':args}))+128
        snapshot=self.store.read_snapshot();previous=[d for d in snapshot.get('input_deliveries',{}).values() if d['request_id']==self.request_id]
        try:
            require(sum(d.get('trajectory_bytes',0) for d in previous)+trajectory_bytes<=self.task['communication_contract']['tool_trajectory_reserve_tokens'],
                    'DYNAMIC_TRAJECTORY_LIMIT','No additional tool arguments fit this frozen request; use a later authorized input window.')
            comm.bound_request(self.store.read_snapshot(),self.request_id,self.execution_id)
            require(name in definitions,'TOOL_NOT_ALLOWED','Tool is outside this request capability.')
            _validate_args(definitions[name]['inputSchema'],args)
            bound=(self.store,self.request_id,self.execution_id)
            if name=='research_messages_list':
                result=comm.inbox(*bound,**args);mids=[x['message_id'] for x in result['messages']]+[x['message_id'] for x in result['withdrawals']]
                # Only host-registered exact group membership is exposed.
                s=self.store.read_snapshot();groups=[g for g in s.get('collaboration_groups',{}).values() if self.request_id in g['request_ids']]
                result['peers']=[{'group_id':g['group_id'],'request_ids':g['request_ids'],'topic':g['topic']} for g in groups]
            elif name=='research_messages_read':result=comm.read_message(*bound,**args);mids=[args['message_id']]
            elif name=='research_messages_send':result=comm.send(*bound,**args)
            elif name=='research_messages_ack':result=comm.ack(*bound,**args)
            elif name=='research_messages_withdraw':result=comm.withdraw(*bound,**args)
            elif name=='main_runtime_context':
                from . import research_audit,strategy
                s=self.store.read_snapshot();iid=self.task['instance_id'];mid=self.task['mission_id'];st=strategy.current(s,iid) or {};frontier=strategy.frontier(s,iid,mid)
                result={'schema':'pmrs.main-runtime-context/4.2.2','instance_id':iid,'request_id':self.request_id,'as_of_commit':s.get('knowledge_commit'),
                    'effective_guidance':research_audit.effective_guidance(s,iid),
                    'pending_audit_events':[deepcopy(x) for x in s.get('research_audit_events',{}).values() if x['instance_id']==iid and x.get('status')=='PENDING'],
                    'strategy_revision':st.get('revision'),'pending_trigger_refs':list(st.get('pending_trigger_refs',[])),
                    'frontier_digest':strategy.frontier_digest(s,iid,mid),'work_frontier':frontier,'covered_binding_ids':sorted({b for r in frontier for b in r['bindings']}),
                    'run_control':deepcopy(s['instances'][iid].get('run_control',{})),
                    'task_states':[{'task_id':r['task_id'],'request_id':r['request_id'],'execution_state':r['execution_state'],'acceptance_state':r.get('acceptance_state'),'capture_ref':r.get('capture_ref')} for r in s['requests'].values() if r['instance_id']==iid]}
            elif name=='main_tasks_list':
                s=self.store.read_snapshot();rows=[t for t in s.get('tasks',{}).values() if t['instance_id']==self.task['instance_id'] and t.get('actor_kind')!='MAIN'];cursor=args.get('cursor',0);limit=args.get('limit',16)
                # Navigation must not repeat the full immutable request, usage
                # evidence ledger and scientific dispositions on every poll.
                # Exact scientific content remains available through knowledge
                # tools; the original request and usage evidence stay native.
                request_fields=('request_id','execution_id','execution_state','acceptance_state','capture_ref',
                    'admission_error','fenced','repair_of','repair_kind')
                result={'tasks':[{'task_id':t['task_id'],'request_id':t['request_id'],'mission_id':t['mission_id'],'stage_id':t['stage_id'],'role':t['role'],
                    'model_policy':t.get('model_policy'),'decision_ref':t.get('strategy_proposal_ref',t.get('entry_basis',{}).get('strategy',{}).get('proposal_ref')),
                    'request':{k:s['requests'][t['request_id']].get(k) for k in request_fields},'independence':comm.independence_status(s,t['task_id'])} for t in rows[cursor:cursor+limit]],
                    'cursor':cursor+min(limit,max(0,len(rows)-cursor)),'has_more':cursor+limit<len(rows),
                    'links':[v for v in s.get('communication_links',{}).values() if v['from_request_id'] in {t['request_id'] for t in rows}]}
            elif name=='main_stage_dispatch':
                from . import strategy
                receipt=strategy.dispatch_from_main(self.store,self.request_id,**args)
                # The submitted proposal is already model input and the exact
                # strategy event is durably stored. Echoing both copies consumed
                # 22 KiB in the real HSC dispatch and starved subsequent contact.
                result={k:v for k,v in receipt.items() if k not in {'proposal','events'}}
                result['proposal_sha256']=sha(canonical(args['proposal']))
                result['event_refs']=[e['event_id'] for e in receipt.get('events',[])]
                result['receipt_scope']='EXACT_CONTROL_RECEIPT; full proposal and events retained in native history'
            elif name=='main_communication_revise':result=comm.revise_links(*bound,**args)
            elif name.startswith('knowledge_'):
                current_task=self.store.read_snapshot()['tasks'][self.task['task_id']]
                result=getattr(knowledge,name[len('knowledge_'):])(self.store,task=current_task,**args)
            elif name.startswith('runtime_'):
                from . import incidents
                result=incidents.task_tool(self.store,self.request_id,name,args)
            else:raise PMRSError('TOOL_NOT_ALLOWED','Unsupported task tool.')
        except PMRSError as exc:
            result={'error':exc.code,'message':str(exc)[:240]};error=True;mids=[]
        # A fenced/sealed request cannot create a new response after finality.
        try:
            return input_delivery.prepare(self.store,self.request_id,self.execution_id,name,result,message_ids=mids,is_error=error,trajectory_bytes=trajectory_bytes)
        except PMRSError as exc:
            # A pause can arrive between a tool and its response publication.
            # Preserve a control-only rejection without reopening the frozen
            # scientific input window or tearing down the whole MCP channel.
            if exc.code not in {'TASK_FENCED','INPUT_WINDOW_SEALED','DYNAMIC_INPUT_LIMIT','DYNAMIC_TRAJECTORY_LIMIT'}:raise
            from .util import now
            body={'error':exc.code,'message':'PMRS control or input capacity prevents this delivery. No new scientific material was delivered. Reconcile any earlier mutation by its original idempotency key after authorized continuation.'}
            response={'content':[{'type':'text','text':canonical(body).decode()}],'isError':True}
            self.store.commit_communication(comm.event('TOOL_CONTROL_REJECTED',{
                'request_id':self.request_id,'execution_id':self.execution_id,'tool_name':name,
                'error_code':exc.code,'response_ref':self.store.blob(canonical(response)),
                'at':now(),'scientific_input_delivered':False}))
            return None,response


def create_binding(store,task):
    folder=store.root/'execution'/'tool-capabilities';folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    request=store.read_snapshot()['requests'][task['request_id']]
    path=folder/(task['request_id']+'.json')
    binding={'schema':'pmrs.task-tool-capability/1','project_root':str(store.root.resolve()),'request_id':task['request_id'],
             'execution_id':request['execution_id'],'task_sha256':sha(canonical(task)),
             'tool_schema_sha256':sha(canonical(tool_definitions(task.get('actor_kind')))),
             'capability_nonce':secrets.token_hex(32)}
    if path.exists():
        old=loads(read(path));require(all(old.get(k)==v for k,v in binding.items() if k!='capability_nonce'),
                                    'TASK_TOOL_BINDING_CHANGED','Original request tool capability differs.');return path
    immutable(path,canonical(binding));return path


def server_command(binding_path):
    package_root=str(Path(__file__).resolve().parent.parent)
    bootstrap='import runpy,sys;sys.path.insert(0,'+repr(package_root)+');runpy.run_module("research_studio.task_tools",run_name="__main__")'
    return [sys.executable,'-I','-c',bootstrap,str(binding_path)]


def codex_arguments(binding_path,actor_kind=None):
    return inventory_arguments(server_command(binding_path),actor_kind)


def inventory_arguments(command,actor_kind=None):
    """Same registration for native execution and no-inference inventory probe."""
    defs=tool_definitions(actor_kind)
    config={'mcp_servers.pmrs.command':command[0],'mcp_servers.pmrs.args':command[1:],
            'mcp_servers.pmrs.required':True,'mcp_servers.pmrs.enabled':True,
            'mcp_servers.pmrs.enabled_tools':[x['name'] for x in defs],
            'mcp_servers.pmrs.default_tools_approval_mode':'approve',
            'mcp_servers.pmrs.startup_timeout_sec':15,'mcp_servers.pmrs.tool_timeout_sec':30}
    return [arg for key,value in config.items() for arg in ('-c',key+'='+json.dumps(value,ensure_ascii=False))]


def schema_probe_command():
    """Inventory only: no project store, capability, deliveries, or tool calls."""
    package_root=str(Path(__file__).resolve().parent.parent)
    code='''import json,sys
sys.path.insert(0,PACKAGE_ROOT)
from research_studio.task_tools import tool_definitions,INSTRUCTIONS
for line in sys.stdin:
 m=json.loads(line);i=m.get('id');method=m.get('method')
 if i is None:continue
 if method=='initialize':r={'protocolVersion':m.get('params',{}).get('protocolVersion','2024-11-05'),'capabilities':{'tools':{}},'serverInfo':{'name':'pmrs-task-tools','version':'4.2.2'},'instructions':INSTRUCTIONS}
 elif method=='tools/list':r={'tools':tool_definitions('MAIN')}
 elif method=='ping':r={}
 else:
  print(json.dumps({'jsonrpc':'2.0','id':i,'error':{'code':-32601,'message':'Inventory probe cannot call tools'}}),flush=True);continue
 print(json.dumps({'jsonrpc':'2.0','id':i,'result':r}),flush=True)
'''.replace('PACKAGE_ROOT',repr(package_root))
    return [sys.executable,'-I','-c',code]


def probe(binding_path):
    """Start the actual stdio process, but never request backend inference."""
    calls=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'pmrs-preflight','version':'1'}}},
           {'jsonrpc':'2.0','method':'notifications/initialized','params':{}},
           {'jsonrpc':'2.0','id':2,'method':'tools/list','params':{}}]
    p=subprocess.run(server_command(binding_path),input=b'\n'.join(canonical(x) for x in calls)+b'\n',capture_output=True,timeout=15)
    require(p.returncode==0,'TASK_TOOLS_UNAVAILABLE','The required request-scoped stdio process failed initialization.')
    try:rows=[json.loads(line) for line in p.stdout.splitlines()]
    except ValueError:raise PMRSError('TASK_TOOLS_UNAVAILABLE','Invalid MCP startup response.')
    require(len(rows)==2 and rows[0].get('result',{}).get('capabilities',{}).get('tools')=={}
            and rows[1].get('result',{}).get('tools'),'TASK_TOOLS_UNAVAILABLE','Required MCP initialization or tool inventory is missing.')
    return {'ready':True,'transport':'stdio','tool_names':[x['name'] for x in rows[1]['result']['tools']],'model_calls':0}


def serve(binding_path):
    from .store import Store
    from . import input_delivery
    binding=loads(read(Path(binding_path)));require(binding.get('schema')=='pmrs.task-tool-capability/1','TASK_TOOL_BINDING_CHANGED','A host capability is required.')
    store=Store(Path(binding['project_root']));s=store.read_snapshot();request=s['requests'][binding['request_id']];task=s['tasks'][request['task_id']]
    require(sha(canonical(task))==binding['task_sha256'] and request['execution_id']==binding['execution_id']
            and sha(canonical(tool_definitions(task.get('actor_kind'))))==binding['tool_schema_sha256'],'TASK_TOOL_BINDING_CHANGED','Frozen tool identity differs.')
    service=TaskTools(store,binding['request_id'],binding['execution_id'])
    while True:
        raw=sys.stdin.buffer.readline(1024*1024+1)
        if not raw:return
        if len(raw)>1024*1024:raise PMRSError('TOOL_ARGUMENT_INVALID','MCP request exceeds the bounded line size.')
        message=json.loads(raw);method=message.get('method');mid=message.get('id');delivery=None
        if mid is None:continue
        if method=='initialize':
            version=message.get('params',{}).get('protocolVersion','2024-11-05')
            result={'protocolVersion':version,'capabilities':{'tools':{}},'serverInfo':{'name':'pmrs-task-tools','version':'4.2.2'},'instructions':INSTRUCTIONS}
        elif method=='tools/list':result={'tools':deepcopy(service.definitions)}
        elif method=='ping':result={}
        elif method=='tools/call':
            params=message.get('params',{});delivery,result=service.call(params.get('name'),params.get('arguments',{}))
        else:
            sys.stdout.buffer.write(canonical({'jsonrpc':'2.0','id':mid,'error':{'code':-32601,'message':'Unsupported bounded MCP method'}})+b'\n');sys.stdout.buffer.flush();continue
        sys.stdout.buffer.write(canonical({'jsonrpc':'2.0','id':mid,'result':result})+b'\n');sys.stdout.buffer.flush()
        if delivery:input_delivery.confirm(store,service.request_id,service.execution_id,delivery)


if __name__=='__main__':
    try:
        require(len(sys.argv)==2,'TASK_TOOL_BINDING_CHANGED','One host-generated capability path is required.')
        serve(sys.argv[1])
    except (PMRSError,OSError,KeyError,ValueError) as exc:
        # stderr contains bounded diagnostics only; never native content/secrets.
        sys.stderr.write('PMRS task tools stopped: '+getattr(exc,'code',type(exc).__name__)+'\n');sys.exit(1)
