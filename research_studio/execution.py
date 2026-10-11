"""One request ledger for research and reports, with capture-before-admission recovery."""
from copy import deepcopy
from .util import identity,require,canonical,PMRSError,immutable,loads,read,sha,now
from . import obligations

EVENT_TYPES={'PREPARE','RESERVE','SENT','UNKNOWN','CAPTURE','SETTLE','VISIT_OPENED','VISIT_DISPOSED',
             'ROUND_ACCOUNTED','NATIVE_RESTORED','ASSIGN_OBLIGATION','COVERAGE_PLAN_REGISTERED','PREPARE_REPAIR',
             'ADD_UNSENT_SOURCES','ADD_UNSENT_INPUTS','REPLAN_UNSENT_MATERIALS','LEGACY_ASSISTANT_RETIRED_UNSENT','ADMISSION_RECHECKED'}
FORMAT_ERRORS=frozenset({'RESPONSE_SCHEMA_INVALID','DUPLICATE_JSON_KEY','UNKNOWN_FIELD'})


def format_diagnostic(snapshot,request_id,raw,blob_get=None):
    """Authorize only a proven representation repair of the original bytes."""
    from .changes import format_repair_evidence
    request=_request(snapshot,request_id)
    require(request['execution_state']=='SETTLED' and request['acceptance_state']=='REJECTED_CONTRACT'
        and request.get('capture_ref')==sha(raw),'REPAIR_NOT_ALLOWED','Exact rejected capture required')
    evidence=format_repair_evidence(snapshot['tasks'][request['task_id']],snapshot,raw,blob_get)
    require(evidence.get('eligible') is True,'REPAIR_NOT_ALLOWED',evidence.get('reason','Scientific preservation could not be established'))
    return {**evidence,'capture_ref':request['capture_ref'],'recorded_error':request.get('admission_error')}


def event(event_type,payload,*,event_id=None):
    payload=deepcopy(payload)
    # Only lifecycle boundaries carry the clock metadata consumed below.
    # Strict business-event payloads retain their exact registered fields.
    if event_type in {'PREPARE','RESERVE','SENT','CAPTURE','UNKNOWN','SETTLE'}:payload.setdefault('issued_at',now())
    e={'actor':'host','capability_ref':'CAP-HOST','event_type':event_type,'payload':payload}
    e['event_id']=event_id or identity(e,'EXEC-EVENT-');return e

def _request(s,rid):
    require(rid in s.get('requests',{}),'REQUEST_UNKNOWN',rid);return s['requests'][rid]



_RECHECK_SETTLEMENT_FIELDS=('execution_state','acceptance_state','receipt_ref','admission_error','admission_diagnostic')

def recheck_context(snapshot,request_id,reason):
    """Bind explicit software-maintenance review to the original rejection."""
    from .changes import validator_identity
    r=_request(snapshot,request_id)
    require(r['execution_state']=='SETTLED' and r['acceptance_state']=='REJECTED_CONTRACT'
            and r.get('capture_ref'),'RECHECK_NOT_ALLOWED','Only the original captured contract rejection permits maintenance recheck.')
    require(isinstance(reason,str) and reason.strip() and len(reason.encode())<=4096,
            'RECHECK_REASON_REQUIRED','Record the software repair that motivates rechecking the original capture.')
    return {'schema':'pmrs.admission-recheck/1','request_id':request_id,'task_id':r['task_id'],
        'execution_id':r['execution_id'],'capture_ref':r['capture_ref'],'reason':reason,
        'previous_settlement':{k:deepcopy(r.get(k)) for k in _RECHECK_SETTLEMENT_FIELDS},
        'validator_identity':validator_identity(),'requested_from_commit':snapshot.get('knowledge_commit')}

def validate_recheck_context(snapshot,context,blob_get):
    from .changes import validator_identity
    expected=recheck_context(snapshot,context['request_id'],context.get('reason'))
    for key in ('schema','request_id','task_id','execution_id','capture_ref','previous_settlement'):
        require(context.get(key)==expected[key],'STALE_RECHECK','Original rejection changed before maintenance recheck could commit.')
    require(context.get('validator_identity')==validator_identity(),'VALIDATOR_CHANGED','Recheck must use the exact recorded current validator.')
    require(sha(blob_get(context['capture_ref']))==context['capture_ref'],'ORIGINAL_BYTES_MISMATCH','Recheck requires untouched original captured bytes.')
    return True

def _unsent_source_binding(snapshot,iid,mid,oid,bid):
    instance=snapshot.get('instances',{}).get(iid,{})
    mission=snapshot.get('missions',{}).get(mid,{})
    require(instance.get('status')=='ACTIVE' and instance.get('current_mission_id')==mid
        and mission.get('instance_id')==iid and mission.get('status')=='ACTIVE',
        'AUTHORIZATION_REQUIRED','Source attachment requires the current active mission')
    obligation=snapshot.get('obligations',{}).get(oid,{})
    definition=obligation.get('definition',{})
    matches=[c for c in definition.get('consumer_bindings',[]) if c.get('binding_id')==bid
        and c.get('instance_id')==iid and c.get('mission_id')==mid]
    require(len(matches)==1,'OBLIGATION_INVALID','Select one exact current consumer binding')
    consumer=matches[0]
    require(definition.get('type') not in {'REPORT','CONTROL'} and not consumer.get('report_context')
        and bid not in snapshot.get('retired_consumers',{}),
        'AUTHORIZATION_REQUIRED','Only an active scientific consumer may receive supplemental sources')
    require(not any(any(b.get('binding_id')==bid for b in task.get('obligation_bindings',[]))
        for task in snapshot.get('tasks',{}).values()),
        'EXISTING_REQUEST','A frozen consumer input cannot be changed, even before its request is sent')
    return definition,consumer


def _source_additions(snapshot,iid,mid,refs):
    require(isinstance(refs,list) and 1<=len(refs)<=256 and all(isinstance(ref,str)
        and ref.startswith('SO-') and len(ref) in {35,67}
        and all(char in '0123456789abcdef' for char in ref[3:]) for ref in refs),
        'UNSENT_SOURCE_INVALID','Select one to 256 exact native source IDs')
    refs=sorted(set(refs));scope=snapshot['missions'][mid]['authorized_scope']
    allowed=set(scope.get('source_refs',[]))|set(scope.get('autoflow',{}).get('source_refs',[]))
    intent=scope.get('autoflow',{}).get('intent_source_ref')
    if intent:allowed.add(intent)
    allowed.update(scope.get('discovery_scope',{}).values())
    allowed.update(ref for o in snapshot.get('obligations',{}).values()
        for c in o['definition']['consumer_bindings'] if c.get('instance_id')==iid and c.get('mission_id')==mid
        for ref in c.get('source_refs',[]))
    allowed.update(item['ref'] for task in snapshot.get('tasks',{}).values()
        if task.get('instance_id')==iid and task.get('mission_id')==mid
        for item in task.get('input_manifest',[]) if item.get('kind')=='source')
    require(all(ref in snapshot.get('sources',{}) for ref in refs),
        'INCOMPLETE_CONTEXT','Supplemental sources must already exist in the native project')
    require(set(refs)<=allowed,'AUTHORIZATION_REQUIRED','Sources must already be authorized in this exact mission')
    require(all(snapshot['sources'][ref].get('access_class')=='SCIENTIFIC_SOURCE' for ref in refs),
        'AUTHORIZATION_REQUIRED','Operator or prior-review materials cannot be added as scientific sources')
    return refs


def add_unsent_sources(store,instance_id,binding_id,source_refs,reason):
    """Add already authorized material before freezing the same exact duty.

    This changes no criterion, role, scope, retry grant, sample or budget. The
    input fingerprint changes normally; sibling frozen consumers stay intact.
    """
    snapshot=store.read_snapshot();mid=snapshot.get('instances',{}).get(instance_id,{}).get('current_mission_id')
    matches=[o for o in snapshot.get('obligations',{}).values() if any(c.get('binding_id')==binding_id
        and c.get('instance_id')==instance_id and c.get('mission_id')==mid for c in o['definition']['consumer_bindings'])]
    require(len(matches)==1,'OBLIGATION_INVALID','Select one exact current consumer binding')
    oid=matches[0]['definition']['obligation_id']
    definition,consumer=_unsent_source_binding(snapshot,instance_id,mid,oid,binding_id)
    refs=_source_additions(snapshot,instance_id,mid,source_refs)
    payload={'instance_id':instance_id,'mission_id':mid,'obligation_id':oid,'binding_id':binding_id,
        'expected_definition_revision':definition['definition_revision'],
        'expected_source_refs':deepcopy(consumer.get('source_refs',[])),'source_refs':refs,'reason':reason}
    result=store.commit_execution(event('ADD_UNSENT_SOURCES',payload))
    return {**result,'instance_id':instance_id,'mission_id':mid,'obligation_id':oid,'binding_id':binding_id,
        'added_source_refs':sorted(set(refs)-set(payload['expected_source_refs'])),
        'source_refs':sorted(set(refs)|set(payload['expected_source_refs'])),'model_calls':0}


