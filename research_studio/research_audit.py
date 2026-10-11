"""Evidence-bound research time and MAIN-authored immutable research memory.

This module never chooses scientific work. Its host observations are not audits,
and its durable research checkpoints are unrelated to Store replay caches.
"""
from copy import deepcopy
from datetime import datetime, timezone
import re
from .util import now, identity, sha, require, loads

MAPS=frozenset({'research_clocks','research_audit_events','research_checkpoints','research_audits','research_guidance'})
DEFAULT_POLICY={'light_check_seconds':1800,'full_audit_seconds':14400,'observation_seconds':60}
PROGRESS={'SIGNIFICANT','LIMITED_REAL','NO_REAL_PROGRESS','NOT_EVALUATED','INSUFFICIENT_EVIDENCE','IN_PROGRESS'}

def verified_runtime_contexts(s,task,blob_get,*,live=False):
    """Read only actually transported context bodies bound to this exact turn.

    Navigation steers and prepared-but-unconfirmed responses are insufficient.
    Frozen knowledge and later deliveries keep distinct provenance identities.
    """
    if not task.get('communication_contract') or blob_get is None:return []
    rid=task['request_id'];request=s['requests'][rid]
    rows=sorted([d for d in s.get('input_deliveries',{}).values() if d.get('request_id')==rid
        and d.get('tool_name')=='main_runtime_context' and d.get('confirmed')],key=lambda d:d['sequence'])
    if not rows:return []
    from .input_delivery import capture_binding
    if live:
        from .communication import bound_request
        bound_request(s,rid,request['execution_id'])
    else:capture_binding(s,rid)
    result=[]
    for delivery in rows:
        require(delivery['execution_id']==request['execution_id'],'INPUT_DELIVERY_INVALID','Runtime context belongs to the original MAIN execution')
        raw=blob_get(delivery['response_ref'])
        require(sha(raw)==delivery['response_ref'] and len(raw)==delivery['bytes'],'ORIGINAL_BYTES_MISMATCH','Runtime context response bytes changed')
        response=loads(raw)
        if response.get('isError'):continue
        payload=loads(response['content'][0]['text']);value=payload.get('result',{})
        if value.get('schema')!='pmrs.main-runtime-context/4.2.2':continue
        require(payload.get('delivery_id')==delivery['delivery_id'] and value.get('request_id')==rid
            and value.get('instance_id')==task['instance_id'],'INPUT_DELIVERY_INVALID','Runtime context must bind its actual owning MAIN request')
        for original in value.get('effective_guidance',{}).get('original_directions',[]):
            native=s.get('human_directions',{}).get(original['direction_id'],{})
            require(native.get('instance_id')==task['instance_id'] and all(native.get(k)==original.get(k) for k in ('text','refs','kind','source','supersedes','revokes')),
                'ORIGINAL_BYTES_MISMATCH','Delivered guidance must preserve original human wording and scope')
        for item in value.get('pending_audit_events',[]):
            require(s.get('research_audit_events',{}).get(item['event_id'],{}).get('instance_id')==task['instance_id'],
                'INPUT_DELIVERY_INVALID','Delivered audit event belongs to this MAIN')
        result.append({**deepcopy(value),'delivery_id':delivery['delivery_id'],'response_ref':delivery['response_ref'],
            'delivery_sequence':delivery['sequence']})
    return result

def seconds(at):
    return int(datetime.fromisoformat(at.replace('Z','+00:00')).timestamp())

def policy(s,iid):
    value={**DEFAULT_POLICY,**s['instances'][iid].get('research_audit_policy',{})}
    require(all(type(v) is int and v>0 for v in value.values()),'AUDIT_POLICY_INVALID','Audit intervals must be positive integer seconds')
    return value

