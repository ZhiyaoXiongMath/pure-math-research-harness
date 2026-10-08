"""Executed workflow controls, not specification-count or historical PASS tests."""
import unittest
from copy import deepcopy
from research_studio import obligations as O,workflow_instances as W,scheduler,execution,handoff
from research_studio.workflows import registry as R
from research_studio.util import PMRSError,identity


def snapshot():
    return {'project_id':'P-test','knowledge_commit':'commit-1','records':{'KR-target':{'kind':'Statement','data':{}}},
        'instances':{},'missions':{},'candidates':{},'capabilities':{
            'CAP-HUMAN':{'actor':'human','actions':['*'],'instance_ids':['*']},
            'CAP-HOST':{'actor':'host','actions':['*'],'instance_ids':['*']}},'scope_versions':{},
        'control_events':{},'obligations':{},'requests':{},'tasks':{},'retry_grants':{},'sources':{},
        'project_budget':{'max_calls':0},'budget_grants':{},'max_workers':4,'synthetic_test_only':True}


def configured(stage='P4',role='RESEARCH',n=1,entry_basis=None):
    s=snapshot();i=W.new_instance(s,'TRW',target_ref='KR-target',instance_id='I')
    s=W.apply_control(s,W.event(s,'CREATE_INSTANCE',{'instance':i}))
    c={'binding_id':'B','instance_id':'I','mission_id':'M','stage_id':stage,'role':role,'retry_grant_id':'G',
       'method_ref':'METHOD','scope':{'target':'KR-target'},'entry_basis':entry_basis or {}}
    s['obligations']['O']=O.make('O','VERIFY' if role in R.INDEPENDENT else 'ESTABLISH',['KR-target'],'criterion',consumer_bindings=[c])
    mission={'mission_id':'M','instance_id':'I','intent_ref':'intent','authorized_scope':{'obligation_ids':['O']},'budget_grant_id':'BG',
        'retry_grants':[{'grant_id':'G','obligation_id':'O','method_ref':'METHOD','max_research_attempts':n,'reason_ref':'explicit research grant'}]}
    s=W.apply_control(s,W.authorize_event(s,'I',mission,{'budget_grant_id':'BG','max_calls':n}))
    return s,c


def prepared_event(s,c):
    p=scheduler.plan(s,['I'],{'max_workers':1});row=p['selected'][0]
    group=row['attempt_group_key'];slot=max([r['sample_slot'] for r in s['requests'].values() if r['attempt_group_key']==group],default=0)+1
    task={'task_id':'T'+str(len(s['tasks'])+1),'request_id':'Q'+str(len(s['tasks'])+1),'instance_id':'I','mission_id':'M',
        **{k:row[k] for k in ['purpose_key','responsibility_key','attempt_group_key','input_fingerprint','stage_spec_digest']},
        'sample_slot':slot,'attempt_key':identity({'group':group,'slot':slot}),'target_refs':['KR-target'],
        'context_budget':{'input_tokens':1,'prompt_overhead_tokens':0,'reserved_output_tokens':1,'safety_margin_tokens':0,'context_window_tokens':10},
        'executor_contract':{'executor':'fake'},'model_policy':{'model':'fake'},'independent':False,'role':c['role']}
    return execution.event('PREPARE',{'task':task,'candidate':row,'max_workers':1})


class Workflows(unittest.TestCase):
    def assertCode(self,code,fn):
        with self.assertRaises(PMRSError) as cm:fn()
        self.assertEqual(cm.exception.code,code)

    def test_n11_single_registry(self):
        self.assertEqual(len(R.REGISTRY['stages']),29)
        rows=list(R.REGISTRY['stages'].values())
        rows=deepcopy(rows)
        for row in rows:row.pop('digest')
        p4=next(x for x in rows if x['stage_id']=='P4');p4['allowed_scientific_kinds']=['Example']
        changed=R.compile_registry(rows)
        out=R.prompt('P4','RESEARCH','Investigate exact scope',changed)
        self.assertEqual(out['stage_spec_digest'],R.spec('P4',changed)['digest'])
        self.assertIn('Allowed scientific kinds: Example',out['sections']['EXPECTED_KNOWLEDGE_CHANGE'])
        self.assertNotEqual(out['stage_spec_digest'],R.spec('P4')['digest'])
        self.assertFalse(any(x['exit_rules']['automatic_next'] for x in rows))

    def test_p7_three_routes_no_extra_work(self):
        for route,roles in R.ROUTES.items():
            for role in ('LEARN','DIRECT','SYNTHESIS'):
                basis={'analysis_route':route,'branch_dispositions':{'LEARN':'NO_RESULT','DIRECT':'PARTIAL'}}
                if role in roles:R.validate_assignment('P7','ESTABLISH',role,basis)
                else:self.assertCode('STAGE_ROLE_FORBIDDEN',lambda:R.validate_assignment('P7','ESTABLISH',role,basis))
        self.assertCode('DEPENDENCY_PENDING',lambda:R.validate_assignment('P7','ESTABLISH','SYNTHESIS',{'analysis_route':'COMPARATIVE'}))

    def test_explicit_verify_only(self):
        self.assertCode('VERIFY_NOT_REQUIRED',lambda:R.validate_assignment('P4','VERIFY','PROOF',{}))
        basis={'dependency_threshold':'SUPPORT_QUALIFIED','consumer_requirement':{'review_mode':'SCOPED_SINGLE','purpose':'PROOF_SUPPORT'}}
        R.validate_assignment('P4','VERIFY','PROOF',basis)
        self.assertCode('STAGE_ROLE_FORBIDDEN',lambda:R.validate_assignment('P4','VERIFY','COUNTEREXAMPLE',basis))
        self.assertCode('REVIEW_MODE_REQUIRED',lambda:R.validate_assignment('P9','VERIFY','PROOF',{'consumer_requirement':{'review_mode':'SCOPED_SINGLE'}}))

    def test_pause_has_no_report_or_math_gate(self):
        s,c=configured();s=W.apply_control(s,W.event(s,'PAUSE',{'reason':'Stop now'},instance_id='I'))
        self.assertEqual(s['instances']['I']['status'],'PAUSED');self.assertEqual(len(s['records']),1)

    def test_decision_missing_report_valid_and_explicit_report_first(self):
        s,c=configured(n=2);s['reports']={'damaged':{'status':'BLOCKED','scope':{'instance_ids':['I']}}}
        e=W.decide_event(s,'I','CONTINUE','Continue from exact open scope',report_ref='damaged')
        out=W.apply_control(s,e);self.assertEqual(out['instances']['I']['status'],'ACTIVE')
        self.assertEqual(e['payload']['decision_basis']['checked_scope'],[])
        self.assertEqual(e['payload']['decision_basis']['open_obligation_refs'],[{'obligation_id':'O','definition_revision':1}])
        s['missions']['M']['report_first_actions']=['CONTINUE']
        self.assertCode('REPORT_BLOCKED',lambda:W.apply_control(s,e))

    def test_control_scope_cas_and_no_model_decision(self):
        s,c=configured();e=W.decide_event(s,'I','CONTINUE','Authorized')
        mutated=deepcopy(s);mutated['obligations']['O']['definition']['definition_revision']=2
        self.assertCode('STALE_READ',lambda:W.apply_control(mutated,e))
        e['actor']='model';self.assertCode('AUTHORIZATION_REQUIRED',lambda:W.apply_control(s,e))

    def test_bounded_sampling_no_renaming_reset(self):
        s,c=configured(n=2)
        for attempt in range(2):
            e=prepared_event(s,c);s=execution.apply_event(s,e);rid=e['payload']['task']['request_id']
            s['requests'][rid]['execution_state']='SETTLED'
        self.assertEqual(scheduler.plan(s,['I'])['state'],'WAIT')
        self.assertIn('RETRY_GRANT_EXHAUSTED',[x.get('code') for x in scheduler.plan(s,['I'])['waits']])
        renamed=deepcopy(s['obligations']['O']);renamed['definition']['obligation_id']='renamed';renamed['definition']['consumer_bindings'][0]['binding_id']='new-binding'
        s['obligations']['renamed']=renamed
        self.assertFalse(scheduler.plan(s,['I'])['selected'])
        self.assertEqual({r['sample_slot'] for r in s['requests'].values()},{1,2})

    def test_unknown_and_capture_block_new_sample(self):
        s,c=configured(n=3);e=prepared_event(s,c);s=execution.apply_event(s,e);rid=e['payload']['task']['request_id']
        s['requests'][rid]['execution_state']='UNKNOWN'
        plan=scheduler.plan(s,['I']);self.assertEqual(plan['selected'],[])
        self.assertEqual(scheduler.project_remaining(s),2)
        s['requests'][rid]['execution_state']='CAPTURED'
        self.assertEqual(scheduler.plan(s,['I'])['actions'][0]['action'],'RECOVER')

    def test_hard_material_blocker_and_relevant_repair(self):
        s,c=configured(n=2);s['blockers']={'X':{'blocker_id':'X','code':'INCOMPLETE_CONTEXT','definition_revision':1,'hardness':'HARD',
            'retry_condition':{'kind':'MATERIAL_VERIFIED','source_id':'S','coverage':['p1']},'resolution_events':[]}}
        s['obligations']['O']['projection']['blocker_refs']=['X']
        self.assertEqual(scheduler.plan(s,['I'])['selected'],[])
        s['sources']['S']={'verified':True,'coverage':['p1'],'sha256':'abc'}
        self.assertEqual(len(scheduler.plan(s,['I'])['selected']),1)
        self.assertEqual(len(s['records']),1)

    def test_route_change_does_not_reset_responsibility_limit(self):
        s,c=configured(stage='P7',role='LEARN',entry_basis={'analysis_route':'SOURCE_APPLICATION'})
        e=prepared_event(s,c);s=execution.apply_event(s,e);s['requests']['Q1']['execution_state']='SETTLED'
        c=s['obligations']['O']['definition']['consumer_bindings'][0]
        c['role']='DIRECT';c['entry_basis']['analysis_route']='DIRECT_ANALYSIS'
        self.assertFalse(scheduler.plan(s,['I'])['selected'])

    def test_bounded_retry_expression(self):
        self.assertCode('RETRY_CONDITION_INVALID',lambda:O.validate_condition({'kind':'ANY','conditions':[{'kind':'MATERIAL_VERIFIED'}]*17}))
        self.assertCode('RETRY_CONDITION_INVALID',lambda:O.validate_condition({'kind':'EXECUTE','script':'unsafe'}))

    def test_handoff_shared_ref_paused_and_idempotent(self):
        s,c=configured();s['records']['KR-candidate']={'kind':'Statement','data':{}}
        row=W.new_instance(s,'TFDW',discovery_brief_ref='brief',instance_id='D')
        s=W.apply_control(s,W.event(s,'CREATE_INSTANCE',{'instance':row}))
        s['candidates']['CB']={'instance_id':'D','statement_ref':'KR-candidate','candidate_state':'SAVED'}
        m=handoff.prepare(s,{'candidate_refs':['KR-candidate']},'TFDW_TO_TRW',from_instance_id='D')
        s=W.apply_control(s,W.event(s,'HANDOFF_PREPARED',{'manifest':m},instance_id='D'))
        d=W.decide_event(s,'D','ADOPT','Study this precise candidate',candidate_ref='KR-candidate');s=W.apply_control(s,d)
        e=handoff.adopt_event(s,m['handoff_id'],d['event_id']);s=W.apply_control(s,e)
        new=s['instances'][s['handoff_adoptions'][d['event_id']]['instance_id']]
        self.assertEqual(new['target_ref'],'KR-candidate');self.assertEqual(new['status'],'PAUSED');self.assertEqual(new['mission_ids'],[])
        self.assertEqual(s['instances']['I']['target_ref'],'KR-target');self.assertEqual(len(s['records']),2)
        self.assertEqual(W.apply_control(s,e),s)

    def test_native_restore_retains_uncertain_budget(self):
        s,c=configured(n=3);s=execution.apply_event(s,prepared_event(s,c));s['requests']['Q1']['execution_state']='SENT'
        out=execution.apply_event(s,execution.event('NATIVE_RESTORED',{'backup_identity':'backup'}))
        self.assertEqual(out['requests']['Q1']['execution_state'],'UNKNOWN');self.assertEqual(scheduler.project_remaining(out),2)
        self.assertEqual(out['instances']['I']['status'],'PAUSED')

