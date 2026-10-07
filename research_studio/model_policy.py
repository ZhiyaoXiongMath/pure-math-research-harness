"""Single model policy for task preparation, UI, CLI and help.

These are responsibility-based product defaults, not benchmark conclusions.
Capability evidence is an executor input; an unavailable setting fails closed.
"""
from copy import deepcopy
from .util import identity,require
from .workflows.registry import spec,role_contract

VERSION='pmrs.model-policy/1'
DEFAULT_MODEL='gpt-6-astra'
DEFAULT_TIER='default'
NO_CALL_ROLES={'HOST','HUMAN'}
LOCAL_PURPOSES={'DETERMINISTIC_DIFF','PROGRESS_SNAPSHOT','PDF_COMPILE','PAGE_COUNT','FILE_CHECK','READ_ONLY'}
REPORT_ROLES={'REPORT_AUTHOR','REPORT_SEMANTIC','REPORT_VISUAL'}
# The exact stage is always part of the key. There is no generic SYNTHESIS row.
_ROWS={
 'P1':{'PLAN':'high'},'P2':{'PLAN':'xhigh'},'P3':{'PLAN':'xhigh'},
 'P4':{'RESEARCH':'max','FALSIFY':'max','PROOF':'max','COUNTEREXAMPLE':'max'},
 'P5':{'SYNTHESIS':'xhigh'},'P6':{'PLAN':'max'},
 'P7':{'LEARN':'max','DIRECT':'max','SYNTHESIS':'xhigh','PROOF':'max','COUNTEREXAMPLE':'max'},
 'P8':{'PLAN':'xhigh','RESEARCH':'max','FALSIFY':'max','SYNTHESIS':'xhigh','PROOF':'max','COUNTEREXAMPLE':'max'},
 'P9':{'PROOF':'max','COUNTEREXAMPLE':'max','SPECIALIST':'max','SYNTHESIS':'xhigh'},
 'P10':{'SYNTHESIS':'max'},'P11':{'SYNTHESIS':'xhigh'},
 'P12':{'INDEPENDENT':'max','SPECIALIST':'max'},
 'D0':{'PLAN':'high'},'D1':{'LEARN':'xhigh','RESEARCH':'xhigh'},
 'D2':{'PLAN':'max','DIRECT':'max','SYNTHESIS':'max'},
 'D3':{'DIRECT':'max','RESEARCH':'max','FALSIFY':'max','LEARN':'xhigh','PROOF':'max','COUNTEREXAMPLE':'max'},
 'D4':{'FORMULATION_REVIEW':'max','ADVERSARIAL_REVIEW':'max'},'D5':{'SYNTHESIS':'xhigh'},
}
_EXCEPTIONS={('P1','PLAN','COMPLEX_DEFINITION_ANALYSIS'):'xhigh',
             ('P2','PLAN','PROVE_REDUCTION'):'max',
             ('P7','SYNTHESIS','MATHEMATICAL_INTEGRATION'):'max',
             ('P8','SYNTHESIS','MATHEMATICAL_INTEGRATION'):'max'}
for _stage,_roles in [('D1',('LEARN','RESEARCH')),('D3',('LEARN',))]:
    for _role in _roles:
        for _purpose in ('NEW_CONSTRUCTION','MATHEMATICAL_DERIVATION','PROVE_APPLICABILITY'):
            _EXCEPTIONS[(_stage,_role,_purpose)]='max'


def describe():
    rules=[]
    from .workflows.registry import definition
    for stage,row in definition()['stages'].items():
        for role in row['roles']:
            rules.append(resolve(row['workflow_kind'],stage,role['role'],require_capability=False))
    return {'schema':VERSION,'default_model':DEFAULT_MODEL,'rules':rules,
            'purpose_exceptions':[{'stage_id':s,'role':r,'purpose':p,'reasoning_effort':e} for (s,r,p),e in sorted(_EXCEPTIONS.items())],
            'layout_only_reasoning_effort':'high','ultra_default':False,'local_purposes':sorted(LOCAL_PURPOSES),
            'unsupported_behavior':'REJECT_WITHOUT_FALLBACK'}


