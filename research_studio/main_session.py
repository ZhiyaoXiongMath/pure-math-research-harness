"""Native guidance, persistent MAIN identity and evidence-bound recovery views."""
from copy import deepcopy
from .util import require,identity,now
from . import strategy

def authorize_execution_recovery(store,instance_id,request_id,capture_ref,repair_reason,authorization_note,*,client_action_id):
    from .main_recovery import authorize
    return authorize(store,instance_id,request_id,capture_ref,repair_reason,authorization_note,client_action_id=client_action_id)

def submit_direction(store,instance_id,text,*,client_action_id,refs=None,kind='GUIDANCE',source='DIRECT_USER',supersedes=None,revokes=None):
    s=store.read_snapshot();require(instance_id in s['instances'],'INSTANCE_UNKNOWN',instance_id)
    require(s['instances'][instance_id]['kind'] in {'TRH','FDH'},'MAIN_NOT_APPLICABLE','SURVEY has a sequential workflow and no MAIN session')
    require(isinstance(client_action_id,str) and client_action_id,'IDEMPOTENCY_REQUIRED','A client action identity is required')
    require(kind in {'GUIDANCE','QUESTION','DISCUSSION','EXECUTION_INSTRUCTION','SOURCE_REQUIREMENT','ROUTE_CONSTRAINT'},'DIRECTION_INVALID','Classify the actual human wording without promoting discussion to authorization')
    prior=list(supersedes or [])+list(revokes or [])
    require(all(s.get('human_directions',{}).get(ref,{}).get('instance_id')==instance_id for ref in prior),'DIRECTION_INVALID','Only this MAIN instance\'s original guidance may be superseded or revoked')
    mid=s['instances'][instance_id].get('current_mission_id');did=identity([instance_id,client_action_id],'DIRECTION-')
    d={'schema':'pmrs.human-direction/1','direction_id':did,'client_action_id':client_action_id,
       'instance_id':instance_id,'mission_id':mid,'text':text,'refs':list(refs or []),
       'kind':kind,'source':source,'supersedes':list(supersedes or []),'revokes':list(revokes or []),
       'submitted_at_commit':s['knowledge_commit'],'created_at':now(),'status':'QUEUED','request_id':None,'reply_ref':None}
    result=store.commit_strategy(strategy.event('HUMAN_DIRECTION_SUBMITTED',{'instance_id':instance_id,'mission_id':mid,'direction':d}))
    return {**result,'direction_id':did,'status':store.read_snapshot()['human_directions'][did]['status'],'model_calls':0}

def view(store,instance_id,*,cursor=0,snapshot=None):
    s=store.read_snapshot() if snapshot is None else snapshot
    require(instance_id in s['instances'],'INSTANCE_UNKNOWN',instance_id)
    require(s['instances'][instance_id]['kind'] in {'TRH','FDH'},'MAIN_NOT_APPLICABLE','SURVEY has a sequential workflow and no MAIN session')
    st=strategy.current(s,instance_id);instance=s['instances'][instance_id];mid=instance.get('current_mission_id')
    mission=s['missions'].get(mid,{})
    from .scheduler import budget_remaining,project_remaining
    remaining=min(budget_remaining(s,mission['budget_grant_id']),project_remaining(s)) if mission else 0
    rows=[d for d in s.get('human_directions',{}).values() if d['instance_id']==instance_id]
    rows.sort(key=lambda d:(d['created_at'],d['direction_id']))
    reason=('NO_ACTIVE_AUTHORIZATION' if not mission else 'PAUSED' if instance['status']!='ACTIVE' else
            'BUDGET_EXHAUSTED' if remaining<=0 else (st or {}).get('waiting_reason'))
    active=s.get('requests',{}).get((st or {}).get('active_main_request_id'),{})
    from . import research_audit
    memory=research_audit.view(s,instance_id)
    routes=[]
    for route_ref in st['route_refs'] if st else []:
        route=deepcopy(s['research_routes'][route_ref])
        route['task_ids']=[tid for tid,t in s['tasks'].items() if t['instance_id']==instance_id and t.get('entry_basis',{}).get('strategy',{}).get('route_ref')==route_ref]
        cids={c['checkpoint_id'] for c in memory['checkpoints'] if any(row['route_key']==route['route_key'] for row in c['account']['route_assessments'])}
        route['audit_ids']=[a['audit_id'] for a in memory['audits'] if a['checkpoint_id'] in cids]
        route['last_audit_id']=route['audit_ids'][-1] if route['audit_ids'] else None
        route['guidance_version']=memory['guidance']['version'];routes.append(route)
    native=None
    try:
        from .native_main import view as native_view
        native=native_view(s,instance_id)
    except ImportError:pass
    return {'schema':'pmrs.main-session/1','main_actor_id':'MAIN-'+instance_id,'instance_id':instance_id,'mission_id':mid,
        'workflow_kind':instance['kind'],'research_audit':memory,'native_goal':native,
        'as_of_commit':s['knowledge_commit'],'target_ref':instance.get('target_ref'),'strategy':st,
        'routes':routes,
        'directions':rows[max(0,cursor):max(0,cursor)+100],'next_cursor':max(0,cursor)+100 if len(rows)>max(0,cursor)+100 else None,
        'proposals':[p for p in s.get('strategy_proposals',{}).values() if p['instance_id']==instance_id],
        'execution_recoveries':[deepcopy(r) for r in s.get('main_execution_recoveries',{}).values() if r['instance_id']==instance_id],
        'execution_state':active.get('execution_state','IDLE'),'active_request_id':active.get('request_id'),
        'waiting_reason':reason,'remaining_calls':remaining if remaining!=float('inf') else None,
        'model':{'model':'gpt-6-astra','reasoning_effort':'ultra','policy_version':'pmrs.main-model-policy/1'},
        'model_calls':0,'read_only':True,'background_lifetime':'PMRS_BACKEND','automatic_next_round':instance.get('run_control',{}).get('mode')=='AUTO_P14',
        'run_control':instance.get('run_control'),
        'method_version':'pmrs.harness-methods/4.2.2',
        'internal_delegation':{'allowed':True,'pmrs_limits':None},
        'inbox':[m for m in s.get('research_messages',{}).values() if m.get('instance_id')==instance_id]}