if __name__=='__main__':unittest.main()

class RuntimeIntegration(unittest.TestCase):
    def make_project(self,root,n=2,stage='P4',role='RESEARCH',entry_basis=None):
        from research_studio.store import Store
        from research_studio.changes import prepare_source_input
        store=Store.create(root,'Synthetic integration test',synthetic=True)
        receipt=store.commit(prepare_source_input(store.read_snapshot(),b'For every integer n, n + 0 = n.',blob_get=store.read_blob))
        s=store.read_snapshot();target=receipt['target_ref'];i=W.new_instance(s,'TRW',target_ref=target,instance_id='I')
        store.commit_control(W.event(s,'CREATE_INSTANCE',{'instance':i}));s=store.read_snapshot()
        criterion=store.blob(b'Investigate the exact target. Account for the attempted method and any unproved condition.')
        c={'binding_id':'B','instance_id':'I','mission_id':'M','stage_id':stage,'role':role,'retry_grant_id':'G','method_ref':'METHOD',
           'scope':{'target_ref':target},'entry_basis':entry_basis or {},'threshold':'ARTIFACT_AVAILABLE'}
        o=O.make('O','REDUCE' if stage=='P6' else 'ESTABLISH',[target],criterion,consumer_bindings=[c],created_by='HUMAN')
        m={'mission_id':'M','instance_id':'I','intent_ref':criterion,'authorized_scope':{'obligation_ids':['O'],'target_refs':[target]},
           'budget_grant_id':'BG','obligations':[o],'retry_grants':[{'grant_id':'G','obligation_id':'O','method_ref':'METHOD','max_research_attempts':n,'reason_ref':criterion}]}
        store.commit_control(W.authorize_event(s,'I',m,{'budget_grant_id':'BG','max_calls':n}))
        policy={'model_policy':{'model':'test-model','reasoning_effort':'none','service_tier':'test'},
                'capacity':{'model_id':'test-model','capacity_source':'SYNTHETIC_TEST_ONLY','capacity_revision':'test-1',
                    'context_window_tokens':100000,'model_max_output_tokens':10000,'tokenizer_revision':'byte-bound-test',
                    'tokenizer_byte_bound_verified':True,'token_count_bound':'UTF8_BYTES'},
                'executor_contract':{'executor':'fake','sandbox':'synthetic','environment_revision':'test-1'}}
        return store,policy

    @staticmethod
    def no_result(task,snapshot):
        from research_studio import contracts as C
        from research_studio.util import canonical
        effects=[{'binding_id':b['binding_id'],'expected_definition_revision':b['expected_definition_revision'],'work_disposition':'NO_RESULT',
                  'resolution_proposal':'UNRESOLVED','evidence_refs':[],'remaining_conditions':[], 'blocker_proposals':[]} for b in task['obligation_bindings']]
        payload={'schema':C.CHANGE_SCHEMA,'task_id':task['task_id'],'request_id':task['request_id'],'base_knowledge_commit':task['knowledge_commit'],
            'read_set_digest':C.digest(task['read_set']),'query_guard_digest':C.digest(task['query_guards']),'write_guard_digest':C.digest(task['write_guards']),
            'operations':[],'obligation_effects':effects,'new_obligation_proposals':[],'work_outcome':'NO_RESULT',
            'attempt_account':'The fixed inputs were read. This deterministic transport provides no new derivation or additional next step.',
            'claimed_change':'No new scientific result.','semantic_novelty':'NOT_AUTOMATICALLY_CERTIFIED'}
        return canonical({'schema':C.RESPONSE_SCHEMA,'task_id':task['task_id'],'request_id':task['request_id'],'payload_kind':'KNOWLEDGE_CHANGE','payload':payload})

    def test_real_store_fake_transport_admission_budget_and_replay(self):
        import tempfile
        from pathlib import Path
        from research_studio.runner import FakeExecutor,run
        with tempfile.TemporaryDirectory() as tmp:
            store,policy=self.make_project(Path(tmp)/'project',n=2);before=store.read_snapshot()
            fake=FakeExecutor(self.no_result);result=run(store,instance_id='I',executor=fake,max_tasks=4,policy=policy)
            s=store.read_snapshot();self.assertEqual(fake.calls,2);self.assertEqual(fake.network_calls+fake.spawn_calls,0)
            self.assertEqual(result['state'],'WAIT');self.assertEqual(len(s['records']),len(before['records']))
            self.assertEqual(s['obligations']['O']['projection']['resolution'],'UNRESOLVED')
            self.assertEqual(s['obligations']['O']['definition']['definition_revision'],1)
            for rid,r in s['requests'].items():
                self.assertEqual(r['execution_state'],'SETTLED');self.assertIsNotNone(r['capture_ref'])
                self.assertEqual(execution.recover(store,rid)['state'],'EXACT_DUPLICATE')
            self.assertEqual(store.read_snapshot()['knowledge_commit'],s['knowledge_commit'])
            store.audit()

    def test_pause_capture_and_fault_recovery_never_calls_twice(self):
        import tempfile
        from pathlib import Path
        from research_studio.runner import FakeExecutor,SimulatedCrash
        with tempfile.TemporaryDirectory() as tmp:
            store,policy=self.make_project(Path(tmp)/'project',n=2)
            made=scheduler.commit_dispatch(store,scheduler.plan(store.read_snapshot(),['I']),policy=policy)
            tid=made['prepared'][0]['task_id'];rid=made['prepared'][0]['request_id']
            fake=FakeExecutor(self.no_result,fault_at='AFTER_CAPTURE_RECEIPT_BEFORE_ADMISSION')
            with self.assertRaises(SimulatedCrash):fake.execute(store,tid)
            s=store.read_snapshot();store.commit_control(W.event(s,'PAUSE',{'reason':'Pause with saved output'},instance_id='I'))
            with self.assertRaises(PMRSError):execution.recover(store,rid)
            s=store.read_snapshot();decision=W.decide_event(s,'I','CONTINUE','Continue the same authorized responsibility')
            store.commit_control(decision);execution.recover(store,rid)
            self.assertEqual(fake.calls,1);self.assertEqual(store.read_snapshot()['requests'][rid]['execution_state'],'SETTLED')
            self.assertEqual(execution.recover(store,rid)['state'],'EXACT_DUPLICATE')


