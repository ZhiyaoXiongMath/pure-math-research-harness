"""Ordinary user entry, actual native capture/admission, controlled transport only."""
import unittest
from tempfile import TemporaryDirectory
from research_studio.engine import Engine
from research_studio import demo, survey, tasks, changes, autoflow
from research_studio.runner import FakeExecutor
from research_studio.knowledge import locator
from research_studio.util import canonical, loads
from tests.test_research_plans import no_result


def response(task,snapshot):
    if task['stage_id'].startswith('S'):return survey.demo_response(task,snapshot)
    raw=loads(no_result(task,snapshot));p=raw['payload']
    if task['stage_id'] in {'P1','P2','P3'}:
        body={'P1':'Synthetic conventions: n is an arbitrary integer, addition is integer addition and zero is its additive identity.',
              'P2':'Synthetic backward implication: deriving the additive identity for arbitrary n suffices for the original universally quantified target; no reversal is assumed.',
              'P3':'Synthetic route: apply the additive identity axiom directly for arbitrary n; test that every step preserves the original integer domain.'}[task['stage_id']]
        loc=locator(body)
        if task['stage_id']=='P1':
            op={'op':'NEW','local_key':'prerequisite','kind':'Context','context_refs':[],'body':body,
                'data':{'definitions':[{'key':'integer_identity','locator':loc}],'objects':[],'assumptions':[],
                        'quantifiers':[],'conventions':[],'parent_context_refs':[]}}
        else:
            op={'op':'NEW','local_key':'prerequisite','kind':'Statement','context_refs':[],'body':body,
                'data':{'statement_locator':loc,'scope_context_refs':[],'hypothesis_locators':[loc],
                        'conclusion_locators':[loc],'quantifier_locators':[loc],'form':'CONJECTURE',
                        'representation':'AUTHORED','source_binding':None}}
        p['operations']=[op];p['work_outcome']='RESULT'
        for effect in p['obligation_effects']:
            effect.update(work_disposition='ADDRESSED',resolution_proposal='CANDIDATE_RESPONSE',
                          evidence_refs=['local:prerequisite'],remaining_conditions=[])
    return canonical(raw)


def gap(raw,task,stage,role,kind,criterion):
    value=loads(raw)
    value['payload']['new_obligation_proposals'].append({'local_key':'gap','type':kind,'reason_code':None,
        'target_refs':task['target_refs'],'criterion_body':criterion,'scope_context_refs':[],
        'dependency_bindings':[],'consumer_binding_proposals':[],
        'effect_on_goal':'ACTIVITY:'+stage+':'+role,'reason_refs':task['target_refs']})
    return canonical(value)


