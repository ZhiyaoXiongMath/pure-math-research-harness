"""Q01-Q04 and GUIDE:C03 claims against actual DEV03 query/read paths."""
from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import unittest

from pmrh.cli import main
from research_studio import host_pool, main_session, views
from research_studio.readonly_query import status, _snapshot, _ConfinedReader, _Unavailable
from research_studio.store import Store
from research_studio.util import canonical, sha
from tests.devpr03.fixtures import IID, RID, changed, footprint, pool, publish, put, state


class QueryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='dev03-query-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.home = self.root/'home'
        self.home.mkdir()
        previous = os.environ['HOME']
        os.environ['HOME'] = str(self.home)
        self.addCleanup(os.environ.__setitem__, 'HOME', previous)
        self.project = self.root/'selected-project'
        self.s, self.blobs = state()

    def existing(self, **kwargs):
        return publish(self.project, self.s, self.blobs, **kwargs)

    def test_Q01_absent_project_pool_and_config_remain_absent(self):
        before = footprint(self.root)
        result = status(self.project, IID)
        self.assertFalse(result['available'])
        self.assertEqual(result['unavailable_reason'], 'NOT_FOUND')
        self.assertEqual(result['host_pool']['unavailable_reason'], 'NOT_FOUND')
        self.assertIsNone(result['host_pool']['active'])
        self.assertEqual(result['configuration']['observation'], 'UNOBSERVED')
        self.assertEqual(before, footprint(self.root))

    def test_Q01_existing_project_without_pool_or_config_is_readable(self):
        head = self.existing()
        before = footprint(self.root)
        result = status(self.project, IID)
        self.assertTrue(result['available'], result)
        self.assertEqual(result['commit'], head['commit'])
        self.assertEqual(result['runtime']['observation'], 'UNOBSERVED')
        self.assertIsNone(result['host_pool']['active'])
        self.assertEqual(before, footprint(self.root))

    def test_Q02_existing_pool_configuration_and_project_footprint_unchanged(self):
        self.existing()
        pool(self.home, self.project)
        put(self.home, '.codex/config.toml', b'# synthetic config; must not be consumed\n')
        before = footprint(self.root)
        result = status(self.project, IID)
        self.assertTrue(result['available'], result)
        self.assertEqual(result['host_pool']['active'], 1)
        self.assertEqual(before, footprint(self.root))

    def test_Q03_paused_unknown_and_scientific_scope_preserved_no_effect_attempts(self):
        self.existing()
        pool(self.home, self.project)
        calls = []
        def forbidden(*args, **kwargs):
            calls.append(True)
            raise AssertionError('query attempted a prohibited effect')
        from research_studio import native_main
        before = footprint(self.root)
        with ExitStack() as guard:
            for obj, names in ((host_pool, ('runtime_root', 'ledger', '_clean', 'reconcile_pool', 'status', 'alive')),
                               (native_main, ('execute', 'sync_pending')),
                               (Store, ('create', '_publish', 'rebuild_projection')),
                               (socket, ('socket', 'create_connection')),
                               (subprocess, ('Popen',)), (threading.Thread, ('start',)),
                               (os, ('mkdir', 'rename', 'replace', 'unlink', 'chmod', 'truncate'))):
                for name in names:
                    guard.enter_context(changed(obj, name, forbidden))
            result = status(self.project, IID)
        self.assertTrue(result['available'], result)
        self.assertEqual(calls, [])
        self.assertEqual(result['workflow']['instances'][0]['status'], 'PAUSED')
        self.assertEqual(result['execution']['unknown'], 1)
        self.assertEqual(result['execution']['requests'][0]['state_axes']['execution'], 'UNKNOWN')
        self.assertEqual(result['execution']['requests'][0]['state_axes']['science'], 'UNOBSERVED')
        self.assertEqual(result['mathematical']['qualification'], 'EXACT_CONSUMER_SCOPE_ONLY')
        self.assertEqual(result['mathematical']['formal_proof'], 'NOT_GRANTED')
        self.assertEqual(before, footprint(self.root))

    def test_Q04_head_publication_during_query_keeps_main_on_selected_commit(self):
        from pmrh.application import read_projections
        head = self.existing()
        original = read_projections.main_view
        def publish_before_main(snapshot, iid, **kwargs):
            newer = deepcopy(self.s)
            newer['instances'][IID]['status'] = 'ACTIVE'
            publish(self.project, newer, previous=head, before=self.s)
            return original(snapshot, iid, **kwargs)
        with changed(read_projections, 'main_view', publish_before_main):
            result = status(self.project, IID)
        self.assertTrue(result['available'], result)
        self.assertEqual(result['commit'], head['commit'])
        self.assertEqual(result['main']['as_of_commit'], head['commit'])
        self.assertEqual(result['main']['native_goal']['desired_status'], 'paused')
        self.assertNotEqual(json.loads((self.project/'HEAD').read_bytes())['commit'], head['commit'])

    def test_Q04_blob_paging_and_repeated_reads_keep_pinned_boundary(self):
        head = self.existing()
        with _snapshot(self.project) as (store, snapshot):
            first = views.current(snapshot, store.read_blob, instance_id=IID, limit=1)
            newer = deepcopy(self.s)
            newer['title'] = 'Later synthetic publication'
            publish(self.project, newer, previous=head, before=self.s, checkpoint=False)
            second = views.current(snapshot, store.read_blob, instance_id=IID, offset=1, limit=1)
            self.assertEqual(len(first['records']), 1)
            self.assertEqual(len(second['records']), 1)
            self.assertNotEqual(first['records'][0]['ref'], second['records'][0]['ref'])
            self.assertEqual(first['commit'], second['commit'])
            self.assertEqual(store.read_snapshot()['knowledge_commit'], head['commit'])
            self.assertEqual(main_session.view(store, IID, snapshot=snapshot)['as_of_commit'], head['commit'])
            self.assertEqual(store.read_record(next(iter(snapshot['records']))), next(iter(snapshot['records'].values())))
        latest = status(self.project, IID)
        old = status(self.project, IID, as_of=head['commit'])
        self.assertTrue(latest['available'], latest)
        self.assertNotEqual(latest['commit'], head['commit'])
        self.assertEqual(old['commit'], head['commit'])

    def test_Q04_pool_has_independent_observation_and_source_identity(self):
        self.existing()
        root, data = pool(self.home, self.project)
        result = status(self.project, IID)
        observed = result['host_pool']
        self.assertEqual(observed['source']['sha256'], sha(canonical(data)))
        self.assertTrue(observed['observed_at'].endswith('Z'))
        self.assertFalse(result['snapshot']['cross_store_atomicity'])
        self.assertFalse(observed['reconciled'])
        self.assertEqual(observed['slots'][0]['state'], 'UNKNOWN')
        self.assertEqual(observed['owner_observation'], 'UNOBSERVED')

    def test_actual_query_rejects_parent_swap_before_descriptor_open(self):
        self.existing(checkpoint=False)
        other = self.root/'unrelated-synthetic-project'
        other.mkdir()
        (other/'canary').write_bytes(b'OUTSIDE')
        opened = []
        original = os.open
        def swap(path, flags, *args, **kwargs):
            if str(path) == 'blobs' and not opened:
                (self.project/'blobs').rename(self.project/'original-blobs')
                (self.project/'blobs').symlink_to(other, target_is_directory=True)
                opened.append(True)
            return original(path, flags, *args, **kwargs)
        with changed(os, 'open', swap):
            result = status(self.project, IID)
        self.assertEqual(opened, [True])
        self.assertFalse(result['available'])
        self.assertEqual(result['unavailable_reason'], 'PATH_UNSAFE')
        self.assertEqual((other/'canary').read_bytes(), b'OUTSIDE')

    def test_parent_swap_after_descriptor_open_reads_original_authorized_inode(self):
        head = self.existing(checkpoint=False)
        other = self.root/'outside-blobs'
        other.mkdir()
        original = os.open
        swapped = []
        def swap(path, flags, *args, **kwargs):
            fd = original(path, flags, *args, **kwargs)
            if str(path) == 'blobs' and not swapped:
                (self.project/'blobs').rename(self.project/'original-blobs')
                (self.project/'blobs').symlink_to(other, target_is_directory=True)
                swapped.append(True)
            return fd
        with changed(os, 'open', swap):
            result = status(self.project, IID)
        self.assertTrue(result['available'], result)
        self.assertEqual(result['commit'], head['commit'])

    def test_static_project_checkpoint_and_pool_symlinks_rejected(self):
        head = self.existing()
        link = self.root/'project-link'
        link.symlink_to(self.project, target_is_directory=True)
        self.assertEqual(status(link, IID)['unavailable_reason'], 'PATH_UNSAFE')
        checkpoint = self.project/'checkpoints'/f"{head['commit']}.json"
        outside = self.root/'checkpoint-copy'
        checkpoint.rename(outside)
        checkpoint.symlink_to(outside)
        self.assertFalse(status(self.project, IID)['available'])
        pool_root, _ = pool(self.home, self.project)
        ledger = pool_root/'model-pool.json'
        ledger.rename(pool_root/'copy.json')
        ledger.symlink_to(pool_root/'copy.json')
        self.assertFalse(host_pool.read_status()['available'])

    def test_denied_project_and_pool_reads_are_explicit_and_no_creation(self):
        self.existing()
        pool(self.home, self.project)
        before = footprint(self.root)
        original = os.open
        def denied(path, flags, *args, **kwargs):
            if str(path) in ('project.json', 'model-pool.json'):
                raise PermissionError('synthetic denial')
            return original(path, flags, *args, **kwargs)
        with changed(os, 'open', denied):
            result = status(self.project, IID)
        self.assertEqual(result['unavailable_reason'], 'PERMISSION_DENIED')
        self.assertEqual(result['host_pool']['unavailable_reason'], 'PERMISSION_DENIED')
        self.assertEqual(before, footprint(self.root))

    def test_actual_permission_denial_and_unchanged_default_store_reader(self):
        head = self.existing()
        store = Store(self.project)
        self.assertEqual(store.read_snapshot()['knowledge_commit'], head['commit'])
        later = deepcopy(self.s)
        later['title'] = 'A later stored title'
        new_head = publish(self.project, later, previous=head, before=self.s, checkpoint=False)
        self.assertEqual(store.read_snapshot()['knowledge_commit'], new_head['commit'])
        marker = self.project/'project.json'
        marker.chmod(0)
        try:
            before = footprint(self.root/'home')
            result = status(self.project, IID)
            self.assertEqual(result['unavailable_reason'], 'PERMISSION_DENIED')
            self.assertEqual(before, footprint(self.root/'home'))
        finally:
            marker.chmod(0o600)

    def test_readonly_permissions_positive(self):
        self.existing()
        for p in self.project.rglob('*'):
            if p.is_file():
                p.chmod(0o400)
        before = footprint(self.root)
        self.assertTrue(status(self.project, IID)['available'])
        self.assertEqual(before, footprint(self.root))

    def test_malformed_and_oversize_project_files_fail_without_repair(self):
        self.existing()
        marker = self.project/'project.json'
        for payload in (b'{', b'null', b'{"schema":1,"schema":2}', b'x'*65537):
            marker.write_bytes(payload)
            before = footprint(self.root)
            result = status(self.project, IID)
            self.assertFalse(result['available'])
            self.assertEqual(before, footprint(self.root))

    def test_corrupt_checkpoint_commit_blob_and_missing_blob_rejected(self):
        head = self.existing()
        checkpoint = self.project/'checkpoints'/f"{head['commit']}.json"
        checkpoint.write_bytes(b'null')
        self.assertFalse(status(self.project, IID)['available'])
        checkpoint.unlink()
        commit = self.project/head['path']
        original = commit.read_bytes()
        commit.write_bytes(original + b' ')
        self.assertEqual(status(self.project, IID)['unavailable_reason'], 'COMMIT_CHANGED')
        commit.write_bytes(original)
        digest = json.loads(original)['registry_delta_ref']
        blob = self.project/'blobs'/digest
        blob.write_bytes(b'{}')
        self.assertEqual(status(self.project, IID)['unavailable_reason'], 'BLOB_CHANGED')
        blob.unlink()
        self.assertEqual(status(self.project, IID)['unavailable_reason'], 'NOT_FOUND')

    def test_traversal_and_special_files_rejected_without_blocking(self):
        self.existing()
        with _ConfinedReader(self.project) as reader:
            for path in ('../outside', '/outside', 'blobs/../HEAD', 'blobs\\file', './HEAD'):
                with self.assertRaises(_Unavailable):
                    reader.read(path)
            os.mkfifo(self.project/'fifo')
            with self.assertRaises(_Unavailable) as exc:
                reader.read('fifo')
            self.assertEqual(exc.exception.reason, 'UNSAFE_FILE_TYPE')
        (self.project/'HEAD').write_bytes(canonical({'sequence': 1, 'commit': 'a'*64, 'path': '../outside'}))
        self.assertEqual(status(self.project, IID)['unavailable_reason'], 'PATH_UNSAFE')

    def test_aggregate_read_budget_and_file_count_fail_explicitly(self):
        self.existing()
        with _ConfinedReader(self.project, max_bytes=2) as reader:
            with self.assertRaises(_Unavailable) as exc:
                reader.read('project.json')
            self.assertEqual(exc.exception.reason, 'QUERY_READ_LIMIT')
        with _ConfinedReader(self.project, max_files=1) as reader:
            self.assertIsNone(reader.read('missing', missing_ok=True))
            with self.assertRaises(_Unavailable):
                reader.read('project.json')

    def test_bad_as_of_and_missing_instance_have_safe_diagnostics(self):
        self.existing()
        for selected, commit, reason in ((IID, '../secret', 'INVALID_AS_OF'),
                                         (IID, 'a'*64, 'SNAPSHOT_NOT_FOUND'),
                                         ('other', None, 'INSTANCE_NOT_FOUND')):
            result = status(self.project, selected, as_of=commit)
            self.assertEqual(result['unavailable_reason'], reason)
            self.assertFalse(result['automatic_retry'])
            self.assertNotIn(str(self.project), json.dumps(result))

    def test_unrepresentable_legacy_states_are_not_invented(self):
        self.s['requests'][RID]['execution_state'] = 'SETTLED'
        self.s['requests'][RID].pop('acceptance_state')
        self.existing()
        result = status(self.project, IID)
        row = result['execution']['requests'][0]
        self.assertEqual(row['execution_state'], 'SETTLED')
        self.assertIsNone(row['state_axes'])

    def test_R1_raw_admission_survives_unavailable_typed_mapping_per_request(self):
        cases = [('ACCEPTED', 'SETTLED'), ('REJECTED_STALE', 'SETTLED'),
                 ('REJECTED_CONTRACT', 'SETTLED'), ('EXACT_DUPLICATE', 'SETTLED'),
                 ('NOT_SUBMITTED', 'PREPARED'), (None, 'SETTLED')]
        expected = {RID: ('PENDING', 'UNKNOWN')}
        for admission, execution in cases:
            rid = 'R-' + (admission or 'missing-admission')
            tid = 'T-' + rid
            self.s['tasks'][tid] = {**self.s['tasks']['T-synthetic'],
                                    'task_id': tid, 'request_id': rid}
            request = {**self.s['requests'][RID], 'request_id': rid, 'task_id': tid,
                       'execution_state': execution}
            if admission is None:
                request.pop('acceptance_state')
            else:
                request['acceptance_state'] = admission
            self.s['requests'][rid] = request
            expected[rid] = (admission, execution)
        self.existing()
        before = footprint(self.root)
        result = status(self.project, IID)
        self.assertTrue(result['available'], result)
        rows = result['execution']['requests']
        self.assertEqual(len(rows), len(expected))
        self.assertEqual({r['request_id'] for r in rows}, set(expected))
        for row in rows:
            admission, execution = expected[row['request_id']]
            self.assertEqual(row['acceptance_state'], admission)
            self.assertEqual(row['acceptance_state_unavailable_reason'],
                             'NOT_RECORDED' if admission is None else None)
            self.assertEqual(row['execution_state'], execution)
            if row['request_id'] != RID:
                self.assertIsNone(row['state_axes'])
                self.assertEqual(row['state_axes_unavailable_reason'], 'LEGACY_VALUES_NOT_REPRESENTABLE')
        self.assertEqual(result['workflow']['instances'][0]['status'], 'PAUSED')
        self.assertEqual(result['mathematical']['formal_proof'], 'NOT_GRANTED')
        self.assertEqual(before, footprint(self.root))

    def cli_utf8(self):
        # The real CLI print path must encode bytes, not only write to StringIO.
        raw = io.BytesIO()
        with io.TextIOWrapper(raw, encoding='utf-8', errors='strict', write_through=True) as output:
            with redirect_stdout(output):
                code = main(['status', str(self.project), '--instance', IID, '--json'])
            return code, raw.getvalue()

    def test_R1_pool_surrogate_values_and_keys_keep_project_cli_json_available(self):
        head = self.existing()
        for field in ('slot-start', 'demand-key'):
            for surrogate in ('\ud800', '\udfff'):
                with self.subTest(field=field, surrogate=ascii(surrogate)):
                    root, data = pool(self.home, self.project)
                    if field == 'slot-start':
                        next(iter(data['slots'].values()))['start'] = surrogate
                    else:
                        data['demands'][surrogate] = {'demand': 1}
                    raw = json.dumps(data, ensure_ascii=True).encode('utf-8')
                    (root/'model-pool.json').write_bytes(raw)
                    before = footprint(self.root)
                    code, output = self.cli_utf8()
                    result = json.loads(output.decode('utf-8'))
                    self.assertEqual(code, 0)
                    self.assertTrue(result['available'], result)
                    self.assertEqual(result['commit'], head['commit'])
                    self.assertEqual(result['workflow']['instances'][0]['status'], 'PAUSED')
                    self.assertEqual(result['execution']['requests'][0]['execution_state'], 'UNKNOWN')
                    observed = result['host_pool']
                    self.assertFalse(observed['available'])
                    self.assertEqual(observed['unavailable_reason'], 'INVALID_POOL_DATA')
                    for name in ('active', 'slots', 'occupied', 'instance_occupied', 'demand', 'shares'):
                        self.assertIsNone(observed[name], name)
                    self.assertEqual(observed['source']['sha256'], sha(raw))
                    self.assertFalse(observed['reconciled'])
                    self.assertEqual(before, footprint(self.root))

    def test_R1_valid_unicode_pool_values_and_keys_reach_utf8_cli_unchanged(self):
        self.existing()
        root, data = pool(self.home, self.project)
        owner = '所有者-é-🧮'
        demand = '需求-é-🧮'
        next(iter(data['slots'].values()))['start'] = owner
        data['demands'][demand] = {'demand': 1}
        raw = canonical(data)
        (root/'model-pool.json').write_bytes(raw)
        before = footprint(self.root)
        code, output = self.cli_utf8()
        self.assertEqual(code, 0)
        self.assertIn(owner.encode('utf-8'), output)
        self.assertIn(demand.encode('utf-8'), output)
        result = json.loads(output.decode('utf-8'))
        self.assertTrue(result['available'], result)
        observed = result['host_pool']
        self.assertTrue(observed['available'], observed)
        self.assertEqual(observed['active'], 1)
        self.assertEqual(observed['slots'][0]['start'], owner)
        self.assertEqual(observed['slots'][0]['state'], 'UNKNOWN')
        self.assertEqual(observed['shares'][demand], 1)
        self.assertEqual(observed['owner_observation'], 'UNOBSERVED')
        self.assertEqual(observed['source']['sha256'], sha(raw))
        self.assertEqual(before, footprint(self.root))

    def test_actual_cli_json_exit_codes_and_as_of(self):
        head = self.existing()
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(['status', str(self.project), '--instance', IID, '--json', '--as-of', head['commit']])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())['commit'], head['commit'])
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(['status', str(self.root/'missing'), '--instance', IID, '--json'])
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(output.getvalue())['available'])

    def test_report_file_paths_are_not_followed_by_minimal_status(self):
        self.s['reports']['report'] = {'scope': {'instance_ids': [IID]}, 'status': 'COMPLETE',
                                       'files': {'../outside': 'a'*64}}
        self.existing()
        result = status(self.project, IID)
        self.assertTrue(result['available'], result)
        self.assertEqual(result['report'][0]['file_verification'], 'UNOBSERVED')

    def test_workspace_progress_uses_read_pool_and_same_main_communication_snapshot(self):
        # Only the read method runs. The Workspace constructor, Login, Engine,
        # maintenance, browser/server and native execution are never started.
        from research_studio.workspace import Workspace
        self.s['tasks'] = {}
        self.s['requests'] = {}
        head = self.existing()
        store = Store(self.project)
        snapshot = store.read_snapshot()
        workspace = Workspace.__new__(Workspace)
        workspace.object_labels = {}
        workspace.jobs = {}
        original = main_session.view
        def publish_before_main(reader, iid, **kwargs):
            later = deepcopy(self.s)
            later['title'] = 'Concurrent workspace publication'
            publish(self.project, later, previous=head, before=self.s)
            return original(reader, iid, **kwargs)
        def forbidden(*args, **kwargs):
            raise AssertionError('progress must not reconcile')
        with changed(main_session, 'view', publish_before_main), changed(host_pool, 'status', forbidden):
            result = workspace._progress('synthetic', store, snapshot, IID)
        self.assertEqual(result['main']['as_of_commit'], head['commit'])
        self.assertEqual(result['communication']['as_of_commit'], head['commit'])
        self.assertIsNone(result['host_pool']['active'])


class PoolTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='dev03-pool-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.home = self.root/'home'
        self.home.mkdir()
        old = os.environ['HOME']
        os.environ['HOME'] = str(self.home)
        self.addCleanup(os.environ.__setitem__, 'HOME', old)

    def test_no_registered_project_traversal_or_owner_process_probe(self):
        root, data = pool(self.home, self.root/'must-not-exist')
        def forbidden(*args, **kwargs):
            raise AssertionError('pool read traversed a registered project or reconciled')
        with changed(Store, '__init__', forbidden), changed(host_pool, 'alive', forbidden), \
             changed(host_pool, '_clean', forbidden):
            result = host_pool.read_status()
        self.assertTrue(result['available'], result)
        self.assertEqual(result['active'], 1)
        self.assertFalse((self.root/'must-not-exist').exists())

    def test_malformed_oversize_and_incomplete_pool_never_claim_zero(self):
        root, data = pool(self.home, self.root/'project')
        for raw in (b'{', b'null', b'{}', b'{"slots":[],"demands":{},"projects":{}}', b'x'*(4*1024**2+1)):
            (root/'model-pool.json').write_bytes(raw)
            result = host_pool.read_status()
            self.assertFalse(result['available'])
            self.assertIsNone(result['active'])
            self.assertIsNone(result['slots'])

    def test_actual_reconciliation_retains_unknown_and_cleans_stale_acquired(self):
        root, data = pool(self.home, self.root/'absent-project')
        unknown_key = next(iter(data['slots']))
        data['slots']['stale-acquired'] = {**data['slots'][unknown_key], 'request_id': 'old', 'state': 'ACQUIRED'}
        data['demands']['stale-demand'] = {'project': data['slots'][unknown_key]['project'],
                                          'pid': 999999999, 'start': 'stale', 'demand': 1}
        (root/'model-pool.json').write_bytes(canonical(data))
        before = host_pool.read_status()
        self.assertEqual(before['active'], 2)
        with changed(host_pool, 'alive', lambda row: False):
            result = host_pool.reconcile_pool()
        self.assertEqual(result['active'], 1)
        self.assertEqual(result['slots'][0]['state'], 'UNKNOWN')
        self.assertEqual(result['demand'], {data['slots'][unknown_key]['instance']: 1})
        self.assertTrue((root/'model-pool.lock').is_file())
        with changed(host_pool, 'alive', lambda row: False):
            self.assertEqual(host_pool.status(), result)

    def test_empty_valid_pool_is_observed_zero(self):
        root, data = pool(self.home, self.root/'absent-project')
        data['slots'] = {}
        (root/'model-pool.json').write_bytes(canonical(data))
        result = host_pool.read_status()
        self.assertTrue(result['available'])
        self.assertEqual(result['active'], 0)
