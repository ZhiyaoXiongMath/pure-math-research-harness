"""Exact architecture exceptions and test-isolation regression boundaries."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts import architecture_deps as deps
from scripts.check_legacy_scope import ALLOWED_PATHS, verify_sections
from scripts.verify_devpr02_artifacts import expected_test_ids, validate_test_log

ROOT = Path(__file__).resolve().parents[2]


class BoundaryTests(unittest.TestCase):
    def policy(self):
        return json.loads((ROOT/'config/architecture-exceptions.json').read_bytes())

    def copy_source(self):
        tmp = tempfile.TemporaryDirectory(prefix='dev03-architecture-')
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for path in ('pmrh', 'research_studio', 'docs/reference/PMRS-Next_Phase1'):
            shutil.copytree(ROOT/path, root/path)
        return root

    def test_exact_read_bridge_and_frozen_inventory_are_enforced(self):
        policy = self.policy()
        self.assertEqual(set(policy['devpr03_read_bridge']['changed_paths']), ALLOWED_PATHS)
        result = deps.run(ROOT, policy)
        self.assertEqual(result['architecture_violations'], [])
        self.assertEqual(result['syntax_errors'], [])
        self.assertEqual(result['legacy_inventory_discrepancies'], [])

    def test_whole_directory_allowance_and_extra_bridge_are_rejected(self):
        policy = self.policy()
        policy['devpr03_read_bridge']['changed_paths'].append('research_studio/')
        result = deps.run(ROOT, policy)
        self.assertIn('invalid_devpr03_path_allowlist', {v['reason'] for v in result['architecture_violations']})
        policy = self.policy()
        policy['devpr03_read_bridge']['direct_edges'].append({
            'source': 'pmrh/ports/interfaces.py', 'target': 'research_studio/store.py',
            'consumer': 'fabricated', 'reason': 'invalid', 'owner': 'DEV-PR-03', 'remove_by': 'DEV-PR-03'})
        self.assertIn('invalid_devpr03_bridge_allowlist', {v['reason'] for v in deps.run(ROOT, policy)['architecture_violations']})

    def test_another_new_consumer_cannot_reach_legacy_via_approved_cli(self):
        root = self.copy_source()
        (root/'pmrh/ports/rogue.py').write_text('from pmrh.cli import main\n')
        result = deps.run(root, self.policy())
        reasons = {v['reason'] for v in result['architecture_violations']}
        self.assertIn('forbidden_new_layer_direction', reasons)
        self.assertIn('unapproved_transitive_legacy_dependency', reasons)

    def test_query_cannot_add_runtime_import_or_dynamic_escape(self):
        root = self.copy_source()
        path = root/'research_studio/readonly_query.py'
        original = path.read_text()
        path.write_text(original + '\nfrom .runner import run\n')
        self.assertIn('query_compatibility_imports_changed', {v['reason'] for v in deps.run(root, self.policy())['architecture_violations']})
        path.write_text(original + '\ndef hidden(name):\n    return __import__(name)\n')
        self.assertIn('unresolved_dynamic_import', {v['reason'] for v in deps.run(root, self.policy())['architecture_violations']})
        path.write_text(original + '\nimport subprocess\n')
        self.assertIn('unapproved_query_capability_import', {v['reason'] for v in deps.run(root, self.policy())['architecture_violations']})

    def test_writer_sections_do_not_inherit_the_read_exception(self):
        before = 'class Store:\n    def read_snapshot(self): return 1\n    def _publish(self): return 2\n'
        allowed = before.replace('return 1', 'return 3')
        verify_sections('research_studio/store.py', before, allowed)
        with self.assertRaises(ValueError):
            verify_sections('research_studio/store.py', before, before.replace('return 2', 'return 4'))

    def test_ancestor_descriptor_allowance_does_not_allow_listing_or_file_read(self):
        root = Path(os.environ['PMRH_SANDBOX_ROOT']).parent
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            with self.assertRaises(PermissionError):
                os.listdir(fd)
            with self.assertRaises(PermissionError):
                os.scandir(fd)
            with self.assertRaises(PermissionError):
                os.open('outside-synthetic-file', os.O_RDONLY, dir_fd=fd)
        finally:
            os.close(fd)

    def test_source_inventory_requires_every_new_test_identity(self):
        ids = expected_test_ids(ROOT, suite='devpr03')
        raw = ''.join(f"{i.rsplit('.',1)[-1]} ({i}) ... ok\n" for i in ids).encode()
        raw += f'\nRan {len(ids)} tests in 0.01s\n\nOK\n'.encode()
        self.assertEqual(validate_test_log(raw, ids), ids)
        with self.assertRaises(ValueError):
            validate_test_log(raw, ids[:-1])
        with self.assertRaises(ValueError):
            validate_test_log(raw.replace(b' ... ok\n', b' ... skipped\n', 1), ids)