def _input_additions(snapshot,iid,mid,definition,consumer,refs):
    """Select existing exact knowledge already authorized in this mission."""
    from .contracts import HASH
    require(isinstance(refs,list) and 1<=len(refs)<=256 and all(isinstance(ref,str)
        and ref.startswith('KR-') and HASH.fullmatch(ref[3:]) for ref in refs),
        'UNSENT_INPUT_INVALID','Select one to 256 exact native knowledge record IDs')
    refs=sorted(set(refs));records=snapshot.get('records',{})
    require(all(ref in records for ref in refs),'INCOMPLETE_CONTEXT','Supplemental knowledge must already exist in the native project')
    scope=snapshot['missions'][mid]['authorized_scope']
    allowed=set(scope.get('target_refs',[]))|set(scope.get('autoflow',{}).get('selected_refs',[]))
    allowed.update(ref for o in snapshot.get('obligations',{}).values()
        for c in o['definition']['consumer_bindings'] if c.get('instance_id')==iid and c.get('mission_id')==mid
        for ref in o['definition'].get('target_refs',[])+c.get('input_refs',[]))
    same_tasks={tid:t for tid,t in snapshot.get('tasks',{}).items() if t.get('instance_id')==iid and t.get('mission_id')==mid}
    allowed.update(item['ref'] for task in same_tasks.values() for item in task.get('input_manifest',[]) if item.get('kind')=='record')
    allowed.update(p['record_ref'] for p in snapshot.get('production_events',{}).values()
        if p.get('task_id') in same_tasks and snapshot.get('requests',{}).get(p.get('request_id'),{}).get('acceptance_state') in {'ACCEPTED','EXACT_DUPLICATE'})
    require(set(refs)<=allowed,'AUTHORIZATION_REQUIRED','Knowledge inputs must already be authorized, read or produced in this exact mission')
    from .workflows.registry import INDEPENDENT
    basis=consumer.get('entry_basis',{})
    isolated=consumer.get('stage_id')=='P7' and consumer.get('role') in {'LEARN','DIRECT'} and bool(basis.get('research_plan') or basis.get('analysis_route')=='COMPARATIVE')
    if consumer.get('role') in INDEPENDENT or isolated:
        from .context import _source_tainted
        from .relations import premise_closure
        ancestry=premise_closure(refs,snapshot)
        require(all(records.get(ref,{}).get('kind')!='Assessment' and not _source_tainted(ref,snapshot) for ref in ancestry),
            'FORBIDDEN_REVIEW_DERIVATIVE','Independent inputs cannot contain prior review or preparation evidence')
        if isolated and basis.get('research_plan'):
            plan_id=basis['research_plan'].get('plan_id');dependencies={d.get('binding_ref') for d in definition.get('dependency_bindings',[])}
            siblings={tid for tid,t in same_tasks.items() if t.get('entry_basis',{}).get('research_plan',{}).get('plan_id')==plan_id
                and not any(b.get('binding_id')==consumer['binding_id'] or b.get('obligation_id') in dependencies for b in t.get('obligation_bindings',[]))}
            for ref in ancestry:
                producers=[p for p in snapshot.get('production_events',{}).values() if p.get('record_ref')==ref]
                require(not producers or not all(p.get('task_id') in siblings for p in producers),
                    'FORBIDDEN_REVIEW_DERIVATIVE','An isolated branch cannot import an unmerged sibling result')
    return refs


def add_unsent_inputs(store,instance_id,binding_id,input_refs,reason):
    """Supplement this same unfrozen duty with its existing mathematical basis.

    Exact criterion, scope, role, grants, sample and model are unchanged. Only
    the input selection/fingerprint changes before any request is frozen.
    """
    snapshot=store.read_snapshot();mid=snapshot.get('instances',{}).get(instance_id,{}).get('current_mission_id')
    matches=[o for o in snapshot.get('obligations',{}).values() if any(c.get('binding_id')==binding_id
        and c.get('instance_id')==instance_id and c.get('mission_id')==mid for c in o['definition']['consumer_bindings'])]
    require(len(matches)==1,'OBLIGATION_INVALID','Select one exact current consumer binding')
    oid=matches[0]['definition']['obligation_id']
    definition,consumer=_unsent_source_binding(snapshot,instance_id,mid,oid,binding_id)
    refs=_input_additions(snapshot,instance_id,mid,definition,consumer,input_refs)
    payload={'instance_id':instance_id,'mission_id':mid,'obligation_id':oid,'binding_id':binding_id,
        'expected_definition_revision':definition['definition_revision'],
        'expected_input_refs':deepcopy(consumer.get('input_refs',[])),'input_refs':refs,'reason':reason}
    result=store.commit_execution(event('ADD_UNSENT_INPUTS',payload))
    return {**result,'instance_id':instance_id,'mission_id':mid,'obligation_id':oid,'binding_id':binding_id,
        'added_input_refs':sorted(set(refs)-set(payload['expected_input_refs'])),
        'input_refs':sorted(set(refs)|set(payload['expected_input_refs'])),'model_calls':0}

def replan_unsent_materials(store,instance_id,binding_id,source_selections,reason):
    """Change only explicit source coverage on the original unfrozen duty."""
    snapshot=store.read_snapshot();mid=snapshot.get('instances',{}).get(instance_id,{}).get('current_mission_id')
    matches=[o for o in snapshot.get('obligations',{}).values() if any(c.get('binding_id')==binding_id
        and c.get('instance_id')==instance_id and c.get('mission_id')==mid for c in o['definition']['consumer_bindings'])]
    require(len(matches)==1,'OBLIGATION_INVALID','Select one exact current consumer binding')
    oid=matches[0]['definition']['obligation_id']
    definition,consumer=_unsent_source_binding(snapshot,instance_id,mid,oid,binding_id)
    payload={'instance_id':instance_id,'mission_id':mid,'obligation_id':oid,'binding_id':binding_id,
        'expected_definition_revision':definition['definition_revision'],
        'expected_source_selections':deepcopy(consumer.get('source_selections',{})),
        'source_selections':deepcopy(source_selections),'reason':reason}
    result=store.commit_execution(event('REPLAN_UNSENT_MATERIALS',payload))
    return {**result,'binding_id':binding_id,'model_calls':0,'source_selections':deepcopy(source_selections)}

