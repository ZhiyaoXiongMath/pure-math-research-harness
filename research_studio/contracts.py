"""Public final contracts and bounded, deterministic parsing.

Scientific identities deliberately exclude producers and mutable projections.
This module is the runtime's single field/enum registry; no legacy aliases.
"""
from __future__ import annotations
import json
import re
from .util import PMRSError, require, canonical, sha

from .version import SCHEMA_VERSION as PROJECT_SCHEMA, TASK_SCHEMA, RESPONSE_SCHEMA, COMMIT_SCHEMA
RECORD_SCHEMA = 'pmrs.knowledge-record/1'
CHANGE_SCHEMA = 'pmrs.knowledge-change/1'
KINDS = frozenset(('Context','Statement','Argument','Example','SourceEvidence','Assessment'))
RECORD_FIELDS = frozenset(('schema','kind','context_refs','body_sha256','data'))
LOCATOR_FIELDS = frozenset(('blob_hash','unit','start','end','quoted_sha256'))
DATA_FIELDS = {
 'Context': 'definitions objects assumptions quantifiers conventions parent_context_refs',
 'Statement': 'statement_locator scope_context_refs hypothesis_locators conclusion_locators quantifier_locators form representation source_binding',
 'Argument': 'conclusion_ref premise_bindings steps discharged_assumptions open_conditions witness_bindings mode mode_payload',
 'Example': 'target_refs construction_locator hypothesis_checks observations scope realization_argument_ref',
 'SourceEvidence': 'source_occurrence_refs locators evidence_type coverage reproducibility_refs',
 'Assessment': 'review_kind target_refs checked unchecked verdict findings scope_context_refs',
}
DATA_FIELDS = {k:frozenset(v.split()) for k,v in DATA_FIELDS.items()}
AUTHORING_REVISION = 'pmrs.response-authoring/3'
SCIENCE_PROJECTION_REVISION = 'pmrs.science-projection/1'
PREMISE_ENDPOINTS = {
 'DEFINITION': frozenset({'Context'}), 'CONTEXT_ASSUMPTION': frozenset({'Context','Statement'}),
 'SUPPORTED_STATEMENT': frozenset({'Statement'}), 'DERIVATION_COMPONENT': frozenset({'Argument'}),
 'CONDITIONAL_CANDIDATE': frozenset({'Statement'})}
KCS_OPTIONAL_FIELDS = frozenset({'strategy_proposal','message_dispositions'})
KCS_FIELDS = frozenset('schema task_id request_id base_knowledge_commit read_set_digest query_guard_digest write_guard_digest operations obligation_effects new_obligation_proposals work_outcome attempt_account claimed_change semantic_novelty'.split())
ENVELOPE_FIELDS = frozenset('schema task_id request_id payload_kind payload'.split())
SOURCE_USE_FIELDS = frozenset('source_ref locators usage_mode trust_boundary'.split())
SOURCE_MODES = frozenset('FULL_ARGUMENT STATEMENT_RELIANCE DECLARED_EXCERPT COMPUTATION_RESULT METHOD_INSPIRATION'.split())
PREMISE_FIELDS = frozenset('premise_ref kind context_ref scope_locator binding_mode support_ref assumption_locator'.split())
INFERENCE_FIELDS = frozenset('premise_refs conclusion_ref operator alternative_argument_refs additional_assumption_refs lifting_check compatibility_check'.split())
ASSURANCE_FIELDS = frozenset('purpose required_scope accepted_evidence_paths review_mode review_slots'.split())
SCOPE_FIELDS = frozenset('target_ref locators aspects'.split())
SLOT_FIELDS = frozenset('slot_id allowed_roles review_kind required_scope independence_required'.split())
CONTEXT_BUDGET_FIELDS = frozenset('model_id capacity_source capacity_revision context_window_tokens model_max_output_tokens reserved_output_tokens prompt_overhead_tokens safety_margin_tokens input_tokens token_count_method tokenizer_revision'.split())
OBLIGATION_TYPES = frozenset('ESTABLISH REFUTE APPLICABILITY REDUCE COMPATIBILITY VERIFY MATERIAL DISCRIMINATE CALIBRATE FORMULATE COMPARE INTEGRATE ACCOUNT REPORT CONTROL'.split())
OP_FIELDS = {
 'NEW': frozenset('op local_key kind context_refs body data'.split()),
 'REVISE': frozenset('op local_key object_id expected_parent new_record'.split()),
 'LINK': frozenset('op type source_ref target_ref scope_context_refs evidence_bindings assertion_state'.split()),
 'WITHDRAW_SUPPORT': frozenset('op support_id expected_qualification_head reason_code evidence_refs scope'.split()),
}
MAX_PAYLOAD = 16 * 1024 * 1024
MAX_BODY = 8 * 1024 * 1024
MAX_DEPTH = 32
MAX_INT = (1 << 63) - 1
LOCAL_KEY = re.compile(r'[A-Za-z][A-Za-z0-9_.-]{0,95}\Z')
HASH = re.compile(r'[0-9a-f]{64}\Z')

class ValidatedChange(dict):
    """A pure validation plan. Store revalidates raw/task under its live lock."""

def fields(value, expected, label='object'):
    require(isinstance(value,dict), 'RESPONSE_SCHEMA_INVALID', label+' must be an object')
    unknown=set(value)-set(expected)
    require(not unknown,'UNKNOWN_FIELD',label+': '+','.join(sorted(unknown)))
    require(set(value)==set(expected),'RESPONSE_SCHEMA_INVALID',label+' missing required fields')
    return value

def enum(value, allowed, label):
    require(isinstance(value,str) and value in allowed,'RESPONSE_SCHEMA_INVALID',label)
    return value

def sequence(value, label, maximum=100000):
    require(isinstance(value,list) and len(value)<=maximum,'RESPONSE_SCHEMA_INVALID',label)
    return value

def refs(value, label, *, nonempty=False, sorted_unique=False):
    sequence(value,label)
    require(all(isinstance(x,str) and x for x in value),'RESPONSE_SCHEMA_INVALID',label)
    require(not nonempty or bool(value),'RESPONSE_SCHEMA_INVALID',label+' cannot be empty')
    require(len(value)==len(set(value)),'RESPONSE_SCHEMA_INVALID',label+' has duplicates')
    if sorted_unique: require(value==sorted(value),'RESPONSE_SCHEMA_INVALID',label+' must be sorted')
    return value

