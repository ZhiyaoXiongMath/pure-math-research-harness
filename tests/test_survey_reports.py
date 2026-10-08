"""Survey reports use native captures and actual isolated PDF rendering.

The author/reviewer transport is explicitly synthetic. PASS checks here establish
software behavior, never real literature coverage or mathematical certification.
"""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research_studio import changes, contracts as C, demo, execution, reports, report_catalog, survey
from research_studio.render import Renderer
from research_studio.runner import FakeExecutor, SimulatedCrash
from research_studio.util import canonical, PMRSError, sha
from tests.test_survey import ready_survey

_RENDER_CACHE = {}


def actual_render(body, *, synthetic=False):
    key = sha(body)
    if key not in _RENDER_CACHE:
        _RENDER_CACHE[key] = Renderer()(body, synthetic=synthetic)
    return deepcopy(_RENDER_CACHE[key])


def envelope(task, payload):
    return canonical({'schema': C.RESPONSE_SCHEMA, 'task_id': task['task_id'],
                      'request_id': task['request_id'],
                      'payload_kind': 'REPORT_OUTPUT' if task['role'] == 'REPORT_AUTHOR' else 'REPORT_REVIEW',
                      'payload': payload})


class SurveyReports(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def ready(self, profile='minimal', calls=12, name='project'):
        store, iid, evidence = ready_survey(self.root / name, profile)
        if profile:
            before = len(store.read_snapshot()['requests'])
            result = survey.start_activity(store, iid, 'S5', 'Authorize this selected synthetic report only.',
                                           max_calls=calls, policy=demo.policy())
            self.assertEqual(result['model_calls'], 0)
            self.assertEqual(len(store.read_snapshot()['requests']), before)
        return store, iid, evidence

    def run_report(self, store, iid, factory=demo.response, **kwargs):
        executor = FakeExecutor(factory)
        result = reports.run(store, iid, executor=executor, policy=demo.policy(), renderer=actual_render, **kwargs)
        return result, executor

    def test_each_selected_profile_has_only_its_actual_pdf_and_independent_checks(self):
        for profile in ('minimal', 'thematic', 'lecture'):
            with self.subTest(profile=profile):
                store, iid, evidence = self.ready(profile, name=profile)
                before = deepcopy(store.read_snapshot()['records'])
                result, executor = self.run_report(store, iid)
                self.assertEqual(result['state'], 'COMPLETED_CURRENT_REPORT')
                state = store.read_snapshot(); entry = state['reports'][result['report_id']]
                self.assertEqual(set(entry['profiles']), {profile})
                self.assertEqual(entry['selected_profiles'], [profile])
                self.assertEqual(entry['output_plan_ref'], evidence['plan_ref'])
                self.assertIsNone(entry['profiles'][profile]['parent_lecture'])
                tasks = [state['tasks'][tid] for tid in result['tasks']]
                self.assertEqual([(t['stage_id'], t['role']) for t in tasks],
                                 [('S6', 'REPORT_AUTHOR'), ('S7', 'REPORT_SEMANTIC'), ('S7', 'REPORT_VISUAL')])
                self.assertEqual([t['model_policy']['reasoning_effort'] for t in tasks], ['xhigh', 'xhigh', 'high'])
                self.assertTrue(all(t['report_context']['profile'] == profile for t in tasks))
                self.assertEqual(executor.calls, 3)
                self.assertEqual(state['records'], before)
                self.assertFalse(state['qualifications'])
                p = entry['profiles'][profile]
                self.assertTrue(reports.profile_complete(p))
                self.assertFalse(p['render']['synthetic'])
                self.assertTrue(p['render']['environment']['namespace_isolated'])
                self.assertTrue(p['render']['environment']['all_pages_rendered'])
                self.assertTrue(store.read_blob(p['render']['pdf_sha256']).startswith(b'%PDF-'))
                self.assertNotRegex(store.read_blob(p['body_sha256']).decode(), r'[\u3400-\u9fff]')
                self.assertIn(b'Inconclusive', store.read_blob(p['body_sha256']))
                for page in p['render']['pages']:
                    self.assertTrue(store.read_blob(page['sha256']).startswith(b'\x89PNG\r\n\x1a\n'))
                    self.assertEqual(p['visual'][page['id']]['sha256'], page['sha256'])
                head = store._head(); repeat, fresh = self.run_report(store, iid)
                self.assertEqual(repeat['report_id'], result['report_id'])
                self.assertEqual(fresh.calls, 0); self.assertEqual(store._head(), head)
                store.audit()

    def test_knowledge_only_never_creates_an_implicit_report(self):
        store, iid, evidence = self.ready(None)
        state = store.read_snapshot(); head = store._head()
        self.assertEqual(survey.readiness(state, iid)['status'], 'SYNTHETIC_READY')
        self.assertIn(evidence['snapshot_ref'], state['survey_snapshots'])
        with self.assertRaisesRegex(PMRSError, 'SURVEY_PLAN_REQUIRED'):
            reports.prepare(store, iid)
        self.assertEqual(store._head(), head)
        self.assertEqual(store.read_snapshot()['reports'], {})
        self.assertEqual(len(store.read_snapshot()['requests']), 3)

    def test_consumed_source_withdrawal_rejects_captured_report_admission(self):
        store, iid, evidence = self.ready()
        crashing = FakeExecutor(demo.response, fault_at='AFTER_CAPTURE_RECEIPT_BEFORE_ADMISSION')
        with self.assertRaises(SimulatedCrash):
            reports.run(store, iid, executor=crashing, policy=demo.policy(), renderer=actual_render)
        state = store.read_snapshot()
        request = next(r for r in state['requests'].values() if r['execution_state'] == 'CAPTURED')
        capture = request['capture_ref']; count = len(state['requests'])
        survey.mark_source(store, iid, evidence['source_ref'], withdrawn=True,
                           reason='The original supporting source has been withdrawn during report execution.')
        self.assertEqual(reports.catalog(store)[0]['classification'], 'STALE_CANDIDATE')
        with self.assertRaisesRegex(PMRSError, 'REPORT_SNAPSHOT_STALE|SURVEY_NOT_READY|STALE_READ'):
            execution.recover(store, request['request_id'])
        state = store.read_snapshot(); entry = next(iter(state['reports'].values()))
        self.assertFalse(entry['profiles']['minimal']['body_sha256'])
        self.assertEqual(state['requests'][request['request_id']]['capture_ref'], capture)
        self.assertEqual(len(state['requests']), count)

    def test_stale_completed_report_cannot_mutate_through_a_new_event(self):
        store, iid, evidence = self.ready()
        result, _ = self.run_report(store, iid)
        entry = store.read_snapshot()['reports'][result['report_id']]
        survey.mark_source(store, iid, evidence['source_ref'], version_conflict=True,
                           reason='A conflicting version invalidates the consumed source.')
        event = reports._event('REPORT_REVISED', result['report_id'],
                               {'expected_revision': entry['profiles']['minimal']['revision'],
                                'expected_content': reports.content_key(entry['profiles']['minimal']),
                                'reason': 'Attempt a new revision after consumed source invalidation.'}, 'minimal')
        with self.assertRaisesRegex(PMRSError, 'REPORT_SNAPSHOT_STALE|SURVEY_NOT_READY'):
            reports.apply_event(store.read_snapshot(), event)
        self.assertEqual(reports.catalog(store)[0]['classification'], 'STALE_CANDIDATE')

    def test_running_report_stays_on_its_selected_plan_when_another_becomes_active(self):
        store, iid, evidence = self.ready()
        original = reports.create(store, iid)
        new_report = []
        def change_plan(task, state):
            if not new_report:
                plan = survey.create_output_plan(store, iid, evidence['snapshot_ref'], 'thematic',
                                                 view='A separately selected thematic perspective.')
                new_report.append(reports.create(store, iid, plan_ref=plan['plan_ref']))
            return demo.response(task, state)
        result, executor = self.run_report(store, iid, change_plan)
        self.assertEqual(result['report_id'], original)
        self.assertEqual(result['state'], 'COMPLETED_CURRENT_REPORT')
        self.assertEqual(executor.calls, 3)
        state = store.read_snapshot()
        self.assertEqual(state['reports'][original]['status'], 'COMPLETE')
        self.assertEqual(state['active_reports'][iid], new_report[0])
        self.assertEqual(state['reports'][new_report[0]]['status'], 'AUTHOR_REQUIRED')
        self.assertFalse(state['reports'][new_report[0]]['profiles']['thematic']['body_sha256'])
        self.assertTrue(all(state['tasks'][tid]['report_context']['profile'] == 'minimal' for tid in result['tasks']))

    def test_cli_prepare_honors_an_explicit_older_output_plan(self):
        from research_studio import cli
        store, iid, evidence = self.ready('minimal')
        survey.create_output_plan(store, iid, evidence['snapshot_ref'], 'lecture',
                                  view='An additional separately selected lecture plan.')
        result = cli.execute(cli.parser().parse_args([
            'report', str(store.root), '--instance', iid, '--plan-ref', evidence['plan_ref'],
            '--profile', 'minimal', '--prepare-only']))
        self.assertEqual(result['profile'], 'minimal')
        entry = store.read_snapshot()['reports'][result['report_id']]
        self.assertEqual(entry['output_plan_ref'], evidence['plan_ref'])
        self.assertEqual(set(entry['profiles']), {'minimal'})
        self.assertEqual(len(store.read_snapshot()['requests']), 3)

    def test_latest_plan_is_acceptance_ordered_when_clock_timestamps_tie(self):
        store, iid, evidence = self.ready('minimal')
        with patch('research_studio.survey.now', return_value='2099-01-01T00:00:00+00:00'):
            survey.create_output_plan(store, iid, evidence['snapshot_ref'], 'thematic',
                                      view='First selection in the same clock second.')
            final = survey.create_output_plan(store, iid, evidence['snapshot_ref'], 'lecture',
                                              view='Last selection in the same clock second.')
        state = store.read_snapshot()
        # Journal maps are JSON objects. Reordering keys must not change which
        # explicitly accepted plan supplies the default report request.
        events = list(state['survey_events'].items())
        for order in (events, list(reversed(events))):
            with self.subTest(order=[key for key, _ in order]):
                state['survey_events'] = dict(order)
                selected = survey.report_scope(state, iid)
                self.assertEqual(selected['survey_plan_ref'], final['plan_ref'])
                self.assertEqual(selected['profiles'], ['lecture'])
        self.assertTrue(store.audit()['valid'])

    def test_abandoned_pinned_report_cannot_dispatch_or_admit_captured_output(self):
        from research_studio import scheduler
        store, iid, _ = self.ready()
        rid = reports.create(store, iid)
        reports.abandon(store, iid, 'Stop this exact queued synthetic report.')
        before = store.read_snapshot(); executor = FakeExecutor(demo.response)
        stopped = reports.run(store, iid, report_id=rid, executor=executor, renderer=actual_render)
        self.assertEqual(stopped['state'], 'REPORT_ABANDONED')
        self.assertEqual(executor.calls, 0)
        self.assertEqual(store.read_snapshot(), before)

        store, iid, _ = self.ready(name='captured-then-abandoned')
        crashing = FakeExecutor(demo.response, fault_at='AFTER_CAPTURE_RECEIPT_BEFORE_ADMISSION')
        with self.assertRaises(SimulatedCrash):
            reports.run(store, iid, executor=crashing, renderer=actual_render)
        state = store.read_snapshot(); rid = state['active_reports'][iid]
        request = next(r for r in state['requests'].values() if r['execution_state'] == 'CAPTURED')
        reports.abandon(store, iid, 'Preserve the captured attempt, but abandon its report.')
        with self.assertRaisesRegex(PMRSError, 'REPORT_ABANDONED'):
            execution.recover(store, request['request_id'])
        state = store.read_snapshot()
        self.assertEqual(state['reports'][rid]['status'], 'ABANDONED')
        self.assertFalse(state['reports'][rid]['profiles']['minimal']['body_sha256'])
        self.assertEqual(state['requests'][request['request_id']]['capture_ref'], request['capture_ref'])
        self.assertEqual(crashing.calls, 1)
        plan = scheduler.plan(state, [iid], demo.policy())
        self.assertFalse(plan['actions']); self.assertFalse(plan['selected'])
        self.assertTrue(store.audit()['valid'])

        store, iid, _ = self.ready(name='prepared-then-abandoned')
        prepared = reports.prepare(store, iid)
        reports._assign_role(store, iid, prepared)
        plan = scheduler.plan(store.read_snapshot(), [iid], demo.policy())
        task = scheduler.commit_dispatch(store, plan, policy=demo.policy())['prepared'][0]
        reports.abandon(store, iid, 'Do not reserve the previously prepared report task.')
        with self.assertRaisesRegex(PMRSError, 'REPORT_ABANDONED'):
            execution.reserve(store, task['request_id'], execution_kind='SYNTHETIC_TEST_ONLY')
        state = store.read_snapshot()
        self.assertEqual(state['requests'][task['request_id']]['execution_state'], 'PREPARED')
        plan = scheduler.plan(state, [iid], demo.policy())
        self.assertFalse(plan['actions']); self.assertFalse(plan['selected'])

        store, iid, _ = self.ready(name='stale-dispatch-plan')
        prepared = reports.prepare(store, iid)
        reports._assign_role(store, iid, prepared)
        plan = scheduler.plan(store.read_snapshot(), [iid], demo.policy())
        self.assertEqual(len(plan['selected']), 1)
        reports.abandon(store, iid, 'Abandon after planning but before task preparation.')
        before_count = len(store.read_snapshot()['requests'])
        with self.assertRaises(PMRSError):
            scheduler.commit_dispatch(store, plan, policy=demo.policy())
        self.assertEqual(len(store.read_snapshot()['requests']), before_count)
        self.assertTrue(store.audit()['valid'])

    def test_revision_and_abandonment_keep_the_dialog_report_after_another_becomes_active(self):
        from research_studio.workspace import Workspace
        workspace = Workspace(self.root / 'workspace'); key = 'WP-' + 'b' * 32
        store, iid, evidence = self.ready(name='workspace/projects/' + key)
        original = reports.create(store, iid)
        later = survey.create_output_plan(store, iid, evidence['snapshot_ref'], 'thematic',
                                          view='A separately selected plan after the original dialog opened.')
        new_report = reports.create(store, iid, plan_ref=later['plan_ref'])
        untouched = deepcopy(store.read_snapshot()['reports'][new_report])
        with patch.object(workspace, 'launch') as launch:
            revised = workspace.action('revise-report', {'project': key, 'instance': iid,
                'report_id': original, 'profile': 'minimal', 'reason': 'Revise the originally selected report.'},
                'pinned-report-revision-1234567890')
            self.assertEqual(revised['report_id'], original)
            launch.assert_called_once_with(key, iid, report=True, report_id=original)
        state = store.read_snapshot()
        self.assertEqual(state['reports'][original]['profiles']['minimal']['revision'], 1)
        self.assertEqual(state['reports'][new_report], untouched)
        self.assertEqual(state['active_reports'][iid], new_report)
        abandoned = workspace.action('abandon-report', {'project': key, 'instance': iid,
            'report_id': original, 'reason': 'Abandon the originally selected report, preserving the later request.'},
            'pinned-report-abandonment-1234567890')
        self.assertEqual(abandoned['report_id'], original)
        state = store.read_snapshot()
        self.assertEqual(state['reports'][original]['status'], 'ABANDONED')
        self.assertEqual(state['reports'][new_report], untouched)
        self.assertEqual(state['active_reports'][iid], new_report)
        self.assertTrue(store.audit()['valid'])

    def test_selected_argument_root_can_report_its_reviewed_statement_dependency(self):
        from research_studio.engine import Engine
        store, iid, evidence = self.ready(None)
        state = store.read_snapshot()
        root = next(ref for ref in evidence['selected_refs'] if state['records'][ref]['kind'] == 'Argument')
        survey.start_activity(store, iid, 'S4', 'Independently check this selected derivation and all consumed dependencies.',
                              selected_refs=[root], max_calls=1, policy=demo.policy())
        Engine().run_round(store, iid, executor=demo.executor(), max_tasks=1)
        self.assertEqual(survey.readiness(store.read_snapshot(), iid, [root])['status'], 'SYNTHETIC_READY')
        frozen = survey.freeze_knowledge(store, iid, [root])
        plan = survey.create_output_plan(store, iid, frozen['snapshot_ref'], 'minimal')
        survey.start_activity(store, iid, 'S5', 'Write only from the selected derivation and its reviewed dependencies.',
                              selected_refs=[root], max_calls=3, policy=demo.policy())
        result, executor = self.run_report(store, iid, plan_ref=plan['plan_ref'], max_tasks=1)
        self.assertEqual(result['state'], 'REPORT_BATCH_LIMIT'); self.assertEqual(executor.calls, 1)
        state = store.read_snapshot(); entry = state['reports'][result['report_id']]
        self.assertEqual(entry['selected_profiles'], ['minimal'])
        self.assertTrue(entry['profiles']['minimal']['body_sha256'])
        self.assertEqual(state['survey_output_plans'][entry['output_plan_ref']]['selected_refs'], [root])
        self.assertTrue(store.audit()['valid'])

    def test_unrelated_evidence_does_not_invalidate_frozen_report_selection(self):
        store, iid, evidence = self.ready()
        result, _ = self.run_report(store, iid)
        rid = result['report_id']; original = deepcopy(store.read_snapshot()['reports'][rid])
        unrelated = store.commit(changes.prepare_material_input(store.read_snapshot(), b'Unrelated branch material.',
                                 'Unrelated branch', 'text/plain', blob_get=store.read_blob))
        survey.mark_source(store, iid, unrelated['source_ref'], withdrawn=True,
                           reason='This withdrawn source is not in the report dependency closure.')
        self.assertEqual(reports.catalog(store)[0]['classification'], 'COMPLETED_CURRENT_REPORT')
        repeat, executor = self.run_report(store, iid)
        self.assertEqual(repeat['report_id'], rid); self.assertEqual(executor.calls, 0)
        self.assertEqual(store.read_snapshot()['reports'][rid], original)

    def test_budget_and_unknown_preserve_existing_cost_without_resend(self):
        store, iid, _ = self.ready(calls=1)
        result, executor = self.run_report(store, iid)
        self.assertEqual(result['state'], 'WAIT'); self.assertEqual(executor.calls, 1)
        self.assertTrue(any(r.get('code') in ('BUDGET_EXHAUSTED', 'BUDGET_OR_WORKER_LIMIT') for r in result['reasons']))
        repeat, fresh = self.run_report(store, iid)
        self.assertEqual(repeat['state'], 'WAIT'); self.assertEqual(fresh.calls, 0)
        store, iid, _ = self.ready(name='unknown')
        crashing = FakeExecutor(demo.response, fault_at='AFTER_RESERVATION_BEFORE_SEND')
        with self.assertRaises(SimulatedCrash):
            reports.run(store, iid, executor=crashing, policy=demo.policy(), renderer=actual_render)
        request = next(r for r in store.read_snapshot()['requests'].values() if r['execution_state'] == 'RESERVED')
        store.commit_execution(execution.event('UNKNOWN', {'request_id': request['request_id'],
                               'execution_id': request['execution_id'], 'reason': 'No original transport outcome is available.'}))
        before = len(store.read_snapshot()['requests'])
        result, fresh = self.run_report(store, iid)
        self.assertEqual(result['code'], 'UNKNOWN_REQUIRES_EVIDENCE'); self.assertEqual(fresh.calls, 0)
        state = store.read_snapshot()
        self.assertEqual(len(state['requests']), before)
        self.assertEqual(state['requests'][request['request_id']]['reserved_calls'], 1)
        self.assertEqual(state['requests'][request['request_id']]['execution_state'], 'UNKNOWN')

    def test_captured_author_recovery_uses_original_and_no_companion_profile(self):
        store, iid, _ = self.ready('thematic')
        crashing = FakeExecutor(demo.response, fault_at='AFTER_CAPTURE_RECEIPT_BEFORE_ADMISSION')
        with self.assertRaises(SimulatedCrash):
            reports.run(store, iid, executor=crashing, policy=demo.policy(), renderer=actual_render)
        request = next(r for r in store.read_snapshot()['requests'].values() if r['execution_state'] == 'CAPTURED')
        capture = request['capture_ref']; result, fresh = self.run_report(store, iid)
        self.assertEqual(result['state'], 'COMPLETED_CURRENT_REPORT'); self.assertEqual(fresh.calls, 2)
        state = store.read_snapshot()
        self.assertEqual(state['requests'][request['request_id']]['capture_ref'], capture)
        self.assertEqual(set(state['reports'][result['report_id']]['profiles']), {'thematic'})

    def test_new_claim_review_blocks_delivery_without_writing_knowledge(self):
        store, iid, _ = self.ready()
        original = deepcopy(store.read_snapshot()['records'])
        def objection(task, state):
            if task['role'] != 'REPORT_SEMANTIC':
                return demo.response(task, state)
            return envelope(task, {'profile': 'minimal', 'verdict': 'REVISE', 'uncheckable': [], 'findings': [
                {'code': 'NEW_LEMMA_REQUIRED', 'anchor': 'Finite sum derivation', 'severity': 'BLOCKING',
                 'description': 'A division step uses a missing nonzero-denominator condition.'}]})
        result, executor = self.run_report(store, iid, objection)
        self.assertEqual(result['state'], 'REPORT_BLOCKED'); self.assertEqual(executor.calls, 2)
        state = store.read_snapshot(); entry = state['reports'][result['report_id']]
        self.assertEqual(state['records'], original); self.assertFalse(state['qualifications'])
        self.assertTrue(entry['open_research_requests']); self.assertFalse(reports.pair_complete(entry))
        duty = state['obligations'][entry['open_research_requests'][0]['obligation_id']]
        self.assertFalse(duty['definition']['consumer_bindings'])
        self.assertEqual(duty['projection']['resolution'], 'UNRESOLVED')

    def test_all_actual_pages_are_checked_and_old_success_does_not_cover_new_failure(self):
        store, iid, _ = self.ready('lecture')
        def three_pages(task, state):
            payload = reports.demo_payload(task, state)
            if task['role'] == 'REPORT_AUTHOR':
                payload['body'] += '\\newpage\nExplicit scope and limitations.\n\\newpage\nFinite sums only.\n'
            return envelope(task, payload)
        result, _ = self.run_report(store, iid, three_pages)
        entry = store.read_snapshot()['reports'][result['report_id']]; p = entry['profiles']['lecture']
        self.assertEqual(len(p['render']['pages']), 3)
        self.assertEqual(set(p['visual']), {r['id'] for r in p['render']['pages']})
        reports.revise(store, iid, 'lecture', 'Revise the selected standalone Survey lecture only.')
        revised = store.read_snapshot()['reports'][result['report_id']]
        self.assertEqual(set(revised['profiles']), {'lecture'})
        self.assertEqual(revised['profiles']['lecture']['history'][0]['body_sha256'], p['body_sha256'])
        self.assertFalse(reports.pair_complete(revised))
        def invalid(task, state):
            payload = reports.demo_payload(task, state)
            if task['role'] == 'REPORT_AUTHOR':
                payload['body'] += ' 中文报告不在本版范围内。'
            return envelope(task, payload)
        with self.assertRaisesRegex(PMRSError, 'LANGUAGE_MISMATCH'):
            self.run_report(store, iid, invalid)
        self.assertFalse(reports.pair_complete(store.read_snapshot()['reports'][result['report_id']]))
        self.assertTrue(store.read_blob(p['body_sha256']))


if __name__ == '__main__':
    unittest.main()