def apply_event(snapshot,e,blob_get=None,*,historical=False):
    old=snapshot.get('execution_events',{}).get(e.get('event_id'))
    if old:
        require(old==e,'ALREADY_SETTLED_CONTENT_CONFLICT','Execution event identity conflict');return deepcopy(snapshot)
    require(set(e)=={'event_id','actor','capability_ref','event_type','payload'} and e['event_type'] in EVENT_TYPES,
            'EXECUTION_EVENT_INVALID','Typed execution event required')
    cap=snapshot.get('capabilities',{}).get(e['capability_ref'],{})
    require(e['actor']=='host' and cap.get('actor')=='host','AUTHORIZATION_REQUIRED','Execution requires host capability')
    s=deepcopy(snapshot);p=e['payload'];kind=e['event_type']
    if kind=='PREPARE':
        from .scheduler import budget_remaining,project_remaining,aggregate_project_remaining
        from .workflows.registry import validate_assignment
        task=deepcopy(p['task']);candidate=p['candidate'];c=candidate['consumer']
        from .scheduler import validate_consumer_control
        validate_consumer_control(s,c)
        from .workflow_instances import validate_discovery_scope
        discovery_scope=validate_discovery_scope(s,s['instances'][c['instance_id']])
        if discovery_scope:require(task.get('discovery_scope')==discovery_scope,'DISCOVERY_SCOPE_INVALID','Frozen task must bind the exact authorized discovery scope')
        require(task['request_id'] not in s.get('requests',{}) and task['task_id'] not in s.get('tasks',{}),'EXISTING_REQUEST','Reuse the frozen request')
        o=s['obligations'][candidate['obligation_id']]
        require(o['definition']['definition_revision']==candidate['definition_revision'],'STALE_OBLIGATION_DEFINITION','Scientific responsibility changed')
        assigned=[b for b in o['definition']['consumer_bindings'] if b['binding_id']==c['binding_id']]
        require(len(assigned)==1 and {k:v for k,v in assigned[0].items() if k!='visit_id'}=={k:v for k,v in c.items() if k!='visit_id'},
                'AUTHORIZATION_REQUIRED','Dispatch must use the exact authorized consumer binding')
        current=obligations.eligible(s,o,c,c['role'],method_ref=c.get('method_ref'))
        require(current['state']=='READY',current['code'],'Request is no longer eligible')
        for k in ('purpose_key','responsibility_key','attempt_group_key','input_fingerprint'):
            require(task[k]==candidate[k]==current[k],'STALE_READ','Related research inputs changed')
        assignment=validate_assignment(c['stage_id'],o['definition']['type'],c['role'],c.get('entry_basis',{}))
        require(task['stage_spec_digest']==assignment['stage_spec_digest'],'STAGE_SPEC_CHANGED','Activity contract changed')
        require((task.get('budget_domain','SCIENCE')!='SCIENCE' or project_remaining(s)>=1) and aggregate_project_remaining(s)>=1
                and budget_remaining(s,candidate['budget_grant_id'])>=1,'BUDGET_EXHAUSTED','All unresolved reservations count against the applicable budget')
        existing=[r['sample_slot'] for r in s.get('requests',{}).values() if r['attempt_group_key']==task['attempt_group_key']]
        require(task['sample_slot']==max(existing,default=0)+1,'WRITE_CAS_CONFLICT','Host sample slot was concurrently allocated')
        require(task['context_budget']['input_tokens']+task['context_budget']['prompt_overhead_tokens']+task['context_budget']['reserved_output_tokens']+task['context_budget']['safety_margin_tokens']<=task['context_budget']['context_window_tokens'],
                'CONTEXT_LIMIT','Frozen request exceeds model capacity')
        s.setdefault('tasks',{})[task['task_id']]=task
        request={k:task[k] for k in ('request_id','task_id','instance_id','mission_id','purpose_key','responsibility_key','attempt_group_key','attempt_key','sample_slot','input_fingerprint')}
        request.update(execution_state='PREPARED',acceptance_state='NOT_SUBMITTED',execution_kind=None,
                       execution_id=identity({'request':task['request_id']},'EXECUTION-'),budget_grant_id=candidate['budget_grant_id'],
                       reserved_calls=1,capture_ref=None,usage=None,fenced=False,receipt_ref=None)
        if task.get('budget_domain'):request['budget_domain']=task['budget_domain']
        s.setdefault('requests',{})[request['request_id']]=request
        from .strategy import request_prepared
        request_prepared(s,task)
        grant=s['retry_grants'][c['retry_grant_id']]
        grant['remaining_uses']=current['remaining_uses']-1
        ledger=s.setdefault('attempt_groups',{}).setdefault(task['attempt_group_key'],{'request_ids':[],'highest_sample_slot':0})
        ledger['request_ids'].append(request['request_id']);ledger['highest_sample_slot']=task['sample_slot']
        scheduler_state=s.setdefault('scheduler_state',{})
        scheduler_state.setdefault('last_instance_by_tier',{})[str(candidate['priority'])]=task['instance_id']
        from .scheduler import ordinary_preparations_since_account
        scheduler_state['ordinary_preparations_since_account']=0 if o['definition']['type'] in {'REPORT','ACCOUNT'} else min(8,ordinary_preparations_since_account(snapshot)+1)
    elif kind=='PREPARE_REPAIR':
        from .scheduler import budget_remaining,project_remaining,aggregate_project_remaining
        require(set(p) in ({'original_request_id','repair_kind','task'}, {'original_request_id','repair_kind','task','format_proof'}),
            'EXECUTION_EVENT_INVALID','Typed finite repair request required')
        original=_request(s,p['original_request_id']);origin=original.get('repair_of',original['request_id']);root=_request(s,origin)
        frozen=s['tasks'][root['task_id']];task=deepcopy(p['task']);repair_kind=p['repair_kind']
        require(repair_kind in {'FORMAT','TRANSPORT'} and task.get('repair_of')==origin and task.get('repair_kind')==repair_kind,
            'REPAIR_NOT_ALLOWED','Repair must preserve its original scientific attempt')
        count=sum(r.get('repair_of')==origin and r.get('repair_kind')==repair_kind for r in s['requests'].values())
        limit=frozen.get('repair_limits',{}).get(repair_kind,0)
        require(type(limit) is int and 0<=limit<=3 and count<limit and task['repair_index']==count+1,'REPAIR_LIMIT','Frozen finite repair allowance exhausted')
        if repair_kind=='TRANSPORT':require(original['execution_state']=='CANCELLED_BEFORE_SEND','REPAIR_NOT_ALLOWED','UNKNOWN or sent requests cannot be retried as transport repairs')
        else:
            require(original['execution_state']=='SETTLED' and original['acceptance_state']=='REJECTED_CONTRACT',
                'REPAIR_NOT_ALLOWED','Only a recorded format rejection permits a format repair')
            proof=p.get('format_proof')
            if proof:
                verify_format_proof(s,p['original_request_id'],proof,blob_get,historical=historical)
            else:
                require(historical and frozen.get('response_contract_revision') is None and original.get('admission_error') in FORMAT_ERRORS,
                    'REPAIR_NOT_ALLOWED','A new FORMAT request requires a complete capture-bound proof, including for structural first errors')
        allowed={'task_id','request_id','input_packet_ref','model_packet_ref','prompt_ref','context_budget','context_budget_details','repair_of','repair_kind','repair_index'}
        comparable_task=deepcopy(task);comparable_frozen=deepcopy(frozen)
        for comparable in (comparable_task,comparable_frozen):
            # Native task IDs have the same fixed length. Only the expected
            # path digest changes; measured profile, bound and derivation stay.
            comparable.get('executor_contract',{}).get('client_input_evidence',{}).pop('expected_work_path_sha256',None)
        require({k:v for k,v in comparable_task.items() if k not in allowed}=={k:v for k,v in comparable_frozen.items() if k not in allowed},
            'EXECUTOR_CONTRACT_CHANGED','Repair cannot change science scope, sample, model, executor or permissions')
        require(task['task_id'] not in s['tasks'] and task['request_id'] not in s['requests'],'EXISTING_REQUEST','Reuse registered repair request')
        from .reports import dispatch_authorized,dispatch_current
        report_authorized=bool(frozen.get('report_context')) and dispatch_authorized(s,frozen)
        if frozen.get('report_context'):dispatch_current(s,frozen['report_context'])
        require((report_authorized or s['instances'][root['instance_id']]['status']=='ACTIVE')
            and (root.get('budget_domain','SCIENCE')!='SCIENCE' or project_remaining(s)>=1)
            and aggregate_project_remaining(s)>=1 and budget_remaining(s,root['budget_grant_id'])>=1,
            'BUDGET_EXHAUSTED','Repairs consume the original finite budget domain and grant')
        from .context import validate_budget
        validate_budget(task['context_budget']);s['tasks'][task['task_id']]=task
        r={k:root[k] for k in ('instance_id','mission_id','purpose_key','responsibility_key','attempt_group_key','attempt_key','sample_slot','input_fingerprint','budget_grant_id')}
        r.update(request_id=task['request_id'],task_id=task['task_id'],execution_id=identity(task['request_id'],'EXECUTION-'),execution_state='PREPARED',
            acceptance_state='NOT_SUBMITTED',execution_kind=None,reserved_calls=1,capture_ref=None,usage=None,fenced=False,receipt_ref=None,
            repair_of=origin,repair_kind=repair_kind,repair_index=count+1)
        if root.get('budget_domain'):r['budget_domain']=root['budget_domain']
        s['requests'][r['request_id']]=r
    elif kind=='RESERVE':
        r=_request(s,p['request_id']);task=s['tasks'][r['task_id']]
        assistant_task=task.get('purpose')=='PROJECT_ASSISTANT'
        require(not assistant_task,'PROJECT_ASSISTANT_REMOVED','Unsent legacy assistant tasks cannot dispatch in 4.2.2; retain original sent/captured history')
        report_authorized=False
        if assistant_task:
            from .assistant import validate_dispatch
            validate_dispatch(s,task)
        if task.get('report_context'):
            from .reports import dispatch_current,dispatch_authorized
            dispatch_current(s,task['report_context'])
            report_authorized=dispatch_authorized(s,task)
        require(r['execution_state']=='PREPARED' and not r['fenced'],'EXISTING_REQUEST','A sent, uncertain or captured request cannot be resent')
        require(assistant_task or report_authorized or s['instances'][r['instance_id']]['status']=='ACTIVE','TASK_FENCED','Workflow is paused')
        require(assistant_task or task.get('report_context') or s['instances'][r['instance_id']]['current_mission_id']==r['mission_id'],
                'TASK_FENCED','A superseded research mission cannot send an old unstarted request; original captures remain recoverable.')
        from .host_pool import is_stage,instance_limit
        from .scheduler import validate_task_control
        validate_task_control(s,task)
        stage=is_stage(s,r)
        active=sum(is_stage(s,x)==stage and x['instance_id']==r['instance_id'] and x['execution_state'] in {'RESERVED','SENT','UNKNOWN'} for x in s.get('requests',{}).values())
        require(active<(instance_limit(s,r['instance_id']) if stage else 1),'BUDGET_OR_WORKER_LIMIT','Uncertain requests retain the original instance lane reservation')
        require(p['executor_contract']==task['executor_contract'] and p['model_policy']==task['model_policy'],
                'EXECUTOR_CONTRACT_CHANGED','No silent executor, permission, model, effort or tier change')
        from .changes import live_check
        if not assistant_task:live_check(task,s)
        require(p['execution_kind'] in {'MODEL','SYNTHETIC_TEST_ONLY'},'EXECUTION_EVENT_INVALID','Unknown execution provenance')
        if p['execution_kind']=='SYNTHETIC_TEST_ONLY':require(s.get('synthetic_test_only') is True,'SYNTHETIC_PROJECT_REQUIRED','Fake output cannot qualify real research')
        r.update(execution_state='RESERVED',execution_kind=p['execution_kind'])
    elif kind in {'SENT','UNKNOWN'}:
        r=_request(s,p['request_id']);require(r['execution_state'] in {'RESERVED','SENT'},'EXECUTION_TRANSITION_INVALID','No active send boundary')
        require(p.get('execution_id')==r['execution_id'],'EXECUTION_IDENTITY','Original request execution required')
        r['execution_state']=kind
        if kind=='SENT':
            from .strategy import request_sent
            request_sent(s,s['tasks'][r['task_id']])
        if kind=='UNKNOWN':r['uncertainty_reason']=p.get('reason','Transport result unknown')
    elif kind=='CAPTURE':
        r=_request(s,p['request_id']);task=s['tasks'][r['task_id']]
        require(p.get('execution_id')==r['execution_id'],'EXECUTION_IDENTITY','Capture must bind the original execution')
        if r['capture_ref']:
            require(r['capture_ref']==p['capture_ref'],'ALREADY_SETTLED_CONTENT_CONFLICT','Do not overwrite original captured bytes')
        else:
            require(r['execution_state'] in {'RESERVED','SENT','UNKNOWN'},'EXECUTION_TRANSITION_INVALID','Capture requires the original request')
            r.update(capture_ref=p['capture_ref'],execution_state='CAPTURED',acceptance_state='PENDING',usage=deepcopy(p.get('usage') if p.get('usage') is not None else r.get('usage')))
            if task.get('communication_contract'):
                from .input_delivery import capture_binding
                binding=capture_binding(s,r['request_id'])
                require(all(p.get(k)==binding[k] for k in ('delivery_manifest_hash','input_window_seal','delivery_cutoff')),'INPUT_DELIVERY_INVALID','Capture must bind the sealed actual input window')
                r.update({k:binding[k] for k in ('delivery_manifest_hash','input_window_seal','delivery_cutoff')})
            if task.get('independent'):
                evidence={'event_id':r['execution_id'],'task_id':task['task_id'],'role':task['role'],
                          'input_manifest_hash':task['input_manifest_hash'],
                          'target_revision_hashes':{item['ref']:identity(s['records'][item['ref']]) for item in task['input_manifest'] if item['kind']=='record'},
                          'independent':True,'author_execution_event':task.get('author_execution_event'),
                          'excluded_verdicts':task.get('excluded_verdicts') is True,
                          'synthetic':r['execution_kind']=='SYNTHETIC_TEST_ONLY','integrity_valid':True,
                          'policy_digest':task.get('policy_digest'),'capture_ref':p['capture_ref']}
                s.setdefault('review_executions',{})[r['execution_id']]=evidence
    elif kind=='SETTLE':
        r=_request(s,p['request_id'])
        require(r['execution_state'] in {'CAPTURED','SETTLED'},'EXECUTION_TRANSITION_INVALID','Capture must precede settlement')
        require(p.get('acceptance_state') in {'ACCEPTED','REJECTED_STALE','REJECTED_CONTRACT','EXACT_DUPLICATE'},'EXECUTION_EVENT_INVALID','Exact admission disposition required')
        if r['execution_state']=='SETTLED':require(r['receipt_ref']==p.get('receipt_ref'),'ALREADY_SETTLED_CONTENT_CONFLICT','Original settlement required')
        else:
            r.update(execution_state='SETTLED',acceptance_state=p['acceptance_state'],receipt_ref=p.get('receipt_ref'),admission_error=p.get('error'))
            if p.get('diagnostic'):r['admission_diagnostic']=deepcopy(p['diagnostic'])
    elif kind=='ADMISSION_RECHECKED':
        r=_request(s,p['request_id'])
        require(p.get('schema')=='pmrs.admission-recheck/1' and p.get('task_id')==r['task_id'] and p.get('execution_id')==r['execution_id']
                and p.get('capture_ref')==r.get('capture_ref') and sha(blob_get(r['capture_ref']))==r['capture_ref'],
                'ORIGINAL_BYTES_MISMATCH','Maintenance recheck must preserve the original request, task, execution and capture.')
        require(p.get('reason') and p.get('validator_identity',{}).get('modules') and
                p.get('previous_settlement',{}).get('acceptance_state')=='REJECTED_CONTRACT',
                'RECHECK_NOT_ALLOWED','Explicit repair reason, validator identity and original rejection are required.')
        if p['outcome']=='ACCEPTED':
            accepted=s.get('accepted_requests',{}).get(r['request_id'],{})
            require(r['acceptance_state']=='ACCEPTED' and r['execution_state']=='SETTLED' and
                    accepted.get('capture_hash')==r['capture_ref'] and p.get('receipt_ref')==r.get('receipt_ref'),
                    'RECHECK_NOT_ALLOWED','A recheck event cannot accept science; full scientific admission must already have committed in this transaction.')
            r['admission_error_resolved_by']=e['event_id']
        else:
            require(p['outcome']=='REJECTED_CONTRACT' and r['execution_state']=='SETTLED' and r['acceptance_state']=='REJECTED_CONTRACT'
                and {k:deepcopy(r.get(k)) for k in _RECHECK_SETTLEMENT_FIELDS}==p['previous_settlement'] and p.get('diagnostic'),
                'STALE_RECHECK','Failed maintenance review preserves its exact original rejection.')
        r.setdefault('admission_rechecks',[]).append({'event_id':e['event_id'],**deepcopy(p)})
    elif kind=='VISIT_OPENED':
        from .workflows.registry import spec,validate_assignment
        visit=deepcopy(p['visit']);iid=visit['instance_id'];mission=s['missions'][visit['mission_id']]
        from .reports import dispatch_authorized
        report_visit=bool(visit['assigned_obligation_bindings']) and all(any(c.get('binding_id')==b['binding_id'] and c.get('report_context') and dispatch_authorized(s,c)
            for c in s['obligations'][b['obligation_id']]['definition']['consumer_bindings']) for b in visit['assigned_obligation_bindings'])
        require((s['instances'][iid]['status']=='ACTIVE' or report_visit) and mission['instance_id']==iid,'AUTHORIZATION_REQUIRED','Active authorized mission or exact report authorization required')
        contract=spec(visit['stage_id'])
        require(contract['workflow_kind']==s['instances'][iid]['kind'] and contract['digest']==visit['stage_spec_digest'],
                'STAGE_SPEC_CHANGED','Workflow activity mismatch')
        require(visit['assigned_obligation_bindings'],'OBLIGATION_REQUIRED','A stage visit is not generic work')
        for b in visit['assigned_obligation_bindings']:
            d=s['obligations'][b['obligation_id']]['definition']
            require(d['definition_revision']==b['expected_definition_revision'],'STALE_OBLIGATION_DEFINITION','Exact definition revision required')
            consumers=[c for c in d['consumer_bindings'] if c['binding_id']==b['binding_id'] and c['instance_id']==iid and c['mission_id']==visit['mission_id']]
            require(len(consumers)==1 and consumers[0]['stage_id']==visit['stage_id'],'AUTHORIZATION_REQUIRED','Visit must be driven by the assigned responsibility')
            validate_assignment(visit['stage_id'],d['type'],consumers[0]['role'],visit['entry_basis'])
        require(visit['visit_id'] not in s.get('visits',{}),'VISIT_EXISTS','Visits are immutable')
        visit.update(outcome=None,exit_evidence=[],unperformed_duties=[])
        s.setdefault('visits',{})[visit['visit_id']]=visit;mission['stage_visit_ids'].append(visit['visit_id'])
    elif kind=='VISIT_DISPOSED':
        from .workflows.registry import validate_exit
        visit=s['visits'][p['disposition']['visit_id']];disposition=validate_exit(visit,p['disposition'])
        require(visit['outcome'] is None,'VISIT_ALREADY_DISPOSED','Do not rewrite performed history')
        if visit['stage_id']=='P6' and disposition['outcome']=='FULFILLED_FOR_SCOPE' and visit['assigned_obligation_bindings']:
            for binding in visit['assigned_obligation_bindings']:
                records=s['obligations'][binding['obligation_id']]['projection'].get('evidence_refs',[])
                require(any(s['records'].get(ref,{}).get('kind')=='Argument' and s['records'][ref]['data'].get('mode')=='REDUCTION' for ref in records),
                    'STAGE_PRODUCT_MISSING','An assigned P6 reduction cannot be fulfilled by a gap or a completed task')
        visit.update(outcome=disposition['outcome'],exit_evidence=deepcopy(disposition),unperformed_duties=disposition['unperformed_bindings'])
    elif kind=='ROUND_ACCOUNTED':
        from .rounds import apply
        apply(s,p)
    elif kind=='LEGACY_ASSISTANT_RETIRED_UNSENT':
        require(set(p)=={'request_id','reason'},'EXECUTION_EVENT_INVALID','Exact legacy compatibility disposition required')
        r=_request(s,p['request_id']);task=s['tasks'][r['task_id']]
        require(task.get('purpose')=='PROJECT_ASSISTANT' and r['execution_state']=='PREPARED' and not r.get('capture_ref'),
            'EXISTING_REQUEST','Only an original never-sent legacy assistant may be retired')
        r.update(execution_state='CANCELLED_BEFORE_SEND',fenced=True,compatibility_disposition='RETIRED_LEGACY_ASSISTANT',
            compatibility_reason=p['reason'])
    elif kind=='NATIVE_RESTORED':
        require(set(p)=={'backup_identity'} and p['backup_identity'],'EXECUTION_EVENT_INVALID','Exact backup identity required')
        for instance in s.get('instances',{}).values():
            if instance['status']!='ENDED':instance['status']='PAUSED'
        for r in s.get('requests',{}).values():
            if r['execution_state'] in {'RESERVED','SENT'}:
                r['execution_state']='UNKNOWN';r['uncertainty_reason']='Restored backup does not restore a remote process.'
    elif kind=='COVERAGE_PLAN_REGISTERED':
        from .context import validate_coverage_plan
        require(set(p)=={'instance_id','mission_id','plan','requirement','support_id'},'EXECUTION_EVENT_INVALID','Typed coverage registration required')
        iid=p['instance_id'];mission=s['missions'].get(p['mission_id'],{});scope=mission.get('authorized_scope',{})
        require(mission.get('instance_id')==iid and s['instances'][iid]['status']=='ACTIVE' and scope.get('allow_derived_work'),
            'AUTHORIZATION_REQUIRED','Coverage consumes an existing active bounded mission')
        validate_coverage_plan(p['plan'],p['requirement']);support=s['supports'].get(p['support_id'])
        require(support and support['statement_ref'] in ({s['instances'][iid].get('target_ref')}|set(scope.get('target_refs',[]))),
            'AUTHORIZATION_REQUIRED','Coverage support outside authorized target')
        pid=p['plan']['plan_id'];require(pid not in s.get('coverage_plans',{}),'EXISTING_REQUEST','Coverage plan is immutable')
        s.setdefault('coverage_plans',{})[pid]=deepcopy(p)
    elif kind=='ADD_UNSENT_SOURCES':
        require(isinstance(p,dict) and set(p)=={'instance_id','mission_id','obligation_id','binding_id',
            'expected_definition_revision','expected_source_refs','source_refs','reason'},
            'EXECUTION_EVENT_INVALID','Exact bounded unsent source attachment required')
        require(isinstance(p['reason'],str) and 0<len(p['reason'].strip())<=12000,
            'UNSENT_SOURCE_INVALID','Preserve the concrete reason for attaching sources')
        definition,consumer=_unsent_source_binding(s,p['instance_id'],p['mission_id'],p['obligation_id'],p['binding_id'])
        require(type(p['expected_definition_revision']) is int
            and p['expected_definition_revision']==definition['definition_revision'],
            'STALE_OBLIGATION_DEFINITION','The scientific duty definition changed')
        refs=_source_additions(s,p['instance_id'],p['mission_id'],p['source_refs'])
        require(refs==p['source_refs'],'UNSENT_SOURCE_INVALID','Native source additions must be sorted and distinct')
        current=consumer.get('source_refs',[])
        if set(refs)<=set(current):return deepcopy(snapshot)
        require(p['expected_source_refs']==current,'STALE_READ','The selected source binding changed')
        # Material selection has its own compare-and-swap and input fingerprint.
        # Preserve the scientific definition revision and every sibling binding.
        consumer['source_refs']=sorted(set(current)|set(refs))
    elif kind=='ADD_UNSENT_INPUTS':
        require(isinstance(p,dict) and set(p)=={'instance_id','mission_id','obligation_id','binding_id',
            'expected_definition_revision','expected_input_refs','input_refs','reason'},
            'EXECUTION_EVENT_INVALID','Exact bounded unsent knowledge attachment required')
        require(isinstance(p['reason'],str) and 0<len(p['reason'].strip())<=12000,
            'UNSENT_INPUT_INVALID','Preserve the mathematical reason for attaching existing knowledge')
        definition,consumer=_unsent_source_binding(s,p['instance_id'],p['mission_id'],p['obligation_id'],p['binding_id'])
        require(type(p['expected_definition_revision']) is int and p['expected_definition_revision']==definition['definition_revision'],
            'STALE_OBLIGATION_DEFINITION','The scientific duty definition changed')
        refs=_input_additions(s,p['instance_id'],p['mission_id'],definition,consumer,p['input_refs'])
        require(refs==p['input_refs'],'UNSENT_INPUT_INVALID','Native knowledge additions must be sorted and distinct')
        current=consumer.get('input_refs',[])
        if set(refs)<=set(current):return deepcopy(snapshot)
        require(p['expected_input_refs']==current,'STALE_READ','The exact selected knowledge binding changed')
        consumer['input_refs']=sorted(set(current)|set(refs))
    elif kind=='REPLAN_UNSENT_MATERIALS':
        require(isinstance(p,dict) and set(p)=={'instance_id','mission_id','obligation_id','binding_id',
            'expected_definition_revision','expected_source_selections','source_selections','reason'},
            'EXECUTION_EVENT_INVALID','Exact bounded unsent material replan required')
        require(isinstance(p['reason'],str) and 0<len(p['reason'].strip())<=12000,
            'INPUT_PLAN_INVALID','Preserve the scientific reason for the changed source coverage')
        definition,consumer=_unsent_source_binding(s,p['instance_id'],p['mission_id'],p['obligation_id'],p['binding_id'])
        require(p['expected_definition_revision']==definition['definition_revision'],
            'STALE_OBLIGATION_DEFINITION','The scientific duty definition changed')
        current=consumer.get('source_selections',{})
        if current==p['source_selections']:return deepcopy(snapshot)
        require(p['expected_source_selections']==current,'STALE_READ','Source coverage changed before replan')
        require(isinstance(p['source_selections'],dict) and len(p['source_selections'])<=256,
            'INPUT_PLAN_INVALID','Source coverage must be a bounded exact source mapping')
        candidate=deepcopy(consumer);candidate['source_selections']=deepcopy(p['source_selections'])
        from .input_plans import build
        plan=build(s,s['obligations'][p['obligation_id']],candidate,blob_get=blob_get)
        consumer['source_selections']=deepcopy(p['source_selections']);consumer['input_plan']=plan
    elif kind=='ASSIGN_OBLIGATION':
        from .workflows.registry import validate_assignment
        from .contracts import HASH
        require(set(p)=={'instance_id','mission_id','obligation','retry_grant','authorization_basis_ref'},
                'EXECUTION_EVENT_INVALID','Exact bounded host assignment required')
        iid=p['instance_id'];mission=s.get('missions',{}).get(p['mission_id'],{})
        proposed=p['obligation'];d=proposed['definition'];oid=d['obligation_id'];scope=mission['authorized_scope']
        from .reports import dispatch_authorized
        report_assignment=d['type']=='REPORT' and bool(d['consumer_bindings']) and all(c.get('report_context') and dispatch_authorized(s,c) for c in d['consumer_bindings'])
        require(mission.get('instance_id')==iid and ((mission.get('status')=='ACTIVE' and s['instances'][iid]['status']=='ACTIVE') or report_assignment),
                'AUTHORIZATION_REQUIRED','Host assignment requires an active mission or exact independent report authorization')
        old_obligation=s.get('obligations',{}).get(oid)
        require(HASH.fullmatch(str(d['criterion_body_ref'])) and p['authorization_basis_ref'],
                'OBLIGATION_INVALID','Host assignment requires a concrete persistent criterion and basis')
        allowed=set(scope.get('target_refs',[]))|({s['instances'][iid]['target_ref']} if s['instances'][iid]['target_ref'] else set())
        allowed.update(c['statement_ref'] for c in s.get('candidates',{}).values() if c['instance_id']==iid)
        if scope.get('allow_derived_work'):
            allowed.update(p['record_ref'] for p in s.get('production_events',{}).values()
                if p.get('workflow_instance_id')==iid and s.get('tasks',{}).get(p.get('task_id'),{}).get('mission_id')==mission['mission_id'])
        require(set(d['target_refs'])<=allowed and all(ref in s['records'] for ref in d['target_refs']),
                'AUTHORIZATION_REQUIRED','Assigned responsibility is outside the existing mission target scope')
        if d['type']=='REPORT':require(report_assignment or scope.get('reports') is True or 'REPORT' in scope.get('obligation_types',[]),
                                      'AUTHORIZATION_REQUIRED','Formal reporting must be requested within the mission budget')
        else:
            from .corrections import is_exact_authorization
            require(scope.get('allow_derived_work') is True or is_exact_authorization(s,p),'AUTHORIZATION_REQUIRED','Mission has no authority to add derived research work')
        expected=obligations.make(oid,d['type'],d['target_refs'],d['criterion_body_ref'],consumer_bindings=d['consumer_bindings'],
            dependencies=d['dependency_bindings'],scope_context_refs=d['scope_context_refs'],effect=d['effect_on_goal'],
            created_by=d['created_by'],reason_code=d['reason_code'],alias_of=d['alias_of'])
        if old_obligation:
            old_d=old_obligation['definition'];new_bindings=d['consumer_bindings'][len(old_d['consumer_bindings']):]
            require({k:v for k,v in d.items() if k not in {'consumer_bindings','definition_revision'}}==
                    {k:v for k,v in old_d.items() if k not in {'consumer_bindings','definition_revision'}} and
                    d['definition_revision']==old_d['definition_revision']+1 and
                    d['consumer_bindings'][:len(old_d['consumer_bindings'])]==old_d['consumer_bindings'] and
                    proposed['projection']==old_obligation['projection'] and new_bindings,
                    'OBLIGATION_INVALID','Host can append a consumer without resetting the existing responsibility or its history')
        else:
            require(proposed==expected,'OBLIGATION_INVALID','New assignments start with no attempts or mathematical qualification')
            new_bindings=d['consumer_bindings']
        for c in new_bindings:
            require(c['instance_id']==iid and c['mission_id']==p['mission_id'],'AUTHORIZATION_REQUIRED','Assignment crosses mission')
            validate_assignment(c['stage_id'],d['type'],c['role'],c.get('entry_basis',{}))
            if d['type']=='REPORT':
                ctx=c.get('report_context',{});report=s.get('reports',{}).get(ctx.get('report_id'),{})
                require(report.get('status')!='ABANDONED','REPORT_ABANDONED','An abandoned report cannot assign work.')
                require(iid in report.get('scope',{}).get('instance_ids',[]) and ctx.get('snapshot_ref')==report.get('snapshot_ref'),
                        'REPORT_SCOPE_INVALID','Report assignment must bind the already frozen exact report')
        grant=deepcopy(p['retry_grant'])
        require(grant['obligation_id']==oid and grant['grant_id'] not in s.get('retry_grants',{})
                and type(grant.get('max_research_attempts',1)) is int and 1<=grant.get('max_research_attempts',1)<=scope.get('max_research_attempts',1),
                'AUTHORIZATION_REQUIRED','New assignment may only consume the existing finite sampling allowance')
        grant.setdefault('max_research_attempts',1);grant['remaining_uses']=grant['max_research_attempts']
        grant.update(authorized_by=e['event_id'],source_decision_or_mission_grant=p['mission_id'])
        s.setdefault('retry_grants',{})[grant['grant_id']]=grant;s.setdefault('obligations',{})[oid]=deepcopy(proposed)
        obligations.validate_graph(s['obligations'])
    if kind in {'PREPARE','RESERVE','SENT','CAPTURE','UNKNOWN','SETTLE'} and p.get('issued_at'):
        from .research_audit import transition
        request=s.get('requests',{}).get(p.get('request_id'))
        iid=(request or {}).get('instance_id') or p.get('instance_id') or p.get('task',{}).get('instance_id')
        if iid in s.get('instances',{}):transition(s,iid,at=p['issued_at'])
    s.setdefault('execution_events',{})[e['event_id']]=deepcopy(e);return s