def bounded_json(raw):
    require(isinstance(raw,(bytes,str)),'RESPONSE_SCHEMA_INVALID','JSON bytes required')
    data=raw.encode('utf-8') if isinstance(raw,str) else raw
    require(len(data)<=MAX_PAYLOAD,'PAYLOAD_LIMIT','JSON exceeds 16 MiB')
    def pairs(items):
        d={}
        for k,v in items:
            require(k not in d,'DUPLICATE_JSON_KEY',k);d[k]=v
        return d
    try:
        value=json.loads(data.decode('utf-8'),object_pairs_hook=pairs,
            parse_float=lambda x: (_ for _ in ()).throw(ValueError('Use decimal strings')),
            parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite number')))
    except PMRSError: raise
    except (ValueError,UnicodeError,RecursionError) as exc:
        raise PMRSError('RESPONSE_SCHEMA_INVALID',str(exc)) from exc
    validate_tree(value)
    return value

def validate_tree(value, depth=0):
    require(depth<=MAX_DEPTH,'PAYLOAD_LIMIT','JSON nesting exceeds 32')
    if isinstance(value,dict):
        require(all(isinstance(k,str) for k in value),'RESPONSE_SCHEMA_INVALID','String keys required')
        for v in value.values(): validate_tree(v,depth+1)
    elif isinstance(value,list):
        for v in value: validate_tree(v,depth+1)
    elif type(value) is int: require(abs(value)<=MAX_INT,'PAYLOAD_LIMIT','Integer out of range')
    else: require(value is None or type(value) in (str,bool),'RESPONSE_SCHEMA_INVALID','Unsupported JSON scalar')

def digest(value):
    validate_tree(value)
    return sha(canonical(value))

def scientific_identity(record):
    validate_tree(record)
    return 'KR-'+sha(RECORD_SCHEMA.encode()+b'\0'+canonical(record))

def inference_identity(argument_ref):
    return 'IB-'+sha(b'pmrs.inference-binding/1\0'+argument_ref.encode('utf-8'))

def registry():
    """Machine-readable contracts used in schemas, prompts and validation."""
    from .strategy import authoring_schema as strategy_schema
    return {'project_schema':PROJECT_SCHEMA,'record_schema':RECORD_SCHEMA,
      'task_schema':TASK_SCHEMA,'response_schema':RESPONSE_SCHEMA,'change_schema':CHANGE_SCHEMA,
      'knowledge_record':{'required':sorted(RECORD_FIELDS),'additionalProperties':False,
         'kinds':sorted(KINDS),'data_fields':{k:sorted(v) for k,v in DATA_FIELDS.items()}},
      'response_envelope':{'required':sorted(ENVELOPE_FIELDS),'additionalProperties':False},
      'knowledge_change':{'required':sorted(KCS_FIELDS),'operations':{k:sorted(v) for k,v in OP_FIELDS.items()},'additionalProperties':False},
      'survey_result':{'schema':'pmrs.survey-result/1','required':['schema','knowledge_change','action','data'],'additionalProperties':False,
         'role_actions':{'SEARCH_PLAN':'SEARCH_PLAN','SOURCE_READ':'READING','ORGANIZE':'ORGANIZE','RECONSTRUCT':'ORGANIZE','READINESS_REVIEW':'REVIEW','COVERAGE_REVIEW':'REVIEW'},
         'knowledge_change':'Same native task/request/read/query/write guards, operation validation, English body policy and captured-byte admission'},
      'response_authoring':authoring_contract(),
      'main_strategy_proposal':strategy_schema(),
      'consumer_assurance':{'required':sorted(ASSURANCE_FIELDS),'slots':sorted(SLOT_FIELDS),
         'paths':['MODEL_CAPTURE','HUMAN_ATTESTATION']},
      'context_budget':{'required':sorted(CONTEXT_BUDGET_FIELDS)},
      'limits':{'json_bytes':MAX_PAYLOAD,'body_bytes':MAX_BODY,'depth':MAX_DEPTH,'records':64,'relations':512,'obligation_effects':256}}


def authoring_contract(task=None, snapshot=None):
    """Complete model-write shapes, shared by new freezes and finite repairs.

    The admission validator remains authoritative for reference integrity,
    permissions and science. This schema describes JSON authoring; it never
    grants capabilities or labels candidate mathematics as qualified.
    """
    def obj(properties):
        return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}
    def arr(item):return {'type':'array','items':item}
    def choice(*values):return {'enum':list(values)}
    def ref(name):return {'$ref':'#/$defs/'+name}
    string={'type':'string','minLength':1};text={'type':'string','minLength':1,'description':'Nonempty English prose'}
    nullable={'anyOf':[string,{'type':'null'}]};refs=arr(string);locs=arr(ref('Locator'))
    defs={}
    defs['Locator']=obj({'blob_hash':{'type':'string','description':'Exact frozen SHA256, or body:<local_key> for a NEW/REVISE body'},
        'unit':choice('UTF8_BYTE','UNICODE_CODEPOINT'),'start':{'type':'integer','minimum':0},'end':{'type':'integer','minimum':1},
        'quoted_sha256':{'anyOf':[{'type':'string','pattern':'^[0-9a-f]{64}$'},{'type':'null'}],
            'description':'SHA256 of exact half-open UTF8 slice; null is allowed only with body:<local_key>, computed by host'}})
    defs['ContextItem']=obj({'key':string,'locator':ref('Locator')})
    defs['Context']=obj({**{k:arr(ref('ContextItem')) for k in ('definitions','objects','assumptions','quantifiers','conventions')},'parent_context_refs':refs})
    defs['SourceUse']=obj({'source_ref':string,'locators':locs,'usage_mode':choice(*sorted(SOURCE_MODES)),'trust_boundary':text})
    defs['Statement']=obj({'statement_locator':ref('Locator'),'scope_context_refs':refs,'hypothesis_locators':locs,'conclusion_locators':locs,
        'quantifier_locators':locs,'form':choice('PROPOSITION','QUESTION','CONJECTURE','CONDITIONAL','EQUIVALENCE','DICHOTOMY'),
        'representation':choice('AUTHORED','SOURCE_BOUND'),'source_binding':{'anyOf':[ref('SourceUse'),{'type':'null'}]}})
    defs['PremiseBinding']=obj({'premise_ref':string,'kind':choice('CONTEXT_ASSUMPTION','SUPPORTED_STATEMENT','DERIVATION_COMPONENT','DEFINITION','CONDITIONAL_CANDIDATE'),
        'context_ref':nullable,'scope_locator':{'anyOf':[ref('Locator'),{'type':'null'}]},'binding_mode':choice('PINNED','CURRENT'),
        'support_ref':nullable,'assumption_locator':{'anyOf':[ref('Locator'),{'type':'null'}]}})
    defs['ArgumentStep']=obj({'step_id':string,'locator':ref('Locator'),'premise_refs':refs})
    defs['OpenCondition']=obj({'condition_ref':nullable,'locator':ref('Locator')})
    defs['WitnessBinding']=obj({'variable':string,'context_ref':string,'locator':ref('Locator')})
    check={'anyOf':[obj({'status':choice('REQUIRED'),'obligation_ids':refs,'evidence_refs':refs}),
        obj({'status':choice('NOT_REQUIRED'),'reason_locator':ref('Locator'),'evidence_refs':refs})]}
    defs['InferenceSpec']=obj({'premise_refs':refs,'conclusion_ref':string,'operator':choice('AND','OR'),'alternative_argument_refs':refs,
        'additional_assumption_refs':refs,'lifting_check':check,'compatibility_check':check})
    defs['Applicability']=obj({'donor_refs':refs,'recipient_ref':string,'substitution_map':{'type':'object'},
        'hypothesis_discharge_refs':refs,'constant_dependency_locators':locs,'open_conditions':{'type':'array'}})
    defs['WitnessCompatibility']=obj({'target_ref':string,'component_argument_refs':refs,'context_refs':refs,'variable_mapping':{'type':'object'},
        'common_data_refs':refs,'quantifier_locators':locs,'evidence_refs':refs,'open_condition_refs':refs})
    defs['Comparison']=obj({'relation_type':choice('IMPLIES','EQUIVALENT_ON_SCOPE'),'from_statement_ref':string,'to_statement_ref':string,
        'direction_argument_refs':refs,'scope_context_refs':refs})
    mode_payload={'PROOF':obj({}),'REFUTATION':obj({}),'DERIVATION':obj({}),'REDUCTION':obj({'inference_spec':ref('InferenceSpec')}),
        'APPLICABILITY':ref('Applicability'),'COMPATIBILITY':obj({'witness_compatibility':ref('WitnessCompatibility')}),'COMPARISON':ref('Comparison')}
    argument_common={'conclusion_ref':string,'premise_bindings':arr(ref('PremiseBinding')),'steps':arr(ref('ArgumentStep')),
        'discharged_assumptions':locs,'open_conditions':arr(ref('OpenCondition')),'witness_bindings':arr(ref('WitnessBinding'))}
    # Factor the common fields once while retaining the exact closed shape
    # and each mode's payload validation. Every branch sees the same object.
    defs['Argument']={'allOf':[
        obj({**argument_common,'mode':choice(*mode_payload),'mode_payload':{}}),
        {'oneOf':[{'type':'object','properties':{'mode':choice(mode),'mode_payload':payload},
                    'required':['mode','mode_payload']} for mode,payload in mode_payload.items()]}]}
    defs['HypothesisCheck']=obj({'hypothesis_locator':ref('Locator'),'result':choice('SATISFIED','VIOLATED','UNKNOWN'),
        'evidence_refs':refs,'explanation_locator':ref('Locator')})
    defs['Observation']=obj({'locator':ref('Locator'),'evidence_refs':refs})
    defs['Example']=obj({'target_refs':refs,'construction_locator':ref('Locator'),'hypothesis_checks':arr(ref('HypothesisCheck')),
        'observations':arr(ref('Observation')),'scope':choice('ORIGINAL_TARGET','MODEL_CASE','BOUNDARY_TEST','NUMERICAL_PROBE'),'realization_argument_ref':nullable})
    defs['SourceEvidence']=obj({'source_occurrence_refs':refs,'locators':locs,'evidence_type':choice('ORIGINAL_TEXT','THEOREM_STATEMENT','EXCERPT','COMPUTATION','OBSERVATION'),
        'coverage':choice('FULL_DOCUMENT','DECLARED_RANGE','METADATA_ONLY'),'reproducibility_refs':refs})
    review_ref={'anyOf':[string,obj({'inference_of':string})]}
    defs['Assessment']=obj({'review_kind':choice('PROOF','COUNTEREXAMPLE','APPLICABILITY','INTEGRATION','FORMULATION','WORK_CHECK'),'target_refs':arr(review_ref),
        'checked':arr(obj({'ref':review_ref,'locators':locs,'aspect':text})),
        'unchecked':arr(obj({'ref':review_ref,'aspect':text,'reason':text})),
        'verdict':choice('SUPPORTED_WITHIN_SCOPE','DEFECT_FOUND','INCONCLUSIVE'),
        'findings':arr(obj({'code':string,'severity':string,'locator':ref('Locator'),'description_locator':ref('Locator'),'evidence_refs':refs})),
        'scope_context_refs':refs})
    record_variants=[obj({'kind':choice(kind),'context_refs':refs,'body':text,'data':ref(kind)}) for kind in sorted(KINDS)]
    defs['NewRecord']={'oneOf':record_variants}
    defs['Operation']={'oneOf':[
        *[obj({'op':choice('NEW'),'local_key':{'type':'string','pattern':'^[A-Za-z][A-Za-z0-9_.-]{0,95}$'},**variant['properties']}) for variant in record_variants],
        obj({'op':choice('REVISE'),'local_key':string,'object_id':string,'expected_parent':string,'new_record':ref('NewRecord')}),
        obj({'op':choice('LINK'),'type':choice('ARGUMENT_FOR','MATHEMATICAL_DEPENDENCY','USED_SOURCE','SOURCE_PROVENANCE','REVIEW_TARGET','RESPONDS_TO_FEEDBACK',
            'REVISION_OF','SUPERSEDES','ADDRESSES_OBLIGATION','INVALIDATES_SUPPORT','COUNTEREXAMPLE_TO','APPLIES_TO','IMPLIES','EQUIVALENT_ON_SCOPE','MOTIVATED_BY','CALIBRATES','TRANSLATES'),
            'source_ref':string,'target_ref':string,'scope_context_refs':refs,'evidence_bindings':{'type':'array','items':{'anyOf':[string,ref('SourceUse'),obj({'argument_ref':string})]}},
            'assertion_state':choice('PROPOSED','BOUND_TO_ARGUMENT','WITHDRAWN')}),
        obj({'op':choice('WITHDRAW_SUPPORT'),'support_id':string,'expected_qualification_head':nullable,'reason_code':string,'evidence_refs':refs,'scope':arr(ref('Scope'))})]}
    defs['Scope']=obj({'target_ref':string,'locators':locs,'aspects':refs})
    defs['DependencyBinding']={'type':'object','required':['dependency_id','binding_ref','threshold'],
        'properties':{'dependency_id':string,'binding_ref':string,'binding_id':string,'threshold':choice('ARTIFACT_AVAILABLE','WORK_DISPOSITION_RECORDED','SUPPORT_QUALIFIED','HUMAN_DECISION_RECORDED','MATERIAL_VERIFIED'),
        'scope':{'type':'object'},'required_assurance':{'type':'object'},'policy_digest':nullable,'allow_deferred':{'type':'boolean'}},'additionalProperties':False}
    retry_leaves={
        'MATERIAL_VERIFIED':{'source_id':string,'coverage':choice('FULL_DOCUMENT','DECLARED_RANGE','METADATA_ONLY'),'sha256':string},
        'INPUT_REVISION_CHANGED':{'logical_object':string,'old_ref':string,'scope':{'type':'object'}},
        'SUPPORT_CHANGED':{'support_id':string,'previous_version':{},'scope':{'type':'object'}},
        'DEPENDENCY_SATISFIED':{'dependency':ref('DependencyBinding')},
        'METHOD_GRANTED':{'grant_id':string,'method_ref':string},'OPERATOR_RELEASED':{'decision_event':string,'blocker_id':string}}
    defs['RetryCondition']={'anyOf':[obj({'kind':choice('ALL','ANY'),'conditions':arr(ref('RetryCondition'))}),
        *[{'type':'object','required':['kind',*(['source_id'] if k=='MATERIAL_VERIFIED' else list(v))],
            'properties':{'kind':choice(k),**v},'additionalProperties':False} for k,v in retry_leaves.items()]]}
    defs['BlockerProposal']=obj({'code':string,'evidence_refs':refs,'scope':{},'hardness':choice('HARD','EXPLORATORY'),'retry_condition':ref('RetryCondition')})
    defs['ObligationEffect']=obj({'binding_id':string,'expected_definition_revision':{'type':'integer','minimum':1},
        'work_disposition':choice('ADDRESSED','PARTIAL','BLOCKED','NO_RESULT'),'resolution_proposal':choice('CANDIDATE_RESPONSE','UNRESOLVED','NEEDS_RECHECK'),
        'evidence_refs':refs,'remaining_conditions':{'anyOf':[{'type':'array'},{'type':'string'}]},'blocker_proposals':arr(ref('BlockerProposal'))})
    defs['NewObligationProposal']=obj({'local_key':string,'type':choice(*sorted(OBLIGATION_TYPES)),
        'reason_code':{'enum':[None,'NORMALIZATION_REQUIRED']},'target_refs':refs,'criterion_body':text,'scope_context_refs':refs,
        'dependency_bindings':arr(ref('DependencyBinding')),'consumer_binding_proposals':{'type':'array','maxItems':0},'effect_on_goal':string,'reason_refs':refs})
    defs['KnowledgeChange']=obj({'schema':choice(CHANGE_SCHEMA),'task_id':string,'request_id':string,'base_knowledge_commit':nullable,
        'read_set_digest':string,'query_guard_digest':string,'write_guard_digest':string,'operations':arr(ref('Operation')),
        'obligation_effects':arr(ref('ObligationEffect')),'new_obligation_proposals':arr(ref('NewObligationProposal')),
        'work_outcome':choice('RESULT','PARTIAL','NO_RESULT','BLOCKED'),'attempt_account':text,'claimed_change':text,
        'semantic_novelty':choice('NOT_AUTOMATICALLY_CERTIFIED')})
    schema=obj({'schema':choice(RESPONSE_SCHEMA),'task_id':string,'request_id':string,'payload_kind':choice('KNOWLEDGE_CHANGE'),'payload':ref('KnowledgeChange')})
    schema['$defs']=defs
    result={'revision':AUTHORING_REVISION,'knowledge_change_schema':schema,
        'binding_rules':['Copy task_id, request_id and knowledge_commit exactly from task.json in envelope and knowledge change.',
          'Guard digests are SHA256 of canonical JSON: UTF8, sorted dictionary keys, compact separators, ensure_ascii=false; preserve list order. Hash task.read_set, task.query_guards and task.write_guards respectively.',
          'Use local:<local_key> for new record references. Use body:<local_key> only for locators on that new body. Do not use a bare local key as a reference.',
          'Every assigned obligation binding appears exactly once in obligation_effects, with its binding_id and expected_definition_revision.',
          'All required fields are present; no unknown fields. Empty arrays are valid where no work exists. Zero operations never establishes a prerequisite.',
          'Context item keys are unique across all five lists. Their locators point to their complete Context body. parent_context_refs equals context_refs, sorted and unique.',
          'Scope context refs are sorted unique Context records and included in the envelope context_refs. Statement AUTHORED uses source_binding=null; SOURCE_BOUND preserves exact source bytes.',
          'Premises must be supplied; SUPPORTED_STATEMENT uses a frozen support_ref, other premise kinds use support_ref=null. CONTEXT_ASSUMPTION requires exact context assumption locator; other kinds use assumption_locator=null.',
          'PremiseBinding.kind uses exact native endpoint kinds: DEFINITION => Context only; CONTEXT_ASSUMPTION => Context or Statement; SUPPORTED_STATEMENT => Statement only; CONDITIONAL_CANDIDATE => Statement only; DERIVATION_COMPONENT => Argument only. Check the supplied record.kind, not the prose name. A Statement containing definitions is not a DEFINITION endpoint. Do not relabel a theorem as an assumption or candidate to bypass this rule: context assumptions require the actual frozen Context assumption locator; candidates remain explicit open conditions; supported statements require their exact frozen support. Reusing a supplied proof binds its Argument as DERIVATION_COMPONENT and retains inherited open conditions.',
          'CONDITIONAL_CANDIDATE and inherited DERIVATION_COMPONENT open conditions remain explicit. PROOF/REFUTATION/DERIVATION mode_payload is {}.',
          'AND reduction uses premise_refs and no alternatives; OR uses complete AND alternative_argument_refs and no premise_refs. All missing lifting/compatibility checks remain obligations.',
          'Assessment checked locators point to exact target bodies, not review prose. Inference aliases are only review targets. No self-review or qualification promotion.',
          'Every Assessment.checked[i].ref and Assessment.unchecked[i].ref must be in that same Assessment.data.target_refs. For excluded foundational or global work, anchor unchecked aspects to the local reviewed target and preserve their exact reasons; mentioning another supplied record does not automatically make it an Assessment target. Do not widen the declared review or claim excluded work was checked.',
          'For an assigned review slot, copy each checked.aspect verbatim from the frozen required_scope.aspects labels; do not rename labels or infer extra checked aspects from their meaning. Copy the locator type, unit, exact target-body hash and byte/codepoint region from that frozen required_scope. For versioned exact scopes, copy scope_version, extent, target_body_sha256 and whole_locator as supplied. WHOLE_TARGET and ranges covering precisely the same full body are equivalent; partial ranges never satisfy WHOLE_TARGET. Legacy unversioned locators=[] remains abstract and cannot be enlarged. Write detailed actual checks and formula locations in the Assessment body while retaining the exact declared checked labels and regions. Preserve unperformed scope explicitly rather than widening checked coverage.',
          'LINK endpoint kinds and permissions must match the native relation algebra; USED_SOURCE only Argument/Example to frozen source, with exact SourceUse locators. Context provenance uses SOURCE_PROVENANCE.',
          'New obligations target supplied/new records only; consumer_binding_proposals stays []; NORMALIZATION_REQUIRED is only for MATERIAL. Dependencies bind native IDs, never prose descriptions.',
          'Retry conditions are bounded: depth <=4, <=16 leaves; ALL/ANY conditions nonempty. Locators have nonempty half-open ranges and exact UTF8 boundaries.',
          'Use only task.permission_manifest allowed payload, operation and record kinds. This knowledge schema is for KNOWLEDGE_CHANGE; role-specific Survey/report contracts still apply.']}
    if task:
        result['frozen_bindings']={'task_id':task['task_id'],'request_id':task['request_id'],'base_knowledge_commit':task.get('knowledge_commit'),
            **{name:digest(task.get(key,[])) for name,key in [('read_set_digest','read_set'),('query_guard_digest','query_guards'),('write_guard_digest','write_guards')]},
            'obligation_bindings':task.get('obligation_bindings',[]),'permission_manifest':task.get('permission_manifest',{})}
    return _compile_authoring(result,task,snapshot)