def phase(s,iid):
    instance=s['instances'][iid];control=instance.get('run_control',{})
    mission=s.get('missions',{}).get(instance.get('current_mission_id'),{})
    if instance.get('status')!='ACTIVE':
        reason=control.get('state') if control.get('state') in {'WAITING_HUMAN_AT_P14','WAITING_HUMAN_AT_D5','COMPLETE','OPEN_ENDED'} else instance.get('status')
        return {'effective':False,'reason':reason,'active_request_ids':[]}
    if control.get('state') in {'WAITING_HUMAN_AT_P14','WAITING_HUMAN_AT_D5','COMPLETE','OPEN_ENDED'}:
        return {'effective':False,'reason':control['state'],'active_request_ids':[]}
    if not mission or mission.get('status')!='ACTIVE':
        return {'effective':False,'reason':'NO_ACTIVE_AUTHORIZATION','active_request_ids':[]}
    requests=[r for r in s.get('requests',{}).values() if r.get('instance_id')==iid and r.get('mission_id')==mission['mission_id']]
    active=sorted(r['request_id'] for r in requests if r.get('execution_state')=='SENT')
    # The instance clock runs once, including MAIN/internal work and live stages.
    if active:return {'effective':True,'reason':'ACTUAL_RESEARCH_IN_FLIGHT','active_request_ids':active}
    if any(r.get('execution_state')=='UNKNOWN' for r in requests):
        return {'effective':False,'reason':'TRANSPORT_UNCERTAIN','active_request_ids':[],'evidence_incomplete':True}
    from .scheduler import budget_remaining,project_remaining
    if min(budget_remaining(s,mission['budget_grant_id']),project_remaining(s))<=0:
        return {'effective':False,'reason':'BUDGET_EXHAUSTED','active_request_ids':[]}
    from .strategy import current
    st=current(s,iid) or {};wait=st.get('wait_condition') or {}
    if st.get('next_action')=='WAIT' or control.get('state')=='WAITING_CONDITION':
        return {'effective':False,'reason':wait.get('kind') or 'EXPLICIT_WAIT','active_request_ids':[]}
    if any(r.get('execution_state') in {'PREPARED','RESERVED'} for r in requests):
        return {'effective':False,'reason':'RESOURCE_ADMISSION_WAIT','active_request_ids':[]}
    return {'effective':False,'reason':'NO_OBSERVED_ACTIVE_RESEARCH','active_request_ids':[]}

def _append_interval(clock,start,end,previous):
    delta=max(0,seconds(end)-seconds(start))
    if not delta:return
    if previous.get('effective'):clock['effective_seconds']+=delta
    row={'from':start,'to':end,'seconds':delta,'effective':previous.get('effective',False),
        'reason':previous.get('reason'),'evidence_request_ids':previous.get('active_request_ids',[])}
    if previous.get('evidence_incomplete'):
        row['evidence_incomplete']=True
        clock.setdefault('uncertainty_intervals',[]).append(deepcopy(row))
    intervals=clock.setdefault('intervals',[])
    if intervals and all(intervals[-1].get(k)==row.get(k) for k in ('effective','reason','evidence_request_ids','evidence_incomplete')) and intervals[-1]['to']==start:
        intervals[-1]['to']=end;intervals[-1]['seconds']+=delta
    else:intervals.append(row)

def initial_clock(s,iid,at):
    return {'schema':'pmrs.research-clock/4.2.2','instance_id':iid,'started_at':at,'last_observed_at':at,
        'effective_seconds':0,'last_full_audit_effective_seconds':0,'last_full_audit_id':None,
        'last_full_audit_at':None,'interval_number':1,'last_light_check_at':at,
        'phase':phase(s,iid),'intervals':[],'uncertainty_intervals':[],
        'policy':policy(s,iid),'pending_event_id':None,'deadline_effective_seconds':policy(s,iid)['full_audit_seconds']}

