"""Finite real HTTP → native assistant/report ledger acceptance; no paid calls."""
from contextlib import closing
import http.client
import json
import time
import unittest
from unittest.mock import patch

from research_studio import assistant, demo, reports, scheduler, execution
from research_studio.runner import FakeExecutor
from research_studio.util import canonical
from research_studio.workspace import Workspace
from tests import test_intervention_surface as surface_helpers
from tests.test_assistant_reports import paused_report, controlled_response


class AssistantSurface(unittest.TestCase):
    setUp=surface_helpers.InterventionSurface.setUp
    tearDown=surface_helpers.InterventionSurface.tearDown
    create=surface_helpers.InterventionSurface.create

    def req(self,method,path,p=None,*,operation=None):
        headers={'Origin':self.origin,'Content-Type':'application/json',**self.headers}
        if hasattr(self,'ordinal'):
            self.ordinal+=1
            headers['Idempotency-Key']=operation or 'assistant-surface-operation-'+str(self.ordinal).zfill(8)
        with closing(http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=20)) as client:
            client.request(method,path,canonical(p) if p is not None else None,headers)
            response=client.getresponse();raw=response.read()
            return response.status,json.loads(raw) if response.getheader('Content-Type','').startswith('application/json') else raw,dict(response.getheaders())

    def action(self,name,p,**options):
        code,result,_=self.req('POST','/api/action/'+name,p,**options)
        self.assertEqual(code,200,result);return result

    def idle(self):
        deadline=time.monotonic()+40
        while self.w.live_jobs() and time.monotonic()<deadline:time.sleep(.02)
        self.assertFalse(self.w.live_jobs(),self.w.assistant_jobs)

    def status(self,project,sid):
        code,value,_=self.req('GET','/api/assistant?project='+project+'&session_id='+sid)
        self.assertEqual(code,200,value);return value

    def test_a1_project_task_report_entry_and_history_do_not_execute(self):
        project='WP-'+'a'*32
        store,iid,rid=paused_report(self.w.root/'projects'/project)
        before=store.read_snapshot();task=next(iter(before['tasks'].values()))
        target=reports.revision_target(store,iid,rid,'lecture')
        contexts=[{}, {'instance_id':iid,'task_id':task['task_id']},
                  {'report_id':rid,'profile':'lecture','revision':0,'body_hash':target['raw_body_sha256']}]
        with patch('research_studio.runner.CodexExecutor.execute',side_effect=AssertionError('Paid model forbidden')):
            for context in contexts:
                session=self.action('assistant-open',{'project':project,'context':context});sid=session['session_id']
                for _ in range(2):
                    state=self.status(project,sid);self.assertEqual(state['model_calls'],0)
                    self.assertEqual(state['budget']['remaining'],0)
                code,evidence,_=self.req('GET','/api/assistant-evidence?project='+project+'&session_id='+sid)
                self.assertEqual(code,200,evidence);self.assertEqual(evidence['model_calls'],0)
            code,_,_=self.req('GET','/static/messages.js');self.assertEqual(code,200)
        after=store.read_snapshot()
        for key in ('requests','tasks','missions','records','reports','project_budget','instances'):
            self.assertEqual(before[key],after[key],key)
        self.assertFalse(self.w.live_jobs());store.audit()

    def test_a2_a5_question_idempotency_operation_query_and_backend_restart(self):
        made=self.create('TRW');project=made['project'];store=self.w.project(project)
        self.w.engine.pause(store,made['instance_id'],'Assistant diagnosis must not restart research.')
        before=store.read_snapshot()
        session=self.action('assistant-open',{'project':project,'instance':made['instance_id']});sid=session['session_id']
        self.action('assistant-authorize',{'project':project,'session_id':sid,'max_calls':1})
        p={'project':project,'session_id':sid,'text':'Why is this workflow paused? Explain the facts only; do not modify the report or research.'}
        with patch('research_studio.runner.CodexExecutor.execute',side_effect=AssertionError('Paid model forbidden')):
            sent=self.action('assistant-send',p,operation='original-assistant-send-0001');self.idle()
            duplicate=self.action('assistant-send',p,operation='original-assistant-send-0001')
            self.assertEqual(sent,duplicate)
            code,op,_=self.req('GET','/api/operation?key=original-assistant-send-0001')
            self.assertEqual(code,200,op);self.assertEqual(op['state'],'COMPLETED')
            current=self.status(project,sid)
            self.assertEqual(current['turns'][0]['acceptance_state'],'ACCEPTED',current)
            restored=Workspace(self.w.root)
            self.assertEqual(restored.assistant_status(project,sid)['turns'][0]['request_id'],current['turns'][0]['request_id'])
            self.action('assistant-recover',{'project':project,'session_id':sid,'turn_id':sent['turn_id']});self.idle()
        after=store.read_snapshot();self.assertEqual(len(after['requests']),len(before['requests'])+1)
        for key in ('missions','records','reports','project_budget','instances'):
            self.assertEqual(before[key],after[key],key)
        task=next(t for t in after['tasks'].values() if t.get('purpose')=='PROJECT_ASSISTANT')
        self.assertEqual(task['model_policy']['model'],'gpt-6-astra')
        self.assertEqual(task['model_policy']['reasoning_effort'],'xhigh')
        self.assertIsNone(task.get('stage_id'));self.assertEqual(after['usage']['model_calls'],0)
        store.audit()

    def test_a3_a4_a7_multiturn_http_report_budget_recovery_and_exact_versions(self):
        project='WP-'+'b'*32;store,iid,rid=paused_report(self.w.root/'projects'/project)
        before=store.read_snapshot();target=reports.revision_target(store,iid,rid,'lecture')
        old=store.read_blob(target['raw_body_sha256']);selected=target['sections'][2]
        sid=self.action('assistant-open',{'project':project,'report_id':rid,'profile':'lecture',
            'revision':0,'body_hash':target['raw_body_sha256']})['session_id']
        self.action('assistant-authorize',{'project':project,'session_id':sid,'max_calls':3})
        assistant_executor=FakeExecutor(controlled_response(store));report_executor=FakeExecutor(controlled_response(store))
        with patch('research_studio.runner.CodexExecutor.execute',side_effect=AssertionError('Paid model forbidden')), \
             patch('research_studio.assistant.demo_executor',return_value=assistant_executor), \
             patch('research_studio.demo.executor',return_value=report_executor):
            for text in ('Discussion only: retain the alpha explanation in the proposed edit.',
                         'Discussion only: also retain the beta clarification, and leave all other sections unchanged.'):
                self.action('assistant-send',{'project':project,'session_id':sid,'text':text});self.idle()
                self.assertEqual(store.read_snapshot()['reports'],before['reports'])
            sent=self.action('assistant-send',{'project':project,'session_id':sid,
                'text':'Please revise only section 3 using the two earlier requirements. Leave every other section unchanged.'})
            self.idle();status=self.status(project,sid)
            job=next(j for j in status['jobs'] if j['turn_id']==sent['turn_id'])
            self.assertEqual(job['state'],'WAITING_REPORT_BUDGET',job)
            self.assertEqual(report_executor.calls,0)
            self.action('assistant-recover',{'project':project,'session_id':sid,'turn_id':sent['turn_id'],'report_calls':1},
                        operation='original-report-budget-0001');self.idle()
            status=self.status(project,sid);job=next(j for j in status['jobs'] if j['turn_id']==sent['turn_id'])
            self.assertEqual(job['state'],'WAITING_REPORT_BUDGET',job)
            self.assertEqual(report_executor.calls,1)
            self.action('assistant-recover',{'project':project,'session_id':sid,'turn_id':sent['turn_id'],'report_calls':5},
                        operation='original-report-budget-0002');self.idle()
            status=self.status(project,sid);job=next(j for j in status['jobs'] if j['turn_id']==sent['turn_id'])
            self.assertEqual(job['state'],'COMPLETED',job)
            self.assertEqual(assistant_executor.calls,3);self.assertEqual(report_executor.calls,6)
            # Refresh and recovery find the exact completed revision, never submit another author.
            self.action('assistant-recover',{'project':project,'session_id':sid,'turn_id':sent['turn_id']});self.idle()
            self.assertEqual((assistant_executor.calls,report_executor.calls),(3,6))
        after=store.read_snapshot();profile=after['reports'][rid]['profiles']['lecture']
        new=store.read_blob(profile['raw_body_sha256'])
        self.assertEqual(profile['revision'],1);self.assertTrue(new.startswith(old[:selected['start_byte']]))
        self.assertTrue(new.endswith(old[selected['end_byte']:]))
        self.assertIn(b'alpha requirement',new);self.assertIn(b'beta clarification',new)
        self.assertTrue(profile['revision_check']['non_target_bytes_preserved'])
        self.assertEqual(profile['semantic']['revision_check']['verdict'],'SATISFIED')
        for key in ('records','project_budget','instances'):self.assertEqual(before[key],after[key],key)
        self.assertEqual(set(after['missions']),set(before['missions']))
        for mid,mission in after['missions'].items():
            self.assertEqual({k:v for k,v in mission.items() if k!='stage_visit_ids'},
                {k:v for k,v in before['missions'][mid].items() if k!='stage_visit_ids'})
        self.assertTrue(all(after['visits'][vid]['stage_id']=='P13' for vid in set(after['visits'])-set(before['visits'])))
        self.assertEqual(scheduler.project_remaining(after),0)
        surfaced=self.status(project,sid);versions=surfaced['report_versions']
        self.assertEqual(surfaced['report_budget']['remaining'],0)
        self.assertEqual(surfaced['turns'][-1]['action']['checks']['lecture']['requirements']['verdict'],'SATISFIED')
        self.assertTrue(surfaced['turns'][-1]['action']['change_summary']['non_target_bytes_preserved'])
        self.assertEqual({(v['profile'],v['revision']) for v in versions},{('lecture',0),('lecture',1),('minimal',0),('minimal',1)})
        for version in versions:
            code,pdf,_=self.req('GET',version['url']);self.assertEqual(code,200);self.assertTrue(pdf.startswith(b'%PDF-'))
        code,progress,_=self.req('GET','/api/progress?project='+project+'&instance='+iid)
        self.assertEqual(code,200,progress);self.assertEqual(progress['budget']['remaining_calls'],0)
        self.assertEqual(after['usage']['model_calls'],0);store.audit()

    def test_a2_unknown_task_http_diagnosis_never_resends_science(self):
        from tests.test_model_pool import fixture, prepare
        project='WP-'+'d'*32;store,iid,policy=fixture(self.w.root/'projects'/project,1,2)
        science=prepare(store,iid,policy)[0]
        reserved=execution.reserve(store,science['request_id'],execution_kind='SYNTHETIC_TEST_ONLY')
        store.commit_execution(execution.event('UNKNOWN',{'request_id':science['request_id'],
            'execution_id':reserved['execution_id'],'reason':'Finite controlled missing outcome evidence.'}))
        self.w.engine.pause(store,iid,'Keep the uncertain original request paused.');before=store.read_snapshot()
        sid=self.action('assistant-open',{'project':project,'task_id':science['task_id']})['session_id']
        self.action('assistant-authorize',{'project':project,'session_id':sid,'max_calls':1})
        with patch('research_studio.runner.CodexExecutor.execute',side_effect=AssertionError('Paid model forbidden')):
            self.action('assistant-send',{'project':project,'session_id':sid,
                'text':'Why is this request UNKNOWN? Explain its actual evidence; do not send research.'});self.idle()
        status=self.status(project,sid);structured=status['messages'][-1]['structured']
        self.assertTrue(structured['unknowns']);self.assertIn('Do not blindly resend UNKNOWN',structured['advice'][0]['text'])
        after=store.read_snapshot();self.assertEqual(after['requests'][science['request_id']],before['requests'][science['request_id']])
        self.assertEqual(len(after['requests']),len(before['requests'])+1)
        for field in ('instances','missions','records','project_budget'):self.assertEqual(after[field],before[field])
        store.audit()


if __name__=='__main__':unittest.main()
