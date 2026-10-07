"""Include dependency-free browser lifecycle regressions in the release suite."""
from pathlib import Path
import re
import shutil
import subprocess
import unittest


class RepairBrowserUnitTests(unittest.TestCase):
    def test_workbench_operation_forms_and_progress_regressions(self):
        node = shutil.which('node')
        self.assertIsNotNone(node, 'Node is required to execute the browser regressions; missing runtime is not a skip.')
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [node, '--test', '--test-reporter=tap', str(root / 'tests/repair-workbench.test.js'), str(root / 'tests/operation-restart-workbench.test.js')],
            cwd=root, capture_output=True, text=True, timeout=60,
        )
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        counts = {key: int(value) for key, value in re.findall(
            r'^# (tests|pass|fail|cancelled|skipped|todo) (\d+)\s*$', output, re.MULTILINE)}
        self.assertGreaterEqual(counts.get('tests', 0), 17, output)
        self.assertEqual(counts.get('pass'), counts['tests'], output)
        for key in ('fail', 'cancelled', 'skipped', 'todo'):
            self.assertEqual(counts.get(key), 0, output)
