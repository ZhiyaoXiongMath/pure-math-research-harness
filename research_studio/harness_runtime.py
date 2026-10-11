"""Event admission for MAIN; deliberately contains no P/D-stage choice."""
from copy import deepcopy
from .util import identity,require
from . import strategy,obligations as O

TERMINAL={'SETTLED','CANCELLED_BEFORE_SEND'}

def maintenance(store,iid):
    """Host-only timer/event observation; never select or dispatch research."""
    from . import research_audit
    research_audit.observe(store,iid)
    s=store.read_snapshot();instance=s['instances'][iid];mid=instance.get('current_mission_id')
    st=strategy.current(s,iid)
    base={'should_wake':False,'model_calls':0,'clock':s.get('research_clocks',{}).get(iid),
        'pending_audit_event_ids':[e['event_id'] for e in s.get('research_audit_events',{}).values()
            if e['instance_id']==iid and e['status']=='PENDING' and e['kind']=='FULL_STRATEGIC_AUDIT_DUE']}
    if instance['kind'] not in {'TRH','FDH'} or not st:return {**base,'reason':'NO_ACTIVE_HARNESS'}
    control=instance.get('run_control',{})
    if instance.get('status')!='ACTIVE' or control.get('state') in {'WAITING_HUMAN_AT_P14','WAITING_HUMAN_AT_D5','COMPLETE','OPEN_ENDED'}:
        return {**base,'reason':control.get('state') if control.get('state') in {'WAITING_HUMAN_AT_P14','WAITING_HUMAN_AT_D5','COMPLETE','OPEN_ENDED'} else instance.get('status')}
    from .scheduler import budget_remaining,project_remaining
    mission=s['missions'][mid]
    if mission.get('status')!='ACTIVE' or min(budget_remaining(s,mission['budget_grant_id']),project_remaining(s))<=0:
        return {**base,'reason':'NO_REMAINING_AUTHORIZATION'}
    active=st.get('active_main_request_id')
    if active and s['requests'][active]['execution_state'] not in TERMINAL:return {**base,'reason':'MAIN_ALREADY_ACTIVE'}
    # A pending MAIN obligation is already a wakeup; never duplicate it.
    bindings=[(o,c) for o in s['obligations'].values() for c in o['definition']['consumer_bindings']
        if c['instance_id']==iid and c['mission_id']==mid and c.get('actor_kind')=='MAIN']
    for o,c in bindings:
        reqs=[r for r in s['requests'].values() if any(b['binding_id']==c['binding_id'] for b in s['tasks'][r['task_id']].get('obligation_bindings',[]))]
        if not reqs:return {**base,'reason':'MAIN_ALREADY_QUEUED'}
        if any(r['execution_state'] not in TERMINAL for r in reqs):return {**base,'reason':'MAIN_ALREADY_ACTIVE'}
        # A rejected MAIN has no substitute scientific controller. Preserve the
        # original request for finite format recovery or explicit maintenance.
        from .main_recovery import authorized_for
        if not any(r.get('acceptance_state')=='ACCEPTED' for r in reqs) and not all(authorized_for(s,r) for r in reqs):
            return {**base,'reason':'MAIN_CAPTURE_REQUIRES_RECOVERY'}
    from .main_recovery import pending as pending_recoveries
    recoveries=pending_recoveries(s,iid,mid)
    prior=s.get('strategy_proposals',{}).get(st.get('last_accepted_proposal_ref'))
    digest=strategy.frontier_digest(s,iid,mid)
    pending=[d for d in strategy.pending_directions(s,iid) if not d.get('request_id')]
    changed=prior is None or prior.get('frontier_digest')!=digest or bool(pending)
    prior_decision=(prior or {}).get('proposal',{})
    p14_self_continue=prior_decision.get('next_action')=='P14' and (prior_decision.get('p14_decision') or {}).get('action')=='CONTINUE' and not prior_decision.get('work_items')
    explicit_followup=bool(prior_decision.get('main_followup') or p14_self_continue)
    observed=research_audit.phase(s,iid)
    audit_ready=bool(base['pending_audit_event_ids']) and observed['reason'] not in {
        'WAIT_FOR_INPUT','WAIT_FOR_RESOURCE','WAIT_FOR_USER','EXPLICIT_WAIT','RESOURCE_ADMISSION_WAIT',
        'BUDGET_EXHAUSTED','NO_ACTIVE_AUTHORIZATION','TRANSPORT_UNCERTAIN'}
    resource_event=None
    if prior and st.get('next_action')=='WAIT':
        if not strategy.wait_ready(s,iid,st,pending=pending) and not audit_ready and not recoveries:return {**base,'reason':'UNCHANGED_EXPLICIT_WAIT'}
        if (st.get('wait_condition') or {}).get('kind')=='WAIT_FOR_RESOURCE':
            resource_event=strategy.resource_state(s,iid);changed=True
    if not changed and not explicit_followup and not audit_ready and not recoveries:return {**base,'reason':'NO_NEW_RESEARCH_EVENT'}
    if prior and strategy.completed_global(s,iid) and control.get('state') not in {'RUNNING','WAITING_CONDITION'}:return {**base,'reason':'DELIVERED_WAITING_CONTROL'}
    event_basis=[digest,sorted(d['direction_id'] for d in pending),st['revision'] if explicit_followup else None,resource_event,
        base['pending_audit_event_ids'] if audit_ready else []]
    if recoveries:event_basis.append({'main_execution_recovery_refs':recoveries})
    key=identity(event_basis)
    if any(c.get('entry_basis',{}).get('main_event_key')==key for _,c in bindings):return {**base,'reason':'EVENT_ALREADY_DELIVERED'}
    return {**base,'should_wake':True,'main_event_key':key,'main_execution_recovery_refs':recoveries,'reason':'MAINTENANCE_RECOVERY' if recoveries else 'INITIAL_RESEARCH' if prior is None else
        'FULL_STRATEGIC_AUDIT_DUE' if audit_ready else 'EXPLICIT_MAIN_FOLLOWUP' if explicit_followup else 'RELEVANT_RESEARCH_EVENT'}

