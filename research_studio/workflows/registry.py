"""Native stage facade; runtime prompt assembly stays in legacy."""
from copy import deepcopy
from ..util import identity, require
from .trh import STAGES as TRH
from .fdh import STAGES as FDH
from .survey import STAGES as SURVEY
from pmrh.domain.protocols import (
    INDEPENDENT,
    REGISTRY,
    REQUIRED,
    ROUTES,
    _main_capabilities,
    compile_registry,
    definition,
    exit_allowed,
    role_contract,
    spec,
    validate_assignment,
    validate_exit,
)

def prompt(stage_id, role, intent, registry=None):
    row = spec(stage_id, registry); contract = role_contract(stage_id, role, registry)
    sections = {name: '' for name in row['prompt_sections']}
    from ..research_prompts import sections as scientific_sections
    sections.update(scientific_sections(stage_id, role))
    sections['EXACT_TASK_INTENT'] = intent
    sections['ROLE_DUTY_AND_BOUNDARIES'] = 'Stage ' + stage_id + ', role ' + role + ': perform the explicit SCIENTIFIC_WORK for this exact task; preserve its input and result boundaries.'
    sections['EXPECTED_KNOWLEDGE_CHANGE'] = 'Allowed scientific kinds: ' + ', '.join(row['allowed_scientific_kinds']) + '. Zero records is valid when the actual attempt is accounted for.'
    sections['NO_AUTHORITY_PROMOTION'] = 'An accepted response is not proof certification. Preserve exact assumptions, quantifiers, unproved conditions and unchecked scope.'
    if contract['independent']:
        sections['ROLE_DUTY_AND_BOUNDARIES'] += ' Independently examine the frozen mathematical scope; never read prior review verdicts or their derivatives.'
    return {'stage_spec_digest': row['digest'], 'sections': sections,
            'ui_labels': row['ui_labels'], 'output_contract_ids': row['output_contract_ids']}
