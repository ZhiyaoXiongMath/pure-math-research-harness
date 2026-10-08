"""Actual offline package resources, reproducibility, installers and evidence gates."""
from pathlib import Path
from unittest.mock import patch
import copy
import hashlib
import importlib.util
import io
import json
import os
import re
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def script(name):
    spec = importlib.util.spec_from_file_location('pmrs_test_' + name.replace('-', '_'), ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


class PackagingUnitTests(unittest.TestCase):
    def test_required_inventory_has_explicit_active_and_retired_scopes(self):
        required = json.loads((ROOT / 'tests/coverage/required.json').read_text())
        self.assertEqual(required['product_version'],'4.2.0')
        cases={c['case_id'] for c in required['cases']}; retired={c['case_id'] for c in required['retired']['cases']}
        self.assertFalse(cases & retired)
        self.assertEqual(retired,{'R08','R09','R10','N27','N33','N34','N46'})
        self.assertEqual({p['port_id'] for p in required['baseline']}|{p['port_id'] for p in required['retired']['baseline']},{f'P{i:03d}' for i in range(1,132)})
        for kind in ('cases','assertions','baseline'):
            self.assertTrue(all(r['reason'] and r['disposition']=='RETIRED_BY_USER_SCOPE' for r in required['retired'][kind]))
        for case in required['cases']: self.assertEqual(case['first_required_gate'], case['phase_gate'])
        for milestone in required['milestones']:
            self.assertEqual(set(milestone['required_case_ids']), {c['case_id'] for c in required['cases'] if c['first_required_gate'] == milestone['milestone_id']})
        required_loaded,cases,ports,_=script('coverage_registry').load(ROOT)
        self.assertEqual(set(cases),{c['case_id'] for c in required_loaded['cases']})
        self.assertEqual(set(ports),{p['port_id'] for p in required_loaded['baseline']})

    def test_source_inventory_and_zip_preserve_current_resources_only(self):
        builder = script('build-release'); members = builder.files(require_docs=False)
        self.assertFalse(any(p.startswith(('historical/','research_studio/migration/')) for p in members))
        names=['research_studio/static/workbench.js','research_studio/contracts.py','tests/fixtures/builders/native_reader.py']
        stream = io.BytesIO(); builder.write_zip(stream, {builder.PREFIX + '/' + p: b for p, b in members.items()})
        with zipfile.ZipFile(stream) as z:
            for name in names:self.assertEqual(z.read(builder.PREFIX + '/' + name),(ROOT/name).read_bytes())

    def test_wheel_contains_all_native_resources_and_verified_record(self):
        builder = script('build-release'); installer = script('install-local'); members = builder.files(require_docs=False)
        members.update({'research_studio/schemas/test-resource.json': b'{"fixture":true}',
            'research_studio/static/test-resource.css': b'body{}', 'research_studio/static/fonts/test-resource.woff2': b'font-fixture'})
        name, raw = builder.wheel(members); contents = installer.verify_wheel(raw)
        for p, b in members.items():
            if p.startswith('research_studio/'): self.assertEqual(contents[p], b)
        self.assertFalse(any(p.startswith(('historical/', 'tests/')) for p in contents))
        self.assertTrue(name.endswith('.whl'))

    def test_wheel_rejects_unbound_or_tampered_resources(self):
        builder = script('build-release'); installer = script('install-local'); _, raw = builder.wheel(builder.files(require_docs=False))
        with zipfile.ZipFile(io.BytesIO(raw)) as z: rows = {p: z.read(p) for p in z.namelist()}
        rows['research_studio/cli.py'] += b'\n# changed\n'
        stream = io.BytesIO(); builder.write_zip(stream, rows)
        with self.assertRaisesRegex(ValueError, 'Wheel content changed'): installer.verify_wheel(stream.getvalue())
        rows['research_studio/unbound.json'] = b'{}'; stream = io.BytesIO(); builder.write_zip(stream, rows)
        with self.assertRaisesRegex(ValueError, 'Wheel RECORD member set differs'): installer.verify_wheel(stream.getvalue())

    def test_desktop_entry_handles_spaces_and_shell_metacharacters_without_shell(self):
        installer = script('install-local')
        text = installer.desktop_entry(Path('/tmp/folder name/$literal%value/pmrs-desktop'))
        self.assertIn('Terminal=false', text); self.assertIn('%%value', text)
        self.assertNotIn('sh -c', text)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'test.desktop'; p.write_text(text)
            run = subprocess.run(['desktop-file-validate', str(p)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
        run = subprocess.run(['desktop-file-validate', str(ROOT / 'Install-PMRS.desktop')], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_dependency_detection_never_installs_or_calls_models(self):
        gui = script('install-gui')
        with patch.object(gui.shutil, 'which', return_value=None), patch.object(gui.subprocess, 'Popen') as popen:
            missing = gui.missing_packages(); self.assertIn('bubblewrap', missing); popen.assert_not_called()
        with patch.object(gui, 'dialog') as dialog, patch.object(gui.shutil, 'which', return_value='/usr/bin/pkexec'), patch.object(gui.subprocess, 'Popen') as popen:
            dialog.return_value.returncode = 1
            self.assertFalse(gui.install_system_packages(['bubblewrap'])); popen.assert_not_called()

    def test_resource_manifest_hashes_json_css_fonts_and_all_fixture_bytes(self):
        registry = script('coverage_registry'); manifest = registry.source_manifest(ROOT)
        self.assertIn('tests/coverage/required.json', manifest)
        self.assertIn('tests/fixtures/builders/native_reader.py', manifest)
        self.assertIn('research_studio/portability.py', manifest)
        self.assertIn('Install-PMRS.desktop', manifest); self.assertIn('INSTALL-HELP.html',manifest)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root / 'research_studio/static/fonts').mkdir(parents=True)
            for name, raw in [('style.css', b'a{}'), ('font.woff2', b'font'), ('rules.json', b'{}')]:
                (root / 'research_studio/static/fonts' / name).write_bytes(raw)
            (root / 'pyproject.toml').write_text('')
            files = registry.source_manifest(root)
            self.assertEqual(len(files), 4)
            self.assertEqual(files['research_studio/static/fonts/font.woff2'], hashlib.sha256(b'font').hexdigest())

    def test_required_missing_skip_and_unrun_do_not_turn_into_pass(self):
        registry = script('coverage_registry')
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); directory = root / 'tests/coverage'; directory.mkdir(parents=True)
            required = {'schema': 'pmrs.required-test-inventory/1', 'cases': [{'case_id': 'N01', 'required': True, 'assertion_ids': ['N01.a1']}], 'baseline': [{'port_id': 'P001', 'required': True}]}
            (directory / 'required.json').write_text(json.dumps(required))
            self.assertFalse(registry.evaluate(root, {})['required_complete'])
            mapping = {'schema': 'pmrs.test-coverage/1', 'acceptance': [{'case_id': 'N01', 'assertions': [{'assertion_id': 'N01.a1', 'test_ids': ['tests.module.T.test_actual']}]}], 'baseline': [{'port_id': 'P001', 'disposition': 'RETAIN', 'reason': 'Actual invariant assertion', 'test_ids': ['tests.module.T.test_actual']}]}
            (directory / 'mapping.json').write_text(json.dumps(mapping))
            self.assertFalse(registry.evaluate(root, {})['required_complete'])
            self.assertFalse(registry.evaluate(root, {'tests.module.T.test_actual': {'outcome': 'SKIP'}})['required_complete'])
            self.assertTrue(registry.evaluate(root, {'tests.module.T.test_actual': {'outcome': 'PASS'}})['required_complete'])
            bad = copy.deepcopy(mapping); bad['acceptance'][0]['assertions'][0]['assertion_id'] = 'invented'
            (directory / 'mapping.json').write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError, 'Unknown/duplicate assertion'): registry.load(root)

    def test_runner_required_skip_zero_and_missing_mapping_exit_nonzero(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); directory = root / 'tests/coverage'; directory.mkdir(parents=True)
            (root / 'tests/__init__.py').write_text(''); (root / 'pyproject.toml').write_text('')
            (root / 'tests/test_example.py').write_text('import unittest\nclass T(unittest.TestCase):\n @unittest.skip("deliberately unavailable")\n def test_skip(self):pass\n def test_pass(self):self.assertTrue(True)\n')
            required = {'schema': 'pmrs.required-test-inventory/1', 'cases': [{'case_id': 'N01', 'required': True, 'assertion_ids': ['N01.a1']}], 'baseline': []}
            (directory / 'required.json').write_text(json.dumps(required))
            for name, test_id in [('missing', 'tests.test_example.T.test_pass'), ('skip', 'tests.test_example.T.test_skip'), ('zero', None)]:
                if name != 'missing':
                    (directory / 'mapping.json').write_text(json.dumps({'schema': 'pmrs.test-coverage/1', 'acceptance': [{'case_id': 'N01', 'assertions': [{'assertion_id': 'N01.a1', 'test_ids': [test_id or 'tests.test_example.T.test_pass']}]}]}))
                evidence = root / (name + '.json')
                command = [sys.executable, '-B', str(ROOT / 'scripts/test-runner.py'), '--root', str(root), '--out', str(evidence), '--required']
                if test_id: command.append(test_id)
                run = subprocess.run(command, capture_output=True, text=True)
                self.assertNotEqual(run.returncode, 0, run.stdout)
                result = json.loads(evidence.read_text()); self.assertEqual(result['status'], 'FAIL')
                self.assertFalse(result['coverage']['required_complete'])

    def test_group_plan_is_not_execution_and_shared_actual_tests_are_deduplicated(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);coverage=root/'tests/coverage';coverage.mkdir(parents=True)
            (root/'tests/__init__.py').write_text('');(root/'pyproject.toml').write_text('')
            (root/'tests/test_example.py').write_text('import unittest\nclass T(unittest.TestCase):\n def test_one(self):self.assertEqual(2+2,4)\n')
            required={'schema':'pmrs.required-test-inventory/1','cases':[{'case_id':c,'required':True,'assertion_ids':[c+'.a1']} for c in ['N01','N02']],'baseline':[]}
            (coverage/'required.json').write_text(json.dumps(required))
            (coverage/'mapping.json').write_text(json.dumps({'schema':'pmrs.test-coverage/1','acceptance':[
                {'case_id':c,'assertions':[{'assertion_id':c+'.a1','test_ids':['tests.test_example.T.test_one']}]} for c in ['N01','N02']]}))
            (root/'scripts').mkdir()
            for name in ('test-runner.py','coverage_registry.py','browser_evidence.py'):shutil.copyfile(ROOT/'scripts'/name,root/'scripts'/name)
            with patch.object(sys,'path',[str(ROOT/'scripts'),*sys.path]):groups=script('validate-groups')
            with patch.object(groups,'ROOT',root),patch.object(sys,'argv',['validate-groups','--out',str(root/'planning'),'--planning-only']):
                self.assertEqual(groups.main(),0)
            plan=json.loads((root/'planning/SUITE-PLAN.json').read_text());self.assertEqual(plan['qualification'],'PLANNING_CHECK')
            self.assertEqual(len(plan['selected_tests']),1);self.assertFalse((root/'planning/SUITE-MANIFEST.json').exists())
            with patch.object(groups,'ROOT',root),patch.object(sys,'argv',['validate-groups','--out',str(root/'actual')]):
                self.assertEqual(groups.main(),0)
            suite=json.loads((root/'actual/SUITE-MANIFEST.json').read_text());summary=json.loads((root/'actual/GROUP-SUMMARY.json').read_text())
            self.assertEqual(suite['result']['tests'],1);self.assertEqual(suite['coverage']['case_count'],2)
            self.assertEqual(summary['unique_selected_tests'],1);self.assertTrue(summary['all_pass'])
            self.assertEqual(set(suite['result']['test_results']),{'tests.test_example.T.test_one'})


class ReleaseInstallationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(); cls.root = Path(cls.tmp.name); cls.builder = script('build-release')
        cls.result = cls.builder.build(cls.root / 'first')
        cls.release = script('install-local').extract_release(
            cls.root / 'first' / (cls.builder.PREFIX + '-release.zip'), cls.root / 'release')

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def test_n35_clean_release_prefix_and_real_wheel_venv_cli_smoke(self):
        installer = script('install-local')
        for use_venv, name in ((False, 'prefix'), (True, 'venv')):
            target = self.root / (name + ' space'); bin_dir = self.root / (name + '-launchers')
            result = installer.install(self.release, target, bin_dir, use_venv=use_venv, desktop_dir=self.root / (name + '-applications'))
            clean_env = {k: v for k, v in os.environ.items() if k not in ('PYTHONPATH', 'PYTHONHOME')}
            # Mount only system libraries and the installed-test workspace.
            # Neither the checkout nor a provider client/home is visible.
            isolation = ['/usr/bin/bwrap','--die-with-parent','--unshare-user','--unshare-pid',
                '--unshare-net','--unshare-ipc','--unshare-uts','--proc','/proc','--dev','/dev',
                '--ro-bind','/usr','/usr','--ro-bind','/lib','/lib','--ro-bind','/lib64','/lib64',
                '--bind',str(self.root),str(self.root),'--chdir',str(self.root)]
            hidden = subprocess.run(isolation+[sys.executable,'-I','-c',
                'from pathlib import Path; assert not Path('+repr(str(ROOT))+').exists()'],
                capture_output=True,text=True)
            self.assertEqual(hidden.returncode,0,hidden.stderr)
            command = isolation+[result['launcher'], '--version']; run = subprocess.run(command, cwd=self.root, env=clean_env, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr); self.assertIn(self.builder.VERSION, run.stdout)
            def cli(*args):
                run = subprocess.run(isolation+[result['launcher'], *map(str,args)], cwd=self.root, env=clean_env, capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stderr)
                return json.loads(run.stdout)
            problem = self.root / (name + '-problem.md'); problem.write_text('原始题目：For every integer n, n + 0 = n.\n')
            project = self.root / (name + '-project')
            self.assertEqual(cli('project','init','--problem',problem,'--out',project)['model_calls'],0)
            initial = cli('status',project); self.assertEqual(initial['execution']['requests'],[])
            self.assertEqual(initial['native_usage']['model_calls'],0)
            knowledge = cli('knowledge','current',project)
            target_ref = next(r['ref'] for r in knowledge['records'] if r['kind']=='Statement')
            instance = cli('workflow','new',project,'--kind','TRW','--target',target_ref)
            self.assertEqual(instance['status'],'PAUSED')
            self.assertEqual(len(cli('workflow','list',project)['instances']),1)
            prepared = cli('report',project,'--instance',instance['instance_id'],'--prepare-only')
            self.assertEqual(prepared['state'],'ROLE_REQUIRED'); self.assertEqual(prepared['model_calls'],0)
            archive=self.root/(name+'-native.zip'); restored=self.root/(name+'-restored')
            cli('project','export',project,'--out',archive)
            cli('project','restore',archive,'--out',restored)
            self.assertEqual(cli('knowledge','current',restored)['records'],knowledge['records'])
            self.assertTrue(cli('audit',restored)['valid']);self.assertTrue(cli('audit',project)['valid'])
            library = next((target/'lib').glob('python*/site-packages')) if use_venv else target
            with zipfile.ZipFile(next((self.release/'wheels').glob('*.whl'))) as wheel:
                for member in wheel.namelist():
                    if member.startswith('research_studio/'):
                        self.assertEqual((library/member).read_bytes(),wheel.read(member),member)
            python = str(target/'bin/python') if use_venv else sys.executable
            probe = '''
from pathlib import Path
from research_studio import demo,execution
from research_studio.engine import Engine
e=Engine();store=e.create(Path(PROJECT),demo.ARITHMETIC,synthetic=True)
target=next(r for r,v in store.read_snapshot()['records'].items() if v['kind']=='Statement')
i=e.new_workflow(store,'TRW',target_ref=target)['instance_id']
e.start_round(store,i,'Installed synthetic admission probe',max_calls=4,max_workers=1,policy=demo.policy())
fake=demo.executor();e.run_round(store,i,executor=fake)
s=store.read_snapshot()
assert fake.calls and fake.network_calls==0 and fake.spawn_calls==0
assert any(v['kind']=='Argument' for v in s['records'].values())
assert all(r['capture_ref'] and r['execution_state']=='SETTLED' for r in s['requests'].values())
assert s['usage']['model_calls']==0
for rid in s['requests']:assert execution.recover(store,rid)['state']=='EXACT_DUPLICATE'
assert store.read_snapshot()['knowledge_commit']==s['knowledge_commit']
assert store.audit()['valid']
'''
            probe = 'import sys;sys.path.insert(0,'+repr(str(library))+');PROJECT='+repr(str(self.root/(name+'-fake')))+'\n'+probe
            run = subprocess.run(isolation+[python,'-I','-c',probe],cwd=self.root,env=clean_env,capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            desktop_probe='''
from pathlib import Path
import json,os,time,urllib.request,urllib.parse,http.cookiejar
from research_studio.desktop import launch
root=Path(WORKSPACE);result=launch(root,open_browser=False);pid=result['pid']
try:
 assert launch(root,open_browser=False)['pid']==pid
 origin=result['url'].split('/#')[0]
 token=urllib.parse.parse_qs(urllib.parse.urlsplit(result['url']).fragment)['session'][0]
 opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
 headers={'Content-Type':'application/json','Origin':origin,'Idempotency-Key':'installed-desktop-probe-123'}
 request=urllib.request.Request(origin+'/api/session',data=json.dumps({'token':token}).encode(),headers=headers)
 with opener.open(request,timeout=5) as response:session=json.load(response)
 with opener.open(origin+'/api/workspace',timeout=5) as response:assert json.load(response)['projects']==[]
 with opener.open(origin+'/static/workbench.js',timeout=5) as response:assert response.status==200
 headers['X-PMRS-CSRF']=session['csrf']
 request=urllib.request.Request(origin+'/api/action/quit',data=b'{}',headers=headers)
 with opener.open(request,timeout=5) as response:assert json.load(response)['stopped']
 for _ in range(100):
  if not (root/'runtime/service.json').exists():break
  time.sleep(.05)
 assert not (root/'runtime/service.json').exists()
 os.waitpid(pid,0)
finally:
 try:os.kill(pid,15)
 except ProcessLookupError:pass
'''
            desktop_probe='import sys;sys.path.insert(0,'+repr(str(library))+');WORKSPACE='+repr(str(self.root/(name+'-desktop-workspace')))+'\n'+desktop_probe
            run=subprocess.run(isolation+[python,'-I','-c',desktop_probe],cwd=self.root,env=clean_env,capture_output=True,text=True,timeout=30)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertTrue(Path(result['desktop_entry']).is_file())
            if use_venv:
                run = subprocess.run([str(target / 'bin/python'), '-I', '-c', 'import research_studio,importlib.resources;print(research_studio.__file__);print(importlib.resources.files("research_studio").joinpath("contracts.py").is_file())'], cwd=self.root, env=clean_env, capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stderr); self.assertIn(str(target), run.stdout); self.assertIn('True', run.stdout)
                self.assertNotIn(str(ROOT), run.stdout)
            self.assertEqual(result['network_calls'], 0)
            with self.assertRaisesRegex(ValueError, 'new installation prefix'): installer.install(self.release, target, bin_dir)

    def test_n36_fixed_epoch_reproducible_source_release_and_wheel(self):
        second = self.builder.build(self.root / 'second')
        self.assertEqual(self.result['artifacts'], second['artifacts'])
        for artifact in self.result['artifacts']:
            a = self.root / 'first' / artifact['filename']; b = self.root / 'second' / artifact['filename']
            self.assertEqual(a.read_bytes(), b.read_bytes())
        self.assertEqual((self.root / 'first/SHA256SUMS.txt').read_bytes(), (self.root / 'second/SHA256SUMS.txt').read_bytes())
        audit=json.loads((self.root/'first/FINAL-ARTIFACT-AUDIT.json').read_text())
        self.assertFalse(any('continuation' in name for name in audit['artifacts']))
        for name,info in audit['artifacts'].items():
            raw=(self.root/'first'/name).read_bytes();self.assertEqual(hashlib.sha256(raw).hexdigest(),info['sha256'])
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                self.assertEqual(set(info['files']),set(archive.namelist()))
                for path,member in info['files'].items():
                    self.assertEqual(hashlib.sha256(archive.read(path)).hexdigest(),member['sha256'])
        with zipfile.ZipFile(self.root / 'first' / (self.builder.PREFIX + '-source.zip')) as z:
            current = 'research_studio/static/workbench.js'
            self.assertEqual(z.read(self.builder.PREFIX + '/' + current), (ROOT / current).read_bytes())
            self.assertFalse(any('/historical/' in name for name in z.namelist()))
            self.assertIn(self.builder.PREFIX + '/SOURCE-MANIFEST.json', z.namelist())

    def test_release_install_rejects_extra_and_modified_files_before_creating_prefix(self):
        installer = script('install-local'); clone = self.root / 'tampered'; shutil.copytree(self.release, clone)
        (clone / 'research_studio/extra.py').write_text('')
        with self.assertRaisesRegex(ValueError, 'member set differs'):
            installer.install(clone, self.root / 'must-not-exist', self.root / 'must-not-launch')
        self.assertFalse((self.root / 'must-not-exist').exists())
        (clone / 'research_studio/extra.py').unlink(); p = clone / 'research_studio/cli.py'; p.write_bytes(p.read_bytes() + b'changed')
        with self.assertRaisesRegex(ValueError, 'Release file changed'): installer.verify_release(clone)

    def test_n40_actual_ubuntu26_fresh_install_isolation_and_real_pdf_evidence(self):
        release={}
        for line in Path('/etc/os-release').read_text().splitlines():
            if '=' in line:
                k,v=line.split('=',1);release[k]=v.strip('"')
        self.assertEqual((release.get('ID'),release.get('VERSION_ID'),platform.machine()),('ubuntu','26.04','x86_64'))
        evidence_root=Path(os.environ.get('PMRS_TEST_ARTIFACTS_ROOT',str(ROOT.parent/(ROOT.name+'-validation')/'test-artifacts')))
        self.assertFalse(evidence_root.resolve().is_relative_to(ROOT));evidence_root.mkdir(parents=True,exist_ok=True)
        out=Path(tempfile.mkdtemp(prefix='installed-ubuntu26-',dir=evidence_root))
        result=script('install-local').install(self.release,out/'installed',out/'launchers',use_venv=True)
        library=next((out/'installed/lib').glob('python*/site-packages'))
        env={k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONHOME')}
        diagnostic=subprocess.run([result['launcher'],'doctor'],cwd=out,env=env,capture_output=True,text=True,timeout=60)
        (out/'doctor.stdout.json').write_text(diagnostic.stdout);(out/'doctor.stderr.txt').write_text(diagnostic.stderr)
        self.assertEqual(diagnostic.returncode,0,diagnostic.stderr);doctor=json.loads(diagnostic.stdout)
        self.assertTrue(doctor['execution']['ready'],doctor);self.assertEqual(doctor['pdf']['missing'],[])
        self.assertEqual(doctor['model_calls'],0);self.assertEqual(doctor['pdf']['production_render_test'],'NOT_RUN')
        policy=subprocess.run([result['launcher'],'model-policy'],cwd=out,env=env,capture_output=True,text=True,timeout=10)
        self.assertEqual(policy.returncode,0,policy.stderr);(out/'model-policy.json').write_text(policy.stdout)
        parsed=json.loads(policy.stdout);self.assertFalse(parsed['ultra_default']);self.assertEqual(parsed['unsupported_behavior'],'REJECT_WITHOUT_FALLBACK')
        check=subprocess.run([sys.executable,'-B',str(self.release/'scripts/verify-pdf.py'),'--runtime-root',str(library),'--out',str(out/'real-pdf')],
            cwd=out,env=env,capture_output=True,text=True,timeout=120)
        (out/'renderer.stdout.json').write_text(check.stdout);(out/'renderer.stderr.txt').write_text(check.stderr)
        self.assertEqual(check.returncode,0,check.stdout+check.stderr)
        rendered=json.loads((out/'real-pdf/RESULT.json').read_text())
        self.assertEqual(rendered['status'],'PASS');self.assertEqual(rendered['pages'],2)
        for key in ('offline','namespace_isolated','all_pages_rendered'):self.assertTrue(rendered['environment'][key])
        self.assertEqual(rendered['paid_model_calls'],0);self.assertFalse(rendered['mathematical_report_approved'])
        self.assertTrue(Path(rendered['runtime_file']).is_relative_to(library))
        assets={}
        for path in sorted((library/'research_studio').rglob('*')):
            if not path.is_file() or '__pycache__' in path.parts:continue
            name=path.relative_to(library).as_posix();raw=path.read_bytes()
            self.assertEqual(raw,(ROOT/name).read_bytes(),'Candidate runtime changed since build: '+name)
            assets[name]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
        evidence={'schema':'pmrs.installed-target-component-evidence/1','os_release':release,'architecture':platform.machine(),
            'python':sys.version,'build':self.result['build'],'source_sha256':hashlib.sha256(script('coverage_registry').encoded(script('coverage_registry').source_manifest(ROOT))).hexdigest(),
            'installed_runtime':str(library),'installed_assets':assets,'doctor':doctor,'actual_real_pdf':rendered,
            'component_status':'PASS','target_e2e':'PARTIAL_PENDING_ACTUAL_INSTALLED_BROWSER_AND_VISUAL_OBSERVATIONS',
            'paid_model_calls':0,'files':{p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*'))
                if p.is_file() and not p.is_relative_to(out/'installed') and not p.is_relative_to(out/'launchers')}}
        (out/'EVIDENCE.json').write_text(json.dumps(evidence,indent=2)+'\n')
        print('Actual installed Ubuntu/PDF component evidence: '+str(out/'EVIDENCE.json'))


if __name__ == '__main__': unittest.main()
