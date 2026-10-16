"""Only fixed offline oracle/query/crash/retry/lock actions. No model execution."""
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, '/source')
from scripts.storage_sandbox import install_guard
install_guard()
mode, *args = sys.argv[1:]

if mode == 'oracle':
    variant, action, root, output = args
    if variant == 'baseline':
        sys.path.insert(0, '/baseline')
    from research_studio.store import Store
    from research_studio import store as module
    from research_studio import changes, workflow_instances as W
    from research_studio.util import canonical, sha
    if action.startswith('query:'):
        from research_studio.readonly_query import status
        result = status(root, action.split(':',1)[1])
    elif action == 'read':
        try:
            state = Store(root).read_snapshot()
            result = {'ok': True, 'commit': state['knowledge_commit']}
        except Exception as exc:
            result = {'ok': False, 'code': getattr(exc, 'code', type(exc).__name__)}
    elif action.startswith('historical:'):
        try:
            Store(root).read_snapshot(action.split(':', 1)[1]); result = {'ok': True}
        except Exception as exc:
            result = {'ok': False, 'code': getattr(exc, 'code', type(exc).__name__)}
    elif action == 'write':
        try:
            store = Store(root)
            store.commit(changes.prepare_source_input(store.read_snapshot(), b'Another source.', source_id='SO-extra', blob_get=store.read_blob))
            result = {'ok': True}
        except Exception as exc:
            result = {'ok': False, 'code': getattr(exc, 'code', type(exc).__name__)}
    else:
        import secrets
        counter = iter(range(100))
        secrets.token_hex = lambda n: format(next(counter), 'x').zfill(2*n)
        # Freeze all already-imported clock aliases, without changing product code.
        for name, imported in list(sys.modules.items()):
            if name.startswith(('research_studio', 'pmrh.adapters.storage')) and hasattr(imported, 'now'):
                imported.now = lambda: '2026-10-15T00:00:00+00:00'
        store = Store.create(root, 'Frozen native trace', synthetic=True)
        first = store.read_snapshot()
        store.commit(changes.prepare_source_input(first, b'For every integer n, n + 0 = n.',
            source_id='SO-fixed', blob_get=store.read_blob))
        state = store.read_snapshot(); target = next(iter(state['records']))
        instance = W.new_instance(state, 'TRH', target_ref=target, name='Fixed instance')
        store.commit_control(W.event(state, 'CREATE_INSTANCE', {'instance': instance}))
        state = store.read_snapshot()
        store.commit_control(W.event(state, 'PAUSE', {'reason': 'Frozen pause'}, instance_id=instance['instance_id']))
        store.audit()
        result = {'files': {str(p.relative_to(root)): sha(p.read_bytes()) for p in sorted(Path(root).rglob('*'))
                            if p.is_file() and '.runtime' not in p.parts},
                  'state': store.read_snapshot(), 'first': store.read_snapshot(first['knowledge_commit'])}
    Path(output).write_text(json.dumps(result, sort_keys=True))
elif mode == 'query':
    from research_studio.readonly_query import status
    result = status(args[0], args[1])
    forbidden = ('research_studio.native_main', 'research_studio.runner', 'research_studio.codex_client',
                 'research_studio.scheduler', 'research_studio.host_pool', 'research_studio.report_catalog',
                 'research_studio.main_session', 'research_studio.storage_compat')
    assert not any(name in sys.modules for name in forbidden)
    Path(args[2]).write_text(json.dumps({'value': result, 'imports': sorted(sys.modules)}))
else:
    from research_studio.store import Store
    from pmrh.ports.dto import storage as T
    from tests.devpr05.fixtures import assemble, stage
    root = Path(args[0]); assert root.is_relative_to('/tmp/tests')
    if mode == 'lock':
        with Store(root)._locked():
            Path(args[1]).write_text('locked')
            deadline = time.monotonic()+10
            while not Path(args[2]).exists():
                assert time.monotonic() < deadline
                time.sleep(.01)
    else:
        iid, input_file = args[1:3]
        payload = json.loads(Path(input_file).read_text())
        boundary = T.ReadBoundary.from_wire(payload['boundary'])
        batch = T.CommitBatch.from_wire(payload['batch'])
        storage, policy, uow = assemble(Store(root), iid)
        tx, permit = stage(uow, policy, boundary, batch)
        if mode == 'crash':
            point = args[3]
            storage.writer._test_fault_hook = lambda where: os._exit(73) if where == point else None
        if mode == 'compete':
            Path(args[3]).write_text('ready')
            deadline = time.monotonic()+10
            while not Path(args[4]).exists():
                assert time.monotonic() < deadline
                time.sleep(.01)
        result = uow.commit(tx, permit)
        print(result.to_json(), flush=True)
