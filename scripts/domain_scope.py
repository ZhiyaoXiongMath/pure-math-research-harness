"""Exact DEV04 extraction boundary. No directory or inferred edge allowances."""
import ast

SYMBOLS = {'research_studio/assurance.py': ['ASSUMPTION_POLICY',
                                  'CONDITION_ROLES',
                                  'PATHS',
                                  'PURPOSES',
                                  'SCOPE_META',
                                  'SCOPE_VERSION',
                                  'STAGE_ROLES',
                                  '_assumption_evaluation',
                                  '_credential',
                                  '_execution',
                                  '_intervals',
                                  '_part_consumable',
                                  '_scope_regions',
                                  '_structural_support_conditions',
                                  'checked_scope',
                                  'condition_evidence',
                                  'coverage',
                                  'coverage_plan_evidence',
                                  'declared_assumption_policy',
                                  'evaluate',
                                  'evaluate_requirement',
                                  'normalize_requirement',
                                  'normalize_scope',
                                  'requirement',
                                  'scope_overlaps',
                                  'validate_assumption_policy',
                                  'validate_requirement',
                                  'validate_scope'],
 'research_studio/changes.py': ['validator_identity'],
 'research_studio/communication.py': ['independence_status'],
 'research_studio/context.py': ['aggregate_coverage', 'validate_budget', 'validate_coverage_plan'],
 'research_studio/contracts.py': ['ASSURANCE_FIELDS',
                                  'AUTHORING_REVISION',
                                  'CHANGE_SCHEMA',
                                  'CONTEXT_BUDGET_FIELDS',
                                  'DATA_FIELDS',
                                  'ENVELOPE_FIELDS',
                                  'HASH',
                                  'INFERENCE_FIELDS',
                                  'KCS_FIELDS',
                                  'KCS_OPTIONAL_FIELDS',
                                  'KINDS',
                                  'LOCAL_KEY',
                                  'LOCATOR_FIELDS',
                                  'MAX_BODY',
                                  'MAX_DEPTH',
                                  'MAX_INT',
                                  'MAX_PAYLOAD',
                                  'OBLIGATION_TYPES',
                                  'OP_FIELDS',
                                  'PREMISE_ENDPOINTS',
                                  'PREMISE_FIELDS',
                                  'RECORD_FIELDS',
                                  'RECORD_SCHEMA',
                                  'SCIENCE_PROJECTION_REVISION',
                                  'SCOPE_FIELDS',
                                  'SLOT_FIELDS',
                                  'SOURCE_MODES',
                                  'SOURCE_USE_FIELDS',
                                  'bounded_json',
                                  'digest',
                                  'enum',
                                  'fields',
                                  'inference_identity',
                                  'optional_fields',
                                  'refs',
                                  'scientific_identity',
                                  'sequence',
                                  'validate_tree'],
 'research_studio/knowledge.py': ['_locs',
                                  '_ref',
                                  'derive_inference',
                                  'identify',
                                  'locator',
                                  'make_record',
                                  'result_family',
                                  'source_use',
                                  'validate_locator',
                                  'validate_mode_payload',
                                  'validate_record'],
 'research_studio/language.py': ['authored_english', 'authored_with_quotes', 'research_data'],
 'research_studio/relations.py': ['FIELDS',
                                  'PREMISES',
                                  'REGISTRY',
                                  'TYPES',
                                  '_acyclic',
                                  'acyclic',
                                  'affected_supports',
                                  'closure',
                                  'edges',
                                  'is_premise',
                                  'kind_of',
                                  'premise_closure',
                                  'relation',
                                  'validate_relation',
                                  'validate_support_graph'],
 'research_studio/util.py': ['MAX_JSON',
                             'PMRSError',
                             'ResearchStudioError',
                             'canonical',
                             'identity',
                             'loads',
                             'require',
                             'sha',
                             'sha256_bytes'],
 'research_studio/workflow_instances.py': ['DISCOVERY_FIELDS',
                                           'completion_evidence',
                                           'validate_discovery_scope'],
 'research_studio/workflows/fdh.py': ['STAGES', 'activity_for_obligation'],
 'research_studio/workflows/registry.py': ['INDEPENDENT',
                                           'REGISTRY',
                                           'REQUIRED',
                                           'ROUTES',
                                           '_main_capabilities',
                                           'compile_registry',
                                           'definition',
                                           'exit_allowed',
                                           'role_contract',
                                           'spec',
                                           'validate_assignment',
                                           'validate_exit'],
 'research_studio/workflows/survey.py': ['STAGES', 'activity_for_obligation'],
 'research_studio/workflows/trh.py': ['STAGES', 'activity_for_obligation']}

