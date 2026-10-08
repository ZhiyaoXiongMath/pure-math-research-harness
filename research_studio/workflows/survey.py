"""Native Survey duties. A stage declares permitted work, never an automatic run."""
from copy import deepcopy

_ROWS = [
 ('S0','Scope and authorization','范围与授权',['CONTROL'],['HUMAN','HOST'],[],['S1','S4'],[]),
 ('S1','Literature discovery','文献调查',['MATERIAL'],['SEARCH_PLAN'],[],['S2'],['S1']),
 ('S2','Read original sources','原文阅读',['MATERIAL'],['SOURCE_READ'],['SourceEvidence'],['S3'],['S1','S2']),
 ('S3','Organize mathematical knowledge','知识组织',['FORMULATE','ESTABLISH','INTEGRATE','ACCOUNT'],['ORGANIZE','RECONSTRUCT'],['Context','Statement','Argument','Example','SourceEvidence'],['S4'],['S1','S2','S3']),
 ('S4','Review scoped readiness','就绪审查',['VERIFY','ACCOUNT'],['READINESS_REVIEW','COVERAGE_REVIEW'],[],['S5'],['S1','S2','S3','S4']),
 ('S5','Freeze knowledge and plan output','快照与写作计划',['CONTROL'],['HUMAN','HOST'],[],['S6'],['S4','S5']),
 ('S6','Write the selected survey','综述写作',['REPORT'],['REPORT_AUTHOR'],[],['S7'],['S3','S4','S5','S6']),
 ('S7','Review and deliver','审查与交付',['REPORT','CONTROL'],['REPORT_SEMANTIC','REPORT_VISUAL','HUMAN','HOST'],[],[],['S3','S4','S6','S7']),
]
STAGES=[]
for sid,en,zh,obligations,roles,kinds,forward,back in _ROWS:
    role_rows=[]
    for role in roles:
        independent=role in {'READINESS_REVIEW','COVERAGE_REVIEW','REPORT_SEMANTIC','REPORT_VISUAL'}
        payload=([] if role=='HUMAN' else ['CONTROL_PROPOSAL'] if role=='HOST' else
                 ['REPORT_OUTPUT'] if role=='REPORT_AUTHOR' else ['REPORT_REVIEW'] if role.startswith('REPORT_') else ['SURVEY_RESULT'])
        role_rows.append({'role':role,'required_when':'FORMAL_REPORT_REQUESTED_WITH_AUTHORIZED_REPORT_BUDGET' if role.startswith('REPORT_') else 'WHEN_ASSIGNED_BY_OBLIGATION',
             'independent':independent,'forbidden_context_classes':['PRIOR_REVIEW_VERDICT','DERIVED_VERDICT_TEXT'] if independent else [],'payload_kinds':payload})
    STAGES.append({'workflow_kind':'SURVEY','stage_id':sid,'version':'pmrs.survey/1','purpose':en,
        'allowed_obligation_types':obligations,'roles':role_rows,
        'input_binding_rule_ids':['FIXED_INSTANCE_SCOPE','EXACT_MANDATORY_CLOSURE','ROLE_MATERIAL_POLICY','SOURCE_BYTES_BOUND','RELEVANT_READ_AND_QUERY_GUARDS','SURVEY_SCOPE_AND_EVIDENCE_VERSIONS'],
        'output_contract_ids':['pmrs.survey-result/1','pmrs.knowledge-change/1'] if sid in {'S1','S2','S3','S4'} else ['pmrs.control-event/1','pmrs.report/final-1'],
        'allowed_scientific_kinds':kinds,
        'empty_outcome_policy':'RESEARCH_NO_RESULT_WITH_DUTY_DISPOSITION; NO_IMPLIED_READINESS_OR_OUTPUT',
        'completion_rule_ids':['STRUCTURE_AND_ROLE_VALID','MANDATORY_SCOPE_ACCOUNTED','OPEN_CONDITIONS_PERSIST','EXACT_SURVEY_EVIDENCE_SCOPE'],
        'exit_rules':{'forward':forward,'return':back,'early_delivery':None,'required':['SCOPE_DISPOSITION_REQUIRED','NO_AUTHORITY_PROMOTION','UNPERFORMED_DUTIES_PERSIST','CHANGED_INPUT_OR_GRANTED_RETRY'],'automatic_next':False},
        'reentry_rule_id':'OBLIGATION_PURPOSE_INPUT_AND_GRANTED_RETRY',
        'forbidden_effects':['NO_AUTHORITY_PROMOTION','NO_AUTOMATIC_HUMAN_DECISION','NO_TARGET_REWRITE','NO_UNBOUNDED_RETRY','NO_NETWORK_IN_MODEL_TASK','NO_IMPLICIT_MANUSCRIPT'],
        'ui_labels':{'en':en,'zh-CN':zh},'prompt_sections':['EXACT_TASK_INTENT','TARGET_CONTEXT_AND_SCOPE','ACTUAL_INPUT_MANIFEST','ROLE_DUTY_AND_BOUNDARIES','EXPECTED_KNOWLEDGE_CHANGE','OUTPUT_CONTRACT','NO_AUTHORITY_PROMOTION']})


def activity_for_obligation(definition):
    return {'MATERIAL':('S2','SOURCE_READ',{}),'FORMULATE':('S3','ORGANIZE',{}),
            'ESTABLISH':('S3','RECONSTRUCT',{}),'INTEGRATE':('S3','ORGANIZE',{}),
            'VERIFY':('S4','READINESS_REVIEW',{}),'ACCOUNT':('S3','ORGANIZE',{})}.get(definition['type'])
