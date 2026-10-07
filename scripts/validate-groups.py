#!/usr/bin/env python3
"""Run explicit test mappings once; groups refer to the same actual suite evidence."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from coverage_registry import load

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--case', action='append', default=[], help='Exact case ID; omit for the complete release gate')
    parser.add_argument('--required-core', action='store_true', help='Select and require native tests only, retaining browser observations as a separate gate')
    parser.add_argument('--planning-only', action='store_true', help='Validate mappings without claiming executed acceptance')
    parser.add_argument('--browser-evidence', type=Path)
    args = parser.parse_args(); out = args.out.absolute(); out.mkdir(parents=True, exist_ok=True)
    required, cases, ports, owners = load(ROOT)
    requested = args.case or [c['case_id'] for c in required['cases']]
    unknown = set(requested) - {c['case_id'] for c in required['cases']}
    if unknown: raise ValueError('Unknown exact case IDs: ' + ', '.join(sorted(unknown)))
    selected = set(t for cid in requested for tids in cases.get(cid, {}).values() for t in tids)
    if not args.case: selected.update(t for port in ports.values() for t in port['test_ids'])
    if args.required_core:selected={t for t in selected if not t.startswith('tests.browser.')}
    missing = [a for c in required['cases'] if c['case_id'] in requested for a in c['assertion_ids'] if a not in cases.get(c['case_id'], {})]
    missing_ports = [p['port_id'] for p in required['baseline'] if p['port_id'] not in ports] if not args.case else []
    plan = {'schema': 'pmrs.exact-suite-plan/1', 'cases': requested, 'selected_tests': sorted(selected),
            'missing_assertions': missing, 'missing_baseline': missing_ports, 'qualification': 'PLANNING_CHECK'}
    (out / 'SUITE-PLAN.json').write_text(json.dumps(plan, indent=2) + '\n')
    if args.planning_only:
        print(json.dumps(plan, indent=2)); return 1 if missing or missing_ports else 0
    target = out / 'SUITE-MANIFEST.json'
    command = [sys.executable, '-B', str(ROOT / 'scripts/test-runner.py'), '--out', str(target)]
    if not args.case: command.append('--required-core' if args.required_core else '--required')
    if args.browser_evidence: command.extend(['--browser-evidence',str(args.browser_evidence)])
    # An empty selection is an error, never a fallback to unrelated tests.
    if not selected: raise ValueError('No exact tests mapped to requested cases')
    run = subprocess.run(command + sorted(selected), cwd=ROOT)
    manifest = json.loads(target.read_text())
    summary = {'shared_suite_manifest': target.name, 'source_sha256': manifest['source_sha256'],
        'cases': {cid: manifest['coverage'].get('cases', {}).get(cid, {'status': 'MISSING'}) for cid in requested},
        'missing_assertions': missing, 'missing_baseline': missing_ports,
        'all_pass': run.returncode == 0 and not missing and not missing_ports,
        'unique_selected_tests': len(selected), 'paid_model_calls': 0}
    (out / 'GROUP-SUMMARY.json').write_text(json.dumps(summary, indent=2) + '\n')
    return 0 if summary['all_pass'] else 1


if __name__ == '__main__': raise SystemExit(main())
