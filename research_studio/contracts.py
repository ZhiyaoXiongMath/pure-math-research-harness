"""Public final contracts and bounded, deterministic parsing.

Scientific identities deliberately exclude producers and mutable projections.
This module is the runtime's single field/enum registry; no legacy aliases.
"""
from __future__ import annotations
from pmrh.domain.contracts import (
    ASSURANCE_FIELDS,
    AUTHORING_REVISION,
    CHANGE_SCHEMA,
    CONTEXT_BUDGET_FIELDS,
    DATA_FIELDS,
    ENVELOPE_FIELDS,
    HASH,
    INFERENCE_FIELDS,
    KCS_FIELDS,
    KCS_OPTIONAL_FIELDS,
    KINDS,
    LOCAL_KEY,
    LOCATOR_FIELDS,
    MAX_BODY,
    MAX_DEPTH,
    MAX_INT,
    MAX_PAYLOAD,
    OBLIGATION_TYPES,
    OP_FIELDS,
    PREMISE_ENDPOINTS,
    PREMISE_FIELDS,
    RECORD_FIELDS,
    RECORD_SCHEMA,
    SCIENCE_PROJECTION_REVISION,
    SCOPE_FIELDS,
    SLOT_FIELDS,
    SOURCE_MODES,
    SOURCE_USE_FIELDS,
    bounded_json,
    digest,
    enum,
    fields,
    inference_identity,
    optional_fields,
    refs,
    scientific_identity,
    sequence,
    validate_tree,
)
import json
import re
from .util import PMRSError, require, canonical, sha

from .version import SCHEMA_VERSION as PROJECT_SCHEMA, TASK_SCHEMA, RESPONSE_SCHEMA, COMMIT_SCHEMA

class ValidatedChange(dict):
    """A pure validation plan. Store revalidates raw/task under its live lock."""


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


from pmrh.domain.native_response import authoring_contract as authoring_contract


from pmrh.domain.native_response import _compile_authoring as _compile_authoring


from pmrh.domain.native_response import _map_schema as _map_schema


from pmrh.domain.native_response import _compact_authoring_schema as _compact_authoring_schema


from pmrh.domain.native_response import schema_diagnostics as schema_diagnostics


from pmrh.domain.native_response import validate_authoring as validate_authoring
