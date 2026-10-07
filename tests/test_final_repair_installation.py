"""R01 regressions: actual package bytes/modes and explicit graphical setup paths.

Selector/download fixtures are not native desktop-click or network acceptance.
"""
from pathlib import Path
from unittest.mock import patch
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import tarfile
import tempfile
import time
import unittest
import zipfile
from research_studio import setup, render, codex_client

ROOT = Path(__file__).resolve().parents[1]


def script(name):
    spec = importlib.util.spec_from_file_location('repair_' + name.replace('-', '_'), ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


class InstallationRepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {'XDG_CONFIG_HOME': str(self.root / 'config'), 'XDG_DATA_HOME': str(self.root / 'data'), 'XDG_CACHE_HOME': str(self.root / 'cache')})
        self.env.start(); self.addCleanup(self.env.stop)

    def executable(self, name):
        path = self.root / name; path.write_text('#!/bin/sh\necho "fixture 0.1"\n'); path.chmod(0o755); return path

    def release_members(self):
        members = {p: b'# fixture\n' for p in ('research_studio/cli.py','research_studio/__init__.py','research_studio/contracts.py','research_studio/workflows/registry.py','scripts/install-gui.py')}
        members.update({'LICENSE': b'fixture license', 'Install-PMRS.desktop': (ROOT / 'Install-PMRS.desktop').read_bytes(), 'start.sh': b'#!/bin/sh\nexit 0\n'})
        members['RELEASE-MANIFEST.json'] = json.dumps({'schema':'pmrs.release/1','version':'4.0.0','files':{
            name:{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'mode':0o755 if name.endswith(('.sh','.desktop')) else 0o644}
            for name,raw in members.items()}}).encode()
        return members

    def test_setup_detection_is_read_only_and_never_opens_install_or_model(self):
        with patch.object(setup.subprocess, 'run') as run, patch.object(setup.subprocess, 'Popen') as popen, patch.object(setup.urllib.request, 'build_opener') as network:
            result = setup.status()
            self.assertEqual(result['model_calls'], 0); self.assertEqual(result['network_calls'], 0)
            self.assertIn('PATH_PRESENCE_ONLY', result['readiness_scope'])
            run.assert_not_called(); popen.assert_not_called(); network.assert_not_called()
        self.assertFalse((self.root / 'config').exists()); self.assertFalse((self.root / 'data').exists())

    def test_selected_paths_merge_and_drive_cli_and_renderer_without_environment_edits(self):
        codex = self.executable('chosen codex'); tectonic = self.executable('chosen tectonic')
        cache = self.root / 'offline-cache'; cache.mkdir(); (cache / 'resource').write_bytes(b'fixture')
        ca = self.root / 'anchors.pem'; ca.write_text('-----BEGIN CERTIFICATE-----\nfixture\n')
        setup.configure({'codex': str(codex)}); setup.configure({'tectonic': str(tectonic), 'tectonic_cache': str(cache), 'ca_bundle': str(ca)})
        self.assertEqual(setup.resolve_binary('codex', 'codex'), str(codex))
        with patch.dict(os.environ, {}, clear=False), patch.object(render.os, 'environ', {k:v for k,v in os.environ.items() if not k.startswith('RS_')}):
            self.assertEqual(render.tool('tectonic'), str(tectonic)); self.assertEqual(render.cache_root(), cache); self.assertEqual(render.ca_bundle(), ca)
        with patch.object(codex_client.subprocess, 'run', return_value=subprocess.CompletedProcess([],0,'fixture\n','')) as run:
            self.assertTrue(codex_client.status()['authenticated'])
            self.assertEqual(run.call_args_list[0].args[0][0], str(codex))
        self.assertEqual((setup.config_root() / 'dependencies.json').stat().st_mode & 0o777, 0o600)
        setup.configure({'ca_bundle': None}); self.assertEqual(setup.configured_path('codex'), str(codex))
        codex.unlink(); self.assertIsNone(setup.resolve_binary('codex'))
        tectonic.unlink()
        with self.assertRaisesRegex(Exception, 'PDF_TOOL_MISSING'): render.tool('tectonic')

    def test_invalid_config_and_cache_links_rejected_before_settings_change(self):
        codex = self.executable('codex'); setup.configure({'codex': str(codex)})
        before = (setup.config_root() / 'dependencies.json').read_bytes()
        cache = self.root / 'bad-cache'; cache.mkdir(); (cache / 'outside').symlink_to(codex)
        for fields in ({'arbitrary': str(codex)}, {'codex':'relative'}, {'tectonic_cache':str(cache)}, {'ca_bundle':str(codex)}):
            with self.assertRaises((ValueError, FileNotFoundError)): setup.configure(fields)
        mixed=self.root/'mixed.pem';mixed.write_text('-----BEGIN CERTIFICATE-----\npublic\n-----BEGIN PRIVATE KEY-----\nprivate\n')
        with self.assertRaisesRegex(ValueError,'without private keys'):setup.configure({'ca_bundle':str(mixed)})
        self.assertEqual(before, (setup.config_root() / 'dependencies.json').read_bytes())

    def test_pdf_components_do_not_gate_detected_cli_and_resource_setup_has_no_credentials(self):
        codex=self.executable('codex');tectonic=self.executable('tectonic')
        setup.configure({'codex':str(codex),'tectonic':str(tectonic)})
        with patch.object(setup,'SYSTEM_FONTS',('a-font-that-is-not-installed.ttf',)):
            state=setup.status();self.assertTrue(state['research_ready']);self.assertFalse(state['pdf_dependencies_present'])
            self.assertFalse(next(c for c in state['components'] if c['id']=='pdf_system')['installed'])
        work=self.root/'prepare';work.mkdir();setup.data_root().mkdir(parents=True)
        def compile_fixture(command,**kwargs):
            self.assertIn('--untrusted',command);self.assertNotIn('--only-cached',command)
            self.assertEqual(kwargs['env']['HOME'],str(work));self.assertNotIn('OPENAI_API_KEY',kwargs['env'])
            self.assertNotIn('CODEX_HOME',kwargs['env']);self.assertNotIn('RESEARCH_SECRET',kwargs['env'])
            cache=work/'cache/tectonic';cache.mkdir(parents=True);(cache/'fixture-resource').write_bytes(b'resource')
            return subprocess.CompletedProcess(command,0)
        with patch.dict(os.environ,{'RESEARCH_SECRET':'fixture-do-not-pass'}),patch.object(setup.subprocess,'run',side_effect=compile_fixture):
            result=setup._prepare_resources(work)
        self.assertEqual(result['production_render_test'],'NOT_RUN')
        self.assertEqual(render.cache_root(),Path(result['cache']))
        self.assertIn('--only-cached',__import__('inspect').getsource(render.Renderer))

    def test_graphical_selector_cancellation_and_selection_are_explicit(self):
        exe = self.executable('selected compiler')
        with patch.object(setup.shutil, 'which', return_value='/usr/bin/zenity'), patch.object(setup.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','')):
            self.assertTrue(setup.select('tectonic')['cancelled']); self.assertFalse(setup.config_root().exists())
        with patch.object(setup.shutil, 'which', return_value='/usr/bin/zenity'), patch.object(setup.subprocess,'run',return_value=subprocess.CompletedProcess([],0,str(exe)+'\n','')) as run:
            self.assertFalse(setup.select('tectonic')['cancelled']); self.assertIn('--file-selection',run.call_args.args[0])
        self.assertEqual(setup.configured_path('tectonic'),str(exe))

    def test_install_requires_confirmation_uses_pinned_artifacts_and_deduplicates_active_job(self):
        with patch.object(setup, '_install_binary') as action:
            with self.assertRaisesRegex(ValueError,'确认'): setup.start_install('codex')
            action.assert_not_called()
        self.assertTrue(all(row['url'].startswith('https://github.com/') and len(row['sha256']) == 64 and row['bytes'] > 0 for row in setup.ARTIFACTS.values()))
        import threading
        started=threading.Event(); finish=threading.Event()
        def installed(component,work): started.set(); finish.wait(3); return {'fixture':True}
        with patch.object(setup,'_install_binary',side_effect=installed) as action:
            job=setup.start_install('codex',confirmed=True); self.assertTrue(started.wait(2))
            self.assertEqual(setup.start_install('codex',confirmed=True)['job_id'],job['job_id'])
            finish.set()
            for _ in range(100):
                rows=setup.status()['jobs']
                if rows[0]['state']!='RUNNING':break
                time.sleep(.01)
            self.assertEqual(rows[0]['state'],'SUCCEEDED');self.assertEqual(action.call_count,1)

    def test_download_hash_and_archive_shape_fail_closed(self):
        raw=b'official fixture'; artifact={'url':'https://github.com/example/release','bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
        opener=unittest.mock.Mock(); opener.open.return_value=io.BytesIO(raw)
        with patch.object(setup.urllib.request,'build_opener',return_value=opener): setup._download(artifact,self.root/'verified')
        opener.open.return_value=io.BytesIO(raw+b'changed')
        with patch.object(setup.urllib.request,'build_opener',return_value=opener),self.assertRaisesRegex(ValueError,'pinned size'):
            setup._download(artifact,self.root/'bad')
        for is_link in (False,True):
            archive=self.root/('link.tar.gz' if is_link else 'binary.tar.gz')
            with tarfile.open(archive,'w:gz') as tar:
                info=tarfile.TarInfo('tectonic')
                if is_link:info.type=tarfile.SYMTYPE;info.linkname='/bin/sh';tar.addfile(info)
                else:info.size=len(raw);tar.addfile(info,io.BytesIO(raw))
            if is_link:
                with self.assertRaisesRegex(ValueError,'archive layout'):setup._extract_binary(archive,'tectonic',self.root/'link')
            else:
                setup._extract_binary(archive,'tectonic',self.root/'binary');self.assertEqual((self.root/'binary').stat().st_mode&0o777,0o755)

    def test_preserved_modes_and_menu_registration_without_desktop_trust_claim(self):
        builder=script('build-release');installer=script('install-local');archive=self.root/'release.zip'
        builder.write_zip(archive,{'release/'+p:b for p,b in self.release_members().items()})
        release=installer.extract_release(archive,self.root/'extracted')
        self.assertEqual((release/'Install-PMRS.desktop').stat().st_mode&0o777,0o755)
        self.assertEqual((release/'start.sh').stat().st_mode&0o777,0o755)
        self.assertEqual((release/'research_studio/cli.py').stat().st_mode&0o777,0o644)
        entry=installer.register_installer(release,self.root/'applications')
        result=subprocess.run(['desktop-file-validate',str(entry)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn(str(release/'scripts/install-gui.py'),entry.read_text()); self.assertNotIn('sh -c',entry.read_text())
        installed=installer.install(release,self.root/'prefix',self.root/'bin')
        self.assertEqual((Path(installed['installed'])/'start.sh').stat().st_mode&0o777,0o755)

    def test_safe_release_extraction_rejects_links_traversal_and_changed_bytes(self):
        builder=script('build-release');installer=script('install-local')
        for number,rows in enumerate(({'release/../escape':b'x'}, {'release/'+p:(b'changed' if p=='LICENSE' else b) for p,b in self.release_members().items()})):
            archive=self.root/(str(number)+'.zip');builder.write_zip(archive,rows)
            with self.assertRaises(ValueError):installer.extract_release(archive,self.root/('bad'+str(number)))
            self.assertFalse((self.root/('bad'+str(number))).exists())
        archive=self.root/'link.zip'
        with zipfile.ZipFile(archive,'w') as z:
            info=zipfile.ZipInfo('release/link');info.external_attr=0o120777<<16;z.writestr(info,'/tmp/outside')
        with self.assertRaisesRegex(ValueError,'Nonregular'):installer.extract_release(archive,self.root/'link-out')

    def test_reproducible_deb_contains_same_release_and_menu_without_scripts_or_home_path(self):
        builder=script('build-release');members=self.release_members()
        name,raw,audit=builder.debian_installer(members)
        self.assertEqual(raw,builder.debian_installer(members)[1]);self.assertEqual(audit['maintainer_scripts'],[])
        package=self.root/name;package.write_bytes(raw);extracted=self.root/'deb-root'
        result=subprocess.run(['dpkg-deb','--extract',str(package),str(extracted)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        for path,content in members.items():self.assertEqual((extracted/'usr/lib/pmrs-installer'/builder.VERSION/path).read_bytes(),content)
        entry=extracted/('usr/share/applications/pmrs-installer-'+builder.VERSION+'.desktop')
        self.assertNotIn(str(Path.home()),entry.read_text());self.assertIn('/usr/bin/python3 /usr/lib/pmrs-installer/',entry.read_text())
        self.assertEqual(subprocess.run(['desktop-file-validate',str(entry)],capture_output=True).returncode,0)
        self.assertEqual((extracted/'usr/lib/pmrs-installer'/builder.VERSION/'Install-PMRS.desktop').stat().st_mode&0o777,0o755)
        info=subprocess.check_output(['dpkg-deb','--field',str(package),'Depends'],text=True)
        self.assertIn('python3-venv',info);self.assertIn('zenity',info)


if __name__=='__main__':unittest.main()