def reserve(store,request_id,*,execution_kind='MODEL',executor_contract=None,model_policy=None):
    s=store.read_snapshot();r=_request(s,request_id);t=s['tasks'][r['task_id']]
    if t.get('report_context'):
        from .reports import dispatch_current
        dispatch_current(s,t['report_context'])
    from .changes import live_check
    if t.get('purpose')=='PROJECT_ASSISTANT':
        from .assistant import validate_dispatch
        validate_dispatch(s,t)
    else:live_check(t,s,store.read_blob)
    receipt=store.commit_execution(event('RESERVE',{'request_id':request_id,'execution_kind':execution_kind,
        'executor_contract':executor_contract or t['executor_contract'],'model_policy':model_policy or t['model_policy']}))
    return {'execution_id':r['execution_id'],'receipt':receipt}

def seal_capture(store,request_id,raw_bytes,*,execution_id=None,usage=None):
    require(isinstance(raw_bytes,bytes),'RESPONSE_SCHEMA_INVALID','Capture preserves exact bytes')
    s=store.read_snapshot();r=_request(s,request_id);task=s['tasks'][r['task_id']]
    require(r['execution_state'] in {'RESERVED','SENT','UNKNOWN','CAPTURED'},'EXISTING_REQUEST','Capture must bind an actual reserved request')
    delivery={}
    if task.get('communication_contract'):
        from .input_delivery import seal as seal_inputs
        delivery=seal_inputs(store,request_id,execution_id or r['execution_id'])
    ref=store.blob(raw_bytes)
    seal={'request_id':request_id,'task_id':task['task_id'],'execution_id':execution_id or r['execution_id'],
          'capture_ref':ref,'task_digest':sha(canonical(task)),'input_manifest_hash':task['input_manifest_hash'],'usage':usage}
    if delivery:seal.update({k:delivery[k] for k in ('delivery_manifest_hash','input_window_seal','delivery_cutoff')})
    immutable(store.root/'execution'/'captures'/(request_id+'.json'),canonical(seal))
    return seal

