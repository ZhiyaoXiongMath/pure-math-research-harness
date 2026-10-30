"""Guide 03 teaching fixture. ALL model outputs and host calls are SYNTHETIC.

Real Journal/UoW/native admission; no Runner, model, research or network call.
"""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pmrh.domain import knowledge as K
from pmrh.domain.primitives import canonical, sha, PMRSError
from research_studio import contracts as C, changes, knowledge_access
from pmrh.application.kb_summary import KnowledgeSummary
from research_studio.store import Store
from tests.devpr05 import fixtures as F
from tests.devpr05.test_scientific_admission import mutate
from tests.test_final_kernel import Fixture


CONTEXT = 'Let N be an integer with N >= 1 and q be a real number.'
STATEMENT = r'For q != 1, \sum_{k=0}^{N-1} q^k = (1-q^N)/(1-q).'
ARGUMENT = 'Set S = 1 + q + ... + q^(N-1). Then qS = q + ... + q^N.\nSubtract to obtain (1-q)S = 1-q^N; divide by 1-q, since q != 1.'
EXAMPLE = 'For q = 2 and N = 3, the sum is 1 + 2 + 4 = 7.'
BRANCH = 'For q = 1 and every integer N >= 1, the sum from k = 0 to N-1 is N.'
V1 = ('Synthetic teaching material; not research evidence.\n\n' + '\n\n'.join([CONTEXT, STATEMENT, ARGUMENT, EXAMPLE]) + '\n').encode()
V2 = V1 + ('\n' + BRANCH + '\n').encode()


def output(task, source, raw, *, branch=False):
    """One fixed output containing native objects and their exact source uses."""
    ops = []
    def add(key, kind, body, data, contexts=()):
        ops.append(dict(op='NEW', local_key=key, kind=kind, body=body, data=data, context_refs=list(contexts)))
        piece = BRANCH if branch else body
        start = raw.index(piece.encode())
        loc = K.locator(raw, start, start + len(piece.encode()))
        use = dict(source_ref=source, locators=[loc], usage_mode='DECLARED_EXCERPT',
                   trust_boundary='Synthetic teaching source, not independent mathematical proof.')
        ops.append(dict(op='LINK', type='SOURCE_PROVENANCE', source_ref='local:' + key,
                        target_ref=source, scope_context_refs=[], evidence_bindings=[use], assertion_state='PROPOSED'))
    if not branch:
        loc = K.locator(CONTEXT)
        add('c', 'Context', CONTEXT, dict(parent_context_refs=[], definitions=[],
            objects=[dict(key='N,q', locator=loc)], assumptions=[dict(key='N>=1', locator=loc)], quantifiers=[], conventions=[]))
    body = BRANCH if branch else STATEMENT
    loc = K.locator(body)
    contexts = [] if branch else ['local:c']
    add('s', 'Statement', body, dict(statement_locator=loc, scope_context_refs=contexts,
        hypothesis_locators=[loc], conclusion_locators=[loc], quantifier_locators=[loc],
        form='PROPOSITION', representation='AUTHORED', source_binding=None), contexts)
    if not branch:
        add('a', 'Argument', ARGUMENT, dict(conclusion_ref='local:s', premise_bindings=[],
            steps=[dict(step_id='subtract', locator=K.locator(ARGUMENT), premise_refs=[])],
            discharged_assumptions=[], open_conditions=[], witness_bindings=[], mode='PROOF', mode_payload={}), contexts)
        add('e', 'Example', EXAMPLE, dict(target_refs=['local:s'], construction_locator=K.locator(EXAMPLE),
            scope='NUMERICAL_PROBE', hypothesis_checks=[], observations=[], realization_argument_ref=None), contexts)
    passage = BRANCH if branch else CONTEXT
    start = raw.index(passage.encode())
    # SourceEvidence is distinct from the original-file registration.
    add('se', 'SourceEvidence', passage, dict(source_occurrence_refs=[source],
        locators=[K.locator(raw, start, start + len(passage.encode()))], evidence_type='EXCERPT',
        coverage='DECLARED_RANGE', reproducibility_refs=[]))
    return Fixture().raw(task, ops)


