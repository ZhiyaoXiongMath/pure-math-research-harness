"""One request ledger for research and reports, with capture-before-admission recovery."""
from copy import deepcopy
from .util import identity,require,canonical,PMRSError,immutable,loads,read,sha
from . import obligations

EVENT_TYPES={'PREPARE','RESERVE','SENT','UNKNOWN','CAPTURE','SETTLE','VISIT_OPENED','VISIT_DISPOSED',
             'NATIVE_RESTORED','ASSIGN_OBLIGATION','COVERAGE_PLAN_REGISTERED','PREPARE_REPAIR'}

def event(event_type,payload,*,event_id=None):
    e={'actor':'host','capability_ref':'CAP-HOST','event_type':event_type,'payload':deepcopy(payload)}
    e['event_id']=event_id or identity(e,'EXEC-EVENT-');return e

def _request(s,rid):
    require(rid in s.get('requests',{}),'REQUEST_UNKNOWN',rid);return s['requests'][rid]

def apply_event(snapshot,e):
    old=snapshot.get('execution_events',{}).get(e.get('event_id'))
    if old:
        require(old==e,'ALREADY_SETTLED_CONTENT_CONFLICT','Execution event identity conflict');return deepcopy(snapshot)
    require(set(e)=={'event_id','actor','capability_ref','event_type','payload'} and e['event_type'] in EVENT_TYPES,
            'EXECUTION_EVENT_INVALID','Typed execution event required')
    cap=snapshot.get('capabilities',{}).get(e['capability_ref'],{})
    require(e['actor']=='host' and cap.get('actor')=='host','AUTHORIZATION_REQUIRED','Execution requires host capability')
    s=deepcopy(snapshot);p=e['payload'];kind=e['event_type']
    if kind=='PREPARE':
        from .scheduler import budget_remaining,project_remaining
        from .workflows.registry import validate_assignment
        task=deepcopy(p['task']);candidate=p['candidate'];c=candidate['consumer']
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
        require(project_remaining(s)>=1 and budget_remaining(s,candidate['budget_grant_id'])>=1,'BUDGET_EXHAUSTED','All unresolved reservations count against the budget')
        existing=[r['sample_slot'] for r in s.get('requests',{}).values() if r['attempt_group_key']==task['attempt_group_key']]
        require(task['sample_slot']==max(existing,default=0)+1,'WRITE_CAS_CONFLICT','Host sample slot was concurrently allocated')
        require(task['context_budget']['input_tokens']+task['context_budget']['prompt_overhead_tokens']+task['context_budget']['reserved_output_tokens']+task['context_budget']['safety_margin_tokens']<=task['context_budget']['context_window_tokens'],
                'CONTEXT_LIMIT','Frozen request exceeds model capacity')
        s.setdefault('tasks',{})[task['task_id']]=task
        request={k:task[k] for k in ('request_id','task_id','instance_id','mission_id','purpose_key','responsibility_key','attempt_group_key','attempt_key','sample_slot','input_fingerprint')}
        request.update(execution_state='PREPARED',acceptance_state='NOT_SUBMITTED',execution_kind=None,
                       execution_id=identity({'request':task['request_id']},'EXECUTION-'),budget_grant_id=candidate['budget_grant_id'],
                       reserved_calls=1,capture_ref=None,usage=None,fenced=False,receipt_ref=None)
        s.setdefault('requests',{})[request['request_id']]=request
        grant=s['retry_grants'][c['retry_grant_id']]
        grant['remaining_uses']=current['remaining_uses']-1
        ledger=s.setdefault('attempt_groups',{}).setdefault(task['attempt_group_key'],{'request_ids':[],'highest_sample_slot':0})
        ledger['request_ids'].append(request['request_id']);ledger['highest_sample_slot']=task['sample_slot']
        s.setdefault('scheduler_state',{}).setdefault('last_instance_by_tier',{})[str(candidate['priority'])]=task['instance_id']
    elif kind=='PREPARE_REPAIR':
        from .scheduler import budget_remaining,project_remaining
        require(set(p)=={'original_request_id','repair_kind','task'},'EXECUTION_EVENT_INVALID','Typed finite repair request required')
        original=_request(s,p['original_request_id']);origin=original.get('repair_of',original['request_id']);root=_request(s,origin)
        frozen=s['tasks'][root['task_id']];task=deepcopy(p['task']);repair_kind=p['repair_kind']
        require(repair_kind in {'FORMAT','TRANSPORT'} and task.get('repair_of')==origin and task.get('repair_kind')==repair_kind,
            'REPAIR_NOT_ALLOWED','Repair must preserve its original scientific attempt')
        count=sum(r.get('repair_of')==origin and r.get('repair_kind')==repair_kind for r in s['requests'].values())
        limit=frozen.get('repair_limits',{}).get(repair_kind,0)
        require(type(limit) is int and 0<=limit<=3 and count<limit and task['repair_index']==count+1,'REPAIR_LIMIT','Frozen finite repair allowance exhausted')
        if repair_kind=='TRANSPORT':require(original['execution_state']=='CANCELLED_BEFORE_SEND','REPAIR_NOT_ALLOWED','UNKNOWN or sent requests cannot be retried as transport repairs')
        else:require(original['execution_state']=='SETTLED' and original['acceptance_state']=='REJECTED_CONTRACT' and original.get('admission_error') in {'RESPONSE_SCHEMA_INVALID','DUPLICATE_JSON_KEY','UNKNOWN_FIELD'},
            'REPAIR_NOT_ALLOWED','Only a recorded format rejection permits a format repair')
        allowed={'task_id','request_id','input_packet_ref','prompt_ref','context_budget','repair_of','repair_kind','repair_index'}
        require({k:v for k,v in task.items() if k not in allowed}=={k:v for k,v in frozen.items() if k not in allowed},
            'EXECUTOR_CONTRACT_CHANGED','Repair cannot change science scope, sample, model, executor or permissions')
        require(task['task_id'] not in s['tasks'] and task['request_id'] not in s['requests'],'EXISTING_REQUEST','Reuse registered repair request')
        require(s['instances'][root['instance_id']]['status']=='ACTIVE' and project_remaining(s)>=1 and budget_remaining(s,root['budget_grant_id'])>=1,
            'BUDGET_EXHAUSTED','Repairs consume the same finite project and mission budget')
        from .context import validate_budget
        validate_budget(task['context_budget']);s['tasks'][task['task_id']]=task
        r={k:root[k] for k in ('instance_id','mission_id','purpose_key','responsibility_key','attempt_group_key','attempt_key','sample_slot','input_fingerprint','budget_grant_id')}
        r.update(request_id=task['request_id'],task_id=task['task_id'],execution_id=identity(task['request_id'],'EXECUTION-'),execution_state='PREPARED',
            acceptance_state='NOT_SUBMITTED',execution_kind=None,reserved_calls=1,capture_ref=None,usage=None,fenced=False,receipt_ref=None,
            repair_of=origin,repair_kind=repair_kind,repair_index=count+1)
        s['requests'][r['request_id']]=r
    elif kind=='RESERVE':
        r=_request(s,p['request_id']);task=s['tasks'][r['task_id']]
        require(r['execution_state']=='PREPARED' and not r['fenced'],'EXISTING_REQUEST','A sent, uncertain or captured request cannot be resent')
        require(s['instances'][r['instance_id']]['status']=='ACTIVE','TASK_FENCED','Workflow is paused')
        active=sum(x['execution_state'] in {'RESERVED','SENT','UNKNOWN'} and x.get('unknown_disposition')!='ABANDON_UNKNOWN' for x in s.get('requests',{}).values())
        require(active<s.get('max_workers',1),'BUDGET_OR_WORKER_LIMIT','Uncertain requests retain worker reservations')
        require(p['executor_contract']==task['executor_contract'] and p['model_policy']==task['model_policy'],
                'EXECUTOR_CONTRACT_CHANGED','No silent executor, permission, model, effort or tier change')
        from .changes import live_check
        live_check(task,s)
        require(p['execution_kind'] in {'MODEL','SYNTHETIC_TEST_ONLY'},'EXECUTION_EVENT_INVALID','Unknown execution provenance')
        if p['execution_kind']=='SYNTHETIC_TEST_ONLY':require(s.get('synthetic_test_only') is True,'SYNTHETIC_PROJECT_REQUIRED','Fake output cannot qualify real research')
        r.update(execution_state='RESERVED',execution_kind=p['execution_kind'])
    elif kind in {'SENT','UNKNOWN'}:
        r=_request(s,p['request_id']);require(r['execution_state'] in {'RESERVED','SENT'},'EXECUTION_TRANSITION_INVALID','No active send boundary')
        require(p.get('execution_id')==r['execution_id'],'EXECUTION_IDENTITY','Original request execution required')
        r['execution_state']=kind
        if kind=='UNKNOWN':r['uncertainty_reason']=p.get('reason','Transport result unknown')
    elif kind=='CAPTURE':
        r=_request(s,p['request_id']);task=s['tasks'][r['task_id']]
        require(p.get('execution_id')==r['execution_id'],'EXECUTION_IDENTITY','Capture must bind the original execution')
        if r['capture_ref']:
            require(r['capture_ref']==p['capture_ref'],'ALREADY_SETTLED_CONTENT_CONFLICT','Do not overwrite original captured bytes')
        else:
            require(r['execution_state'] in {'RESERVED','SENT','UNKNOWN'},'EXECUTION_TRANSITION_INVALID','Capture requires the original request')
            r.update(capture_ref=p['capture_ref'],execution_state='CAPTURED',acceptance_state='PENDING',usage=deepcopy(p.get('usage')))
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
        else:r.update(execution_state='SETTLED',acceptance_state=p['acceptance_state'],receipt_ref=p.get('receipt_ref'),admission_error=p.get('error'))
    elif kind=='VISIT_OPENED':
        from .workflows.registry import spec,validate_assignment
        visit=deepcopy(p['visit']);iid=visit['instance_id'];mission=s['missions'][visit['mission_id']]
        require(s['instances'][iid]['status']=='ACTIVE' and mission['instance_id']==iid,'AUTHORIZATION_REQUIRED','Active authorized mission required')
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
    elif kind=='ASSIGN_OBLIGATION':
        from .workflows.registry import validate_assignment
        from .contracts import HASH
        require(set(p)=={'instance_id','mission_id','obligation','retry_grant','authorization_basis_ref'},
                'EXECUTION_EVENT_INVALID','Exact bounded host assignment required')
        iid=p['instance_id'];mission=s.get('missions',{}).get(p['mission_id'],{})
        require(mission.get('instance_id')==iid and mission.get('status')=='ACTIVE'
                and s['instances'][iid]['status']=='ACTIVE','AUTHORIZATION_REQUIRED','Host assignment requires an active authorized mission')
        proposed=p['obligation'];d=proposed['definition'];oid=d['obligation_id'];scope=mission['authorized_scope']
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
        if d['type']=='REPORT':require(scope.get('reports') is True or 'REPORT' in scope.get('obligation_types',[]),
                                      'AUTHORIZATION_REQUIRED','Formal reporting must be requested within the mission budget')
        else:require(scope.get('allow_derived_work') is True,'AUTHORIZATION_REQUIRED','Mission has no authority to add derived research work')
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
    s.setdefault('execution_events',{})[e['event_id']]=deepcopy(e);return s

