"""Pause stops new sends; original in-flight/captured work is preserved."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import os,time,unittest
from research_studio import changes,demo,execution,host_pool,resources,runner,tasks
from research_studio.engine import Engine
from research_studio.store import Store
from tests.test_model_pool import fixture,prepare,transport_root,events
from tests.test_research_plans import no_result
from research_studio.util import canonical,PMRSError


class RunnerPauseTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        env=patch.dict(os.environ,{'PMRS_HOST_POOL_ROOT':str(self.root/'host'),'PMRS_CONTROLLED_TRANSPORT':str(self.root/'transport')})
        env.start();self.addCleanup(env.stop)

    def test_explicit_empty_selection_does_not_fall_back_to_instance(self):
        store,iid,policy=fixture(self.root/'project',1,1);made=prepare(store,iid,policy)[0]
        result=runner.run(store,instance_ids=[],instance_id=iid,policy=policy,max_tasks=1)
        self.assertEqual(result['state'],'PAUSED');self.assertEqual(result['model_calls'],0)
        self.assertEqual(store.read_snapshot()['requests'][made['request_id']]['execution_state'],'PREPARED')

    def test_pause_during_resource_queue_does_not_restart_or_spin(self):
        store,iid,policy=fixture(self.root/'project',1,1);made=prepare(store,iid,policy)[0]
        selected=[iid];ticks=[]
        def tick(current):
            ticks.append(time.monotonic())
            if len(ticks)==2:Engine().pause(current,iid,'Pause new dispatch while preserving this request.');selected.clear()
        with resources.reserve(store.root,owner='existing-preparation',temporary_bytes=0,memory_bytes=1,max_preparations=1), \
             patch('research_studio.runner.subprocess.Popen',side_effect=AssertionError('Paused queue cannot send')):
            started=time.monotonic();result=runner.run(store,instance_ids=selected,policy=policy,max_tasks=1,on_tick=tick)
        self.assertLess(time.monotonic()-started,3);self.assertEqual(result['state'],'PAUSED')
        self.assertEqual(store.read_snapshot()['requests'][made['request_id']]['execution_state'],'PREPARED')
        self.assertEqual(host_pool.status()['active'],0)

    def test_pause_racing_admission_preserves_capture_then_resumes_without_send(self):
        store,iid,policy=fixture(self.root/'project',1,1);made=prepare(store,iid,policy)[0]
        binary=transport_root(self.root/'transport',[store],delay=.01);executor=runner.CodexExecutor(str(binary),timeout=5)
        validate=changes.validate_response
        def pause_before_validation(*args,**kwargs):
            Engine().pause(store,iid,'Preserve the original completed request for correction.');return validate(*args,**kwargs)
        with patch('research_studio.runner.doctor',return_value={'ready':True,'binary':str(binary)}), \
             patch('research_studio.changes.validate_response',side_effect=pause_before_validation):
            result=executor.execute(store,made['task_id'])
        self.assertEqual(result['state'],'PAUSED');self.assertEqual(result['model_calls'],1)
        request=store.read_snapshot()['requests'][made['request_id']]
        self.assertEqual(request['execution_state'],'CAPTURED');self.assertEqual(request['acceptance_state'],'PENDING')
        self.assertEqual(host_pool.status()['active'],0)
        snapshot=store.read_snapshot();engine=Engine()
        decision=engine.decide(store,iid,'CONTINUE','Continue the same original capture.',snapshot_commit=snapshot['knowledge_commit'])
        engine.resume(store,iid,decision)
        with patch('research_studio.runner.subprocess.Popen',side_effect=AssertionError('Resume cannot repeat a captured request')):
            self.assertEqual(executor.execute(Store(store.root),made['task_id'])['state'],'ACCEPTED')
        self.assertEqual(len([r for r in events(self.root/'transport/events.jsonl') if r['phase']=='start']),1)
        self.assertEqual(len(store.read_snapshot()['requests']),1)

    def test_new_mission_fences_old_unsent_but_retains_original_capture(self):
        for state in ('PREPARED','CAPTURED'):
            with self.subTest(state=state):
                store,iid,policy=fixture(self.root/state,1,1);made=prepare(store,iid,policy)[0]
                task=tasks.load(store,made['task_id']);rid=task['request_id']
                if state=='CAPTURED':
                    reserved=execution.reserve(store,rid,execution_kind='SYNTHETIC_TEST_ONLY')
                    execution.capture(store,rid,no_result(task,store.read_snapshot()),execution_id=reserved['execution_id'])
                frozen=canonical(task);request=store.read_snapshot()['requests'][rid].copy()
                Engine().plan_work(store,iid,'A distinct later finite mission.',[
                    {'key':'later','stage':'P4','role':'RESEARCH','intent':'Investigate a distinct later responsibility.'}],
                    max_calls=1,max_workers=1,policy=demo.policy())
                self.assertNotEqual(store.read_snapshot()['instances'][iid]['current_mission_id'],task['mission_id'])
                executor=runner.CodexExecutor('controlled-unused',timeout=5)
                with patch('research_studio.runner.doctor',return_value={'ready':True,'binary':'controlled-unused'}), \
                     patch('research_studio.runner.subprocess.Popen',side_effect=AssertionError('The original request cannot be sent again')):
                    if state=='PREPARED':
                        with self.assertRaisesRegex(PMRSError,'TASK_FENCED'):executor.execute(store,task['task_id'])
                        self.assertEqual(store.read_snapshot()['requests'][rid],request)
                    else:
                        self.assertEqual(executor.execute(store,task['task_id'])['state'],'ACCEPTED')
                        self.assertEqual(store.read_snapshot()['requests'][rid]['capture_ref'],request['capture_ref'])
                self.assertEqual(canonical(store.read_snapshot()['tasks'][task['task_id']]),frozen)
                self.assertEqual(len(store.read_snapshot()['requests']),1)


if __name__=='__main__':unittest.main()