def transition(s,iid,*,at=None):
    """Pure reducer hook after an actual control or execution state change."""
    if s['instances'][iid]['kind'] not in {'TRH','FDH'}:return None
    at=at or now();clock=s.setdefault('research_clocks',{}).get(iid)
    if not clock:return None  # First maintenance reconstructs the immutable journal.
    if seconds(at)<seconds(clock['last_observed_at']):return clock
    elapsed=seconds(at)-seconds(clock['last_observed_at'])
    if elapsed>2*clock['policy']['observation_seconds']:
        clock.setdefault('uncertainty_intervals',[]).append({'from':clock['last_observed_at'],'to':at,'seconds':elapsed,
            'reason':'BACKEND_OBSERVATION_GAP','accounting':'Persisted research phase used; continuous process activity was not observed here.'})
    _append_interval(clock,clock['last_observed_at'],at,clock['phase'])
    clock['last_observed_at']=at;clock['phase']=phase(s,iid);clock['policy']=policy(s,iid)
    clock['deadline_effective_seconds']=clock['last_full_audit_effective_seconds']+clock['policy']['full_audit_seconds']
    return clock

def bootstrap(store,s,iid,at):
    """Recover actual elapsed instance time from immutable journal boundaries."""
    from .store import _apply_delta
    from .util import loads
    head=s['_head'];entries=[]
    while head:
        entry=store._commit_record(head);entries.append(entry);head=entry['previous_commit']
    replay={};clock=None
    for entry in reversed(entries):
        before=phase(replay,iid) if iid in replay.get('instances',{}) else None
        if clock and before:_append_interval(clock,clock['last_observed_at'],entry['at'],before)
        for name in ('knowledge_delta_ref','control_delta_ref','report_delta_ref','registry_delta_ref'):
            if entry[name]:_apply_delta(replay,loads(store.read_blob(entry[name])))
        if iid not in replay.get('instances',{}):continue
        if not clock and replay['instances'][iid].get('current_mission_id'):
            clock=initial_clock(replay,iid,entry['at'])
        if clock:clock['last_observed_at']=entry['at'];clock['phase']=phase(replay,iid)
    clock=clock or initial_clock(s,iid,at)
    _append_interval(clock,clock['last_observed_at'],at,clock['phase'])
    clock['last_observed_at']=at;clock['phase']=phase(s,iid)
    clock['reconstructed_through_commit']=s['knowledge_commit']
    clock['reconstruction_basis']='IMMUTABLE_JOURNAL_REQUEST_AND_CONTROL_INTERVALS'
    # A SENT ledger is evidence of a dispatched request, not uninterrupted CPU
    # use. State that observation boundary rather than silently assuming zero.
    clock['timing_evidence_note']='Elapsed wall time uses native SENT/control transitions, not summed agent work. Unobserved transport or downtime intervals remain explicitly marked.'
    return clock

def observe(store,iid):
    from .strategy import event
    s=store.read_snapshot();instance=s['instances'][iid]
    if instance['kind'] not in {'TRH','FDH'} or not instance.get('current_mission_id'):return None
    at=now();old=s.get('research_clocks',{}).get(iid);new_phase=phase(s,iid)
    if old and new_phase==old['phase'] and seconds(at)-seconds(old['last_observed_at'])<policy(s,iid)['observation_seconds']:
        return deepcopy(old)
    payload={'instance_id':iid,'mission_id':instance['current_mission_id'],'observed_at':at,
        'observed_phase':new_phase}
    if not old:payload['initial_clock']=bootstrap(store,s,iid,at)
    store.commit_strategy(event('AUDIT_CLOCK_OBSERVED',payload))
    return store.read_snapshot()['research_clocks'][iid]

