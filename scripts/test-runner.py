#!/usr/bin/env python3
"""Execute tests once and bind exact case/assertion outcomes to a shared source manifest."""
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from coverage_registry import source_manifest, encoded, evaluate
from browser_evidence import load_browser_evidence

CHILD = r'''
import gc,json,sys,time,unittest
sys.path.insert(0,sys.argv[1])
unraisable=[]
def error(args):
 unraisable.append(str(args.exc_value));sys.__unraisablehook__(args)
sys.unraisablehook=error
class ExactResult(unittest.TextTestResult):
 def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows={};self.starts={}
 def startTest(self,t):self.starts[t.id()]=time.monotonic();self.rows[t.id()]={'outcome':'RUNNING'};super().startTest(t)
 def stopTest(self,t):self.rows[t.id()]['elapsed_seconds']=time.monotonic()-self.starts[t.id()];super().stopTest(t)
 def mark(self,t,status,detail=None):
  self.rows.setdefault(t.id(),{})['outcome']=status
  if detail:self.rows[t.id()]['detail']=detail
 def addSuccess(self,t):self.mark(t,'PASS');super().addSuccess(t)
 def addError(self,t,e):self.mark(t,'ERROR',self._exc_info_to_string(e,t));super().addError(t,e)
 def addFailure(self,t,e):self.mark(t,'FAIL',self._exc_info_to_string(e,t));super().addFailure(t,e)
 def addSkip(self,t,r):self.mark(t,'SKIP',r);super().addSkip(t,r)
 def addExpectedFailure(self,t,e):self.mark(t,'EXPECTED_FAILURE',self._exc_info_to_string(e,t));super().addExpectedFailure(t,e)
 def addUnexpectedSuccess(self,t):self.mark(t,'UNEXPECTED_SUCCESS');super().addUnexpectedSuccess(t)
 def addSubTest(self,t,sub,e):
  if e:self.mark(t,'FAIL',self._exc_info_to_string(e,t))
  super().addSubTest(t,sub,e)
suite=unittest.defaultTestLoader.loadTestsFromNames(sys.argv[3:]) if sys.argv[3:] else unittest.defaultTestLoader.discover(sys.argv[1]+'/tests',pattern='test_final_*.py',top_level_dir=sys.argv[1])
def leaves(s):
 for t in s:
  if isinstance(t,unittest.TestSuite):yield from leaves(t)
  else:yield t.id()
ids=list(leaves(suite))
if len(ids)!=len(set(ids)):raise ValueError('Duplicate actual test IDs are not counted twice')
r=unittest.TextTestRunner(verbosity=2,resultclass=ExactResult).run(suite)
gc.collect()
result={'tests':r.testsRun,'failures':len(r.failures),'errors':len(r.errors),'skipped':len(r.skipped),'expected_failures':len(r.expectedFailures),'unexpected_successes':len(r.unexpectedSuccesses),'unraisable':unraisable,'test_results':r.rows}
with open(sys.argv[2],'w') as f:json.dump(result,f)
sys.exit(0 if r.wasSuccessful() and not unraisable and not r.skipped and not r.expectedFailures and r.testsRun else 1)
'''