def capture(store,request_id,raw_bytes,*,execution_id=None,usage=None):
    seal=seal_capture(store,request_id,raw_bytes,execution_id=execution_id,usage=usage)
    result=store.commit_execution(event('CAPTURE',{k:seal[k] for k in ('request_id','execution_id','capture_ref','usage','delivery_manifest_hash','input_window_seal','delivery_cutoff') if k in seal}))
    _release_model_slot(store,request_id)
    return result

def _release_model_slot(store,request_id):
    if store.read_snapshot()['requests'][request_id].get('execution_kind')=='MODEL':
        from .host_pool import release
        release(store,request_id)

def recover_capture_seal(store,request_id):
    s=store.read_snapshot();r=_request(s,request_id);task=s['tasks'][r['task_id']]
    path=store.root/'execution'/'captures'/(request_id+'.json')
    if not path.exists():return False
    seal=loads(read(path));require(set(seal) in ({'request_id','task_id','execution_id','capture_ref','task_digest','input_manifest_hash','usage'},
        {'request_id','task_id','execution_id','capture_ref','task_digest','input_manifest_hash','usage','delivery_manifest_hash','input_window_seal','delivery_cutoff'}),
        'ORIGINAL_BYTES_MISMATCH','Malformed host capture seal')
    require(seal['request_id']==request_id and seal['task_id']==task['task_id'] and seal['execution_id']==r['execution_id']
        and seal['task_digest']==sha(canonical(task)) and seal['input_manifest_hash']==task['input_manifest_hash'],
        'ORIGINAL_BYTES_MISMATCH','Capture seal differs from frozen request')
    store.read_blob(seal['capture_ref'])
    store.commit_execution(event('CAPTURE',{k:seal[k] for k in ('request_id','execution_id','capture_ref','usage','delivery_manifest_hash','input_window_seal','delivery_cutoff') if k in seal}))
    _release_model_slot(store,request_id)
    return True

