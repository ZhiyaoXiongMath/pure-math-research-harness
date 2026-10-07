"""Evidence-parser unit fixtures only: these tests do not execute a browser."""
from pathlib import Path
from unittest.mock import patch
import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class BrowserEvidenceValidation(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.root=self.base/'source';self.evidence=self.base/'private';self.evidence.mkdir()
        (self.root/'tests/coverage').mkdir(parents=True);(self.root/'research_studio').mkdir()
        (self.root/'pyproject.toml').write_text('');(self.root/'research_studio/asset.json').write_text('{"synthetic_fixture":true}')
        inventory={'schema':'pmrs.required-test-inventory/1','cases':[{'case_id':'WEB01','required':True,'assertion_ids':['WEB01.a1'],
            'browser_test_id':'tests.browser.WEB01','required_browser_paths':['install','open']}],'baseline':[]}
        (self.root/'tests/coverage/required.json').write_text(json.dumps(inventory))
        mapping={'schema':'pmrs.test-coverage/1','acceptance':[{'case_id':'WEB01','assertions':[{'assertion_id':'WEB01.a1','test_ids':['tests.browser.WEB01']}]}]}
        (self.root/'tests/coverage/browser.json').write_text(json.dumps(mapping))
        with patch.object(sys,'path',[str(ROOT/'scripts'),*sys.path]):
            spec=importlib.util.spec_from_file_location('browser_evidence_fixture',ROOT/'scripts/browser_evidence.py')
            self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
        self.source_hash=hashlib.sha256(self.module.encoded(self.module.source_manifest(self.root))).hexdigest()
        installed=self.evidence/'installed/research_studio/asset.json';installed.parent.mkdir(parents=True)
        installed.write_bytes((self.root/'research_studio/asset.json').read_bytes())
        observed=self.evidence/'observation.txt';observed.write_text('Synthetic parser fixture, not a real browser observation.')
        def entry(p):return {'path':p.relative_to(self.evidence).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
        self.record={'schema':'pmrs.browser-evidence/1','mode':'CUA_INSTALLED_BROWSER','source_sha256':self.source_hash,
            'environment':{'os':'parser-fixture','python':'parser-fixture','browser':'parser-fixture','installed_runtime':'installed'},
            'installed_assets':{'research_studio/asset.json':entry(installed)},
            'actual_test_results':{'tests.browser.WEB01':{'outcome':'PASS','executed_paths':['install','open'],
                'steps':[{'path':p,'action':'Synthetic parser fixture action','observed':'Synthetic parser fixture observation','artifact_refs':['fixture']} for p in ['install','open']],
                'artifacts':{'fixture':entry(observed)}}}}
        self.path=self.evidence/'browser.json'

    def load(self,record=None):
        self.path.write_text(json.dumps(record or self.record))
        return self.module.load_browser_evidence(self.root,self.path,self.source_hash)


    def test_validated_records_keep_external_provenance_separate(self):
        rows,meta=self.load();self.assertEqual(meta['actual_tests'],['tests.browser.WEB01'])
        self.assertEqual(rows['tests.browser.WEB01']['provenance']['mode'],'CUA_INSTALLED_BROWSER')
        self.assertEqual(meta['installed_asset_count'],1)

    def test_stale_source_nonbrowser_mode_missing_path_and_hash_rejected(self):
        bad=copy.deepcopy(self.record);bad['source_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'different source'):self.load(bad)
        bad=copy.deepcopy(self.record);bad['mode']='API_UNIT_TEST'
        with self.assertRaisesRegex(ValueError,'Actual CUA'):self.load(bad)
        bad=copy.deepcopy(self.record);row=bad['actual_test_results']['tests.browser.WEB01'];row['steps'].pop();row['executed_paths'].pop()
        with self.assertRaisesRegex(ValueError,'not all observed'):self.load(bad)
        (self.evidence/'observation.txt').write_text('changed')
        with self.assertRaisesRegex(ValueError,'artifact hash differs'):self.load()

    def test_path_escape_symlink_missing_installed_asset_and_unknown_id_rejected(self):
        bad=copy.deepcopy(self.record);bad['installed_assets']={}
        with self.assertRaisesRegex(ValueError,'member set differs'):self.load(bad)
        bad=copy.deepcopy(self.record);bad['actual_test_results']['tests.browser.WEB01']['artifacts']['fixture']['path']='../source/pyproject.toml'
        with self.assertRaisesRegex(ValueError,'without escapes'):self.load(bad)
        bad=copy.deepcopy(self.record);bad['actual_test_results']['tests.browser.UNKNOWN']=bad['actual_test_results'].pop('tests.browser.WEB01')
        with self.assertRaisesRegex(ValueError,'Unknown external'):self.load(bad)
        p=self.evidence/'observation.txt';p.unlink();p.symlink_to(self.root/'pyproject.toml')
        with self.assertRaisesRegex(ValueError,'symlink'):self.load()

    def test_external_only_runner_absence_fails_and_fixture_record_merges_explicitly(self):
        out=self.evidence/'suite.json'
        command=[sys.executable,'-B',str(ROOT/'scripts/test-runner.py'),'--root',str(self.root),'--out',str(out),'--required','tests.browser.WEB01']
        run=subprocess.run(command,capture_output=True,text=True)
        self.assertNotEqual(run.returncode,0,run.stdout)
        result=json.loads(out.read_text());self.assertEqual(result['coverage']['assertions']['WEB01.a1']['status'],'NOT_RUN')
        self.load();run=subprocess.run(command[:2]+command[2:]+['--browser-evidence',str(self.path)],capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        result=json.loads(out.read_text());self.assertEqual(result['result']['tests'],0);self.assertEqual(result['result']['browser_observations'],1)
        self.assertEqual(result['browser_evidence']['mode'],'CUA_INSTALLED_BROWSER')











    def test_unexecuted_native_paths_remain_skip_without_erasing_automated_evidence(self):
        inventory=json.loads((self.root/'tests/coverage/required.json').read_text())
        inventory['cases'][0]['required_browser_paths'].append('path-picker')
        inventory['cases'][0]['native_manual_paths']=['path-picker']
        (self.root/'tests/coverage/required.json').write_text(json.dumps(inventory))
        self.source_hash=hashlib.sha256(self.module.encoded(self.module.source_manifest(self.root))).hexdigest()
        self.record['source_sha256']=self.source_hash
        self.record['actual_test_results']['tests.browser.WEB01']['outcome']='SKIP'
        rows,_=self.load();row=rows['tests.browser.WEB01']
        self.assertEqual(row['outcome'],'SKIP');self.assertTrue(row['automated_installed_complete'])
        self.assertEqual(row['native_click_unverified'],['path-picker'])
        row=self.record['actual_test_results']['tests.browser.WEB01'];row['outcome']='PASS'
        with self.assertRaisesRegex(ValueError,'not all observed'):self.load()

    def test_prior_candidate_human_component_protocol_is_not_current_acceptance(self):
        bad=copy.deepcopy(self.record);bad['mode']='MIXED_INSTALLED_ACCEPTANCE'
        with self.assertRaisesRegex(ValueError,'Actual CUA'):self.load(bad)
        bad=copy.deepcopy(self.record);bad['actual_test_results']['tests.browser.WEB01']['steps'][0]['provenance']={'mode':'HUMAN_REPORTED_COMPONENT_REUSE'}
        with self.assertRaisesRegex(ValueError,'cannot relabel'):self.load(bad)


if __name__=='__main__':unittest.main()