def environment():
    os_release = {}
    p = Path('/etc/os-release')
    if p.exists():
        for line in p.read_text().splitlines():
            if '=' in line:
                key, value = line.split('=', 1); os_release[key] = value.strip('"')
    return {'python': sys.version, 'platform': platform.platform(), 'architecture': platform.machine(),
            'os_release': os_release, 'target_ubuntu': 'EXECUTED_ON_TARGET_UBUNTU_26_04'
            if os_release.get('ID') == 'ubuntu' and os_release.get('VERSION_ID') == '26.04' and platform.machine() == 'x86_64'
            else 'NOT_RUN_ON_TARGET_UBUNTU'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--required', action='store_true', help='Fail unless every required assertion and baseline behavior has actual PASS evidence')
    parser.add_argument('--required-core', action='store_true', help='Require all mapped native assertions and behaviors; browser paths remain separately reported')
    parser.add_argument('--browser-evidence', type=Path, help='Frozen actual CUA installed-browser observations outside the source tree')
    parser.add_argument('tests', nargs='*')
    args = parser.parse_args(); root = args.root.resolve(); out = args.out.absolute()
    out.parent.mkdir(parents=True, exist_ok=True)
    before = source_manifest(root); result_path = out.with_suffix('.result.json')
    result_path.unlink(missing_ok=True)  # A failed child must not reuse an earlier run's result.
    source_hash = hashlib.sha256(encoded(before)).hexdigest()
    external = {}; browser_record = None; browser_error = None
    if args.browser_evidence:
        try: external,browser_record = load_browser_evidence(root,args.browser_evidence,source_hash)
        except (ValueError,KeyError,TypeError,OSError) as exc: browser_error = str(exc)
    browser_ids = {c.get('browser_test_id') for c in json.loads((root/'tests/coverage/required.json').read_text())['cases'] if c.get('browser_test_id')}
    external_ids=browser_ids
    actual_selection = [t for t in args.tests if t not in external_ids]
    # An explicit external-only selection never falls back to unrelated discovery.
    external_only = bool(args.tests) and not actual_selection
    command = [sys.executable, '-B', '-W', 'error::ResourceWarning', '-c', CHILD, str(root), str(result_path), *actual_selection]
    start = time.monotonic()
    print(json.dumps({'state': 'RUNNING', 'log': str(out.with_suffix('.log')), 'required_release_gate': args.required}), flush=True)
    with out.with_suffix('.log').open('wb') as log:
        if external_only:
            run = subprocess.CompletedProcess(command,0)
            result = {'tests':0,'errors':0,'test_results':{}}
        else:
            run = subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT,
                                 env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1','PMRS_TEST_ARTIFACTS_ROOT':str(out.parent/'artifacts')})
            result = json.loads(result_path.read_text()) if result_path.exists() else {'tests': 0, 'errors': 'Runner did not complete', 'test_results': {}}
    if args.tests: external = {t:r for t,r in external.items() if t in args.tests}
    if set(external)&set(result['test_results']): browser_error = 'Browser IDs cannot replace unittest results'
    else: result['test_results'].update(external)
    result['browser_observations'] = len(set(external)&browser_ids)
    after = source_manifest(root); unchanged = before == after
    coverage_error = None
    try: coverage = evaluate(root, result['test_results'])
    except (ValueError, KeyError, OSError) as exc:
        coverage = {'required_complete': False}; coverage_error = str(exc)
    selected_external_ok = all(t in external and external[t]['outcome']=='PASS' for t in args.tests if t in external_ids)
    passed = run.returncode == 0 and unchanged and coverage_error is None and browser_error is None and selected_external_ok
    passed = passed and bool(result['tests'] or external) and all(r['outcome']=='PASS' for r in external.values())
    if args.required: passed = passed and coverage['required_complete']
    if args.required_core: passed = passed and coverage.get('core_complete',False)
    record = {'schema': 'pmrs.executed-suite/1', 'environment': environment(), 'source_files': before,
        'source_sha256': source_hash, 'source_unchanged_during_suite': unchanged,
        'result': result, 'coverage': coverage, 'coverage_error': coverage_error,
        'browser_evidence':browser_record,'browser_evidence_error':browser_error,
        'status': 'PASS' if passed else 'FAIL', 'release_qualification': 'COMPLETE' if passed and coverage['required_complete'] else 'PARTIAL',
        'required_gate_enforced': args.required, 'core_gate_enforced':args.required_core, 'exit_code': 0 if passed else 1,
        'elapsed_seconds': time.monotonic() - start, 'paid_model_calls': 0,
        'real_model_smoke': 'NOT_RUN_REAL_MODEL_SMOKE',
        'raw_log_sha256': hashlib.sha256(out.with_suffix('.log').read_bytes()).hexdigest()}
    out.write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'status': record['status'], 'tests': result['tests'], 'release_qualification': record['release_qualification'],
        'source_unchanged_during_suite': unchanged, 'source_sha256': record['source_sha256'],
        'coverage_error': coverage_error, 'elapsed_seconds': record['elapsed_seconds']}, indent=2))
    return record['exit_code']


if __name__ == '__main__': raise SystemExit(main())
