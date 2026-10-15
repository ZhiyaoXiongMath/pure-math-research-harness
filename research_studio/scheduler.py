"""Read-only obligation planning with stable leases and bounded fair selection."""
from copy import deepcopy
from .util import identity, require, PMRSError
from . import obligations
from .workflows.registry import validate_assignment, spec


from pmrh.application.read_projections import _cost as _cost

from pmrh.application.read_projections import budget_remaining as budget_remaining

from pmrh.application.read_projections import project_remaining as project_remaining

from pmrh.application.read_projections import aggregate_project_remaining as aggregate_project_remaining


def ordinary_preparations_since_account(snapshot):
    count=snapshot.get('scheduler_state',{}).get('ordinary_preparations_since_account')
    if count is not None:
        require(type(count) is int and 0<=count<=8,'SCHEDULER_STATE_INVALID','Invalid native preparation age.')
        return count
    # Legacy snapshots have no durable chronological index in their task/event
    # maps. Do not invent one from JSON key order. A bounded first accounting
    # turn is conservative; the next PREPARE persists the exact new counter.
    events=snapshot.get('execution_events',{})
    return min(8,sum(e.get('event_type')=='PREPARE' for e in events.values()) if events else len(snapshot.get('tasks',{})))

def validate_consumer_control(snapshot,consumer):
    """Resource execution may only implement an actual MAIN decision."""
    iid=consumer['instance_id'];kind=snapshot['instances'][iid]['kind']
    if kind not in {'TRH','FDH'} or consumer.get('actor_kind')=='MAIN' or consumer.get('report_context'):return
    ref=consumer.get('strategy_proposal_ref') or consumer.get('entry_basis',{}).get('strategy',{}).get('proposal_ref')
    proposal=snapshot.get('strategy_proposals',{}).get(ref)
    require(proposal and proposal.get('instance_id')==iid,'MAIN_DECISION_REQUIRED','A harness stage task requires a recorded actual MAIN decision.')
    control=snapshot.get('consumer_controls',{}).get(consumer.get('binding_id'),{})
    require(control.get('status','ACTIVE')=='ACTIVE','TASK_FENCED','MAIN parked or cancelled this unstarted responsibility.')
    route_ref=consumer.get('entry_basis',{}).get('strategy',{}).get('route_ref')
    route=snapshot.get('research_routes',{}).get(route_ref,{})
    require(route.get('status') not in {'PARKED','SUPERSEDED','EXHAUSTED','REFUTED_ON_SCOPE'},'TASK_FENCED','MAIN route disposition prevents new dispatch.')

def validate_task_control(snapshot,task):
    bindings=task.get('obligation_bindings',[])
    for binding in bindings:
        obligation=snapshot.get('obligations',{}).get(binding.get('obligation_id'),{})
        for consumer in obligation.get('definition',{}).get('consumer_bindings',[]):
            if consumer['binding_id']==binding['binding_id']:validate_consumer_control(snapshot,consumer)


