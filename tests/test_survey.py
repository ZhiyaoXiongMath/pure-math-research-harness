"""Survey contract/recovery checks use isolated synthetic native workspaces."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from research_studio import survey, demo, changes
from research_studio.engine import Engine
from research_studio.store import Store
from research_studio.util import PMRSError


def ready_survey(root,profile='minimal'):
    """Return (store, instance_id, evidence dict); no network or paid model calls."""
    store=Store.create(root,'Synthetic finite geometric survey',synthetic=True)
    material=store.commit(changes.prepare_material_input(store.read_snapshot(),survey.TEACHING_TEXT.encode(),
        'Explicit synthetic teaching material','text/plain',blob_get=store.read_blob))
    scope=survey.demo_scope();scope['source_refs']=[material['source_ref']]
    iid=Engine().new_workflow(store,'SURVEY',name='Synthetic geometric survey',survey_scope=scope)['instance_id']
    for stage in ('S2','S3','S4'):
        survey.start_activity(store,iid,stage,'Explicit synthetic software test of '+stage,max_calls=1,policy=demo.policy())
        result=Engine().run_round(store,iid,executor=demo.executor(),max_tasks=1)
        if not result['tasks']:raise AssertionError(result)
    ready=survey.readiness(store.read_snapshot(),iid)
    if ready['status']!='SYNTHETIC_READY':raise AssertionError(ready)
    frozen=survey.freeze_knowledge(store,iid)
    plan=survey.create_output_plan(store,iid,frozen['snapshot_ref'],profile) if profile else None
    return store,iid,{'source_ref':material['source_ref'],'selected_refs':ready['selected_refs'],
                     'snapshot_ref':frozen['snapshot_ref'],'plan_ref':plan['plan_ref'] if plan else None}


class Survey(unittest.TestCase):
    def test_creation_has_no_target_or_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Engine().create_survey(Path(tmp)/'p',survey.demo_scope(),synthetic=True)
            s=store.read_snapshot();instance=next(iter(s['instances'].values()))
            self.assertEqual(instance['status'],'PAUSED');self.assertIsNone(instance['target_ref'])
            self.assertEqual(s['records'],{});self.assertEqual(s['tasks'],{});self.assertEqual(s['reports'],{})

    def test_native_knowledge_only_and_independent_readiness(self):
        with tempfile.TemporaryDirectory() as tmp:
            store,iid,evidence=ready_survey(Path(tmp)/'p',None);s=store.read_snapshot()
            self.assertEqual(len(s['tasks']),3);self.assertEqual(len(s['accepted_requests']),3)
            self.assertEqual(s['reports'],{});self.assertEqual(s['survey_output_plans'],{})
            self.assertEqual(len(s['qualifications']),0)
            review=next(iter(s['survey_reviews'].values()));task=s['tasks'][review['task_id']]
            self.assertTrue(task['independent']);self.assertEqual(task['model_policy']['reasoning_effort'],'max')
            self.assertEqual(survey.status(s,iid)['readiness']['status'],'SYNTHETIC_READY')

    def test_related_only_invalidation_and_original_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            store,iid,evidence=ready_survey(Path(tmp)/'p');scope=survey.report_scope(store.read_snapshot(),iid,evidence['plan_ref'])
            self.assertTrue(survey.report_current(store.read_snapshot(),scope))
            unrelated=store.commit(changes.prepare_material_input(store.read_snapshot(),b'Unrelated material.','Unrelated','text/plain',blob_get=store.read_blob))
            self.assertTrue(survey.report_current(store.read_snapshot(),scope))
            survey.mark_source(store,iid,unrelated['source_ref'],withdrawn=True,reason='Unrelated source withdrawal test.')
            self.assertTrue(survey.report_current(store.read_snapshot(),scope))
            survey.mark_source(store,iid,evidence['source_ref'],withdrawn=True,reason='Consumed teaching source withdrawal test.')
            self.assertFalse(survey.report_current(store.read_snapshot(),scope))
            self.assertIn(evidence['snapshot_ref'],store.read_snapshot()['survey_snapshots'])

    def test_profiles_are_only_explicit_selections(self):
        with tempfile.TemporaryDirectory() as tmp:
            store,iid,e=ready_survey(Path(tmp)/'p',None)
            with self.assertRaises(PMRSError):survey.report_scope(store.read_snapshot(),iid)
            for profile in survey.PROFILES:
                plan=survey.create_output_plan(store,iid,e['snapshot_ref'],profile)
                scope=survey.report_scope(store.read_snapshot(),iid,plan['plan_ref'])
                self.assertEqual(scope['profiles'],[profile]);self.assertTrue(survey.report_current(store.read_snapshot(),scope))
                self.assertEqual(survey.freeze_for_report(store.read_snapshot(),scope)['survey_output_plan']['language'],'en')
            self.assertEqual(store.read_snapshot()['reports'],{})


class SurveyRecovery(unittest.TestCase):
    def make_search(self,root):
        store=Engine().create_survey(root,survey.demo_scope(),synthetic=True);iid=next(iter(store.read_snapshot()['instances']))
        survey.start_activity(store,iid,'S1','Synthetic bounded search plan',max_calls=1,policy=demo.policy())
        Engine().run_round(store,iid,executor=demo.executor(),max_tasks=1)
        return store,iid,next(iter(store.read_snapshot()['survey_search_plans']))

    def test_actual_plan_mock_acquisition_versions_and_no_repeat(self):
        from research_studio.survey_retrieval import MockProvider
        from research_studio.util import sha
        with tempfile.TemporaryDirectory() as tmp:
            store,iid,plan=self.make_search(Path(tmp)/'p')
            candidate={'candidate_id':'teaching-v1','title':'Explicit synthetic teaching material','version':'teaching-v1',
                       'url':'https://example.invalid/teaching','publication_status':'SYNTHETIC_TEACHING'}
            provider=MockProvider({'finite geometric series':{'status':'SUCCESS','candidates':[candidate]}},
                {'teaching-v1':{'status':'SUCCESS','raw':survey.TEACHING_TEXT.encode(),'attempts':[{'outcome':'SUCCESS'}]}})
            receipt=survey.retrieve(store,iid,plan,provider=provider)
            self.assertEqual(receipt['retrieval']['status'],'COMPLETE');self.assertEqual(len(provider.calls),2)
            self.assertEqual(receipt['retrieval']['network_requests'],0)
            self.assertEqual(receipt['retrieval']['simulated_network_requests'],2)
            ref=receipt['retrieval']['candidates'][0]['source_ref'];s=store.read_snapshot();details=survey.source_details(s,ref)
            self.assertEqual(details['version'],'teaching-v1');self.assertEqual(details['material_sha256'],sha(survey.TEACHING_TEXT.encode()))
            self.assertIsNone(details['original_pdf_sha256']);self.assertEqual(details['access_status'],'FULL_DOCUMENT_AVAILABLE')
            self.assertEqual(s['survey_readings'],{})
            duplicate=survey.retrieve(Store(store.root),iid,plan,provider=provider)
            self.assertEqual(duplicate['outcome'],'EXACT_DUPLICATE');self.assertEqual(len(provider.calls),2)

    def test_query_failure_and_metadata_only_have_honest_states(self):
        from research_studio.survey_retrieval import MockProvider
        with tempfile.TemporaryDirectory() as tmp:
            store,iid,plan=self.make_search(Path(tmp)/'p')
            provider=MockProvider({'finite geometric series':{'status':'RATE_LIMITED','reason':'Controlled 429','candidates':[]}})
            result=survey.retrieve(store,iid,plan,provider=provider)
            self.assertEqual(result['retrieval']['status'],'PARTIAL')
            self.assertEqual(result['retrieval']['queries'][0]['status'],'RATE_LIMITED')
            self.assertEqual(len(store.read_snapshot()['tasks']),1)
        with tempfile.TemporaryDirectory() as tmp:
            store,iid,plan=self.make_search(Path(tmp)/'p')
            provider=MockProvider({'finite geometric series':{'status':'SUCCESS','candidates':[{'candidate_id':'metadata-only',
                'title':'Only metadata','version':'metadata-v1','url':'https://example.invalid/metadata'}]}})
            result=survey.retrieve(store,iid,plan,provider=provider)
            ref=result['retrieval']['candidates'][0]['source_ref']
            self.assertEqual(survey.source_details(store.read_snapshot(),ref)['access_status'],'METADATA_ONLY')
            survey.start_activity(store,iid,'S2','Inspect acquisition limitation',source_refs=[ref],max_calls=1,policy=demo.policy())
            prepared=Engine().prepare(store,iid)['prepared'][0];task=store.read_snapshot()['tasks'][prepared['task_id']]
            from research_studio.util import loads,canonical
            from research_studio.knowledge import locator
            response=loads(survey.demo_response(task,store.read_snapshot()));details=task['survey_context']['source_details'][ref]
            response['payload']['data']['readings']=[{'source_ref':ref,'version':details['version'],'locators':[locator(store.read_blob(details['material_sha256']))],
                'read_scope':'Attempt to mislabel metadata as full original reading.','unread_scope':[],'limitations':[],'claim_refs':[]}]
            with self.assertRaises(PMRSError) as error:Engine().preflight(store,task['task_id'],canonical(response))
            self.assertEqual(error.exception.code,'SURVEY_READING_INVALID')

    def test_lost_retrieval_is_unknown_and_preserves_reservations(self):
        from research_studio.survey_retrieval import MockProvider
        class Interrupted(MockProvider):
            def search(self,*args):raise RuntimeError('Controlled process loss after durable start')
        with tempfile.TemporaryDirectory() as tmp:
            store,iid,plan=self.make_search(Path(tmp)/'p')
            with self.assertRaises(RuntimeError):survey.retrieve(store,iid,plan,provider=Interrupted())
            restarted=Store(store.root);view=survey.status(restarted.read_snapshot(),iid)['retrievals'][0]
            self.assertEqual(view['status'],'UNKNOWN');self.assertEqual(view['network_request_reservations'],0)
            self.assertGreater(view['simulated_network_request_reservations'],0)
            provider=MockProvider();result=survey.retrieve(restarted,iid,plan,provider=provider)
            self.assertEqual(result['retrieval']['status'],'UNKNOWN');self.assertEqual(provider.calls,[])

    def test_handoff_and_ended_update_are_paused(self):
        with tempfile.TemporaryDirectory() as tmp:
            store,iid,e=ready_survey(Path(tmp)/'p');engine=Engine();s=store.read_snapshot()
            target=next(r for r in e['selected_refs'] if s['records'][r]['kind']=='Statement')
            prepared=engine.prepare_handoff(store,iid,'SURVEY_TO_TRW',{'target_refs':[target]})
            decision=engine.decide(store,iid,'ADOPT_HANDOFF','Explicit synthetic handoff',snapshot_commit=store.read_snapshot()['knowledge_commit'])
            adopted=engine.adopt_handoff(store,prepared['handoff_id'],decision);new=store.read_snapshot()['instances'][adopted['instance_id']]
            self.assertEqual(new['kind'],'TRW');self.assertEqual(new['status'],'PAUSED');self.assertEqual(new['target_ref'],target)
            self.assertEqual(new['mission_ids'],[]);self.assertEqual(len(store.read_snapshot()['tasks']),3)
            engine.decide(store,iid,'END','Knowledge only goal completed in fixture',snapshot_commit=store.read_snapshot()['knowledge_commit'])
            with self.assertRaises(PMRSError):survey.start_activity(store,iid,'S4','Restart ended instance',max_calls=1,policy=demo.policy())
            scope=survey.demo_scope();scope.update(entry='UPDATE',parent_instance_id=iid,selected_refs=e['selected_refs'],source_refs=[e['source_ref']])
            update=engine.new_workflow(store,'SURVEY',survey_scope=scope)
            self.assertEqual(update['status'],'PAUSED');self.assertEqual(update['model_calls'],0)
            # Reuse depends on the selected scope and evidence, not saved status.
            self.assertEqual(survey.readiness(store.read_snapshot(),update['instance_id'])['status'],'SYNTHETIC_READY')


class RetrievalBoundary(unittest.TestCase):
    def test_addresses_and_proxy_dns_are_bounded(self):
        from research_studio.survey_retrieval import validate_url
        from unittest.mock import patch
        import socket
        for url in ['http://arxiv.org/pdf/2501.00001','https://127.0.0.1/','file:///etc/passwd',
                    'https://arxiv.org.evil.invalid/pdf/2501.00001','https://arxiv.org/pdf/../../etc/passwd',
                    'https://user:password@arxiv.org/pdf/2501.00001','https://arxiv.org:444/pdf/2501.00001']:
            with self.assertRaises(PMRSError):validate_url(url,resolve=False)
        for address in ['127.0.0.1','10.0.0.1','169.254.169.254','192.168.1.1','::1','fc00::1']:
            with patch('research_studio.survey_retrieval.socket.getaddrinfo',return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',(address,443))]):
                with self.assertRaises(PMRSError):validate_url('https://api.crossref.org/works')
        for address in ['198.18.0.35','2001:2::1b','1.1.1.1']:
            with patch('research_studio.survey_retrieval.socket.getaddrinfo',return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',(address,443))]):
                self.assertEqual(validate_url('https://api.crossref.org/works'),'https://api.crossref.org/works')

class SurveyScopedReadiness(unittest.TestCase):
    def review(self,store,iid,intent,modify):
        from research_studio.runner import FakeExecutor
        from research_studio.util import loads,canonical
        survey.start_activity(store,iid,'S4',intent,max_calls=1,policy=demo.policy())
        def response(task,snapshot):
            row=loads(survey.demo_response(task,snapshot));modify(row['payload']['data'],task,snapshot);return canonical(row)
        Engine().run_round(store,iid,executor=FakeExecutor(response),max_tasks=1)

    def test_version_conflict_and_later_condition_finding_override_old_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            store,iid,e=ready_survey(Path(tmp)/'p');oldscope=survey.report_scope(store.read_snapshot(),iid,e['plan_ref'])
            survey.mark_source(store,iid,e['source_ref'],version_conflict=True,reason='The supplied statement may use a different q domain.')
            errors=survey.readiness(store.read_snapshot(),iid)['errors']
            self.assertIn('SOURCE_VERSION_CONFLICT',[r['code'] for r in errors]);self.assertFalse(survey.report_current(store.read_snapshot(),oldscope))
            survey.mark_source(store,iid,e['source_ref'],reason='Controlling version has been identified; request a fresh review.')
            self.assertEqual(survey.readiness(store.read_snapshot(),iid)['status'],'NEEDS_WORK')
            self.review(store,iid,'Recheck after exact source version resolution',lambda d,t,s:None)
            self.assertEqual(survey.readiness(store.read_snapshot(),iid)['status'],'SYNTHETIC_READY')
            def condition_defect(data,task,snapshot):
                data['verdict']='NEEDS_WORK';data['findings']=[{'code':'HYPOTHESIS_MISMATCH','ref':e['source_ref'],
                    'message':'The source conditions have not been matched to the selected statement.','blocking':True,'return_stage':'S2'}]
            self.review(store,iid,'Independent omission challenge finds a condition mismatch',condition_defect)
            status=survey.readiness(store.read_snapshot(),iid)
            self.assertEqual(status['status'],'NEEDS_WORK');self.assertTrue(any(r['code']=='HYPOTHESIS_MISMATCH' and r['return_stage']=='S2' for r in status['errors']))

    def test_proof_promises_require_actual_independent_checked_steps(self):
        with tempfile.TemporaryDirectory() as tmp:
            store,iid,e=ready_survey(Path(tmp)/'p',None);s=store.read_snapshot()
            argument=next(r for r in e['selected_refs'] if s['records'][r]['kind']=='Argument')
            promise=[{'record_ref':argument,'treatment':'complete','required_steps':['multiply_subtract']}]
            with self.assertRaises(PMRSError) as error:survey.create_output_plan(store,iid,e['snapshot_ref'],'lecture',proof_promises=promise)
            self.assertEqual(error.exception.code,'SURVEY_NOT_READY')
            self.review(store,iid,'Independently check the exact multiply_subtract proof step',lambda d,t,s:d.update(proof_steps={argument:['multiply_subtract']}))
            frozen=survey.freeze_knowledge(store,iid);plan=survey.create_output_plan(store,iid,frozen['snapshot_ref'],'lecture',proof_promises=promise)
            self.assertEqual(plan['plan']['proof_promises'],promise)
            self.assertEqual(store.read_snapshot()['qualifications'],{})

    def test_unselected_pending_branch_is_disclosed_without_global_block(self):
        from research_studio.runner import FakeExecutor
        from research_studio.util import loads,canonical
        from research_studio.knowledge import locator
        with tempfile.TemporaryDirectory() as tmp:
            store=Store.create(Path(tmp)/'p','Synthetic partial selection',synthetic=True)
            material=store.commit(changes.prepare_material_input(store.read_snapshot(),survey.TEACHING_TEXT.encode(),'Synthetic teaching','text/plain',blob_get=store.read_blob))
            scope=survey.demo_scope();q1=scope['questions'][0];q2='Which finite sums admit a different matrix generalization?';scope['questions'].append(q2);scope['source_refs']=[material['source_ref']]
            iid=Engine().new_workflow(store,'SURVEY',survey_scope=scope)['instance_id']
            survey.start_activity(store,iid,'S2','Read synthetic finite-sum material',max_calls=1,policy=demo.policy());Engine().run_round(store,iid,executor=demo.executor(),max_tasks=1)
            survey.start_activity(store,iid,'S3','Organize finite formula and retain unresolved independent branch',max_calls=1,policy=demo.policy())
            def organize(task,snapshot):
                row=loads(survey.demo_response(task,snapshot));kcs=row['payload']['knowledge_change'];body='For which square complex matrices is the corresponding finite-sum identity invertible?'
                loc=locator(body);kcs['operations'].append({'op':'NEW','local_key':'branch','kind':'Statement','context_refs':[],'body':body,
                    'data':{'statement_locator':loc,'scope_context_refs':[],'hypothesis_locators':[],'conclusion_locators':[loc],'quantifier_locators':[], 'form':'QUESTION','representation':'AUTHORED','source_binding':None}})
                row['payload']['data']['coverage'].append({'question':q2,'answer_refs':['local:branch'],'mechanism_refs':[],'boundary_refs':[],
                    'assessment':'PENDING','rationale':'An independent matrix question is recorded but has not been investigated.',
                    'gaps':[{'description':'The matrix scope remains unresolved.','refs':['local:branch'],'disposition':'OPEN','reason':'Outside the explicitly selected scalar formula.','return_stage':'S3'}]})
                return canonical(row)
            Engine().run_round(store,iid,executor=FakeExecutor(organize),max_tasks=1)
            self.review(store,iid,'Review only the scalar question and its complete dependency closure',lambda d,t,s:d.update(coverage_questions=[q1]))
            self.assertEqual(survey.readiness(store.read_snapshot(),iid)['status'],'NEEDS_WORK')
            frozen=survey.freeze_knowledge(store,iid,question_ids=[q1]);self.assertEqual(frozen['snapshot']['readiness']['status'],'SYNTHETIC_READY')
            self.assertTrue(any(r.get('question')==q2 for r in frozen['snapshot']['readiness']['unchecked']))
            plan=survey.create_output_plan(store,iid,frozen['snapshot_ref'],'minimal')
            self.assertEqual(plan['plan']['unselected_questions'],[q2]);self.assertEqual(plan['plan']['question_ids'],[q1])
            self.assertTrue(survey.report_current(store.read_snapshot(),survey.report_scope(store.read_snapshot(),iid,plan['plan_ref'])))

    def test_reading_wrong_version_or_unavailable_extent_is_rejected(self):
        from research_studio.util import loads,canonical
        with tempfile.TemporaryDirectory() as tmp:
            store,iid,e=ready_survey(Path(tmp)/'p',None)
            survey.start_activity(store,iid,'S2','Verify explicit reading bounds again',max_calls=1,policy=demo.policy())
            made=Engine().prepare(store,iid)['prepared'][0];task=store.read_snapshot()['tasks'][made['task_id']]
            row=loads(survey.demo_response(task,store.read_snapshot()));wrong=deepcopy(row)
            wrong['payload']['data']['readings'][0]['version']='invented version'
            with self.assertRaises(PMRSError) as error:Engine().preflight(store,task['task_id'],canonical(wrong))
            self.assertEqual(error.exception.code,'SOURCE_VERSION_CONFLICT')
            wrong=deepcopy(row);wrong['payload']['data']['readings'][0]['locators'][0]['end']+=100000
            with self.assertRaises(PMRSError) as error:Engine().preflight(store,task['task_id'],canonical(wrong))
            self.assertEqual(error.exception.code,'RESPONSE_SCHEMA_INVALID')
            self.assertEqual(store.read_snapshot()['requests'][task['request_id']]['execution_state'],'PREPARED')

    def test_survey_override_is_exact_and_frozen_tasks_do_not_change(self):
        from research_studio import model_policy
        with tempfile.TemporaryDirectory() as tmp:
            store=Engine().create_survey(Path(tmp)/'p',survey.demo_scope(),synthetic=True);iid=next(iter(store.read_snapshot()['instances']))
            survey.start_activity(store,iid,'S1','Bounded synthetic discovery',max_calls=2,policy=demo.policy())
            made=Engine().prepare(store,iid)['prepared'][0];before=deepcopy(store.read_snapshot()['tasks'][made['task_id']])
            override={'explicit':True,'scope':{'workflow_kind':'SURVEY','stage_id':'S1','role':'SEARCH_PLAN','purpose':'DEFAULT'},'reasoning_effort':'max'}
            Engine().update_configuration(store,iid,[override])
            self.assertEqual(before,store.read_snapshot()['tasks'][made['task_id']])
            self.assertEqual(model_policy.resolve('TRW','P4','RESEARCH',require_capability=False)['reasoning_effort'],'max')
            self.assertEqual(model_policy.resolve('TFDW','D1','LEARN',require_capability=False)['reasoning_effort'],'xhigh')
            bad={**override,'reasoning_effort':'ultra'}
            with self.assertRaises(PMRSError) as error:Engine().update_configuration(store,iid,[bad])
            self.assertEqual(error.exception.code,'MODEL_CONFIGURATION_UNSUPPORTED')

class ExtractionBoundary(unittest.TestCase):
    def test_pdf_stream_extraction_stops_on_stdout_or_stderr_limit(self):
        from research_studio import survey_retrieval as retrieval
        from unittest.mock import patch
        import subprocess,sys
        original=subprocess.Popen
        for channel,bytes_count in [('stdout',100000),('stderr',100000)]:
            def oversized(*args,**kwargs):
                return original([sys.executable,'-c',f'import sys;sys.{channel}.write("x"*{bytes_count});sys.{channel}.flush()'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            with patch.object(retrieval,'MAX_BYTES',128),patch.object(retrieval.subprocess,'Popen',side_effect=oversized):
                result=retrieval.extract_pdf(b'%PDF-1.4\ncontrolled process-boundary fixture')
            self.assertEqual(result['status'],'EXTRACTION_FAILED');self.assertEqual(result['reason'],'SURVEY_EXTRACTION_FAILED')
            self.assertIsNone(result['text'])

class PdfProvenance(unittest.TestCase):
    def test_original_pdf_and_registered_text_are_distinct_frozen_inputs(self):
        from research_studio.survey_retrieval import MockProvider
        from research_studio.util import sha,loads
        with tempfile.TemporaryDirectory() as tmp:
            store,iid,plan=SurveyRecovery().make_search(Path(tmp)/'p')
            original=b'%PDF-1.4\nExplicit synthetic transport fixture; not a real manuscript PDF.'
            text=survey.TEACHING_TEXT.encode()
            candidate={'candidate_id':'synthetic-pdf-v1','title':'Synthetic PDF transport fixture','version':'synthetic-pdf-v1','url':'https://example.invalid/source'}
            provider=MockProvider({'finite geometric series':{'status':'SUCCESS','candidates':[candidate]}},
                {'synthetic-pdf-v1':{'status':'SUCCESS','raw':original,'attempts':[{'outcome':'SUCCESS'}],
                                   'extraction':{'text':text,'limitation':'Deterministic extracted-text fixture; real pdftotext is separately smoke tested.'}}})
            result=survey.retrieve(store,iid,plan,provider=provider);ref=result['retrieval']['candidates'][0]['source_ref']
            details=survey.source_details(store.read_snapshot(),ref)
            self.assertEqual(details['original_pdf_sha256'],sha(original));self.assertEqual(details['text_sha256'],sha(text))
            self.assertNotEqual(details['original_pdf_sha256'],details['text_sha256'])
            self.assertEqual(store.read_snapshot()['sources'][ref]['blob_hash'],sha(original))
            self.assertIn(sha(text),store.read_snapshot()['sources'][ref]['extraction_blob_hashes'])
            for stage in ('S2','S3','S4'):
                survey.start_activity(store,iid,stage,'Synthetic PDF provenance '+stage,max_calls=1,source_refs=[ref],policy=demo.policy())
                Engine().run_round(store,iid,executor=demo.executor(),max_tasks=1)
            ready=survey.readiness(store.read_snapshot(),iid);self.assertEqual(ready['status'],'SYNTHETIC_READY')
            task=next(t for t in store.read_snapshot()['tasks'].values() if t['stage_id']=='S2')
            packet=loads(store.read_blob(task['input_packet_ref']))
            self.assertIn(sha(original),packet['source_bytes_base64']);self.assertIn(sha(text),packet['source_bytes_base64'])
            frozen=survey.freeze_knowledge(store,iid)
            plan=survey.create_output_plan(store,iid,frozen['snapshot_ref'],'minimal')
            metadata=survey.freeze_for_report(store.read_snapshot(),survey.report_scope(store.read_snapshot(),iid,plan['plan_ref']))
            self.assertEqual(metadata['source_texts'][ref],sha(text))
            self.assertEqual(store.read_blob(details['original_pdf_sha256']),original)

class UploadedPdf(unittest.TestCase):
    def test_selected_upload_gets_host_extraction_without_creating_model_task(self):
        from unittest.mock import patch
        from research_studio.util import sha
        with tempfile.TemporaryDirectory() as tmp:
            store=Engine().create_survey(Path(tmp)/'p',survey.demo_scope(),synthetic=True);iid=next(iter(store.read_snapshot()['instances']))
            original=b'%PDF-1.4\nExplicit synthetic uploaded PDF fixture'
            uploaded=store.commit(changes.prepare_material_input(store.read_snapshot(),original,'Supplied PDF','application/pdf',blob_get=store.read_blob));ref=uploaded['source_ref']
            with patch('research_studio.survey_retrieval.extract_pdf',return_value={'status':'TEXT_EXTRACTED','text':survey.TEACHING_TEXT.encode(),'limitation':'Synthetic extraction fixture.'}) as extract:
                result=survey.start_activity(store,iid,'S2','Read this selected uploaded PDF',source_refs=[ref],max_calls=1,policy=demo.policy())
            self.assertEqual(extract.call_count,1);self.assertEqual(result['model_calls'],0)
            s=store.read_snapshot();self.assertEqual(s['tasks'],{})
            details=survey.source_details(s,ref);self.assertEqual(details['original_pdf_sha256'],sha(original))
            self.assertEqual(details['text_sha256'],sha(survey.TEACHING_TEXT.encode()));self.assertTrue(details['text_source_ref'])
            Engine().run_round(store,iid,executor=demo.executor(),max_tasks=1)
            self.assertEqual(len(store.read_snapshot()['survey_readings']),1)
