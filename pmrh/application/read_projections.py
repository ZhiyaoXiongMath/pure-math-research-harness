"""Snapshot-only projections extracted from the frozen native query slices."""
from copy import deepcopy
from pmrh.domain.primitives import require, identity
from pmrh.domain.relations import premise_closure

def _cost(snapshot,request):
    # Unknown usage retains the full authorization reservation, never zero.
    if request['execution_state']=='CANCELLED_BEFORE_SEND':return 0
    return request.get('reserved_calls',1)

def budget_remaining(snapshot,grant_id):
    grant=snapshot.get('budget_grants',{}).get(grant_id,{})
    if grant.get('explicit_unlimited') is True:return float('inf')
    maximum=grant.get('max_calls',0)
    used=sum(_cost(snapshot,r) for r in snapshot.get('requests',{}).values() if r.get('budget_grant_id')==grant_id)
    return max(0,maximum-used)

def project_remaining(snapshot):
    budget=snapshot.get('project_budget',{'max_calls':0})
    if budget.get('explicit_unlimited') is True:return aggregate_project_remaining(snapshot)
    return min(aggregate_project_remaining(snapshot),max(0,budget.get('max_calls',0)-sum(_cost(snapshot,r) for r in snapshot.get('requests',{}).values()
        if r.get('budget_domain','SCIENCE')=='SCIENCE')))

def aggregate_project_remaining(snapshot):
    """An optional explicitly configured total includes every request domain."""
    budget=snapshot.get('project_total_budget')
    if not budget or budget.get('explicit_unlimited') is True:return float('inf')
    return max(0,budget.get('max_calls',0)-sum(_cost(snapshot,r) for r in snapshot.get('requests',{}).values()))

NATIVE_SCHEMA='pmrs.native-main/1'

GATE_REVISION='pmrs.native-admission/1'

def native_desired(snapshot,iid):
    i=snapshot['instances'][iid];c=i.get('run_control',{});mid=i.get('current_mission_id')
    mission=snapshot.get('missions',{}).get(mid)
    remaining=min(budget_remaining(snapshot,mission['budget_grant_id']),project_remaining(snapshot)) if mission else 0
    reason=(c.get('waiting_reason') or c.get('pause_reason') or i.get('pause_reason') or i.get('status'))
    if i.get('status')=='COMPLETE':
        decision=snapshot.get('main_decisions',{}).get(c.get('last_decision_ref'),{})
        if decision.get('action')=='COMPLETE' and decision.get('qualified_evidence'):return 'complete','QUALIFIED_SCIENTIFIC_COMPLETION'
    if i.get('status')!='ACTIVE' or not mission:return 'paused',str(reason or 'NO_ACTIVE_AUTHORIZATION')
    prepaid=any(r['instance_id']==iid and r.get('mission_id')==mid and r['execution_state'] in {'RESERVED','SENT'} and not r.get('fenced') and snapshot['tasks'][r['task_id']].get('actor_kind')=='MAIN' for r in snapshot.get('requests',{}).values())
    if remaining<=0 and not prepaid:return 'paused','BUDGET_EXHAUSTED'
    return 'active',None

def native_view(snapshot,iid):
    b=deepcopy(snapshot.get('native_main_bindings',{}).get(iid));want,reason=native_desired(snapshot,iid)
    g=(b or {}).get('observed_goal') or {}
    last_sync=(b or {}).get('last_sync')
    if not last_sync:
        observations=[e['payload'] for e in snapshot.get('native_main_events',{}).values() if e['payload'].get('instance_id')==iid and e['event_type']=='NATIVE_GOAL_ERROR']
        last_sync=max(observations,key=lambda x:x.get('observed_at',''),default=None)
    return {'schema':NATIVE_SCHEMA,'binding':b,'thread_id':(b or {}).get('thread_id'),'goal_id':None,
        'goal_identity':{'thread_id':g.get('threadId'),'created_at':g.get('createdAt'),'objective_sha256':(b or {}).get('objective_sha256')} if g else None,
        'desired_status':want,'observed_status':g.get('status','UNOBSERVED'),'observed_goal':g or None,
        'last_sync':last_sync,'last_observation':(b or {}).get('last_observation'),'control_revision':snapshot['instances'][iid].get('run_control',{}).get('control_version',0),
        'wait_reason':reason,'continuation_gate':{'revision':GATE_REVISION,'required':True,'scope':'ROOT_MAIN_ONLY','native_internal_limits':None},
        'goal_id_semantics':'Native API exposes threadId and createdAt, not an opaque Goal ID.',
        'turns':[deepcopy(t) for t in snapshot.get('native_main_turns',{}).values() if t['instance_id']==iid]}