def optional_fields(value, required, optional=(), label='object'):
    """A closed object with explicitly versioned optional fields."""
    require(isinstance(value,dict),'RESPONSE_SCHEMA_INVALID',label+' must be an object')
    require(not set(value)-set(required)-set(optional),'UNKNOWN_FIELD',label+' has unknown fields')
    require(set(required)<=set(value),'RESPONSE_SCHEMA_INVALID',label+' missing required fields')
    return value


def _compile_authoring(result,task,snapshot):
    """Compile author guidance and validation from exactly the same shapes."""
    from copy import deepcopy
    schema=result['knowledge_change_schema'];defs=schema['$defs']
    def obj(properties,optional=()):
        return {'type':'object','properties':properties,'required':[x for x in properties if x not in optional],'additionalProperties':False}
    def arr(item,**kw):return {'type':'array','items':item,**kw}
    def ref(name):return {'$ref':'#/$defs/'+name}
    def choice(*values):return {'enum':list(values)}
    string={'type':'string','minLength':1};text=string;nullable={'anyOf':[string,{'type':'null'}]};refs=arr(string,uniqueItems=True);locs=arr(ref('Locator'))
    # The endpoint matrix drives both authoring and knowledge.validate_record.
    result['premise_endpoint_matrix']={k:sorted(v) for k,v in PREMISE_ENDPOINTS.items()}
    defs['PremiseBinding']['properties']['kind']=choice(*sorted(PREMISE_ENDPOINTS))
    scope_meta={'scope_version':choice('pmrs.exact-scope/1'),'extent':choice('WHOLE_TARGET','EXACT_REGIONS'),
        'target_body_sha256':{'type':'string','pattern':'^[0-9a-f]{64}$'},'whole_locator':ref('Locator')}
    legacy=deepcopy(defs['Scope']);defs['Scope']={'oneOf':[legacy,obj({**legacy['properties'],**scope_meta})]}
    checked=defs['Assessment']['properties']['checked']['items']
    defs['Assessment']['properties']['checked']['items']={'oneOf':[deepcopy(checked),obj({**checked['properties'],**scope_meta})]}
    permission=(task or {}).get('permission_manifest',{})
    allowed_ops=set(permission.get('allowed_operations',OP_FIELDS));allowed_kinds=set(permission.get('allowed_record_kinds',KINDS))
    if task:
        variants=[]
        for branch in defs['Operation']['oneOf']:
            p=branch['properties'];op=p['op']['enum'][0]
            if op not in allowed_ops or op=='NEW' and p['kind']['enum'][0] not in allowed_kinds:continue
            variants.append(branch)
        defs['Operation']={'oneOf':variants} if variants else {'not':{}}
        defs['NewRecord']['oneOf']=[v for v in defs['NewRecord']['oneOf'] if v['properties']['kind']['enum'][0] in allowed_kinds]
    defs['KnowledgeChange']['properties']['operations']['maxItems']=640
    defs['KnowledgeChange']['properties']['obligation_effects']['maxItems']=256
    defs['KnowledgeChange']['properties']['new_obligation_proposals']['maxItems']=32
    defs['MessageDisposition']=obj({'message_id':string,'disposition':choice('VIEWED','USED','REJECTED','NEEDS_CLARIFICATION'),'reason':text,'record_refs':refs})
    defs['KnowledgeChange']['properties']['message_dispositions']=arr(ref('MessageDisposition'),maxItems=256)
    if task and task.get('actor_kind')=='MAIN':
        from . import strategy
        defs['KnowledgeChange']['properties']['strategy_proposal']=strategy.authoring_schema(task)
        defs['KnowledgeChange']['required'].append('strategy_proposal')
    elif task is None:
        # A task-free registry exposes the extension without granting its use.
        defs['KnowledgeChange']['properties']['strategy_proposal']={'type':'object','description':'Only a frozen MAIN task may emit the role-specific strategy schema.'}
    survey_actions={
      'SEARCH_PLAN':obj({'queries':arr(obj({'provider':choice('arxiv','crossref'),'query':{'type':'string','minLength':1,'maxLength':1500},'reason':text,'max_results':{'type':'integer','minimum':1,'maximum':10}}),minItems=1,maxItems=4),'stop_reason':text}),
      'READING':obj({'readings':arr(obj({'source_ref':string,'version':string,'locators':arr(ref('Locator'),minItems=1),'read_scope':text,'unread_scope':refs,'limitations':refs,'claim_refs':refs}),maxItems=64)}),
      'ORGANIZE':obj({'selected_refs':refs,'dependencies':arr(obj({'source_ref':string,'target_ref':string,'relation':choice('uses_definition','proof_input','explained_by','compares_with')}),maxItems=512),
        'coverage':arr(obj({'question':text,'answer_refs':refs,'mechanism_refs':refs,'boundary_refs':refs,'gaps':arr(obj({'description':text,'refs':refs,'disposition':choice('OPEN','RESOLVED','OUTSIDE_SCOPE','DEFERRED_NONESSENTIAL'),'reason':text,'return_stage':choice('S1','S2','S3')}),maxItems=256),'assessment':choice('PENDING','ADEQUATE','LIMITED'),'rationale':text}),maxItems=256)}),
      'REVIEW':obj({'selected_refs':refs,'checked_refs':refs,'unchecked_refs':refs,'coverage_questions':refs,'verdict':choice('READY','NEEDS_WORK'),
        'proof_steps':{'type':'object','additionalProperties':refs},'findings':arr(obj({'code':string,'ref':nullable,'message':text,'blocking':{'type':'boolean'},'return_stage':choice('S1','S2','S3','S4')}),maxItems=256),'limitations':refs})}
    role_actions={'SEARCH_PLAN':'SEARCH_PLAN','SOURCE_READ':'READING','ORGANIZE':'ORGANIZE','RECONSTRUCT':'ORGANIZE','READINESS_REVIEW':'REVIEW','COVERAGE_REVIEW':'REVIEW'}
    action=role_actions.get((task or {}).get('role'))
    defs['SurveyResult']={'oneOf':[obj({'schema':choice('pmrs.survey-result/1'),'knowledge_change':ref('KnowledgeChange'),'action':choice(a),'data':p}) for a,p in survey_actions.items() if action is None or a==action]}
    ctx=(task or {}).get('report_context',{});profile=choice(ctx['profile']) if ctx.get('profile') else string
    finding=obj({'code':string,'anchor':string,'severity':choice('BLOCKING','WARNING'),'description':text})
    author=obj({'profile':profile,'body':text,'notation_tex':text,'shared_statements':arr(obj({'id':{'type':'string','pattern':'^[A-Za-z0-9]+$'},'statement_tex':text,'status':choice('OPEN','CONDITIONAL','CANDIDATE','BACKGROUND','INCONCLUSIVE'),'source_refs':arr(string,minItems=1)}),maxItems=64),
        'coverage':obj({k:text for k in ('goal','notation','inherited_basis','current_results','proofs','failures','open_obligations')}),'included_refs':refs,'omissions':arr(obj({'ref':string,'reason':text})),'parent_lecture':nullable})
    if ctx.get('revision_request',{}).get('scope',{}).get('kind')=='SECTIONS':author=obj({'profile':profile,'replacements':arr(obj({'section_id':string,'body':text}),minItems=1)})
    semantic={'profile':profile,'verdict':choice('PASS','REVISE'),'findings':arr(finding),'uncheckable':arr(string)}
    if ctx.get('revision_request'):semantic['revision_check']=obj({'verdict':choice('SATISFIED','UNMET','UNCERTAIN'),'unmet_requirement_refs':refs,'uncertain_requirement_refs':refs,'summary':text})
    visual=obj({'profile':profile,'pages':arr(obj({'id':string,'sha256':{'type':'string','pattern':'^[0-9a-f]{64}$'},'verdict':choice('PASS','REVISE'),'findings':arr(finding)}))})
    defs['ReportOutput']=author;defs['ReportReview']=visual if (task or {}).get('role')=='REPORT_VISUAL' else obj(semantic)
    payloads={'KNOWLEDGE_CHANGE':ref('KnowledgeChange'),'SURVEY_RESULT':ref('SurveyResult'),'REPORT_OUTPUT':ref('ReportOutput'),'REPORT_REVIEW':ref('ReportReview')}
    allowed=permission.get('allowed_payload_kinds',list(payloads));bindings=result.get('frozen_bindings',{})
    if task:
        for field in ('task_id','request_id','base_knowledge_commit','read_set_digest','query_guard_digest','write_guard_digest'):
            defs['KnowledgeChange']['properties'][field]={'const':bindings[field]}
    branches=[obj({'schema':choice(RESPONSE_SCHEMA),'task_id':{'const':task['task_id']} if task else string,
        'request_id':{'const':task['request_id']} if task else string,'payload_kind':choice(kind),'payload':shape}) for kind,shape in payloads.items() if kind in allowed]
    if task:
        reachable=set()
        def visit(value):
            if isinstance(value,list):
                for item in value:visit(item)
            elif isinstance(value,dict):
                if '$ref' in value and value['$ref'].startswith('#/$defs/'):
                    name=value['$ref'][8:]
                    if name not in reachable:
                        require(name in defs,'RESPONSE_SCHEMA_INVALID','Unknown internal authoring definition: '+name)
                        reachable.add(name);visit(defs[name])
                for key,item in value.items():
                    if key!='$defs':visit(item)
        visit(branches);defs={name:defs[name] for name in sorted(reachable)}
    result['response_schema']=_compact_authoring_schema({'$schema':'https://json-schema.org/draft/2020-12/schema','oneOf':branches,'$defs':defs})
    # Historical callers of knowledge_change_schema receive the narrowed native
    # envelope too; one source of truth avoids prose-only role restrictions.
    result['knowledge_change_schema']=result['response_schema']
    result['binding_rules']=[
        'Use the schema constants for frozen IDs, base and guards. Hashes use UTF8 canonical JSON: sorted object keys, compact separators, ensure_ascii=false, unchanged list order.',
        'New record references use local:<key>; only local-body locators use body:<key> with quoted_sha256=null for host calculation. All other locators need exact supplied blob and quote hashes, nonempty half-open ranges and intact UTF8 boundaries.',
        'Every task.obligation_bindings entry appears once in effects with its exact definition revision. Zero operations do not fulfill scientific prerequisites. Empty arrays mean no such work; unknown fields are forbidden.',
        'Context keys are unique across definitions/objects/assumptions/quantifiers/conventions; locators point to that full body. parent_context_refs equals sorted unique context_refs. Scope Contexts are a subset of context_refs.',
        'AUTHORED Statements use null source_binding; SOURCE_BOUND bodies preserve exact original source passages. URL/metadata alone is not read full text.',
        'Use premise_endpoint_matrix and actual record.kind. Do not relabel a theorem to evade qualification. SUPPORTED_STATEMENT requires its exact frozen qualified support. Other kinds use support_ref=null.',
        'CONTEXT_ASSUMPTION needs context_ref in argument.context_refs and an actual Context assumption_locator. Other premise kinds use assumption_locator=null. Keep CONDITIONAL_CANDIDATE and inherited DERIVATION_COMPONENT conditions explicitly open.',
        'PROOF/REFUTATION/DERIVATION payload is {}. AND reductions bind premise_refs without alternatives; OR binds complete AND alternatives without premise_refs. Missing lifting/compatibility remain obligations; a shared witness needs explicit quantifier and compatibility evidence.',
        'Assessment checked and unchecked refs belong to its target_refs. Copy assigned targets/aspects literally. Checked locators identify target bodies, not review prose. Inference aliases are only review targets. Exclusions retain reasons; unperformed checks cannot become support.',
        'Copy exact scope codec metadata. WHOLE_TARGET equals only ranges covering its exact full body; partial ranges do not. Legacy unversioned [] remains abstract. Findings can explain locations without widening assigned scope. No self-review or qualification promotion.',
        'LINK uses native endpoint kinds. USED_SOURCE is Argument/Example to an actually delivered source with exact SourceUse; Context provenance uses SOURCE_PROVENANCE. Method inspiration is not a mathematical premise.',
        'New gaps target supplied/new records; consumer_binding_proposals stays []. Only MATERIAL may use NORMALIZATION_REQUIRED. Dependencies use exact native IDs. Retry trees have depth<=4, <=16 leaves and nonempty ALL/ANY.',
        'A declared hypothesis requires the exact Context assumption locator in Statement.hypothesis_locators. Typed consumer policy binds this statement and argument use; sharing a Context or a label discharges nothing. Extra conditions never establish an unrestricted target.',
        'Only frozen task.permission_manifest branches are authorized. Reports cannot create science; Survey metadata uses the same captured native KCS and separate role-specific action. All scientific bodies and authored metadata are English; exact original source quotations retain their bytes.'
    ]
    if task:
        records=(snapshot or {}).get('records',{})
        result['binding_table']={
          'records':[{'ref':b['record_ref'],'kind':records.get(b['record_ref'],{}).get('kind'),'body_sha256':b['body_hash'],'required_support_refs':b.get('required_support_refs',[])} for b in task.get('read_set',[])],
          'sources':[i for i in task.get('input_manifest',[]) if i.get('kind')=='source'],
          'source_uses':task.get('source_uses',[]),'obligation_bindings':task.get('obligation_bindings',[]),
          'required_assurance':task.get('required_assurance'),'write_guards':task.get('write_guards',[])}
        result['review_templates']=[{'ref':r['target_ref'],'aspect':a,'locators':r['locators'],**{k:r[k] for k in scope_meta if k in r}} for r in (task.get('required_assurance') or {}).get('required_scope',[]) for a in r['aspects']]
    if task:result.pop('frozen_bindings',None)  # Exact constants already occur in response_schema; bindings live in binding_table.
    return result