def recover(store,request_id,*,check_only=False,recheck=False,reason=None):
    from . import resources
    # A completed local transport may have sealed its original files before
    # capture publication ran out of physical resources. Recover those exact
    # bytes; this path never sends a request or invents a new attempt.
    require(type(recheck) is bool,'RECHECK_NOT_ALLOWED','Maintenance recheck must be explicit.')
    snapshot=store.read_snapshot();request=_request(snapshot,request_id)
    if recheck:
        with resources.reserve(store.root,owner='recheck-'+request_id,temporary_bytes=64*resources.MIB,
                               memory_bytes=resources.PHASE_MEMORY['admission'],phase='admission'):
            return _recheck(store,request_id,check_only=check_only,reason=reason)
    if not check_only and not request.get('capture_ref') and (store.root/'runs'/request['task_id']/'capture.json').exists():
        from .runner import recover_transport
        return recover_transport(store,request['task_id'])
    with resources.reserve(store.root,owner='admit-'+request_id,temporary_bytes=64*resources.MIB,
                           memory_bytes=resources.PHASE_MEMORY['admission'],phase='admission'):
        return _recover(store,request_id,check_only=check_only)


def _recheck(store,request_id,*,check_only=False,reason=None):
    from . import changes
    from .contracts import AUTHORING_REVISION
    s=store.read_snapshot();r=_request(s,request_id)
    if r.get('acceptance_state') in {'ACCEPTED','EXACT_DUPLICATE'}:
        return {'state':'EXACT_DUPLICATE','receipt_ref':r.get('receipt_ref'),'capture_ref':r.get('capture_ref'),'model_calls':0}
    context=recheck_context(s,request_id,reason);raw=store.read_blob(context['capture_ref']);task=s['tasks'][r['task_id']]
    try:
        # check_only is read-only, but it still runs every current live guard.
        proposal=changes.validate_response(task,s,raw,mode='live',blob_get=store.read_blob)
        if check_only:return {'state':'VALIDATED_RECHECK','request_id':request_id,'capture_ref':context['capture_ref'],
            'validator_identity':context['validator_identity'],'previous_settlement':context['previous_settlement'],'model_calls':0}
        receipt=store.commit(proposal,admission_recheck=context)
        return {'state':'ACCEPTED','receipt':receipt,'request_id':request_id,'capture_ref':context['capture_ref'],
                'same_original_capture':True,'model_calls':0}
    except PMRSError as exc:
        if exc.code in {'RESOURCE_DISK_LOW','RESOURCE_WAIT','RESOURCE_LIMIT','FILE_UNAVAILABLE','FILE_INVALID','BLOB_CHANGED','JOURNAL_INVALID','CHECKPOINT_CHANGED','CAPABILITY_VIOLATION','STALE_RECHECK','VALIDATOR_CHANGED'}:raise
        diagnostic={'code':exc.code,'message':exc.message,'capture_ref':context['capture_ref'],
            'validator_revision':AUTHORING_REVISION,'validator_identity':context['validator_identity'],
            'details':[changes._error_diagnostic(exc)]}
        payload={**context,'outcome':'REJECTED_CONTRACT','receipt_ref':context['previous_settlement']['receipt_ref'],'diagnostic':diagnostic}
        receipt=None if check_only else store.commit_execution(event('ADMISSION_RECHECKED',payload))
        return {'state':'REJECTED_CONTRACT','code':exc.code,'diagnostic':diagnostic,'capture_ref':context['capture_ref'],
                'recheck_receipt':receipt,'original_rejection_preserved':True,'model_calls':0}

