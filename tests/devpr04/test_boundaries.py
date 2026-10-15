"""Extraction and application-boundary checks on synthetic data only."""
import ast
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pmrh.domain import assurance as A, contracts as C, knowledge as K, protocols as P, relations as R
from pmrh.domain.primitives import PMRSError
from research_studio import changes, workflow_instances as W
from scripts import architecture_deps as deps, domain_scope
from tests.test_final_kernel import Fixture, statement, AssuranceContextTests

ROOT = Path(__file__).resolve().parents[2]


class ExtractionBoundaries(unittest.TestCase):
    def test_single_implementation_and_error_identity(self):
        from research_studio import assurance, contracts, knowledge, relations, context, communication, util
        for old, new, names in [(assurance, A, ('evaluate_requirement', '_credential', 'coverage_plan_evidence')),
                                (contracts, C, ('scientific_identity', 'bounded_json')),
                                (knowledge, K, ('make_record', 'validate_record', 'derive_inference')),
                                (relations, R, ('affected_supports', 'validate_support_graph')),
                                (W, P, ('completion_evidence', 'validate_discovery_scope')),
                                (context, A, ('aggregate_coverage', 'validate_coverage_plan', 'validate_budget')),
                                (communication, A, ('independence_status',))]:
            for name in names:
                self.assertIs(getattr(old, name), getattr(new, name))
        self.assertIs(util.PMRSError, PMRSError)
        self.assertIs(util.ResearchStudioError, PMRSError)
        with self.assertRaises(util.PMRSError):
            C.fields({'unknown': 1}, set())

    def test_fingerprint_tracks_every_domain_file(self):
        before = changes.validator_identity()
        paths = sorted((ROOT/'pmrh/domain').glob('*.py'))
        self.assertTrue(paths)
        real = Path.read_bytes
        for path in paths:
            def modified(p, target=path):
                return real(p) + (b'\n# synthetic mutation\n' if p == target else b'')
            with patch.object(Path, 'read_bytes', modified):
                after = changes.validator_identity()
            name = 'pmrh/domain/' + path.name
            self.assertNotEqual(before['modules'][name], after['modules'][name])
            self.assertEqual(set(before['modules']), set(after['modules']))
            self.assertEqual([k for k in before['modules'] if before['modules'][k] != after['modules'][k]], [name])

    def test_architecture_rejects_forbidden_edges_io_and_blanket_allowance(self):
        policy = json.loads((ROOT/'config/architecture-exceptions.json').read_text())
        for change in ('path', 'edge', 'owner'):
            bad = deepcopy(policy)
            if change == 'path': bad['devpr04_domain_bridge']['changed_paths'].append('research_studio/')
            elif change == 'edge': bad['devpr04_domain_bridge']['direct_edges'][0]['target'] = 'pmrh/domain/'
            else: bad['devpr04_domain_bridge']['direct_edges'][0]['owner'] = 'unspecified'
            self.assertIn('invalid_devpr04_extraction_allowlist', {v['reason'] for v in deps.run(ROOT, bad)['architecture_violations']})
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for file in ('pmrh/__init__.py', 'pmrh/domain/__init__.py', 'pmrh/ports/__init__.py',
                         'pmrh/application/__init__.py', 'research_studio/__init__.py'):
                p = root/file; p.parent.mkdir(parents=True, exist_ok=True); p.write_text('')
            source = root/'pmrh/domain/probe.py'
            for text, reason in [
                ('import research_studio', 'new_package_may_not_depend_on_legacy'),
                ('import pmrh.ports', 'forbidden_new_layer_direction'),
                ('import pmrh.application', 'forbidden_new_layer_direction'),
                ('import subprocess', 'prohibited_capability_import'),
                ('import socket', 'prohibited_capability_import'),
                ('import pathlib', 'prohibited_capability_import'),
                ('import openai', 'prohibited_capability_import'),
                ("open('synthetic')", 'domain_io_or_dynamic_execution')]:
                source.write_text(text)
                self.assertIn(reason, {v['reason'] for v in deps.run(root, policy)['architecture_violations']}, text)

    def test_exact_symbol_allowance_does_not_admit_mixed_writer_edits(self):
        for path, symbol in [('research_studio/changes.py', '_validate'),
                             ('research_studio/workflow_instances.py', 'apply_control'),
                             ('research_studio/context.py', 'build_packet'),
                             ('research_studio/communication.py', 'apply_event'),
                             ('research_studio/util.py', 'immutable')]:
            raw = (ROOT/path).read_text()
            tree = ast.parse(raw); node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == symbol)
            original = ast.unparse(ast.Module(body=[n for n in tree.body if not (isinstance(n, ast.ImportFrom) and (n.module or '').startswith('pmrh.domain.'))], type_ignores=[]))
            domain_scope.verify_sections(path, original, raw)
            lines = raw.splitlines(keepends=True); lines.insert(node.body[0].lineno-1, '    unauthorized_writer_change = True\n')
            with self.assertRaisesRegex(ValueError, 'Non-domain legacy section changed'):
                domain_scope.verify_sections(path, original, ''.join(lines))
        raw = (ROOT/'research_studio/knowledge.py').read_text()
        with self.assertRaisesRegex(ValueError, 'retains or introduces implementation'):
            domain_scope.verify_sections('research_studio/knowledge.py', raw, raw+'\ndef duplicate_rule(): return True\n')
        raw = (ROOT/'research_studio/contracts.py').read_text()
        with self.assertRaisesRegex(ValueError, 'Moved domain implementation remains'):
            domain_scope.verify_sections('research_studio/contracts.py', raw,
                raw+'\ndef fields(value, expected, label="object"): return value\n')

    def test_slots_require_distinct_execution_and_coverage_requires_integration(self):
        helper = AssuranceContextTests(); f, target, arg, sid, scope = helper.build()
        req = A.requirement('WORK_CHECK', scope)
        req['review_slots'].append({**deepcopy(req['review_slots'][0]), 'slot_id': 'second'})
        helper.review(f, sid, scope, role='WORK_CHECK', kind='WORK_CHECK', event_id='one')
        self.assertNotEqual(A.evaluate_requirement(f.s, sid, req, 'p')['result'], 'QUALIFIED')
        helper.review(f, sid, scope, role='WORK_CHECK', kind='WORK_CHECK', event_id='two')
        self.assertEqual(A.evaluate_requirement(f.s, sid, req, 'p')['result'], 'QUALIFIED')
        single = A.requirement('PROOF_SUPPORT', scope)
        plan = {'plan_id': 'P', 'target_revision_refs': [arg], 'required_scope': scope,
                'parts': [{'part_id': 'part', 'review_slot_id': 'proof', 'checked_scope': scope,
                           'required_input_refs': [arg], 'declared_boundary_refs': [], 'task_ref': 'part-task'}],
                'integration_scope': scope}
        results = {'part': {'result': 'QUALIFIED', 'checked_scope': scope}}
        self.assertEqual(A.aggregate_coverage(plan, single, results)['result'], 'PARTIAL')
        self.assertEqual(A.aggregate_coverage(plan, single, results,
            {'result': 'QUALIFIED', 'independent': True, 'checked_scope': scope})['result'], 'QUALIFIED')

    def test_paused_capture_is_not_main_authority(self):
        f = Fixture(); target = f.add(statement()); task = f.task([target])
        task['instance_id'] = 'I'
        f.s['instances'] = {'I': {'kind': 'TRH', 'target_ref': target, 'status': 'PAUSED'}}
        f.s['requests'][task['request_id']] = {'task_id': task['task_id'], 'instance_id': 'I',
            'execution_state': 'CAPTURED', 'capture_ref': 'synthetic-sealed-bytes'}
        self.assertTrue(changes.live_check(task, f.s, f.get))
        for field, value in [('actor_kind', 'MAIN')]:
            with self.assertRaisesRegex(PMRSError, 'TASK_FENCED'):
                changes.live_check({**task, field: value}, f.s, f.get)
        f.s['requests'][task['request_id']]['fenced'] = True
        with self.assertRaisesRegex(PMRSError, 'TASK_FENCED'):
            changes.live_check(task, f.s, f.get)

    def test_p13_p14_and_ordinary_versus_formal_d5(self):
        def fixture(kind='TRH'):
            return {'instances': {'I': {'kind': kind, 'target_ref': 'KR-original', 'status': 'ACTIVE',
                'run_control': {'mode': 'AUTO_P14', 'control_version': 0, 'round_number': 1,
                                'automatic_authorization_ref': 'human-grant'}}}, 'missions': {'M': {}}}
        task = {'actor_kind': 'MAIN', 'instance_id': 'I', 'mission_id': 'M', 'request_id': 'R'}
        request = {'request_id': 'R', 'capture_ref': 'sealed'}
        proposal = {'progress_account': {'summary': ''}, 'p14_decision': {'action': 'CONTINUE', 'rationale': 'Same original goal.'}}
        with self.assertRaisesRegex(PMRSError, 'ROUND_REPORT_REQUIRED'):
            W.apply_p14_decision(fixture(), task, request, proposal, 'proposal')
        proposal['p14_decision']['report_body'] = 'The original target remains open; the stated duties remain.'
        s = fixture(); result = W.apply_p14_decision(s, task, request, proposal, 'proposal')
        self.assertTrue(result['allow_dispatch']); self.assertEqual(len(s['round_deliveries']), 1)
        self.assertEqual(s['instances']['I']['target_ref'], 'KR-original')
        s = fixture(); s['instances']['I']['run_control']['stop_request'] = {'status': 'PENDING'}
        self.assertFalse(W.apply_p14_decision(s, task, request, proposal, 'proposal')['allow_dispatch'])
        self.assertEqual(s['instances']['I']['status'], 'PAUSED')
        s = fixture('FDH'); W.preserve_main_report(s, task, request, proposal, 'progress')
        self.assertEqual(s['instances']['I']['status'], 'ACTIVE')
        result = W.apply_p14_decision(s, task, request, proposal, 'formal')
        self.assertEqual(result['state'], 'WAITING_HUMAN_AT_D5'); self.assertFalse(result['allow_dispatch'])
        # A later ordinary report cannot act as human continuation.
        W.preserve_main_report(s, task, request, proposal, 'late')
        self.assertEqual(s['instances']['I']['status'], 'PAUSED')

    def test_registry_dynamic_duties_share_declarations_and_digest(self):
        from research_studio.workflows import registry as legacy, trh, fdh, survey
        from pmrh.domain import stages
        self.assertIs(trh.STAGES, stages.TRH)
        self.assertIs(fdh.STAGES, stages.FDH)
        self.assertIs(survey.STAGES, stages.SURVEY)
        self.assertIs(legacy.REGISTRY, P.REGISTRY)
        self.assertEqual(set(P.REGISTRY['stages']),
            {f'P{i}' for i in range(15)} | {f'D{i}' for i in range(6)} |
            {f'S{i}' for i in range(8)} | {'MAIN_TRH', 'MAIN_FDH'})
        rows = deepcopy(list(P.REGISTRY['stages'].values()))
        for row in rows: row.pop('digest')
        p4 = next(r for r in rows if r['stage_id'] == 'P4')
        p4['allowed_scientific_kinds'] = ['Example']
        changed = P.compile_registry(rows)
        prompt = legacy.prompt('P4', 'RESEARCH', 'Synthetic exact scope.', changed)
        self.assertEqual(prompt['stage_spec_digest'], changed['stages']['P4']['digest'])
        self.assertNotEqual(prompt['stage_spec_digest'], P.spec('P4')['digest'])
        self.assertIn('Allowed scientific kinds: Example', prompt['sections']['EXPECTED_KNOWLEDGE_CHANGE'])
        self.assertTrue(P.exit_allowed('P8', 'P6'))
        self.assertFalse(any(r['exit_rules']['automatic_next'] for r in rows))
        p4['exit_rules']['automatic_next'] = True
        with self.assertRaisesRegex(PMRSError, 'STAGE_SPEC_INVALID'): P.compile_registry(rows)

    def test_excerpt_delivery_pure_packet_excludes_unread_backing(self):
        from tests.test_consumer_input_plans import ConsumerInputPlans
        from research_studio import input_plans, context, obligations
        helper = ConsumerInputPlans(); f, target, consumer = helper.fixture()
        raw = b'Opening definitions.\nExact required theorem.\nUnused later discussion.\n'
        source = helper.source(f, raw); loc = K.locator(raw, 21, 44)
        consumer['source_refs'] = [source]
        consumer['source_selections'] = {source: {'coverage': 'DECLARED_RANGE', 'locators': [loc], 'reason': 'Only this exact passage.'}}
        obligation = obligations.make('O', 'COMPARE', [target], 'criterion')
        before = deepcopy((f.s, consumer))
        plan = input_plans.build(f.s, obligation, consumer, blob_get=f.get)
        packet = context.build_packet(f.s, plan['roots'], f.get, required_source_refs=plan['required_source_refs'], source_selections=plan['source_selections'])
        self.assertEqual((f.s, consumer), before)
        self.assertEqual(list(packet['source_excerpt_bodies'].values()), [raw[21:44]])
        self.assertNotIn(loc['blob_hash'], packet['source_bodies']); self.assertFalse(packet['complete'])
        task = {'input_manifest': packet['input_manifest']}
        changes.validate_source_delivery(task, source, [loc])
        with self.assertRaisesRegex(PMRSError, 'INCOMPLETE_CONTEXT'):
            changes.validate_source_delivery(task, source, [K.locator(raw)])
        consumer['source_selections'][source]['locators'][0]['end'] = len(raw)+1
        with self.assertRaisesRegex(PMRSError, 'RESPONSE_SCHEMA_INVALID'):
            input_plans.build(f.s, obligation, consumer, blob_get=f.get)

    def test_coverage_recomputes_authentic_parts_and_integration(self):
        helper = AssuranceContextTests(); f, target, arg, sid, scope = helper.build()
        req = A.requirement('PROOF_SUPPORT', scope)
        plan = {'plan_id': 'P', 'target_revision_refs': [arg], 'required_scope': scope,
                'parts': [{'part_id': 'part', 'review_slot_id': 'proof', 'checked_scope': scope,
                           'required_input_refs': [arg], 'declared_boundary_refs': [], 'task_ref': 'part-exec'}],
                'integration_scope': scope}
        f.s['coverage_plans'] = {'P': {'plan': plan, 'requirement': req, 'support_id': sid}}
        def captured(event, part, role, kind):
            q = helper.review(f, sid, scope, role=role, kind=kind, event_id=event)
            f.s['qualifications'][q]['policy_digest'] = C.digest(req)
            f.s['tasks'][event] = {'task_id': event, 'request_id': event, 'coverage_plan_id': 'P', 'coverage_part_id': part}
            f.s['requests'][event] = {'acceptance_state': 'ACCEPTED', 'execution_id': event}
        captured('part-exec', 'part', 'PROOF', 'PROOF')
        self.assertEqual(A.coverage_plan_evidence(f.s, 'P')[0]['result'], 'PARTIAL')
        captured('integration-exec', None, 'INDEPENDENT', 'INTEGRATION')
        before = deepcopy(f.s)
        self.assertEqual(A.coverage_plan_evidence(f.s, 'P')[0]['result'], 'QUALIFIED')
        self.assertEqual(f.s, before)
        f.s['review_executions']['integration-exec']['excluded_verdicts'] = False
        self.assertEqual(A.coverage_plan_evidence(f.s, 'P')[0]['result'], 'PARTIAL')
