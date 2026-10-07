"""Compile built-in activity contracts once for every kernel consumer.

An available role is not a request to execute it. Activities only constrain an
already identified obligation; they never mint generic stage work.
"""
from copy import deepcopy
from ..util import identity, require
from .trw import STAGES as TRW
from .tfdw import STAGES as TFDW

REQUIRED = {'workflow_kind', 'stage_id', 'version', 'purpose', 'allowed_obligation_types',
            'roles', 'input_binding_rule_ids', 'output_contract_ids', 'empty_outcome_policy',
            'completion_rule_ids', 'exit_rules', 'reentry_rule_id', 'forbidden_effects',
            'ui_labels', 'prompt_sections', 'allowed_scientific_kinds'}
ROUTES = {'SOURCE_APPLICATION': ('LEARN',), 'DIRECT_ANALYSIS': ('DIRECT',),
          'COMPARATIVE': ('LEARN', 'DIRECT', 'SYNTHESIS')}
INDEPENDENT = {'PROOF', 'COUNTEREXAMPLE', 'INDEPENDENT', 'SPECIALIST',
               'FORMULATION_REVIEW', 'ADVERSARIAL_REVIEW', 'REPORT_SEMANTIC', 'REPORT_VISUAL'}

def compile_registry(rows=None):
    rows = deepcopy(TRW + TFDW if rows is None else rows)
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

def prompt(stage_id, role, intent, registry=None):
    row = spec(stage_id, registry); contract = role_contract(stage_id, role, registry)
    sections = {name: '' for name in row['prompt_sections']}
    sections['EXACT_TASK_INTENT'] = intent
    sections['ROLE_DUTY_AND_BOUNDARIES'] = row['purpose'] + '. Role: ' + role + '.'
    sections['EXPECTED_KNOWLEDGE_CHANGE'] = 'Allowed scientific kinds: ' + ', '.join(row['allowed_scientific_kinds']) + '. Zero records is valid when the actual attempt is accounted for.'
    sections['NO_AUTHORITY_PROMOTION'] = 'An accepted response is not proof certification. Preserve exact assumptions, quantifiers, unproved conditions and unchecked scope.'
    if contract['independent']:
        sections['ROLE_DUTY_AND_BOUNDARIES'] += ' Independently examine the frozen mathematical scope; never read prior review verdicts or their derivatives.'
    return {'stage_spec_digest': row['digest'], 'sections': sections,
            'ui_labels': row['ui_labels'], 'output_contract_ids': row['output_contract_ids']}