class RuntimeStories(unittest.TestCase):
    def test_start_form_report_first_is_explicit_and_failed_report_blocks_only_selected_actions(self):
        from tempfile import TemporaryDirectory
        from research_studio.engine import Engine
        from research_studio import demo,reports,contracts as C
        from research_studio.runner import FakeExecutor
        from research_studio.util import canonical
        from tests.test_final_reports import actual_render
        def failed_semantic(task,snapshot):
            if task['role']!='REPORT_SEMANTIC':return demo.response(task,snapshot)
            payload={'profile':task['report_context']['profile'],'verdict':'REVISE','uncheckable':[],
                     'findings':[{'code':'NEW_LEMMA_REQUIRED','anchor':'Scope','severity':'BLOCKING',
                                  'description':'A required uniform argument remains unresolved.'}]}
            return canonical({'schema':C.RESPONSE_SCHEMA,'task_id':task['task_id'],'request_id':task['request_id'],
                              'payload_kind':'REPORT_REVIEW','payload':payload})
        with TemporaryDirectory() as directory:
            e=Engine();store=e.create(directory+'/p',demo.ARITHMETIC,synthetic=True)
            target=next(iter(store.read_snapshot()['records']))
            for explicit in (False,True):
                iid=e.new_workflow(store,'TRW',target_ref=target)['instance_id']
                before=store.read_snapshot()['knowledge_commit']
                for invalid in ('CONTINUE',['PAUSE'],['CONTINUE','CONTINUE'],[True]):
                    with self.assertRaisesRegex(PMRSError,'AUTHORIZATION_REQUIRED'):
                        e.start_round(store,iid,'Invalid report-first selection.',max_calls=8,policy=demo.policy(),report_first_actions=invalid)
                    self.assertEqual(store.read_snapshot()['knowledge_commit'],before)
                result=e.start_round(store,iid,'Review the exact open scope.',max_calls=8,policy=demo.policy(),
                                     report_first_actions=['CONTINUE'] if explicit else None)
                mission=store.read_snapshot()['missions'][result['mission_id']]
                if explicit:
                    self.assertEqual(mission['report_first_actions'],['CONTINUE'])
                    with self.assertRaisesRegex(PMRSError,'REPORT_BLOCKED'):
                        e.decide(store,iid,'CONTINUE','Wait for the explicitly selected report condition.',snapshot_commit=store.read_snapshot()['knowledge_commit'])
                else:
                    self.assertNotIn('report_first_actions',mission)
                    e.decide(store,iid,'CONTINUE','Continue from the open knowledge basis.',snapshot_commit=store.read_snapshot()['knowledge_commit'])
                fake=FakeExecutor(failed_semantic)
                failed=reports.run(store,iid,executor=fake,policy=demo.policy(),renderer=actual_render)
                self.assertEqual(failed['state'],'REPORT_BLOCKED');self.assertEqual(fake.calls,2)
                kwargs={'snapshot_commit':store.read_snapshot()['knowledge_commit'],'report_ref':failed['report_id']}
                if explicit:
                    with self.assertRaisesRegex(PMRSError,'REPORT_BLOCKED'):
                        e.decide(store,iid,'CONTINUE','An incomplete report cannot satisfy this explicit condition.',**kwargs)
                else:e.decide(store,iid,'CONTINUE','The report defect does not invalidate the knowledge decision.',**kwargs)
                e.decide(store,iid,'END','Ending was not selected as a report-first action.',snapshot_commit=store.read_snapshot()['knowledge_commit'])
                self.assertEqual(fake.calls,2)
            store.audit()

    def test_trw_original_target_dual_and_open_decision(self):
        from tempfile import TemporaryDirectory
        from research_studio.engine import Engine
        from research_studio import demo,assurance
        with TemporaryDirectory() as d:
            engine=Engine();store=engine.create(d+'/p',demo.ARITHMETIC,synthetic=True)
            target=next(iter(store.read_snapshot()['records']));iid=engine.new_workflow(store,'TRW',target_ref=target)['instance_id']
            engine.start_round(store,iid,'Investigate the fixed target.',max_calls=6,max_workers=2,policy=demo.policy())
            fake=demo.executor();result=engine.run_round(store,iid,executor=fake);s=store.read_snapshot()
            self.assertEqual(fake.calls,3);self.assertEqual(fake.network_calls+fake.spawn_calls,0)
            self.assertEqual({(t['stage_id'],t['role']) for t in s['tasks'].values()},{('P4','RESEARCH'),('P9','PROOF'),('P9','COUNTEREXAMPLE')})
            reviews=[t for t in s['tasks'].values() if t['independent']]
            self.assertEqual(len({t['purpose_key'] for t in reviews}),2)
            self.assertEqual({t['model_policy']['reasoning_effort'] for t in reviews},{'max'})
            for t in reviews:
                self.assertFalse(any(s['records'][x['ref']]['kind']=='Assessment' for x in t['input_manifest'] if x['kind']=='record'))
                self.assertTrue(t['excluded_verdicts']);self.assertEqual(t['required_assurance']['review_mode'],'TARGET_DUAL')
            self.assertEqual(s['instances'][iid]['target_ref'],target)
            self.assertTrue(all(r['acceptance_state']=='ACCEPTED' for r in s['requests'].values()))
            sid=next(iter(s['supports']));self.assertNotEqual(assurance.evaluate_requirement(s,sid,reviews[0]['required_assurance'])['result'],'QUALIFIED')
            before=len(s['tasks']);engine.decide(store,iid,'CONTINUE','Keep the exact open mathematics.',snapshot_commit=s['knowledge_commit'])
            self.assertEqual(engine.run_round(store,iid,executor=fake)['state'],'WAIT');self.assertEqual(len(store.read_snapshot()['tasks']),before)
            store.audit()

    def test_tfdw_candidate_formulation_and_exact_paused_handoff(self):
        from tempfile import TemporaryDirectory
        from research_studio.engine import Engine
        from research_studio import demo
        with TemporaryDirectory() as d:
            engine=Engine();store=engine.create(d+'/p',demo.scenario('TFDW').encode(),synthetic=True,phenomenon=True)
            iid=engine.new_workflow(store,'TFDW',discovery_scope=demo.discovery_scope('Discover exact matrix candidates.'))['instance_id']
            engine.start_round(store,iid,'Keep the background fixed and retain unknown evidence.',max_calls=5,policy=demo.policy())
            fake=demo.executor();engine.run_round(store,iid,executor=fake);s=store.read_snapshot()
            self.assertEqual(fake.calls,2);self.assertEqual(len(s['candidates']),1);self.assertEqual(s['supports'],{})
            candidate=next(iter(s['candidates'].values()))['statement_ref'];self.assertEqual(s['records'][candidate]['kind'],'Statement')
            self.assertEqual({t['role'] for t in s['tasks'].values()},{'LEARN','FORMULATION_REVIEW'})
            prepared=engine.prepare_handoff(store,iid,'TFDW_TO_TRW',{'candidate_refs':[candidate]})
            decision=engine.decide(store,iid,'ADOPT','Research this exact candidate without granting proof.',snapshot_commit=store.read_snapshot()['knowledge_commit'],candidate_ref=candidate)
            result=engine.adopt_handoff(store,prepared['handoff_id'],decision);s=store.read_snapshot();adopted=s['instances'][result['instance_id']]
            self.assertEqual(adopted['target_ref'],candidate);self.assertEqual(adopted['status'],'PAUSED');self.assertEqual(adopted['mission_ids'],[])
            self.assertEqual(len(s['tasks']),2);self.assertEqual(s['supports'],{});store.audit()

    def test_zero_candidates_no_padding_and_report_failure_does_not_block_decision(self):
        from tempfile import TemporaryDirectory
        from research_studio.engine import Engine
        from research_studio import demo
        from research_studio.runner import FakeExecutor
        with TemporaryDirectory() as d:
            e=Engine();store=e.create(d+'/p',b'An unresolved phenomenon.',phenomenon=True,synthetic=True)
            iid=e.new_workflow(store,'TFDW',discovery_scope=demo.discovery_scope('Preserve uncertainty.'))['instance_id']
            e.start_round(store,iid,'Do not fabricate candidates.',max_calls=4,policy=demo.policy())
            f=FakeExecutor(RuntimeIntegration.no_result);e.run_round(store,iid,executor=f)
            s=store.read_snapshot();self.assertEqual(s['candidates'],{});self.assertEqual(f.calls,1)
            decision=e.decide(store,iid,'END_WITHOUT_ADOPTION','No supported candidate was identified.',snapshot_commit=s['knowledge_commit'])
            self.assertIsNone(decision['decision_basis']['report_ref']);self.assertEqual(store.read_snapshot()['instances'][iid]['status'],'ENDED')

    def test_future_scope_configuration_preserves_old_tasks_and_budget(self):
        from tempfile import TemporaryDirectory
        from research_studio.engine import Engine
        from research_studio import demo
        with TemporaryDirectory() as d:
            e=Engine();store=e.create(d+'/p',demo.ARITHMETIC,synthetic=True);target=next(iter(store.read_snapshot()['records']))
            iid=e.new_workflow(store,'TRW',target_ref=target)['instance_id'];e.start_round(store,iid,'Fixed scope.',max_calls=6,policy=demo.policy())
            e.prepare(store,iid);before=store.read_snapshot()
            override={'explicit':True,'scope':{'workflow_kind':'TRW','stage_id':'P9','role':'PROOF','purpose':'DEFAULT'},'reasoning_effort':'xhigh'}
            e.update_configuration(store,iid,[override]);after=store.read_snapshot()
            self.assertEqual(before['tasks'],after['tasks']);self.assertEqual(before['project_budget'],after['project_budget']);self.assertEqual(before['retry_grants'],after['retry_grants'])
            e.run_round(store,iid,executor=demo.executor());s=store.read_snapshot()
            self.assertEqual({t['role']:t['model_policy']['reasoning_effort'] for t in s['tasks'].values()},{'RESEARCH':'max','PROOF':'xhigh','COUNTEREXAMPLE':'max'})


