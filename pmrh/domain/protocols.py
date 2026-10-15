"""Compile built-in activity contracts once for every kernel consumer.

An available role is not a request to execute it. Activities only constrain an
already identified obligation; they never mint generic stage work.
"""
from copy import deepcopy
from .primitives import identity, require
from .stages import TRH, FDH, SURVEY

REQUIRED = {'workflow_kind', 'stage_id', 'version', 'purpose', 'allowed_obligation_types',
            'roles', 'input_binding_rule_ids', 'output_contract_ids', 'empty_outcome_policy',
            'completion_rule_ids', 'exit_rules', 'reentry_rule_id', 'forbidden_effects',
            'ui_labels', 'prompt_sections', 'allowed_scientific_kinds'}
ROUTES = {'SOURCE_APPLICATION': ('LEARN',), 'DIRECT_ANALYSIS': ('DIRECT',),
          'COMPARATIVE': ('LEARN', 'DIRECT', 'SYNTHESIS')}
INDEPENDENT = {'PROOF', 'COUNTEREXAMPLE', 'INDEPENDENT', 'SPECIALIST',
               'FORMULATION_REVIEW', 'ADVERSARIAL_REVIEW', 'REPORT_SEMANTIC', 'REPORT_VISUAL', 'READINESS_REVIEW', 'COVERAGE_REVIEW'}

def _main_capabilities():
    """Control capabilities, not an automatically selected scientific stage."""
    result=[]
    for kind,stages,account in [('TRH',TRH,'P11'),('FDH',FDH,'D5')]:
        row=deepcopy(next(s for s in stages if s['stage_id']==account))
        row.update(stage_id='MAIN_'+kind,version='pmrs.harness-main/4.2.2',
            purpose='Continuing '+kind+' MAIN: decide, research, communicate and account within the fixed scope',
            allowed_obligation_types=['ACCOUNT','CONTROL'],
            roles=[{'role':'MAIN_DECIDE','required_when':'WHEN_ASSIGNED_BY_OBLIGATION','independent':False,
                    'forbidden_context_classes':[],'payload_kinds':['KNOWLEDGE_CHANGE']}],
            allowed_scientific_kinds=['Context','Statement','Argument','Example','SourceEvidence','Assessment'],
            ui_labels={'zh-CN':kind+' MAIN 研究决策','en':kind+' MAIN research decision'})
        row['exit_rules']={'forward':[],'return':[],'early_delivery':None,
            'required':['NO_AUTHORITY_PROMOTION','UNPERFORMED_DUTIES_PERSIST'],'automatic_next':False}
        row['forbidden_effects']=['NO_TARGET_REWRITE','NO_UNAUTHORIZED_BUDGET','NO_AUTHORITY_PROMOTION']
        result.append(row)
    return result

def compile_registry(rows=None):
    rows = deepcopy(TRH + FDH + SURVEY + _main_capabilities() if rows is None else rows)
    compiled = {}
    for row in rows:
        require(REQUIRED <= row.keys(), 'STAGE_SPEC_INVALID', 'Missing activity contract fields')
        key = row['stage_id']
        require(key not in compiled, 'STAGE_SPEC_INVALID', 'Duplicate activity')
        require(row['exit_rules'].get('automatic_next') is False, 'STAGE_SPEC_INVALID', 'Automatic transitions are forbidden')
        require(row['reentry_rule_id'] == 'OBLIGATION_PURPOSE_INPUT_AND_GRANTED_RETRY', 'STAGE_SPEC_INVALID', 'Unbounded reentry')
        roles = [r['role'] for r in row['roles']]
        require(len(set(roles)) == len(roles) and 'TASK_CHECK' not in roles,
                'STAGE_SPEC_INVALID', 'Role duplication or obsolete generic review')
        row['digest'] = identity(row, 'STAGE-')
        compiled[key] = row
    for row in compiled.values():
        edges = row['exit_rules']['forward'] + row['exit_rules']['return']
        if row['exit_rules'].get('early_delivery'): edges += [row['exit_rules']['early_delivery']]
        for target in edges:
            require(target in compiled and compiled[target]['workflow_kind'] == row['workflow_kind'],
                    'STAGE_SPEC_INVALID', 'Activity edge leaves its workflow')
    return {'schema': 'pmrs.stage-registry/1', 'digest': identity(rows, 'REGISTRY-'), 'stages': compiled}

REGISTRY = compile_registry()