class AutomaticRounds(unittest.TestCase):
    def trw(self,path):
        e=Engine();store=e.create(path,demo.ARITHMETIC,synthetic=True)
        iid=e.new_workflow(store,'TRW',target_ref=next(iter(store.read_snapshot()['records'])))['instance_id']
        return e,store,iid

    def test_default_missing_prerequisites_then_actual_work_and_honest_delivery(self):
        with TemporaryDirectory() as d:
            e,s,i=self.trw(d+'/p');started=e.start_round(s,i,'Investigate the exact original integer identity.',max_calls=8,policy=demo.policy())
            self.assertEqual([b['stage_id'] for b in started['bindings']],['P1'])
            fake=FakeExecutor(response);result=e.run_round(s,i,executor=fake)
            state=s.read_snapshot();stages=[t['stage_id'] for t in state['tasks'].values()]
            self.assertCountEqual(stages,['P1','P2','P3','P4','P11'])
            self.assertTrue(all(r['acceptance_state']=='ACCEPTED' for r in state['requests'].values()))
            self.assertEqual(fake.calls,5);self.assertEqual(fake.network_calls,0)
            self.assertEqual(len(state['missions']),1);self.assertEqual(len(state['budget_grants']),1)
            self.assertFalse(state['reports']);self.assertTrue(autoflow.status(state,i)['complete'])
            self.assertIn(result['round_result']['state'],{'READY_FOR_DECISION','BUDGET_EXHAUSTED'})
            s.audit()

    def test_existing_actual_prerequisites_reused_without_resetting_attempt_budget(self):
        with TemporaryDirectory() as d:
            e,s,i=self.trw(d+'/p');e.start_round(s,i,'First bounded attempt.',max_calls=8,policy=demo.policy())
            e.run_round(s,i,executor=FakeExecutor(response));before=len(s.read_snapshot()['tasks'])
            started=e.start_round(s,i,'Reuse valid background and routes in the same exact scope.',max_calls=8,policy=demo.policy())
            self.assertEqual(started['autoflow']['prerequisites']['missing'],[])
            self.assertEqual(set(started['autoflow']['prerequisites']['reused']),{'P1','P2','P3'})
            self.assertEqual([b['stage_id'] for b in started['bindings']],['P4'])
            fake=FakeExecutor(response);e.run_round(s,i,executor=fake)
            self.assertEqual(fake.calls,0);self.assertEqual(len(s.read_snapshot()['tasks']),before)
            s.audit()

    def test_no_result_is_not_prerequisite_success_and_budget_is_not_extended(self):
        for allowance,callback in [(8,no_result),(2,response)]:
            with self.subTest(allowance=allowance), TemporaryDirectory() as d:
                e,s,i=self.trw(d+'/p');e.start_round(s,i,'Respect missing prerequisite evidence.',max_calls=allowance,policy=demo.policy())
                fake=FakeExecutor(callback);result=e.run_round(s,i,executor=fake);state=s.read_snapshot()
                self.assertEqual(fake.calls,1 if allowance==8 else 2)
                self.assertTrue(autoflow.status(state,i)['missing'])
                self.assertNotIn('P4',[t['stage_id'] for t in state['tasks'].values()])
                self.assertEqual(len(state['budget_grants']),1)
                if allowance==2:self.assertEqual(result['round_result']['state'],'BUDGET_EXHAUSTED')
                self.assertFalse(state['reports'])

    def test_accepted_specific_gap_automatically_returns_in_original_mission(self):
        with TemporaryDirectory() as d:
            e,s,i=self.trw(d+'/p');e.start_round(s,i,'Follow only concrete mathematical gaps.',max_calls=12,policy=demo.policy())
            seen=[]
            def controlled(task,snapshot):
                seen.append(task['stage_id']);raw=response(task,snapshot)
                if task['stage_id']=='P4':return gap(raw,task,'P6','PLAN','REDUCE','Reduce the exact unresolved additive-identity interface to a sufficient axiom-level lemma.')
                if task['stage_id']=='P6' and seen.count('P6')==1:return gap(raw,task,'P8','RESEARCH','ESTABLISH','Carry out the first actual derivation for the reduced axiom-level identity interface.')
                if task['stage_id']=='P8' and seen.count('P8')==1:return gap(raw,task,'P6','PLAN','REDUCE','Repair the newly located domain mismatch in the reduction without weakening the original integer quantifier.')
                return raw
            fake=FakeExecutor(controlled);e.run_round(s,i,executor=fake);state=s.read_snapshot()
            self.assertEqual(seen[:4],['P1','P2','P3','P4'])
            self.assertEqual(seen.count('P6'),2);self.assertIn('P8',seen);self.assertEqual(seen[-1],'P11')
            self.assertEqual({r['mission_id'] for r in state['requests'].values()},set(state['missions']))
            self.assertEqual(len(state['missions']),1);self.assertLessEqual(fake.calls,12)
            s.audit()

    def test_survey_knowledge_only_automatically_reads_organizes_reviews_and_freezes(self):
        with TemporaryDirectory() as d:
            e=Engine();s=e.create_survey(d+'/p',survey.demo_scope(),synthetic=True);i=next(iter(s.read_snapshot()['instances']))
            source=s.commit(changes.prepare_material_input(s.read_snapshot(),survey.TEACHING_TEXT.encode(),
                title='Explicit synthetic teaching material',media_type='text/plain',blob_get=s.read_blob))['source_ref']
            e.start_round(s,i,'Complete the selected finite sum knowledge scope.',source_refs=[source],max_calls=4,policy=demo.policy())
            fake=FakeExecutor(response);e.run_round(s,i,executor=fake);state=s.read_snapshot()
            self.assertCountEqual([t['stage_id'] for t in state['tasks'].values()],['S2','S3','S4'])
            self.assertEqual(survey.readiness(state,i)['status'],'SYNTHETIC_READY');self.assertTrue(state['survey_snapshots'])
            self.assertEqual(len(state['missions']),1);self.assertFalse(state['reports']);self.assertFalse(state['survey_output_plans'])
            self.assertEqual(fake.calls,3);self.assertTrue(autoflow.status(state,i)['complete'])
            s.audit()

    def test_transfer_gap_creates_independent_direct_and_complete_join_automatically(self):
        with TemporaryDirectory() as d:
            e,s,i=self.trw(d+'/p');e.start_round(s,i,'Investigate a concrete transfer obstacle.',max_calls=12,max_workers=2,policy=demo.policy())
            captures=[]
            def controlled(task,snapshot):
                captures.append(task);raw=response(task,snapshot)
                if task['stage_id']=='P4':return gap(raw,task,'P7','LEARN','APPLICABILITY','Test whether a named additive framework transfers to the fixed identity obstacle with its precise hypotheses.')
                if task['stage_id']=='P7' and task['role']=='SYNTHESIS':
                    return gap(raw,task,'P8','RESEARCH','ESTABLISH','Attempt the precise remaining compatibility condition identified by both actually attempted routes.')
                return raw
            fake=FakeExecutor(controlled);e.run_round(s,i,executor=fake);state=s.read_snapshot()
            p7=[t for t in captures if t['stage_id']=='P7'];self.assertCountEqual([t['role'] for t in p7],['LEARN','DIRECT','SYNTHESIS'])
            join=next(t for t in p7 if t['role']=='SYNTHESIS')
            selected=join['entry_basis']['synthesis_branches'];self.assertEqual(len(selected),2)
            prompt=s.read_blob(join['prompt_ref']).decode();self.assertIn('Synthetic actual attempt',prompt)
            self.assertIn('P8',[t['stage_id'] for t in captures]);self.assertEqual(len(state['missions']),1)
            self.assertLessEqual(fake.calls,12);s.audit()

    def test_discovery_default_frontier_waits_for_human_selection_and_zero_is_valid(self):
        for produce in (False,True):
            with self.subTest(produce=produce), TemporaryDirectory() as d:
                e=Engine();s=e.create(d+'/p',b'Synthetic matrix phenomenon.',phenomenon=True,synthetic=True)
                i=e.new_workflow(s,'TFDW',discovery_scope={'phenomenon':'Finite positive definite matrix observations.',
                    'immutable_background':'Real symmetric two by two matrices.','allowed_axes':'Compare the exact eigenvalue hypotheses.'})['instance_id']
                e.start_round(s,i,'Investigate the selected frontier within the fixed discovery axes.',max_calls=5,policy=demo.policy())
                def controlled(task,snapshot):
                    return demo.response(task,snapshot) if produce and task['stage_id']=='D1' or task['stage_id']=='D4' else no_result(task,snapshot)
                fake=FakeExecutor(controlled);e.run_round(s,i,executor=fake);state=s.read_snapshot()
                self.assertCountEqual([t['stage_id'] for t in state['tasks'].values()],['D1','D3','D4'] if produce else ['D1'])
                self.assertTrue(autoflow.status(state,i)['waiting_human']);self.assertEqual(len(state['instances']),1)
                self.assertFalse(state['reports']);self.assertFalse(state.get('handoff_adoptions'))
                self.assertEqual(len(state['missions']),1);s.audit()

    def test_survey_missing_material_waits_for_selection_without_network_or_manuscript(self):
        with TemporaryDirectory() as d:
            e=Engine();s=e.create_survey(d+'/p',survey.demo_scope(),synthetic=True);i=next(iter(s.read_snapshot()['instances']))
            e.start_round(s,i,'Survey only the exact selected scope.',max_calls=4,source_refs=[],policy=demo.policy())
            fake=FakeExecutor(response);e.run_round(s,i,executor=fake);state=s.read_snapshot()
            self.assertEqual(fake.calls,1);self.assertEqual(fake.network_calls,0)
            self.assertEqual(autoflow.status(state,i)['waiting_human'],['SOURCE_SELECTION'])
            self.assertTrue(state['survey_search_plans']);self.assertFalse(state['survey_retrievals'])
            self.assertFalse(state['reports']);self.assertFalse(state['survey_snapshots'])

    def test_teaching_default_uses_real_prerequisite_records_and_keeps_review_inconclusive(self):
        with TemporaryDirectory() as d:
            e,s,i=self.trw(d+'/p');e.start_round(s,i,'Run only the synthetic integer-identity teaching example.',max_calls=8,policy=demo.policy())
            fake=demo.executor();e.run_round(s,i,executor=fake);state=s.read_snapshot()
            self.assertCountEqual([t['stage_id'] for t in state['tasks'].values()],['P1','P2','P3','P4','P9','P9','P11'])
            reviews=[r for r in state['records'].values() if r['kind']=='Assessment']
            self.assertEqual(len(reviews),2);self.assertTrue(all(r['data']['verdict']=='INCONCLUSIVE' for r in reviews))
            self.assertEqual(fake.calls,7);self.assertEqual(len(state['missions']),1);s.audit()

    def test_source_status_change_invalidates_prerequisite_reuse_through_native_event(self):
        with TemporaryDirectory() as d:
            e,s,i=self.trw(d+'/p')
            source=s.commit(changes.prepare_material_input(s.read_snapshot(),b'Synthetic additive conventions version A.',
                title='Synthetic selected conventions',media_type='text/plain',blob_get=s.read_blob))['source_ref']
            e.start_round(s,i,'Read the selected conventions and investigate.',source_refs=[source],max_calls=8,policy=demo.policy())
            e.run_round(s,i,executor=FakeExecutor(response))
            self.assertEqual(autoflow.status(s.read_snapshot(),i)['prerequisites']['missing'],[])
            si=e.new_workflow(s,'SURVEY',survey_scope=survey.demo_scope())['instance_id']
            s.commit_survey(survey.event(s.read_snapshot(),si,'SOURCE_STATUS_CHANGED',{'source_ref':source,
                'withdrawn':True,'version_conflict':False,'reason':'Synthetic authoritative source withdrawal; prior prerequisite reuse must be invalidated.'}))
            self.assertEqual(autoflow.status(s.read_snapshot(),i)['prerequisites']['missing'],['P1','P2','P3'])
            before=len(s.read_snapshot()['tasks'])
            e.start_round(s,i,'Recheck the now withdrawn conventions.',source_refs=[source],max_calls=8,policy=demo.policy())
            fake=FakeExecutor(response);e.run_round(s,i,executor=fake)
            self.assertEqual(fake.calls,0);self.assertEqual(len(s.read_snapshot()['tasks']),before)
            s.audit()

    def test_new_global_assembly_triggers_actual_independent_p12_without_checklist_calls(self):
        with TemporaryDirectory() as d:
            e,s,i=self.trw(d+'/p');e.start_round(s,i,'Inspect any genuinely new global assembly independently.',max_calls=12,policy=demo.policy())
            captured=[];made_global=False
            def controlled(task,snapshot):
                nonlocal made_global
                captured.append(task)
                if task['stage_id']=='P11' and not made_global:
                    made_global=True
                    out=loads(response(task,snapshot));p=out['payload']
                    body='Synthetic global assembly: for arbitrary integer n, the additive identity axiom gives n + 0 = n. This artifact only tests independent followup routing.'
                    p['operations']=[{'op':'NEW','local_key':'global','kind':'Argument','context_refs':[],'body':body,
                        'data':{'conclusion_ref':task['target_refs'][0],'premise_bindings':[],
                            'steps':[{'step_id':'identity','locator':locator(body),'premise_refs':[]}],
                            'discharged_assumptions':[],'open_conditions':[],'witness_bindings':[],'mode':'PROOF','mode_payload':{}}}]
                    p['work_outcome']='RESULT'
                    for effect in p['obligation_effects']:effect.update(work_disposition='ADDRESSED',resolution_proposal='CANDIDATE_RESPONSE',evidence_refs=['local:global'])
                    return canonical(out)
                return demo.response(task,snapshot) if task['stage_id']=='P9' else response(task,snapshot)
            fake=FakeExecutor(controlled);e.run_round(s,i,executor=fake);state=s.read_snapshot()
            reviews=[t for t in captured if t['stage_id']=='P12'];self.assertEqual(len(reviews),1)
            self.assertTrue(reviews[0]['independent']);self.assertTrue(any(x['kind']=='record' and state['records'][x['ref']]['kind']=='Argument' for x in reviews[0]['input_manifest']))
            self.assertFalse(any(x['kind']=='record' and state['records'][x['ref']]['kind']=='Assessment' for x in reviews[0]['input_manifest']))
            self.assertEqual(len(state['missions']),1);self.assertLessEqual(fake.calls,12);s.audit()

    def test_unassignable_accepted_gap_is_disclosed_instead_of_complete(self):
        with TemporaryDirectory() as d:
            e,s,i=self.trw(d+'/p');e.start_round(s,i,'Keep any unscoped review gap visible.',max_calls=8,policy=demo.policy())
            def controlled(task,snapshot):
                raw=response(task,snapshot)
                if task['stage_id']=='P4':return gap(raw,task,'P9','PROOF','VERIFY','Review an unresolved local proof obligation whose exact qualified support scope has not yet been established.')
                return raw
            fake=FakeExecutor(controlled);result=e.run_round(s,i,executor=fake)
            auto=autoflow.status(s.read_snapshot(),i)
            self.assertFalse(auto['complete']);self.assertEqual(auto['unassigned'][0]['type'],'VERIFY')
            self.assertIn('UNASSIGNED_SCIENTIFIC_GAP',auto['missing']);self.assertEqual(fake.calls,4)
            self.assertEqual(result['round_result']['state'],'HUMAN_INPUT_REQUIRED');s.audit()

    def corrected_pending_prerequisite(self,path,*,legacy_dependency=False):
        from unittest.mock import patch
        from research_studio import obligations as O, corrections
        e,s,i=self.trw(path)
        e.start_round(s,i,'Synthetic ordinary start followed by an exact prerequisite correction.',max_calls=2,policy=demo.policy())
        original=demo.executor();first=e.run_round(s,i,executor=original);before=s.read_snapshot()
        self.assertEqual(first['round_result']['state'],'BUDGET_EXHAUSTED');self.assertEqual(original.calls,2)
        prior_tasks={tid:canonical(t) for tid,t in before['tasks'].items()}
        captures={rid:r['capture_ref'] for rid,r in before['requests'].items()}
        old_o,old_c=next((o,c) for o in before['obligations'].values() for c in o['definition']['consumer_bindings'] if c['stage_id']=='P3')
        old_bid=old_c['binding_id'];old_oid=old_o['definition']['obligation_id'];mid=before['instances'][i]['current_mission_id']
        correction=e.request_correction(s,i,old_bid,'Keep the original universal integer domain explicit in the executable route.',
            'Provide a route preserving the original quantifier and its actual first mathematical attempt.')
        self.assertEqual(s.read_snapshot()['instances'][i]['status'],'PAUSED')
        self.assertEqual(s.read_snapshot()['budget_grants'],before['budget_grants'])
        e.extend_budget(s,i,5,'Exactly five additional synthetic calls for correction and its necessary downstream research.')
        decision=e.decide(s,i,'CONTINUE','Resume the same corrected round under the explicitly extended finite budget.',snapshot_commit=s.read_snapshot()['knowledge_commit'])
        e.resume(s,i,decision)
        seen=[]
        def controlled(task,snapshot):
            seen.append(task);raw=loads(demo.response(task,snapshot))
            if task.get('entry_basis',{}).get('human_correction'):
                op=raw['payload']['operations'][0]
                op['body']+=' Corrected-route sentinel: the quantified integer domain is retained.'
                loc=locator(op['body']);op['data'].update(statement_locator=loc,hypothesis_locators=[loc],conclusion_locators=[loc],quantifier_locators=[loc])
                raw['payload']['attempt_account']='Actual synthetic corrected-route account: the quantified integer domain is retained.'
            return canonical(raw)
        fake=FakeExecutor(controlled)
        frozen_p4=None
        if legacy_dependency:
            # Reproduce the exact prior selector through ordinary start/continue:
            # native P4 gets every P1-P3 binding, including the retired original.
            # Disable only the newly introduced replacement resolver until that
            # existing, unfrozen native P4 has demonstrably blocked.
            with patch('research_studio.autoflow._prerequisite_bindings',lambda rows,current:[(o,c) for o,c in rows if c['stage_id'] in autoflow.PREREQUISITES]), \
                 patch('research_studio.corrections.resolve_dependency',lambda snapshot,dep:dep):
                blocked=e.run_round(s,i,executor=fake)
            self.assertEqual(blocked['round_result']['state'],'WAITING_DEPENDENCY')
            self.assertFalse(any(t['stage_id']=='P4' for t in s.read_snapshot()['tasks'].values()))
            p4=next(o for o in s.read_snapshot()['obligations'].values() if any(c['stage_id']=='P4' for c in o['definition']['consumer_bindings']))
            frozen_p4=canonical(p4['definition']);self.assertEqual(len(p4['definition']['dependency_bindings']),4)
        result=e.run_round(s,i,executor=fake);state=s.read_snapshot()
        self.assertEqual(fake.calls,5);self.assertEqual(len(state['requests']),7)
        self.assertEqual(state['instances'][i]['current_mission_id'],mid);self.assertEqual(len(state['missions']),1)
        self.assertIn(old_bid,state['retired_consumers']);self.assertNotIn(old_bid,state['obligations'][old_oid]['projection']['consumer_resolutions'])
        self.assertFalse(any(any(b['binding_id']==old_bid for b in t['obligation_bindings']) for t in state['tasks'].values()))
        for tid,raw in prior_tasks.items():self.assertEqual(canonical(state['tasks'][tid]),raw)
        for rid,digest in captures.items():self.assertEqual(state['requests'][rid]['capture_ref'],digest)
        p4=next(t for t in seen if t['stage_id']=='P4');prompt=s.read_blob(p4['prompt_ref']).decode()
        self.assertIn('Actual synthetic corrected-route account',prompt)
        records=[state['records'][x['ref']] for x in p4['input_manifest'] if x['kind']=='record']
        self.assertTrue(any('Corrected-route sentinel' in s.read_blob(r['body_sha256']).decode() for r in records))
        duty=state['obligations'][p4['obligation_bindings'][0]['obligation_id']]
        self.assertTrue(all(O.dependency_met(state,d) for d in duty['definition']['dependency_bindings']))
        if frozen_p4 is not None:self.assertEqual(canonical(duty['definition']),frozen_p4)
        else:
            self.assertEqual(len(duty['definition']['dependency_bindings']),3)
            self.assertNotIn(old_bid,{d['binding_id'] for d in duty['definition']['dependency_bindings']})
        self.assertIn(correction['binding_id'],{d['binding_id'] for d in duty['definition']['dependency_bindings']})
        self.assertIn(result['round_result']['state'],{'READY_FOR_DECISION','BUDGET_EXHAUSTED'})
        s.audit()

    def test_normal_budget_stop_corrected_p3_continues_with_exact_replacement_dependency(self):
        with TemporaryDirectory() as d:self.corrected_pending_prerequisite(d+'/p')

    def test_existing_unfrozen_p4_with_retired_original_dependency_recovers_natively(self):
        with TemporaryDirectory() as d:self.corrected_pending_prerequisite(d+'/p',legacy_dependency=True)
