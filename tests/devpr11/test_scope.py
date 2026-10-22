"""Static scope/oracle pairs and complete validator identity; run only confined."""
import ast
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from scripts import fastmath_scope as G
from research_studio import changes

ROOT=Path(__file__).resolve().parents[2]


class ScopeTests(unittest.TestCase):
    def oracle_root(self,path):
        data=G.oracle(ROOT)
        for relative in ('scripts/fastmath_scope_preintegration.json',*data['inherited_guard_hashes']):
            target=path/relative;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes((ROOT/relative).read_bytes())
        return data

    def test_FM22_exact_pinned_oracle_and_missing_swapped_forged_rejection(self):
        self.assertEqual(len(G.PATHS),46)
        self.assertNotIn('scripts/fastmath_scope_preintegration.json',G.PATHS)
        self.assertEqual(G.verify(ROOT)['parent'],G.PARENT)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=self.oracle_root(root)
            self.assertEqual(G.oracle(root),data)
            oracle=root/'scripts/fastmath_scope_preintegration.json';raw=oracle.read_bytes()
            oracle.unlink()
            with self.assertRaises(FileNotFoundError):G.oracle(root)
            oracle.write_bytes(raw+b'\n')
            with self.assertRaisesRegex(ValueError,'Root-pinned'):G.oracle(root)
            altered=deepcopy(data);altered['parent']='0'*40
            oracle.write_text(json.dumps(altered))
            with self.assertRaisesRegex(ValueError,'Root-pinned'):G.oracle(root)
            oracle.write_bytes(raw)
            guard=next(iter(data['inherited_guard_hashes']))
            (root/guard).write_bytes((root/guard).read_bytes()+b'\n# attempted stage weakening\n')
            with self.assertRaisesRegex(ValueError,'Inherited guard'):G.oracle(root)

    def test_FM22_exact_parent_reconstruction_and_symbol_rejections(self):
        data=G.oracle(ROOT)
        for path,row in data['files'].items():
            with self.subTest(path=path):
                original=base64.b64decode(row['bytes_base64'],validate=True)
                self.assertEqual(hashlib.sha256(original).hexdigest(),row['sha256'])
                self.assertEqual(G.preintegration(path,(ROOT/path).read_bytes(),ROOT),original)
        path='research_studio/changes.py';parent=base64.b64decode(data['files'][path]['bytes_base64'])
        with self.assertRaisesRegex(ValueError,'Outside DEV11'):
            G.verify_file(path,parent,(ROOT/path).read_bytes()+b'\nUNAUTHORIZED = True\n')
        path='research_studio/task_tools.py';parent=base64.b64decode(data['files'][path]['bytes_base64'])
        current=(ROOT/path).read_bytes()
        altered=current.replace(b"name=='main_runtime_context'",b"name=='main_runtime_context_forged'",1)
        self.assertNotEqual(altered,current)
        with self.assertRaisesRegex(ValueError,'Non-knowledge tool dispatch'):
            G.verify_file(path,parent,altered)
        path='config/architecture-exceptions.json';parent=base64.b64decode(data['files'][path]['bytes_base64'])
        current=json.loads((ROOT/path).read_bytes());current['devpr11_fastmath_bridge']['direct_edges'].append(
            dict(source='pmrh/domain/fastmath/model.py',target='research_studio/native.py'))
        with self.assertRaisesRegex(ValueError,'exact architecture edges'):
            G.verify_file(path,parent,json.dumps(current).encode())

    def test_FM22_domain_has_no_adapter_legacy_or_process_dependencies(self):
        forbidden=('research_studio','pmrh.adapters','pmrh.application','subprocess','socket','os','pathlib','importlib')
        for path in [*sorted((ROOT/'pmrh/domain/fastmath').glob('*.py')),ROOT/'pmrh/domain/native_response.py',ROOT/'pmrh/domain/native_settlement.py']:
            tree=ast.parse(path.read_bytes())
            modules=[]
            for node in ast.walk(tree):
                if isinstance(node,ast.Import):modules.extend(a.name for a in node.names)
                elif isinstance(node,ast.ImportFrom):modules.append(node.module or '')
            self.assertFalse([m for m in modules if any(m==f or m.startswith(f+'.') for f in forbidden)],path.name)

    def test_FM20_validator_identity_covers_actual_combined_bytes(self):
        identity=changes.validator_identity();modules=identity['modules']
        critical=[p for p in G.PATHS if p.startswith(('pmrh/domain/fastmath/','pmrh/adapters/storage/','pmrh/application/','research_studio/'))]
        for path in critical:
            with self.subTest(path=path):
                key=path.removeprefix('research_studio/') if path.removeprefix('research_studio/') in modules else path
                self.assertIn(key,modules)
                self.assertEqual(modules[key],hashlib.sha256((ROOT/path).read_bytes()).hexdigest())
        self.assertIn('pmrh/domain/native_response.py',modules)
        self.assertIn('pmrh/domain/native_settlement.py',modules)
        self.assertIn('pmrh/adapters/storage/pool.py',modules)
        self.assertIn('pmrh/ports/dto/core.py',modules)


    def test_FM22_pool_amendment_preserves_every_other_byte(self):
        path='pmrh/adapters/storage/pool.py';data=G.oracle(ROOT)
        parent=base64.b64decode(data['files'][path]['bytes_base64'])
        current=(ROOT/path).read_bytes()
        self.assertTrue(G.verify_file(path,parent,current))
        for old,new in ((b"'pmrh.control-fast.commit/1'",b"'unknown/1'"),
                        (b"len(effective) < 20",b"len(effective) < 200"),
                        (b"check(not state['requests'])",b"check(True)")):
            bad=current.replace(old,new,1);self.assertNotEqual(bad,current)
            with self.assertRaisesRegex(ValueError,'exact Pool discriminator'):
                G.verify_file(path,parent,bad)


    def test_FM22_scope02_scope03_exact_restrictions(self):
        data=G.oracle(ROOT)
        path='pmrh/adapters/storage/control.py';old=base64.b64decode(data['files'][path]['bytes_base64']);current=(ROOT/path).read_bytes()
        self.assertTrue(G.verify_file(path,old,current))
        bad=current.replace(b'command(value, combined=self.combined);',b'command(value, combined=True);',1)
        with self.assertRaisesRegex(ValueError,'exact acquire_slot'):G.verify_file(path,old,bad)
        path='pmrh/adapters/storage/io.py';old=base64.b64decode(data['files'][path]['bytes_base64']);current=(ROOT/path).read_bytes()
        self.assertTrue(G.verify_file(path,old,current))
        bad=current.replace(b'max_files=4096',b'max_files=8192',1)
        with self.assertRaisesRegex(ValueError,'exact io symbols'):G.verify_file(path,old,bad)
        bad=current.replace(b'self.remaining_bytes -= size',b'self.remaining_bytes -= 0',1)
        with self.assertRaisesRegex(ValueError,'legacy read factoring'):G.verify_file(path,old,bad)


    def test_FM22_reopen_process_guard_rejects_other_argv_and_environment(self):
        # Invoke actual installed audit hooks without creating any child here.
        # The paired positive executes the real reopen in StorageTests.
        import os,sys
        from unittest.mock import patch
        argv=[sys.executable,'-B','/source/scripts/fastmath_sandbox.py','--reopen','/tmp/tests/fixture/project']
        changed=dict(os.environ,DEV11_UNLISTED_ENV='denied')
        for executable,args,env in (
                ('/bin/true',argv,dict(os.environ)),
                (sys.executable,[sys.executable,'-c','pass'],dict(os.environ)),
                (sys.executable,argv[:-1]+['/source'],dict(os.environ)),
                (sys.executable,argv[:-1]+['/tmp/tests/../outside'],dict(os.environ)),
                (sys.executable,argv+['--suite','default'],dict(os.environ)),
                (sys.executable,argv,changed)):
            with self.subTest(argv=args,environment_changed=env==changed):
                with self.assertRaises(PermissionError):sys.audit('os.posix_spawn',executable,args,env)
        with self.assertRaises(PermissionError):sys.audit('subprocess.Popen',sys.executable,argv,None,changed)
        with self.assertRaises(PermissionError):sys.audit('subprocess.Popen',sys.executable,argv,'/tmp/tests',None)
        original=dict(os.environ)
        with patch.dict(os.environ,{'DEV11_UNLISTED_ENV':'denied'}):
            with self.assertRaises(PermissionError):sys.audit('os.posix_spawn',sys.executable,argv,original)
            with self.assertRaises(PermissionError):sys.audit('os.posix_spawn',sys.executable,argv,None)
            with self.assertRaises(PermissionError):sys.audit('subprocess.Popen',sys.executable,argv,None,None)


    def test_source17_scope05_exact_guard_hash_and_direct_composition(self):
        from unittest.mock import patch
        from scripts import control_scope as C
        data=G.oracle(ROOT);path='scripts/control_scope.py'
        original=base64.b64decode(data['files'][path]['bytes_base64']);current=(ROOT/path).read_bytes()
        self.assertEqual(hashlib.sha256(original).hexdigest(),'dace2caa8827070ef991af813de59bf0fec9616b8b01b2056ff9a848a21c7092')
        self.assertEqual(hashlib.sha256(current).hexdigest(),'17c4ad8adc05f7c2d413a368caaeeda9c079ea9f2c1b75475b7ce17fdb0341dd')
        self.assertTrue(G.verify_file(path,original,current))
        for old,new in ((original+b'\n',current),(original,current+b'\n'),
                (original,current.replace(b'current = fastmath_scope.preintegration(path, current)',b'current = original',1)),
                (original,current.replace(C.BASE.encode(),b'0'*40,1))):
            with self.assertRaisesRegex(ValueError,'exact Scope05'):G.verify_file(path,old,new)
        # Old valid comparisons do not need the successor oracle at all.
        path='research_studio/communication.py';raw=(ROOT/path).read_bytes()
        node=next(n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef) and n.name=='send')
        lines=raw.splitlines(keepends=True);lines.insert(node.body[0].lineno-1,b'    native_owned_edit = True\n')
        with patch.object(G,'preintegration',side_effect=AssertionError('Unexpected successor stage')):
            C.verify_sections(path,raw,raw+b'\n')
            C.verify_sections(path,raw,b''.join(lines))
        with self.assertRaisesRegex(ValueError,'Change outside exact approved DEV06 symbols'):
            C.verify_sections(path,raw,raw+b'\nUNOWNED = True\n')
        for path in ('research_studio/changes.py','research_studio/strategy.py'):
            parent=base64.b64decode(data['files'][path]['bytes_base64']);current=(ROOT/path).read_bytes()
            self.assertNotEqual(C.outside(parent,C.SYMBOLS[path]),C.outside(current,C.SYMBOLS[path]))
            C.verify_sections(path,parent,current)
            with self.assertRaisesRegex(ValueError,'Change outside exact approved DEV06 symbols'):
                C.verify_sections(path,parent+b'\nFORGED_PARENT = True\n',current)
            with self.assertRaises(ValueError):C.verify_sections(path,parent,current+b'\nUNOWNED = True\n')
        # An extra DEV06-owned edit cannot hide beside a real DEV11 delta.
        path='research_studio/strategy.py';parent=base64.b64decode(data['files'][path]['bytes_base64']);current=(ROOT/path).read_bytes()
        node=next(n for n in ast.parse(current).body if isinstance(n,ast.FunctionDef) and n.name=='initialize')
        lines=current.splitlines(keepends=True);lines.insert(node.body[0].lineno-1,b'    unauthorized_scope05 = True\n')
        with self.assertRaisesRegex(ValueError,'Outside DEV11'):
            C.verify_sections(path,parent,b''.join(lines))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.oracle_root(root);guard=root/'scripts/control_scope.py';raw=guard.read_bytes()
            guard.write_bytes(original)
            with self.assertRaisesRegex(ValueError,'Inherited guard'):G.oracle(root)
            guard.write_bytes(raw+b'\n')
            with self.assertRaisesRegex(ValueError,'Inherited guard'):G.oracle(root)


    def test_source13_native_reexports_and_mechanical_moves_are_closed(self):
        data=G.oracle(ROOT);G.verify_native_moves(ROOT,data)
        for path,names in G.SCOPE04_SYMBOL_SHA256.items():
            parent=base64.b64decode(data['files'][path]['bytes_base64'])
            current=(ROOT/path).read_bytes()
            self.assertTrue(G.verify_file(path,parent,current))
            with self.assertRaisesRegex(ValueError,'Outside DEV11'):
                G.verify_file(path,parent,current+b'\nUNAUTHORIZED_OUTSIDE_SYMBOL = True\n')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for relative in ('pmrh/domain/native_response.py','pmrh/domain/native_settlement.py'):
                p=root/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/relative).read_bytes())
            G.verify_native_moves(root,data)
            path=root/'pmrh/domain/native_settlement.py';raw=path.read_bytes()
            path.write_bytes(raw.replace(b"'light_check_seconds':1800",b"'light_check_seconds':1801",1))
            with self.assertRaisesRegex(ValueError,'Native mechanical move'):G.verify_native_moves(root,data)
            path.write_bytes(raw)
            path=root/'pmrh/domain/native_response.py';raw=path.read_bytes()
            path.write_bytes(raw.replace(b"['maxItems']=640",b"['maxItems']=641",1))
            with self.assertRaisesRegex(ValueError,'Native mechanical move'):G.verify_native_moves(root,data)
