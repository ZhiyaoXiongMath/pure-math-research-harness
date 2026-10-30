#!/usr/bin/env python3
"""Fixed original legacy baseline with exact DEV03 file and read-section limits."""
import ast
import json
from pathlib import Path
import subprocess
try:
    from scripts import domain_scope, storage_scope, control_scope, fastmath_scope
except ModuleNotFoundError:
    import domain_scope, storage_scope, control_scope, fastmath_scope

BASE = 'e4de0210f9985224e030ac4cfd2f7e2904005b37'
TREE = 'c17a592ff0a4906afa7a6423535f41c67c926128'
READ_SECTIONS = {
    'research_studio/store.py': {'Store.__init__', 'Store._marker', 'Store._head', 'Store._commit_record',
                                  'Store.read_snapshot', 'Store.read_blob', 'Store.read_record'},
    'research_studio/host_pool.py': {'status', 'read_status', 'reconcile_pool'},
    'research_studio/views.py': {'status'},
    'research_studio/main_session.py': {'view'},
    'research_studio/workspace.py': {'Workspace._progress'},
}
NEW_QUERY = 'research_studio/readonly_query.py'
ALLOWED_PATHS = frozenset((*READ_SECTIONS, NEW_QUERY))


def outside_read_sections(raw, allowed):
    tree = ast.parse(raw)
    def trim(body, prefix=''):
        result = []
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and prefix + node.name in allowed:
                continue
            if isinstance(node, ast.ClassDef):
                node.body = trim(node.body, prefix + node.name + '.')
            result.append(node)
        return result
    tree.body = trim(tree.body)
    return ast.dump(tree, include_attributes=False)


def verify_sections(path, original, current):
    allowed = READ_SECTIONS[path]
    if outside_read_sections(original, allowed) != outside_read_sections(current, allowed):
        raise ValueError('Non-query legacy section changed: ' + path)
    if path == 'research_studio/host_pool.py':
        old = next(n for n in ast.parse(original).body if isinstance(n, ast.FunctionDef) and n.name == 'status')
        new = next(n for n in ast.parse(current).body if isinstance(n, ast.FunctionDef) and n.name == 'reconcile_pool')
        new.name = 'status'
        if isinstance(new.body[0], ast.Expr) and isinstance(new.body[0].value, ast.Constant):
            new.body.pop(0)
        if ast.dump(old, include_attributes=False) != ast.dump(new, include_attributes=False):
            raise ValueError('Original pool reconciliation behavior changed')


def main():
    root = Path(__file__).resolve().parents[1]
    fastmath_scope.verify(root)
    def candidate(path):
        return fastmath_scope.preintegration(path,(root/path).read_bytes(),root)
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=root)
    if git('rev-parse', BASE+'^{tree}').decode().strip() != TREE:
        raise ValueError('Original baseline tree changed')
    changed = set(filter(None, git('diff', '--name-only', '--no-renames', BASE, '--', 'research_studio/').decode().splitlines()))
    if changed - ALLOWED_PATHS - domain_scope.SYMBOLS.keys() - storage_scope.PATHS - control_scope.PATHS - fastmath_scope.PATHS:
        raise ValueError('Legacy change outside the exact DEV03 allowlist: ' + ', '.join(sorted(changed-ALLOWED_PATHS-domain_scope.SYMBOLS.keys()-storage_scope.PATHS-control_scope.PATHS)))
    policy = json.loads((root/'config/architecture-exceptions.json').read_bytes())
    if set(policy['devpr03_read_bridge']['changed_paths']) != ALLOWED_PATHS:
        raise ValueError('DEV03 policy path allowlist differs from the fixed authorized scope')
    if policy['devpr04_domain_bridge']['symbols'] != domain_scope.SYMBOLS or set(policy['devpr04_domain_bridge']['changed_paths']) != set(domain_scope.SYMBOLS):
        raise ValueError('DEV04 extraction scope differs from its exact authorization')
    if git('rev-parse', storage_scope.BASE+'^{tree}').decode().strip() != storage_scope.TREE:
        raise ValueError('DEV05 accepted baseline tree changed')
    if policy['devpr05_storage_bridge']['symbols'] != storage_scope.SYMBOLS or set(policy['devpr05_storage_bridge']['changed_paths']) != storage_scope.PATHS:
        raise ValueError('DEV05 exact scope differs')
    if git('rev-parse', control_scope.BASE+'^{tree}').decode().strip() != control_scope.TREE:
        raise ValueError('DEV06 frozen baseline tree changed')
    control = policy['devpr06_control_bridge']
    if control['symbols'] != control_scope.SYMBOLS or set(control['changed_paths']) != control_scope.PATHS or control['baseline'] != control_scope.BASE:
        raise ValueError('DEV06 exact symbol authorization differs')
    for path in control_scope.PATHS:
        control_scope.verify_sections(path, git('show', control_scope.BASE+':'+path), candidate(path))
    def before_control(path):
        return git('show', control_scope.BASE+':'+path) if path in control_scope.PATHS else candidate(path)
    def inherited(path):
        return git('show', storage_scope.BASE+':'+path) if path in storage_scope.PATHS else before_control(path)
    for path in storage_scope.SYMBOLS:
        storage_scope.verify_sections(path, git('show', storage_scope.BASE+':'+path), before_control(path))
    # Recheck DEV03/04 against their original baseline before applying DEV05's
    # separately frozen slices. This does not reset either previous guard.
    for path in domain_scope.SYMBOLS:
        domain_scope.verify_sections(path, git('show', BASE+':'+path), inherited(path))
    for path in READ_SECTIONS:
        verify_sections(path, git('show', BASE+':'+path), inherited(path))
    for path in git('ls-tree', '-r', '--name-only', storage_scope.BASE, '--', 'tests/').decode().splitlines():
        original = git('show', storage_scope.BASE+':'+path)
        current = (root/path).read_bytes()
        if path == storage_scope.TEST_SEAM_PATH:
            storage_scope.verify_test_seam(original, current)
        elif original != current:
            raise ValueError('Original test outside SCOPE-02 changed: '+path)
    print(json.dumps({'baseline': BASE, 'baseline_tree': TREE, 'changed_paths': sorted(changed),
                      'other_legacy_bytes': 'UNCHANGED', 'outside_authorized_sections': 'UNCHANGED', 'domain_extraction': 'EXACT_SYMBOLS_AND_FACADES',
                      'reconciliation_body': 'UNCHANGED', 'storage_extraction': 'EXACT_R1_SYMBOLS',
                      'dev03_test_seam': 'EXACT_SCOPE_02', 'other_original_tests': 'UNCHANGED'}))


if __name__ == '__main__':
    main()
