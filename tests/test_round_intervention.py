"""Native correction/accounting fixtures; not automatic vertical-chain evidence."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import os,unittest
from research_studio import corrections,demo,execution,rounds,scheduler,tasks,workflow_instances as W
from research_studio.engine import Engine
from research_studio.runner import FakeExecutor
from research_studio.store import Store
from research_studio.util import canonical,PMRSError,sha
from tests.test_research_plans import no_result


class RoundInterventionTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        env=patch.dict(os.environ,{'PMRS_HOST_POOL_ROOT':str(self.root/'host')});env.start();self.addCleanup(env.stop)

    def project(self,name='project',*,calls=3,dependency=False):
        engine=Engine();store=Store.create(self.root/name,'Explicit correction fixture only',synthetic=True)
        iid=engine.new_workflow(store,'TRH',target=b'A synthetic exact target used only for native intervention tests.')['instance_id']
        items=[{'key':'parent','stage':'P4','role':'RESEARCH','intent':'Inspect the exact first scoped mathematical interface.'}]
        if dependency:items.append({'key':'child','stage':'P4','role':'RESEARCH','intent':'Inspect the dependent second interface after the first disposition.','depends_on':['parent']})
        engine.plan_work(store,iid,'Explicit advanced correction test plan; not an automatic workflow claim.',items,
                         max_calls=calls,max_workers=1,policy=demo.policy(),allow_reports=False)
        policy={'max_workers':1,'mission_policies':True}
        return engine,store,iid,policy

    def binding(self,store,key='parent'):
        return next(c['binding_id'] for o in store.read_snapshot()['obligations'].values() for c in o['definition']['consumer_bindings']
                    if c.get('entry_basis',{}).get('research_plan',{}).get('branch_key')==key)

    def prepare(self,store,iid,policy):
        plan=scheduler.plan(store.read_snapshot(),[iid],policy)
        self.assertTrue(plan['selected'],plan['waits']);plan['selected']=plan['selected'][:1]
        made=scheduler.commit_dispatch(store,plan,policy=policy)['prepared'][0]
        return tasks.load(store,made['task_id'])

    def resume(self,engine,store,iid):
        snapshot=store.read_snapshot()
        decision=engine.decide(store,iid,'CONTINUE','Resume the exact corrected responsibilities without increasing the budget.',snapshot_commit=snapshot['knowledge_commit'])
        engine.resume(store,iid,decision)

    def correction(self,store,iid,bid):
        return corrections.request(store,iid,bid,'Inspect the missing endpoint assumption in the selected responsibility.',
                                   'Give an exact endpoint argument or record the concrete unresolved boundary.')

    def test_correction_atomically_pauses_preserves_sent_and_capture_and_cancels_only_unsent(self):
        for desired in ('PREPARED','SENT','CAPTURED','UNKNOWN'):
            with self.subTest(state=desired):
                engine,store,iid,policy=self.project(desired);task=self.prepare(store,iid,policy);rid=task['request_id']
                if desired!='PREPARED':
                    reserved=execution.reserve(store,rid,execution_kind='SYNTHETIC_TEST_ONLY')
                    store.commit_execution(execution.event('SENT',{'request_id':rid,'execution_id':reserved['execution_id']}))
                    if desired=='CAPTURED':execution.capture(store,rid,no_result(task,store.read_snapshot()),execution_id=reserved['execution_id'])
                    elif desired=='UNKNOWN':store.commit_execution(execution.event('UNKNOWN',{'request_id':rid,'execution_id':reserved['execution_id'],'reason':'Controlled uncertain transport.'}))
                before=store.read_snapshot();frozen=canonical(task);bid=task['obligation_bindings'][0]['binding_id']
                result=self.correction(store,iid,bid);after=store.read_snapshot();request=after['requests'][rid]
                self.assertEqual(after['_snapshot_sequence'],before['_snapshot_sequence']+1)
                self.assertEqual(after['instances'][iid]['status'],'PAUSED');self.assertIn(bid,after['retired_consumers'])
                self.assertEqual(after['budget_grants'],before['budget_grants']);self.assertEqual(after['project_budget'],before['project_budget'])
                self.assertEqual(canonical(after['tasks'][task['task_id']]),frozen)
                self.assertEqual(request['execution_state'],'CANCELLED_BEFORE_SEND' if desired=='PREPARED' else desired)
                self.assertEqual(request['capture_ref'],before['requests'][rid]['capture_ref'])
                self.assertEqual(request['fenced'],desired=='PREPARED')
                sequence=after['_snapshot_sequence'];paths=len(list(store.root.rglob('*')))
                self.assertEqual(self.correction(store,iid,bid)['correction_id'],result['correction_id'])
                self.assertEqual(store.read_snapshot()['_snapshot_sequence'],sequence);self.assertEqual(len(list(store.root.rglob('*'))),paths)
                if desired=='UNKNOWN':
                    self.resume(engine,store,iid);self.assertEqual(corrections.advance(store,iid),[])
                    actions=scheduler.plan(store.read_snapshot(),[iid],policy)['actions']
                    self.assertFalse(any(a.get('request_id')==rid and a['action']=='REUSE' for a in actions))
                    executor=FakeExecutor(no_result)
                    with self.assertRaisesRegex(PMRSError,'EXISTING_REQUEST'):executor.execute(store,task['task_id'])
                    self.assertEqual(executor.calls,0);self.assertEqual(len(store.read_snapshot()['requests']),1)

    def test_continue_freezes_and_executes_concrete_correction_in_original_budget(self):
        engine,store,iid,policy=self.project();old=self.prepare(store,iid,policy);before=store.read_snapshot()
        result=self.correction(store,iid,old['obligation_bindings'][0]['binding_id']);self.resume(engine,store,iid)
        self.assertEqual(len(corrections.advance(store,iid)),1)
        corrected=self.prepare(store,iid,policy);state=store.read_snapshot()
        self.assertNotEqual(corrected['task_id'],old['task_id']);self.assertEqual(corrected['mission_id'],old['mission_id'])
        self.assertEqual(state['requests'][corrected['request_id']]['budget_grant_id'],before['requests'][old['request_id']]['budget_grant_id'])
        obligation=state['obligations'][corrected['obligation_bindings'][0]['obligation_id']]
        criterion=store.read_blob(obligation['definition']['criterion_body_ref']).decode();prompt=store.read_blob(corrected['prompt_ref']).decode()
        self.assertIn('missing endpoint assumption',criterion);self.assertIn('exact endpoint argument',criterion)
        self.assertIn(criterion,prompt);self.assertEqual(corrected['target_refs'],old['target_refs'])
        self.assertEqual(state['project_budget'],before['project_budget']);self.assertEqual(state['budget_grants'],before['budget_grants'])
        executor=FakeExecutor(no_result);self.assertEqual(executor.execute(store,corrected['task_id'])['state'],'ACCEPTED')
        self.assertEqual(executor.calls,1);self.assertEqual(scheduler.project_remaining(store.read_snapshot()),2)
        self.assertTrue(next(r for r in corrections.pending(store.read_snapshot(),iid) if r['correction_id']==result['correction_id'])['complete'])
        self.assertEqual(store.read_snapshot()['requests'][old['request_id']]['execution_state'],'CANCELLED_BEFORE_SEND')

    def test_original_inflight_capture_settles_before_new_corrected_request(self):
        engine,store,iid,policy=self.project();old=self.prepare(store,iid,policy)
        reserved=execution.reserve(store,old['request_id'],execution_kind='SYNTHETIC_TEST_ONLY')
        store.commit_execution(execution.event('SENT',{'request_id':old['request_id'],'execution_id':reserved['execution_id']}))
        self.correction(store,iid,old['obligation_bindings'][0]['binding_id'])
        raw=no_result(old,store.read_snapshot());execution.capture(store,old['request_id'],raw,execution_id=reserved['execution_id'])
        self.assertEqual(corrections.advance(store,iid),[]);self.resume(engine,store,iid)
        self.assertEqual(corrections.advance(store,iid),[])
        self.assertEqual(execution.recover(store,old['request_id'])['state'],'ACCEPTED')
        self.assertEqual(len(corrections.advance(store,iid)),1)
        corrected=self.prepare(store,iid,policy);FakeExecutor(no_result).execute(store,corrected['task_id'])
        state=store.read_snapshot();self.assertEqual(state['requests'][old['request_id']]['capture_ref'],sha(raw))
        self.assertEqual(len(state['requests']),2);self.assertEqual(scheduler.project_remaining(state),1)

    def test_correction_cannot_bypass_original_unsatisfied_dependencies(self):
        engine,store,iid,policy=self.project(dependency=True)
        child=self.binding(store,'child');original=next(o for o in store.read_snapshot()['obligations'].values() if any(c['binding_id']==child for c in o['definition']['consumer_bindings']))
        result=self.correction(store,iid,child);self.resume(engine,store,iid);corrections.advance(store,iid)
        state=store.read_snapshot();corrected=next(o for o in state['obligations'].values() if any(c['binding_id']==result['binding_id'] for c in o['definition']['consumer_bindings']))
        self.assertEqual(corrected['definition']['dependency_bindings'],original['definition']['dependency_bindings'])
        plan=scheduler.plan(state,[iid],policy);self.assertFalse(any(row['consumer']['binding_id']==result['binding_id'] for row in plan['selected']))
        parent=self.prepare(store,iid,policy);FakeExecutor(no_result).execute(store,parent['task_id'])
        plan=scheduler.plan(store.read_snapshot(),[iid],policy)
        self.assertTrue(any(row['consumer']['binding_id']==result['binding_id'] for row in plan['selected']))

    def test_round_account_distinguishes_dependency_budget_fault_resource_and_deliverable(self):
        engine,store,iid,policy=self.project('dependency',dependency=True)
        parent=self.binding(store);snapshot=store.read_snapshot()
        store.commit_control(W.event(snapshot,'RETIRE_CONSUMER',{'binding_id':parent,'reason':'Explicitly defer this prerequisite without claiming it was performed.'},instance_id=iid,mission_id=snapshot['instances'][iid]['current_mission_id']))
        dependency=rounds.describe(store.read_snapshot(),iid)
        self.assertEqual(dependency['state'],'WAITING_DEPENDENCY');self.assertEqual(len(dependency['unperformed_bindings']),2)
        self.assertFalse(dependency['actual_requests']);self.assertFalse(dependency['scientific_completion'])
        delivered=rounds.record(store,iid);self.assertEqual(delivered['state'],'WAITING_DEPENDENCY')
        self.assertIn(delivered['delivery_id'],store.read_snapshot()['round_deliveries'])
        _,budget,bid,_=self.project('budget',calls=0)
        exhausted=rounds.describe(budget.read_snapshot(),bid)
        self.assertEqual(exhausted['state'],'BUDGET_EXHAUSTED');self.assertEqual(len(exhausted['unperformed_bindings']),1)
        _,fault,fid,fp=self.project('fault');bad=self.prepare(fault,fid,fp)
        with self.assertRaises(PMRSError):FakeExecutor(lambda *_:b'{"bad":true}').execute(fault,bad['task_id'])
        failure=rounds.describe(fault.read_snapshot(),fid)
        self.assertEqual(failure['state'],'FAULT');self.assertEqual(len(failure['failures']),1)
        _,waiting,wid,wp=self.project('resource');prepared=self.prepare(waiting,wid,wp);before=waiting.read_snapshot()['_snapshot_sequence']
        resources={'state':'RESOURCE_WAIT','waiting_requests':[{'request_id':prepared['request_id'],'code':'RESOURCE_WAIT'}]}
        pending=rounds.record(waiting,wid,resources)
        self.assertEqual(pending['state'],'WAITING_RESOURCE');self.assertEqual(pending['resource_waits'],resources['waiting_requests'])
        self.assertEqual(waiting.read_snapshot()['_snapshot_sequence'],before)
        _,done,did,dp=self.project('done');task=self.prepare(done,did,dp);FakeExecutor(no_result).execute(done,task['task_id'])
        decision=rounds.describe(done.read_snapshot(),did)
        self.assertEqual(decision['state'],'READY_FOR_DECISION');self.assertEqual(decision['next_decision'],'HUMAN_ONLY')
        self.assertFalse(decision['scientific_completion']);self.assertEqual(len(decision['actual_requests']),1)

    def test_repeated_native_round_record_is_read_only_after_first_exact_delivery(self):
        _,store,iid,policy=self.project();task=self.prepare(store,iid,policy);FakeExecutor(no_result).execute(store,task['task_id'])
        before=store.read_snapshot();first=rounds.record(store,iid);after=store.read_snapshot();files=len(list(store.root.rglob('*')))
        self.assertEqual(after['_snapshot_sequence'],before['_snapshot_sequence']+1)
        self.assertEqual(after['control_events'],before['control_events']);self.assertEqual(after['project_budget'],before['project_budget'])
        second=rounds.record(store,iid);self.assertEqual(second,first)
        self.assertEqual(store.read_snapshot()['_snapshot_sequence'],after['_snapshot_sequence']);self.assertEqual(len(list(store.root.rglob('*'))),files)
        self.assertEqual(first['stage_id'],'P13');self.assertFalse(first['scientific_completion'])
        self.assertEqual(first['model_calls'],0);store.audit()

    def test_explicit_added_budget_continues_recorded_correction_in_original_mission(self):
        engine,store,iid,policy=self.project(calls=1);old=self.prepare(store,iid,policy)
        FakeExecutor(no_result).execute(store,old['task_id']);self.assertEqual(scheduler.project_remaining(store.read_snapshot()),0)
        self.correction(store,iid,old['obligation_bindings'][0]['binding_id']);before=store.read_snapshot()
        mid=before['instances'][iid]['current_mission_id'];gid=before['missions'][mid]['budget_grant_id']
        event=W.event(before,'EXTEND_MISSION_BUDGET',{'added_calls':1,'reason':'Authorize exactly one call for the already recorded endpoint correction.'},instance_id=iid,mission_id=mid)
        store.commit_control(event);after=store.read_snapshot()
        self.assertEqual(after['budget_grants'][gid]['max_calls'],before['budget_grants'][gid]['max_calls']+1)
        self.assertEqual(after['project_budget']['max_calls'],before['project_budget']['max_calls']+1)
        self.assertEqual(after['instances'][iid]['status'],'PAUSED');self.assertEqual(after['instances'][iid]['current_mission_id'],mid)
        for collection in ('requests','tasks','retry_grants','attempt_groups','corrections','missions'):
            self.assertEqual(after[collection],before[collection])
        sequence=after['_snapshot_sequence'];duplicate=store.commit_control(event)
        self.assertEqual(duplicate['outcome'],'EXACT_DUPLICATE');self.assertEqual(store.read_snapshot()['_snapshot_sequence'],sequence)
        self.assertEqual(corrections.advance(store,iid),[])
        self.resume(engine,store,iid);self.assertEqual(len(corrections.advance(store,iid)),1)
        corrected=self.prepare(store,iid,policy);self.assertEqual(corrected['mission_id'],mid)
        executor=FakeExecutor(no_result);self.assertEqual(executor.execute(store,corrected['task_id'])['state'],'ACCEPTED')
        self.assertEqual(executor.calls,1);self.assertEqual(scheduler.project_remaining(store.read_snapshot()),0)
        self.assertEqual(len(store.read_snapshot()['requests']),2)

    def test_budget_extension_requires_exact_human_finite_authorization_and_never_resets_attempts(self):
        engine,store,iid,policy=self.project(calls=1);old=self.prepare(store,iid,policy);FakeExecutor(no_result).execute(store,old['task_id'])
        before=store.read_snapshot();mid=before['instances'][iid]['current_mission_id']
        for added,reason in ((0,'zero'),(-1,'negative'),(True,'boolean'),(1001,'too large'),(1,'')):
            with self.subTest(added=added,reason=reason):
                with self.assertRaisesRegex(PMRSError,'AUTHORIZATION_REQUIRED'):
                    store.commit_control(W.event(store.read_snapshot(),'EXTEND_MISSION_BUDGET',{'added_calls':added,'reason':reason},instance_id=iid,mission_id=mid))
        with self.assertRaisesRegex(PMRSError,'AUTHORIZATION_REQUIRED'):
            store.commit_control(W.event(before,'EXTEND_MISSION_BUDGET',{'added_calls':1,'reason':'Wrong old round'},instance_id=iid,mission_id='MISSION-other'))
        self.assertEqual(store.read_snapshot()['_snapshot_sequence'],before['_snapshot_sequence'])
        store.commit_control(W.event(before,'EXTEND_MISSION_BUDGET',{'added_calls':2,'reason':'Explicit finite remainder for this exact round only.'},instance_id=iid,mission_id=mid))
        after=store.read_snapshot();self.assertEqual(after['instances'][iid]['status'],'ACTIVE')
        for collection in ('requests','tasks','retry_grants','attempt_groups'):
            self.assertEqual(after[collection],before[collection])
        self.assertFalse(scheduler.plan(after,[iid],policy)['selected'])
        self.assertEqual(scheduler.project_remaining(after),2)


if __name__=='__main__':unittest.main()