def _map_schema(value,change,*,definition=False):
    """Visit schema positions only, never values inside const/enum annotations."""
    if not isinstance(value,dict):return value
    value=change(value,definition)
    result=dict(value)
    for key,item in value.items():
        if key in ('properties','$defs'):
            result[key]={name:_map_schema(sub,change,definition=key=='$defs') for name,sub in item.items()}
        elif key in ('items','not','additionalProperties') and isinstance(item,dict):
            result[key]=_map_schema(item,change)
        elif key in ('oneOf','anyOf','allOf'):
            result[key]=[_map_schema(sub,change) for sub in item]
    return result


def _compact_authoring_schema(schema):
    """Lossless JSON Schema compression, after permission narrowing.

    In a closed object, requiring every listed property is exactly equivalent
    to a property-count lower bound equal to that list's length. All property
    definitions remain visible. The other transformation replaces identical
    schema subtrees with local references; it cannot remove a branch or field.
    Original named definitions remain stable public schema entry points.
    """
    from collections import Counter
    from copy import deepcopy
    schema=deepcopy(schema);definitions=schema['$defs']
    operation=definitions.get('Operation',{}).get('oneOf',[])
    new=[b for b in operation if b.get('properties',{}).get('op',{}).get('enum')==['NEW']]
    records=definitions.get('NewRecord',{}).get('oneOf',[])
    variants=records or new
    def record_shape(branch):
        props=branch.get('properties',{})
        return (branch.get('type')=='object' and branch.get('additionalProperties') is False
                and set(branch.get('required',[]))==set(props) and {'kind','data'}<=set(props))
    if len(variants)>1 and all(record_shape(b) for b in [*records,*new]):
        bindings=[{'properties':{key:b['properties'][key] for key in ('kind','data')}} for b in variants]
        signatures=[canonical(b) for b in bindings]
        groups=[group for group in (records,new) if group]
        compatible=all([canonical({'properties':{k:b['properties'][k] for k in ('kind','data')}}) for b in group]==signatures
            and len({canonical({k:v for k,v in b['properties'].items() if k not in ('kind','data')}) for b in group})==1
            and len({canonical({k:v for k,v in b.items() if k!='properties'}) for b in group})==1 for group in groups)
        if compatible:
            # The closed parent requires kind and data; this disjoint union
            # supplies their exact paired validators. NEW and REVISE use the
            # same pairing while preserving their different outer fields.
            definitions['RecordData']={'oneOf':bindings}
            def factored(group):
                base=deepcopy(group[0]);base['properties'].update(kind={},data={})
                base['allOf']=[{'$ref':'#/$defs/RecordData'}];return base
            if records:definitions['NewRecord']=factored(records)
            if new:definitions['Operation']['oneOf']=[factored(new),*[b for b in operation if b not in new]]
    def closed_shape(node,_):
        if node.get('type')=='object' and node.get('additionalProperties') is False:
            props=node.get('properties',{});required=node.get('required',[])
            if props and len(required)==len(props) and set(required)==set(props):
                result=dict(node);result.pop('required');result['minProperties']=len(props)
                if len(canonical(result))<len(canonical(node)):return result
        return node
    result=_map_schema(schema,closed_shape)
    while True:
        counts=Counter();subtrees={}
        def inventory(node,definition):
            if not definition and node and '$ref' not in node:
                key=canonical(node);counts[key]+=1;subtrees[key]=node
            return node
        _map_schema(result,inventory)
        definitions=result['$defs'];existing={canonical(node):name for name,node in definitions.items()}
        name='S'+str(sum(k.startswith('S') and k[1:].isdigit() for k in definitions))
        while name in definitions:name='S'+str(int(name[1:])+1)
        choices=[]
        for key,copies in counts.items():
            target=existing.get(key,name);replacement={'$ref':'#/$defs/'+target}
            # Final references use local anchors. Include the new anchor's
            # annotation in this cost, not the longer intermediate JSON path.
            reference_size=len(canonical({'$ref':'#a' if len(definitions)<52 else '#aa'}))
            saving=copies*(len(key)-reference_size)-(0 if key in existing else len(key)+len(target)+18)
            if saving>0:choices.append((saving,key,target,replacement))
        if not choices:break
        # Recount after each extraction: a shared parent reduces child copies,
        # while extracting a child can reveal an identical enclosing subtree.
        _,key,target,replacement=max(choices,key=lambda row:(row[0],row[1]))
        def replace(node,definition):
            return replacement if not definition and canonical(node)==key else node
        result=_map_schema(result,replace)
        if key not in existing:result['$defs'][target]=subtrees[key]
    alphabet='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ';anchors={}
    for index,name in enumerate(result['$defs']):
        anchor=''
        while True:
            anchor=alphabet[index%len(alphabet)]+anchor;index=index//len(alphabet)-1
            if index<0:break
        anchors[name]=anchor
    def anchor_ref(node,_):
        target=node.get('$ref','')
        if target.startswith('#/$defs/'):
            return {**node,'$ref':'#'+anchors[target[8:]]}
        return node
    result=_map_schema(result,anchor_ref)
    for name,node in result['$defs'].items():node['$anchor']=anchors[name]
    return result


