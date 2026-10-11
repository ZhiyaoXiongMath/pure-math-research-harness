"""Freeze exact native tasks and bytes; all dispatches use the shared registry."""
from copy import deepcopy
import json
from .util import canonical,identity,require,sha
from . import resources
from .version import TASK_SCHEMA,RESPONSE_SCHEMA
from .workflows.registry import spec,prompt,INDEPENDENT,validate_assignment

DEFAULT_MODEL={'model':'gpt-6-astra','reasoning_effort':'xhigh','service_tier':'default'}
INPUT_BOOTSTRAP='Read prompt.md, task.json and packet.json. Read every exact frozen material file referenced by this request; do not treat a hash or path as its content. Perform only this request and return the complete JSON contract.\n'

MODEL_INPUT_REVISION='pmrs.task-input/5'
MODEL_INPUT_REVISIONS={'pmrs.task-input/1','pmrs.task-input/2','pmrs.task-input/3','pmrs.task-input/4',MODEL_INPUT_REVISION}

def input_bootstrap(task):
    if task.get('actor_kind')=='MAIN' and task.get('model_input_revision')==MODEL_INPUT_REVISION:
        return ('Read prompt.md, task.json and packet.json. Follow main_material_delivery for initial full scope reads '
            'and exact historical material retrieval in this persistent native session. A path/hash is not content. '
            'Perform this request and return the complete JSON contract.\n')
    return INPUT_BOOTSTRAP

def model_task_payload(task):
    """Actual task.json view; native immutable host guards stay in the store.

    packet.json owns material/record/source manifests. prompt.md owns the
    authoring schema. Do not serialize another copy of either into task.json.
    Legacy frozen tasks retain their exact original representation.
    """
    if task.get('model_input_revision') not in MODEL_INPUT_REVISIONS:
        return deepcopy(task)
    fields=('schema','task_id','request_id','stage_id','role','actor_kind',
            'work_purpose','target_refs','obligation_bindings','scope','required_assurance','entry_basis',
            'discovery_scope','executor_contract','communication_contract',
            'initial_manifest_hash','permission_manifest',
            'language_policy','independent','excluded_verdicts','round_number','method_manual','guidance_context',
            'survey_context','coverage_plan_id','coverage_part_id','model_input_revision','main_material_delivery')
    result={key:deepcopy(task[key]) for key in fields if key in task}
    executor=result.get('executor_contract',{})
    # Capacity and client-profile evidence are HOST admission facts.  Verified
    # scientific tool capabilities and execution boundaries remain visible.
    executor.pop('client_input_evidence',None)
    basis=result.get('entry_basis',{})
    basis.pop('autoflow',None)
    if isinstance(basis.get('research_plan'),dict):
        basis['research_plan']={key:value for key,value in basis['research_plan'].items()
            if key in {'plan_id','branch_key','plan_intent'}}
    if 'consumer_requirement' in basis:basis['consumer_requirement']='task.json:required_assurance'
    result['material_manifest']='packet.json:material_refs,records,sources,source_excerpts'
    result['response_contract']='prompt.md:OUTPUT_CONTRACT'
    if task.get('strategy_context'):result['strategy_context']='packet.json:strategy_context'
    if task.get('report_context'):result['report_context']='packet.json:report_context'
    if task.get('model_input_revision') in {'pmrs.task-input/2','pmrs.task-input/3','pmrs.task-input/4',MODEL_INPUT_REVISION} and task.get('actor_kind')=='MAIN':
        # The full handbook and source mapping occur once in the packet.
        # Keep its exact identity here; this does not replace reading its body.
        method=result.get('method_manual',{})
        result['method_manual']={key:deepcopy(method[key]) for key in
            ('version','workflow_kind','body_sha256','blob_ref') if key in method}
        result['method_manual']['complete_manual']='packet.json:strategy_context.method_manual'
    return result

