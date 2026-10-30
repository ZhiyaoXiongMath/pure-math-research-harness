"""Exact DEV06 legacy symbols over the independently frozen DEV05 successor."""
import ast

BASE = '4239f15ad1233cc89cd6556cec284951b5fc2e3e'
TREE = '5680df0c7d62ea5cb4bf42dd388771380ce66e32'
SYMBOLS = {
    'research_studio/changes.py': ['validator_identity'],
    'research_studio/communication.py': ['send'],
    'research_studio/input_delivery.py': ['seal'],
    'research_studio/execution.py': ['apply_event', 'reserve', 'seal_capture', 'capture', 'recover_capture_seal', 'recover'],
    'research_studio/host_pool.py': ['acquire', 'release', 'mark', 'update_demand', 'clear_demand'],
    'research_studio/native_main.py': ['Service.__init__', 'Service.run', 'execute', '_sync_unloaded', 'sync_pending'],
    'research_studio/runner.py': ['FakeExecutor.execute', 'CodexExecutor.execute', 'CodexExecutor._execute',
        'materialize_task_inputs', '_preflight_dispatch', 'recover_transport', 'run'],
    'research_studio/scheduler.py': ['plan', 'commit_dispatch'],
    'research_studio/strategy.py': ['initialize', 'trigger', 'request_prepared', 'dispatch_from_main'],
    'research_studio/store.py': ['Store.commit'],
    'research_studio/storage_compat.py': ['LegacyWriters._typed_commit',
        'LegacyWriters.commit_control', 'LegacyWriters._control_guard', 'LegacyWriters._control_native',
        'SyntheticSetup', 'ControlNativeBridge'],
}
PATHS = frozenset(SYMBOLS)
EDGES = frozenset({
    ('research_studio/execution.py', 'pmrh/application/read_projections.py'),
    ('research_studio/storage_compat.py', 'pmrh/adapters/storage/control.py'),
    ('research_studio/store.py', 'pmrh/adapters/storage/control.py'),
})


def outside(raw, allowed):
    tree = ast.parse(raw)
    def trim(body, prefix=''):
        result = []
        for node in body:
            key = prefix + getattr(node, 'name', '')
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and key in allowed:
                continue
            if isinstance(node, ast.ClassDef):
                node.body = trim(node.body, key+'.')
            result.append(node)
        return result
    tree.body = trim(tree.body)
    return ast.dump(tree, include_attributes=False)


def verify_sections(path, original, current):
    if outside(original, SYMBOLS[path]) != outside(current, SYMBOLS[path]):
        from scripts import fastmath_scope
        current = fastmath_scope.preintegration(path, current)
        if outside(original, SYMBOLS[path]) != outside(current, SYMBOLS[path]):
            raise ValueError('Change outside exact approved DEV06 symbols: '+path)