IMPORTS = {'research_studio/assurance.py': ['from pmrh.domain.assurance import ASSUMPTION_POLICY, '
                                  'CONDITION_ROLES, PATHS, PURPOSES, SCOPE_META, SCOPE_VERSION, '
                                  'STAGE_ROLES, _assumption_evaluation, _credential, _execution, '
                                  '_intervals, _part_consumable, _scope_regions, '
                                  '_structural_support_conditions, checked_scope, '
                                  'condition_evidence, coverage, coverage_plan_evidence, '
                                  'declared_assumption_policy, evaluate, evaluate_requirement, '
                                  'normalize_requirement, normalize_scope, requirement, '
                                  'scope_overlaps, validate_assumption_policy, '
                                  'validate_requirement, validate_scope'],
 'research_studio/changes.py': [],
 'research_studio/communication.py': ['from pmrh.domain.assurance import independence_status'],
 'research_studio/context.py': ['from pmrh.domain.assurance import aggregate_coverage, '
                                'validate_budget, validate_coverage_plan'],
 'research_studio/contracts.py': ['from pmrh.domain.contracts import ASSURANCE_FIELDS, '
                                  'AUTHORING_REVISION, CHANGE_SCHEMA, CONTEXT_BUDGET_FIELDS, '
                                  'DATA_FIELDS, ENVELOPE_FIELDS, HASH, INFERENCE_FIELDS, '
                                  'KCS_FIELDS, KCS_OPTIONAL_FIELDS, KINDS, LOCAL_KEY, '
                                  'LOCATOR_FIELDS, MAX_BODY, MAX_DEPTH, MAX_INT, MAX_PAYLOAD, '
                                  'OBLIGATION_TYPES, OP_FIELDS, PREMISE_ENDPOINTS, PREMISE_FIELDS, '
                                  'RECORD_FIELDS, RECORD_SCHEMA, SCIENCE_PROJECTION_REVISION, '
                                  'SCOPE_FIELDS, SLOT_FIELDS, SOURCE_MODES, SOURCE_USE_FIELDS, '
                                  'bounded_json, digest, enum, fields, inference_identity, '
                                  'optional_fields, refs, scientific_identity, sequence, '
                                  'validate_tree'],
 'research_studio/knowledge.py': ['from pmrh.domain.knowledge import _locs, _ref, '
                                  'derive_inference, identify, locator, make_record, '
                                  'result_family, source_use, validate_locator, '
                                  'validate_mode_payload, validate_record'],
 'research_studio/language.py': ['from pmrh.domain.primitives import authored_english, '
                                 'authored_with_quotes, research_data'],
 'research_studio/relations.py': ['from pmrh.domain.relations import FIELDS, PREMISES, REGISTRY, '
                                  'TYPES, _acyclic, acyclic, affected_supports, closure, edges, '
                                  'is_premise, kind_of, premise_closure, relation, '
                                  'validate_relation, validate_support_graph'],
 'research_studio/util.py': ['from pmrh.domain.primitives import MAX_JSON, PMRSError, '
                             'ResearchStudioError, canonical, identity, loads, require, sha, '
                             'sha256_bytes'],
 'research_studio/workflow_instances.py': ['from pmrh.domain.protocols import DISCOVERY_FIELDS, '
                                           'completion_evidence, validate_discovery_scope'],
 'research_studio/workflows/fdh.py': ['from pmrh.domain.stages import FDH as STAGES, '
                                      'fdh_activity_for_obligation as activity_for_obligation'],
 'research_studio/workflows/registry.py': ['from pmrh.domain.protocols import INDEPENDENT, '
                                           'REGISTRY, REQUIRED, ROUTES, _main_capabilities, '
                                           'compile_registry, definition, exit_allowed, '
                                           'role_contract, spec, validate_assignment, '
                                           'validate_exit'],
 'research_studio/workflows/survey.py': ['from pmrh.domain.stages import SURVEY as STAGES, '
                                         'survey_activity_for_obligation as '
                                         'activity_for_obligation'],
 'research_studio/workflows/trh.py': ['from pmrh.domain.stages import TRH as STAGES, '
                                      'trh_activity_for_obligation as activity_for_obligation']}

