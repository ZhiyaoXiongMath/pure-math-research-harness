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
    def test_source37_closed_storage_timeout_and_unchanged_other_selectors(self):
        from scripts.offline_fastmath import suite_timeout_seconds
        self.assertEqual(suite_timeout_seconds('ci-storage'),3600)
        for selector in ('default','ci-core','source04-affected','source07-affected','source09-affected',
                'source10-affected','source11-affected','source11-query','source12-permission',
                'source13-core','source13-business','source16-small','source17-affected','source18-affected',
                'source19-capacity','source20-final-remaining','source21-affected','p01-large','p01-256',
                'p01-256-plus-one','fm13-pilot','fm13-native-pilot'):
            with self.subTest(selector=selector):self.assertEqual(suite_timeout_seconds(selector),1800)
        for unknown in ('ci-storage-extra','ci','',None,3600,[]):
            with self.subTest(selector=unknown):
                with self.assertRaisesRegex(ValueError,'Unknown closed suite selector'):suite_timeout_seconds(unknown)

    def test_source37_parent_timing_split_prefix_docstring_and_active_timeout(self):
        from scripts.offline_fastmath import ParentTestTimings
        timing=ParentTestTimings();name='tests.devpr11.test_storage.StorageTests.test_one'
        first=b'test_one (tests.devpr11.test_storage.';second=b'StorageTests.test_one)'
        self.assertFalse(timing.feed(first,1))
        self.assertEqual(timing.snapshot(2)['status'],'UNKNOWN')
        self.assertTrue(timing.feed(second,3))
        active=timing.snapshot(9)
        self.assertEqual(active['active_test_id'],name)
        self.assertEqual(active['rows'][0]['elapsed_seconds'],6)
        self.assertIsNone(active['rows'][0]['completion_observed_seconds'])
        timing.feed(b'\nOriginal multi-line description ... ',10)
        timing.feed(b'ok',11)
        self.assertEqual(timing.snapshot(11)['rows'][0]['state'],'INCOMPLETE')
        self.assertTrue(timing.feed(b'\n',12))
        finished=timing.snapshot(12)
        self.assertEqual(finished['rows'][0]['observed_result'],'ok')
        self.assertEqual(finished['rows'][0]['elapsed_seconds'],9)
        self.assertIsNone(finished['active_test_id'])
        prefix=b'test_two (tests.devpr11.test_storage.StorageTests.test_two) ... '
        original=bytes(prefix);timing.feed(prefix,14);timing.feed(b'partial progress',15)
        active=timing.snapshot(20)
        self.assertEqual(prefix,original)
        self.assertEqual(active['active_test_id'],'tests.devpr11.test_storage.StorageTests.test_two')
        self.assertEqual(active['rows'][-1]['elapsed_seconds'],6)
        self.assertEqual(active['rows'][-1]['last_progress_observed_seconds'],15)
        self.assertEqual(active['rows'][-1]['reason'],'no_completion_observed')
        self.assertEqual(active['status'],'OBSERVATIONS_ONLY')

    def test_source37_parent_timing_buffered_unknown_and_finite_limits(self):
        from scripts.offline_fastmath import ParentTestTimings
        timing=ParentTestTimings()
        self.assertEqual(timing.snapshot(0)['rows'],[])
        timing.feed(b'noise ... ok\n',1)
        self.assertEqual(timing.snapshot(1)['status'],'UNKNOWN')
        batch=(b'test_a (tests.devpr11.test_scope.ScopeTests.test_a) ... ok\n'
               b'test_b (tests.devpr11.test_scope.ScopeTests.test_b) ... ERROR\n')
        timing.feed(batch,5);rows=timing.snapshot(6)['rows']
        self.assertEqual([r['observed_result'] for r in rows],['ok','ERROR'])
        self.assertEqual([r['elapsed_seconds'] for r in rows],[0,0])
        self.assertIn('Buffered/coalesced',timing.snapshot(6)['limitation'])
        timing.feed(b'x'*(timing.MAX_LINE_BYTES+17),7)
        limited=timing.snapshot(8)
        self.assertTrue(limited['lines_truncated'])
        self.assertLessEqual(len(timing.buffer),timing.MAX_LINE_BYTES)
        timing.feed(b'ignored ... ok\n',9)
        for n in range(timing.MAX_ROWS+1):
            name='test_n'+str(n)
            line=(name+' (tests.devpr11.test_scope.ScopeTests.'+name+') ... ok\n').encode()
            timing.feed(line,10+n)
        limited=timing.snapshot(2000)
        self.assertEqual(len(limited['rows']),timing.MAX_ROWS)
        self.assertTrue(limited['rows_truncated'])
        timing.feed(b'test_last (tests.devpr11.test_scope.ScopeTests.test_last)',2001)
        limited=timing.snapshot(2009)
        self.assertEqual(len(limited['rows']),timing.MAX_ROWS)
        self.assertEqual(limited['active_test_id'],'tests.devpr11.test_scope.ScopeTests.test_last')
        self.assertEqual(limited['rows'][-1]['elapsed_seconds'],8)
        timing.feed(b'\n  subtest detail ... FAIL\n',2010)
        self.assertEqual(timing.snapshot(2010)['active_test_id'],limited['active_test_id'])
        timing.feed(b'test_next (tests.devpr11.test_scope.ScopeTests.test_next)',2011)
        previous=timing.snapshot(2012)['rows'][-2]
        self.assertEqual(previous['state'],'INCOMPLETE')
        self.assertEqual(previous['reason'],'next_prefix_without_completion')
        self.assertIsNone(previous['completion_observed_seconds'])

    def test_source36_ci_partition_complete_disjoint_ordered_pair(self):
        from scripts.offline_fastmath import ci_partition_ids
        first='tests.devpr11.test_storage.StorageTests.test_first'
        middle='tests.devpr11.test_domain.DomainTests.test_middle'
        last='tests.devpr11.test_storage.StorageTests.test_last'
        harness='tests.devpr11.test_scope.ScopeTests.test_new_harness'
        full=[first,middle,last,harness];original=list(full)
        core=ci_partition_ids(full,'ci-core');storage=ci_partition_ids(full,'ci-storage')
        self.assertEqual(full,original)
        self.assertEqual(core,{'full':full,'selected':[middle,harness],'complement':[first,last]})
        self.assertEqual(storage,{'full':full,'selected':[first,last],'complement':[middle,harness]})
        self.assertEqual(core['full'],storage['full'])
        self.assertFalse(set(core['selected']) & set(storage['selected']))
        self.assertEqual(set(core['selected']) | set(storage['selected']),set(full))
        self.assertEqual(len(core['selected'])+len(storage['selected']),len(full))

    def test_source36_ci_partition_rejects_unknown_duplicate_and_missing(self):
        from scripts.offline_fastmath import ci_partition_ids
        core='tests.devpr11.test_scope.ScopeTests.test_core'
        storage='tests.devpr11.test_storage.StorageTests.test_storage'
        for selector in ('default','ci','ci-all','ci-core-extra','',None):
            with self.subTest(selector=selector):
                with self.assertRaisesRegex(ValueError,'Unknown closed CI partition'):
                    ci_partition_ids([core,storage],selector)
        for invalid in (None,[],[core,storage,core],[storage,core,storage],
                        [core,''],[core,None],[core,'unittest.loader._FailedTest.test_missing']):
            for selector in ('ci-core','ci-storage'):
                with self.subTest(full=invalid,selector=selector):
                    with self.assertRaisesRegex(ValueError,'CI discovery identity'):
                        ci_partition_ids(invalid,selector)
        for missing in ([core],[storage]):
            for selector in ('ci-core','ci-storage'):
                with self.subTest(full=missing,selector=selector):
                    with self.assertRaisesRegex(ValueError,'Missing or invalid complete CI partition'):
                        ci_partition_ids(missing,selector)

    def test_source35_synthetic_graph_applicability_and_dependency_denial(self):
        from scripts import architecture_deps as D
        policy={'legacy_baseline_commit':'e4de0210f9985224e030ac4cfd2f7e2904005b37',
                'legacy_owners':{}}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for relative,raw in (
                    ('docs/reference/PMRS-Next_Phase1/source-inventory.json','{"modules":[]}'),
                    ('pmrh/domain/rules.py','VALUE = 1\n'),
                    ('pmrh/ports/spec.py','from pmrh.domain.rules import VALUE\n')):
                path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(raw)
            self.assertEqual(D.run(root,policy)['architecture_violations'],[])
            bridge=json.loads((ROOT/'config/architecture-exceptions.json').read_bytes())['devpr11_fastmath_bridge']
            malformed_paths=dict(bridge,changed_paths=[[]])
            malformed_edges=dict(bridge,direct_edges=[None])
            for declared in ({},None,[],False,'invalid',malformed_paths,malformed_edges):
                with self.subTest(declared=declared):
                    report=D.run(root,dict(policy,devpr11_fastmath_bridge=declared))
                    self.assertEqual(report['architecture_violations'],[{'reason':'invalid_devpr11_exact_scope'}])
            # Even a valid declaration must verify actual complete source and oracle.
            report=D.run(root,dict(policy,devpr11_fastmath_bridge=bridge))
            self.assertIn('invalid_devpr11_stage',{v['reason'] for v in report['architecture_violations']})
            path=root/'pmrh/adapters/disk.py';path.parent.mkdir(parents=True);path.write_text('VALUE = 1\n')
            (root/'pmrh/domain/rules.py').write_text('import pmrh.adapters.disk\n')
            report=D.run(root,policy);reasons={v['reason'] for v in report['architecture_violations']}
            self.assertIn('forbidden_new_layer_direction',reasons)
            self.assertNotIn('invalid_devpr11_exact_scope',reasons)

    def test_source35_fast_source_presence_requires_policy(self):
        from scripts import architecture_deps as D
        policy={'legacy_baseline_commit':'e4de0210f9985224e030ac4cfd2f7e2904005b37',
                'legacy_owners':{}}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);inventory=root/'docs/reference/PMRS-Next_Phase1/source-inventory.json'
            inventory.parent.mkdir(parents=True);inventory.write_text('{"modules":[]}')
            for relative in ('pmrh/domain/fastmath/model.py','pmrh/domain/fastmath/unlisted.py',
                    'pmrh/domain/native_response.py','pmrh/domain/native_settlement.py',
                    'pmrh/adapters/storage/fastmath.py','pmrh/adapters/storage/control_fast.py',
                    'pmrh/application/fastmath.py','scripts/fastmath_scope.py','tests/devpr11/unlisted.py'):
                with self.subTest(source=relative):
                    path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('VALUE = 1\n')
                    for supplied in (policy,dict(policy,devpr11_fastmath_bridge={}),
                                     dict(policy,devpr11_fastmath_bridge=None)):
                        report=D.run(root,supplied)
                        self.assertEqual(report['architecture_violations'],[{'reason':'invalid_devpr11_exact_scope'}])
                    path.unlink()

    def test_source35_real_repository_policy_and_tampering_fail_closed(self):
        from scripts import architecture_deps as D
        policy=json.loads((ROOT/'config/architecture-exceptions.json').read_bytes())
        self.assertEqual(D.run(ROOT,policy)['architecture_violations'],[])
        missing=deepcopy(policy);del missing['devpr11_fastmath_bridge']
        report=D.run(ROOT,missing)
        self.assertIn('invalid_devpr11_exact_scope',{v['reason'] for v in report['architecture_violations']})
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=self.oracle_root(root)
            for relative in set(data['baseline_file_sha256'])|G.PATHS:
                path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((ROOT/relative).read_bytes())
            path=root/'pmrh/domain/contracts.py';original=path.read_bytes()
            altered=original.replace(b'pmrs.response/4.2.2',b'pmrs.response/forged',1)
            self.assertNotEqual(altered,original);path.write_bytes(altered)
            report=D.run(root,policy)
            self.assertIn('invalid_devpr11_stage',{v['reason'] for v in report['architecture_violations']})
            path.write_bytes(original)
            path=root/'pmrh/domain/fastmath/model.py';path.write_bytes(path.read_bytes()+b'\nimport socket\n')
            report=D.run(root,policy)
            self.assertTrue(any(v['reason']=='prohibited_capability_import' and
                v.get('source')=='pmrh/domain/fastmath/model.py' for v in report['architecture_violations']))

    def test_source32_exact_symbol_uniqueness_rejects_shadow_bindings(self):
        data=G.oracle(ROOT);path='pmrh/domain/contracts.py'
        original=base64.b64decode(data['files'][path]['bytes_base64']);current=(ROOT/path).read_bytes()
        self.assertEqual(G.preintegration(path,current,ROOT),original)
        for suffix in (
                b"RESPONSE_SCHEMA = 'wrong'\n",
                b"RESPONSE_SCHEMA: str = 'wrong'\n",
                b"RESPONSE_SCHEMA: str\n",
                b"RESPONSE_SCHEMA = other = 'wrong'\n",
                b"other = RESPONSE_SCHEMA = 'wrong'\n",
                b"RESPONSE_SCHEMA, other = 'wrong', None\n",
                b"def RESPONSE_SCHEMA(): return 'wrong'\n",
                b"async def RESPONSE_SCHEMA(): return 'wrong'\n",
                b"class RESPONSE_SCHEMA: pass\n",
                b"from synthetic import wrong as RESPONSE_SCHEMA\n",
                b"from synthetic import RESPONSE_SCHEMA\n"):
            with self.subTest(binding=suffix):
                with self.assertRaisesRegex(ValueError,'Duplicate exact native symbol: RESPONSE_SCHEMA'):
                    G.preintegration(path,current+b'\n'+suffix,ROOT)
        # Actual wrapper and reexport identities must also remain unique.
        for path,name,suffix in (
                ('research_studio/changes.py','_validate',b'\ndef _validate(*args): return None\n'),
                ('research_studio/contracts.py','authoring_contract',
                 b'\nfrom pmrh.domain.native_response import authoring_contract as authoring_contract\n')):
            current=(ROOT/path).read_bytes();original=base64.b64decode(data['files'][path]['bytes_base64'])
            self.assertTrue(G.verify_file(path,original,current))
            with self.assertRaisesRegex(ValueError,'Duplicate exact native symbol: '+name):
                G.verify_file(path,original,current+suffix)
        # Isolated valid binding forms are parsed only, never executed/imported.
        for raw in (b'value = 1\n',b'value: int = 1\n',b'def value(): pass\n',
                    b'async def value(): pass\n',b'class value: pass\n',
                    b'from synthetic import original as value\n',b'from synthetic import value\n',
                    b'@staticmethod\ndef value(): pass\n'):
            with self.subTest(unique=raw):
                self.assertEqual(ast.dump(G._symbol_node(raw,'value')),ast.dump(ast.parse(raw).body[0]))
                with self.assertRaisesRegex(ValueError,'Missing exact native symbol: absent'):
                    G._symbol_node(raw,'absent')

    def test_source31_scope06_exact_files_and_inherited_guard(self):
        data=G.oracle(ROOT)
        for path in ('scripts/domain_scope.py','tests/devpr05/test_extraction_boundaries.py'):
            with self.subTest(path=path):
                original=base64.b64decode(data['files'][path]['bytes_base64'])
                current=(ROOT/path).read_bytes()
                self.assertTrue(G.verify_file(path,original,current))
                self.assertEqual(G.preintegration(path,current,ROOT),original)
                for before,after in ((original+b'\n',current),(original,current+b'\n# extra guard/test byte\n'),
                                     (original,current.replace(b'fastmath_scope.preintegration(',b'forged_preintegration(',1))):
                    self.assertNotEqual((before,after),(original,current))
                    with self.assertRaisesRegex(ValueError,'exact Scope06'):
                        G.verify_file(path,before,after)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.oracle_root(root)
            path=root/'scripts/domain_scope.py';current=path.read_bytes()
            for bad in (base64.b64decode(data['files']['scripts/domain_scope.py']['bytes_base64']),current+b'\n'):
                path.write_bytes(bad)
                with self.assertRaisesRegex(ValueError,'Inherited guard'):G.oracle(root)
            path.write_bytes(current)
            oracle=root/'scripts/fastmath_scope_preintegration.json'
            oracle.write_bytes(oracle.read_bytes()+b'\n')
            with self.assertRaisesRegex(ValueError,'Root-pinned'):G.oracle(root)

    def test_source31_native_source_spans_and_direct_domain_guard(self):
        from scripts import domain_scope
        data=G.oracle(ROOT)
        self.assertEqual(sum(map(len,G.SCOPE04_SYMBOL_SHA256.values())),36)
        for path in ('research_studio/changes.py','research_studio/contracts.py'):
            current=(ROOT/path).read_bytes();parent=base64.b64decode(data['files'][path]['bytes_base64'])
            tree=ast.parse(current)
            # This is the original DEV04 direct caller, with its pre-extraction imports removed.
            original=ast.unparse(ast.Module(body=[n for n in tree.body if not
                (isinstance(n,ast.ImportFrom) and (n.module or '').startswith('pmrh.domain.'))],type_ignores=[]))
            domain_scope.verify_sections(path,original,current)
            self.assertTrue(G.verify_file(path,parent,current))
            # Source locations may move; each pinned symbol's complete bytes must not.
            self.assertTrue(G.verify_file(path,parent,b'# preceding comment shifts line numbers\n'+current))
            reexport=G.SCOPE04_REEXPORTS[path][0].encode()
            changed=current.replace(reexport,reexport.replace(b' as ',b' as unauthorized_'),1)
            self.assertNotEqual(changed,current)
            with self.assertRaises(ValueError):domain_scope.verify_sections(path,original,changed)
            with self.assertRaises(ValueError):G.verify_file(path,parent,changed)
            # Even an AST-equivalent trailing comment changes the frozen source span.
            changed=current.replace(reexport+b'\n',reexport+b' # unapproved bytes\n',1)
            self.assertNotEqual(changed,current)
            with self.assertRaisesRegex(ValueError,'exact native extraction'):G.verify_file(path,parent,changed)
            if path=='research_studio/changes.py':
                node=G._symbol_node(current,'_validate');lines=current.splitlines(keepends=True)
                for position,addition in ((node.body[0].lineno-1,b'    unauthorized_writer_change = True\n'),
                                          (node.lineno-1,b'@staticmethod\n')):
                    modified=lines[:];modified.insert(position,addition);changed=b''.join(modified)
                    with self.assertRaisesRegex(ValueError,'exact native extraction'):G.verify_file(path,parent,changed)
                    with self.assertRaisesRegex(ValueError,'Non-domain legacy section changed'):
                        domain_scope.verify_sections(path,original,changed)

    def test_source31_shared_constant_and_unrelated_domain_remain_exact(self):
        data=G.oracle(ROOT);path='pmrh/domain/contracts.py'
        original=base64.b64decode(data['files'][path]['bytes_base64']);current=(ROOT/path).read_bytes()
        self.assertEqual(G.preintegration(path,current,ROOT),original)
        for changed in (current.replace(b'pmrs.response/4.2.2',b'pmrs.response/forged',1),
                        current+b'\nUNAUTHORIZED_DOMAIN_SYMBOL = True\n'):
            self.assertNotEqual(changed,current)
            with self.assertRaises(ValueError):G.preintegration(path,changed,ROOT)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.oracle_root(root)
            for relative in set(data['baseline_file_sha256'])|G.PATHS:
                destination=root/relative;destination.parent.mkdir(parents=True,exist_ok=True)
                destination.write_bytes((ROOT/relative).read_bytes())
            self.assertEqual(G.verify(root)['status'],'PASS')
            path=root/'pmrh/domain/knowledge.py';raw=path.read_bytes()
            path.write_bytes(raw+b'\nUNRELATED_DOMAIN_CHANGE = True\n')
            with self.assertRaisesRegex(ValueError,'Unowned baseline file changed: pmrh/domain/knowledge.py'):
                G.verify(root)

    def oracle_root(self,path):
        data=G.oracle(ROOT)
        for relative in ('scripts/fastmath_scope_preintegration.json',*data['inherited_guard_hashes']):
            target=path/relative;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes((ROOT/relative).read_bytes())
        return data

    def test_FM22_exact_pinned_oracle_and_missing_swapped_forged_rejection(self):
        self.assertEqual(len(G.PATHS),48)
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
