"""Offline smoke for the existing calls documented by the four skill entrypoints.

No model, native research runner or real project is used. Native skill discovery
is checked separately through Codex skills/list; this suite is not a router.
"""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import shutil
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pmrh.cli import main
from pmrh.domain.primitives import PMRSError
from research_studio import changes, knowledge_access as knowledge
from research_studio.store import Store
from tests.devpr03.fixtures import IID, footprint, publish, state


class SharedCallSmoke(unittest.TestCase):
    def test_each_entry_reads_status_without_mutation_or_renaming(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(Path, 'home', return_value=root / 'unused-home'):
                for skill, kind in [('pmrh-kb', 'TRH'), ('pmrh-summary', 'SURVEY'),
                                    ('pmrh-trh', 'TRH'), ('pmrh-fdh', 'FDH')]:
                    with self.subTest(skill=skill):
                        snapshot, blobs = state()
                        snapshot['instances'][IID]['kind'] = kind
                        project = root / skill
                        head = publish(project, snapshot, blobs)
                        before = footprint(root)
                        output = io.StringIO()
                        with redirect_stdout(output):
                            code = main(['status', str(project), '--instance', IID, '--json'])
                        value = json.loads(output.getvalue())
                        self.assertEqual(code, 0, value)
                        self.assertTrue(value['read_only'])
                        self.assertEqual(value['commit'], head['commit'])
                        self.assertEqual(value['execution']['unknown'], 1)
                        self.assertEqual(value['workflow']['instances'][0]['kind'], kind)
                        self.assertEqual(value['workflow']['instances'][0]['status'], 'PAUSED')
                        if kind == 'SURVEY':
                            self.assertIsNone(value['main'])
                        self.assertEqual(footprint(root), before)

    def test_shared_knowledge_operations_read_the_same_exact_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store.create(root / 'synthetic', 'Skill smoke', synthetic=True)
            raw = b'Synthetic source: for every integer n, n + 0 = n.'
            store.commit(changes.prepare_material_input(
                store.read_snapshot(), raw, source_id='SO-skill-smoke',
                title='Synthetic input', media_type='text/plain', blob_get=store.read_blob))
            before = footprint(root)
            page = knowledge.search(store, 'integer')  # KB
            self.assertIn('SO-skill-smoke', {row['ref'] for row in page['results']})
            body = knowledge.get(store, 'SO-skill-smoke')  # Summary
            self.assertEqual(body['body'], raw.decode())
            for operation, key in [(knowledge.dependencies, 'dependencies'),  # TRH
                                   (knowledge.history, 'objects')]:  # FDH
                result = operation(store, 'SO-skill-smoke')
                self.assertEqual(result['ref'], 'SO-skill-smoke')
                self.assertIn(key, result)
                self.assertEqual(result['as_of_commit'], body['as_of_commit'])
            with self.assertRaises(PMRSError) as denied:
                knowledge.get(store, 'SO-outside-view')
            self.assertEqual(denied.exception.code, 'KNOWLEDGE_FORBIDDEN')
            self.assertEqual(footprint(root), before)

    def test_missing_project_is_unavailable_and_not_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / 'missing'
            before = footprint(root)
            output = io.StringIO()
            with patch.object(Path, 'home', return_value=root / 'unused-home'), redirect_stdout(output):
                code = main(['status', str(project), '--instance', IID, '--json'])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(output.getvalue())['unavailable_reason'], 'NOT_FOUND')
            self.assertFalse(project.exists())
            self.assertEqual(footprint(root), before)

    def test_scope_guard_accepts_only_the_exact_authorized_skill_overlay(self):
        from scripts import fastmath_scope as guard
        source = Path(__file__).resolve().parents[2]
        self.assertEqual(guard.verify(source)['status'], 'PASS')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'candidate'
            shutil.copytree(source, root, ignore=shutil.ignore_patterns('.git', '__pycache__'))
            for relative in ['README.md', '.github/workflows/phase0-safe.yml',
                             '.agents/skills/pmrh-kb/SKILL.md']:
                with self.subTest(tampered=relative):
                    path = root / relative
                    raw = path.read_bytes()
                    path.write_bytes(raw + b'\nUNAUTHORIZED_CHANGE\n')
                    with self.assertRaisesRegex(ValueError, 'Skill entrypoint overlay changed'):
                        guard.verify(root)
                    path.write_bytes(raw)
            path = root / 'pmrh/domain/knowledge.py'
            raw = path.read_bytes()
            path.write_bytes(raw + b'\nUNRELATED_CHANGE = True\n')
            with self.assertRaisesRegex(ValueError, 'Unowned baseline file changed'):
                guard.verify(root)
            path.write_bytes(raw)
            path = root / '.agents/skills/pmrh-router/SKILL.md'
            path.parent.mkdir()
            path.write_text('Unrequested fifth skill')
            with self.assertRaisesRegex(ValueError, 'Unlisted source addition'):
                guard.verify(root)

    def test_skill_names_are_not_fake_research_cli_commands(self):
        for command in ['pmrh-kb', 'pmrh-summary', 'pmrh-trh', 'pmrh-fdh']:
            with self.subTest(command=command), redirect_stderr(io.StringIO()):
                self.assertEqual(main([command]), 2)


if __name__ == '__main__':
    unittest.main()