def capability_check(config,capabilities):
    require(isinstance(capabilities,dict) and capabilities.get('source') and capabilities.get('revision'),
            'MODEL_CAPABILITY_UNKNOWN','Executor capability source and revision are required before dispatch')
    models=capabilities.get('models',{});model=models.get(config['model'])
    require(isinstance(model,dict),'MODEL_CONFIGURATION_UNSUPPORTED','The executor does not advertise the requested model')
    require(config['reasoning_effort'] in model.get('reasoning_efforts',[]),'MODEL_CONFIGURATION_UNSUPPORTED','Requested reasoning effort is not supported; no fallback was applied')
    require(config['service_tier'] in model.get('service_tiers',['default']),'MODEL_CONFIGURATION_UNSUPPORTED','Requested service tier is not supported')
    if config['reasoning_effort']=='ultra':
        require(capabilities.get('isolated_ultra_verified') is True and capabilities.get('internal_delegation') is False,
                'MODEL_CONFIGURATION_UNSUPPORTED','Ultra is unavailable unless the executor proves the same isolation and disables internal delegation')
    return {'source':capabilities['source'],'revision':capabilities['revision'],'executor':capabilities.get('executor'),
            'capability_digest':identity(capabilities),'supported':True}


def resolve(workflow_kind,stage_id,role,purpose='DEFAULT',*,override=None,capabilities=None,require_capability=True):
    row=spec(stage_id)
    require(row['workflow_kind']==workflow_kind,'MODEL_POLICY_UNREGISTERED','Workflow/stage mismatch')
    role_contract(stage_id,role)
    base={'policy_version':VERSION,'workflow_kind':workflow_kind,'stage_id':stage_id,'role':role,'purpose':purpose}
    if role in NO_CALL_ROLES or stage_id in {'P0','P14'} or purpose in LOCAL_PURPOSES:
        return {**base,'call_model':False,'rule_id':'LOCAL_OPERATION','model':None,'reasoning_effort':None,
                'service_tier':None,'capability':None,'override_applied':False}
    if role in REPORT_ROLES:
        require(purpose in {'DEFAULT','CONTENT','LAYOUT_ONLY'},'MODEL_POLICY_UNREGISTERED','Unknown report purpose')
        effort='high' if role=='REPORT_VISUAL' or purpose=='LAYOUT_ONLY' else 'xhigh'
        rule='SHARED_REPORT_'+('LAYOUT_ONLY' if purpose=='LAYOUT_ONLY' else role)
    else:
        effort=_EXCEPTIONS.get((stage_id,role,purpose))
        if effort is None:
            require(purpose in {'DEFAULT','BRIEF_ORGANIZATION'} and (purpose!='BRIEF_ORGANIZATION' or stage_id=='D0'),
                    'MODEL_POLICY_UNREGISTERED','Unknown task purpose; no generic effort fallback')
            effort=_ROWS.get(stage_id,{}).get(role)
        require(effort is not None,'MODEL_POLICY_UNREGISTERED','No default for this workflow/stage/role/purpose')
        rule=':'.join((workflow_kind,stage_id,role,purpose))
    config={'model':DEFAULT_MODEL,'reasoning_effort':effort,'service_tier':DEFAULT_TIER}
    applied=False
    if override:
        require(override.get('explicit') is True and override.get('scope')=={
            'workflow_kind':workflow_kind,'stage_id':stage_id,'role':role,'purpose':purpose},
            'AUTHORIZATION_REQUIRED','A future task override must explicitly match its full stage, role and purpose')
        fields=set(override)-{'explicit','scope','configuration_ref'}
        require(fields<={'model','reasoning_effort','service_tier'},'MODEL_POLICY_UNREGISTERED','Unknown model override field')
        config.update({k:override[k] for k in fields});applied=True
    capability=capability_check(config,capabilities) if require_capability else None
    return {**base,'call_model':True,'rule_id':rule,**config,'capability':capability,'override_applied':applied}