def reserve(store,request_id,*,execution_kind='MODEL',executor_contract=None,model_policy=None):
    s=store.read_snapshot();r=_request(s,request_id);t=s['tasks'][r['task_id']]
    from .changes import live_check
    live_check(t,s,store.read_blob)
    receipt=store.commit_execution(event('RESERVE',{'request_id':request_id,'execution_kind':execution_kind,
        'executor_contract':executor_contract or t['executor_contract'],'model_policy':model_policy or t['model_policy']}))
    return {'execution_id':r['execution_id'],'receipt':receipt}

def seal_capture(store,request_id,raw_bytes,*,execution_id=None,usage=None):
    require(isinstance(raw_bytes,bytes),'RESPONSE_SCHEMA_INVALID','Capture preserves exact bytes')
    s=store.read_snapshot();r=_request(s,request_id);task=s['tasks'][r['task_id']]
    require(r['execution_state'] in {'RESERVED','SENT','UNKNOWN','CAPTURED'},'EXISTING_REQUEST','Capture must bind an actual reserved request')
    ref=store.blob(raw_bytes)
    seal={'request_id':request_id,'task_id':task['task_id'],'execution_id':execution_id or r['execution_id'],
          'capture_ref':ref,'task_digest':sha(canonical(task)),'input_manifest_hash':task['input_manifest_hash'],'usage':usage}
    immutable(store.root/'execution'/'captures'/(request_id+'.json'),canonical(seal))
    return seal

