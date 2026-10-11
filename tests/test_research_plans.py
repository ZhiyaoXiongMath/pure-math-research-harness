"""Synthetic native evidence for scientific duties and finite shared plans."""
import json
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

from research_studio import demo, tasks, scheduler, execution, obligations as O, changes, survey, workflow_instances as W
from research_studio.engine import Engine
from research_studio.runner import FakeExecutor
from research_studio.util import canonical, loads, PMRSError
from research_studio.research_prompts import DUTIES
from research_studio.workflows import registry


def no_result(task,snapshot):
    value=loads(demo.response(task,snapshot));payload=value['payload']
    if value['payload_kind']=='SURVEY_RESULT':payload=payload['knowledge_change']
    payload['operations']=[];payload['new_obligation_proposals']=[];payload['work_outcome']='NO_RESULT'
    payload['attempt_account']='Synthetic actual attempt: inspected the exact assigned hypotheses and found the remaining interface unresolved; no mathematical success is certified.'
    for effect in payload['obligation_effects']:
        effect.update(work_disposition='NO_RESULT',resolution_proposal='UNRESOLVED',evidence_refs=[],remaining_conditions=['The full mathematical responsibility remains open.'])
    return canonical(value)


class ScientificPlans(unittest.TestCase):
    def trh(self,path):
        engine=Engine();store=engine.create(path,demo.ARITHMETIC,synthetic=True)
        target=next(iter(store.read_snapshot()['records']))
        iid=engine.new_workflow(store,'TRH',target_ref=target)['instance_id']
        return engine,store,iid,target

    def dispatch_one(self,store,iid,key=None,response=no_result):
        p=scheduler.plan(store.read_snapshot(),[iid],{'max_workers':store.read_snapshot()['max_workers']})
        if key is not None:p['selected']=[r for r in p['selected'] if r['consumer']['entry_basis']['research_plan']['branch_key']==key]
        self.assertTrue(p['selected'],p['waits']);p['selected']=p['selected'][:1]
        # Freeze the selected native plan row directly: it remains bound to the
        # same authorization, request budget and dependency gate.
        result=scheduler.commit_dispatch(store,p,policy={**demo.policy(),'max_workers':store.read_snapshot()['max_workers']})
        row=result['prepared'][0];FakeExecutor(response).execute(store,row['task_id'])
        return tasks.load(store,row['task_id'])

    def test_t1_all_29_contracts_and_actual_stage_specific_tasks(self):
        self.assertEqual(set(DUTIES),set(registry.definition()['stages']))
        self.assertEqual(len(DUTIES),29)
        for sid,row in registry.definition()['stages'].items():
            with self.subTest(stage=sid):
                self.assertFalse(row['exit_rules']['automatic_next'])
                self.assertTrue(row['input_binding_rule_ids'] and row['output_contract_ids'] and row['completion_rule_ids'])
                for role in row['roles']:
                    prompt=registry.prompt(sid,role['role'],'Investigate exactly the specified responsibility.')
                    self.assertEqual(prompt['stage_spec_digest'],row['digest'])
                    self.assertEqual(prompt['sections']['SCIENTIFIC_INPUT_REQUIREMENTS'],DUTIES[sid][0])
                    self.assertIn(DUTIES[sid][1],prompt['sections']['SCIENTIFIC_WORK'])
                    self.assertIn(DUTIES[sid][2],prompt['sections']['RESULT_AND_DOWNSTREAM_DUTY'])
        with TemporaryDirectory() as d:
            e,store,iid,target=self.trh(d+'/p')
            for sid,role in [('P1','PLAN'),('P2','PLAN'),('P3','PLAN'),('P5','SYNTHESIS'),('P6','PLAN'),('P8','RESEARCH'),('P10','SYNTHESIS'),('P11','SYNTHESIS'),('P12','INDEPENDENT')]:
                result=e.start_round(store,iid,'Synthetic exact '+sid+' scientific responsibility.',stage=sid,role=role,max_calls=1,policy=demo.policy())
                self.assertEqual(result['model_calls'],0)
                task=self.dispatch_one(store,iid,response=no_result)
                text=store.read_blob(task['prompt_ref']).decode()
                self.assertIn(DUTIES[sid][1],text)
                self.assertIn(target,[x['ref'] for x in task['input_manifest']])
                self.assertEqual(store.read_snapshot()['requests'][task['request_id']]['acceptance_state'],'ACCEPTED')
            self.assertEqual(len(store.read_snapshot()['tasks']),9)
            e.pause(store,iid,'Synthetic control evidence');before=len(store.read_snapshot()['tasks'])
            e.decide(store,iid,'END','Finish the synthetic software scenario without proof.',snapshot_commit=store.read_snapshot()['knowledge_commit'])
            self.assertEqual(len(store.read_snapshot()['tasks']),before)
            self.assertEqual(store.read_snapshot()['instances'][iid]['target_ref'],target)
            store.audit()

    def test_t2_p7_n_plus_m_complete_dispositions_first_research_and_global_gap(self):
        with TemporaryDirectory() as d:
            e,store,iid,target=self.trh(d+'/p');sources=[]
            for n in range(3):
                sources.append(store.commit(changes.prepare_material_input(store.read_snapshot(),('Synthetic framework '+str(n)+' with its explicit assumptions.').encode(),title='Framework '+str(n),media_type='text/plain',blob_get=store.read_blob))['source_ref'])
            items=[{'key':'learn'+str(n),'stage':'P7','role':'LEARN','intent':'Reconstruct framework '+str(n)+' and test its transfer to the additive identity obstacle.',
                    'framework_scope':'Different mathematical framework '+str(n)+' for the fixed obstacle','source_refs':[sources[n]],
                    **({'depends_on':['learn0']} if n==2 else {})} for n in range(3)]
            items += [{'key':'direct0','stage':'P7','role':'DIRECT','intent':'Derive directly from the additive group axioms.','framework_scope':'Axiomatic direct derivation'},
                      {'key':'direct1','stage':'P7','role':'DIRECT','intent':'Test an independent constructive boundary route.','framework_scope':'Constructive boundary route','required':False},
                      {'key':'join','stage':'P7','role':'SYNTHESIS','intent':'Compare all selected transfers and direct attempts, including the deferred route.','synthesis_of':['learn0','learn1','learn2','direct0','direct1']},
                      {'key':'first','stage':'P8','role':'RESEARCH','intent':'Execute the first actual additive-identity proof attempt using the surviving exact hypotheses.','depends_on':['join']},
                      {'key':'global','stage':'P11','role':'SYNTHESIS','intent':'Reassess the entire original target and all unproved or deferred interfaces.','synthesis_of':['first']},
                      {'key':'independent','stage':'P12','role':'INDEPENDENT','intent':'Independently recheck the new global assembly and gap boundary.','depends_on':['global']}]
            planned=e.plan_work(store,iid,'Synthetic finite shared research plan; never certify actual mathematics.',items,max_calls=8,max_workers=4,policy=demo.policy())
            initial=scheduler.plan(store.read_snapshot(),[iid],{'max_workers':4})
            selected={r['consumer']['entry_basis']['research_plan']['branch_key'] for r in initial['selected']}
            self.assertNotIn('learn2',selected);self.assertNotIn('join',selected);self.assertNotIn('first',selected)
            binding=next(b for b in planned['bindings'] if b['key']=='direct1')
            e.defer_work(store,iid,binding['binding_id'],'Explicitly nonessential constructive branch deferred within this synthetic plan; its mathematics remains open.')
            captured=[]
            for key in ('learn0','learn1','direct0','learn2','join','first','global','independent'):
                def respond(task,snapshot):
                    if task['stage_id']=='P8':return demo.response(task,snapshot)
                    raw=loads(no_result(task,snapshot));payload=raw['payload']
                    branch=task['entry_basis']['research_plan']['branch_key']
                    if branch in {'learn0','learn1'}:
                        from research_studio.knowledge import locator
                        body='For the synthetic framework '+branch+', the transferred conclusion requires an unproved compatibility hypothesis. This is a conditional software fixture, not a proved result.'
                        loc=locator(body)
                        payload['operations']=[{'op':'NEW','local_key':'conditional','kind':'Statement','context_refs':[],
                            'body':body,'data':{'statement_locator':loc,'scope_context_refs':[],'hypothesis_locators':[loc],
                            'conclusion_locators':[loc],'quantifier_locators':[loc],'form':'CONJECTURE','representation':'AUTHORED','source_binding':None}}]
                        payload['work_outcome']='RESULT'
                        for effect in payload['obligation_effects']:effect.update(work_disposition='PARTIAL',resolution_proposal='CANDIDATE_RESPONSE',evidence_refs=['local:conditional'])
                    return canonical(raw)
                task=self.dispatch_one(store,iid,key,respond);captured.append(task)
                if key in ('direct0','learn2'):
                    material={x['ref'] for x in task['input_manifest'] if x['kind']=='source'}
                    if key=='direct0':self.assertFalse(set(sources)&material)
                    else:self.assertIn(sources[2],material);self.assertNotIn(sources[1],material)
            state=store.read_snapshot();self.assertEqual(len(state['missions']),1);self.assertEqual(len(state['requests']),8)
            self.assertEqual(scheduler.budget_remaining(state,state['missions'][planned['mission_id']]['budget_grant_id']),0)
            join=next(t for t in captured if t['entry_basis']['research_plan']['branch_key']=='join')
            context=O.branch_context(state,next(c for o in state['obligations'].values() for c in o['definition']['consumer_bindings'] if c['binding_id']==join['obligation_bindings'][0]['binding_id']))
            self.assertEqual(len(context),5);self.assertEqual(sum(x['disposition']=='DEFERRED' for x in context),1)
            self.assertTrue(all(x['attempt_accounts'] for x in context if x['disposition']=='RECORDED'))
            join_text=store.read_blob(join['prompt_ref']).decode()
            self.assertIn('synthesis_work',join_text)
            self.assertIn('constructive branch deferred',join_text)
            self.assertTrue(all(branch['binding_id'] in join_text for branch in context))
            transfer_refs={ref for branch in context if branch['role']=='LEARN' for ref in branch['evidence_refs']}
            direct=next(t for t in captured if t['role']=='DIRECT')
            self.assertFalse(transfer_refs & {m['ref'] for m in direct['input_manifest']})
            self.assertTrue(transfer_refs <= {m['ref'] for m in join['input_manifest']})
            global_task=next(t for t in captured if t['stage_id']=='P11')
            self.assertIn('global_gap_inventory',store.read_blob(global_task['prompt_ref']).decode())
            self.assertTrue(transfer_refs <= {m['ref'] for m in global_task['input_manifest']})
            self.assertIn('actual transferred proposition',store.read_blob(captured[0]['prompt_ref']).decode())
            first=next(t for t in captured if t['stage_id']=='P8');self.assertTrue(any(p['task_id']==first['task_id'] and state['records'][p['record_ref']]['kind']=='Argument' for p in state['production_events'].values()))
            self.assertIn('Reassess globally',store.read_blob(next(t for t in captured if t['stage_id']=='P11')['prompt_ref']).decode())
            self.assertTrue(captured[-1]['independent']);self.assertTrue(captured[-1]['excluded_verdicts']);store.audit()

    def test_t2_labels_methods_and_new_missions_do_not_reset_duty_budget(self):
        with TemporaryDirectory() as d:
            e,store,iid,target=self.trh(d+'/p')
            item={'key':'original','stage':'P8','role':'RESEARCH','intent':'Attempt the same exact scientific question.','framework_scope':'Same obstacle and scope','method_ref':'FIRST_LABEL'}
            original=e.plan_work(store,iid,'First wrapper',[item],max_calls=1,policy=demo.policy());task=self.dispatch_one(store,iid)
            changed={**item,'key':'renamed','method_ref':'RENAMED_METHOD'}
            second=e.plan_work(store,iid,'Second wrapper with the same scientific duty',[changed],max_calls=1,policy=demo.policy())
            self.assertEqual(original['obligation_ids'],second['obligation_ids'])
            state=store.read_snapshot();plan=scheduler.plan(state,[iid],demo.policy())
            self.assertFalse(plan['selected']);self.assertIn('RETRY_GRANT_EXHAUSTED',{r['code'] for r in plan['waits']})
            self.assertEqual(len(state['requests']),1);self.assertEqual(next(iter(state['requests'].values()))['responsibility_key'],task['responsibility_key'])
            duplicate=[item,{**item,'key':'cosmetic2','method_ref':'OTHER'}]
            before=state['project_budget']['max_calls']
            with self.assertRaises(PMRSError) as cm:e.plan_work(store,iid,'Duplicate branch names',duplicate,policy=demo.policy())
            self.assertEqual(cm.exception.code,'RESEARCH_PLAN_DUPLICATE_DUTY');self.assertEqual(store.read_snapshot()['project_budget']['max_calls'],before)

    def test_t2_synthesis_cannot_omit_selected_branch_or_read_pending_work(self):
        with TemporaryDirectory() as d:
            e,store,iid,target=self.trh(d+'/p')
            branches=[{'key':'l'+str(n),'stage':'P7','role':'LEARN','intent':'Study exact framework '+str(n),'framework_scope':'Framework '+str(n)} for n in range(2)]
            branches.append({'key':'direct','stage':'P7','role':'DIRECT','intent':'An independent direct derivation.'})
            items=branches+[{'key':'join','stage':'P7','role':'SYNTHESIS','intent':'Compare selected methods.','synthesis_of':['l0','direct']}]
            with self.assertRaises(PMRSError) as cm:e.plan_work(store,iid,'Must account for every branch',items,policy=demo.policy())
            self.assertEqual(cm.exception.code,'RESEARCH_PLAN_INVALID');self.assertFalse(store.read_snapshot()['missions'])
            items[-1]['synthesis_of']=['l0','l1','direct']
            result=e.plan_work(store,iid,'All branches are fixed',items,max_calls=4,max_workers=2,policy=demo.policy())
            binding=next(b for b in result['bindings'] if b['key']=='l1')
            store.commit_control(W.event(store.read_snapshot(),'RETIRE_CONSUMER',{'binding_id':binding['binding_id'],'reason':'Required branch remains unperformed.'},instance_id=iid))
            self.dispatch_one(store,iid,'l0');self.dispatch_one(store,iid,'direct')
            planned=scheduler.plan(store.read_snapshot(),[iid],demo.policy())
            self.assertFalse(planned['selected']);self.assertIn('DEPENDENCY_PENDING',{r['code'] for r in planned['waits']})

    def test_t2_accepted_concrete_method_followup_enters_p8_and_d4_keeps_comparisons(self):
        from research_studio.engine import derive_followups
        with TemporaryDirectory() as d:
            e,store,iid,target=self.trh(d+'/trh')
            result=e.plan_work(store,iid,'A source-free direct investigation followed only by its concrete gap.',
                [{'key':'direct','stage':'P7','role':'DIRECT','intent':'Analyze a precise additive identity interface directly.'}],max_calls=2,policy=demo.policy())
            def concrete_gap(task,snapshot):
                raw=loads(no_result(task,snapshot));raw['payload']['new_obligation_proposals']=[{
                    'local_key':'first_attempt','type':'ESTABLISH','reason_code':None,'target_refs':[target],
                    'criterion_body':'Carry out the first actual proof attempt for the precise unresolved identity interface.',
                    'scope_context_refs':[],'dependency_bindings':[],'consumer_binding_proposals':[],
                    'effect_on_goal':'OPEN_SCOPE','reason_refs':[target]}]
                return canonical(raw)
            self.dispatch_one(store,iid,'direct',concrete_gap);created=derive_followups(store,iid)
            self.assertEqual(len(created),1)
            state=store.read_snapshot();new=next(o for o in state['obligations'].values() if o['definition']['created_by'].startswith('CHANGE-'))
            c=new['definition']['consumer_bindings'][0];self.assertEqual((c['stage_id'],c['role']),('P8','RESEARCH'))
            self.assertEqual(c['mission_id'],result['mission_id']);self.assertEqual(len(state['budget_grants']),1)
            task=self.dispatch_one(store,iid,response=demo.response);self.assertEqual(task['stage_id'],'P8')
            discovery=e.create(d+'/discovery',b'Synthetic frontier.',phenomenon=True,synthetic=True)
            di=e.new_workflow(discovery,'FDH',discovery_scope=demo.discovery_scope())['instance_id']
            e.start_round(discovery,di,'Explore only the declared evidence and its precise candidate.',max_calls=3,policy=demo.policy())
            self.dispatch_one(discovery,di,response=demo.response);derive_followups(discovery,di)
            self.assertFalse(any(c['stage_id']=='D4' for o in discovery.read_snapshot()['obligations'].values() for c in o['definition']['consumer_bindings']))
            comparison=self.dispatch_one(discovery,di,response=no_result)
            self.assertEqual(comparison['stage_id'],'D3');derive_followups(discovery,di)
            review=next(c for o in discovery.read_snapshot()['obligations'].values() for c in o['definition']['consumer_bindings'] if c['stage_id']=='D4')
            self.assertTrue(all('inter_candidate_comparisons' in part['aspects'] and 'hypothesis_cost' in part['aspects'] for part in review['scope']))
            self.assertEqual(len(discovery.read_snapshot()['missions']),1)

    def test_t3_survey_reading_topic_review_dag_shares_one_authorization(self):
        with TemporaryDirectory() as d:
            e=Engine();store=e.create_survey(d+'/p',survey.demo_scope(),synthetic=True)
            iid=next(iter(store.read_snapshot()['instances']));sources=[]
            for n in range(2):
                receipt=store.commit(changes.prepare_material_input(store.read_snapshot(),survey.TEACHING_TEXT.encode(),title='Synthetic independent reading package '+str(n),media_type='text/plain',blob_get=store.read_blob));sources.append(receipt['source_ref'])
            items=[{'key':'read'+str(n),'stage':'S2','role':'SOURCE_READ','intent':'Read exact synthetic material package '+str(n),'source_refs':[sources[n]]} for n in range(2)]
            items += [{'key':'organize','stage':'S3','role':'ORGANIZE','intent':'Organize the finite-sum mechanism and its boundary from both actual reading packages.','depends_on':['read0','read1']},
                      {'key':'review','stage':'S4','role':'READINESS_REVIEW','intent':'Independently check the exact selected knowledge, source conditions and full question coverage.','depends_on':['organize']}]
            result=survey.start_activity(store,iid,intent='One finite synthetic Survey reading and organization plan.',items=items,max_calls=4,max_workers=2,policy=demo.policy())
            initial=scheduler.plan(store.read_snapshot(),[iid],{'max_workers':2});self.assertEqual({r['role'] for r in initial['selected']},{'SOURCE_READ'})
            self.assertEqual(len(initial['selected']),2)
            seen=[]
            for key in ('read0','read1','organize','review'):
                task=self.dispatch_one(store,iid,key,demo.response);seen.append(task)
                if key.startswith('read'):
                    self.assertEqual(task['survey_context']['source_refs'],[sources[int(key[-1])]])
            state=store.read_snapshot();self.assertEqual(len(state['missions']),1)
            self.assertFalse(state['missions'][result['mission_id']]['authorized_scope']['allow_derived_work'])
            self.assertEqual(len(seen[2]['survey_context']['readings']),2)
            self.assertTrue(seen[3]['survey_context']['coverage']);self.assertTrue(seen[3]['survey_context']['selected_refs'])
            ready=survey.readiness(state,iid,seen[3]['survey_context']['selected_refs']);self.assertEqual(ready['status'],'SYNTHETIC_READY')
            frozen=survey.freeze_knowledge(store,iid,seen[3]['survey_context']['selected_refs']);self.assertTrue(frozen['snapshot_ref'])
            self.assertFalse(state['reports']);self.assertEqual(scheduler.budget_remaining(state,state['missions'][result['mission_id']]['budget_grant_id']),0)
            before=state['project_budget']['max_calls']
            with self.assertRaises(PMRSError):survey.start_activity(store,iid,intent='Rename the wrapper',items=items,max_calls=4,policy=demo.policy())
            self.assertEqual(store.read_snapshot()['project_budget']['max_calls'],before)
            target=next(r for r in ready['selected_refs'] if state['records'][r]['kind']=='Statement')
            handoff=e.prepare_handoff(store,iid,'SURVEY_TO_TRH',{'target_refs':[target]})
            decision=e.decide(store,iid,'ADOPT_HANDOFF','Select the exact synthetic target for a paused handoff.',snapshot_commit=store.read_snapshot()['knowledge_commit'])
            adopted=e.adopt_handoff(store,handoff['handoff_id'],decision)
            self.assertEqual(adopted['status'],'PAUSED');self.assertEqual(len(store.read_snapshot()['requests']),4)
            e.decide(store,iid,'END','The Knowledge only synthetic plan ends without an article.',snapshot_commit=store.read_snapshot()['knowledge_commit']);store.audit()

    def test_t3_discovery_zero_candidates_and_frontier_comparison_remain_native(self):
        with TemporaryDirectory() as d:
            e=Engine();store=e.create(d+'/p',b'Synthetic discovery phenomenon.',phenomenon=True,synthetic=True)
            iid=e.new_workflow(store,'FDH',discovery_scope=demo.discovery_scope())['instance_id']
            items=[{'key':'evidence','stage':'D1','role':'LEARN','intent':'Assess the positive and negative evidence without requiring a candidate.'},
                   {'key':'axis','stage':'D2','role':'DIRECT','intent':'Explore the permitted positivity axis only.','depends_on':['evidence']},
                   {'key':'second_axis','stage':'D2','role':'DIRECT','intent':'Explore the semidefinite boundary axis only.','depends_on':['evidence']},
                   {'key':'distinguish','stage':'D3','role':'DIRECT','intent':'Compare both exact candidates with distinguishing examples; preserve unknown implications.','depends_on':['axis','second_axis']},
                   {'key':'comparison','stage':'D4','role':'FORMULATION_REVIEW','intent':'Independently examine the candidate frontier and all candidate-to-candidate comparisons.','depends_on':['axis','second_axis','distinguish']}]
            e.plan_work(store,iid,'Bounded discovery example',items,max_calls=5,max_workers=2,policy=demo.policy())
            self.dispatch_one(store,iid,'evidence',no_result);self.assertFalse(store.read_snapshot()['candidates'])
            def candidate_only(task,snapshot):
                raw=loads(demo.response(task,snapshot));payload=raw['payload']
                payload['operations']=[op for op in payload['operations'] if op['kind']=='Statement']
                if task['entry_basis']['research_plan']['branch_key']=='second_axis':
                    from research_studio.knowledge import locator
                    op=payload['operations'][0];op['body']=op['body'].replace('positive definite','positive semidefinite').replace('is positive.','is nonnegative.')
                    loc=locator(op['body'])
                    op['data'].update(statement_locator=loc,hypothesis_locators=[loc],conclusion_locators=[loc],quantifier_locators=[loc])
                for effect in payload['obligation_effects']:effect['evidence_refs']=['local:candidate']
                return canonical(raw)
            self.dispatch_one(store,iid,'axis',candidate_only);self.assertEqual(len(store.read_snapshot()['candidates']),1)
            self.dispatch_one(store,iid,'second_axis',candidate_only);self.assertEqual(len(store.read_snapshot()['candidates']),2)
            distinction=self.dispatch_one(store,iid,'distinguish',no_result)
            candidates={c['statement_ref'] for c in store.read_snapshot()['candidates'].values()}
            self.assertTrue(candidates <= {m['ref'] for m in distinction['input_manifest']})
            task=self.dispatch_one(store,iid,'comparison',no_result)
            self.assertIn('relations BETWEEN candidates',store.read_blob(task['prompt_ref']).decode())
            self.assertTrue(candidates <= {m['ref'] for m in task['input_manifest']});self.assertTrue(task['independent'])
            self.assertIsNone(store.read_snapshot()['instances'][iid]['target_ref']);store.audit()


if __name__=='__main__':unittest.main()
