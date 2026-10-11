"""Evidence-bound faults and a closed recovery vocabulary for the main actor."""
from copy import deepcopy
from pathlib import Path
from .util import require,identity,canonical,sha,now,PMRSError

SCHEMA='pmrs.incident/1'
MAPS=frozenset({'incidents','recovery_proposals','incident_events'})
OPTIONS={'REFRESH_PROJECTION','RECOVER_CAPTURE','INGEST_USAGE','CHECK_RESOURCE',
         'ADD_UNSENT_INPUTS','ADD_UNSENT_SOURCES','REPLAN_MATERIALS','FINITE_FORMAT'}

def state_guard(s,iid):
    instance=s['instances'][iid];mid=instance.get('current_mission_id')
    return identity({'instance':instance,'requests':{rid:{k:r.get(k) for k in
        ('execution_state','acceptance_state','capture_ref','fenced')} for rid,r in s['requests'].items() if r['mission_id']==mid},
        'duties':{oid:o['definition']['definition_revision'] for oid,o in s['obligations'].items()
            if any(c['mission_id']==mid for c in o['definition']['consumer_bindings'])}})

def project(s,incident):
    """Annotate original faults with observed execution, without rewriting them."""
    row=deepcopy(incident);current=row.get('state_guard')==state_guard(s,row['instance_id'])
    row.update(state_guard_current=current,blocking=current and row.get('status') in
        {'MAINTENANCE_REQUIRED','WAITING_CONTEXT','WAITING_AUTHORIZATION'},
        recovery_disposition='CURRENT_RECORDED_FAULT' if current else 'HISTORICAL_STATE_CHANGED',boundary_passage=None)
    # Only this precise rejected boundary is inferred here. Later unrelated
    # activity cannot prove that an arbitrary software fault was repaired.
    if row.get('code')!='EXECUTION_EVENT_INVALID' or row.get('message')!='Exact bounded host assignment required':return row
    from datetime import datetime
    def stamp(value):return datetime.fromisoformat(value.replace('Z','+00:00'))
    for turn in sorted(s.get('native_main_turns',{}).values(),key=lambda v:v.get('observed_at','')):
        if turn.get('instance_id')!=row['instance_id'] or not turn.get('observed_at') or stamp(turn['observed_at'])<=stamp(row['created_at']):continue
        request=s.get('requests',{}).get(turn.get('request_id'),{})
        task=s.get('tasks',{}).get(request.get('task_id'),{})
        if request.get('mission_id')!=row.get('mission_id') or task.get('actor_kind')!='MAIN':continue
        ids={b['obligation_id'] for b in task.get('obligation_bindings',[])}
        assignments=[e for e in s.get('execution_events',{}).values() if e.get('event_type')=='ASSIGN_OBLIGATION'
            and e.get('payload',{}).get('mission_id')==row.get('mission_id')
            and e.get('payload',{}).get('obligation',{}).get('definition',{}).get('obligation_id') in ids]
        if not assignments:continue
        row.update(blocking=False,recovery_disposition='BOUNDARY_PASSED_BY_NATIVE_SUCCESSOR',
            boundary_passage={'request_id':request['request_id'],'task_id':task['task_id'],
                'assignment_event_ids':sorted(e['event_id'] for e in assignments),
                'native_thread_id':turn['thread_id'],'native_turn_id':turn['turn_id'],
                'observed_at':turn['observed_at'],'claim':'Exact host assignment and native root admission occurred after the original fault; no claim about later research success.'})
        break
    return row

def current_fault(s,iid):
    guard=state_guard(s,iid)
    matches=[row for row in s.get('incidents',{}).values() if row['instance_id']==iid and row.get('state_guard')==guard
             and row['status'] in {'MAINTENANCE_REQUIRED','WAITING_CONTEXT','WAITING_AUTHORIZATION'}]
    matches=[project(s,row) for row in matches]
    matches=[row for row in matches if row['blocking']]
    return sorted(matches,key=lambda row:row['created_at'])[-1] if matches else None

def event(kind,payload):
    e={'actor':'host','capability_ref':'CAP-HOST','event_type':kind,'payload':deepcopy(payload)}
    return {**e,'event_id':identity(e,'INCIDENT-EVENT-')}