def advance(store,s,instance,mission):
    iid=instance['instance_id'];mid=mission['mission_id']
    strategy.initialize(store,iid)
    wake=maintenance(store,iid)
    if not wake['should_wake']:return []
    s=store.read_snapshot();instance=s['instances'][iid];mission=s['missions'][mid];st=strategy.current(s,iid)
    control=instance.get('run_control',{});key=wake['main_event_key']
    sid='MAIN_'+instance['kind'];cfg=mission['authorized_scope']['autoflow']
    strategy.trigger(store,iid,wake['reason']+(':'+','.join(wake['pending_audit_event_ids']) if wake['reason']=='FULL_STRATEGIC_AUDIT_DUE' else ''),sid)
    s=store.read_snapshot();st=strategy.current(s,iid)
    refs=set(cfg['selected_refs'])
    from .research_audit import context as memory_context
    memory=memory_context(s,iid);checkpoint=memory.get('latest_checkpoint')
    incremental={r['request_id'] for r in memory['incremental_requests']}
    requests={r['request_id'] for r in s['requests'].values() if r.get('instance_id')==iid and r.get('acceptance_state')=='ACCEPTED'
        and (checkpoint is None or r['request_id'] in incremental)}
    if checkpoint:refs.update(r for r in checkpoint['evidence_refs'] if r in s['records'])
    refs.update(e['record_ref'] for e in s.get('production_events',{}).values() if e.get('request_id') in requests)
    refs.update(c['statement_ref'] for c in s.get('candidates',{}).values() if c['instance_id']==iid)
    criterion=('Read the complete '+instance['kind']+' method manual and exact original materials. Decide the next scientific work from the current evidence; no P/D stage has been selected by the host. '
        'Give a concrete strategy, communicate with tasks, do substantive mathematics where justified, and account honestly for limitations. '
        'Latest user execution authorization supersedes any historical intent paragraph requiring manual continuation: TRH AUTO_P14 is authorized within the same original target and existing total allowance, unless run_control says HUMAN_P14 or stop requested. '
        'Read current effective guidance, the latest published research checkpoint and exact subsequent increments before choosing work. '
        'If a full strategic audit is due, account for all routes/candidates, evidence, progress or uncertainty and cross-route failures in an actual research_audit checkpoint. '
        'Event identity: '+key)
    cref=store.blob(criterion.encode());oid=identity([iid,mid,key],'MAIN-OB-');bid='BINDING-'+oid
    c={'binding_id':bid,'instance_id':iid,'mission_id':mid,'stage_id':sid,'role':'MAIN_DECIDE',
       'actor_kind':'MAIN','work_purpose':'MAIN_STRATEGY','strategy_ref':st['strategy_id'],'strategy_revision':st['revision'],
       'round_number':control.get('round_number',1),'retry_grant_id':'RETRY-'+bid,'method_ref':'MAIN_EVENT_DECISION','scope':{'target_refs':cfg['selected_refs']},
       'entry_basis':{'main_event_key':key,'main_execution_recovery_refs':wake.get('main_execution_recovery_refs',[])},'input_refs':sorted(refs),
       'source_refs':sorted(set(cfg['source_refs']+[cfg['intent_source_ref']]+list(mission['authorized_scope'].get('discovery_scope',{}).values()))),
       'threshold':'WORK_DISPOSITION_RECORDED','success_criterion':cref,'ready_since':s.get('_snapshot_sequence',0)}
    o=O.make(oid,'ACCOUNT',cfg['selected_refs'],cref,consumer_bindings=[c],dependencies=[],created_by='MAIN_EVENT_ADMISSION',effect='MAIN_DECISION_REQUIRED')
    from .engine import _assign_followup
    return [_assign_followup(store,instance,mission,o,c,basis_ref=mission['intent_ref'])]