class RuntimeFaults(unittest.TestCase):
    def test_capture_boundaries_recover_without_second_call(self):
        from tempfile import TemporaryDirectory
        from research_studio.runner import FakeExecutor,SimulatedCrash
        from research_studio import execution
        for fault in ['AFTER_FREEZE','AFTER_RESERVATION_BEFORE_SEND','AFTER_SEND_BEFORE_SENT','AFTER_CAPTURE_BLOB_BEFORE_RECEIPT','AFTER_CAPTURE_RECEIPT_BEFORE_ADMISSION']:
            with self.subTest(fault=fault),TemporaryDirectory() as d:
                store,policy=RuntimeIntegration().make_project(d+'/p',2);iid='I'
                ids=scheduler.commit_dispatch(store,scheduler.plan(store.read_snapshot(),[iid],policy),policy=policy)
                tid=ids['prepared'][0]['task_id']
                fake=FakeExecutor(RuntimeIntegration.no_result,fault_at=fault)
                with self.assertRaises(SimulatedCrash):fake.execute(store,tid)
                before=store.read_snapshot();rid=before['tasks'][tid]['request_id'];out=execution.recover(store,rid)
                self.assertEqual(fake.calls,0 if fault in {'AFTER_FREEZE','AFTER_RESERVATION_BEFORE_SEND'} else 1)
                if 'CAPTURE' in fault:
                    self.assertEqual(out['state'],'ACCEPTED');self.assertEqual(execution.recover(store,rid)['state'],'EXACT_DUPLICATE')
                else:self.assertEqual(out['state'],'WAIT')
                self.assertEqual(len(store.read_snapshot()['requests']),1);store.audit()

    def test_sealed_capture_recovery_never_spawns(self):
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from research_studio import tasks
        from research_studio.runner import recover_transport
        from research_studio.util import immutable,canonical,sha
        with TemporaryDirectory() as d:
            store,policy=RuntimeIntegration().make_project(d+'/p',1);iid='I'
            tid=scheduler.commit_dispatch(store,scheduler.plan(store.read_snapshot(),[iid],policy),policy=policy)['prepared'][0]['task_id']
            task=tasks.load(store,tid);rid=task['request_id'];reservation=execution.reserve(store,rid,execution_kind='SYNTHETIC_TEST_ONLY')
            raw=RuntimeIntegration.no_result(task,store.read_snapshot());root=store.root/'runs'/tid
            command=['synthetic-no-process','--model','test-model'];immutable(root/'command.json',canonical(command))
            for name,value in {'task.json':canonical(task),'packet.json':store.read_blob(task['input_packet_ref']),'prompt.md':store.read_blob(task['prompt_ref']),'response.json':raw}.items():immutable(root/'work'/name,value)
            immutable(root/'capture.json',canonical({'task_id':tid,'request_id':rid,'execution_id':reservation['execution_id'],'task_sha256':sha(canonical(task)),'response_sha256':sha(raw),'command_sha256':sha(canonical(command))}))
            with patch('subprocess.Popen',side_effect=AssertionError('Recovery must never spawn')):
                self.assertEqual(recover_transport(store,tid)['state'],'ACCEPTED');self.assertEqual(recover_transport(store,tid)['state'],'EXACT_DUPLICATE')
            self.assertEqual(len(store.read_snapshot()['requests']),1);store.audit()