def seal(store, iid, prepared, serial, *, branch=False, capture=True):
    """Explicit fixture host: frozen task + original fixed capture, not real inference."""
    fixture = Fixture()
    plan = prepared['plan']
    fixture.s = store.read_snapshot()
    task = fixture.task(request='summary-fixture-' + str(serial))
    source = fixture.s['sources'][plan['source_ref']]
    coverage = dict(source_ref=plan['source_ref'], source_revision=C.digest(source), source_blob_hash=plan['version'],
                    segments=[dict(locator=loc) for loc in plan['locators']])
    task.update(instance_id=iid, actor_kind='WORKER', input_manifest=[
        dict(kind='source', ref=plan['source_ref'], sha256=plan['version'], body_coverage=coverage)])
    task['input_manifest_hash'] = C.digest(task['input_manifest'])
    task['input_packet_ref'] = store.put_blob(canonical(dict(classification='SYNTHETIC_TEST_ONLY',
        kb_summary_plan_ref=prepared['plan_ref'].to_wire(), request=plan['request'],
        source_ref=plan['source_ref'], passages=[K.validate_locator(loc, store.read_blob).decode() for loc in plan['locators']])))
    task['prompt_ref'] = store.put_blob(b'SYNTHETIC_TEST_ONLY extract selected passages once')
    raw = output(task, plan['source_ref'], store.read_blob(plan['version']), branch=branch)
    if capture:
        store.put_blob(raw)
    def edit(state):
        state['instances'][iid]['status'] = 'ACTIVE'
        state['tasks'][task['task_id']] = deepcopy(task)
        state['requests'][task['request_id']] = dict(request_id=task['request_id'], task_id=task['task_id'],
            instance_id=iid, execution_state='CAPTURED' if capture else 'UNKNOWN',
            execution_kind='SYNTHETIC_TEST_ONLY', acceptance_state='PENDING', fenced=False,
            **(dict(capture_ref=sha(raw)) if capture else {}))
    mutate(store, edit)
    return task, raw