FACADES = frozenset({'research_studio/assurance.py',
           'research_studio/knowledge.py',
           'research_studio/relations.py',
           'research_studio/workflows/fdh.py',
           'research_studio/workflows/survey.py',
           'research_studio/workflows/trh.py'})

EDGES = frozenset({('research_studio/assurance.py', 'pmrh/domain/assurance.py'),
           ('research_studio/communication.py', 'pmrh/domain/assurance.py'),
           ('research_studio/context.py', 'pmrh/domain/assurance.py'),
           ('research_studio/contracts.py', 'pmrh/domain/contracts.py'),
           ('research_studio/knowledge.py', 'pmrh/domain/knowledge.py'),
           ('research_studio/language.py', 'pmrh/domain/primitives.py'),
           ('research_studio/relations.py', 'pmrh/domain/relations.py'),
           ('research_studio/util.py', 'pmrh/domain/primitives.py'),
           ('research_studio/workflow_instances.py', 'pmrh/domain/protocols.py'),
           ('research_studio/workflows/fdh.py', 'pmrh/domain/stages.py'),
           ('research_studio/workflows/registry.py', 'pmrh/domain/protocols.py'),
           ('research_studio/workflows/survey.py', 'pmrh/domain/stages.py'),
           ('research_studio/workflows/trh.py', 'pmrh/domain/stages.py')})



def verify_sections(path, original, current):
    before, after = ast.parse(original), ast.parse(current)
    # Compose only the exact DEV11 reexports, then retain every DEV04 check.
    # The caller-supplied current bytes must pass the root-pinned stage too.
    fastmath_scope = None
    if path in ('research_studio/changes.py', 'research_studio/contracts.py'):
        if __package__:
            from scripts import fastmath_scope as fast_scope
        else:
            import fastmath_scope as fast_scope
        reexports = {ast.dump(ast.parse(row).body[0], include_attributes=False)
                     for row in fast_scope.SCOPE04_REEXPORTS[path]}
        if any(ast.dump(n, include_attributes=False) in reexports for n in after.body):
            fastmath_scope = fast_scope
            before.body = [n for n in before.body
                           if ast.dump(n, include_attributes=False) not in reexports]
            after.body = [n for n in after.body
                          if ast.dump(n, include_attributes=False) not in reexports]
    allowed_imports = {ast.dump(ast.parse(row).body[0], include_attributes=False)
                       for row in IMPORTS[path]}
    def dump(node):
        return ast.dump(node, include_attributes=False)
    def doc(node):
        return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
    actual = {dump(n) for n in after.body if isinstance(n, ast.ImportFrom)
              and (n.module or '').startswith('pmrh.domain.')}
    if actual != allowed_imports:
        raise ValueError('DEV04 facade imports differ: ' + path)
    if path in FACADES:
        if any(not doc(n) and dump(n) not in allowed_imports for n in after.body):
            raise ValueError('DEV04 facade retains or introduces implementation: ' + path)
        return
    if path != 'research_studio/changes.py':
        for node in after.body:
            names = {node.name} if isinstance(node, (ast.FunctionDef, ast.ClassDef)) else {
                target.id for target in node.targets if isinstance(target, ast.Name)
            } if isinstance(node, ast.Assign) else set()
            if names & set(SYMBOLS[path]):
                raise ValueError('Moved domain implementation remains in legacy: ' + path)
    def trim(tree, extra=()):
        result=[]
        for n in tree.body:
            if doc(n) or dump(n) in extra:
                continue
            names = {n.name} if isinstance(n, (ast.FunctionDef, ast.ClassDef)) else {
                target.id for target in n.targets if isinstance(target, ast.Name)
            } if isinstance(n, ast.Assign) else set()
            if names and names <= set(SYMBOLS[path]):
                continue
            result.append(dump(n))
        return result
    if trim(before) != trim(after, allowed_imports):
        raise ValueError('Non-domain legacy section changed: ' + path)
    if fastmath_scope is not None:
        try:
            fastmath_scope.preintegration(path, current.encode() if isinstance(current, str) else current)
        except ValueError as exc:
            raise ValueError('Non-domain legacy section changed: ' + path) from exc