def strategy_id(iid):return identity(iid,'STRATEGY-')

def strategy_current(s,iid):return s.get('strategies',{}).get(strategy_id(iid))

def effective_guidance(s,iid):
    rows=[d for d in s.get('human_directions',{}).values() if d['instance_id']==iid]
    rows.sort(key=lambda d:(d.get('created_at',''),d['direction_id']))
    replaced={old for d in rows for old in d.get('supersedes',[])+d.get('revokes',[])}
    active=[d for d in rows if d['direction_id'] not in replaced and d.get('status') not in {'REVOKED','SUPERSEDED'}]
    original=[{k:deepcopy(d.get(k)) for k in ('direction_id','text','refs','created_at','kind','source','supersedes','revokes','status','request_id','reply_ref')} for d in active]
    version=identity([[d['direction_id'],d['text'],d['refs'],d.get('kind')] for d in active],'GUIDANCE-')
    summaries=[g for g in s.get('research_guidance',{}).values() if g['instance_id']==iid and g['guidance_version']==version]
    deliveries=[]
    for task in s.get('tasks',{}).values():
        context=task.get('guidance_context',{})
        if task.get('instance_id')!=iid or not context.get('direction_ids'):continue
        request=s['requests'][task['request_id']]
        sent=request['execution_state'] in {'SENT','UNKNOWN','CAPTURED','SETTLED'}
        deliveries.append({'task_id':task['task_id'],'request_id':task['request_id'],
            'direction_ids':context['direction_ids'],'guidance_version':context['version'],
            'delivery_state':'FROZEN_INPUT_SENT' if sent else 'FROZEN_NOT_SENT',
            'actual_read_state':'NOT_INFERRED_FROM_DELIVERY','capture_ref':request.get('capture_ref')})
    return {'version':version,'original_directions':original,'current_summary':deepcopy(summaries[-1]) if summaries else None,
        'task_deliveries':deliveries,
        'interpretation':'Original human wording governs; discussion or suggestions do not grant execution authority.'}

def audit_view(s,iid):
    return {'clock':deepcopy(s.get('research_clocks',{}).get(iid)),
        'events':[deepcopy(r) for r in s.get('research_audit_events',{}).values() if r['instance_id']==iid],
        'audits':[deepcopy(r) for r in s.get('research_audits',{}).values() if r['instance_id']==iid],
        'checkpoints':[deepcopy(r) for r in s.get('research_checkpoints',{}).values() if r['instance_id']==iid],
        'guidance':effective_guidance(s,iid)}

def scope_refs(snapshot,instance_id=None):
    if instance_id is None:return set(snapshot['records'])
    require(instance_id in snapshot['instances'],'INSTANCE_UNKNOWN','Select an existing workflow')
    instance=snapshot['instances'][instance_id];roots=set()
    if instance.get('target_ref'):roots.add(instance['target_ref'])
    if instance.get('discovery_brief_ref'):roots.add(instance['discovery_brief_ref'])
    roots.update(instance.get('discovery_scope',{}).values())
    roots.update(instance.get('survey_scope',{}).get('selected_refs',[]))
    roots.update(instance.get('survey_scope',{}).get('source_refs',[]))
    for event in snapshot.get('production_events',{}).values():
        task=snapshot.get('tasks',{}).get(event.get('task_id'),{})
        if task.get('instance_id')==instance_id and event.get('record_ref') in snapshot['records']:
            roots.add(event['record_ref'])
    roots.update(c['statement_ref'] for c in snapshot.get('candidates',{}).values() if c['instance_id']==instance_id)
    for o in snapshot.get('obligations',{}).values():
        if any(c['instance_id']==instance_id for c in o['definition']['consumer_bindings']):
            roots.update(o['definition']['target_refs']);roots.update(o['projection'].get('evidence_refs',[]))
    for ref,r in snapshot['records'].items():
        if r['kind']=='Argument' and r['data']['conclusion_ref'] in roots:roots.add(ref)
        if r['kind']=='Example' and set(r['data']['target_refs'])&roots:roots.add(ref)
    return premise_closure(roots,snapshot,include_method_sources=True)