def spec(stage_id, registry=None):
    rows = (registry or REGISTRY)['stages']
    require(stage_id in rows, 'STAGE_SPEC_INVALID', 'Unknown activity: ' + str(stage_id))
    return deepcopy(rows[stage_id])

def definition():
    return deepcopy(REGISTRY)

def role_contract(stage_id, role, registry=None):
    row = spec(stage_id, registry)
    matches = [r for r in row['roles'] if r['role'] == role]
    require(bool(matches), 'STAGE_ROLE_FORBIDDEN', role)
    return matches[0]

def validate_assignment(stage_id, obligation_type, role, entry_basis, *, registry=None):
    row = spec(stage_id, registry)
    require(obligation_type in row['allowed_obligation_types'], 'STAGE_OBLIGATION_FORBIDDEN', obligation_type)
    contract = role_contract(stage_id, role, registry)
    condition = contract['required_when']
    if condition.startswith('ANALYSIS_ROUTE_'):
        route = entry_basis.get('analysis_route')
        require(route in ROUTES, 'ANALYSIS_ROUTE_REQUIRED', 'Freeze the analysis route on the visit and request')
        require(role in ROUTES[route], 'STAGE_ROLE_FORBIDDEN', 'Role is outside the selected analysis route')
        if role == 'SYNTHESIS':
            branches = entry_basis.get('synthesis_branches')
            if branches is not None:
                require(isinstance(branches, list) and 2 <= len(branches) <= 32
                        and {b.get('role') for b in branches} >= {'LEARN', 'DIRECT'}
                        and all(b.get('stage_id') == 'P7' and b.get('binding_id') and b.get('obligation_id') for b in branches)
                        and len({b['binding_id'] for b in branches}) == len(branches),
                        'DEPENDENCY_PENDING', 'Freeze every selected transfer and direct branch for comparative synthesis')
            else:
                require(set(entry_basis.get('branch_dispositions', {})) >= {'LEARN', 'DIRECT'},
                        'DEPENDENCY_PENDING', 'Comparative synthesis requires both independent dispositions')
    elif condition.startswith('SCOPED_SINGLE_'):
        requirement = entry_basis.get('consumer_requirement', {})
        require(obligation_type == 'VERIFY' and entry_basis.get('dependency_threshold') == 'SUPPORT_QUALIFIED'
                and requirement.get('review_mode') == 'SCOPED_SINGLE', 'VERIFY_NOT_REQUIRED', 'An explicit local support consumer is required')
        purpose = 'REFUTATION_SUPPORT' if role == 'COUNTEREXAMPLE' else 'PROOF_SUPPORT'
        require(requirement.get('purpose') == purpose, 'STAGE_ROLE_FORBIDDEN', 'Local review must match its support purpose')
    elif condition == 'TARGET_DUAL_FOR_FORMAL_FIXED_TARGET_OR_EXPLICIT_ESCALATED_SCOPE':
        require(entry_basis.get('consumer_requirement', {}).get('review_mode') == 'TARGET_DUAL',
                'REVIEW_MODE_REQUIRED', 'Freeze the formal target or escalated dual review requirement')
    elif condition == 'OPTIONAL_EXPLICITLY_AUTHORIZED_SCOPE':
        require(role in entry_basis.get('authorized_optional_roles', []), 'AUTHORIZATION_REQUIRED', 'Optional specialist scope not authorized')
    elif condition == 'FORMAL_REPORT_REQUESTED_WITH_AUTHORIZED_REPORT_BUDGET':
        require(entry_basis.get('formal_report_requested') is True, 'AUTHORIZATION_REQUIRED', 'Formal report not requested')
    elif condition == 'EXPLICIT_ACCOUNT_DUTY_NOT_REQUIRED_FOR_HOST_SNAPSHOT':
        require(obligation_type == 'ACCOUNT', 'STAGE_OBLIGATION_FORBIDDEN', 'Host snapshot needs no model author')
    return {'stage_spec_digest': row['digest'], 'role_contract': contract}

def exit_allowed(stage_id, target, registry=None):
    row = spec(stage_id, registry)
    return target in row['exit_rules']['forward'] + row['exit_rules']['return'] + [row['exit_rules'].get('early_delivery')]

