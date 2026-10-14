#!/usr/bin/env python3
"""Fixed DEV03 synthetic suite; no selectable product command or research path."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import offline_test as baseline
from scripts.verify_devpr02_artifacts import expected_test_ids, validate_test_log

COMMAND = ['-B', '-m', 'unittest', 'discover', '-s', 'tests/devpr03', '-p', 'test_*.py', '-t', '.', '-v']


def fingerprints():
    paths = []
    for directory in ('pmrh', 'research_studio', 'tests', 'scripts', 'config', '.github'):
        paths.extend(p for p in (ROOT/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def execute(out):
    fd = baseline._isolated_artifact_directory(out)
    try:
        before = fingerprints()
        ids = expected_test_ids(ROOT, suite='devpr03')
        with tempfile.TemporaryDirectory(prefix='pmrh-devpr03-offline-') as folder:
            env = baseline.environment(Path(folder))
            env['PMRH_QUERY_TEST_GUARD'] = '1'
            command = [sys.executable, *COMMAND]
            error = None
            try:
                run = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, timeout=180)
                raw, code = run.stdout + run.stderr, run.returncode
            except subprocess.TimeoutExpired as exc:
                raw, code, error = (exc.stdout or b'') + (exc.stderr or b''), None, 'TIMEOUT'
            except OSError:
                raw, code, error = b'', None, 'CHILD_START_FAILED'
            observed = ()
            try:
                observed = validate_test_log(raw, ids)
            except ValueError:
                pass
            unchanged = before == fingerprints()
            passed = code == 0 and observed == ids and unchanged
            receipt = {
                'schema': 'pmrh.devpr03-test/1', 'status': 'PASS' if passed else 'FAIL',
                'source_sha': os.environ.get('PMRH_SOURCE_SHA', 'UNVERIFIED_WORKTREE'),
                'checkout_tree': os.environ.get('PMRH_CHECKOUT_TREE', 'UNVERIFIED_WORKTREE'),
                'command': command, 'python': sys.version, 'exit_code': code, 'error': error,
                'environment_keys': sorted(env), 'isolated_home_xdg_tmp': True,
                'source_files_sha256': before, 'source_unchanged': unchanged,
                'expected_test_ids': list(ids), 'validated_test_ids': list(observed),
                'raw_log_sha256': hashlib.sha256(raw).hexdigest(),
                'research_model_calls': baseline.model_measurement(),
                'limitations': ['PYTHON_GUARD_NOT_OS_SANDBOX', 'OS_ATIME_NOT_COMPARED',
                                'REAL_RESEARCH_NATIVE_PROVIDER_BROWSER_PDF_NOT_EXECUTED',
                                'DEV09_STREAMING_EVENTS_NOT_EXECUTED'],
            }
            baseline._write_artifact_fd(fd, 'unittest.log', raw)
            baseline._write_artifact_fd(fd, 'receipt.json', (json.dumps(receipt, indent=2, sort_keys=True)+'\n').encode())
            print(json.dumps({k: receipt[k] for k in ('status', 'source_sha', 'exit_code', 'error', 'source_unchanged')}))
            if not passed:
                print(raw.decode(errors='replace')[-18000:], file=sys.stderr)
            return passed
    finally:
        os.close(fd)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--out', type=Path, required=True)
    sys.exit(0 if execute(parser.parse_args().out) else 1)