class KnowledgeSummaryMVP(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store, self.iid, self.storage, self.policy, self.uow = F.project(Path(self.tmp.name) / 'p')
        self.denied = set()
        self.service = self.reopen()

    def reopen(self):
        return KnowledgeSummary(Store(self.store.root), self.uow, native_changes=changes, knowledge_reader=knowledge_access, authorize=self.policy.authorize,
            expectation=lambda b: F.expected(b, self.policy), allow_ref=lambda ref: ref not in self.denied)

    def prepare(self, raw=V1, name='geometric.md', request='Explain the finite geometric sum and its boundary.'):
        return self.service.prepare(raw, material_id='geometric-teaching', name=name,
                                    origin='Explicit synthetic test upload', request=request)

    def complete(self, prepared, serial=1, **kwargs):
        task, raw = seal(self.store, self.iid, prepared, serial, **kwargs)
        result = self.service.complete(prepared['plan_ref'], task['request_id'])
        return result, task, raw

    def test_first_import_repeat_rename_increment_and_exact_export(self):
        prepared = self.prepare()
        source = prepared['plan']['source_ref']
        self.assertEqual(prepared['reading']['text'], [V1.decode()])
        self.assertEqual(self.store.read_snapshot()['records'].__len__(), 1)  # only existing target
        imports = self.service._rows('material')
        self.assertEqual(imports[-1][1]['read_coverage'], [])
        result, task, raw = self.complete(prepared)
        state = self.store.read_snapshot()
        self.assertEqual(state['requests'][task['request_id']]['acceptance_state'], 'ACCEPTED')
        self.assertEqual(self.store.read_blob(sha(raw)), raw)
        self.assertEqual({state['records'][r]['kind'] for r in result['result']['bindings']},
                         {'Context','Statement','Argument','Example','SourceEvidence'})
        self.assertFalse(state['qualifications'])
        markdown = self.service.export(result['result_ref'])
        for text in ('N >= 1', 'q != 1', r'\sum_{k=0}^{N-1}', 'Subtract', '1 + 2 + 4 = 7', source, sha(V1), 'no independent mathematical proof'):
            self.assertIn(text, markdown)
        old_records = deepcopy(state['records'])
        old_requests = deepcopy(state['requests'])
        self.service = self.reopen()
        head = self.store._head()
        repeat = self.prepare()
        self.assertEqual(repeat['status'], 'REUSED')
        self.assertEqual(self.store._head(), head)
        renamed = self.prepare(name='renamed.tex')
        self.assertEqual(renamed['result_ref'], result['result_ref'])
        self.assertEqual(len(self.store.read_snapshot()['sources']), len(state['sources']))
        self.assertEqual(self.service._rows('material')[-1][1]['name'], 'renamed.tex')
        self.assertEqual(self.store.read_snapshot()['requests'], old_requests)
        outside_change = self.service.prepare(V1 + b'\nAn unrelated editorial note.\n',
            material_id='geometric-teaching', name='geometric.md', origin='Synthetic scoped version',
            request=result['result']['request'], ranges=[(0, len(V1))])
        self.assertEqual(outside_change['status'], 'REUSED')
        self.assertEqual(outside_change['pinned_version'], sha(V1))
        self.assertNotEqual(outside_change['registered_material']['version'], sha(V1))
        self.assertEqual(self.store.read_snapshot()['requests'], old_requests)
        updated = self.prepare(V2)
        self.assertEqual(updated['status'], 'NEEDS_CAPTURE')
        self.assertEqual(set(updated['plan']['reuse']), set(result['result']['bindings']))
        self.assertEqual(len(updated['plan']['changed_ranges']), 1)
        second, _, _ = self.complete(updated, 2, branch=True)
        self.assertEqual(len(second['result']['added_refs']), 2)
        self.assertEqual(set(second['result']['reused_refs']), set(result['result']['bindings']))
        self.assertIn(BRANCH, second['result']['markdown'])
        self.assertIn(STATEMENT, second['result']['markdown'])
        self.assertEqual(self.service.export(result['result_ref']), markdown)
        self.assertTrue(all(self.store.read_snapshot()['records'][ref] == row for ref, row in old_records.items()))
        # A changed theorem condition also affects its Argument and Example,
        # while unchanged definitions/source passages remain reusable.
        changed = self.prepare(V1.replace(b'q != 1', b'q > 1'))
        recheck_kinds = {self.store.read_snapshot()['records'][ref]['kind']
                         for ref in changed['plan']['needs_recheck_refs']}
        self.assertTrue({'Statement', 'Argument', 'Example'} <= recheck_kinds)
        self.assertIn('Context', {self.store.read_snapshot()['records'][ref]['kind'] for ref in changed['plan']['reuse']})
        # New wording/audience may produce the SAME native content. Count the
        # native admission receipt, not the number of production events.
        another = self.prepare(request='Explain the same finite sum for advanced readers.')
        before = deepcopy(self.store.read_snapshot()['records'])
        same_content, _, _ = self.complete(another, 3)
        self.assertEqual(same_content['result']['added_refs'], [])
        self.assertEqual(len(same_content['result']['reused_refs']), 5)
        self.assertEqual(self.store.read_snapshot()['records'], before)
        self.assertTrue(self.store.audit()['valid'])

    def test_current_permissions_prevent_direct_cached_and_indirect_leaks(self):
        prepared = self.prepare()
        result, _, _ = self.complete(prepared)
        hidden = self.service.register(b'Private forbidden formula.', material_id='private', name='private.txt', origin='Synthetic private input')
        self.denied.add(hidden['source_ref'])
        with self.assertRaisesRegex(PMRSError, 'KNOWLEDGE_FORBIDDEN'):
            self.service.read(hidden['source_ref'])
        self.assertNotIn('Private forbidden', self.service.export(result['result_ref']))
        self.denied.add(prepared['plan']['source_ref'])
        with self.assertRaisesRegex(PMRSError, 'KNOWLEDGE_FORBIDDEN'):
            self.service.export(result['result_ref'])
        with self.assertRaisesRegex(PMRSError, 'KNOWLEDGE_FORBIDDEN'):
            self.service.recover('kb-summary:' + result['result_ref'].sha256)
        self.assertEqual(self.service._rows('result'), [])
        self.policy.enabled = False
        with self.assertRaisesRegex(PMRSError, 'AUTHORIZATION_REQUIRED'):
            self.service.export(result['result_ref'])

    def test_native_and_output_interruptions_recover_same_operation_without_new_capture(self):
        prepared = self.prepare()
        task, raw = seal(self.store, self.iid, prepared, 1)
        def crash(boundary):
            if boundary == 'after_head':
                raise OSError('Explicit synthetic power-loss fixture after durable HEAD')
        self.service.store._test_fault_hook = crash
        with self.assertRaises(OSError):
            self.service.complete(prepared['plan_ref'], task['request_id'])
        self.service.store._test_fault_hook = None
        accepted = deepcopy(self.store.read_snapshot()['records'])
        self.storage.writer._test_fault_hook = crash
        with self.assertRaisesRegex(PMRSError, 'SUMMARY_COMMIT_UNCERTAIN') as unknown:
            self.service.complete(prepared['plan_ref'], task['request_id'])
        operation = str(unknown.exception).split('continuation: ')[-1]
        self.storage.writer._test_fault_hook = None
        self.service = self.reopen()
        self.assertIsNotNone(self.service.recover(operation))
        head = self.store._head()
        recovered = self.service.complete(prepared['plan_ref'], task['request_id'])
        self.assertEqual(recovered['status'], 'REUSED')
        self.assertEqual(self.store._head(), head)
        self.assertEqual(self.store.read_snapshot()['records'], accepted)
        self.assertEqual(len(self.store.read_snapshot()['requests']), 1)
        self.assertEqual(self.store.read_blob(sha(raw)), raw)

    def test_unknown_missing_capture_bad_scope_and_unsupported_inputs_fail_closed(self):
        prepared = self.prepare()
        task, _ = seal(self.store, self.iid, prepared, 1, capture=False)
        with self.assertRaisesRegex(PMRSError, 'SUMMARY_CAPTURE_REQUIRED'):
            self.service.complete(prepared['plan_ref'], task['request_id'])
        self.assertEqual(len(self.store.read_snapshot()['requests']), 1)
        for raw, name in ((b'%PDF-scan', 'scan.pdf'), (b'\xff', 'bad.txt')):
            with self.subTest(name=name), self.assertRaises(PMRSError):
                self.prepare(raw, name)
        # A task that received only one selected passage cannot cite the rest.
        partial = self.service.prepare(V1, material_id='partial', name='partial.md',
            origin='Synthetic range test', request='Only the context.', ranges=[(V1.index(CONTEXT.encode()), V1.index(CONTEXT.encode()) + len(CONTEXT))])
        task, _ = seal(self.store, self.iid, partial, 2)
        before = deepcopy(self.store.read_snapshot()['records'])
        with self.assertRaisesRegex(PMRSError, 'INCOMPLETE_CONTEXT|KNOWLEDGE_SCOPE_LIMIT'):
            self.service.complete(partial['plan_ref'], task['request_id'])
        self.assertEqual(self.service._rows('result'), [])
        self.assertEqual(self.store.read_snapshot()['records'], before)

    def test_request_binding_and_production_boundary_are_not_inferred(self):
        prepared = self.prepare()
        task, _ = seal(self.store, self.iid, prepared, 1)
        different = self.prepare(request='Only discuss the numerical example.')
        before = deepcopy(self.store.read_snapshot()['records'])
        with self.assertRaisesRegex(PMRSError, 'AUTHORIZATION_REQUIRED'):
            self.service.complete(different['plan_ref'], task['request_id'])
        self.assertEqual(self.store.read_snapshot()['records'], before)
        # A local negative fixture with a production marker, not a real project.
        from research_studio.engine import Engine
        project = Engine().create(Path(self.tmp.name) / 'production-marker-negative',
                                  b'Synthetic negative fixture only.', synthetic=False)
        target = next(iter(project.read_snapshot()['records']))
        iid = Engine().new_workflow(project, 'TRH', target_ref=target)['instance_id']
        storage, policy, uow = F.assemble(project, iid, install=False)
        head = project._head()
        with self.assertRaisesRegex(PMRSError, 'UNSUPPORTED_CAPABILITY'):
            KnowledgeSummary(project, uow, native_changes=changes, knowledge_reader=knowledge_access, authorize=policy.authorize,
                expectation=lambda boundary: F.expected(boundary, policy), allow_ref=lambda ref: True)
        self.assertEqual(project._head(), head)


def example(destination):
    """Re-runnable isolated teaching example, with reviewable Markdown outputs."""
    import json
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    store, iid, storage, policy, uow = F.project(destination / 'synthetic-project')
    service = KnowledgeSummary(store, uow, native_changes=changes, knowledge_reader=knowledge_access, authorize=policy.authorize,
        expectation=lambda boundary: F.expected(boundary, policy), allow_ref=lambda ref: True)
    common = dict(material_id='geometric', name='geometric.md', origin='Synthetic example upload',
                  request='Explain the finite geometric sum and its boundary.')
    first = service.prepare(V1, **common)
    task, _ = seal(store, iid, first, 1)
    one = service.complete(first['plan_ref'], task['request_id'])
    repeated = service.prepare(V1, **common)
    second = service.prepare(V2, **common)
    task, _ = seal(store, iid, second, 2, branch=True)
    two = service.complete(second['plan_ref'], task['request_id'])
    for filename, raw in [('material-v1.md', V1), ('material-v2.md', V2),
                          ('summary-v1.md', service.export(one['result_ref']).encode()),
                          ('summary-v2.md', service.export(two['result_ref']).encode())]:
        (destination / filename).write_bytes(raw)
    receipt = dict(classification='SYNTHETIC_TEST_ONLY', repeated=repeated['status'],
        second_added=len(two['result']['added_refs']), second_reused=len(two['result']['reused_refs']),
        original_capture_sha256=[one['result']['capture_sha256'], two['result']['capture_sha256']],
        real_host_call='NOT_EXECUTED; authenticated production assembly unavailable')
    (destination / 'example.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == '--example':
        example(sys.argv[2])
    else:
        unittest.main()