def capture(store,request_id,raw_bytes,*,execution_id=None,usage=None):
    seal=seal_capture(store,request_id,raw_bytes,execution_id=execution_id,usage=usage)
    return store.commit_execution(event('CAPTURE',{k:seal[k] for k in ('request_id','execution_id','capture_ref','usage')}))

def recover_capture_seal(store,request_id):
    s=store.read_snapshot();r=_request(s,request_id);task=s['tasks'][r['task_id']]
    path=store.root/'execution'/'captures'/(request_id+'.json')
    if not path.exists():return False
    seal=loads(read(path));require(set(seal)=={'request_id','task_id','execution_id','capture_ref','task_digest','input_manifest_hash','usage'},
        'ORIGINAL_BYTES_MISMATCH','Malformed host capture seal')
    require(seal['request_id']==request_id and seal['task_id']==task['task_id'] and seal['execution_id']==r['execution_id']
        and seal['task_digest']==sha(canonical(task)) and seal['input_manifest_hash']==task['input_manifest_hash'],
        'ORIGINAL_BYTES_MISMATCH','Capture seal differs from frozen request')
    store.read_blob(seal['capture_ref'])
    store.commit_execution(event('CAPTURE',{k:seal[k] for k in ('request_id','execution_id','capture_ref','usage')}))
    return True