def schema():
    return {'$schema':'https://json-schema.org/draft/2020-12/schema','$id':VERSION,
            'title':'PMRS responsibility-bound model policy','type':'object','additionalProperties':False,
            'required':['policy_version','workflow_kind','stage_id','role','purpose','call_model','rule_id','model','reasoning_effort','service_tier','capability','override_applied'],
            'properties':{'policy_version':{'const':VERSION},'workflow_kind':{'enum':['TRW','TFDW']},
                'stage_id':{'enum':[f'P{i}' for i in range(15)]+[f'D{i}' for i in range(6)]},
                'role':{'type':'string'},'purpose':{'type':'string'},'call_model':{'type':'boolean'},
                'rule_id':{'type':'string'},'model':{'type':['string','null']},'reasoning_effort':{'type':['string','null']},
                'service_tier':{'type':['string','null']},'capability':{'type':['object','null']},'override_applied':{'type':'boolean'}},
            'x-runtime-policy':describe()}


def codex_arguments(config):
    """Explicit command values shared by the real and instrumented transports."""
    require(config.get('call_model') is True,'NO_MODEL_OPERATION','This is a local or human operation')
    import json
    return ['--model',config['model'],'-c','model_reasoning_effort='+json.dumps(config['reasoning_effort']),
            '-c','service_tier='+json.dumps(config['service_tier'])]


def validate_override(value):
    require(isinstance(value,dict) and value.get('explicit') is True,'MODEL_POLICY_INVALID','Explicit future configuration required')
    scope=value.get('scope',{})
    require(set(scope)=={'workflow_kind','stage_id','role','purpose'},'MODEL_POLICY_INVALID','Exact configuration scope required')
    resolve(scope['workflow_kind'],scope['stage_id'],scope['role'],scope['purpose'],override=value,require_capability=False)
    return value


def merge_overrides(existing,updates,*,reset_scopes=(),workflow_kind=None,capabilities=None):
    """Amend exact stage/role/purpose entries without replacing other entries."""
    require(isinstance(existing,list) and isinstance(updates,list) and isinstance(reset_scopes,(list,tuple)),
            'MODEL_POLICY_INVALID','Configuration updates and resets must be lists')
    def key(scope):
        require(isinstance(scope,dict) and set(scope)=={'workflow_kind','stage_id','role','purpose'},
                'MODEL_POLICY_INVALID','Exact configuration scope required')
        require(workflow_kind is None or scope['workflow_kind']==workflow_kind,
                'MODEL_POLICY_INVALID','Configuration belongs to another workflow kind')
        resolve(scope['workflow_kind'],scope['stage_id'],scope['role'],scope['purpose'],require_capability=False)
        return tuple(scope[k] for k in ('workflow_kind','stage_id','role','purpose'))
    merged={}
    for item in existing:
        validate_override(item);k=key(item['scope'])
        require(k not in merged,'MODEL_POLICY_INVALID','Duplicate existing configuration scope');merged[k]=deepcopy(item)
    reset_keys=[key(scope) for scope in reset_scopes]
    require(len(reset_keys)==len(set(reset_keys)),'MODEL_POLICY_INVALID','Duplicate reset scope')
    for k in reset_keys:merged.pop(k,None)
    seen=set()
    for item in updates:
        validate_override(item);k=key(item['scope'])
        require(k not in seen and k not in reset_keys,'MODEL_POLICY_INVALID','Duplicate or conflicting configuration update');seen.add(k)
        scope=item['scope']
        resolve(scope['workflow_kind'],scope['stage_id'],scope['role'],scope['purpose'],override=item,capabilities=capabilities)
        merged[k]=deepcopy(item)
    return [merged[k] for k in sorted(merged)]