def plan(snapshot,authorized_instances,policy=None):
    policy=policy or {};workers=8
    allowed=set(authorized_instances);actions=[];waits=[];ready=[]
    for iid in allowed:require(iid in snapshot.get('instances',{}),'INSTANCE_UNKNOWN',iid)
    from .host_pool import is_stage,instance_limit
    active_by_instance={iid:sum(is_stage(snapshot,r) and r['instance_id']==iid and r['execution_state'] in {'RESERVED','SENT','UNKNOWN'} for r in snapshot.get('requests',{}).values()) for iid in allowed}
    main_active={iid:sum(not is_stage(snapshot,r) and r['instance_id']==iid and r['execution_state'] in {'PREPARED','RESERVED','SENT','UNKNOWN'} for r in snapshot.get('requests',{}).values()) for iid in allowed}
    seen_purposes=set()
    for rid,r in sorted(snapshot.get('requests',{}).items()):
        if r.get('purpose')=='PROJECT_ASSISTANT':continue
        if r['instance_id'] not in allowed:continue
        status=r['execution_state'];purpose=r['purpose_key']
        if status=='PREPARED':
            try:validate_task_control(snapshot,snapshot['tasks'][r['task_id']])
            except PMRSError as exc:
                waits.append({'request_id':rid,'code':exc.code,'reason':exc.message});seen_purposes.add(purpose);continue
        ctx=snapshot.get('tasks',{}).get(r['task_id'],{}).get('report_context',{})
        if snapshot.get('reports',{}).get(ctx.get('report_id'),{}).get('status')=='ABANDONED':
            waits.append({'request_id':rid,'code':'REPORT_ABANDONED'})
            if status in obligations.PENDING:seen_purposes.add(purpose)
            continue
        if status=='PREPARED' and not ctx and r['mission_id']!=snapshot['instances'][r['instance_id']].get('current_mission_id'):
            waits.append({'request_id':rid,'code':'SUPERSEDED_MISSION'});seen_purposes.add(purpose);continue
        if ctx and status=='PREPARED':
            try:
                from .reports import dispatch_current
                dispatch_current(snapshot,ctx)
            except PMRSError as exc:
                waits.append({'request_id':rid,'code':exc.code,'reason':exc.message})
                seen_purposes.add(purpose);continue
        from .reports import dispatch_authorized
        dispatchable=dispatch_authorized(snapshot,ctx) if ctx else False
        dispatchable=dispatchable or snapshot['instances'][r['instance_id']]['status']=='ACTIVE'
        if status=='CAPTURED' and not r.get('fenced') and dispatchable:
            actions.append({'action':'RECOVER','request_id':rid,'reason':'PERSISTED_CAPTURE_FIRST'})
        elif status=='PREPARED' and not r.get('fenced') and dispatchable:
            actions.append({'action':'REUSE','request_id':rid,'reason':'REUSE_FROZEN_REQUEST'})
        elif status in {'RESERVED','SENT','UNKNOWN'}:
            waits.append({'request_id':rid,'code':('UNKNOWN_ABANDONED_RESERVATION_RETAINED' if r.get('unknown_disposition')=='ABANDON_UNKNOWN' else 'UNKNOWN_REQUIRES_EVIDENCE') if status=='UNKNOWN' else 'EXISTING_REQUEST'})
        if status in obligations.PENDING:seen_purposes.add(purpose)
    for oid,o in sorted(snapshot.get('obligations',{}).items()):
        if policy.get('only_obligation_ids') is not None and oid not in policy['only_obligation_ids']:continue
        d=o['definition']
        for consumer in d['consumer_bindings']:
            iid=consumer['instance_id']
            if iid not in allowed:continue
            if consumer['mission_id']!=snapshot['instances'][iid].get('current_mission_id') and not consumer.get('report_context'):
                continue
            if consumer['binding_id'] in snapshot.get('retired_consumers',{}):continue
            stage=consumer.get('stage_id');role=consumer.get('role')
            try:
                validate_consumer_control(snapshot,consumer)
                role_spec=validate_assignment(stage,d['type'],role,consumer.get('entry_basis',{}))
                obligations.validate_branch_dispositions(snapshot,consumer)
                if consumer.get('report_context'):
                    from .reports import dispatch_current
                    dispatch_current(snapshot,consumer['report_context'])
                from .model_policy import resolve
                if not resolve(spec(stage)['workflow_kind'],stage,role,consumer.get('work_purpose','DEFAULT'),actor_kind=consumer.get('actor_kind'),require_capability=False)['call_model']:
                    waits.append({'obligation_id':oid,'binding_id':consumer['binding_id'],'state':'LOCAL','code':'NO_MODEL_OPERATION'});continue
                decision=obligations.eligible(snapshot,o,consumer,role,method_ref=consumer.get('method_ref'))
                if decision['state']!='READY':
                    waits.append({'obligation_id':oid,'binding_id':consumer['binding_id'],**decision});continue
                mission=snapshot['missions'][consumer['mission_id']]
                scope=mission['authorized_scope']
                from .reports import dispatch_budget
                report_grant=dispatch_budget(snapshot,consumer)
                if not report_grant and scope.get('obligation_ids') and oid not in scope['obligation_ids'] and not scope.get('allow_derived_work') and not (d['type']=='REPORT' and scope.get('reports')):
                    waits.append({'obligation_id':oid,'code':'AUTHORIZATION_REQUIRED'});continue
                if not report_grant and scope.get('stage_ids') and stage not in scope['stage_ids']:
                    waits.append({'obligation_id':oid,'code':'AUTHORIZATION_REQUIRED'});continue
                if decision['purpose_key'] in seen_purposes:continue
                priority=(-1000000 if consumer.get('actor_kind')=='MAIN' else snapshot.get('consumer_controls',{}).get(consumer['binding_id'],{}).get('priority',consumer.get('priority',0)))
                ready.append({'obligation_id':oid,'definition_revision':d['definition_revision'],
                    'consumer':deepcopy(consumer),'instance_id':iid,'mission_id':consumer['mission_id'],
                    'stage_id':stage,'role':role,'stage_spec_digest':role_spec['stage_spec_digest'],
                    'budget_grant_id':report_grant or mission['budget_grant_id'],'budget_domain':snapshot['budget_grants'][report_grant or mission['budget_grant_id']].get('budget_domain','SCIENCE'),'priority':priority,
                    'ready_since':consumer.get('ready_since',0),**decision})
            except PMRSError as exc:waits.append({'obligation_id':oid,'binding_id':consumer['binding_id'],'state':'REJECT','code':exc.code,'reason':exc.message})
    # PREPARE increments/resets this counter under the native Store write lock.
    # Task and event dictionaries are content-addressed maps, never a timeline.
    demand_by_grant={}
    for row in ready:
        gid=row['budget_grant_id'];demand_by_grant[gid]=demand_by_grant.get(gid,0)+1
    science_demand=sum(min(n,budget_remaining(snapshot,gid)) for gid,n in demand_by_grant.items() if snapshot['budget_grants'][gid].get('budget_domain','SCIENCE')=='SCIENCE')
    independent_demand=sum(min(n,budget_remaining(snapshot,gid)) for gid,n in demand_by_grant.items() if snapshot['budget_grants'][gid].get('budget_domain','SCIENCE')!='SCIENCE')
    ready_demand=min(aggregate_project_remaining(snapshot),min(project_remaining(snapshot),science_demand)+independent_demand)
    existing_demand=sum(r.get('purpose')!='PROJECT_ASSISTANT' and r['instance_id'] in allowed and r['execution_state'] in {'PREPARED','RESERVED','SENT','UNKNOWN'} for r in snapshot.get('requests',{}).values())
    last=snapshot.get('scheduler_state',{}).get('last_instance_by_tier',{})
    chosen=[];budget_used={};selected_scopes=[];project_available=project_remaining(snapshot)
    science_selected=0;total_available=aggregate_project_remaining(snapshot);chosen_stage={iid:0 for iid in allowed};chosen_main={iid:0 for iid in allowed}
    for tier in sorted({r['priority'] for r in ready}):
        queues={iid:sorted([r for r in ready if r['priority']==tier and r['instance_id']==iid],key=lambda r:(r['ready_since'],r['consumer']['binding_id'])) for iid in sorted(allowed)}
        order=[iid for iid in queues if queues[iid]]
        previous=last.get(str(tier))
        if previous in order:
            pos=order.index(previous);order=order[pos+1:]+order[:pos+1]
        while any(queues[iid] for iid in order):
            for iid in order:
                if not queues[iid]:continue
                row=queues[iid].pop(0);gid=row['budget_grant_id'];scope=row['consumer'].get('write_scope',[])
                main=row['consumer'].get('actor_kind')=='MAIN'
                capacity_ok=(main_active[iid]+chosen_main[iid]<1) if main else (active_by_instance[iid]+chosen_stage[iid]<instance_limit(snapshot,iid))
                if not capacity_ok or len(chosen)>=total_available or row.get('budget_domain','SCIENCE')=='SCIENCE' and science_selected>=project_available:
                    waits.append({'obligation_id':row['obligation_id'],'code':'BUDGET_OR_WORKER_LIMIT'});continue
                if budget_remaining(snapshot,gid)<=budget_used.get(gid,0):
                    waits.append({'obligation_id':row['obligation_id'],'code':'BUDGET_EXHAUSTED'});continue
                if any(set(scope)&set(other) for other in selected_scopes):
                    waits.append({'obligation_id':row['obligation_id'],'code':'WRITE_CAS_CONFLICT'});continue
                if row['purpose_key'] in seen_purposes:continue
                chosen.append(row)
                if main:chosen_main[iid]+=1
                else:chosen_stage[iid]+=1
                seen_purposes.add(row['purpose_key']);budget_used[gid]=budget_used.get(gid,0)+1;selected_scopes.append(scope)
                if row.get('budget_domain','SCIENCE')=='SCIENCE':science_selected+=1
    value={'schema':'pmrs.dispatch-plan/1','knowledge_commit':snapshot.get('knowledge_commit'),
           'actions':actions,'selected':chosen,'waits':waits,'max_workers':workers,
           'ready_demand':existing_demand+ready_demand,
           'ready_by_instance':{iid:active_by_instance[iid]+sum(row['instance_id']==iid and row['consumer'].get('actor_kind')!='MAIN' for row in ready)+sum(r['instance_id']==iid and is_stage(snapshot,r) and r['execution_state']=='PREPARED' and not r.get('fenced') for r in snapshot.get('requests',{}).values()) for iid in allowed},
           'state':'READY' if actions or chosen else 'WAIT','model_calls':0}
    value['plan_id']=identity(value,'PLAN-');return value