def apply_event(snapshot,e,blob_get=None):
    require(e['actor']=='host' and snapshot['capabilities'][e['capability_ref']]['actor']=='host','AUTHORIZATION_REQUIRED','Host recovery evidence required')
    old=snapshot.get('incident_events',{}).get(e['event_id'])
    if old:require(old==e,'ALREADY_SETTLED_CONTENT_CONFLICT','Incident event conflict');return deepcopy(snapshot)
    s=deepcopy(snapshot);p=e['payload'];kind=e['event_type']
    if kind=='INCIDENT_DETECTED':
        row=p['incident'];old=s.setdefault('incidents',{}).get(row['incident_id'])
        if old:return deepcopy(snapshot)
        s['incidents'][row['incident_id']]=deepcopy(row)
    elif kind=='RECOVERY_PROPOSED':
        row=p['proposal'];incident=s['incidents'][row['incident_id']]
        require(incident['revision']==row['expected_revision'],'STALE_INCIDENT','Incident revision changed')
        require(row['option'] in OPTIONS,'RECOVERY_NOT_ALLOWED','Only registered recovery operations are allowed')
        s.setdefault('recovery_proposals',{})[row['proposal_id']]=deepcopy(row)
        incident.update(revision=incident['revision']+1,status='RECOVERY_PENDING')
    elif kind=='RECOVERY_RECORDED':
        row=s['recovery_proposals'][p['proposal_id']];require(row['status']=='PENDING','ALREADY_SETTLED_CONTENT_CONFLICT','Recovery was already recorded')
        row.update(status=p['status'],result=deepcopy(p['result']))
        incident=s['incidents'][row['incident_id']];incident.update(revision=incident['revision']+1,status=p['incident_status'])
        incident.setdefault('attempts',[]).append(row['proposal_id'])
    else:raise PMRSError('INCIDENT_EVENT_INVALID','Unknown incident event')
    s.setdefault('incident_events',{})[e['event_id']]=deepcopy(e);return s

def detect(store,instance_id,error,*,location,request_id=None):
    s=store.read_snapshot();mid=s['instances'][instance_id].get('current_mission_id')
    request=s['requests'].get(request_id,{})
    from . import __version__
    source_hash=identity({p.name:sha(p.read_bytes()) for p in Path(__file__).parent.glob('*.py')})
    guard=state_guard(s,instance_id)
    fingerprint=identity([instance_id,mid,error.code,location,request_id,guard,source_hash])
    iid='INCIDENT-'+fingerprint
    if iid in s.get('incidents',{}):return s['incidents'][iid]
    classification=('WAITING_RESOURCE' if error.code.startswith('RESOURCE') else
        'WAITING_AUTHORIZATION' if error.code in {'BUDGET_EXHAUSTED','AUTHORIZATION_REQUIRED'} else
        'WAITING_CONTEXT' if error.code in {'CONTEXT_LIMIT','INCOMPLETE_CONTEXT'} else 'MAINTENANCE_REQUIRED')
    row={'schema':SCHEMA,'incident_id':iid,'instance_id':instance_id,'mission_id':mid,'revision':1,
         'fingerprint':fingerprint,'status':classification,'created_at':now(),'code':error.code,
         'message':error.message,'location':location,'request_id':request_id,'execution_id':request.get('execution_id'),
         'task_id':request.get('task_id'),'capture_ref':request.get('capture_ref'),
         'runtime_version':__version__,'source_sha256':source_hash,'as_of_commit':s['knowledge_commit'],'state_guard':guard,
         'inflight_requests':[r['request_id'] for r in s['requests'].values() if r['execution_state'] in {'RESERVED','SENT','UNKNOWN'}],
         'host_facts':[{'code':error.code,'message':error.message,'location':location}],
         'main_hypotheses':[],'attempts':[],'maintenance_executor_available':False,
         'handoff':{'reproduce':'Open the same native project and run the affected original request or unsent duty preflight at '+location,
                    'source_modules':[location.split('.')[0]],'preserve':['original target and authorization','frozen tasks and captures','sample and repair limits','source versions','all rejection history'],
                    'expected_recovery':'Fix the implementation in an isolated source copy, record a runtime boundary, then recover the same capture or unsent responsibility without adding authorization.'}}
    store.commit_incident(event('INCIDENT_DETECTED',{'incident':row}));return row

def list_recovery_options(store,incident_id):
    s=store.read_snapshot();incident=s.get('incidents',{}).get(incident_id);require(incident,'INCIDENT_UNKNOWN',incident_id)
    choices=['REFRESH_PROJECTION','CHECK_RESOURCE'];r=s['requests'].get(incident.get('request_id'),{})
    if r.get('capture_ref') and r['execution_state']=='CAPTURED':choices.append('RECOVER_CAPTURE')
    if r.get('task_id') and (store.root/'runs'/r['task_id']/'events.jsonl').exists():choices.append('INGEST_USAGE')
    if r.get('acceptance_state')=='REJECTED_CONTRACT':
        try:
            from .execution import format_diagnostic
            format_diagnostic(s,r['request_id'],store.read_blob(r['capture_ref']),store.read_blob)
            origin=r.get('repair_of',r['request_id']);root=s['requests'][origin];task=s['tasks'][root['task_id']]
            if sum(x.get('repair_of')==origin and x.get('repair_kind')=='FORMAT' for x in s['requests'].values())<task.get('repair_limits',{}).get('FORMAT',0):choices.append('FINITE_FORMAT')
        except PMRSError:pass
    if incident['code'] in {'CONTEXT_LIMIT','INCOMPLETE_CONTEXT','SOURCE_MISSING','INPUT_PLAN_REQUIRED'}:
        choices+=['ADD_UNSENT_INPUTS','ADD_UNSENT_SOURCES','REPLAN_MATERIALS']
    return {'incident_id':incident_id,'expected_revision':incident['revision'],'options':choices,
            'maintenance_executor_available':False,'model_calls':0}

