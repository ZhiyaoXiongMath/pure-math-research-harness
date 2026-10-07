"""Public final contracts and bounded, deterministic parsing.

Scientific identities deliberately exclude producers and mutable projections.
This module is the runtime's single field/enum registry; no legacy aliases.
"""
from __future__ import annotations
import json
import re
from .util import PMRSError, require, canonical, sha

PROJECT_SCHEMA = 'pmrs.project/3.4-final-1'
RECORD_SCHEMA = 'pmrs.knowledge-record/1'
CHANGE_SCHEMA = 'pmrs.knowledge-change/1'
TASK_SCHEMA = 'pmrs.task/final-1'
RESPONSE_SCHEMA = 'pmrs.response/final-1'
COMMIT_SCHEMA = 'pmrs.commit/final-1'
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
    return {'project_schema':PROJECT_SCHEMA,'record_schema':RECORD_SCHEMA,
      'task_schema':TASK_SCHEMA,'response_schema':RESPONSE_SCHEMA,'change_schema':CHANGE_SCHEMA,
      'knowledge_record':{'required':sorted(RECORD_FIELDS),'additionalProperties':False,
         'kinds':sorted(KINDS),'data_fields':{k:sorted(v) for k,v in DATA_FIELDS.items()}},
      'response_envelope':{'required':sorted(ENVELOPE_FIELDS),'additionalProperties':False},
      'knowledge_change':{'required':sorted(KCS_FIELDS),'operations':{k:sorted(v) for k,v in OP_FIELDS.items()},'additionalProperties':False},
      'consumer_assurance':{'required':sorted(ASSURANCE_FIELDS),'slots':sorted(SLOT_FIELDS),
         'paths':['MODEL_CAPTURE','HUMAN_ATTESTATION']},
      'context_budget':{'required':sorted(CONTEXT_BUDGET_FIELDS)},
      'limits':{'json_bytes':MAX_PAYLOAD,'body_bytes':MAX_BODY,'depth':MAX_DEPTH,'records':64,'relations':512,'obligation_effects':256}}
