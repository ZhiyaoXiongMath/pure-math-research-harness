"""Validate explicit installed-browser observations without simulating execution."""
import hashlib
import json
from pathlib import Path, PurePosixPath
from coverage_registry import encoded, source_manifest


def _file(base, relative):
    name = PurePosixPath(relative)
    if not relative or name.is_absolute() or '..' in name.parts or str(name) != relative or '\\' in relative:
        raise ValueError('Browser artifact path must be relative without escapes')
    path = base.joinpath(*name.parts)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Browser artifact symlink is forbidden')
    if not path.is_file(): raise ValueError('Browser evidence artifact is missing: ' + relative)
    return path


def load_browser_evidence(root, path, expected_source_sha256):
    path = Path(path).absolute(); root = Path(root).resolve()
    if path.resolve().is_relative_to(root): raise ValueError('Browser evidence must be outside the source tree')
    if any(p.is_symlink() for p in (path, *path.parents)): raise ValueError('Browser evidence symlink is forbidden')
    path=path.resolve()
    raw = path.read_bytes()
    if len(raw) > 16 * 1024**2: raise ValueError('Browser evidence exceeds the bounded record size')
    record = json.loads(raw)
    if record.get('schema') != 'pmrs.browser-evidence/1' or record.get('mode') != 'CUA_INSTALLED_BROWSER':
        raise ValueError('Actual CUA installed-browser evidence for the current candidate is required')
    if record.get('source_sha256') != expected_source_sha256: raise ValueError('Browser evidence belongs to a different source candidate')
    env = record.get('environment', {})
    if not all(isinstance(env.get(k), str) and env[k].strip() for k in ('os','python','browser','installed_runtime')):
        raise ValueError('Browser evidence requires actual environment and installed runtime')
    source = source_manifest(root)
    assets = record.get('installed_assets', {})
    expected = {p: h for p, h in source.items() if p.startswith('research_studio/')}
    if set(assets) != set(expected): raise ValueError('Installed browser runtime/resource member set differs')
    for name, digest in expected.items():
        row = assets[name]
        data = _file(path.parent, row['path']).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest or row.get('sha256') != digest or row.get('bytes') != len(data):
            raise ValueError('Installed browser runtime/resource hash differs: ' + name)
    inventory = json.loads((root/'tests/coverage/required.json').read_text())
    cases = {c.get('browser_test_id'): c for c in inventory['cases'] if c.get('browser_test_id')}
    actual = record.get('actual_test_results')
    if not isinstance(actual,dict) or not actual: raise ValueError('No actual browser observations supplied')
    if set(actual) - set(cases): raise ValueError('Unknown external browser test ID')
    results = {}; modes = set()
    for test_id, row in actual.items():
        if row.get('outcome') not in {'PASS','FAIL','ERROR','SKIP'}: raise ValueError('Browser outcome must be explicit')
        required = cases[test_id].get('required_browser_paths')
        if not isinstance(required,list) or not required or len(set(required)) != len(required):
            raise ValueError('Browser case requires exact registered paths')
        artifacts = row.get('artifacts', {}); checked = {}
        for aid, artifact in artifacts.items():
            data = _file(path.parent, artifact['path']).read_bytes()
            if len(data) != artifact.get('bytes') or hashlib.sha256(data).hexdigest() != artifact.get('sha256'):
                raise ValueError('Browser observation artifact hash differs: ' + aid)
            checked[aid] = artifact
        steps = row.get('steps'); paths = row.get('executed_paths')
        if not isinstance(steps,list) or not steps or not isinstance(paths,list): raise ValueError('Actual browser steps and paths required')
        seen = set()
        for step in steps:
            if not all(isinstance(step.get(k),str) and step[k].strip() for k in ('path','action','observed')):
                raise ValueError('A browser step needs its exact path, action and observation')
            if not step.get('artifact_refs') or set(step['artifact_refs']) - set(checked):
                raise ValueError('A browser step must bind its actual observation artifacts')
            provenance = step.get('provenance', {})
            if not isinstance(provenance, dict): raise ValueError('Step provenance must be explicit')
            mode = provenance.get('mode')
            if mode not in {None, 'CUA_INSTALLED_BROWSER'}:
                raise ValueError('CUA evidence cannot relabel human or other execution modes')
            mode = 'CUA_INSTALLED_BROWSER'
            modes.add(mode)
            seen.add(step['path'])
        if set(paths) != seen: raise ValueError('Browser executed paths differ from observed steps')
        if row['outcome']=='PASS' and set(required)-seen: raise ValueError('Required installed browser paths were not all observed')
        manual = cases[test_id].get('native_manual_paths', [])
        if not isinstance(manual,list) or len(set(manual))!=len(manual) or set(manual)-set(required):
            raise ValueError('Manual paths must be a unique subset of required paths')
        missing_manual=sorted(set(manual)-seen)
        automated_complete=not(set(required)-set(manual)-seen) and row['outcome'] not in {'FAIL','ERROR'}
        results[test_id] = {**row,'automated_installed_complete':automated_complete,
                            'native_click_unverified':missing_manual,'provenance':{'mode':record['mode'],'evidence_sha256':hashlib.sha256(raw).hexdigest(),
                            'source_sha256':expected_source_sha256,'environment':env}}
    return results, {'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(),'mode':record['mode'],
                     'actual_tests':sorted(results),'environment':env,'installed_asset_count':len(assets)}