def recover(store,request_id,*,check_only=False):
    from .changes import validate_response
    s=store.read_snapshot();r=_request(s,request_id);t=deepcopy(s['tasks'][r['task_id']])
    if r['execution_state']=='SETTLED':
        if r['acceptance_state'] in {'ACCEPTED','EXACT_DUPLICATE'} and r.get('receipt_ref'):
            return {'state':'EXACT_DUPLICATE','receipt_ref':r['receipt_ref'],'model_calls':0}
        return {'state':r['acceptance_state'],'code':r.get('admission_error'),'capture_ref':r['capture_ref'],'model_calls':0}
    if not check_only and not r['capture_ref'] and recover_capture_seal(store,request_id):
        s=store.read_snapshot();r=_request(s,request_id)
    if not r['capture_ref']:return {'state':'WAIT','code':'UNKNOWN_REQUIRES_EVIDENCE' if r['execution_state']=='UNKNOWN' else 'EXISTING_REQUEST','model_calls':0}
    require(not r['fenced'],'TASK_FENCED','Captured bytes retained after cancellation')
    if not check_only:require(s['instances'][r['instance_id']]['status']=='ACTIVE','TASK_FENCED','Pause preserves capture; human resume is required before admission')
    raw=store.read_blob(r['capture_ref'])
    try:
        proposal=validate_response(t,s,raw,mode='preflight' if check_only else 'live',blob_get=store.read_blob)
        if check_only:return {'state':'VALIDATED','proposal':proposal,'model_calls':0}
        receipt=store.commit(proposal)
        # The scientific transaction settles the request and its deterministic
        # admission receipt atomically. No second settlement can race that HEAD.
        return {'state':'ACCEPTED','receipt':receipt,'model_calls':0}
    except PMRSError as exc:
        if not check_only:
            category='REJECTED_STALE' if exc.code in {'STALE_READ','STALE_QUERY','WRITE_CAS_CONFLICT','STALE_OBLIGATION_DEFINITION'} else 'REJECTED_CONTRACT'
            store.commit_execution(event('SETTLE',{'request_id':request_id,'acceptance_state':category,'receipt_ref':None,'error':exc.code}))
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
    if repair_kind=='FORMAT':
        require(previous.get('capture_ref'),'REPAIR_NOT_ALLOWED','A sealed original capture is required')
        packet['format_repair']={'original_request_id':request_id,'original_capture_ref':previous['capture_ref'],
             'original_bytes_base64':base64.b64encode(store.read_blob(previous['capture_ref'])).decode(),
             'recorded_error':previous.get('admission_error')}
        prompt+='\n\nThis is a finite format repair of the preserved original capture. Produce a new complete response for this new task/request binding. Do not change the scientific claim, introduce evidence, or treat the original rejection as mathematical failure.'
    task['input_packet_ref']=store.blob(canonical(packet));task['prompt_ref']=store.blob(prompt.encode())
    policy=Engine().policy(store,root['instance_id']);capacity=deepcopy(policy.get('capacity',{}))
    require(capacity.get('model_id')==task['model_policy']['model'],'CONTEXT_LIMIT','Repair retains the frozen model')
    task['context_budget']=token_preflight(canonical({'task':task,'prompt':prompt,'packet':packet}),capacity,
       reserved_output_tokens=frozen['context_budget']['reserved_output_tokens'],safety_margin_tokens=frozen['context_budget']['safety_margin_tokens'])
    receipt=store.commit_execution(event('PREPARE_REPAIR',{'original_request_id':request_id,'repair_kind':repair_kind,'task':task}))
    return {**receipt,'task_id':task['task_id'],'request_id':task['request_id']}