def schema_diagnostics(value,schema,*,limit=32):
    """Small deterministic validator for the exact schema vocabulary above.

    No optional runtime dependency or remote schema resolution is involved.
    Semantic relations, provenance and authorization still run in changes.py.
    """
    defs=schema.get('$defs',{});anchors={value['$anchor']:value for value in defs.values() if '$anchor' in value}
    def dereference(s):
        while '$ref' in s:
            target=s['$ref'];s=defs[target[8:]] if target.startswith('#/$defs/') else anchors[target.removeprefix('#')]
        return s
    def issue(pointer,expected,actual,code='RESPONSE_SCHEMA_INVALID'):
        return {'code':code,'category':'STRUCTURE','pointer':pointer or '/','expected':expected,
                'actual':{'type':type(actual).__name__,'value':actual if not isinstance(actual,(dict,list)) else ('object keys '+','.join(actual) if isinstance(actual,dict) else 'array length '+str(len(actual)))}}
    def walk(v,s,p=''):
        if '$ref' in s:return walk(v,dereference(s),p)
        errors=[]
        if 'not' in s and not walk(v,s['not'],p):return [issue(p,'No value authorized',v)]
        if 'allOf' in s:
            for sub in s['allOf']:errors+=walk(v,sub,p)
        for union in ('oneOf','anyOf'):
            if union in s:
                branches=s[union]
                # Exact discriminators improve diagnostics without guessing a
                # semantic coercion for an enum or record kind.
                matched=[]
                if isinstance(v,dict):
                    for b in branches:
                        bs=dereference(b)
                        discriminators={k:dereference(x) for k,x in bs.get('properties',{}).items() if k in ('op','kind','mode','payload_kind','action') and ('enum' in dereference(x) or 'const' in dereference(x))}
                        if discriminators and all(v.get(k) in x.get('enum',[x.get('const')]) for k,x in discriminators.items()):matched.append(b)
                considered=matched or branches
                outcomes=[walk(v,b,p) for b in considered]
                valid=sum(not x for x in outcomes)
                if (union=='oneOf' and valid!=1) or (union=='anyOf' and valid==0):
                    errors+=min(outcomes,key=len) if outcomes and all(outcomes) else [issue(p,union+' exact branch',v)]
        if 'const' in s and v!=s['const']:errors.append(issue(p,{'const':s['const']},v))
        if 'enum' in s and v not in s['enum']:errors.append(issue(p,{'enum':s['enum']},v))
        typ=s.get('type');checks={'object':isinstance(v,dict),'array':isinstance(v,list),'string':isinstance(v,str),'integer':type(v) is int,'boolean':type(v) is bool,'null':v is None}
        if typ and not (any(checks.get(t,False) for t in typ) if isinstance(typ,list) else checks.get(typ,False)):return errors+[issue(p,{'type':typ},v)]
        if isinstance(v,dict):
            props=s.get('properties',{})
            required=s.get('required',[])
            if s.get('additionalProperties') is False and s.get('minProperties')==len(props):
                # Retain missing-field pointers for the compact closed form.
                required=list(dict.fromkeys([*required,*props]))
            elif len(v)<s.get('minProperties',0):errors.append(issue(p,'Object property count',v))
            for key in required:
                if key not in v:errors.append(issue(p+'/'+key,'Required field','<missing>'))
            for key,item in v.items():
                ptr=p+'/'+key.replace('~','~0').replace('/','~1')
                if key in props:errors+=walk(item,props[key],ptr)
                elif s.get('additionalProperties') is False:errors.append(issue(ptr,'No additional field',item,'UNKNOWN_FIELD'))
                elif isinstance(s.get('additionalProperties'),dict):errors+=walk(item,s['additionalProperties'],ptr)
        if isinstance(v,list):
            if len(v)<s.get('minItems',0) or len(v)>s.get('maxItems',100000):errors.append(issue(p,'Array bounds',v))
            if s.get('uniqueItems') and len({canonical(x) for x in v})!=len(v):errors.append(issue(p,'Unique items',v))
            if 'items' in s:
                for i,item in enumerate(v):errors+=walk(item,s['items'],p+'/'+str(i))
        if isinstance(v,str):
            if len(v)<s.get('minLength',0) or len(v)>s.get('maxLength',MAX_BODY):errors.append(issue(p,'String length',v))
            if 'pattern' in s and not re.search(s['pattern'],v):errors.append(issue(p,{'pattern':s['pattern']},v))
        if type(v) is int and (v<s.get('minimum',-MAX_INT) or v>s.get('maximum',MAX_INT)):errors.append(issue(p,'Integer bounds',v))
        return errors[:limit]
    return walk(value,schema)[:limit]


def validate_authoring(value,task,snapshot=None):
    diagnostics=schema_diagnostics(value,authoring_contract(task,snapshot)['response_schema'])
    if diagnostics:
        d=diagnostics[0];error=PMRSError(d['code'],d['pointer']+': expected '+str(d['expected']))
        error.diagnostic=d;error.diagnostics=diagnostics;raise error
    return value
