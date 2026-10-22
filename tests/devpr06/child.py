"""Fixed isolated child actions; stdin/stdout barriers, never a model runner."""
import errno
import json
import os
from pathlib import Path
import select
import sys


def barrier(label):
    print(label, flush=True)
    if not select.select([sys.stdin], [], [], 20)[0]:
        raise TimeoutError('Missing deterministic parent barrier: '+label)
    assert sys.stdin.readline().strip() == 'GO'


def isolated():
    assert os.environ['HOME'] == '/tmp/home' and os.environ['TMPDIR'] == '/tmp/tests'
    probes=json.loads(Path('/tmp/tests/s2-probes.json').read_text())
    assert os.readlink('/proc/self/ns/net') == probes['network_namespace']
    for root in ('/source','/baseline'):
        try:fd=os.open(root+'/README.md',os.O_WRONLY|os.O_APPEND)
        except OSError as exc:assert exc.errno in (errno.EROFS,errno.EACCES,errno.EPERM)
        else:
            os.close(fd)
            raise AssertionError('Child source mount is writable')
    assert not Path('/home').exists()
    sys.path.insert(0,'/source')
    from scripts.control_sandbox import install_guard
    install_guard()


def oracle(args):
    variant,action,root,output=args
    assert variant in {'baseline','current'}
    if variant=='baseline':sys.path.insert(0,'/baseline')
    from research_studio.store import Store
    from research_studio import changes,workflow_instances as W
    from research_studio.util import sha
    if action in {'read','write'} or action.startswith('historical:'):
        try:
            store=Store(root)
            if action=='write':store.commit(changes.prepare_source_input(store.read_snapshot(),b'SYNTHETIC old writer attempt.',blob_get=store.read_blob))
            else:store.read_snapshot(None if action=='read' else action.split(':',1)[1])
            result={'ok':True}
        except Exception as exc:result={'ok':False,'code':getattr(exc,'code',type(exc).__name__)}
    else:
        assert action=='trace'
        import secrets
        counter=iter(range(100));secrets.token_hex=lambda n:format(next(counter),'x').zfill(2*n)
        for name,module in list(sys.modules.items()):
            if name.startswith(('research_studio','pmrh.adapters.storage')) and hasattr(module,'now'):
                module.now=lambda:'2026-10-15T00:00:00+00:00'
        store=Store.create(root,'Frozen native trace',synthetic=True)
        store.commit(changes.prepare_source_input(store.read_snapshot(),b'For every integer n, n + 0 = n.',
            source_id='SO-fixed',blob_get=store.read_blob))
        state=store.read_snapshot();instance=W.new_instance(state,'TRH',target_ref=next(iter(state['records'])),name='Fixed instance')
        store.commit_control(W.event(state,'CREATE_INSTANCE',{'instance':instance}))
        store.commit_control(W.event(store.read_snapshot(),'PAUSE',{'reason':'Frozen pause'},instance_id=instance['instance_id']))
        result={'files':{str(p.relative_to(root)):sha(p.read_bytes()) for p in sorted(Path(root).rglob('*'))
                        if p.is_file() and '.runtime' not in p.parts},'state':store.read_snapshot()}
    Path(output).write_text(json.dumps(result,sort_keys=True))


def assemble(value):
    from tests.devpr06.test_control import Harness, NOW
    from research_studio.store import Store
    from research_studio.storage_compat import ControlNativeBridge
    from pmrh.application.control import Control,AuthorityRegistry
    from pmrh.adapters.storage.control import ControlStorage
    from pmrh.adapters.storage.pool import Pool,RootBinding
    h=Harness.__new__(Harness)
    h.root=Path(value['root']);assert h.root.is_relative_to('/tmp/tests')
    h.store=Store(h.root/'project');h.scope=value['scope'];h.iid=h.scope['instance_id'];h.project=h.scope['project_id']
    h.key=value['key'];h.genesis=value['genesis'];h.producer=value['producer'];h.binding_ref=value['binding_ref'];h.serial=value['serial']
    h.binding=RootBinding.register('fixture-project',h.store.root)
    h.pool=Pool(RootBinding.register('fixture-runtime',h.root/'runtime'),'synthetic-test-pool',[h.binding])
    h.registry=AuthorityRegistry(clock=lambda:NOW)
    for spec,row in value['manifests']:
        h.registry.register_manifest(row['manifest_ref'],row['binding_ref'],producer_ref=row['producer_ref'],spec_ref=spec,identity=row['identity'])
        if not row['active']:h.registry.revoke_manifest(spec)
    for reference,row in value['originals']:h.registry.register_original(reference,**row)
    h.storage=ControlStorage(h.store,ControlNativeBridge(h.store))
    h.control=Control(h.storage,h.pool,h.registry,binding_id=h.binding.binding_id)
    h.operator=h.session(human=True);h.service=h.session()
    return h