def apply_event(s,e):
    p=e['payload'];iid=p['instance_id'];at=p['observed_at'];clock=s.setdefault('research_clocks',{}).get(iid)
    if not clock:
        clock=deepcopy(p.get('initial_clock') or initial_clock(s,iid,at))
        require(clock['instance_id']==iid and clock['effective_seconds']>=0,'AUDIT_CLOCK_INVALID','Clock must bind this instance')
        s['research_clocks'][iid]=clock
    transition(s,iid,at=at)
    if seconds(at)-seconds(clock['last_light_check_at'])>=clock['policy']['light_check_seconds']:
        eid=identity([iid,'LIGHT',clock['last_light_check_at']],'AUDIT-EVENT-')
        s.setdefault('research_audit_events',{})[eid]={'event_id':eid,'instance_id':iid,'kind':'LIGHT_CONTROL_CHECK',
            'due_at':datetime.fromtimestamp(seconds(clock['last_light_check_at'])+clock['policy']['light_check_seconds'],timezone.utc).isoformat(),
            'observed_at':at,'phase':deepcopy(clock['phase']),'status':'HOST_CHECKED','main_judgment':False,
            'model_calls':0,'delayed_reason':None if clock['phase']['effective'] else clock['phase']['reason']}
        clock['last_light_check_at']=at
    if clock['effective_seconds']>=clock['deadline_effective_seconds']:
        eid=identity([iid,'FULL',clock['interval_number'],clock['last_full_audit_id']],'AUDIT-EVENT-')
        row=s.setdefault('research_audit_events',{}).setdefault(eid,{'event_id':eid,'instance_id':iid,
            'kind':'FULL_STRATEGIC_AUDIT_DUE','interval_number':clock['interval_number'],
            'deadline_effective_seconds':clock['deadline_effective_seconds'],'first_observed_due_at':at,
            'status':'PENDING','main_judgment':False,'covered_by':None})
        if row['status']=='PENDING':
            active=any(s['tasks'][r['task_id']].get('actor_kind')=='MAIN' and r.get('execution_state') in {'PREPARED','RESERVED','SENT','UNKNOWN','CAPTURED'} for r in s['requests'].values() if r['instance_id']==iid)
            row['delayed_reason']='MAIN_ALREADY_ACTIVE' if active else None if clock['phase']['effective'] else clock['phase']['reason']
            clock['pending_event_id']=eid
    return s

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

def context(s,iid,blob_get=None):
    checkpoints=[c for c in s.get('research_checkpoints',{}).values() if c['instance_id']==iid and c['status']=='PUBLISHED']
    checkpoints.sort(key=lambda c:(c['published_sequence'],c['checkpoint_id']))
    latest=deepcopy(checkpoints[-1]) if checkpoints else None
    if latest and blob_get:latest['body']=blob_get(latest['body_ref']).decode('utf-8')
    known=(latest or {}).get('request_versions',{})
    uncovered=set((latest or {}).get('uncovered_incremental_refs',[]))
    increments=[{'request_id':r['request_id'],'task_id':r['task_id'],'state':r['execution_state'],
        'acceptance_state':r['acceptance_state'],'capture_ref':r.get('capture_ref'),
        'record_refs':[v['record_ref'] for v in s.get('production_events',{}).values() if v.get('request_id')==r['request_id']],
        'admission_error':r.get('admission_error')} for r in s.get('requests',{}).values()
        if r.get('instance_id')==iid and (r['request_id'] in uncovered or known.get(r['request_id'])!=identity([r['execution_state'],r['acceptance_state'],r.get('capture_ref')]))]
    invalid=[]
    for ref in (latest or {}).get('evidence_refs',[]):
        source_status=s.get('survey_source_status',{}).get(ref,{})
        if source_status.get('withdrawn') or source_status.get('version_conflict'):invalid.append(ref)
        supports=[v for v in s.get('supports',{}).values() if ref in {v.get('statement_ref'),v.get('argument_ref')}]
        if any(v.get('needs_recheck') or any(w.get('support_id')==v['support_id'] and w.get('active',True) for w in s.get('withdrawals',{}).values()) for v in supports):invalid.append(ref)
    events=[deepcopy(e) for e in s.get('research_audit_events',{}).values() if e['instance_id']==iid and e['status']=='PENDING']
    return {'schema':'pmrs.research-memory/4.2.2','clock':deepcopy(s.get('research_clocks',{}).get(iid)),
        'pending_audit_events':events,'latest_checkpoint':latest,'incremental_requests':increments,
        'invalidated_checkpoint_refs':sorted(set(invalid)),'effective_guidance':effective_guidance(s,iid),
        'as_of_commit':s.get('knowledge_commit'),'authority':'RESEARCH_MEMORY_NOT_MATHEMATICAL_SUPPORT'}