def _recover(store,request_id,*,check_only=False):
    from .changes import validate_response
    s=store.read_snapshot();r=_request(s,request_id);t=deepcopy(s['tasks'][r['task_id']])
    def cleaned(result):
        if not check_only:
            from .runner import cleanup_task_inputs_safely
            cleanup=cleanup_task_inputs_safely(store,t['task_id'])
            if cleanup.get('warning'):result={**result,'cache_cleanup':cleanup}
        return result
    if r['execution_state']=='SETTLED':
        if r['acceptance_state'] in {'ACCEPTED','EXACT_DUPLICATE'} and r.get('receipt_ref'):
            return cleaned({'state':'EXACT_DUPLICATE','receipt_ref':r['receipt_ref'],'model_calls':0})
        return cleaned({'state':r['acceptance_state'],'code':r.get('admission_error'),'diagnostic':r.get('admission_diagnostic'),
            'capture_ref':r['capture_ref'],'model_calls':0})
    if not check_only and not r['capture_ref'] and recover_capture_seal(store,request_id):
        s=store.read_snapshot();r=_request(s,request_id)
    if not r['capture_ref']:return {'state':'WAIT','code':'UNKNOWN_REQUIRES_EVIDENCE' if r['execution_state']=='UNKNOWN' else 'EXISTING_REQUEST','model_calls':0}
    require(not r['fenced'],'TASK_FENCED','Captured bytes retained after cancellation')
    assistant_task=t.get('purpose')=='PROJECT_ASSISTANT'
    report_authorized=False
    if t.get('report_context'):
        from .reports import dispatch_authorized
        report_authorized=dispatch_authorized(s,t)
    if not check_only:
        instance=s['instances'][r['instance_id']]
        paused_stage_capture=(instance['status']=='PAUSED' and t.get('actor_kind')!='MAIN' and r['execution_state']=='CAPTURED')
        require(assistant_task or report_authorized or instance['status']=='ACTIVE' or paused_stage_capture,'TASK_FENCED','Pause preserves MAIN capture until explicit resume; already captured stage results can be admitted without new research')
    raw=store.read_blob(r['capture_ref'])
    try:
        if assistant_task:
            from .assistant import recover as recover_assistant
            return cleaned(recover_assistant(store,request_id,check_only=check_only))
        proposal=validate_response(t,s,raw,mode='preflight' if check_only else 'live',blob_get=store.read_blob)
        if check_only:return {'state':'VALIDATED','proposal':proposal,'model_calls':0}
        receipt=store.commit(proposal)
        # The scientific transaction settles the request and its deterministic
        # admission receipt atomically. No second settlement can race that HEAD.
        return cleaned({'state':'ACCEPTED','receipt':receipt,'model_calls':0})
    except PMRSError as exc:
        if exc.code in {'RESOURCE_DISK_LOW','RESOURCE_WAIT','RESOURCE_LIMIT','TASK_FENCED','FILE_UNAVAILABLE','FILE_INVALID','BLOB_CHANGED','JOURNAL_INVALID','CHECKPOINT_CHANGED','CAPABILITY_VIOLATION'}:
            # Preparation/publication failure is not a scientific disposition.
            # Keep the original capture recoverable, with its consumed budget.
            raise
        if not check_only:
            category='REJECTED_STALE' if exc.code in {'STALE_READ','STALE_QUERY','WRITE_CAS_CONFLICT','STALE_OBLIGATION_DEFINITION'} else 'REJECTED_CONTRACT'
            from .changes import response_diagnostics
            from .contracts import AUTHORING_REVISION
            diagnostics=response_diagnostics(t,s,raw,store.read_blob)
            diagnostic={'code':exc.code,'message':exc.message,'capture_ref':r['capture_ref'],
                'validator_revision':AUTHORING_REVISION,'details':diagnostics['diagnostics'],
                'format_repair_eligible':diagnostics.get('format_repair_eligible',False)}
            store.commit_execution(event('SETTLE',{'request_id':request_id,'acceptance_state':category,'receipt_ref':None,'error':exc.code,
                'diagnostic':diagnostic}))
            return cleaned({'state':category,'code':exc.code,'diagnostic':diagnostic,'capture_ref':r['capture_ref'],'model_calls':0})
        raise


