"""Freeze exact native tasks and bytes; all dispatches use the shared registry."""
from copy import deepcopy
import base64
from .util import canonical,identity,require,sha
from . import resources
from .workflows.registry import spec,prompt,INDEPENDENT,validate_assignment

DEFAULT_MODEL={'model':'gpt-6-astra','reasoning_effort':'xhigh','service_tier':'default'}

def freeze(store,snapshot,candidate,policy):
    with resources.reserve(store.root,owner="freeze-task",temporary_bytes=128*resources.MIB,memory_bytes=resources.MAX_PREPARATION_MEMORY,max_preparations=min(2,snapshot.get('max_workers',1))):
        return _freeze(store,snapshot,candidate,policy)

def _freeze(store,snapshot,candidate,policy):
    from .context import build_packet,token_preflight
    from .contracts import registry as contract_registry
    c=candidate['consumer'];o=snapshot['obligations'][candidate['obligation_id']];d=o['definition']
    resources.json_bytes({'consumer':c,'definition':d},resources.METADATA_BYTES,code='CONTEXT_LIMIT')
    from .workflow_instances import validate_discovery_scope
    discovery_scope=validate_discovery_scope(snapshot,snapshot['instances'][c['instance_id']])
    required_sources=list(dict.fromkeys(list(c.get('source_refs',()))+list(discovery_scope.values())))
    for source in c.get('survey_context',{}).get('source_details',{}).values():
        if source.get('text_source_ref'):required_sources.append(source['text_source_ref'])
    stage=spec(c['stage_id']);role=c['role'];basis=deepcopy(c.get('entry_basis',{}))
    from . import model_policy
    purpose=c.get('work_purpose','DEFAULT')
    requested_scope={'workflow_kind':stage['workflow_kind'],'stage_id':c['stage_id'],'role':role,'purpose':purpose}
    overrides=deepcopy(policy.get('model_overrides',[]))
    if policy.get('model_override'):overrides.append(deepcopy(policy['model_override']))
    seen=set();override=None
    for item in overrides:
        key=canonical(item.get('scope'))
        require(key not in seen,'MODEL_POLICY_INVALID','Duplicate model override scope');seen.add(key)
        model_policy.validate_override(item)
        if item['scope']==requested_scope:override=item
    if policy.get('model_policy'):
        require(snapshot.get('synthetic_test_only') or policy.get('configuration_authorized') is True,
                'AUTHORIZATION_REQUIRED','Future task model configuration must be explicitly authorized')
        override={'explicit':True,'scope':{'workflow_kind':stage['workflow_kind'],'stage_id':c['stage_id'],'role':role,'purpose':purpose},
                  **deepcopy(policy['model_policy'])}
    capabilities=policy.get('model_capabilities',snapshot.get('model_capabilities'))
    if capabilities is None and snapshot.get('synthetic_test_only'):
        test_model=override.get('model',model_policy.DEFAULT_MODEL) if override else model_policy.DEFAULT_MODEL
        test_effort=override.get('reasoning_effort') if override else None
        capabilities={'source':'SYNTHETIC_TEST_ONLY','revision':'deterministic-test-1','executor':'fake',
                      'models':{test_model:{'reasoning_efforts':[test_effort] if test_effort else ['high','xhigh','max'],
                         'service_tiers':[override.get('service_tier','default') if override else 'default']}}}
    require(snapshot.get('synthetic_test_only') or not capabilities or capabilities.get('source')!='SYNTHETIC_TEST_ONLY',
            'MODEL_CAPABILITY_UNKNOWN','Test capability evidence cannot authorize real dispatch')
    resolved=model_policy.resolve(stage['workflow_kind'],c['stage_id'],role,purpose,override=override,capabilities=capabilities)
    require(resolved['call_model'],'NO_MODEL_OPERATION','Host and human controls never generate model requests')
    assignment=validate_assignment(c['stage_id'],d['type'],role,basis)
    independent=role in INDEPENDENT
    siblings=[t['task_id'] for t in snapshot.get('tasks',{}).values() if t['instance_id']==c['instance_id']
              and t.get('visit_id')==c.get('visit_id') and t['role']!=role]
    if not independent and not basis.get('analysis_route')=='COMPARATIVE':siblings=[]
    from .obligations import dependency_inputs
    roots=list(dict.fromkeys(d['target_refs']+d['scope_context_refs']+c.get('input_refs',[])+dependency_inputs(snapshot,d)))
    report_context=deepcopy(c.get('report_context'))
    if report_context and role=='REPORT_VISUAL':
        roots=[];required_sources=[]
    if c.get('coverage_part'):
        from .context import build_coverage_packet
        packet=build_coverage_packet(snapshot,c['coverage_part'],store.read_blob,independent=independent,
            required_source_refs=required_sources,sibling_tasks=siblings)
    else:
        packet=build_packet(snapshot,roots,store.read_blob,independent=independent or basis.get('analysis_route')=='COMPARATIVE',
                            required_source_refs=required_sources,sibling_tasks=siblings,
                            budget_blob_hashes=(report_context or {}).get('files',{}).values())
    criterion_ref=d['criterion_body_ref']
    try:
        require(resources.blob_info(store,criterion_ref)['bytes']<=resources.METADATA_BYTES,'CONTEXT_LIMIT','Task instructions exceed the metadata budget.')
        criterion=store.read_blob(criterion_ref).decode('utf-8')
    except (ValueError,KeyError) as exc:
        if getattr(exc,'code',None)=='CONTEXT_LIMIT':raise
        # Criterion strings are allowed only in an explicit deterministic test project.
        require(snapshot.get('synthetic_test_only',False),'INCOMPLETE_CONTEXT','Criterion body is not available')
        criterion=criterion_ref
    generated=prompt(c['stage_id'],role,criterion)
    generated['sections']['TARGET_CONTEXT_AND_SCOPE']=canonical({'target_refs':d['target_refs'],'scope':c.get('scope',{}),'entry_basis':basis}).decode()
    survey_context=deepcopy(c.get('survey_context'))
    if survey_context:
        from .survey import response_contract
        generated['sections']['SURVEY_FROZEN_CONTEXT']=canonical(survey_context).decode()
        generated['sections']['SURVEY_RESULT_CONTRACT']=canonical(response_contract(role)).decode()
    if discovery_scope:generated['sections']['EXACT_DISCOVERY_SCOPE']=canonical(discovery_scope).decode()
    generated['sections']['ACTUAL_INPUT_MANIFEST']=canonical(packet['input_manifest']).decode()
    generated['sections']['OUTPUT_CONTRACT']=canonical(contract_registry()).decode()
    require(sum(len(value.encode()) for value in generated['sections'].values())<=resources.METADATA_BYTES,'CONTEXT_LIMIT','Complete instructions exceed the task metadata budget.')
    instructions='\n\n'.join(k+'\n'+v for k,v in generated['sections'].items())
    instructions+='\n\nWrite new research and reports in English. Preserve quoted original source bytes. Return only the frozen response schema. Do not call another model or read sibling sessions.'
    model={k:resolved[k] for k in ('model','reasoning_effort','service_tier')}
    permission={'allowed_payload_kinds':assignment['role_contract']['payload_kinds'],
                'allowed_record_kinds':stage['allowed_scientific_kinds'],
                'allowed_operations':['NEW','REVISE','LINK','WITHDRAW_SUPPORT']}
    response_contract={'schema':'pmrs.response/final-1','permission_manifest':permission,'stage_spec_digest':stage['digest']}
    # Reject expansion before constructing full text/base64 and JSON copies.
    material={**packet['bodies'],**packet['source_bodies']}
    report_sizes={}
    if report_context:
        for digest in set(report_context['files'].values()):report_sizes[digest]=resources.blob_info(store,digest)['bytes']
    unique_bytes=sum(len(raw) for raw in material.values())+sum(size for digest,size in report_sizes.items() if digest not in material)
    require(unique_bytes<=resources.CONTEXT_BYTES,'CONTEXT_LIMIT','Complete report inputs exceed the material budget before serialization; choose an explicit smaller coverage scope.')
    wire={k:v for k,v in packet.items() if k not in {'bodies','source_bodies'}}
    resources.json_bytes(wire,resources.METADATA_BYTES,code='CONTEXT_LIMIT')
    # A text byte can expand to six JSON bytes; count actual escaped text in
    # bounded chunks before canonical serialization, and base64 by its formula.
    predicted=resources.json_bytes(wire,resources.SERIALIZED_BYTES,code='CONTEXT_LIMIT')
    for raw in packet['bodies'].values():predicted+=resources.json_bytes(raw.decode('utf-8'),resources.SERIALIZED_BYTES,code='CONTEXT_LIMIT')
    predicted+=sum(4*((len(raw)+2)//3)+128 for raw in packet['source_bodies'].values())
    require(predicted+len(instructions.encode())<=resources.SERIALIZED_BYTES,'CONTEXT_LIMIT','Complete serialized input exceeds the preparation budget before base64 construction.')
    wire['body_text']={h:b.decode('utf-8') for h,b in packet['bodies'].items()}
    wire['source_bytes_base64']={h:base64.b64encode(b).decode('ascii') for h,b in packet['source_bodies'].items()}
    if report_context:
        require(role==report_context['role'],'REPORT_SCOPE_INVALID','Frozen report role differs')
        wire['report_files']={name:{'sha256':digest,'bytes':report_sizes[digest],'path':'report-inputs/'+name} for name,digest in report_context['files'].items()}
        wire['report_context']=report_context
        from .reports import authoring_rules
        instructions+='\n\n'+authoring_rules(report_context)
    serialized=resources.bounded_canonical({'prompt':instructions,'packet':wire,'response_contract':response_contract},code='CONTEXT_LIMIT')
    file_token_bound=sum(4*((report_sizes[digest]+2)//3) for digest in (report_context or {}).get('files',{}).values())
    capacity=policy.get('capacity',snapshot.get('model_capacities',{}).get(model['model']))
    require(capacity is not None,'CONTEXT_LIMIT','No verified model capacity configured for the requested model')
    require(capacity.get('model_id')==model['model'],'CONTEXT_LIMIT','Model capacity must match the actual frozen model')
    require(snapshot.get('synthetic_test_only') or capacity.get('capacity_source')!='SYNTHETIC_TEST_ONLY',
            'CONTEXT_LIMIT','Synthetic capacity cannot authorize a real model request')
    budget=token_preflight(serialized,capacity,reserved_output_tokens=policy.get('reserved_output_tokens',4096),
                           safety_margin_tokens=policy.get('safety_margin_tokens',1024),additional_input_bytes=file_token_bound)
    prior_slots=[r['sample_slot'] for r in snapshot.get('requests',{}).values() if r.get('attempt_group_key')==candidate['attempt_group_key']]
    sample_slot=max(prior_slots,default=0)+1
    attempt_key=identity({'group':candidate['attempt_group_key'],'sample_slot':sample_slot},'ATTEMPT-')
    tid=identity({'attempt':attempt_key,'contract':stage['digest'],'instance':c['instance_id'],'mission':c['mission_id']},'TASK-')
    task={'schema':'pmrs.task/final-1','task_id':tid,'request_id':identity({'task':tid},'REQUEST-'),
          'instance_id':c['instance_id'],'mission_id':c['mission_id'],'visit_id':c.get('visit_id'),
          'stage_id':c['stage_id'],'stage_spec_digest':stage['digest'],'role':role,
          'obligation_bindings':[{'binding_id':c['binding_id'],'obligation_id':d['obligation_id'],'expected_definition_revision':d['definition_revision']}],
          'target_refs':d['target_refs'],'knowledge_commit':snapshot.get('knowledge_commit'),
          'read_set':packet['read_set'],'query_guards':c.get('query_guards',[]),'write_guards':c.get('write_guards',[]),
          'input_manifest':packet['input_manifest'],'input_packet_ref':sha(resources.bounded_canonical(wire,code='CONTEXT_LIMIT')),
          'prompt_ref':sha(instructions.encode()),'context_budget':budget,
          'resource_policy_revision':policy.get('resource_policy_revision','pmrs.resources/1'),
          'repair_limits':deepcopy(policy.get('repair_limits',{'FORMAT':1,'TRANSPORT':1})),
          'language_policy':snapshot.get('language_policy',{'research':'en','reports':'en','interaction':'zh-CN'}),
          'model_policy':model,'model_policy_resolution':resolved,'permission_manifest':permission,'budget_grant':candidate['budget_grant_id'],
          'retry_grant':c['retry_grant_id'],'purpose_key':candidate['purpose_key'],
          'responsibility_key':candidate['responsibility_key'],'attempt_group_key':candidate['attempt_group_key'],
          'attempt_key':attempt_key,'sample_slot':sample_slot,'input_fingerprint':candidate['input_fingerprint'],
          'response_contract_digest':identity(response_contract),'entry_basis':basis,
          'required_assurance':deepcopy(c.get('required_assurance',basis.get('consumer_requirement'))),
          'input_manifest_hash':identity(packet['input_manifest']),'independent':independent,
          'excluded_verdicts':independent,'policy_digest':c.get('policy_digest'),
          'author_execution_event':c.get('author_execution_event'),
          'executor_contract':deepcopy(policy.get('executor_contract',{'executor':'disabled','sandbox':'required','environment_revision':'unconfigured'}))}
    if survey_context:task['survey_context']=survey_context
    if report_context:task['report_context']=report_context
    if discovery_scope:task['discovery_scope']=deepcopy(discovery_scope)
    if c.get('coverage_plan_id'):task['coverage_plan_id']=c['coverage_plan_id'];task['coverage_part_id']=c.get('coverage_part_id')
    # The actual executor supplies task.json as well as prompt and packet. Count
    # that complete metadata too; iterate the few self-describing integer widths
    # until the frozen ContextBudget is stable instead of omitting task overhead.
    for _ in range(8):
        complete=resources.bounded_canonical({'prompt':instructions,'packet':wire,'response_contract':response_contract,'task':task},code='CONTEXT_LIMIT')
        exact=token_preflight(complete,capacity,reserved_output_tokens=policy.get('reserved_output_tokens',4096),
            prompt_overhead_tokens=policy.get('prompt_overhead_tokens',0),safety_margin_tokens=policy.get('safety_margin_tokens',1024),additional_input_bytes=file_token_bound)
        if exact==task['context_budget']:break
        task['context_budget']=exact
    else:require(False,'CONTEXT_LIMIT','Could not freeze a stable complete-request token budget')
    store.blob(resources.bounded_canonical(wire,code='CONTEXT_LIMIT'));store.blob(instructions.encode())
    return task

def load(store,task_id):
    snapshot=store.read_snapshot();require(task_id in snapshot.get('tasks',{}),'TASK_UNKNOWN',task_id)
    task=deepcopy(snapshot['tasks'][task_id])
    packet=store.read_blob(task['input_packet_ref']);store.read_blob(task['prompt_ref'])
    require(identity(__import__('json').loads(packet)['input_manifest'])==task['input_manifest_hash'],'ORIGINAL_BYTES_MISMATCH','Frozen input manifest changed')
    return task


def capture(store,task_id,raw,*,execution_id=None,usage=None):
    from .execution import capture as capture_request
    task=load(store,task_id)
    return capture_request(store,task['request_id'],raw,execution_id=execution_id,usage=usage)