plan_dispatch=plan


def commit_dispatch(store,dispatch_plan,*,policy=None):
    """The event reducer rechecks relevant state under Store's single write lock."""
    from . import tasks,execution
    snapshot=store.read_snapshot(); prepared=[]
    for candidate in dispatch_plan['selected']:
        candidate=deepcopy(candidate);consumer=candidate['consumer']
        if not consumer.get('visit_id'):
            binding={'binding_id':consumer['binding_id'],'obligation_id':candidate['obligation_id'],
                     'expected_definition_revision':candidate['definition_revision']}
            basis=consumer.get('entry_basis',{})
            matches=[v for v in snapshot.get('visits',{}).values() if v['instance_id']==candidate['instance_id']
                and v['mission_id']==candidate['mission_id'] and v['stage_id']==candidate['stage_id']
                and v['entry_basis']==basis and v.get('outcome') is None and binding in v['assigned_obligation_bindings']]
            if matches:consumer['visit_id']=sorted(matches,key=lambda x:x['visit_id'])[0]['visit_id']
            else:
                visit={'instance_id':candidate['instance_id'],'mission_id':candidate['mission_id'],
                       'stage_id':candidate['stage_id'],'stage_spec_digest':candidate['stage_spec_digest'],
                       'assigned_obligation_bindings':[binding],'entry_basis':deepcopy(basis)}
                visit['visit_id']=identity({**visit,'sequence':len(snapshot.get('visits',{}))},'VISIT-')
                store.commit_execution(execution.event('VISIT_OPENED',{'visit':visit}))
                consumer['visit_id']=visit['visit_id'];snapshot=store.read_snapshot()
        task_policy=policy or {}
        if task_policy.get('mission_policies'):
            task_policy=snapshot['budget_grants'][candidate['budget_grant_id']].get('execution_policy',{})
        task=tasks.freeze(store,snapshot,candidate,task_policy)
        e=execution.event('PREPARE',{'task':task,'candidate':candidate,'max_workers':dispatch_plan['max_workers']})
        receipt=store.commit_execution(e);prepared.append({'task_id':task['task_id'],'request_id':task['request_id'],'receipt':receipt})
        snapshot=store.read_snapshot()
    return {'prepared':prepared,'actions':dispatch_plan['actions'],'waits':dispatch_plan['waits'],'model_calls':0}