def authoring_schema():
    text={'type':'string'};refs={'type':'array','items':text}
    def obj(properties):return {'type':'object','additionalProperties':False,'properties':properties,'required':list(properties)}
    assessment=obj({'route_key':text,'progress':{'enum':sorted(PROGRESS)},'before_pending':text,'after_pending':text,
        'evidence_refs':refs,'decision':text,'reason':text,'decision_outcome':text,'unassessed':refs})
    failure=obj({'classification':{'enum':['METHOD_FAILURE','STRONGER_CLAIM_FAILURE','ORIGINAL_TARGET_COUNTEREXAMPLE','CONDITIONAL_GAP','SOURCE_UNAVAILABLE','EXECUTION_FAILURE']},
        'route_keys':refs,'attempt_refs':refs,'evidence_refs':refs,'shared_obstacle':text,'changed_basis':text,'next_decision':text})
    return obj({'kind':{'const':'FULL_STRATEGIC_AUDIT'},'body':text,'basis_commit':text,'target_scope_refs':refs,
        'method_version':text,'guidance_version':text,'covered_event_ids':refs,'route_assessments':{'type':'array','items':assessment},
        'failure_synthesis':{'type':'array','items':failure},'known_results':refs,'conditional_results':refs,
        'candidate_refs':refs,'unknown_comparisons':refs,'critical_obstacles':refs,'source_limitations':refs,
        'invalidated_refs':refs,'active_task_ids':refs,'communication_account':text,'next_plan':text,
        'decision_changers':refs,'uncovered_incremental_refs':refs})