def validate_exit(visit, disposition, registry=None):
    required = {'visit_id', 'outcome', 'completed_work_bindings', 'open_mathematical_bindings',
                'unperformed_bindings', 'next_activity_proposal', 'reason_ref'}
    require(required <= disposition.keys() and disposition['visit_id'] == visit['visit_id'],
            'EXIT_DISPOSITION_REQUIRED', 'Exact work and open scope must be accounted for')
    require(disposition['outcome'] in {'FULFILLED_FOR_SCOPE', 'INVESTIGATED_OPEN', 'BLOCKED', 'DEFERRED_WITH_REASON'}
            and bool(disposition['reason_ref']), 'EXIT_DISPOSITION_REQUIRED', 'Honest activity disposition required')
    assigned = {identity(b) for b in visit['assigned_obligation_bindings']}
    accounted = {identity(b) for k in ('completed_work_bindings', 'open_mathematical_bindings', 'unperformed_bindings') for b in disposition[k]}
    require(assigned <= accounted, 'EXIT_DISPOSITION_REQUIRED', 'No assigned responsibility may disappear')
    target = disposition['next_activity_proposal']
    if target: require(exit_allowed(visit['stage_id'], target, registry), 'TRANSITION_FORBIDDEN', str(target))
    return deepcopy(disposition)



DISCOVERY_FIELDS={'phenomenon_ref':'现象','immutable_background_ref':'不可改变的背景','allowed_axes_ref':'允许探索的范围'}

def validate_discovery_scope(snapshot,instance,*,required=True):
    if instance['kind']!='FDH':return {}
    scope=instance.get('discovery_scope') or {}
    require(isinstance(scope,dict) and not set(scope)-set(DISCOVERY_FIELDS),'DISCOVERY_SCOPE_INVALID','Unknown discovery scope field')
    for key,label in DISCOVERY_FIELDS.items():
        ref=scope.get(key)
        require(not required or ref,'DISCOVERY_SCOPE_REQUIRED','请补齐'+label+'；若无附加限制，请由用户明确说明。')
        if ref:
            source=snapshot.get('sources',{}).get(ref)
            require(source is not None and source.get('access_class','SCIENTIFIC_SOURCE')=='SCIENTIFIC_SOURCE'
                    and source.get('bytes',0)>0,'DISCOVERY_SCOPE_INVALID',label+'必须引用完整保存的用户原文。')
    if scope.get('phenomenon_ref'):
        require(scope['phenomenon_ref']==instance.get('discovery_brief_ref'),'DISCOVERY_SCOPE_INVALID','Phenomenon and discovery brief must bind the same original source')
    return deepcopy(scope)

def completion_evidence(snapshot, instance_id, refs):
    """Exact original-target dual checks and global integration, never MAIN confidence."""
    from . import assurance
    target=snapshot['instances'][instance_id]['target_ref'];qualified=[]
    for sid,support in snapshot.get('supports',{}).items():
        argument=support.get('argument_ref')
        if support.get('statement_ref')!=target or argument not in refs:continue
        scope=[]
        for ref,aspect in ((target,'original_target'),(argument,'full_argument')):
            match=None
            for record in snapshot.get('records',{}).values():
                if record.get('kind')!='Assessment':continue
                for row in assurance.checked_scope(record):
                    if (row['target_ref']==ref and aspect in row['aspects'] and row.get('extent')=='WHOLE_TARGET'
                        and row.get('target_body_sha256')==snapshot['records'][ref]['body_sha256']):
                        match={**deepcopy(row),'aspects':[aspect]};break
                if match:break
            if match:scope.append(match)
        if len(scope)!=2:continue
        mode=snapshot['records'][argument]['data'].get('mode')
        req=assurance.requirement('REFUTATION_SUPPORT' if mode=='REFUTATION' else 'PROOF_SUPPORT',scope,
            review_mode='TARGET_DUAL',assumption_policy=assurance.declared_assumption_policy(snapshot,target,argument))
        evaluation=assurance.evaluate_requirement(snapshot,sid,req)
        if evaluation['result']!='QUALIFIED' or evaluation.get('open_conditions'):continue
        # A newly integrated global argument retains its extra integration duty.
        integration_needed=any(v.get('argument_ref')==argument and v.get('kind') in {'AND_INTEGRATION','GLOBAL_ASSEMBLY'}
                               for v in snapshot.get('inferences',{}).values())
        if integration_needed:
            integrated=assurance.evaluate_requirement(snapshot,sid,assurance.requirement('INTEGRATION',scope))
            if integrated['result']!='QUALIFIED':continue
        qualified.append({'support_id':sid,'argument_ref':argument,'target_ref':target,'assurance':evaluation})
    return qualified