def register_coverage_plan(store,instance_id,plan,requirement,support_id):
    """Schedule exact parts under a pre-existing finite research mission."""
    from . import execution,assurance,contracts as C,obligations as O
    from .engine import _assign_followup
    s=store.read_snapshot();instance=s['instances'][instance_id];mission=s['missions'][instance['current_mission_id']]
    require(instance['kind']=='SURVEY','MAIN_DECISION_REQUIRED','Independent coverage work must be explicitly selected by the harness MAIN.')
    store.commit_execution(execution.event('COVERAGE_PLAN_REGISTERED',{'instance_id':instance_id,'mission_id':mission['mission_id'],
        'plan':plan,'requirement':requirement,'support_id':support_id}))
    for part in plan['parts']:
        slot=next(x for x in requirement['review_slots'] if x['slot_id']==part['review_slot_id']);role=slot['allowed_roles'][0]
        req=deepcopy(requirement);req['required_scope']=deepcopy(part['checked_scope'])
        for x in req['review_slots']:x['required_scope']=deepcopy(part['checked_scope'])
        oid=identity({'plan':plan['plan_id'],'part':part['part_id']},'OB-')
        criterion=store.blob(b'Independently review only the explicitly assigned exact original segments. All complete premises and boundaries must be supplied. Do not extrapolate this local review to unprovided scope or global integration.')
        c={'binding_id':'BINDING-'+oid,'instance_id':instance_id,'mission_id':mission['mission_id'],'stage_id':'P9','role':role,
           'retry_grant_id':'RETRY-'+oid,'method_ref':'COVERAGE_PART','scope':part['checked_scope'],'input_refs':part['required_input_refs'],
           'source_refs':[],'threshold':'WORK_DISPOSITION_RECORDED','required_assurance':req,'selected_support':support_id,
           'max_responsibility_attempts':len(requirement['review_slots']),'policy_digest':C.digest(requirement),'coverage_plan_id':plan['plan_id'],'coverage_part_id':part['part_id'],
           'coverage_part':deepcopy(part),'entry_basis':{'consumer_requirement':req}}
        o=O.make(oid,'VERIFY',[s['supports'][support_id]['statement_ref']],criterion,created_by=plan['plan_id'],effect='PARTIAL_EXACT_COVERAGE')
        _assign_followup(store,instance,mission,o,c,basis_ref=plan['plan_id'])
    return {'plan_id':plan['plan_id'],'model_calls':0}


