"""Explicit current acceptance and retained behavior coverage; test-name guessing is forbidden."""
from pathlib import Path
import hashlib
import json


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def source_manifest(root):
    root = Path(root); result = {}
    for relative in ('research_studio', 'scripts', 'tests'):
        for p in sorted((root / relative).rglob('*')):
            rel = p.relative_to(root)
            if {'__pycache__', '.venv', '.runtime'}.intersection(rel.parts) or p.suffix in ('.pyc', '.pyo'):
                continue
            if p.is_symlink(): raise ValueError('Code/resource manifest rejects symbolic links: ' + str(rel))
            if p.is_file(): result[rel.as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    for name in ('pyproject.toml','Install-PMRS.desktop','INSTALL-HELP.html'):
        path=root/name
        if path.exists(): result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def load(root):
    directory = Path(root) / 'tests/coverage'
    required = json.loads((directory / 'required.json').read_text())
    if required.get('schema') != 'pmrs.required-test-inventory/1': raise ValueError('Required inventory schema differs')
    cases = {}; ports = {}; owners = {}
    required_cases = {c['case_id']: c for c in required['cases']}; required_ports = {p['port_id']: p for p in required['baseline']}
    retired = required.get('retired', {})
    for kind, key, active in (('cases','case_id',set(required_cases)),('baseline','port_id',set(required_ports)),
                              ('assertions','assertion_id',{a for c in required['cases'] for a in c['assertion_ids']})):
        rows=retired.get(kind,[]); ids=[r[key] for r in rows]
        if len(ids)!=len(set(ids)) or active&set(ids) or any(r.get('disposition')!='RETIRED_BY_USER_SCOPE' or not r.get('reason') for r in rows):
            raise ValueError('Retired scope must be explicit, unique and disjoint: '+kind)
    for path in sorted(directory.glob('*.json')):
        if path.name in ('required.json', 'groups.json'): continue
        mapping = json.loads(path.read_text())
        if mapping.get('schema') != 'pmrs.test-coverage/1': raise ValueError('Unrecognized coverage schema: ' + path.name)
        for case in mapping.get('acceptance', []):
            cid = case['case_id']
            if cid not in required_cases: raise ValueError('Unknown acceptance case: ' + cid)
            target = cases.setdefault(cid, {})
            for assertion in case['assertions']:
                aid = assertion['assertion_id']
                if aid not in required_cases[cid]['assertion_ids'] or aid in target: raise ValueError('Unknown/duplicate assertion mapping: ' + aid)
                test_ids = assertion['test_ids']
                if not test_ids or len(set(test_ids)) != len(test_ids) or any(not t.startswith('tests.') for t in test_ids):
                    raise ValueError('Exact unique test IDs required for ' + aid)
                target[aid] = test_ids; owners[aid] = path.name
        for port in mapping.get('baseline', []):
            pid = port['port_id']
            if pid not in required_ports or pid in ports: raise ValueError('Unknown/duplicate baseline mapping: ' + pid)
            if port['disposition'] not in ('RETAIN', 'MERGE', 'SPLIT', 'REPLACE') or not port.get('reason') or not port.get('test_ids'):
                raise ValueError('Resolved behavior disposition and exact tests required: ' + pid)
            ports[pid] = port; owners[pid] = path.name
    return required, cases, ports, owners


def evaluate(root, test_results):
    required, cases, ports, owners = load(root)
    def outcome(test_ids):
        if not test_ids: return 'MISSING_MAPPING'
        states = [test_results.get(t, {}).get('outcome', 'NOT_RUN') for t in test_ids]
        if all(s == 'PASS' for s in states): return 'PASS'
        if any(s in ('FAIL', 'ERROR', 'UNEXPECTED_SUCCESS', 'EXPECTED_FAILURE') for s in states): return 'FAIL'
        if 'SKIP' in states: return 'SKIP'
        return 'NOT_RUN'
    assertions = {}; case_results = {}; baseline = {}
    for case in required['cases']:
        cid = case['case_id']; rows = {}
        for aid in case['assertion_ids']:
            tids = cases.get(cid, {}).get(aid, [])
            rows[aid] = {'status': outcome(tids), 'test_ids': tids, 'mapping': owners.get(aid)}
            assertions[aid] = rows[aid]
        case_results[cid] = {'required': case['required'], 'status': 'PASS' if all(r['status'] == 'PASS' for r in rows.values()) else 'INCOMPLETE', 'assertions': rows}
    for port in required['baseline']:
        pid = port['port_id']; row = ports.get(pid, {})
        baseline[pid] = {**row, 'status': outcome(row.get('test_ids', [])), 'mapping': owners.get(pid)}
    browser_ids={c['browser_test_id'] for c in required['cases'] if c.get('browser_test_id')}
    native_ids={t for row in assertions.values() for t in row['test_ids'] if t not in browser_ids}
    native_ids.update(t for row in baseline.values() for t in row.get('test_ids',[]) if t not in browser_ids)
    mapped=all(row['test_ids'] for row in assertions.values()) and all(row.get('test_ids') for row in baseline.values())
    core_complete=bool(native_ids) and mapped and all(test_results.get(t,{}).get('outcome')=='PASS' for t in native_ids)
    automated=bool(browser_ids) and all(test_results.get(t,{}).get('automated_installed_complete') is True for t in browser_ids)
    unverified={t:test_results.get(t,{}).get('native_click_unverified',[]) for t in browser_ids if test_results.get(t,{}).get('native_click_unverified')}
    return {'schema': 'pmrs.executed-test-coverage/1', 'core_complete':core_complete,
            'automated_installed_complete':automated,'native_click_unverified':unverified,'retired':required.get('retired',{}), 'cases': case_results, 'assertions': assertions,
            'baseline': baseline, 'required_complete': all(c['status'] == 'PASS' for c in case_results.values() if c['required'])
                and all(b['status'] == 'PASS' for b in baseline.values()),
            'case_count': len(case_results), 'assertion_count': len(assertions), 'baseline_count': len(baseline)}