def model_packet_payload(packet):
    """Actual packet.json view. Exact scientific content is never summarized."""
    if packet.get('model_input_revision') not in MODEL_INPUT_REVISIONS:return deepcopy(packet)
    from .input_plans import model_view
    view=deepcopy(packet)
    for key in ('read_set','input_manifest','input_manifest_hash','bytes','independent','excluded_verdicts','roots'):
        view.pop(key,None)
    if view.get('input_plan'):view['input_plan']=model_view(view['input_plan'])
    for row in view.get('material_refs',{}).values():
        # The map key is the identical digest; records/sources map each use.
        row.pop('sha256',None);row.pop('uses',None)
    if packet.get('model_input_revision') in {'pmrs.task-input/2','pmrs.task-input/3','pmrs.task-input/4',MODEL_INPUT_REVISION} and view.get('strategy_context'):
        # MAIN already receives every selected scientific body in the exact
        # material files and all original guidance in research_memory. Do not
        # copy their first 1200 characters and the same human words again in a
        # navigation brief. Old /1 packets retain their original representation.
        brief=view['task_brief'];navigation=brief['exact_material_navigation']
        brief['exact_material_navigation']={
            'record_refs':[row['record_ref'] for row in navigation],
            'read_from':'packet.json:records and material_refs; read each complete exact body. This index contains no scientific text and grants no read qualification.'}
        guidance=brief['effective_guidance']
        brief['effective_guidance']={
            'version':guidance['version'],
            'original_direction_ids':[row['direction_id'] for row in guidance['original_directions']],
            'complete_original_words':'packet.json:strategy_context.research_memory.effective_guidance.original_directions',
            'filtered_reason':guidance['filtered_reason']}
        brief['exact_sources']={
            'source_refs':[row['source_ref'] for row in brief['exact_sources']],
            'read_from':'packet.json:sources, input_plan.source_selections and material_refs; preserve exact source coverage and read the supplied original files.'}
        if packet.get('model_input_revision')==MODEL_INPUT_REVISION:
            brief['exact_material_navigation']['read_from']='packet.json:records and material_refs. Follow main_material_delivery; retrieve complete bodies and their dependencies before using scientific claims. This index grants no read qualification.'
    if packet.get('model_input_revision') in {'pmrs.task-input/3','pmrs.task-input/4',MODEL_INPUT_REVISION} and view.get('strategy_context'):
        from .main_input_tables import encode
        view=encode(view,packed=packet.get('model_input_revision') in {'pmrs.task-input/4',MODEL_INPUT_REVISION})
    return view

def model_authoring_payload(authoring):
    """One exact authoring schema with pointers to already supplied bindings.

    This is only the prompt representation.  Admission/repair continue using
    the full authoring API and the native task/packet.  No reference, scope,
    imposed support or write guard is reconstructed or relaxed here.
    """
    view=deepcopy(authoring)
    if view.get('knowledge_change_schema')==view.get('response_schema'):
        view.pop('knowledge_change_schema')
    bindings=view.get('binding_table')
    if bindings is not None:
        view['binding_table']={
            'obligation_bindings':'task.json:obligation_bindings',
            'required_assurance':'task.json:required_assurance',
            'records':'packet.json:records; map keys are native refs, with exact kind and body_sha256',
            'sources':'packet.json:sources; map keys are native refs, with exact blob_hash',
            'required_support_refs':{row['ref']:row['required_support_refs'] for row in bindings.get('records',[])
                                     if row.get('required_support_refs')},
            'source_uses':deepcopy(bindings.get('source_uses',[])),
            'write_guards':deepcopy(bindings.get('write_guards',[]))}
    return view

def material_references(store,packet,report_context=None):
    """One small reference per exact content identity; never another body copy."""
    from .util import safe_path
    refs={}
    def add(digest,use,media_type):
        if digest not in refs:
            size=resources.blob_info(store,digest)['bytes']
            refs[digest]={'sha256':digest,'bytes':size,'path':'materials/'+digest+'.bin',
                          'media_type':media_type,'uses':[]}
        row=refs[digest]
        if media_type=='image/png':row['media_type']=media_type
        elif row['media_type']=='application/octet-stream':row['media_type']=media_type
        if use not in row['uses']:row['uses'].append(use)
    for ref,row in packet['records'].items():
        if row['body_sha256'] in packet['bodies']:add(row['body_sha256'],'record:'+ref,'text/plain')
    for digest in packet['bodies']:add(digest,'exact-locator-material','text/plain')
    for ref,row in packet['sources'].items():
        if row['blob_hash'] in packet['source_bodies']:add(row['blob_hash'],'source:'+ref,row.get('media_type','application/octet-stream'))
    for digest,raw in packet.get('source_excerpt_bodies',{}).items():
        require(store.blob(raw)==digest,'ORIGINAL_BYTES_MISMATCH','Source excerpt bytes changed before materialization')
        add(digest,'exact-source-excerpt','text/plain')
    for ref,row in packet.get('partial_target_bodies',{}).items():
        for segment in row['segments']:
            digest=store.blob(segment.pop('text').encode('utf-8')) if 'text' in segment else segment['material_sha256']
            segment['material_sha256']=digest;add(digest,'declared-target-slice:'+ref,'text/plain')
    for name,digest in (report_context or {}).get('files',{}).items():
        require('/' not in name and '\\' not in name and name not in {'.','..'},'PATH_INVALID','Report material needs a basename')
        media='image/png' if name.endswith('.png') else 'text/plain' if name.endswith(('.txt','.tex','.json')) else 'application/octet-stream'
        add(digest,'report:'+name,media)
    for digest,row in refs.items():
        suffix={
            'application/pdf':'.pdf','image/png':'.png','image/jpeg':'.jpg',
            'image/webp':'.webp','image/gif':'.gif'
        }.get(row['media_type'],'.txt' if row['media_type'].startswith('text/') else '.bin')
        row['path']='materials/'+digest+suffix
        safe_path(store.root,row['path']);row['uses'].sort()
    return dict(sorted(refs.items()))