def control(mode,args):
    from pmrh.domain.primitives import PMRSError
    value=json.loads(Path(args[0]).read_text());h=assemble(value)
    class Boundary:
        def first_effect(self):
            path=h.root/'effects'
            fd=os.open(path,os.O_WRONLY|os.O_APPEND|os.O_CREAT,0o600)
            try:os.write(fd,b'one synthetic first effect\n');os.fsync(fd)
            finally:os.close(fd)
            if value['barrier']:barrier('BOUNDARY')
    boundary=Boundary();h.storage.register_boundary(boundary,h.scope)
    if value['fault']=='head_fsync':
        from pmrh.adapters.storage import io
        original_sync = io.fsync_dir
        def uncertain(directory):
            if Path(directory)==h.store.root:
                raise OSError(errno.EIO, 'SYNTHETIC HEAD replaced; directory fsync result uncertain')
            return original_sync(directory)
        io.fsync_dir = uncertain
    elif value['fault']:
        h.store._test_fault_hook=lambda point:os._exit(73) if point==value['fault'] else None
    if mode=='compete':barrier('READY')
    if mode=='lock':
        import fcntl
        from pmrh.domain.primitives import canonical,sha
        key=sha(canonical([h.pool.pool_id,h.project,h.genesis,h.iid]))
        fd=os.open(h.pool.path/'egress'/f'{key}.lock',os.O_RDONLY)
        try:
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:print('BLOCKED',flush=True)
            else:print('ACQUIRED',flush=True)
        finally:os.close(fd)
        return
    command=value['command'];kwargs=dict(grant_ref=value['grant_ref'],manifest_ref=value['manifest_ref'])
    try:
        if value['mode']=='send':result=h.control.send(command,h.service,boundary=boundary,**kwargs)
        elif value['mode']=='slot':result=h.storage.acquire_slot(h.control,command,h.service,**kwargs)
        elif value['mode']=='release':result=h.storage.release_slot(h.control,h.scope,command['payload']['request_id'],h.service)
        else:
            assert value['mode']=='apply'
            operator=command['type'] in {'CONTROL_APPLIED','OWNER_ACQUIRED','GRANT_REVOKED'}
            result=h.control.apply(command,h.operator if operator else h.service,**kwargs)
        if value.get('remain_live'):barrier('LIVE')
        print('RESULT '+json.dumps({'ok':True,'value':result},sort_keys=True),flush=True)
    except PMRSError as exc:
        print('RESULT '+json.dumps({'ok':False,'code':exc.code},sort_keys=True),flush=True)
    except OSError as exc:
        print('RESULT '+json.dumps({'ok':False,'code':'IO_UNCERTAIN','errno':exc.errno,'error':str(exc)},sort_keys=True),flush=True)


if __name__=='__main__':
    isolated()
    mode,*args=sys.argv[1:]
    assert mode in {'oracle','query','control','crash','compete','lock','launcher','native_duplicate'}
    if mode=='native_duplicate':
        from contextlib import contextmanager
        from research_studio.store import Store
        from research_studio.util import PMRSError
        root,event_path,wait=args
        store=Store(root);original_lock=store._locked
        if wait=='barrier':
            @contextmanager
            def delayed():
                barrier('BEFORE_NATIVE_LOCK')
                with original_lock():yield
            store._locked=delayed
        else:assert wait=='immediate'
        try:
            value=json.loads(Path(event_path).read_bytes())
            if set(value)=={'source_input'}:
                from research_studio import changes
                # The source route exists on the exact fresh native prefix.
                # Validate before Store.commit chooses its pre-lock profile.
                proposal=changes.prepare_source_input(store.read_snapshot(),value['source_input'].encode(),
                    source_id='SO-synthetic-racing-source',blob_get=store.read_blob)
                result=store.commit(proposal)
            else:result=store.commit_control(value)
            print('RESULT '+json.dumps(dict(ok=True,value=result)),flush=True)
        except PMRSError as exc:print('RESULT '+json.dumps(dict(ok=False,code=exc.code)),flush=True)
    elif mode=='launcher':
        import signal
        scenario, = args
        assert scenario in {'fail','timeout','interrupt','incomplete','pass'}
        print('partial stdout',flush=True);print('partial stderr',file=sys.stderr,flush=True)
        if scenario=='timeout':
            while True:signal.pause()
        elif scenario=='interrupt':
            os.kill(os.getppid(),signal.SIGTERM)
            while True:signal.pause()
        elif scenario=='incomplete':pass
        else:
            # Marks used only to unit-test launcher accounting, not product PASS.
            print('DEV06_PROBES '+json.dumps({'synthetic_launcher_test':True}),flush=True)
            print('DEV06_TEST_IDS '+json.dumps(['synthetic.launcher.fixture']),flush=True)
            print('DEV06_RESULT '+json.dumps(dict(discovered=1,tests=1,failures=int(scenario=='fail'),errors=0,
                skipped=0,expected_failures=0,status='FAIL' if scenario=='fail' else 'PASS')),flush=True)
            raise SystemExit(1 if scenario=='fail' else 0)
    elif mode=='oracle':oracle(args)
    elif mode=='query':
        from research_studio.readonly_query import status
        value=status(args[0],args[1])
        assert not any(name in sys.modules for name in ('research_studio.runner','research_studio.native_main',
            'research_studio.storage_compat','research_studio.host_pool','research_studio.scheduler'))
        Path(args[2]).write_text(json.dumps(value,sort_keys=True))
    else:control(mode,args)
