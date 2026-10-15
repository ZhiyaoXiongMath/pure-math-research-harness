import ast
import base64
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import architecture_deps as deps, storage_scope
from research_studio.util import PMRSError,canonical,sha
from . import fixtures as F

ROOT=Path('/source')
BASE=Path('/baseline')


class Extraction(unittest.TestCase):
    def test_query_output_matches_original_and_runtime_imports_are_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);store,iid,_,_,_=F.project(root/'p',extended=False)
            baseline=root/'old.json';current=root/'new.json'
            old=F.child('oracle','baseline','query:'+iid,store.root,baseline)
            new=F.child('query',store.root,iid,current)
            self.assertEqual(old.returncode,0,old.stderr);self.assertEqual(new.returncode,0,new.stderr)
            expected=json.loads(baseline.read_text());actual=json.loads(current.read_text())['value']
            for value in (expected,actual):value['host_pool'].pop('observed_at')
            self.assertTrue(actual['available'],actual)
            self.assertEqual(actual,expected)
            self.assertEqual(actual['main']['native_goal']['desired_status'],'paused')

    def test_static_closure_shrinks_and_general_layer_rules_remain(self):
        policy=json.loads((ROOT/'config/architecture-exceptions.json').read_text())
        report=deps.run(ROOT,policy);self.assertEqual(report['architecture_violations'],[])
        old=deps.run(BASE,json.loads((BASE/'config/architecture-exceptions.json').read_text()))
        for query in ('pmrh/cli.py','pmrh/__main__.py','research_studio/readonly_query.py'):
            self.assertLess(len(report['transitive_graph'][query]),len(old['transitive_graph'][query]))
            self.assertNotIn('research_studio/native_main.py',report['transitive_graph'][query])
        for path in ('pmrh/adapters/storage/journal.py','pmrh/adapters/storage/repositories.py'):
            self.assertFalse(any(p.startswith('research_studio/') for p in report['transitive_graph'][path]))
        self.assertNotIn('adapters',deps.ALLOWED['application'])
        self.assertNotIn('adapters',deps.ALLOWED['interfaces'])
        bad=deepcopy(policy);bad['devpr05_storage_bridge']['direct_edges'].append({
            'source':'research_studio/','target':'pmrh/','owner':'DEV-PR-05','remove_by':'DEV-PR-18','consumer':'bad','reason':'bad'})
        self.assertIn('invalid_devpr05_storage_allowlist',{v['reason'] for v in deps.run(ROOT,bad)['architecture_violations']})
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for path,text in {'pmrh/__init__.py':'','pmrh/application/__init__.py':'',
                'pmrh/adapters/__init__.py':'','pmrh/adapters/bad.py':'',
                'pmrh/application/bad.py':'import pmrh.adapters.bad\n'}.items():
                p=root/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
            violations=deps.run(root,policy)['architecture_violations']
            self.assertIn('forbidden_new_layer_direction',{v['reason'] for v in violations})

    def test_exact_symbol_guard_and_shared_compatibility_identity(self):
        from pmrh.application import read_projections as pure
        from pmrh.adapters.storage import io,native_format,pool_read
        from research_studio import native_main,scheduler,language,host_pool,util,strategy
        for old,new in [(native_main.view,pure.native_view),(native_main.desired,pure.native_desired),
                        (scheduler.budget_remaining,pure.budget_remaining),(strategy.current,pure.strategy_current),
                        (language.policy,native_format.policy),(host_pool.read_status,pool_read.read_status),
                        (util.atomic,io.atomic)]:self.assertIs(old,new)
        self.assertIs(language.DEFAULT,native_format.DEFAULT)
        for path in storage_scope.SYMBOLS:
            original=(BASE/path).read_bytes();current=(ROOT/path).read_bytes()
            storage_scope.verify_sections(path,original,current)
            with self.assertRaises(ValueError):storage_scope.verify_sections(path,original,current+b'\nforbidden_extra_symbol = True\n')
        for directory in ('pmrh/domain','pmrh/ports','scripts/offline_guard'):
            for path in (BASE/directory).rglob('*'):
                if path.is_file():self.assertEqual(path.read_bytes(),(ROOT/path.relative_to(BASE)).read_bytes())

    def test_frozen_symbol_fingerprints_bind_exact_source_segments(self):
        import hashlib
        self.assertEqual(set(storage_scope.ORIGINAL_SOURCE_SEGMENT_SHA256),set(storage_scope.SYMBOLS))
        for path,symbols in storage_scope.SYMBOLS.items():
            original=(BASE/path).read_bytes();text=original.decode('utf-8')
            expected=storage_scope.ORIGINAL_SOURCE_SEGMENT_SHA256[path]
            self.assertEqual(set(expected),set(symbols))
            for node in ast.parse(text).body:
                symbol=(node.name if isinstance(node,(ast.FunctionDef,ast.ClassDef)) else
                        node.targets[0].id if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) else None)
                if symbol in expected:
                    segment=ast.get_source_segment(text,node)
                    self.assertIsNotNone(segment)
                    self.assertEqual(hashlib.sha256(segment.encode('utf-8')).hexdigest(),expected[symbol])
            storage_scope.verify_sections(path,original,(ROOT/path).read_bytes())
        path='research_studio/changes.py'
        original=(BASE/path).read_bytes();current=(ROOT/path).read_bytes()
        tampered=original.replace(b'def validator_identity(',b'def validator_identity( ',1)
        self.assertNotEqual(original,tampered)
        self.assertEqual(ast.dump(ast.parse(original)),ast.dump(ast.parse(tampered)))
        with self.assertRaisesRegex(ValueError,'Frozen DEV05 source symbol differs'):
            storage_scope.verify_sections(path,tampered,current)
        with patch.object(storage_scope.ast,'get_source_segment',return_value=None):
            with self.assertRaisesRegex(ValueError,'Frozen DEV05 source segment missing'):
                storage_scope.verify_sections(path,original,current)

    def test_actual_live_format_fingerprint_and_historical_identity(self):
        from tests.test_contract421 import FormatContract421
        from research_studio import changes,execution
        fixture=FormatContract421();fixture.setUp()
        raw=json.loads(fixture.f.raw(fixture.task,[fixture.arg_op()]))
        raw['request_id']='wrong';raw['payload']['read_set_digest']='wrong';raw=canonical(raw)
        capture=sha(raw);fixture.f.blobs[capture]=raw
        rid=fixture.task['request_id']
        fixture.f.s['requests'][rid]={'request_id':rid,'task_id':fixture.task['task_id'],
            'capture_ref':capture,'execution_state':'SETTLED','acceptance_state':'REJECTED_CONTRACT',
            'admission_error':'RESPONSE_SCHEMA_INVALID'}
        diagnostic=execution.format_diagnostic(fixture.f.s,rid,raw,fixture.f.get)
        proof={'schema':'pmrs.format-repair-proof/1','raw_base64':base64.b64encode(raw).decode(),
               'diagnostic':diagnostic}
        self.assertTrue(execution.verify_format_proof(fixture.f.s,rid,proof,fixture.f.get))
        saved=deepcopy(proof);real=Path.read_bytes
        moved=[ROOT/'research_studio/storage_compat.py',ROOT/'research_studio/util.py',ROOT/'research_studio/resources.py',
               ROOT/'pmrh/application/unit_of_work.py',ROOT/'pmrh/application/read_projections.py']
        moved+=sorted((ROOT/'pmrh/adapters/storage').glob('*.py'))
        # Include package initialization and the complete statically registered
        # DTO closure, including authorization types, not just direct storage imports.
        port_paths=['pmrh/ports/__init__.py','pmrh/ports/interfaces.py']
        port_paths+=['pmrh/ports/dto/'+name+'.py' for name in
                    ('__init__','wire','core','enums','events','storage','control',
                     'capability','execution','orchestration','specs')]
        moved += [ROOT/path for path in port_paths]
        for path in moved:
            with self.subTest(path=path):
                key=str(path.relative_to(ROOT))
                self.assertIn(key,diagnostic['validator_revision']['modules'])
                self.assertEqual(diagnostic['validator_revision']['modules'][key],sha(real(path)))
                def changed(p):return real(p)+(b'\n# simulated changed implementation\n' if p==path else b'')
                with patch.object(Path,'read_bytes',changed):
                    with self.assertRaisesRegex(PMRSError,'ORIGINAL_BYTES_MISMATCH'):
                        execution.verify_format_proof(fixture.f.s,rid,proof,fixture.f.get)
                    self.assertTrue(execution.verify_format_proof(fixture.f.s,rid,proof,fixture.f.get,historical=True))
                self.assertEqual(proof,saved)
        # A previously recorded module-map shape without this closure remains
        # historical evidence; it cannot authorize live FORMAT under new code.
        prior=deepcopy(proof)
        for key in port_paths:prior['diagnostic']['validator_revision']['modules'].pop(key)
        recorded=deepcopy(prior)
        self.assertTrue(execution.verify_format_proof(fixture.f.s,rid,prior,fixture.f.get,historical=True))
        with self.assertRaisesRegex(PMRSError,'ORIGINAL_BYTES_MISMATCH'):
            execution.verify_format_proof(fixture.f.s,rid,prior,fixture.f.get)
        self.assertEqual(prior,recorded)
        self.assertEqual(proof,saved)

    def test_scope_02_only_migrates_the_concurrent_publication_hook(self):
        original=(BASE/storage_scope.TEST_SEAM_PATH).read_bytes()
        current=(ROOT/storage_scope.TEST_SEAM_PATH).read_bytes()
        storage_scope.verify_test_seam(original,current)
        mutations=[current+b'\n# Outside-method edit\n',
            current.replace(b"self.assertEqual(result['commit'], head['commit'])",
                            b"self.assertTrue(True)",1),
            current.replace(b"newer['instances'][IID]['status'] = 'ACTIVE'",
                            b"newer['instances'][IID]['status'] = 'PAUSED'",1),
            current.replace(b'class PoolTests(unittest.TestCase):',
                            b'class ChangedPoolTests(unittest.TestCase):',1)]
        for changed in mutations:
            with self.assertRaises(ValueError):storage_scope.verify_test_seam(original,changed)

    def test_ci_artifact_gates_allow_only_the_exact_dev05_relocation(self):
        from tests.devpr01.test_review_closure import CIArtifactReviewClosure
        from tests.devpr02.test_ci_contracts import ArtifactGateTests
        report=deps.run(ROOT,json.loads((ROOT/'config/architecture-exceptions.json').read_text()))
        self.assertEqual(report['architecture_violations'],[])
        old='research_studio/store.py';current='research_studio/storage_compat.py'
        target='research_studio/native_main.py'
        rows=report['named_architectural_couplings']
        index=next(i for i,row in enumerate(rows) if row['source']==old and row['target']==target)
        self.assertEqual(rows[index]['status'],'RELOCATED_TO_TRUSTED_WRITER_ASSEMBLY')
        for fixture in (CIArtifactReviewClosure,ArtifactGateTests):
            case=fixture();case.setUp();self.addCleanup(case.doCleanups)
            graph=deepcopy(case.graph)
            for key in ('direct_graph','direct_imports','named_architectural_couplings'):
                graph[key]=deepcopy(report[key])
            artifact=case.root/'ast/dependency-graph.json'
            artifact.write_text(json.dumps(graph))
            self.assertEqual(case.validate()['status'],'PASS')
            negatives=[]
            for field,value in [('source','research_studio/other.py'),('target','research_studio/runner.py'),
                                ('owner','DEV-PR-07'),('current_source','research_studio/other.py'),
                                ('status','MISSING_DIRECT_EDGE'),('status','MATCHED_DIRECT_EDGE'),
                                ('direct_occurrences',1)]:
                bad=deepcopy(graph);bad['named_architectural_couplings'][index][field]=value
                negatives.append((field+':'+str(value),bad))
            bad=deepcopy(graph);bad['direct_graph'][old].append(target)
            negatives.append(('old edge restored',bad))
            bad=deepcopy(graph);bad['direct_imports'].append({'source':old,'target':target})
            negatives.append(('old import restored',bad))
            bad=deepcopy(graph);bad['direct_graph'][current].remove(target)
            negatives.append(('new direct edge absent',bad))
            bad=deepcopy(graph);bad['direct_imports']=[e for e in bad['direct_imports']
                if (e['source'],e['target'])!=(current,target)]
            negatives.append(('new import absent',bad))
            for node in (old,current):
                bad=deepcopy(graph);del bad['direct_graph'][node]
                negatives.append(('node absent:'+node,bad))
            bad=deepcopy(graph);del bad['named_architectural_couplings'][index]
            negatives.append(('named original absent',bad))
            bad=deepcopy(graph);bad['named_architectural_couplings'].append(deepcopy(rows[index]))
            negatives.append(('duplicate relocation',bad))
            bad=deepcopy(graph);duplicate=deepcopy(rows[index]);duplicate['status']='MATCHED_DIRECT_EDGE'
            bad['named_architectural_couplings'].append(duplicate)
            negatives.append(('contradictory original tuple',bad))
            bad=deepcopy(graph)
            next(row for row in bad['named_architectural_couplings'] if row['source']!=old)['status']='MISSING_DIRECT_EDGE'
            negatives.append(('unrelated missing coupling',bad))
            for label,bad in negatives:
                with self.subTest(gate=fixture.__name__,mutation=label):
                    artifact.write_text(json.dumps(bad))
                    with self.assertRaises(ValueError):case.validate()

    def test_original_admission_and_initializer_bodies_are_unchanged(self):
        original=ast.parse((BASE/'research_studio/store.py').read_text())
        moved=ast.parse((ROOT/'research_studio/storage_compat.py').read_text())
        old_class=next(n for n in original.body if isinstance(n,ast.ClassDef) and n.name=='Store')
        new_class=next(n for n in moved.body if isinstance(n,ast.ClassDef) and n.name=='LegacyWriters')
        for name in ('create','commit'):
            before=next(n for n in old_class.body if getattr(n,'name',None)==name)
            after=next(n for n in new_class.body if getattr(n,'name',None)==name)
            self.assertEqual(ast.dump(before,include_attributes=False),ast.dump(after,include_attributes=False))
        before=next(n for n in original.body if getattr(n,'name',None)=='initial_state')
        after=next(n for n in moved.body if getattr(n,'name',None)=='initial_state')
        self.assertEqual(ast.dump(before,include_attributes=False),ast.dump(after,include_attributes=False))
        # The five native typed publication policies retain their original map sets.
        from research_studio import store,storage_compat
        from pmrh.adapters.storage import journal
        for name in ('SCIENCE_MAPS','CONTROL_MAPS','EXECUTION_MAPS','REPORT_MAPS'):
            self.assertIs(getattr(store,name),getattr(journal,name))
        self.assertEqual(store.Store._other_control_maps,storage_compat.SURVEY_MAPS|storage_compat.ASSISTANT_MAPS)

    def test_s2_guard_rejects_unlisted_process_and_network(self):
        import socket, subprocess, sys
        with self.assertRaises(PermissionError):
            subprocess.run([sys.executable,'-c','raise AssertionError("must not execute")'],check=True)
        with self.assertRaises(PermissionError):socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        with self.assertRaises(OSError):
            with open('/source/README.md','ab'):pass

    def test_s2_spawn_requires_the_original_cleared_environment(self):
        import os, subprocess, sys
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);store,iid,_,_,_=F.project(root/'p',extended=False)
            output=root/'query.json'
            argv=[sys.executable,'-B','/source/tests/devpr05/child.py',
                  'query',str(store.root),iid,str(output)]
            environment=dict(os.environ)
            # Python 3.14 reports inherited spawn environments as None.
            # Exercise that audit event without launching an extra process.
            sys.audit('os.posix_spawn',sys.executable,argv,None)
            self.assertFalse(output.exists())
            pid=os.posix_spawn(sys.executable,argv,environment)
            _,status=os.waitpid(pid,0)
            self.assertEqual(os.waitstatus_to_exitcode(status),0)
            self.assertTrue(json.loads(output.read_text())['value']['available'])
            output.unlink()
            for name in ('PYTHONPATH','PYTHONHOME'):
                with self.subTest(name=name):
                    injected={**environment,name:'/tmp/tests/injected'}
                    with self.assertRaises(PermissionError):
                        os.posix_spawn(sys.executable,argv,injected)
                    with self.assertRaises(PermissionError):
                        subprocess.run(argv,env=injected,check=True)
                    with patch.dict(os.environ,{name:'/tmp/tests/injected'}):
                        with self.assertRaises(PermissionError):
                            sys.audit('os.posix_spawn',sys.executable,argv,None)
                        with self.assertRaises(PermissionError):
                            subprocess.run(argv,check=True)
                    self.assertFalse(output.exists())

    def test_s2_empty_discovery_and_skips_fail_closed(self):
        import io
        from contextlib import redirect_stdout
        from scripts.storage_sandbox import run_suite
        with self.assertRaisesRegex(ValueError,'EMPTY_TEST_DISCOVERY'):
            run_suite(unittest.TestSuite(),stream=io.StringIO())
        def skipped():raise unittest.SkipTest('Synthetic unexpected skip')
        for case,expected in ((lambda:None,0),(skipped,1)):
            with redirect_stdout(io.StringIO()) as output:
                result=run_suite(unittest.TestSuite([unittest.FunctionTestCase(case)]),stream=io.StringIO())
            self.assertEqual(result,expected)
            receipt=json.loads(output.getvalue().removeprefix('S2_RESULT '))
            self.assertEqual(receipt['tests'],1)
            self.assertEqual(receipt['skipped'],expected)
            self.assertEqual(receipt['status'],'PASS' if expected==0 else 'FAIL')