def coverage_status(snapshot,plan_id):
    from .assurance import coverage_plan_evidence
    return coverage_plan_evidence(snapshot,plan_id)


def derive_coverage_integration(store,instance_id):
    from . import assurance,contracts as C,obligations as O
    from .engine import _assign_followup
    s=store.read_snapshot();instance=s['instances'][instance_id];mission=s['missions'].get(instance['current_mission_id']);added=[]
    if instance['kind'] in {'TRH','FDH'}:return added
    if not mission:return added
    for pid,row in s.get('coverage_plans',{}).items():
        if row['instance_id']!=instance_id or row['mission_id']!=mission['mission_id']:continue
        plan=row['plan'];_,results,_=coverage_status(s,pid)
        if any(results.get(p['part_id'],{}).get('result')!='QUALIFIED' for p in plan['parts']):continue
        if not plan['integration_scope']:continue  # No-interface attestation is never fabricated by a scheduler.
        oid=identity({'plan':pid,'integration':plan['integration_scope']},'OB-')
        if oid in s['obligations']:continue
        scope=plan['integration_scope'];req=assurance.requirement('INTEGRATION',scope)
        roots=sorted({x['target_ref'] for x in scope}|{r for p in plan['parts'] for r in p['declared_boundary_refs']})
        criterion=store.blob(b'Independently check the exact cross-part interfaces, global quantifiers and shared witnesses on original material. Prior part verdicts do not substitute for mathematical premises. Report any remaining unchecked integration scope.')
        c={'binding_id':'BINDING-'+oid,'instance_id':instance_id,'mission_id':mission['mission_id'],'stage_id':'P12','role':'INDEPENDENT',
           'retry_grant_id':'RETRY-'+oid,'method_ref':'COVERAGE_INTEGRATION','scope':scope,'input_refs':roots,'source_refs':[],
           'threshold':'WORK_DISPOSITION_RECORDED','required_assurance':req,'selected_support':row['support_id'],
           'policy_digest':C.digest(row['requirement']),'coverage_plan_id':pid,'coverage_part_id':None,
           'entry_basis':{'new_integration_scope':scope,'consumer_requirement':req}}
        if all(x['locators'] for x in scope):
            targets={x['target_ref'] for x in scope}
            common=sorted(({r for p in plan['parts'] for r in p['required_input_refs']}|{r for p in plan['parts'] for r in p['declared_boundary_refs']})-targets)
            c['coverage_part']={'part_id':'INTEGRATION','review_slot_id':'independent','checked_scope':scope,
                'required_input_refs':common,'declared_boundary_refs':[],'task_ref':None}
        o=O.make(oid,'VERIFY',[s['supports'][row['support_id']]['statement_ref']],criterion,created_by=pid,effect='INDEPENDENT_GLOBAL_INTERFACE')
        added.append(_assign_followup(store,instance,mission,o,c,basis_ref=pid))
    return added