def prepare(s,task,audit,*,supplied,known_sources,blobs,live=False,route_keys=(),runtime_contexts=()):
    if audit is None:return None
    require(not live and task.get('actor_kind')=='MAIN','AUDIT_CAPTURE_REQUIRED','A completed audit is published with the original captured MAIN response')
    from .contracts import schema_diagnostics
    require(not schema_diagnostics(audit,authoring_schema()),'AUDIT_INVALID','Complete strategic audit/checkpoint fields are required')
    require(len(audit['body'].strip())>=100 and len(audit['body'].encode())<=256*1024,'AUDIT_INVALID','A full actual MAIN-authored checkpoint body is required')
    actual_bases={task['knowledge_commit']}|{v['as_of_commit'] for v in runtime_contexts}
    require(audit['basis_commit'] in actual_bases,'STALE_AUDIT','Checkpoint must name its exact frozen or actually delivered runtime input snapshot')
    require(audit['method_version']==task.get('method_manual',{}).get('version'),'STALE_AUDIT','Checkpoint method must match the supplied complete manual')
    iid=task['instance_id'];instance=s['instances'][iid]
    scope=[instance['target_ref']] if instance['kind']=='TRH' else list(instance.get('discovery_scope',{}).values())
    if instance['kind']=='FDH':
        from .workflow_instances import validate_discovery_scope
        scope=list(validate_discovery_scope(s,instance).values())
    require(set(audit['target_scope_refs'])==set(scope),'AUDIT_SCOPE_INVALID','Exact original target or complete D0 scope is required')
    frozen=deepcopy(task.get('research_memory_context',{}));delivery_refs=[]
    scientific_baseline=deepcopy(frozen.get('request_versions',{}))
    input_frontier=task.get('strategy_context',{}).get('frontier_digest')
    available_versions={frozen.get('guidance_version')}
    available_events=set(frozen.get('pending_audit_event_ids',[]))
    for received in runtime_contexts:
        guidance=received.get('effective_guidance',{})
        available_versions.add(guidance.get('version'));available_events.update(e['event_id'] for e in received.get('pending_audit_events',[]))
        delivery_refs.append(received['delivery_id'])
        if guidance.get('version')==audit['guidance_version']:
            frozen['guidance_direction_ids']=[d['direction_id'] for d in guidance.get('original_directions',[])]
        if received['as_of_commit']==audit['basis_commit']:
            frozen['request_versions']={r['request_id']:identity([r['execution_state'],r['acceptance_state'],r.get('capture_ref')]) for r in received.get('task_states',[])}
            frozen['known_request_ids']=list(frozen['request_versions'])
            input_frontier=received.get('frontier_digest')
    require(audit['guidance_version'] in available_versions,'STALE_AUDIT','Audit must account for the effective guidance actually supplied')
    require(set(audit['covered_event_ids'])<=available_events,'AUDIT_INVALID','Only frozen or actually delivered audit events may be marked covered')
    assessed={row['route_key'] for row in audit['route_assessments']}
    require(set(route_keys)<=assessed,'AUDIT_INCOMPLETE','A full audit accounts for every known route, including explicit unknown progress and parked routes')
    require(len(assessed)==len(audit['route_assessments']),'AUDIT_INVALID','Route assessment identities must be unique')
    # The frozen schema declares result summaries as strings, not *_refs.
    # Narrative summaries remain MAIN prose and confer no scientific support.
    # Exact native identities in these fields still obey the ordinary read set.
    refs=set(audit['candidate_refs']+audit['invalidated_refs'])
    for value in audit['known_results']+audit['conditional_results']:
        require(value.strip() and len(value.encode())<=24000,'AUDIT_INVALID','Bounded actual result summaries are required')
        if re.fullmatch(r'[A-Z][A-Z0-9_-]*-[0-9a-f]{64}',value):refs.add(value)
    execution_refs={ref for ref in task.get('entry_basis',{}).get('main_execution_recovery_refs',[])
        if s.get('main_execution_recoveries',{}).get(ref,{}).get('instance_id')==iid}
    attempt_refs={ref for collection in ('requests','tasks') for ref,row in s.get(collection,{}).items() if row.get('instance_id')==iid}|set(supplied)
    for row in audit['route_assessments']:refs.update(row['evidence_refs'])
    for row in audit['failure_synthesis']:
        refs.update(row['evidence_refs'])
        require(set(row['attempt_refs'])<=attempt_refs,'AUDIT_INVALID','Failure synthesis cites this instance\'s actual attempts or supplied attempt records')
    require(refs<=set(supplied)|set(known_sources)|execution_refs,'INCOMPLETE_CONTEXT','Audit evidence must be actually supplied or newly authored')
    require(set(audit['active_task_ids'])<=set(s.get('tasks',{})) and all(s['tasks'][tid]['instance_id']==iid for tid in audit['active_task_ids']),
        'AUDIT_INVALID','Task handoff must belong to this MAIN')
    current_guidance=effective_guidance(s,iid)
    new_directions={d['direction_id'] for d in current_guidance['original_directions']}-{d for d in frozen.get('guidance_direction_ids',[])}
    require(new_directions<=set(audit['uncovered_incremental_refs']),'STALE_AUDIT','Explicitly mark newly arrived guidance as an uncovered increment')
    host_uncovered=[]
    for request in s.get('requests',{}).values():
        if request.get('instance_id')!=iid or request['request_id']==task['request_id'] or request.get('execution_state')!='SETTLED':continue
        version=identity([request['execution_state'],request['acceptance_state'],request.get('capture_ref')])
        # Seeing a changed task state through runtime navigation does not mean
        # its mathematical body was read. Preserve that unread increment.
        if scientific_baseline.get(request['request_id'])==version:continue
        produced={p['record_ref'] for p in s.get('production_events',{}).values() if p.get('request_id')==request['request_id']}
        # A new result may have been read through the real dynamic input tools.
        # Otherwise retain a host-observed increment separately from MAIN's
        # unchanged authored account. A late unread completion cannot require
        # MAIN to name an identity it never received or block every checkpoint.
        if not produced or not produced<=set(supplied):
            if request['request_id'] not in audit['uncovered_incremental_refs']:host_uncovered.append(request['request_id'])
    body=audit['body'].encode();body_ref=sha(body);blobs[body_ref]=body
    return {'audit':deepcopy(audit),'body_ref':body_ref,'evidence_refs':sorted(refs),
        'input_request_ids':deepcopy(frozen.get('known_request_ids',[])),
        'request_versions':deepcopy(frozen.get('request_versions',{})),
        'runtime_delivery_refs':delivery_refs,
        'host_uncovered_incremental_refs':sorted(host_uncovered),
        'input_frontier_digest':input_frontier}