def propose_recovery(store,request_id,incident_id,option,*,expected_revision,idempotency_key,arguments=None):
    s=store.read_snapshot();caller=s['requests'].get(request_id,{});task=s['tasks'].get(caller.get('task_id'),{})
    incident=s.get('incidents',{}).get(incident_id,{})
    require(task.get('actor_kind')=='MAIN' and caller.get('instance_id')==incident.get('instance_id')
            and caller.get('mission_id')==incident.get('mission_id'),'AUTHORIZATION_REQUIRED','Main recovery is limited to this exact authorized mission')
    args=deepcopy(arguments or {});require(not set(args)-{'binding_id','input_refs','source_refs','source_selections','reason'},'RECOVERY_NOT_ALLOWED','Arbitrary paths, shell, JSON patches and authorizations are forbidden')
    pid=identity([request_id,idempotency_key],'RECOVERY-');prior=s.get('recovery_proposals',{}).get(pid)
    if prior:
        require(prior['option']==option and prior['arguments']==args,'ALREADY_SETTLED_CONTENT_CONFLICT','Recovery idempotency conflict')
        return prior
    require(option in list_recovery_options(store,incident_id)['options'],'RECOVERY_NOT_ALLOWED','Option is not currently legal')
    proposal={'schema':'pmrs.recovery-proposal/1','proposal_id':pid,'request_id':request_id,'incident_id':incident_id,
              'expected_revision':expected_revision,'option':option,'arguments':args,'status':'PENDING'}
    store.commit_incident(event('RECOVERY_PROPOSED',{'proposal':proposal}))
    try:
        from . import execution
        rid=incident.get('request_id')
        if option=='REFRESH_PROJECTION':result=store.rebuild_projection()
        elif option=='RECOVER_CAPTURE':result=execution.recover(store,rid)
        elif option=='FINITE_FORMAT':result=execution.prepare_repair(store,rid,'FORMAT')
        elif option=='INGEST_USAGE':
            from .usage_ledger import ingest_safely
            r=store.read_snapshot()['requests'][rid]
            result=ingest_safely(store,rid,r['execution_id'],final=True)
        elif option=='CHECK_RESOURCE':
            from .host_pool import status
            result={'host_pool':status(),'disposition':'RECHECKED_WITHOUT_DISPATCH'}
        elif option=='ADD_UNSENT_INPUTS':result=execution.add_unsent_inputs(store,incident['instance_id'],args['binding_id'],args['input_refs'],args['reason'])
        elif option=='ADD_UNSENT_SOURCES':result=execution.add_unsent_sources(store,incident['instance_id'],args['binding_id'],args['source_refs'],args['reason'])
        else:result=execution.replan_unsent_materials(store,incident['instance_id'],args['binding_id'],args['source_selections'],args['reason'])
        # Preparing a repair or rebuilding a view is not proof the original fault is gone.
        recovered=option=='RECOVER_CAPTURE' and result.get('state') in {'ACCEPTED','EXACT_DUPLICATE'}
        store.commit_incident(event('RECOVERY_RECORDED',{'proposal_id':pid,'status':'EXECUTED','result':result,
            'incident_status':'RECOVERED' if recovered else 'DIAGNOSED'}))
    except (PMRSError,KeyError,TypeError) as exc:
        result={'code':getattr(exc,'code','RECOVERY_INVALID'),'message':str(exc)}
        store.commit_incident(event('RECOVERY_RECORDED',{'proposal_id':pid,'status':'FAILED','result':result,'incident_status':'MAINTENANCE_REQUIRED'}))
    return store.read_snapshot()['recovery_proposals'][pid]

def task_tool(store,request_id,tool_name,arguments):
    s=store.read_snapshot();r=s['requests'].get(request_id,{});t=s['tasks'].get(r.get('task_id'),{})
    require(t.get('actor_kind')=='MAIN','AUTHORIZATION_REQUIRED','Only the main actor may request recovery operations')
    name=tool_name.replace('.','_');iid=arguments.get('incident_id')
    allowed={k:v for k,v in s.get('incidents',{}).items() if v['instance_id']==r['instance_id'] and v['mission_id']==r['mission_id']}
    if name=='runtime_inspect_incident':
        require(iid is None or iid in allowed,'INCIDENT_UNKNOWN','Incident is outside current authorization')
        return {'incidents':[allowed[iid]] if iid else list(allowed.values()),'model_calls':0}
    require(iid in allowed,'INCIDENT_UNKNOWN','Select an incident in this mission')
    if name=='runtime_list_recovery_options':return list_recovery_options(store,iid)
    require(name=='runtime_propose_recovery','TOOL_UNKNOWN',name)
    return propose_recovery(store,request_id,iid,arguments['option'],expected_revision=arguments['expected_revision'],
        idempotency_key=arguments['idempotency_key'],arguments=arguments.get('arguments'))