def prepare_repair(store,request_id,repair_kind):
    """Create one separately costed candidate; never edit or resend a capture."""
    from .context import token_preflight
    from .engine import Engine
    import base64
    s=store.read_snapshot();previous=_request(s,request_id);origin=previous.get('repair_of',request_id);root=_request(s,origin)
    frozen=s['tasks'][root['task_id']];task=deepcopy(frozen)
    count=sum(r.get('repair_of')==origin and r.get('repair_kind')==repair_kind for r in s['requests'].values())
    task.update(repair_of=origin,repair_kind=repair_kind,repair_index=count+1)
    task['task_id']=identity({'origin':origin,'repair':repair_kind,'ordinal':count+1},'TASK-');task['request_id']=identity(task['task_id'],'REQUEST-')
    packet=loads(store.read_blob(frozen['input_packet_ref']));prompt=store.read_blob(frozen['prompt_ref']).decode()
    proof=None
    if repair_kind=='FORMAT':
        require(previous.get('capture_ref'),'REPAIR_NOT_ALLOWED','A sealed original capture is required')
        original_bytes=store.read_blob(previous['capture_ref'])
        diagnostic=format_diagnostic(s,request_id,original_bytes,store.read_blob)
        encoded=base64.b64encode(original_bytes).decode()
        proof={'schema':'pmrs.format-repair-proof/1','raw_base64':encoded,'diagnostic':diagnostic}
        packet['format_repair']={'original_request_id':request_id,'original_capture_ref':previous['capture_ref'],
             'original_bytes_base64':encoded,'recorded_error':previous.get('admission_error'),'diagnostic':diagnostic}
        from .contracts import authoring_contract
        contract=authoring_contract(task,s)
        contract.pop('knowledge_change_schema',None)
        prompt+='\n\nFINITE FORMAT REPAIR\n'+canonical({'instructions':
            'Decode and read the original saved response in packet.format_repair.original_bytes_base64. Repair only JSON representation and exact new task/request binding. '
            'Preserve the original mathematical body, actual work account, claims, conditions, missing-source boundary and unchecked status. '
            'Do not add new science, new claims, new evidence, source retrieval or stronger work disposition; do not treat contract rejection as a mathematical failure. '
            'The current contract below supersedes incomplete authoring shape instructions only. Record fields using exact body locators; preserve partial/open duties. '
            'Return one complete native response under this new task/request. The original capture remains immutable.',
            'diagnostic':diagnostic,'complete_response_contract':contract}).decode()
    task['input_packet_ref']=store.blob(canonical(packet));task['prompt_ref']=store.blob(prompt.encode())
    if task.get('model_input_revision'):
        from .tasks import model_packet_payload
        task['model_packet_ref']=store.blob(canonical(model_packet_payload(packet)))
    if frozen.get('report_context'):
        # The original frozen grant owns repairs, even if a later report role
        # obtains a separately authorized grant.
        policy=deepcopy(s['budget_grants'][root['budget_grant_id']].get('execution_policy',{}))
    else:policy=Engine().policy(store,root['instance_id'])
    capacity=deepcopy(policy.get('capacity',{}))
    require(capacity.get('model_id')==task['model_policy']['model'],'CONTEXT_LIMIT','Repair retains the frozen model')
    overhead=frozen['context_budget']['prompt_overhead_tokens']
    if frozen.get('executor_contract',{}).get('client_input_evidence'):
        from .codex_client import derive_task_input_evidence
        derived=derive_task_input_evidence({'executor_contract':frozen['executor_contract'],
            'prompt_overhead_tokens':overhead},store.root,task['task_id'],task.get('actor_kind'))
        task['executor_contract']['client_input_evidence']=derived['client_input_evidence']
        overhead=derived['prompt_overhead_tokens']
    from .tasks import request_budget
    for _ in range(6):
        budget,details=request_budget(task,prompt,packet,capacity,
            reserved_output_tokens=frozen['context_budget']['reserved_output_tokens'],
            prompt_overhead_tokens=overhead,
            safety_margin_tokens=frozen['context_budget']['safety_margin_tokens'])
        if task.get('context_budget')==budget and task.get('context_budget_details')==details:break
        task['context_budget']=budget;task['context_budget_details']=details
    else:raise PMRSError('CONTEXT_LIMIT','Repair input accounting did not converge.')
    payload={'original_request_id':request_id,'repair_kind':repair_kind,'task':task}
    if proof:payload['format_proof']=proof
    receipt=store.commit_execution(event('PREPARE_REPAIR',payload))
    return {**receipt,'task_id':task['task_id'],'request_id':task['request_id']}


def verify_format_proof(snapshot,request_id,proof,blob_get=None,*,historical=False):
    """Verify a native proof without relabeling historic validator behavior.

    Live creation re-executes all current admission checks using exact blobs.
    Historical event replay checks immutable capture/snapshot/projection and
    recorded implementation identities, without running a different validator
    and claiming it was the historical one. Legacy proofs remain read-only.
    """
    import base64
    from . import contracts as C
    from .changes import science_projection,validation_snapshot_digest
    require(isinstance(proof,dict),'REPAIR_NOT_ALLOWED','A complete format proof is required')
    version=proof.get('schema')
    if version is None:
        require(historical and set(proof)=={'raw_base64','diagnostic'},'REPAIR_NOT_ALLOWED','Legacy format proofs are for historical replay only')
    else:
        C.fields(proof,{'schema','raw_base64','diagnostic'},'FormatRepairProof')
        require(version=='pmrs.format-repair-proof/1','REPAIR_NOT_ALLOWED','Unknown format proof version')
    try:raw=base64.b64decode(proof['raw_base64'],validate=True)
    except (ValueError,TypeError) as exc:raise PMRSError('REPAIR_NOT_ALLOWED','Invalid original capture proof') from exc
    require(len(raw)<=C.MAX_PAYLOAD,'PAYLOAD_LIMIT','Original format capture exceeds its size bound')
    request=_request(snapshot,request_id);task=snapshot['tasks'][request['task_id']];evidence=proof['diagnostic']
    require(request.get('capture_ref')==sha(raw),'ORIGINAL_BYTES_MISMATCH','Format proof has different captured bytes')
    if version is None:
        require(evidence.get('capture_ref')==request['capture_ref'] and evidence.get('recorded_error')==request.get('admission_error'),
            'ORIGINAL_BYTES_MISMATCH','Legacy proof is not bound to its original refusal')
        return True
    require(evidence.get('schema')=='pmrs.format-evidence/1' and evidence.get('eligible') is True,
        'REPAIR_NOT_ALLOWED','Only complete positive pure-format evidence can reserve a repair')
    require(evidence.get('task_id')==task['task_id'] and evidence.get('request_id')==request_id
        and evidence.get('capture_sha256')==evidence.get('capture_ref')==request['capture_ref']
        and evidence.get('recorded_error')==request.get('admission_error'),'ORIGINAL_BYTES_MISMATCH','Format proof task, capture or original refusal differs')
    require(evidence.get('snapshot_digest')==validation_snapshot_digest(snapshot)
        and evidence.get('snapshot_commit')==snapshot.get('knowledge_commit'),'STALE_READ','The exact validation snapshot changed before FORMAT preparation')
    require(evidence.get('projection_revision')==C.SCIENCE_PROJECTION_REVISION
        and evidence.get('projection_digest')==C.digest(science_projection(raw)),'REPAIR_SCIENCE_UNVERIFIABLE','Original scientific projection differs')
    implementation=evidence.get('validator_revision',{})
    require(implementation.get('revision')=='pmrs.admission-validator/3' and isinstance(implementation.get('modules'),dict)
        and all(C.HASH.fullmatch(x) for x in implementation['modules'].values())
        and {'contracts.py','changes.py','knowledge.py','relations.py','assurance.py'}<=set(implementation['modules'])
        and C.HASH.fullmatch(str(evidence.get('contract_digest'))),'REPAIR_SCIENCE_UNVERIFIABLE','Original contract and validator implementation identities are missing')
    if not historical:
        require(blob_get is not None,'INCOMPLETE_CONTEXT','Live FORMAT verification requires all exact original bytes')
        require(blob_get(request['capture_ref'])==raw,'ORIGINAL_BYTES_MISMATCH','Native original capture differs')
        current=format_diagnostic(snapshot,request_id,raw,blob_get)
        require(current==evidence,'ORIGINAL_BYTES_MISMATCH','Live format evidence differs from the sealed capture and current validator')
    return True
