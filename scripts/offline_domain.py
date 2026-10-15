#!/usr/bin/env python3
"""Fixed DEV04 synthetic selection and independently frozen baseline oracle.

The baseline is read-only source with exact per-file hashes, never a facade
against the same implementation. No arbitrary command or suite option exists.
The Python guard supplements the externally provisioned OS isolation.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import offline_test as isolation


def fingerprints(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for directory in ('pmrh', 'research_studio', 'tests', 'scripts', 'config', '.github')
            for p in sorted((root/directory).rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts}


def test_ids():
    result = []
    for path in sorted((ROOT/'tests/devpr04').glob('test_*.py')):
        for cls in ast.parse(path.read_text()).body:
            if isinstance(cls, ast.ClassDef):
                result += ['tests.devpr04.'+path.stem+'.'+cls.name+'.'+fn.name for fn in cls.body
                           if isinstance(fn, ast.FunctionDef) and fn.name.startswith('test_')]
    return sorted(result)


def validate_log(raw, expected):
    observed = re.findall(r'^test_\w+ \(([^)]+)\)(?:\s+[^\n]*)? \.\.\. ok$', raw.decode(), re.M)
    count = re.findall(rb'Ran (\d+) tests? in ', raw)
    return sorted(observed) == sorted(expected) and bool(count) and int(count[-1]) == len(expected) and b'\nOK\n' in raw


def execute(out, oracle):
    fd = isolation._isolated_artifact_directory(out)
    try:
        manifest = json.loads((ROOT/'tests/devpr04/oracle-manifest.json').read_text())
        oracle = oracle.resolve(strict=True)
        if oracle == ROOT or ROOT in oracle.parents:
            raise ValueError('Oracle must be independently frozen outside the working source')
        for path, digest in manifest['files_sha256'].items():
            if hashlib.sha256((oracle/path).read_bytes()).hexdigest() != digest:
                raise ValueError('Frozen oracle mismatch: '+path)
        before = fingerprints(ROOT)
        selection = json.loads((ROOT/'tests/devpr04/selection.json').read_text())
        selected = sorted({test for group in selection.values() for test in group})
        runs = []
        traces = {}
        with tempfile.TemporaryDirectory(prefix='pmrh-devpr04-offline-') as folder:
            sandbox = Path(folder)
            # Identical fixture source is copied to each isolated process root.
            probe = sandbox/'domain_probe.py'
            probe.write_bytes((ROOT/'tests/devpr04/domain_probe.py').read_bytes())
            cases = [
                ('baseline-selected', oracle, ['-m', 'unittest', '-v', *selected], selected),
                ('baseline-trace', oracle, [str(probe), 'legacy'], None),
                ('facade-selected', ROOT, ['-m', 'unittest', '-v', *selected], selected),
                ('facade-trace', ROOT, [str(probe), 'legacy'], None),
                ('domain-trace', ROOT, [str(probe), 'domain'], None),
                ('devpr04-boundaries', ROOT, ['-m', 'unittest', '-v', *test_ids()], test_ids()),
            ]
            for name, source, tail, expected in cases:
                child = sandbox/name; child.mkdir()
                env = isolation.environment(child)
                env['PMRH_QUERY_TEST_GUARD'] = '1'
                env['PMRH_SOURCE_ROOT'] = str(source)
                env['PYTHONPATH'] = os.pathsep.join([str(ROOT/'scripts/offline_guard'), str(source)])
                # Both fixture and source are readable without opening either
                # checkout for writes or granting arbitrary host read access.
                child_probe = child/'domain_probe.py'; child_probe.write_bytes(probe.read_bytes())
                tail = [str(child_probe) if arg == str(probe) else arg for arg in tail]
                command = [sys.executable, '-B', *tail]
                error = None
                try:
                    run = subprocess.run(command, cwd=source, env=env, capture_output=True, timeout=180)
                    stdout, stderr, code = run.stdout, run.stderr, run.returncode
                except subprocess.TimeoutExpired as exc:
                    stdout, stderr, code, error = exc.stdout or b'', exc.stderr or b'', None, 'TIMEOUT'
                except OSError:
                    stdout, stderr, code, error = b'', b'', None, 'CHILD_START_FAILED'
                raw = stdout + stderr
                valid = code == 0 and (expected is None or validate_log(raw, expected))
                if expected is None and valid:
                    try: traces[name] = json.loads(stdout)
                    except ValueError: valid = False
                isolation._write_artifact_fd(fd, name+'.log', raw)
                runs.append({'name': name, 'command': command, 'cwd': str(source), 'status': 'PASS' if valid else 'FAIL',
                    'exit_code': code, 'error': error, 'test_ids': expected,
                    'raw_log_sha256': hashlib.sha256(raw).hexdigest(), 'environment_keys': sorted(env)})
                print(json.dumps({'run': name, 'status': runs[-1]['status']}), flush=True)
                if not valid: print(raw.decode(errors='replace')[-10000:], file=sys.stderr, flush=True)
        equivalent = len(traces) == 3 and traces['baseline-trace'] == traces['facade-trace'] == traces['domain-trace']
        oracle_unchanged = all(hashlib.sha256((oracle/p).read_bytes()).hexdigest() == h for p, h in manifest['files_sha256'].items())
        unchanged = before == fingerprints(ROOT)
        passed = equivalent and unchanged and oracle_unchanged and all(r['status'] == 'PASS' for r in runs)
        receipt = {'schema': 'pmrh.devpr04-offline/1', 'status': 'PASS' if passed else 'FAIL',
            'base': manifest['base'], 'oracle_tree': manifest['tree'], 'oracle_files_sha256': manifest['files_sha256'],
            'oracle_unchanged': oracle_unchanged, 'source_sha': os.environ.get('PMRH_SOURCE_SHA', 'UNCOMMITTED_WORKTREE'),
            'source_files_sha256': before, 'source_unchanged': unchanged,
            'source_manifest_sha256': hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(),
            'fixture_sha256': before['tests/devpr04/domain_probe.py'], 'python': sys.version, 'platform': sys.platform,
            'runs': runs, 'paired_group_selection': selection,
            'differential_status': 'PASS' if equivalent else 'FAIL',
            'differential_keys': sorted(traces.get('baseline-trace', {})),
            'research_model_calls': isolation.model_measurement(),
            'limitations': ['SYNTHETIC_CONTRACTS_NOT_MATHEMATICAL_PROOF', 'PYTHON_GUARD_NOT_OS_SANDBOX',
                'NO_LIVE_ENGINE_NATIVE_MAIN_PROVIDER_BROWSER_PDF_RESEARCH', 'COMPLETE_58_PLUS_46_NOT_EXECUTED',
                'MR03_MR04_MR08_EXISTING_DOMAIN_FRAGMENTS_ONLY', 'DEV11_DEV12_NOT_IMPLEMENTED'],
            'writes': 'Dedicated isolated scratch HOME/XDG/TMP and artifact descriptors only',
            'processes': 'Six fixed Python test children; nested test process/network entrypoints blocked'}
        encoded = (json.dumps(receipt, indent=2, sort_keys=True)+'\n').encode()
        isolation._write_artifact_fd(fd, 'receipt.json', encoded)
        # Run index only; the six named .log files contain the raw output.
        isolation._write_artifact_fd(fd, 'unittest.log', ('\n'.join(json.dumps(r, sort_keys=True) for r in runs)+'\n').encode())
        print(json.dumps({'status': receipt['status'], 'differential_status': receipt['differential_status'],
                          'source_manifest_sha256': receipt['source_manifest_sha256']}), flush=True)
        return passed
    finally:
        os.close(fd)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--oracle', type=Path, required=True)
    args = parser.parse_args()
    sys.exit(0 if execute(args.out, args.oracle) else 1)