def status(snapshot,*,instance_id=None,report=None):
    instances={k:v for k,v in snapshot['instances'].items() if instance_id is None or k==instance_id}
    require(instance_id is None or instance_id in instances,'INSTANCE_UNKNOWN','Unknown workflow selector')
    requests=[r for r in snapshot.get('requests',{}).values() if instance_id is None or r['instance_id']==instance_id]
    if report is None:
        # The minimal status query reads journal facts only. It neither opens
        # report artifact paths nor upgrades stored reports to verified output.
        report=[{'report_id':rid,'state':r.get('status'),
                 'instance_ids':deepcopy(r.get('scope',{}).get('instance_ids',[])),
                 'file_verification':'UNOBSERVED'}
                for rid,r in snapshot.get('reports',{}).items()
                if instance_id is None or instance_id in r.get('scope',{}).get('instance_ids',[])]
    return {'commit':snapshot['knowledge_commit'],'project_id':snapshot['project_id'],'title':snapshot['title'],
            'mathematical':{'target_refs':[i['target_ref'] for i in instances.values() if i.get('target_ref')],
                'records':len(scope_refs(snapshot,instance_id)&set(snapshot['records'])),'qualification':'EXACT_CONSUMER_SCOPE_ONLY','formal_proof':'NOT_GRANTED'},
            'workflow':{'instances':deepcopy(list(instances.values())),
                'automatic_next_round':any(i.get('run_control',{}).get('mode')=='AUTO_P14' for i in instances.values())},
            'execution':{'requests':[{k:r.get(k) for k in ('request_id','execution_state','capture_ref','usage','fenced')} for r in requests],
                'running_processes':'NOT_INFERRED_FROM_WORKFLOW_STATUS','unknown':sum(r['execution_state']=='UNKNOWN' for r in requests)},
            'acceptance':{'pending_captures':sum(r['execution_state']=='CAPTURED' for r in requests),
                'accepted':sum(r.get('acceptance_state')=='ACCEPTED' for r in requests)},
            'report':report,'language_policy':snapshot['language_policy'],
            'native_usage':deepcopy(snapshot.get('usage',{})),
            'read_only':True,'model_calls':0}

def main_view(s,instance_id,*,cursor=0):
    require(instance_id in s['instances'],'INSTANCE_UNKNOWN',instance_id)
    require(s['instances'][instance_id]['kind'] in {'TRH','FDH'},'MAIN_NOT_APPLICABLE','SURVEY has a sequential workflow and no MAIN session')
    st=strategy_current(s,instance_id);instance=s['instances'][instance_id];mid=instance.get('current_mission_id')
    mission=s['missions'].get(mid,{})
    remaining=min(budget_remaining(s,mission['budget_grant_id']),project_remaining(s)) if mission else 0
    rows=[d for d in s.get('human_directions',{}).values() if d['instance_id']==instance_id]
    rows.sort(key=lambda d:(d['created_at'],d['direction_id']))
    reason=('NO_ACTIVE_AUTHORIZATION' if not mission else 'PAUSED' if instance['status']!='ACTIVE' else
            'BUDGET_EXHAUSTED' if remaining<=0 else (st or {}).get('waiting_reason'))
    active=s.get('requests',{}).get((st or {}).get('active_main_request_id'),{})
    memory=audit_view(s,instance_id)
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