class CoverageExecution(unittest.TestCase):
    def test_superwindow_parts_and_required_independent_integration(self):
        from tempfile import TemporaryDirectory
        from research_studio.engine import Engine
        from research_studio import demo,assurance,contracts as C,tasks
        from research_studio.runner import FakeExecutor,run
        from research_studio.knowledge import locator
        from research_studio.util import loads,canonical
        with TemporaryDirectory() as d:
            e=Engine();store=e.create(d+'/p',demo.ARITHMETIC,synthetic=True);target=next(iter(store.read_snapshot()['records']))
            iid=e.new_workflow(store,'TRW',target_ref=target)['instance_id'];policy=demo.policy()
            e.start_round(store,iid,'Review the exact long argument and its interfaces.',max_calls=12,max_workers=2,policy=policy)
            longbody=('Let n be an arbitrary integer. The identity axiom gives n + 0 = n. This line preserves the declared original mathematical text.\n'*1200)
            def author(task,s):
                response=loads(demo.response(task,s));op=response['payload']['operations'][0];op['body']=longbody;op['data']['steps'][0]['locator']=locator(longbody)
                return canonical(response)
            run(store,instance_id=iid,executor=FakeExecutor(author),max_tasks=1,policy=policy)
            s=store.read_snapshot();sid=next(iter(s['supports']));arg=s['supports'][sid]['argument_ref'];raw=longbody.encode();length=len(raw)
            scope=[{'target_ref':arg,'locators':[locator(raw)],'aspects':['derivation']}]
            req=assurance.requirement('PROOF_SUPPORT',scope,review_mode='TARGET_DUAL')
            parts=[];bounds=[length*k//4 for k in range(5)]
            for slot in req['review_slots']:
                for index in range(4):parts.append({'part_id':slot['slot_id']+str(index),'review_slot_id':slot['slot_id'],
                    'checked_scope':[{'target_ref':arg,'locators':[locator(raw,bounds[index],bounds[index+1])],'aspects':['derivation']}],
                    'required_input_refs':[target],'declared_boundary_refs':[target],'task_ref':None})
            plan={'plan_id':'CP-long','target_revision_refs':[arg],'required_scope':scope,'parts':parts,
                'integration_scope':[{'target_ref':arg,'locators':[locator(raw,0,100),locator(raw,length-100,length)],'aspects':['global_quantifiers_and_common_witness']}]}
            small=deepcopy(policy);small['capacity']['context_window_tokens']=80000;small['resource_policy_revision']='test-small-2';small['max_workers']=2
            # A full request really exceeds the actual byte-bound context. The
            # explicit parts retain full original hashes, never a summary.
            from research_studio.context import build_packet,token_preflight
            full=build_packet(s,[arg],store.read_blob,independent=True)
            with self.assertRaises(PMRSError) as cm:token_preflight(canonical({'body':longbody}),small['capacity'],reserved_output_tokens=4096)
            self.assertEqual(cm.exception.code,'CONTEXT_LIMIT')
            scheduler.register_coverage_plan(store,iid,plan,req,sid)
            def review(task,s):
                response=loads(demo.response(task,s));data=response['payload']['operations'][0]['data'];assigned=task['required_assurance']['required_scope']
                data['checked']=[{'ref':r['target_ref'],'locators':r['locators'],'aspect':a} for r in assigned for a in r['aspects']]
                data['unchecked']=[];data['verdict']='SUPPORTED_WITHIN_SCOPE'
                return canonical(response)
            fake=FakeExecutor(review);result=run(store,instance_id=iid,executor=fake,max_tasks=8,policy=small);s=store.read_snapshot()
            self.assertEqual(len(result['tasks']),8);aggregate,perpart,_=scheduler.coverage_status(s,'CP-long')
            self.assertTrue(all(v['result']=='QUALIFIED' for v in perpart.values()));self.assertEqual(aggregate['result'],'PARTIAL')
            self.assertNotEqual(assurance.evaluate_requirement(s,sid,req,C.digest(req))['result'],'QUALIFIED')
            for tid in result['tasks']:
                t=tasks.load(store,tid);packet=loads(store.read_blob(t['input_packet_ref']))
                self.assertIn(s['records'][target]['body_sha256'],packet['body_text'])
                self.assertNotIn(s['records'][arg]['body_sha256'],packet['body_text']);self.assertEqual(packet['partial_target_bodies'][arg]['state'],'PARTIAL_TARGET_BODY')
                self.assertLess(t['context_budget']['input_tokens']+t['context_budget']['reserved_output_tokens']+t['context_budget']['safety_margin_tokens'],80001)
                self.assertEqual(t['resource_policy_revision'],'test-small-2')
            self.assertEqual(len(scheduler.derive_coverage_integration(store,iid)),1)
            run(store,instance_id=iid,executor=fake,max_tasks=1,policy=small);s=store.read_snapshot()
            self.assertEqual(scheduler.coverage_status(s,'CP-long')[0]['result'],'QUALIFIED')
            self.assertEqual(assurance.evaluate_requirement(s,sid,req,C.digest(req))['result'],'QUALIFIED')
            damaged=deepcopy(s)
            for eid,event in list(damaged['review_executions'].items()):
                if damaged['tasks'][event['task_id']].get('coverage_plan_id')=='CP-long' and damaged['tasks'][event['task_id']].get('coverage_part_id') is None:del damaged['review_executions'][eid]
            damaged['coverage_plans']['CP-long']['status']='QUALIFIED'
            self.assertNotEqual(assurance.evaluate_requirement(damaged,sid,req,C.digest(req))['result'],'QUALIFIED')
            self.assertEqual(fake.calls,9);self.assertEqual(fake.network_calls+fake.spawn_calls,0);store.audit()


class RuntimeBoundaries(unittest.TestCase):
    def test_format_repairs_are_separate_finite_cost_not_new_science_sample(self):
        from tempfile import TemporaryDirectory
        from research_studio.engine import Engine
        from research_studio import demo
        from research_studio.runner import FakeExecutor
        with TemporaryDirectory() as d:
            e=Engine();store=e.create(d+'/p',demo.ARITHMETIC,synthetic=True);target=next(iter(store.read_snapshot()['records']))
            iid=e.new_workflow(store,'TRW',target_ref=target)['instance_id'];e.start_round(store,iid,'Investigate.',max_calls=4,policy=demo.policy())
            tid=e.prepare(store,iid)['prepared'][0]['task_id'];bad=FakeExecutor(lambda t,s:b'{"bad":true}')
            with self.assertRaises(PMRSError):bad.execute(store,tid)
            s=store.read_snapshot();rid=s['tasks'][tid]['request_id'];original=s['requests'][rid]['capture_ref']
            repaired=execution.prepare_repair(store,rid,'FORMAT');good=FakeExecutor(RuntimeIntegration.no_result);good.execute(store,repaired['task_id'])
            s=store.read_snapshot();self.assertEqual(store.read_blob(original),b'{"bad":true}');self.assertEqual(len(s['requests']),2)
            self.assertEqual({r['sample_slot'] for r in s['requests'].values()},{1});self.assertEqual(scheduler.project_remaining(s),2)
            self.assertEqual(execution.recover(store,rid)['state'],'REJECTED_CONTRACT')
            with self.assertRaises(PMRSError) as cm:execution.prepare_repair(store,rid,'FORMAT')
            self.assertEqual(cm.exception.code,'REPAIR_LIMIT');self.assertFalse(e.schedule(store,iid)['selected'])
            self.assertEqual(bad.calls+good.calls,2);store.audit()

    def test_cancel_unknown_and_capture_identity_do_not_close_duty(self):
        from tempfile import TemporaryDirectory
        from research_studio.runner import FakeExecutor,SimulatedCrash
        with TemporaryDirectory() as d:
            store,policy=RuntimeIntegration().make_project(d+'/p',2);made=scheduler.commit_dispatch(store,scheduler.plan(store.read_snapshot(),['I']),policy=policy)
            tid=made['prepared'][0]['task_id'];rid=made['prepared'][0]['request_id'];before=deepcopy(store.read_snapshot()['obligations'])
            fake=FakeExecutor(RuntimeIntegration.no_result,fault_at='AFTER_CAPTURE_RECEIPT_BEFORE_ADMISSION')
            with self.assertRaises(SimulatedCrash):fake.execute(store,tid)
            with self.assertRaises(PMRSError):execution.capture(store,rid,b'different bytes')
            store.commit_control(W.event(store.read_snapshot(),'CANCEL_REQUEST',{'request_id':rid,'reason':'Cancel only this lease.'},instance_id='I'))
            with self.assertRaises(PMRSError):execution.recover(store,rid)
            self.assertEqual(store.read_snapshot()['obligations'],before);self.assertEqual(scheduler.project_remaining(store.read_snapshot()),1)
            self.assertEqual(fake.calls,1)

    def test_no_budget_real_fake_and_missing_isolation_fail_before_call(self):
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from research_studio.engine import Engine
        from research_studio import demo
        from research_studio.runner import FakeExecutor,CodexExecutor
        with TemporaryDirectory() as d:
            e=Engine();store=e.create(d+'/real',demo.ARITHMETIC,synthetic=False);target=next(iter(store.read_snapshot()['records']))
            iid=e.new_workflow(store,'TRW',target_ref=target)['instance_id'];self.assertEqual(scheduler.project_remaining(store.read_snapshot()),0)
            fake=demo.executor()
            with self.assertRaises(PMRSError):e.run_round(store,iid,executor=fake)
            self.assertEqual(fake.calls,0)
            store,policy=RuntimeIntegration().make_project(d+'/test',1);tid=scheduler.commit_dispatch(store,scheduler.plan(store.read_snapshot(),['I']),policy=policy)['prepared'][0]['task_id']
            with patch('subprocess.Popen',side_effect=AssertionError('No launch permitted')):
                with self.assertRaises(PMRSError):CodexExecutor().execute(store,tid)
            self.assertEqual(next(iter(store.read_snapshot()['requests'].values()))['execution_state'],'PREPARED')
            # The same frozen fake request is refused if a real project supplies
            # it, before fake.calls increments or any process/network action.
            state=store.read_snapshot();state['synthetic_test_only']=False
            with self.assertRaises(PMRSError):execution.apply_event(state,execution.event('RESERVE',{'request_id':state['tasks'][tid]['request_id'],
                'execution_kind':'SYNTHETIC_TEST_ONLY','executor_contract':state['tasks'][tid]['executor_contract'],'model_policy':state['tasks'][tid]['model_policy']}))

    def test_transport_contract_environment_and_single_coordinator(self):
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from pathlib import Path
        from research_studio.runner import permissions,environment,coordinator
        from research_studio.store import Store
        with TemporaryDirectory() as d:
            command=permissions('/usr/bin/codex',Path(d));encoded=str(command)
            self.assertIn('permissions.research-task.network.enabled=false',encoded);self.assertIn('web_search="disabled"',encoded);self.assertNotIn('danger-full-access',encoded)
            with patch.dict('os.environ',{'CODEX_THREAD_ID':'secret','CODEX_APP_SERVER_URL':'secret','OPENAI_API_KEY':'secret','CODEX_HOME':d},clear=True):
                env=environment();self.assertNotIn('CODEX_THREAD_ID',env);self.assertNotIn('CODEX_APP_SERVER_URL',env)
            store=Store.create(d+'/p','Only one coordinator',synthetic=True)
            with coordinator(store):
                with self.assertRaises(PMRSError) as cm:
                    with coordinator(store):pass
                self.assertEqual(cm.exception.code,'COORDINATOR_BUSY')

    def test_frozen_manifest_and_model_tampering_fail_closed(self):
        from tempfile import TemporaryDirectory
        from research_studio import tasks,changes
        with TemporaryDirectory() as d:
            store,policy=RuntimeIntegration().make_project(d+'/p',1);tid=scheduler.commit_dispatch(store,scheduler.plan(store.read_snapshot(),['I']),policy=policy)['prepared'][0]['task_id']
            task=tasks.load(store,tid);rid=task['request_id'];original=store.read_snapshot()
            wrong=deepcopy(task['model_policy']);wrong['reasoning_effort']='high'
            with self.assertRaises(PMRSError) as cm:execution.reserve(store,rid,execution_kind='SYNTHETIC_TEST_ONLY',model_policy=wrong)
            self.assertEqual(cm.exception.code,'EXECUTOR_CONTRACT_CHANGED');self.assertEqual(store.read_snapshot()['requests'],original['requests'])
            malformed=deepcopy(task);malformed['read_set'][0]['body_hash']='f'*64
            with self.assertRaises(PMRSError):changes.live_check(malformed,original,store.read_blob)
            revised=deepcopy(original);revised['obligations']['O']['definition']['definition_revision']+=1
            with self.assertRaises(PMRSError) as cm:changes.live_check(task,revised,store.read_blob)
            self.assertEqual(cm.exception.code,'STALE_OBLIGATION_DEFINITION')


class SharedRuntime(unittest.TestCase):
    def test_actual_multiinstance_fair_dispatch_and_policy_isolation(self):
        from tempfile import TemporaryDirectory
        from threading import Barrier,Lock
        from research_studio.engine import Engine
        from research_studio import demo
        from research_studio.runner import FakeExecutor
        with TemporaryDirectory() as d:
            e=Engine();store=e.create(d+'/p',demo.ARITHMETIC,synthetic=True);target=next(iter(store.read_snapshot()['records']))
            trw=e.new_workflow(store,'TRW',target_ref=target)['instance_id'];tfdw=e.new_workflow(store,'TFDW',discovery_scope=demo.discovery_scope('A separate discovery phenomenon.'))['instance_id']
            p=demo.policy();p['model_overrides']=[{'explicit':True,'scope':{'workflow_kind':'TRW','stage_id':'P4','role':'RESEARCH','purpose':'DEFAULT'},'reasoning_effort':'high'}]
            e.start_round(store,trw,'Investigate the fixed target.',max_calls=3,max_workers=2,policy=p)
            e.start_round(store,tfdw,'Keep the discovery frontier unknown.',max_calls=3,max_workers=2,policy=demo.policy())
            barrier=Barrier(2);seen=[];lock=Lock()
            def response(t,s):
                with lock:seen.append((t['instance_id'],t['model_policy']['reasoning_effort']))
                barrier.wait(timeout=3);return RuntimeIntegration.no_result(t,s)
            fake=FakeExecutor(response);e.run_round(store,trw,executor=fake)
            s=store.read_snapshot();self.assertEqual(set(seen),{(trw,'high'),(tfdw,'xhigh')});self.assertEqual(fake.calls,2)
            self.assertEqual(len({r['purpose_key'] for r in s['requests'].values()}),2);self.assertEqual(scheduler.project_remaining(s),4)
            self.assertEqual(s['instances'][trw]['target_ref'],target);self.assertIsNone(s['instances'][tfdw]['target_ref']);self.assertEqual(s['candidates'],{})
            self.assertEqual(len(s['missions']),2);self.assertEqual(len(s['tasks']),2);self.assertIn('2',s['scheduler_state']['last_instance_by_tier'])
            self.assertEqual(e.run_round(store,tfdw,executor=fake)['state'],'WAIT');self.assertEqual(fake.calls,2);store.audit()

    def test_concurrent_recover_has_one_scientific_commit(self):
        from tempfile import TemporaryDirectory
        from concurrent.futures import ThreadPoolExecutor
        from research_studio.runner import FakeExecutor,SimulatedCrash
        with TemporaryDirectory() as d:
            store,policy=RuntimeIntegration().make_project(d+'/p',1);prepared=scheduler.commit_dispatch(store,scheduler.plan(store.read_snapshot(),['I']),policy=policy)['prepared'][0]
            fake=FakeExecutor(RuntimeIntegration.no_result,fault_at='AFTER_CAPTURE_RECEIPT_BEFORE_ADMISSION')
            with self.assertRaises(SimulatedCrash):fake.execute(store,prepared['task_id'])
            with ThreadPoolExecutor(2) as pool:
                futures=[pool.submit(execution.recover,store,prepared['request_id']) for _ in range(2)]
                for f in futures:self.assertIn(f.result()['state'],{'ACCEPTED','EXACT_DUPLICATE'})
            s=store.read_snapshot();self.assertEqual(len(s['accepted_requests']),1);self.assertEqual(len(s['requests']),1);self.assertEqual(fake.calls,1);store.audit()

    def test_p7_single_routes_and_comparative_actual_work(self):
        from tempfile import TemporaryDirectory
        from research_studio.runner import FakeExecutor,run
        from research_studio import tasks
        from research_studio.util import loads
        for route,roles in [('SOURCE_APPLICATION',['LEARN']),('DIRECT_ANALYSIS',['DIRECT']),('COMPARATIVE',['LEARN','DIRECT','SYNTHESIS'])]:
            with self.subTest(route=route),TemporaryDirectory() as d:
                store,policy=RuntimeIntegration().make_project(d+'/p',1,stage='P7',role=roles[0],entry_basis={'analysis_route':route})
                from research_studio import demo
                policy=demo.policy()
                store.commit_control(W.event(store.read_snapshot(),'RETIRE_CONSUMER',{'binding_id':'B','reason':'Use the exact comparative mission scope.'},instance_id='I'))
                s=store.read_snapshot();target=s['instances']['I']['target_ref'];criterion=store.blob(b'Inspect only the assigned method and preserve unresolved mathematical conditions.')
                obligations=[];grants=[]
                for role in roles:
                    basis={'analysis_route':route}
                    if role=='SYNTHESIS':basis['branch_dispositions']={'LEARN':'B-LEARN','DIRECT':'B-DIRECT'}
                    c={'binding_id':'B-'+role,'instance_id':'I','mission_id':'M2','stage_id':'P7','role':role,'retry_grant_id':'G-'+role,
                        'method_ref':'COMPARATIVE_METHOD','scope':{'target_ref':target},'entry_basis':basis,'threshold':'WORK_DISPOSITION_RECORDED'}
                    obligations.append(O.make('O-'+role,'ESTABLISH',[target],criterion,consumer_bindings=[c]))
                    grants.append({'grant_id':'G-'+role,'obligation_id':'O-'+role,'method_ref':'COMPARATIVE_METHOD','max_research_attempts':1,'max_responsibility_attempts':len(roles)})
                m={'mission_id':'M2','instance_id':'I','intent_ref':criterion,'authorized_scope':{'target_refs':[target],'reports':True,'allow_derived_work':True,'obligation_ids':[o['definition']['obligation_id'] for o in obligations]},
                   'budget_grant_id':'BG2','obligations':obligations,'retry_grants':grants}
                store.commit_control(W.authorize_event(s,'I',m,{'budget_grant_id':'BG2','max_calls':len(roles)+6,'max_workers':2,'execution_policy':policy}));policy['max_workers']=2
                before=scheduler.plan(store.read_snapshot(),['I'],policy)
                self.assertNotIn('SYNTHESIS',[r['role'] for r in before['selected']])
                fake=FakeExecutor(RuntimeIntegration.no_result);result=run(store,instance_id='I',executor=fake,max_tasks=4,policy=policy)
                s=store.read_snapshot();actual=[s['tasks'][tid]['role'] for tid in result['tasks']]
                self.assertEqual(set(actual),set(roles));self.assertEqual(fake.calls,len(roles))
                if route=='COMPARATIVE':self.assertEqual(actual[-1],'SYNTHESIS')
                for t in s['tasks'].values():
                    packet=loads(store.read_blob(t['input_packet_ref']));self.assertFalse(any(r['kind']=='Assessment' for r in packet['records'].values()))
                self.assertEqual(len(s['records']),1);self.assertFalse(scheduler.plan(s,['I'],policy)['selected']);store.audit()
                from research_studio.engine import Engine
                from research_studio import reports,demo
                from tests.test_final_reports import actual_render
                engine=Engine();decision=engine.decide(store,'I','CONTINUE','The work dispositions preserve the open fixed target before any report.',snapshot_commit=store.read_snapshot()['knowledge_commit'])
                self.assertIsNone(decision['decision_basis']['report_ref'])
                delivered=reports.run(store,'I',executor=demo.executor(),policy=policy,renderer=actual_render)
                self.assertEqual(delivered['state'],'COMPLETED_CURRENT_REPORT')
                s=store.read_snapshot();self.assertEqual(len(s['records']),1)
                self.assertFalse({v['stage_id'] for v in s['visits'].values()}&{'P9','P10','P11','P12'})
                self.assertTrue(all(reports.profile_complete(p) for p in s['reports'][delivered['report_id']]['profiles'].values()));store.audit()


class FullWorkflowStories(unittest.TestCase):
    def test_n45_false_original_discovery_exact_adoption_independent_proof_and_reports(self):
        from tempfile import TemporaryDirectory
        from research_studio.engine import Engine
        from research_studio import demo,changes,assurance,reports
        from research_studio.runner import FakeExecutor,SimulatedCrash
        from research_studio.knowledge import locator
        from research_studio.util import loads,canonical,sha
        from tests.test_final_reports import actual_render
        false=b'For every real symmetric 2 by 2 matrix A, every eigenvalue of A is positive.'
        with TemporaryDirectory() as d:
            e=Engine();store=e.create(d+'/p',false,synthetic=True);t0=next(iter(store.read_snapshot()['records']));i0=e.new_workflow(store,'TRW',target_ref=t0)['instance_id']
            e.start_round(store,i0,'Resolve the original symmetric matrix claim without weakening it.',max_calls=16,max_workers=2,policy=demo.policy())
            def response(task,s):
                out=loads(demo.response(task,s))
                if task['role'].startswith('REPORT_'):return canonical(out)
                if task['independent']:
                    data=out['payload']['operations'][0]['data'];scope=task['required_assurance']['required_scope']
                    data['checked']=[{'ref':r['target_ref'],'locators':r['locators'],'aspect':a} for r in scope for a in r['aspects']];data['unchecked']=[];data['verdict']='SUPPORTED_WITHIN_SCOPE'
                elif task['role']=='RESEARCH':
                    target=task['target_refs'][0];negative=target==t0
                    body=('Take A = diag(-1, 2). This matrix is real and symmetric. The vector (1, 0) is an eigenvector with eigenvalue -1, which is not positive. Thus the original universal assertion is false.' if negative else
                        'Write A = [[a,b],[b,c]]. Positive definiteness tested on the two coordinate vectors implies a > 0 and c > 0. The nonzero vector (-b,a) gives a(ac-b^2) > 0, hence ac-b^2 > 0. The two eigenvalues are real because the discriminant is (a-c)^2+4b^2 >= 0. Their sum a+c is positive and their product ac-b^2 is positive, so both eigenvalues are positive. The same matrix A occurs throughout the argument.')
                    op={'op':'NEW','local_key':'argument','kind':'Argument','context_refs':[],'body':body,'data':{'conclusion_ref':target,'premise_bindings':[],
                        'steps':[{'step_id':'matrix','locator':locator(body),'premise_refs':[]}],'discharged_assumptions':[],'open_conditions':[],
                        'witness_bindings':[],'mode':'REFUTATION' if negative else 'PROOF','mode_payload':{}}}
                    ops=[op]
                    if negative:
                        ops.append({'op':'NEW','local_key':'example','kind':'Example','context_refs':[],'body':body,'data':{'target_refs':[t0],
                            'construction_locator':locator(body),'hypothesis_checks':[{'hypothesis_locator':s['records'][t0]['data']['statement_locator'],
                                'result':'SATISFIED','evidence_refs':[],'explanation_locator':locator(body)}],
                            'observations':[{'locator':locator(body),'evidence_refs':[]}],'scope':'ORIGINAL_TARGET','realization_argument_ref':'local:argument'}})
                    out['payload']['operations']=ops;out['payload']['work_outcome']='RESULT'
                    for effect in out['payload']['obligation_effects']:effect.update(work_disposition='ADDRESSED',resolution_proposal='CANDIDATE_RESPONSE',evidence_refs=['local:argument'],remaining_conditions=[])
                return canonical(out)
            fake=FakeExecutor(response);e.run_round(store,i0,executor=fake);s=store.read_snapshot()
            refutation=next(x for x in s['supports'].values() if x['statement_ref']==t0);negative=next(r for r,v in s['records'].items() if v['kind']=='Example')
            c0=next(c for o in s['obligations'].values() for c in o['definition']['consumer_bindings'] if c.get('stage_id')=='P9')
            self.assertEqual(assurance.evaluate(t0,c0,s)['claim_outcome'],'SCOPED_REFUTATION')
            self.assertEqual(reports.run(store,i0,executor=fake,policy=demo.policy(),renderer=actual_render)['state'],'COMPLETED_CURRENT_REPORT')
            brief=store.commit(changes.prepare_source_input(store.read_snapshot(),b'Keep real symmetric matrices as the background. Investigate sufficient hypotheses for positivity of both eigenvalues, retaining the negative original example.',purpose='PHENOMENON',blob_get=store.read_blob))['source_ref']
            fixture_scope=e.prepare_discovery_scope(store,{**{k:v for k,v in demo.discovery_scope().items() if k!='phenomenon'},'phenomenon_ref':brief})
            prepared=e.prepare_handoff(store,i0,'TRW_TO_TFDW',{'argument_refs':[refutation['argument_ref']],'example_refs':[negative],'source_refs':[brief],'discovery_scope':fixture_scope})
            records_before=deepcopy(store.read_snapshot()['records']);decision=e.decide(store,i0,'ADOPT_HANDOFF','Investigate precise replacement hypotheses.',snapshot_commit=store.read_snapshot()['knowledge_commit']);decision['discovery_brief_ref']=brief
            discovery=e.adopt_handoff(store,prepared['handoff_id'],decision)['instance_id'];self.assertEqual(store.read_snapshot()['records'],records_before)
            self.assertEqual(store.read_snapshot()['instances'][discovery]['status'],'PAUSED')
            e.start_round(store,discovery,'Preserve the original counterexample while formulating a new candidate.',max_calls=12,max_workers=2,policy=demo.policy())
            e.run_round(store,discovery,executor=fake);s=store.read_snapshot();candidate=next(c['statement_ref'] for c in s['candidates'].values() if c['instance_id']==discovery)
            learn=next(t for t in s['tasks'].values() if t['instance_id']==discovery and t['role']=='LEARN');self.assertIn(refutation['argument_ref'],{x['ref'] for x in learn['input_manifest']})
            self.assertFalse(any(x['statement_ref']==candidate for x in s['supports'].values()))
            self.assertEqual(reports.run(store,discovery,executor=fake,policy=demo.policy(),renderer=actual_render)['state'],'COMPLETED_CURRENT_REPORT')
            prepared=e.prepare_handoff(store,discovery,'TFDW_TO_TRW',{'candidate_refs':[candidate]});records_before=deepcopy(store.read_snapshot()['records'])
            decision=e.decide(store,discovery,'ADOPT','Adopt exactly the positive definite candidate, without borrowing proof authority.',snapshot_commit=store.read_snapshot()['knowledge_commit'],candidate_ref=candidate)
            adopted=e.adopt_handoff(store,prepared['handoff_id'],decision)['instance_id'];self.assertEqual(store.read_snapshot()['records'],records_before)
            e.start_round(store,adopted,'Prove this exact candidate independently.',max_calls=12,max_workers=2,policy=demo.policy())
            prepared=e.prepare(store,adopted)['prepared'][0]
            store.commit_control(W.event(store.read_snapshot(),'CANCEL_REQUEST',{'request_id':prepared['request_id'],'reason':'Cancel this unstarted lease only.'},instance_id=adopted))
            second=e.prepare(store,adopted)['prepared'][0]
            crashing=FakeExecutor(response,fault_at='AFTER_CAPTURE_RECEIPT_BEFORE_ADMISSION')
            with self.assertRaises(SimulatedCrash):crashing.execute(store,second['task_id'])
            e.pause(store,adopted,'Pause with candidate capture intact.')
            with self.assertRaises(PMRSError):execution.recover(store,second['request_id'])
            e.decide(store,adopted,'CONTINUE','Resume the same frozen scope and existing allowance.',snapshot_commit=store.read_snapshot()['knowledge_commit'])
            execution.recover(store,second['request_id']);e.run_round(store,adopted,executor=fake);s=store.read_snapshot()
            c1=next(c for o in s['obligations'].values() for c in o['definition']['consumer_bindings'] if c['instance_id']==adopted and c.get('stage_id')=='P9')
            self.assertEqual(assurance.evaluate(candidate,c1,s)['claim_outcome'],'SUPPORTED_ASSERTION')
            self.assertEqual(assurance.evaluate(t0,c0,s)['claim_outcome'],'SCOPED_REFUTATION');self.assertEqual(s['instances'][i0]['target_ref'],t0);self.assertEqual(s['instances'][adopted]['target_ref'],candidate)
            self.assertEqual(store.read_blob(s['records'][t0]['body_sha256']),false)
            self.assertEqual(reports.run(store,adopted,executor=fake,policy=demo.policy(),renderer=actual_render)['state'],'COMPLETED_CURRENT_REPORT')
            self.assertEqual(crashing.calls,1);self.assertEqual(fake.network_calls+fake.spawn_calls,0)
            self.assertEqual(execution.recover(store,second['request_id'])['state'],'EXACT_DUPLICATE');store.audit()


class DiscoveryFlow(unittest.TestCase):
    def test_n44_four_discovery_variants_feedback_unknown_and_formal_reports(self):
        from tempfile import TemporaryDirectory
        from research_studio.engine import Engine
        from research_studio import demo,reports
        from research_studio.runner import FakeExecutor
        from research_studio.knowledge import locator
        from research_studio.util import loads,canonical
        from tests.test_final_reports import actual_render
        for variant in ('ZERO','BIASED','TWO','NO_DISCRIMINATION'):
            with self.subTest(variant=variant),TemporaryDirectory() as d:
                e=Engine();store=e.create(d+'/p',b'Finite observations of symmetric matrices; positive observations may be biased. Negative and unknown evidence must remain visible.',phenomenon=True,synthetic=True)
                iid=e.new_workflow(store,'TFDW',discovery_scope=demo.discovery_scope('Keep the matrix background fixed and distinguish evidence from universal claims.'))['instance_id']
                e.start_round(store,iid,'Investigate formulations without padding candidate count.',max_calls=24,max_workers=2,policy=demo.policy())
                def proposal(key,kind,targets,criterion):
                    return {'local_key':key,'type':kind,'reason_code':None,'target_refs':targets,'criterion_body':criterion,'scope_context_refs':[],
                        'dependency_bindings':[],'consumer_binding_proposals':[],'effect_on_goal':'DISCOVERY_EVIDENCE','reason_refs':targets}
                def response(t,s):
                    if t['role'].startswith('REPORT_'):return demo.response(t,s)
                    out=loads(RuntimeIntegration.no_result(t,s));p=out['payload'];stage=t['stage_id']
                    if variant=='ZERO':return canonical(out)
                    if stage=='D1':p['new_obligation_proposals']=[proposal('formulate','FORMULATE',[],'Formulate precise matrix hypotheses and keep the original observational bias explicit.')]
                    elif stage=='D2':
                        earlier=[x for x in s['tasks'].values() if x['instance_id']==iid and x['stage_id']=='D2' and x['task_id']!=t['task_id']]
                        if not earlier:
                            out=loads(demo.response(t,s));p=out['payload'];p['operations']=[x for x in p['operations'] if x['kind']=='Statement'];targets=['local:candidate']
                            for effect in p['obligation_effects']:effect['evidence_refs']=['local:candidate']
                            if variant in {'TWO','NO_DISCRIMINATION'}:
                                text='For every real symmetric 2 by 2 matrix A, if A is positive semidefinite, then every eigenvalue of A is nonnegative.';loc=locator(text)
                                second=deepcopy(p['operations'][0]);second.update(local_key='candidate2',body=text);second['data'].update(statement_locator=loc,hypothesis_locators=[loc],conclusion_locators=[loc],quantifier_locators=[loc])
                                p['operations'].append(second);targets.append('local:candidate2')
                            p['new_obligation_proposals']=[proposal('calibrate','CALIBRATE',targets,'Calibrate this exact candidate frontier using positive, negative and untested cases. Finite success cannot prove a universal theorem.')]
                    elif stage=='D4':
                        out=loads(demo.response(t,s));p=out['payload'];p['new_obligation_proposals']=[proposal('learn','APPLICABILITY',t['target_refs'],'Revisit original matrix evidence because the available examples do not remove selection bias. Preserve unchecked applicability.')]
                    elif stage=='D3' and t['role']=='RESEARCH':
                        p['new_obligation_proposals']=[proposal('feedback','FORMULATE',t['target_refs'],'Reconsider the same exact formulations after the calibration attempt found no decisive general argument.')]
                        if variant in {'TWO','NO_DISCRIMINATION'}:p['new_obligation_proposals'].append(proposal('distinguish','DISCRIMINATE' if variant=='NO_DISCRIMINATION' else 'COMPARE',t['target_refs'],'Determine a supported implication or a distinguishing example. With no argument, retain UNKNOWN instead of claiming incomparability.'))
                    p['attempt_account']='The assigned finite exploration was performed. Positive examples do not remove bias, and no missing implication or untested range is silently certified.'
                    return canonical(out)
                fake=FakeExecutor(response);e.run_round(store,iid,executor=fake);s=store.read_snapshot();candidates=[c for c in s['candidates'].values() if c['instance_id']==iid]
                self.assertEqual(len(candidates),0 if variant=='ZERO' else 1 if variant=='BIASED' else 2);self.assertEqual(s['supports'],{})
                self.assertTrue(all(not c.get('comparison_refs') for c in candidates))
                stages=[t['stage_id'] for t in s['tasks'].values() if t['instance_id']==iid]
                if variant=='ZERO':self.assertEqual(stages,['D1'])
                else:
                    self.assertTrue({'D1','D2','D3','D4'}<=set(stages));self.assertEqual(stages.count('D2'),2)
                    review=next(r for r in s['records'].values() if r['kind']=='Assessment');self.assertEqual(review['data']['verdict'],'INCONCLUSIVE');self.assertTrue(review['data']['unchecked'])
                decision=e.decide(store,iid,'CONTINUE_DISCOVERY','Use the exact unknown frontier before requesting any report.',snapshot_commit=s['knowledge_commit'])
                self.assertIsNone(decision['decision_basis']['report_ref'])
                if variant=='BIASED':
                    def fail_report(t,s):
                        if t['role']!='REPORT_SEMANTIC':return demo.response(t,s)
                        p={'profile':t['report_context']['profile'],'verdict':'REVISE','uncheckable':[],
                           'findings':[{'code':'SOURCE_PROOF_ERROR','anchor':'Scope','severity':'BLOCKING','description':'The source evidence does not justify removing the explicitly retained bias.'}]}
                        out=loads(demo.response(t,s));out['payload']=p;return canonical(out)
                    blocked=reports.run(store,iid,executor=FakeExecutor(fail_report),policy=demo.policy(),renderer=actual_render);self.assertEqual(blocked['state'],'REPORT_BLOCKED')
                    e.decide(store,iid,'CONTINUE_DISCOVERY','The valid knowledge basis remains usable despite this report defect.',snapshot_commit=store.read_snapshot()['knowledge_commit'],report_ref=blocked['report_id'])
                    reports.revise(store,iid,'lecture','Describe the exact open evidence boundary honestly.')
                delivered=reports.run(store,iid,executor=demo.executor(),policy=demo.policy(),renderer=actual_render)
                self.assertEqual(delivered['state'],'COMPLETED_CURRENT_REPORT');entry=store.read_snapshot()['reports'][delivered['report_id']]
                self.assertTrue(all(reports.profile_complete(p) for p in entry['profiles'].values()))
                self.assertEqual(store.read_snapshot()['supports'],{});self.assertEqual(fake.network_calls+fake.spawn_calls,0);store.audit()

    def test_n30_chinese_original_two_selected_instances_readers_and_english_tasks(self):
        from tempfile import TemporaryDirectory
        from research_studio.engine import Engine
        from research_studio import demo,changes,views
        from research_studio.runner import FakeExecutor
        from research_studio.util import loads
        raw='每个实对称二阶矩阵的特征值是否都是正数？'.encode()
        with TemporaryDirectory() as d:
            e=Engine();store=e.create(d+'/p',raw,title='中文题目',synthetic=True);target=next(iter(store.read_snapshot()['records']))
            source=store.commit(changes.prepare_material_input(store.read_snapshot(),'原文补充：不要把例子当成普遍证明。'.encode(),media_type='text/plain',blob_get=store.read_blob))['source_ref']
            fixed=e.new_workflow(store,'TRW',target_ref=target)['instance_id'];discovery=e.new_workflow(store,'TFDW',discovery_scope=demo.discovery_scope('保持背景不变，研究合适的附加条件。'))['instance_id']
            with self.assertRaises(PMRSError) as cm:e.start_round(store,None,'缺少实例选择',max_calls=2,policy=demo.policy())
            self.assertEqual(cm.exception.code,'INSTANCE_SELECTOR_REQUIRED')
            fake=FakeExecutor(RuntimeIntegration.no_result);before=store._head();views.status(store.read_snapshot(),store);store.audit()
            self.assertEqual(store._head(),before);self.assertEqual(fake.calls,0)
            e.start_round(store,fixed,'请研究原命题，不能悄悄改变假设。',max_calls=2,max_workers=2,policy=demo.policy())
            e.start_round(store,discovery,'保留尚未检查的范围，不凑候选数。',max_calls=2,max_workers=2,policy=demo.policy())
            e.run_round(store,fixed,executor=fake);s=store.read_snapshot();self.assertEqual(fake.calls,2);self.assertEqual(len(s['missions']),2)
            self.assertEqual(store.read_blob(s['records'][target]['body_sha256']),raw)
            for task in s['tasks'].values():
                packet=loads(store.read_blob(task['input_packet_ref']));self.assertIn(source,{x['ref'] for x in task['input_manifest']})
                self.assertIn('Write new research and reports in English',store.read_blob(task['prompt_ref']).decode())
                capture=store.read_blob(s['requests'][task['request_id']]['capture_ref']).decode();self.assertNotRegex(capture,r'[\u3400-\u9fff]')
            self.assertEqual(s['instances'][fixed]['target_ref'],target);self.assertIsNone(s['instances'][discovery]['target_ref']);self.assertEqual(s['candidates'],{});store.audit()


class ClosureContracts(unittest.TestCase):
    def test_p6_gap_cannot_fulfill_a_reduction_visit(self):
        from tempfile import TemporaryDirectory
        from research_studio.runner import FakeExecutor,run
        with TemporaryDirectory() as d:
            store,policy=RuntimeIntegration().make_project(d+'/p',1,stage='P6',role='PLAN')
            run(store,instance_id='I',executor=FakeExecutor(RuntimeIntegration.no_result),max_tasks=1,policy=policy)
            s=store.read_snapshot();visit=next(iter(s['visits'].values()));bindings=visit['assigned_obligation_bindings']
            disposition={'visit_id':visit['visit_id'],'outcome':'FULFILLED_FOR_SCOPE','completed_work_bindings':bindings,'open_mathematical_bindings':[],
                'unperformed_bindings':[],'next_activity_proposal':'P7','reason_ref':store.blob(b'Only a gap was identified; there is no reduction argument.')}
            with self.assertRaises(PMRSError) as cm:store.commit_execution(execution.event('VISIT_DISPOSED',{'disposition':disposition}))
            self.assertEqual(cm.exception.code,'STAGE_PRODUCT_MISSING')
            disposition.update(outcome='INVESTIGATED_OPEN',open_mathematical_bindings=bindings,next_activity_proposal=None)
            store.commit_execution(execution.event('VISIT_DISPOSED',{'disposition':disposition}));self.assertEqual(store.read_snapshot()['supports'],{})


class PersistentInputKeys(unittest.TestCase):
    def test_structured_source_provenance_preserves_independent_source_isolation(self):
        from research_studio import context
        from research_studio.util import sha
        raw=b'Exact mathematical source, without a review conclusion.';h=sha(raw)
        provenance='SO-original'
        source={'source_id':'SO-input','blob_hash':h,'access_class':'SCIENTIFIC_SOURCE','provenance_refs':[provenance]}
        snapshot={'sources':{'SO-input':source},'records':{},'relations':[]}
        packet=context.build_packet(snapshot,[],lambda digest:raw,independent=True,required_source_refs=['SO-input'])
        self.assertEqual(packet['source_bodies'][h],raw)
        snapshot['sources']['SO-review']={'source_id':'SO-review','blob_hash':h,'access_class':'HISTORICAL_REVIEW','provenance_refs':[]}
        for parent in ('SO-review',{'source_ref':'SO-review'},{'arbitrary':'SO-review'}):
            source['provenance_refs']=[provenance,parent]
            with self.assertRaisesRegex(PMRSError,'FORBIDDEN_REVIEW_DERIVATIVE'):
                context.build_packet(snapshot,[],lambda digest:raw,independent=True,required_source_refs=['SO-input'])
        source['provenance_refs']=[provenance];source['access_class']='OPERATOR_PREPARATION'
        with self.assertRaisesRegex(PMRSError,'FORBIDDEN_REVIEW_DERIVATIVE'):
            context.build_packet(snapshot,[],lambda digest:raw,independent=True,required_source_refs=['SO-input'])

    def test_dependency_candidate_changes_dispatch_key_and_packet(self):
        s,c=configured(n=2);o=s['obligations']['O'];o['definition']['dependency_bindings']=[{'dependency_id':'D','threshold':'ARTIFACT_AVAILABLE','binding_ref':'UP','scope':[]}]
        s['records']['KR-a']={'kind':'Argument','data':{}};s['records']['KR-b']={'kind':'Argument','data':{'different':True}}
        s['obligations']['UP']=O.make('UP','ESTABLISH',['KR-target'],'upstream');s['obligations']['UP']['projection']['evidence_refs']=['KR-a']
        before=O.keys(s,o,c,'RESEARCH','METHOD');s['obligations']['UP']['projection']['evidence_refs']=['KR-b'];after=O.keys(s,o,c,'RESEARCH','METHOD')
        self.assertNotEqual(before['input_fingerprint'],after['input_fingerprint']);self.assertEqual(before['purpose_key'],after['purpose_key'])
        self.assertEqual(O.dependency_inputs(s,o['definition']),['KR-b','KR-target'])

    def test_blocker_wording_target_order_and_grant_wrapper_do_not_reset(self):
        s,c=configured(n=2);s['records']['KR-other']={'kind':'Statement','data':{}};o=s['obligations']['O'];o['definition']['target_refs'].append('KR-other')
        first=O.keys(s,o,c,'RESEARCH','METHOD');o['definition']['target_refs'].reverse();o['projection']['blocker_refs']=['B']
        s['blockers']={'B':{'explanation':'Different prose without a scientific change.'}};c['retry_grant_id']='renamed'
        self.assertEqual(first,O.keys(s,o,c,'RESEARCH','METHOD'))

    def test_actual_supplement_source_fulfills_hash_predicate_and_is_frozen(self):
        from tempfile import TemporaryDirectory
        from research_studio.engine import Engine
        from research_studio import demo,changes,tasks
        from research_studio.util import sha,loads
        with TemporaryDirectory() as d:
            e=Engine();store=e.create(d+'/p',demo.ARITHMETIC,synthetic=True);target=next(iter(store.read_snapshot()['records']))
            raw=b'This is the exact supplemental source required by the scoped investigation.';predicate={'kind':'MATERIAL_VERIFIED','source_id':'SO-required','coverage':'FULL_DOCUMENT','sha256':sha(raw)}
            self.assertFalse(O.condition_met(predicate,store.read_snapshot()))
            before=len(store.read_snapshot()['records']);store.commit(changes.prepare_material_input(store.read_snapshot(),raw,source_id='SO-required',media_type='text/plain',blob_get=store.read_blob))
            self.assertTrue(O.condition_met(predicate,store.read_snapshot()));self.assertEqual(len(store.read_snapshot()['records']),before)
            iid=e.new_workflow(store,'TRW',target_ref=target)['instance_id'];e.start_round(store,iid,'Use the supplied exact original.',max_calls=1,policy=demo.policy())
            tid=e.prepare(store,iid)['prepared'][0]['task_id'];task=tasks.load(store,tid);packet=loads(store.read_blob(task['input_packet_ref']))
            import base64
            self.assertEqual(base64.b64decode(packet['source_bytes_base64'][sha(raw)]),raw);self.assertIn('SO-required',{x['ref'] for x in task['input_manifest']})

    def test_reauthorizing_same_intent_does_not_refill_default_sample(self):
        from tempfile import TemporaryDirectory
        from research_studio.engine import Engine
        from research_studio import demo
        from research_studio.runner import FakeExecutor
        with TemporaryDirectory() as d:
            e=Engine();store=e.create(d+'/p',demo.ARITHMETIC,synthetic=True);target=next(iter(store.read_snapshot()['records']));iid=e.new_workflow(store,'TRW',target_ref=target)['instance_id']
            fake=FakeExecutor(RuntimeIntegration.no_result)
            e.start_round(store,iid,'One persistent responsibility.',max_calls=2,policy=demo.policy());e.run_round(store,iid,executor=fake)
            e.start_round(store,iid,'One persistent responsibility.',max_calls=2,policy=demo.policy());e.run_round(store,iid,executor=fake)
            self.assertEqual(fake.calls,1);self.assertEqual(len(store.read_snapshot()['requests']),1)
            e.start_round(store,iid,'One persistent responsibility.',max_calls=2,max_research_attempts=2,policy=demo.policy());e.run_round(store,iid,executor=fake)
            self.assertEqual(fake.calls,2);self.assertEqual(scheduler.project_remaining(store.read_snapshot()),4)
            self.assertEqual(len({r['attempt_key'] for r in store.read_snapshot()['requests'].values()}),2);self.assertEqual(len({r['responsibility_key'] for r in store.read_snapshot()['requests'].values()}),1);store.audit()


class RecoveryCompleteness(unittest.TestCase):
    def test_profile_accepted_before_pair_crash_reuses_first_profile(self):
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from research_studio.engine import Engine
        from research_studio import demo,reports
        from research_studio.runner import SimulatedCrash
        from research_studio.store import Store
        from tests.test_final_reports import actual_render
        with TemporaryDirectory() as d:
            e=Engine();store=e.create(d+'/p',demo.ARITHMETIC,synthetic=True);target=next(iter(store.read_snapshot()['records']));iid=e.new_workflow(store,'TRW',target_ref=target)['instance_id']
            e.authorize(store,iid,{'intent':'Deliver both report profiles under one finite authorization.','authorized_scope':{'target_refs':[target],'reports':True},'obligations':[]},
                {'max_calls':6,'max_workers':1,'execution_policy':demo.policy()})
            original=reports.prepare
            def stop_after_lecture(*a,**kw):
                result=original(*a,**kw)
                if result.get('profile')=='minimal':raise SimulatedCrash('AFTER_PROFILE_ACCEPTANCE_BEFORE_PAIR')
                return result
            first=demo.executor()
            with patch.object(reports,'prepare',side_effect=stop_after_lecture):
                with self.assertRaises(SimulatedCrash):reports.run(store,iid,executor=first,policy=demo.policy(),renderer=actual_render)
            s=store.read_snapshot();rid=s['active_reports'][iid];lecture=deepcopy(s['reports'][rid]['profiles']['lecture'])
            self.assertTrue(reports.profile_complete(lecture));self.assertFalse(s['reports'][rid]['profiles']['minimal']['body_sha256']);self.assertEqual(first.calls,3)
            reopened=Store(store.root);second=demo.executor();done=reports.run(reopened,iid,executor=second,policy=demo.policy(),renderer=actual_render)
            self.assertEqual(done['state'],'COMPLETED_CURRENT_REPORT');self.assertEqual(second.calls,3);self.assertEqual(reopened.read_snapshot()['reports'][rid]['profiles']['lecture'],lecture)
            self.assertEqual(scheduler.project_remaining(reopened.read_snapshot()),0);reopened.audit()