def apply_validated(s,task,prepared,proposal_id):
    if not prepared:return
    iid=task['instance_id'];request=s['requests'][task['request_id']]
    require(request.get('capture_ref'),'AUDIT_CAPTURE_REQUIRED','Original MAIN capture is required')
    audit=prepared['audit'];cid=identity([task['request_id'],request['capture_ref'],prepared['body_ref']],'RESEARCH-CHECKPOINT-')
    if cid in s.setdefault('research_checkpoints',{}):return
    at=now();transition(s,iid,at=at)
    row={'schema':'pmrs.research-checkpoint/4.2.2','checkpoint_id':cid,'instance_id':iid,'mission_id':task['mission_id'],
        'body_ref':prepared['body_ref'],'body_sha256':prepared['body_ref'],'author_request_id':task['request_id'],
        'author_capture_ref':request['capture_ref'],'proposal_id':proposal_id,'basis_commit':audit['basis_commit'],
        'method_version':audit['method_version'],'guidance_version':audit['guidance_version'],'target_scope_refs':audit['target_scope_refs'],
        'published_at':at,'published_sequence':s.get('_snapshot_sequence',0)+1,'status':'PUBLISHED',
        'evidence_refs':prepared['evidence_refs'],'known_request_ids':prepared['input_request_ids'],
        'request_versions':prepared['request_versions'],
        'runtime_delivery_refs':prepared.get('runtime_delivery_refs',[]),
        'uncovered_incremental_refs':sorted(set(audit['uncovered_incremental_refs'])|set(prepared.get('host_uncovered_incremental_refs',[]))),
        'main_uncovered_incremental_refs':deepcopy(audit['uncovered_incremental_refs']),
        'host_uncovered_incremental_refs':deepcopy(prepared.get('host_uncovered_incremental_refs',[])),
        'account':{k:deepcopy(v) for k,v in audit.items() if k!='body'}}
    s['research_checkpoints'][cid]=row
    aid=identity(cid,'RESEARCH-AUDIT-')
    s.setdefault('research_audits',{})[aid]={'audit_id':aid,'instance_id':iid,'checkpoint_id':cid,
        'body_ref':prepared['body_ref'],'body_sha256':prepared['body_ref'],'author_request_id':task['request_id'],
        'author_capture_ref':request['capture_ref'],'basis_commit':audit['basis_commit'],'completed_at':at,
        'covered_event_ids':audit['covered_event_ids'],'status':'PUBLISHED','main_judgment':True,
        'uncovered_incremental_refs':deepcopy(row['uncovered_incremental_refs']),
        'host_uncovered_incremental_refs':deepcopy(row['host_uncovered_incremental_refs'])}
    for eid in audit['covered_event_ids']:
        event=s['research_audit_events'][eid];event.update(status='COMPLETED',covered_by=aid,completed_at=at,main_judgment=True)
    for event in s.get('research_audit_events',{}).values():
        if event['instance_id']==iid and event['status']=='PENDING' and event['kind']=='FULL_STRATEGIC_AUDIT_DUE':
            event.update(status='COALESCED_BY_FULL_AUDIT',covered_by=aid,completed_at=at,
                delayed_reason='Full actual strategic audit completed after this reminder was frozen')
    clock=s.get('research_clocks',{}).get(iid)
    if clock:
        clock.update(last_full_audit_id=aid,last_full_audit_at=at,last_full_audit_effective_seconds=clock['effective_seconds'],
            deadline_effective_seconds=clock['effective_seconds']+clock['policy']['full_audit_seconds'],
            interval_number=clock['interval_number']+1,pending_event_id=None)

def view(s,iid):
    return {'clock':deepcopy(s.get('research_clocks',{}).get(iid)),
        'events':[deepcopy(r) for r in s.get('research_audit_events',{}).values() if r['instance_id']==iid],
        'audits':[deepcopy(r) for r in s.get('research_audits',{}).values() if r['instance_id']==iid],
        'checkpoints':[deepcopy(r) for r in s.get('research_checkpoints',{}).values() if r['instance_id']==iid],
        'guidance':effective_guidance(s,iid)}
