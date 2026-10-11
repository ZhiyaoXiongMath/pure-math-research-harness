"""Native main control tests; no external model or mathematical certification."""
from copy import deepcopy
from tempfile import TemporaryDirectory
import unittest

from research_studio import demo, strategy, main_session, scheduler, execution, model_policy, rounds
from research_studio.engine import Engine
from research_studio.runner import FakeExecutor
from research_studio.util import canonical, loads, PMRSError
from tests.test_autoflow import response


class NativeMain(unittest.TestCase):
    def setup_round(self,path,calls=12,workers=1):
        e=Engine();s=e.create(path,demo.ARITHMETIC,synthetic=True)
        i=e.new_workflow(s,'TRH',target_ref=next(iter(s.read_snapshot()['records'])))['instance_id']
        e.start_round(s,i,'Inspect the exact fixed target with bounded native main work.',max_calls=calls,max_workers=workers,policy=demo.policy())
        return e,s,i

    def test_direction_native_plan_read_only_views_and_repeat_driver(self):
        with TemporaryDirectory() as d:
            e,s,i=self.setup_round(d+'/p')
            direction=main_session.submit_direction(s,i,'Compare the arbitrary integer proof with finite examples.',client_action_id='direction-one')
            fake=FakeExecutor(response);result=e.run_round(s,i,executor=fake)
            state=s.read_snapshot();main=[t for t in state['tasks'].values() if t.get('actor_kind')=='MAIN']
            self.assertCountEqual([t['stage_id'] for t in main],['P3','P5','P11'])
            self.assertTrue(all(t['model_policy']['reasoning_effort']=='ultra' for t in main))
            self.assertEqual(state['human_directions'][direction['direction_id']]['status'],'APPLIED')
            self.assertTrue(strategy.completed_global(state,i));self.assertEqual(result['round_result']['state'],'READY_FOR_DECISION')
            self.assertFalse(result['round_result']['scientific_completion'])
            self.assertFalse(state['human_decisions']);self.assertFalse(state['reports'])
            before=state['knowledge_commit'];calls=fake.calls
            for _ in range(3):
                self.assertTrue(main_session.view(s,i)['read_only']);scheduler.plan(s.read_snapshot(),[i])
            self.assertEqual(s.read_snapshot()['knowledge_commit'],before)
            e.run_round(s,i,executor=fake);self.assertEqual(fake.calls,calls)
            main_session.submit_direction(s,i,'Compare the arbitrary integer proof with finite examples.',client_action_id='direction-one')
            self.assertEqual(len(s.read_snapshot()['human_directions']),1);s.audit()
            from pathlib import Path
            from research_studio.store import Store
            from research_studio.portability import export_project,restore
            saved=s.read_snapshot();archive=Path(d)/'native.zip'
            export_project(s,archive);restore(archive,Path(d)/'restored')
            restored=Store(Path(d)/'restored');restored.audit();after=restored.read_snapshot()
            for field in ('records','requests','strategy_proposals','research_routes','human_directions','budget_grants'):
                self.assertEqual(saved[field],after[field])
            for checkpoint in (restored.root/'checkpoints').glob('*.json'):checkpoint.unlink()
            self.assertEqual(after,restored.read_snapshot());restored.audit()

    def test_rejected_main_plan_does_not_publish_science_or_assignments(self):
        with TemporaryDirectory() as d:
            e,s,i=self.setup_round(d+'/p');seen=[]
            def invalid(task,snapshot):
                raw=loads(response(task,snapshot))
                if task.get('actor_kind')=='MAIN':
                    seen.append(task);raw['payload']['strategy_proposal']['work_items'][0]['source_refs']=['SO-not-authorized']
                return canonical(raw)
            fake=FakeExecutor(invalid);e.run_round(s,i,executor=fake);state=s.read_snapshot()
            self.assertEqual(len(seen),1);self.assertFalse(state.get('strategy_proposals'))
            self.assertEqual(state['requests'][seen[0]['request_id']]['acceptance_state'],'REJECTED_CONTRACT')
            self.assertFalse(any(c['stage_id']=='P4' for o in state['obligations'].values() for c in o['definition']['consumer_bindings']))
            self.assertFalse(any(p.get('task_id')==seen[0]['task_id'] for p in state['production_events'].values()))
            self.assertEqual(fake.calls,3);e.run_round(s,i,executor=fake);self.assertEqual(fake.calls,3);s.audit()

    def test_main_policy_cannot_downgrade_or_be_claimed_by_worker(self):
        capabilities=demo.policy()['model_capabilities']
        self.assertEqual(model_policy.resolve('TRH','P3','PLAN','MAIN_STRATEGY',actor_kind='MAIN',capabilities=capabilities)['reasoning_effort'],'ultra')
        for kwargs in ({'actor_kind':'MAIN','override':{'reasoning_effort':'max'}},{'actor_kind':None}):
            with self.assertRaises(PMRSError):model_policy.resolve('TRH','P3','PLAN','MAIN_STRATEGY',capabilities=capabilities,**kwargs)
        capabilities=deepcopy(capabilities);capabilities['isolated_ultra_verified']=False
        with self.assertRaises(PMRSError):model_policy.resolve('TRH','P3','PLAN','MAIN_STRATEGY',actor_kind='MAIN',capabilities=capabilities)

    def test_zero_budget_and_pause_preserve_queued_direction(self):
        with TemporaryDirectory() as d:
            e,s,i=self.setup_round(d+'/p',calls=1);fake=FakeExecutor(response)
            e.run_round(s,i,executor=fake);mid=s.read_snapshot()['instances'][i]['current_mission_id']
            main_session.submit_direction(s,i,'Explain the remaining exact implication.',client_action_id='after-budget')
            e.run_round(s,i,executor=fake);self.assertEqual(fake.calls,1)
            self.assertEqual(main_session.view(s,i)['waiting_reason'],'BUDGET_EXHAUSTED')
            e.pause(s,i,'Synthetic pause');main_session.submit_direction(s,i,'Retain this direction during pause.',client_action_id='paused')
            self.assertEqual(e.run_round(s,i,executor=fake)['state'],'PAUSED')
            self.assertEqual({x['status'] for x in main_session.view(s,i)['directions']},{'QUEUED'})
            self.assertEqual(s.read_snapshot()['instances'][i]['current_mission_id'],mid)

    def test_preflight_failure_has_native_incident_and_no_false_delivery(self):
        from unittest.mock import patch
        from research_studio import incidents
        with TemporaryDirectory() as d:
            e,s,i=self.setup_round(d+'/p')
            with patch('research_studio.engine.derive_followups',side_effect=PMRSError('CONTEXT_LIMIT','Synthetic exact freeze capacity failure.')):
                with self.assertRaises(PMRSError):e.run_round(s,i,executor=FakeExecutor(response))
            state=s.read_snapshot();self.assertEqual(len(state['incidents']),1)
            self.assertEqual(rounds.describe(state,i)['state'],'FAULT');self.assertFalse(state['tasks'])
            incident=next(iter(state['incidents'].values()))
            self.assertFalse(incident['maintenance_executor_available']);self.assertTrue(incident['handoff']['preserve'])
            self.assertIn('REPLAN_MATERIALS',incidents.list_recovery_options(s,incident['incident_id'])['options'])
            with self.assertRaises(PMRSError):incidents.propose_recovery(s,'unbound',incident['incident_id'],'REFRESH_PROJECTION',arguments={},expected_revision=1,idempotency_key='bad')
            s.audit()

    def test_unsent_material_replan_is_native_and_cannot_change_frozen_duty(self):
        from research_studio import changes,knowledge
        with TemporaryDirectory() as d:
            e=Engine();s=e.create(d+'/p',demo.ARITHMETIC,synthetic=True)
            i=e.new_workflow(s,'TRH',target_ref=next(iter(s.read_snapshot()['records'])))['instance_id']
            body=b'Exact selected passage. Separate unprovided appendix.'
            source=s.commit(changes.prepare_material_input(s.read_snapshot(),body,'Generated material','text/plain',blob_get=s.read_blob))['source_ref']
            e.start_round(s,i,'Read the declared passage for this generated fixture.',source_refs=[source],max_calls=1,policy=demo.policy())
            before=s.read_snapshot();obligation=next(iter(before['obligations'].values()));definition=obligation['definition']
            bid=definition['consumer_bindings'][0]['binding_id']
            selections={source:{'coverage':'DECLARED_RANGE','locators':[knowledge.locator(body,0,23)],'reason':'This exact fixture only asks about the selected passage.'}}
            execution.replan_unsent_materials(s,i,bid,selections,'Make the exact frozen coverage explicit without changing the scientific duty.')
            after=s.read_snapshot();updated=after['obligations'][definition['obligation_id']]['definition']
            self.assertEqual(updated['criterion_body_ref'],definition['criterion_body_ref'])
            self.assertEqual(updated['definition_revision'],definition['definition_revision'])
            self.assertEqual(after['budget_grants'],before['budget_grants']);self.assertFalse(after['requests'])
            self.assertEqual(updated['consumer_bindings'][0]['input_plan']['source_selections'][source],selections[source])
            plan=scheduler.plan(after,[i],demo.policy());scheduler.commit_dispatch(s,plan,policy=demo.policy())
            with self.assertRaisesRegex(PMRSError,'EXISTING_REQUEST'):
                execution.replan_unsent_materials(s,i,bid,{},'This must not rewrite a frozen request.')
            s.audit()


if __name__=='__main__':unittest.main()
