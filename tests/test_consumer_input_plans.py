"""Material closure and real-byte capacity regressions; no paid execution."""
from copy import deepcopy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from research_studio import context, demo, input_plans, knowledge, obligations as O, tasks, changes, scheduler
from research_studio.engine import Engine, derive_followups
from research_studio.store import Store
from research_studio.util import PMRSError, sha, canonical
from tests.test_final_kernel import Fixture, statement, argument


class ConsumerInputPlans(unittest.TestCase):
    def fixture(self):
        f=Fixture();target=f.add(statement('Every admissible object satisfies the original bound.'))
        f.s['instances']={'I':{'instance_id':'I','target_ref':target}}
        c={'binding_id':'B-next','instance_id':'I','mission_id':'M','stage_id':'P2','role':'PLAN',
           'input_refs':[],'source_refs':[],'entry_basis':{'research_plan':{'plan_id':'P'}}}
        return f,target,c

    def produce(self,f,refs,*,task='T-up',capture='capture',stage='P1',role='PLAN',sources=()):
        request='R-'+task;binding='B-'+task
        f.s['tasks'][task]={'task_id':task,'request_id':request,'instance_id':'I','mission_id':'M',
            'stage_id':stage,'role':role,'obligation_bindings':[{'binding_id':binding,'obligation_id':'O-'+task,'expected_definition_revision':1}],
            'input_manifest':[{'kind':'source','ref':r,'sha256':f.s['sources'][r]['blob_hash']} for r in sources]}
        f.s['requests'][request]={'request_id':request,'task_id':task,'mission_id':'M','capture_ref':capture,'acceptance_state':'ACCEPTED'}
        for ref in refs:
            eid='E-'+task+'-'+ref
            f.s['production_events'][eid]={'event_id':eid,'record_ref':ref,'task_id':task,'request_id':request,'capture_hash':capture}
        o=O.make('O-'+task,'MATERIAL',[], 'criterion');o['projection']['evidence_refs']=list(refs)
        f.s['obligations']['O-'+task]=o
        return {'dependency_id':'D-'+task,'binding_ref':'O-'+task,'binding_id':binding,'threshold':'WORK_DISPOSITION_RECORDED'}

    def source(self,f,raw=b'Exact primary theorem with all its hypotheses.\n',ref='SO-paper'):
        f.s['sources'][ref]={'blob_hash':sha(raw),'bytes':len(raw),'media_type':'text/plain','coverage':'FULL_DOCUMENT','access_class':'SCIENTIFIC_SOURCE'}
        f.blobs[sha(raw)]=raw
        return ref

    def test_completion_identity_is_distinct_from_scientific_background_and_source(self):
        f,target,c=self.fixture();source=self.source(f)
        text='The common original hypotheses and normalization remain fixed.'
        background=f.add(knowledge.make_record('Context',text,{'definitions':[], 'objects':[], 'assumptions':[],
            'quantifiers':[], 'conventions':[], 'parent_context_refs':[]}))
        evidence=f.add(knowledge.make_record('SourceEvidence','The exact primary text was read.',{
            'source_occurrence_refs':[source],'locators':[knowledge.locator(f.blobs[f.s['sources'][source]['blob_hash']])],
            'evidence_type':'ORIGINAL_TEXT','coverage':'FULL_DOCUMENT','reproducibility_refs':[]},sources=f.s['sources'],blob_get=f.get))
        dep=self.produce(f,[background,evidence],sources=[source])
        o=O.make('O-next','REDUCE',[target],'criterion',dependencies=[dep])
        self.assertEqual(O.dependency_inputs(f.s,o['definition']),[])
        plan=input_plans.build(f.s,o,c,blob_get=f.get)
        self.assertIn(background,plan['scientific_input_refs']);self.assertNotIn(evidence,plan['scientific_input_refs'])
        self.assertIn(source,plan['required_source_refs'])
        account=plan['completion_dependencies'][0]
        self.assertEqual(account['accepted_requests'][0]['capture_ref'],'capture')
        self.assertEqual(account['excluded_outputs'],[{'record_ref':evidence,'reason':'NOT_A_PREMISE_OF_THIS_DUTY'}])
        packet=context.build_packet(f.s,plan['roots'],f.get,required_source_refs=plan['required_source_refs'])
        self.assertEqual(set(packet['records']),{target,background});self.assertEqual(set(packet['sources']),{source})

    def test_gap_binds_same_producer_argument_and_establish_original_source(self):
        f,target,c=self.fixture();source=self.source(f)
        claim=f.add(statement('The exact derived conditional estimate is available.'))
        proof=f.add(argument(claim,'This is the exact self-contained argument for that estimate.'))
        other=f.add(argument(claim,'This different accepted argument is not the selected producer.'))
        self.produce(f,[claim,proof],task='T-origin',capture='origin',sources=[source])
        self.produce(f,[other],task='T-unrelated',capture='unrelated')
        c.update(stage_id='P8',role='RESEARCH',entry_basis={})
        o=O.make('O-gap','ESTABLISH',[claim],'criterion',created_by='CHANGE-origin')
        plan=input_plans.build(f.s,o,c,blob_get=f.get)
        self.assertIn(proof,plan['scientific_input_refs']);self.assertNotIn(other,plan['scientific_input_refs'])
        self.assertIn(source,plan['required_source_refs'])
        self.assertEqual(next(r for r in plan['selected_records'] if r['record_ref']==proof)['provenance'][0]['capture_ref'],'origin')
        self.assertEqual(input_plans.enrich_consumer(f.s,o,c)['input_refs'],[])
        selected=deepcopy(c);selected['selected_support']='SP-missing'
        with self.assertRaisesRegex(PMRSError,'INCOMPLETE_CONTEXT'):input_plans.build(f.s,o,selected)

    def test_exact_excerpt_delivers_slice_not_full_backing_and_reports_unread_scope(self):
        f,target,c=self.fixture();raw=b'Opening definitions.\nExact required theorem.\nUnused later discussion.\n';source=self.source(f,raw)
        loc=knowledge.locator(raw,21,44)
        c['source_refs']=[source];c['source_selections']={source:{'coverage':'DECLARED_RANGE','locators':[loc],
            'reason':'Only the exact theorem statement is needed for this declared comparison.'}}
        o=O.make('O-next','COMPARE',[target],'criterion')
        plan=input_plans.build(f.s,o,c,blob_get=f.get)
        packet=context.build_packet(f.s,plan['roots'],f.get,required_source_refs=plan['required_source_refs'],source_selections=plan['source_selections'])
        piece=raw[21:44]
        self.assertNotIn(sha(raw),packet['source_bodies']);self.assertEqual(packet['source_excerpt_bodies'],{sha(piece):piece})
        self.assertEqual(packet['source_excerpts'][source]['source_blob_hash'],sha(raw));self.assertFalse(packet['complete'])
        with TemporaryDirectory() as d:
            store=Store.create(Path(d)/'p','Excerpt fixture',synthetic=True)
            for value in f.blobs.values():store.blob(value)
            material=tasks.material_references(store,packet)
            self.assertIn(sha(piece),material);self.assertNotIn(sha(raw),material)
            self.assertEqual(store.read_blob(material[sha(piece)]['sha256']),piece)
        c['source_selections'][source]['locators'][0]['end']=len(raw)+1
        with self.assertRaisesRegex(PMRSError,'RESPONSE_SCHEMA_INVALID'):input_plans.build(f.s,o,c,blob_get=f.get)

    def test_excerpt_cannot_omit_required_premise_or_claim_full_document_read(self):
        f,target,c=self.fixture();raw=b'First exact premise. Second necessary premise. End.\n';source=self.source(f,raw)
        source_use={'source_ref':source,'locators':[knowledge.locator(raw,21,45)],
                    'usage_mode':'STATEMENT_RELIANCE','trust_boundary':'Only supplied original text; no qualification.'}
        full=knowledge.locator(raw)
        claim_body=raw[21:45].decode()
        claim=f.add(knowledge.make_record('Statement',claim_body,{'statement_locator':source_use['locators'][0],
            'scope_context_refs':[],'hypothesis_locators':[],'conclusion_locators':[],'quantifier_locators':[],
            'form':'PROPOSITION','representation':'SOURCE_BOUND','source_binding':source_use},sources=f.s['sources'],blob_get=f.get))
        selection={source:{'coverage':'DECLARED_RANGE','locators':[knowledge.locator(raw,0,20)],'reason':'Incomplete proposed reading.'}}
        with self.assertRaisesRegex(PMRSError,'INCOMPLETE_CONTEXT'):
            context.build_packet(f.s,[claim],f.get,source_selections=selection)
        ev=f.add(knowledge.make_record('SourceEvidence','The full original document is required.',{
            'source_occurrence_refs':[source],'locators':[full],'evidence_type':'ORIGINAL_TEXT','coverage':'FULL_DOCUMENT',
            'reproducibility_refs':[]},sources=f.s['sources'],blob_get=f.get))
        with self.assertRaisesRegex(PMRSError,'INCOMPLETE_CONTEXT'):
            context.build_packet(f.s,[ev],f.get,source_selections=selection)

    def test_declared_source_range_snapshot_fingerprint_is_pure_and_freeze_checks_bytes(self):
        f,target,c=self.fixture();raw=b'Exact primary theorem. Remainder with limitations.'
        source=self.source(f,raw);loc=knowledge.locator(raw,0,22)
        c.update(source_refs=[source],source_selections={source:{'coverage':'DECLARED_RANGE','locators':[loc],
            'reason':'This duty examines only the exact theorem wording.'}})
        o=O.make('O-next','REDUCE',[target],'criterion')
        plan=input_plans.build(f.s,o,c)
        self.assertEqual(plan,input_plans.build(f.s,o,c,blob_get=f.get))
        bad=deepcopy(c);bad['source_selections'][source]['locators'][0]['quoted_sha256']='0'*64
        # Snapshot preflight validates identity/shape. Exact bytes are required
        # before freezing or delivering any source range.
        input_plans.build(f.s,o,bad)
        with self.assertRaisesRegex(PMRSError,'ORIGINAL_BYTES_MISMATCH'):
            input_plans.build(f.s,o,bad,blob_get=f.get)

    def test_reverse_counterevidence_enters_the_same_plan_and_changes_its_hash(self):
        from research_studio import relations
        f,target,c=self.fixture();o=O.make('O-next','REDUCE',[target],'criterion')
        before=input_plans.build(f.s,o,c,blob_get=f.get)
        opposing=f.add(argument(target,'An exact candidate counterexample challenges the original target.'))
        f.s['relations'].append(relations.relation(opposing,target,'COUNTEREXAMPLE_TO'))
        plan=input_plans.build(f.s,o,c,blob_get=f.get)
        self.assertIn(opposing,plan['scientific_input_refs']);self.assertNotEqual(before['plan_hash'],plan['plan_hash'])
        packet=context.build_packet(f.s,plan['roots'],f.get,required_source_refs=plan['required_source_refs'])
        self.assertEqual(set(plan['scientific_input_refs']),set(packet['records']))

    def test_new_consumer_requirement_uses_exact_scope_and_same_policy_digest(self):
        from research_studio import assurance,contracts as C
        f,target,c=self.fixture()
        old=assurance.requirement('PROOF_SUPPORT',[{'target_ref':target,'aspects':['full_argument'],'locators':[]}])
        c.update(required_assurance=old,policy_digest=C.digest(old),entry_basis={'consumer_requirement':deepcopy(old)})
        o=O.make('O-next','REDUCE',[target],'criterion')
        enriched=input_plans.enrich_consumer(f.s,o,c,blob_get=f.get)
        req=enriched['required_assurance']
        self.assertEqual(req['required_scope'][0]['scope_version'],'pmrs.exact-scope/1')
        self.assertEqual(enriched['policy_digest'],C.digest(req))
        self.assertEqual(enriched['entry_basis']['consumer_requirement'],req)
        for slot in req['review_slots']:
            self.assertEqual(slot['required_scope'][0]['target_body_sha256'],f.s['records'][target]['body_sha256'])
        self.assertNotIn('scope_version',old['required_scope'][0])

    def test_client_overhead_reservation_covers_only_exact_observed_tool_schema(self):
        from research_studio import task_tools
        wire=canonical({'tools':task_tools.tool_definitions(),'instructions':task_tools.INSTRUCTIONS})
        task={'communication_contract':{'max_dynamic_input_tokens':8192,'tool_trajectory_reserve_tokens':4096},
              'tool_schema_hash':sha(wire),'executor_contract':{'client_input_evidence':{
                  'non_task_input_bytes':22000,'task_tools_included':True,'covered_tool_schema_hashes':[sha(wire)]}}}
        packet={'input_representation':'BLOB_REFERENCES_V1','material_refs':{}}
        capacity=demo.policy()['capacity']
        covered,details=tasks.request_budget(task,'prompt',packet,capacity,reserved_output_tokens=1280,prompt_overhead_tokens=22000)
        self.assertTrue(details['client_overhead_includes_task_tools'])
        self.assertEqual(covered['prompt_overhead_tokens'],22000)
        with self.assertRaisesRegex(PMRSError,'CONTEXT_LIMIT'):
            tasks.request_budget(task,'prompt',packet,capacity,reserved_output_tokens=1280,prompt_overhead_tokens=21999)
        task['executor_contract']['client_input_evidence']['covered_tool_schema_hashes']=[]
        untrusted,details=tasks.request_budget(task,'prompt',packet,capacity,reserved_output_tokens=1280,prompt_overhead_tokens=22000)
        self.assertFalse(details['client_overhead_includes_task_tools'])
        self.assertGreater(untrusted['input_tokens'],covered['input_tokens']+len(wire)-100)

    def test_model_files_remove_only_host_or_exact_duplicate_metadata(self):
        legacy={'task_id':'T','read_set':[{'record_ref':'KR-1'}]}
        self.assertEqual(tasks.model_task_payload(legacy),legacy)
        task={**legacy,'model_input_revision':tasks.MODEL_INPUT_REVISION,
              'scope':{'target_refs':['KR-1']},'required_assurance':{'exact':'scope'},
              'executor_contract':{'capabilities':{'python':{'available':True}},
                                   'client_input_evidence':{'non_task_input_bytes':31415}},
              'entry_basis':{'autoflow':{'key':'P2'},'analysis_route':'COMPARATIVE'}}
        view=tasks.model_task_payload(task)
        self.assertNotIn('read_set',view);self.assertNotIn('client_input_evidence',view['executor_contract'])
        self.assertEqual(view['scope'],task['scope']);self.assertEqual(view['required_assurance'],task['required_assurance'])
        self.assertEqual(view['executor_contract']['capabilities'],task['executor_contract']['capabilities'])
        self.assertEqual(view['entry_basis'],{'analysis_route':'COMPARATIVE'})
        packet={'model_input_revision':tasks.MODEL_INPUT_REVISION,'records':{'KR-1':{'kind':'Statement','data':{'unchanged':['all','fields']}}},
                'sources':{'SO-1':{'origin':{'uri':'exact original'},'blob_hash':'abc'}},
                'source_excerpts':{'SO-1':{'coverage':'DECLARED_RANGE','segments':[{'start':1,'end':2}]}},
                'relations':[{'type':'CANDIDATE_SUPPORT'}]}
        supplied=tasks.model_packet_payload(packet)
        for key in ('records','sources','source_excerpts','relations'):self.assertEqual(supplied[key],packet[key])
        authoring={'response_schema':{'all':'branches'},'knowledge_change_schema':{'all':'branches'},
                   'binding_rules':['All precise rules remain.'],'binding_table':{
                       'records':[{'ref':'KR-1','required_support_refs':['SUP-1']}],
                       'source_uses':[{'source_ref':'SO-1','trust_boundary':'Exact preserved boundary'}],
                       'write_guards':[{'record_ref':'KR-1','revision':3}]}}
        prompt_view=tasks.model_authoring_payload(authoring)
        self.assertEqual(prompt_view['response_schema'],authoring['response_schema'])
        self.assertEqual(prompt_view['binding_rules'],authoring['binding_rules'])
        self.assertEqual(prompt_view['binding_table']['required_support_refs'],{'KR-1':['SUP-1']})
        for key in ('source_uses','write_guards'):self.assertEqual(prompt_view['binding_table'][key],authoring['binding_table'][key])
        self.assertNotIn('knowledge_change_schema',prompt_view)
        self.assertIn('knowledge_change_schema',authoring)

    def test_full_hsc_length_p2_capacity_has_no_smaller_output_reserve(self):
        # Same original LaTeX byte length as the incident (56,995), synthesized
        # text only. The actual same-version HSC experiment is separate evidence.
        with TemporaryDirectory() as d, patch.dict(os.environ,{'PMRS_HOST_POOL_ROOT':str(Path(d)/'pool')}):
            engine=Engine();original_target=(demo.ARITHMETIC+b'\n'+(b'The integer domain and ordinary additive identity remain the exact fixed conventions. '*100))[:4786]
            store=engine.create(Path(d)/'p',original_target,synthetic=True)
            target=next(iter(store.read_snapshot()['records']));iid=engine.new_workflow(store,'TRH',target_ref=target)['instance_id']
            raw=(b'Exact long original source: assumptions, proof and limitations.\n'*1000)[:56995]
            source=store.commit(changes.prepare_material_input(store.read_snapshot(),raw,'Generated long-source fixture','text/plain',blob_get=store.read_blob))['source_ref']
            p=demo.policy();p['capacity'].update(context_window_tokens=258400,model_max_output_tokens=128000)
            p.update(reserved_output_tokens=128000,safety_margin_tokens=2048,communication={'max_dynamic_input_tokens':8192,'tool_trajectory_reserve_tokens':4096})
            intent=('Inspect the fixed target with this full exact source and keep all hypotheses. '*30)[:1375]
            engine.start_round(store,iid,intent,source_refs=[source],max_calls=5,policy=p)
            first=engine.prepare(store,iid,policy=p)['prepared'][0]
            with patch.object(demo,'ARITHMETIC',original_target):
                self.assertEqual(demo.executor().execute(store,first['task_id'])['state'],'ACCEPTED')
            derive_followups(store,iid)
            second=engine.prepare(store,iid,policy=p)['prepared'][0]
            task=tasks.load(store,second['task_id']);packet=json.loads(store.read_blob(task['input_packet_ref']))
            self.assertEqual(task['stage_id'],'P2');self.assertEqual(task['context_budget']['reserved_output_tokens'],128000)
            self.assertLessEqual(task['context_budget']['input_tokens'],128352)
            self.assertEqual(task['communication_contract']['max_dynamic_input_tokens'],8192)
            self.assertGreater(task['context_budget_details']['tool_schema_and_instructions_bytes'],0)
            self.assertEqual(task['context_budget_details']['tool_trajectory_reserve_tokens'],4096)
            self.assertEqual(store.read_blob(task['material_refs'][sha(raw)]['sha256']),raw)
            self.assertNotIn('body_text',packet);self.assertTrue(packet['input_plan']['completion_dependencies'])
            # Exact bound equality passes and one less byte stops before sends.
            prompt=store.read_blob(task['prompt_ref']).decode();budget=task['context_budget']
            total=budget['input_tokens']+budget['reserved_output_tokens']+budget['safety_margin_tokens']
            with self.assertRaisesRegex(PMRSError,'CONTEXT_LIMIT'):
                tasks.request_budget(task,prompt,packet,{**p['capacity'],'context_window_tokens':total-1},reserved_output_tokens=128000,safety_margin_tokens=2048)


if __name__=='__main__':unittest.main()
