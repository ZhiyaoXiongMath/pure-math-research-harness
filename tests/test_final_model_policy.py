"""Web UI supplement: precise workload policy and actual frozen request parameters."""
import json,tempfile,unittest
from copy import deepcopy
from pathlib import Path
from research_studio import model_policy as M,scheduler,execution
from research_studio.workflows.registry import definition
from research_studio.util import PMRSError
from tests import test_final_workflows as WF

CAP={'source':'test-executor-capability','revision':'v1','executor':'codex','models':{
    'gpt-6-astra':{'reasoning_efforts':['high','xhigh','max'],'service_tiers':['default']}}}

class ModelPolicy(unittest.TestCase):
    def test_every_registered_role_in_all_21_stages_is_resolved(self):
        expected={'P1':{'PLAN':'high'},'P2':{'PLAN':'xhigh'},'P3':{'PLAN':'xhigh'},
            'P4':dict.fromkeys(['RESEARCH','FALSIFY','PROOF','COUNTEREXAMPLE'],'max'),
            'P5':{'SYNTHESIS':'xhigh'},'P6':{'PLAN':'max'},
            'P7':{'LEARN':'max','DIRECT':'max','SYNTHESIS':'xhigh','PROOF':'max','COUNTEREXAMPLE':'max'},
            'P8':{'PLAN':'xhigh','RESEARCH':'max','FALSIFY':'max','SYNTHESIS':'xhigh','PROOF':'max','COUNTEREXAMPLE':'max'},
            'P9':{'PROOF':'max','COUNTEREXAMPLE':'max','SPECIALIST':'max','SYNTHESIS':'xhigh'},
            'P10':{'SYNTHESIS':'max'},'P11':{'SYNTHESIS':'xhigh'},'P12':{'INDEPENDENT':'max','SPECIALIST':'max'},
            'D0':{'PLAN':'high'},'D1':{'LEARN':'xhigh','RESEARCH':'xhigh'},'D2':dict.fromkeys(['PLAN','DIRECT','SYNTHESIS'],'max'),
            'D3':{'DIRECT':'max','RESEARCH':'max','FALSIFY':'max','LEARN':'xhigh','PROOF':'max','COUNTEREXAMPLE':'max'},
            'D4':{'FORMULATION_REVIEW':'max','ADVERSARIAL_REVIEW':'max'},'D5':{'SYNTHESIS':'xhigh'}}
        self.assertEqual(len(definition()['stages']),21)
        for sid,row in definition()['stages'].items():
            for rc in row['roles']:
                role=rc['role'];out=M.resolve(row['workflow_kind'],sid,role,capabilities=CAP)
                if role in {'HOST','HUMAN'} or sid in {'P0','P14'}:
                    self.assertFalse(out['call_model']);self.assertIsNone(out['reasoning_effort'])
                else:
                    effort=('high' if role=='REPORT_VISUAL' else 'xhigh') if role.startswith('REPORT_') else expected[sid][role]
                    self.assertEqual(out['reasoning_effort'],effort,(sid,role));self.assertEqual(out['model'],'gpt-6-astra')

    def test_purpose_exceptions_and_specific_synthesis(self):
        for sid,role,purpose,expected in [
            ('P1','PLAN','COMPLEX_DEFINITION_ANALYSIS','xhigh'),('P2','PLAN','PROVE_REDUCTION','max'),
            ('P7','SYNTHESIS','MATHEMATICAL_INTEGRATION','max'),('P8','SYNTHESIS','MATHEMATICAL_INTEGRATION','max'),
            ('D1','LEARN','NEW_CONSTRUCTION','max'),('D1','RESEARCH','PROVE_APPLICABILITY','max'),
            ('D3','LEARN','MATHEMATICAL_DERIVATION','max')]:
            out=M.resolve('TRW' if sid.startswith('P') else 'TFDW',sid,role,purpose,capabilities=CAP)
            self.assertEqual(out['reasoning_effort'],expected)
        self.assertEqual(M.resolve('TRW','P10','SYNTHESIS',capabilities=CAP)['reasoning_effort'],'max')
        self.assertEqual(M.resolve('TFDW','D2','SYNTHESIS',capabilities=CAP)['reasoning_effort'],'max')
        self.assertFalse(M.resolve('TRW','P11','SYNTHESIS','DETERMINISTIC_DIFF',capabilities=CAP)['call_model'])
        self.assertEqual(M.resolve('TRW','P13','REPORT_AUTHOR','LAYOUT_ONLY',capabilities=CAP)['reasoning_effort'],'high')

    def test_unsupported_capability_no_fallback_or_implicit_ultra(self):
        for cap in [None,{**CAP,'models':{'gpt-6-astra':{'reasoning_efforts':['xhigh']}}}]:
            with self.assertRaises(PMRSError):M.resolve('TRW','P10','SYNTHESIS',capabilities=cap)
        override={'explicit':True,'scope':{'workflow_kind':'TRW','stage_id':'P10','role':'SYNTHESIS','purpose':'DEFAULT'},'reasoning_effort':'ultra'}
        cap=deepcopy(CAP);cap['models']['gpt-6-astra']['reasoning_efforts'].append('ultra')
        with self.assertRaises(PMRSError):M.resolve('TRW','P10','SYNTHESIS',override=override,capabilities=cap)
        with self.assertRaises(PMRSError):M.resolve('TRW','P10','SYNTHESIS','UNREGISTERED',capabilities=CAP)
        self.assertFalse(M.resolve('TRW','P14','HUMAN',override=override,capabilities=cap)['call_model'])

    def test_generic_override_cannot_shadow_specific_stage(self):
        with self.assertRaises(PMRSError):M.resolve('TRW','P10','SYNTHESIS',override={'explicit':True,'scope':{'role':'SYNTHESIS'},'reasoning_effort':'xhigh'},capabilities=CAP)

    def test_checked_in_schema_is_single_source_export(self):
        path=Path(__file__).parents[1]/'research_studio/schemas/model-policy.schema.json'
        self.assertEqual(json.loads(path.read_text()),M.schema())

    def test_frozen_task_and_actual_command_use_same_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            store,policy=WF.RuntimeIntegration().make_project(Path(tmp)/'p')
            policy.pop('model_policy');policy['model_capabilities']=CAP
            policy['capacity']['model_id']='gpt-6-astra'
            made=scheduler.commit_dispatch(store,scheduler.plan(store.read_snapshot(),['I']),policy=policy)
            t=store.read_snapshot()['tasks'][made['prepared'][0]['task_id']]
            self.assertEqual(t['model_policy']['reasoning_effort'],'max')
            self.assertEqual(t['model_policy_resolution']['rule_id'],'TRW:P4:RESEARCH:DEFAULT')
            args=M.codex_arguments(t['model_policy_resolution'])
            self.assertEqual(args,['--model','gpt-6-astra','-c','model_reasoning_effort="max"','-c','service_tier="default"'])
            changed=deepcopy(policy);changed['model_override']={'explicit':True,'scope':{'workflow_kind':'TRW','stage_id':'P4','role':'RESEARCH','purpose':'DEFAULT'},'reasoning_effort':'xhigh'}
            plan=scheduler.plan(store.read_snapshot(),['I'])
            self.assertFalse(plan['selected']);self.assertEqual(plan['actions'][0]['action'],'REUSE')
            self.assertEqual(store.read_snapshot()['tasks'][t['task_id']]['model_policy'],t['model_policy'])

    def test_model_change_uses_next_existing_slot_without_new_budget(self):
        from research_studio.runner import FakeExecutor
        with tempfile.TemporaryDirectory() as tmp:
            store,policy=WF.RuntimeIntegration().make_project(Path(tmp)/'p')
            first=scheduler.commit_dispatch(store,scheduler.plan(store.read_snapshot(),['I']),policy=policy)['prepared'][0]
            FakeExecutor(WF.RuntimeIntegration.no_result).execute(store,first['task_id'])
            old=store.read_snapshot();policy['model_policy']['reasoning_effort']='high'
            second=scheduler.commit_dispatch(store,scheduler.plan(store.read_snapshot(),['I']),policy=policy)['prepared'][0]
            new=store.read_snapshot();t1=old['tasks'][first['task_id']];t2=new['tasks'][second['task_id']]
            self.assertEqual(t1['attempt_group_key'],t2['attempt_group_key']);self.assertEqual(t2['sample_slot'],2)
            self.assertEqual(new['project_budget'],old['project_budget']);self.assertEqual(t1['model_policy']['reasoning_effort'],'none')
            self.assertFalse(scheduler.plan(new,['I'])['selected'])

if __name__=='__main__':unittest.main()