def material_input_bound(task,packet):
    """Explain actual separate file accounting, including legacy report files.

    UTF8_BYTES is the existing conservative text method, not an exact tokenizer.
    Binary/image files retain the prior base64-size allowance; that allowance
    is disclosed as a representation estimate, not a measured vision token cost.
    """
    refs=packet.get('material_refs') if packet.get('input_representation')=='BLOB_REFERENCES_V1' else None
    if refs is None:
        refs={str(i):row for i,row in enumerate(packet.get('report_files',{}).values())}
    initial=None
    if task.get('actor_kind')=='MAIN' and task.get('model_input_revision')==MODEL_INPUT_REVISION:
        from .main_materials import initial_hashes
        initial=initial_hashes(task,packet)
    text_bytes=binary_bytes=image_bytes=allowance=all_allowance=0
    for digest,row in refs.items():
        size=row['bytes'];require(type(size) is int and size>=0,'CONTEXT_LIMIT','Invalid frozen material size')
        media=row.get('media_type','application/octet-stream')
        if media.startswith('text/'):
            text_bytes+=size;cost=size
        else:
            if media.startswith('image/'):image_bytes+=size
            else:binary_bytes+=size
            cost=4*((size+2)//3)
        all_allowance+=cost
        if initial is None or digest in initial:allowance+=cost
    details={'material_text_bytes':text_bytes,'material_binary_bytes':binary_bytes,
        'image_file_bytes':image_bytes,'separate_material_input_bound':allowance,
        'material_count':len(refs),'file_accounting':'UNIQUE_FROZEN_FILES' if packet.get('input_representation')=='BLOB_REFERENCES_V1' else 'LEGACY_SEPARATE_FILES',
        'image_accounting':'BASE64_SIZE_ALLOWANCE_NOT_EXACT_VISION_TOKENS'}
    if initial is not None:
        details.update(file_accounting='NATIVE_MAIN_INITIAL_SCOPE_FILES_PLUS_EXACT_DEMAND_READ_ARCHIVE',
            all_material_input_byte_bound=all_allowance,initial_material_count=len(initial),
            deferred_material_count=len(refs)-len(initial),deferred_material_byte_bound=all_allowance-allowance,
            admission_scope='Initial metadata, complete method/guidance/checkpoint and original scope sources, plus existing dynamic/tool/output reserves. Later historical reads are native session activity, not a simultaneous preload.',
            later_reads='Full exact files remain supplied. MAIN chooses reads and must verify scientific dependencies; native context management and actual usage apply. No new internal token quota.')
    return allowance,details


def request_budget(task,prompt,packet,capacity,*,reserved_output_tokens,prompt_overhead_tokens=0,safety_margin_tokens=0):
    """Count the metadata actually read plus the actual separately read files."""
    from .context import token_preflight
    allowance,details=material_input_bound(task,packet)
    # These are the three actual input files. The response schema is already
    # in prompt.md, so do not manufacture another transmitted schema copy.
    model_packet=model_packet_payload(packet)
    serialized=resources.bounded_canonical(model_task_payload(task),code='CONTEXT_LIMIT')+prompt.encode()+resources.bounded_canonical(model_packet,code='CONTEXT_LIMIT')+input_bootstrap(task).encode()
    packed=model_packet.get('metadata_tables',{}).get('packed_metadata')
    if packed:
        details.update(metadata_transport_encoding=packed['encoding'],packed_metadata_decoded_bytes=packed['decoded_bytes'],
            metadata_count_scope='Exact frozen transport bytes; later native file/tool reads and compaction remain native-session activity, not a claim of tokenizer-exact lifetime context size.')
    # MCP initialization is additional model input, even though it is not a
    # fourth workspace file. Freeze the exact registered schema/instructions.
    tool_bytes=0;dynamic_reserve=0;trajectory_reserve=0;client_covers_tools=False
    client_evidence=task.get('executor_contract',{}).get('client_input_evidence',{})
    if client_evidence:
        baseline=client_evidence.get('non_task_input_bytes')
        require(type(baseline) is int and baseline>=0 and prompt_overhead_tokens>=baseline,
                'CONTEXT_LIMIT','Frozen client input overhead is not completely reserved')
    if task.get('communication_contract'):
        from . import task_tools
        definitions=task_tools.tool_definitions(actor_kind=task.get('actor_kind'))
        tools_wire=canonical({'tools':definitions,'instructions':task_tools.INSTRUCTIONS})
        expected=task.get('tool_schema_hash')
        require(expected is None or expected==sha(tools_wire),'ORIGINAL_BYTES_MISMATCH','Task tool schema differs from the frozen contract')
        tool_bytes=len(tools_wire)
        client_covers_tools=(client_evidence.get('task_tools_included') is True and
            sha(tools_wire) in client_evidence.get('covered_tool_schema_hashes',[]))
        if not client_covers_tools:serialized+=tools_wire
        contract=task['communication_contract']
        dynamic_reserve=contract['max_dynamic_input_tokens'];trajectory_reserve=contract['tool_trajectory_reserve_tokens']
        require(all(type(n) is int and n>=0 for n in (dynamic_reserve,trajectory_reserve)),
                'CONTEXT_LIMIT','Dynamic input and tool trajectory reserves must be finite nonnegative bounds')
    require(len(serialized)<=resources.SERIALIZED_BYTES,'CONTEXT_LIMIT','Complete frozen metadata exceeds 64 MiB serialization support.')
    details.update(serialized_metadata_and_prompt_bytes=len(serialized),prompt_bytes=len(prompt.encode()),bootstrap_bytes=len(input_bootstrap(task).encode()),
        output_reserve_tokens=reserved_output_tokens,safety_margin_tokens=safety_margin_tokens,
        client_input_overhead_tokens=prompt_overhead_tokens,client_overhead_includes_task_tools=client_covers_tools,
        **({'tool_schema_and_instructions_bytes':tool_bytes,'dynamic_input_reserve_tokens':dynamic_reserve,
            'tool_trajectory_reserve_tokens':trajectory_reserve} if task.get('communication_contract') else {}),
        counter='UTF8_BYTES_CONSERVATIVE_BOUND',output_reserve_enforcement='Frozen client/model policy; no smaller output cap assumed')
    from .util import PMRSError
    try:
        budget=token_preflight(serialized,capacity,reserved_output_tokens=reserved_output_tokens,
            prompt_overhead_tokens=prompt_overhead_tokens,safety_margin_tokens=safety_margin_tokens,
            additional_input_bytes=allowance+dynamic_reserve+trajectory_reserve)
    except PMRSError as error:
        if error.code!='CONTEXT_LIMIT':raise
        raise PMRSError('CONTEXT_LIMIT',str(error)+'; frozen input accounting '+canonical(details).decode()+
            '; select a smaller explicit source/coverage scope while retaining its necessary premises; model policy and output reserve are unchanged.') from error
    return budget,details

def freeze(store,snapshot,candidate,policy):
    with resources.reserve(store.root,owner="freeze-task",temporary_bytes=128*resources.MIB,memory_bytes=resources.MAX_PREPARATION_MEMORY,max_preparations=min(2,snapshot.get('max_workers',1))):
        return _freeze(store,snapshot,candidate,policy)

def _freeze(store,snapshot,candidate,policy):
    from .context import build_packet,token_preflight
    from . import input_plans
    from .survey import refresh_task_consumer
    c=refresh_task_consumer(snapshot,candidate['consumer']);o=snapshot['obligations'][candidate['obligation_id']];d=o['definition']
    resources.json_bytes({'consumer':c,'definition':d},resources.METADATA_BYTES,code='CONTEXT_LIMIT')
    from .workflow_instances import validate_discovery_scope
    discovery_scope=validate_discovery_scope(snapshot,snapshot['instances'][c['instance_id']])
    c=deepcopy(c)
    required_sources=list(dict.fromkeys(list(c.get('source_refs',()))+list(discovery_scope.values())))
    for source in c.get('survey_context',{}).get('source_details',{}).values():
        if source.get('text_source_ref'):required_sources.append(source['text_source_ref'])
    c['source_refs']=list(dict.fromkeys(required_sources))
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
    resolved=model_policy.resolve(stage['workflow_kind'],c['stage_id'],role,purpose,override=override,capabilities=capabilities,actor_kind=c.get('actor_kind'))
    require(resolved['call_model'],'NO_MODEL_OPERATION','Host and human controls never generate model requests')
    assignment=validate_assignment(c['stage_id'],d['type'],role,basis)
    independent=role in INDEPENDENT
    siblings=[t['task_id'] for t in snapshot.get('tasks',{}).values() if t['instance_id']==c['instance_id']
              and t.get('visit_id')==c.get('visit_id') and t['role']!=role]
    if not independent and not basis.get('analysis_route')=='COMPARATIVE':siblings=[]
    input_plan=input_plans.build(snapshot,o,c,blob_get=store.read_blob)
    roots=input_plan['roots'];required_sources=input_plan['required_source_refs']
    instance=snapshot['instances'][c['instance_id']]
    from .obligations import task_plan_context
    branch_context=input_plans.compact_context(task_plan_context(snapshot,c),input_plan)
    branch_isolated=c['stage_id']=='P7' and role in {'LEARN','DIRECT'} and bool(basis.get('research_plan') or basis.get('analysis_route')=='COMPARATIVE')
    if branch_isolated and basis.get('research_plan'):
        plan_id=basis['research_plan']['plan_id']
        allowed_dependencies={row['binding_ref'] for row in d['dependency_bindings']}
        siblings=[t['task_id'] for t in snapshot.get('tasks',{}).values()
            if t.get('entry_basis',{}).get('research_plan',{}).get('plan_id')==plan_id
            and not any(b['binding_id']==c['binding_id'] or b['obligation_id'] in allowed_dependencies for b in t['obligation_bindings'])]
    report_context=deepcopy(c.get('report_context'))
    if report_context and role=='REPORT_VISUAL':
        roots=[];required_sources=[]
    if c.get('coverage_part'):
        from .context import build_coverage_packet
        packet=build_coverage_packet(snapshot,c['coverage_part'],store.read_blob,independent=independent,
            required_source_refs=required_sources,sibling_tasks=siblings)
    else:
        packet=build_packet(snapshot,roots,store.read_blob,independent=independent or branch_isolated,
                            required_source_refs=required_sources,sibling_tasks=siblings,
                            budget_blob_hashes=(report_context or {}).get('files',{}).values(),
                            source_selections=input_plan['source_selections'] if not (report_context and role=='REPORT_VISUAL') else {})
    packet['input_plan']=input_plan
    packet['task_brief']=input_plans.task_brief(snapshot,o,c,input_plan,blob_get=store.read_blob,
        independent=independent or branch_isolated)
    if branch_context:packet['research_plan_context']=branch_context
    strategy_context=None
    if c.get('actor_kind')=='MAIN':
        from . import strategy
        strategy_context=strategy.task_context(store,snapshot,c)
        packet['strategy_context']=strategy_context
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
    generated['sections']['TARGET_CONTEXT_AND_SCOPE']='Keep task.json target_refs, scope, entry_basis and required_assurance exact.'
    survey_context=deepcopy(c.get('survey_context'))
    if survey_context:
        from .survey import response_contract
        generated['sections']['SURVEY_FROZEN_CONTEXT']='Use the complete exact survey_context in task.json.'
        generated['sections']['SURVEY_RESULT_CONTRACT']=canonical(response_contract(role)).decode()
    if branch_context:generated['sections']['RESEARCH_PLAN_CONTEXT']='packet.json research_plan_context retains actual attempts and gaps. Completion dependencies are not scientific premises or proof certification.'
    generated['sections']['TASK_BRIEF_AND_HANDOFF']='Read packet.json task_brief alongside the complete exact material files. In the normal attempt_account, give reusable completed work, evidence and open gaps, failed attempts and blockers, and suggested next steps for MAIN. Suggestions do not authorize another stage. For an independent task, no strategic summary or previous verdict is scientific input.'
    if discovery_scope:generated['sections']['EXACT_DISCOVERY_SCOPE']='Use the exact task.json discovery_scope original source identities.'
    generated['sections']['ACTUAL_INPUT_MANIFEST']='packet.json binds exact records, sources and material_refs. source_excerpts declares supplied ranges; metadata is not full-text reading.'
    require(sum(len(value.encode()) for value in generated['sections'].values())<=resources.METADATA_BYTES,'CONTEXT_LIMIT','Complete instructions exceed the task metadata budget.')
    # A stage's generated criterion can already contain its full duty verbatim.
    # Keep custom criteria exact and remove only proven duplicate instructions.
    sections=generated['sections']
    if sections.get('SCIENTIFIC_WORK') and sections['SCIENTIFIC_WORK'] in criterion:sections.pop('SCIENTIFIC_WORK')
    from .research_prompts import DUTIES
    original_result=DUTIES[c['stage_id']][2]
    if original_result in criterion and sections.get('RESULT_AND_DOWNSTREAM_DUTY','').startswith(original_result):
        sections['RESULT_AND_DOWNSTREAM_DUTY']=sections['RESULT_AND_DOWNSTREAM_DUTY'][len(original_result):].lstrip()
    sections.pop('ROLE_DUTY_AND_BOUNDARIES',None)  # Exact stage/role already in task.json.
    sections['EXPECTED_KNOWLEDGE_CHANGE']='Zero records is valid only with an account of the actual attempt.'
    instructions='\n\n'.join(k+'\n'+v for k,v in sections.items() if v)
    instructions+='\n\nReturn only OUTPUT_CONTRACT JSON.'
    if c.get('actor_kind')=='MAIN':
        instructions+=' Codex native internal delegation is freely authorized. Stage CLI dispatch uses the product MAIN tools; never edit native state directly.'
        instructions+='\n\nMAIN METADATA TABLES\nRead metadata_tables.instructions and metadata_tables.packed_metadata.instructions BEFORE interpreting packet.json. The exact metadata container uses Python standard library base64.b64decode and zlib.decompress: verify its decoded_bytes and SHA256, parse the JSON list, and replace each indicated path placeholder with its exact value. Then a {"$s":i} value is strings[i]; a {"$r":[i,v0,...]} value maps fields[i] to recursively interpreted values v0,... . Verify decoded_packet_sha256 after removing metadata_tables and decoding records, relations and strategy_context (leave method_manual unchanged). Read the resulting complete original metadata and all original frozen material files; do not infer their content from a path/hash. The entire method handbook, current guidance/checkpoint prose and control facts remain directly present. Packaging changes no scientific text, qualification or native reference. Use ordinary fully resolved native objects in tools and OUTPUT_CONTRACT; never return packed_metadata or $s/$r input markers.'
    else:instructions+=' No independent model calls or sibling-session reads; use authorized request-scoped communication.'
    model={k:resolved[k] for k in ('model','reasoning_effort','service_tier')}
    permission={'allowed_payload_kinds':assignment['role_contract']['payload_kinds'],
                'allowed_record_kinds':stage['allowed_scientific_kinds'],
                'allowed_operations':['NEW','REVISE','LINK','WITHDRAW_SUPPORT']}
    response_contract={'schema':RESPONSE_SCHEMA,'permission_manifest':permission,'stage_spec_digest':stage['digest']}
    # New packets bind each immutable body once. Actual model-readable copies
    # are prepared from these references; old embedded packets remain unchanged.
    material_refs=material_references(store,packet,report_context)
    wire={k:v for k,v in packet.items() if k not in {'bodies','source_bodies','source_excerpt_bodies'}}
    wire['material_refs']=material_refs
    wire['input_representation']='BLOB_REFERENCES_V1'
    wire['model_input_revision']=MODEL_INPUT_REVISION
    if c.get('actor_kind')=='MAIN':
        from .main_materials import policy as material_policy,INSTRUCTIONS as material_instructions
        wire['main_material_delivery']=material_policy(wire,d['target_refs'])
        instructions=instructions.replace('Read the resulting complete original metadata and all original frozen material files;',
            'Read the resulting complete original metadata and retrieve scientific originals according to main_material_delivery;')
    if report_context:
        require(role==report_context['role'],'REPORT_SCOPE_INVALID','Frozen report role differs')
        wire['report_files']={name:deepcopy(material_refs[digest]) for name,digest in report_context['files'].items()}
        wire['report_context']=report_context
        from .reports import authoring_rules
        instructions+='\n\n'+authoring_rules(report_context)
    instructions+='\n\nFROZEN MATERIAL ACCESS\n'+(material_instructions if c.get('actor_kind')=='MAIN' else 'Read every material file; metadata is not its text.')+' material_refs hash keys bind records/sources to exact files. Preserve necessary premises and unprovided boundaries. Report unreadable inputs. Inspect supplied images as images. PDF and other binary originals retain their native file extension; use available document-reading tools on those exact files, never decode binary as prose. Knowledge text tools do not return binary originals. A supplied original is not evidence that it was successfully read.'
    resources.json_bytes(wire,resources.METADATA_BYTES,code='CONTEXT_LIMIT')
    unique_bytes=sum(row['bytes'] for row in material_refs.values())
    require(unique_bytes+resources.json_bytes(wire,resources.METADATA_BYTES,code='CONTEXT_LIMIT')<=resources.CONTEXT_BYTES,
            'CONTEXT_LIMIT','Unique required materials plus frozen metadata exceed 32 MiB; select a smaller explicit scope without omitting necessary premises.')
    capacity=policy.get('capacity',snapshot.get('model_capacities',{}).get(model['model']))
    require(capacity is not None,'CONTEXT_LIMIT','No verified model capacity configured for the requested model')
    require(capacity.get('model_id')==model['model'],'CONTEXT_LIMIT','Model capacity must match the actual frozen model')
    require(snapshot.get('synthetic_test_only') or capacity.get('capacity_source')!='SYNTHETIC_TEST_ONLY',
            'CONTEXT_LIMIT','Synthetic capacity cannot authorize a real model request')
    prior_slots=[r['sample_slot'] for r in snapshot.get('requests',{}).values() if r.get('attempt_group_key')==candidate['attempt_group_key']]
    sample_slot=max(prior_slots,default=0)+1
    attempt_key=identity({'group':candidate['attempt_group_key'],'sample_slot':sample_slot},'ATTEMPT-')
    tid=identity({'attempt':attempt_key,'contract':stage['digest'],'instance':c['instance_id'],'mission':c['mission_id']},'TASK-')
    task={'schema':TASK_SCHEMA,'model_input_revision':MODEL_INPUT_REVISION,'task_id':tid,'request_id':identity({'task':tid},'REQUEST-'),
          'instance_id':c['instance_id'],'mission_id':c['mission_id'],'visit_id':c.get('visit_id'),
          'stage_id':c['stage_id'],'stage_spec_digest':stage['digest'],'role':role,
          'obligation_bindings':[{'binding_id':c['binding_id'],'obligation_id':d['obligation_id'],'expected_definition_revision':d['definition_revision']}],
          'target_refs':d['target_refs'],'knowledge_commit':snapshot.get('knowledge_commit'),
          'read_set':packet['read_set'],'query_guards':c.get('query_guards',[]),'write_guards':c.get('write_guards',[]),
          'input_manifest':packet['input_manifest'],'input_packet_ref':sha(resources.bounded_canonical(wire,code='CONTEXT_LIMIT')),
          'model_packet_ref':sha(resources.bounded_canonical(model_packet_payload(wire),code='CONTEXT_LIMIT')),
          'prompt_ref':sha(instructions.encode()),'context_budget':{},'context_budget_details':{},
          'input_representation':'BLOB_REFERENCES_V1','material_refs':deepcopy(material_refs),
          'resource_policy_revision':policy.get('resource_policy_revision','pmrs.resources/1'),
          'repair_limits':deepcopy(policy.get('repair_limits',{'FORMAT':1,'TRANSPORT':1})),
          'language_policy':snapshot.get('language_policy',{'research':'en','reports':'en','interaction':'zh-CN'}),
          'model_policy':model,'model_policy_resolution':resolved,'permission_manifest':permission,'budget_grant':candidate['budget_grant_id'],
          'retry_grant':c['retry_grant_id'],'purpose_key':candidate['purpose_key'],
          'responsibility_key':candidate['responsibility_key'],'attempt_group_key':candidate['attempt_group_key'],
          'attempt_key':attempt_key,'sample_slot':sample_slot,'input_fingerprint':candidate['input_fingerprint'],
          'response_contract_digest':identity(response_contract),'response_contract_revision':'pmrs.response-authoring/3',
          'entry_basis':basis,'scope':deepcopy(c.get('scope',{})),
          'required_assurance':deepcopy(c.get('required_assurance',basis.get('consumer_requirement'))),
          'input_manifest_hash':identity(packet['input_manifest']),'independent':independent,
          'excluded_verdicts':independent,'policy_digest':c.get('policy_digest'),
          'author_execution_event':c.get('author_execution_event'),
          'executor_contract':deepcopy(policy.get('executor_contract',{'executor':'disabled','sandbox':'required','environment_revision':'unconfigured'}))}
    task['input_plan_hash']=input_plan['plan_hash']
    if wire.get('main_material_delivery'):
        task['main_material_delivery']=deepcopy(wire['main_material_delivery'])
    guidance=packet['task_brief']['effective_guidance']
    task['guidance_context']={'version':guidance['version'],
        'direction_ids':[d['direction_id'] for d in guidance['original_directions']],
        'independence_filter':guidance['filtered_reason'],'delivery_basis':'FROZEN_INPUT'}
    if packet.get('source_excerpts'):task['source_excerpts']=deepcopy(packet['source_excerpts'])
    for field in ('actor_kind','strategy_ref','strategy_revision','strategy_proposal_ref','priority','round_number','allow_independence_loss'):
        if c.get(field) is not None:task[field]=deepcopy(c[field])
    task['work_purpose']=purpose
    task.setdefault('round_number',instance.get('run_control',{}).get('round_number',1))
    if strategy_context:
        task['assignment_strategy_revision']=task.get('strategy_revision')
        task['strategy_revision']=strategy_context['revision']
        task['strategy_context']={key:deepcopy(strategy_context[key]) for key in
            ('schema','strategy_id','revision','frontier_digest','pending_trigger_refs','direction_ids',
             'main_request_purpose','covered_binding_ids','run_control') if key in strategy_context}
        method=strategy_context['method_manual']
        task['method_manual']={k:deepcopy(method[k]) for k in ('version','workflow_kind','body_sha256','source_mapping','policy_source')}
        task['method_manual']['blob_ref']=store.blob(method['body'].encode())
        memory=strategy_context['research_memory'];guidance=memory['effective_guidance']
        task['research_memory_context']={'guidance_version':guidance['version'],
            'guidance_direction_ids':[d['direction_id'] for d in guidance['original_directions']],
            'pending_audit_event_ids':[e['event_id'] for e in memory['pending_audit_events']],
            'latest_checkpoint_id':(memory.get('latest_checkpoint') or {}).get('checkpoint_id'),
            'known_request_ids':[r['request_id'] for r in memory['incremental_requests']],
            'request_versions':{r['request_id']:identity([r['execution_state'],r['acceptance_state'],r.get('capture_ref')])
                for r in snapshot['requests'].values() if r.get('instance_id')==c['instance_id']}}
        from . import strategy
        instructions+='\n\n'+'\n\n'.join(key+'\n'+value for key,value in strategy.prompt_sections(task).items())
    if survey_context:task['survey_context']=survey_context
    if report_context:
        task['report_context']=report_context
        if report_context.get('budget_domain'):task['budget_domain']=report_context['budget_domain']
    if discovery_scope:task['discovery_scope']=deepcopy(discovery_scope)
    if c.get('coverage_plan_id'):task['coverage_plan_id']=c['coverage_plan_id'];task['coverage_part_id']=c.get('coverage_part_id')
    if task.get('required_assurance'):
        from .assurance import normalize_scope
        req=task['required_assurance'];req['required_scope']=normalize_scope(req['required_scope'],snapshot,store.read_blob)
        for slot in req['review_slots']:slot['required_scope']=normalize_scope(slot['required_scope'],snapshot,store.read_blob)
        from .contracts import digest
        task['policy_digest']=digest(req)
    if task['executor_contract'].get('executor')=='codex' and not snapshot.get('synthetic_test_only'):
        require(task['executor_contract'].get('client_input_evidence'),'CONTEXT_LIMIT',
                'New Codex task requires measured frozen client/system/tool/environment input overhead')
    prompt_overhead=policy.get('prompt_overhead_tokens',0)
    if task['executor_contract'].get('client_input_evidence'):
        from .codex_client import derive_task_input_evidence
        derived=derive_task_input_evidence(policy,store.root,tid,task.get('actor_kind'))
        if derived:
            task['executor_contract']['client_input_evidence']=derived['client_input_evidence']
            prompt_overhead=derived['prompt_overhead_tokens']
    if policy.get('executor_contract',{}).get('executor')=='codex' or 'communication' in policy:
        from . import communication,task_tools
        full_material=(packet.get('complete') is True and not packet.get('partial_target_bodies')
                       and not any(row.get('body_coverage') for row in packet['input_manifest']))
        task['communication_contract']=communication.frozen_contract(snapshot,c,policy,
                                                                    initial_material_complete=full_material)
        task['initial_manifest_hash']=task['input_manifest_hash']
        task['tool_schema_hash']=sha(canonical({'tools':task_tools.tool_definitions(actor_kind=task.get('actor_kind')),
                                               'instructions':task_tools.INSTRUCTIONS}))
        instructions+='\n\nTASK COMMUNICATION\nUse the real request-scoped tools to read/reply and preserve source, premise and isolation boundaries. Return message_dispositions with actual delivery identities.'
        if task.get('actor_kind')!='MAIN':instructions+=' Respect the frozen communication tool allowance.'
    from .contracts import authoring_contract
    authoring=model_authoring_payload(authoring_contract(task,snapshot))
    instructions+='\n\nOUTPUT_CONTRACT\n'+canonical(authoring).decode()
    instructions+='\n\nEXECUTOR CAPABILITIES\nOnly task.json executor_contract.capabilities verifies tool availability. Missing optional tools are environment limits, not mathematical failure. Do not install packages or change the frozen environment.'
    task['prompt_ref']=sha(instructions.encode())
    # The actual executor supplies task.json as well as prompt and packet. Count
    # that complete metadata too; iterate the few self-describing integer widths
    # until the frozen ContextBudget is stable instead of omitting task overhead.
    for _ in range(8):
        exact,details=request_budget(task,instructions,wire,capacity,
            reserved_output_tokens=policy.get('reserved_output_tokens',4096),
            prompt_overhead_tokens=prompt_overhead,safety_margin_tokens=policy.get('safety_margin_tokens',1024))
        if exact==task['context_budget'] and details==task['context_budget_details']:break
        task['context_budget']=exact;task['context_budget_details']=details
    else:require(False,'CONTEXT_LIMIT','Could not freeze a stable complete-request token budget')
    store.blob(resources.bounded_canonical(wire,code='CONTEXT_LIMIT'))
    store.blob(resources.bounded_canonical(model_packet_payload(wire),code='CONTEXT_LIMIT'));store.blob(instructions.encode())
    return task

def load(store,task_id):
    snapshot=store.read_snapshot();require(task_id in snapshot.get('tasks',{}),'TASK_UNKNOWN',task_id)
    task=deepcopy(snapshot['tasks'][task_id])
    packet=json.loads(store.read_blob(task['input_packet_ref']));store.read_blob(task['prompt_ref'])
    if task.get('model_packet_ref'):
        require(store.read_blob(task['model_packet_ref'])==canonical(model_packet_payload(packet)),
                'ORIGINAL_BYTES_MISMATCH','Frozen model packet view differs from the complete native packet')
    require(identity(packet['input_manifest'])==task['input_manifest_hash'],'ORIGINAL_BYTES_MISMATCH','Frozen input manifest changed')
    if task.get('input_representation')=='BLOB_REFERENCES_V1':
        require(packet.get('material_refs')==task.get('material_refs') and packet.get('input_representation')=='BLOB_REFERENCES_V1',
                'ORIGINAL_BYTES_MISMATCH','Frozen material reference manifest differs')
    return task


def capture(store,task_id,raw,*,execution_id=None,usage=None):
    from .execution import capture as capture_request
    task=load(store,task_id)
    return capture_request(store,task['request_id'],raw,execution_id=execution_id,usage=usage)
