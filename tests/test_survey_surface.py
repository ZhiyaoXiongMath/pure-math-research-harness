"""Native Survey workspace controls and origin-independent display preferences."""
from contextlib import closing
from pathlib import Path
import http.client
import json
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from research_studio.workspace import Workspace
from research_studio.ui import app_handler
from research_studio.util import canonical, PMRSError


class LocaleHostTests(unittest.TestCase):
    def test_preference_survives_new_server_and_changed_port_without_research_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'workspace';w=Workspace(root)
            made=w.action('create',{'kind':'TRW','title':'Locale isolation','text':'For every integer n, n + 0 = n.'},'locale-isolation-1234567890')
            store=w.project(made['project']);before=store.read_snapshot();receipts=w.operations()
            ports=[]
            for iteration in range(2):
                w=Workspace(root);server=ThreadingHTTPServer(('127.0.0.1',0),app_handler(w,'test-bootstrap'))
                thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                try:
                    port=server.server_port;ports.append(port)
                    headers={'Content-Type':'application/json','Origin':f'http://127.0.0.1:{port}'}
                    def request(method,path,value=None,custom=None):
                        with closing(http.client.HTTPConnection('127.0.0.1',port,timeout=10)) as c:
                            c.request(method,path,canonical(value) if value is not None else None,{**headers,**(custom or {})})
                            r=c.getresponse();return r.status,json.loads(r.read()),dict(r.getheaders())
                    _,session,response_headers=request('POST','/api/session',{'token':'test-bootstrap'})
                    self.assertEqual(session['ui_locale'],'en' if iteration==0 else 'zh-CN')
                    headers.update(Cookie=response_headers['Set-Cookie'].split(';')[0],**{'X-PMRS-CSRF':session['csrf'],'X-PMRS-Workspace':w.workspace_id})
                    if iteration==0:
                        code,error,_=request('POST','/api/preferences',{'ui_locale':'zh-CN'},{'X-PMRS-CSRF':'wrong'})
                        self.assertEqual((code,error['error']),(403,'CSRF_INVALID'))
                        code,result,_=request('POST','/api/preferences',{'ui_locale':'zh-CN'})
                        self.assertEqual((code,result['ui_locale'],result['model_calls']),(200,'zh-CN',0))
                    self.assertEqual(request('GET','/api/preferences')[1]['ui_locale'],'zh-CN')
                    self.assertEqual(request('POST','/api/preferences',{'ui_locale':'fr'})[0],400)
                    self.assertEqual(store.read_snapshot(),before);self.assertEqual(w.operations(),receipts)
                finally:server.shutdown();server.server_close();thread.join(5)
            self.assertEqual((root/'runtime/preferences.json').stat().st_mode&0o777,0o600)


class SurveyWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.w=Workspace(Path(self.temp.name)/'workspace')

    def ready(self):
        from tests.test_survey import ready_survey
        self.key='WP-'+'a'*32
        self.store,self.iid,self.evidence=ready_survey(self.w.root/'projects'/self.key)
        return {'project':self.key,'instance':self.iid}

    def test_create_named_paused_survey_and_independent_explicit_new_operation(self):
        p={'kind':'SURVEY','title':'Teaching project','name':'Finite sums','survey_scope':{
            'topic':'Finite geometric sums','questions':['What happens at q=1?'],'delivery_goal':'KNOWLEDGE_ONLY'}}
        first=self.w.action('create',p,'survey-create-1234567890')
        self.assertEqual(self.w.action('create',p,'survey-create-1234567890'),first)
        s=self.w.project(first['project']).read_snapshot();instance=s['instances'][first['instance_id']]
        self.assertEqual(instance['name'],'Finite sums');self.assertEqual(instance['status'],'PAUSED')
        self.assertIsNone(instance['target_ref']);self.assertEqual(s['usage']['model_calls'],0);self.assertFalse(s['reports'])
        second=self.w.action('create',p,'survey-create-new-1234567890')
        self.assertNotEqual(first['project'],second['project'])

    def test_survey_handoffs_preserve_precise_inputs_and_never_start(self):
        from research_studio import demo
        base=self.ready();state=self.store.read_snapshot()
        target=next(ref for ref in self.evidence['selected_refs'] if state['records'][ref]['kind']=='Statement')
        calls=state['usage']['model_calls'];tasks=state['tasks']
        for kind in ('TRW','TFDW'):
            payload={**base,'direction':'SURVEY_TO_'+kind,'target_ref':target,'name':'Paused '+kind,
                     'note':'Adopt this exact teaching statement with its source and context.'}
            if kind=='TFDW':payload['discovery_scope']=demo.discovery_scope('Explore precise finite-sum variants.')
            result=self.w.action('handoff',payload,'survey-handoff-'+kind.lower()+'-1234567890')
            s=self.store.read_snapshot();adopted=s['instances'][result['instance_id']]
            self.assertEqual((adopted['kind'],adopted['status']),(kind,'PAUSED'))
            self.assertEqual(adopted['mission_ids'],[]);self.assertFalse(s['qualifications'])
            if kind=='TRW':self.assertEqual(adopted['target_ref'],target)
            self.assertEqual(s['usage']['model_calls'],calls);self.assertEqual(s['tasks'],tasks)
        self.assertTrue(self.store.audit()['valid'])

    def test_selected_output_authorization_is_host_only_and_dispatch_pins_report(self):
        base=self.ready();before=self.store.read_snapshot()['usage']['model_calls']
        with patch.object(self.w,'launch') as launch:
            granted=self.w.action('survey-activity',{**base,'stage':'S5','intent':'Authorize only the selected minimal English teaching survey.',
                'max_calls':3},'survey-output-budget-1234567890')
            launch.assert_not_called();self.assertEqual(granted['model_calls'],0)
            result=self.w.action('report',{**base,'plan_ref':self.evidence['plan_ref'],'profiles':['minimal']},'survey-output-1234567890')
            launch.assert_called_once_with(self.key,self.iid,report=True,report_id=result['report_id'])
        state=self.store.read_snapshot();entry=state['reports'][result['report_id']]
        self.assertEqual(list(entry['profiles']),['minimal']);self.assertEqual(state['usage']['model_calls'],before)
        inputs=self.w.workflow_inputs(self.key)
        self.assertTrue(inputs['records']);self.assertTrue(all(r['kind']=='Statement' for r in inputs['statements']))

    def test_progress_updates_host_execution_without_knowledge_commit_change(self):
        base=self.ready();before=self.w.progress(self.key,self.iid)
        self.w.jobs[(self.key,self.iid)]={'state':'RUNNING','instance_id':self.iid,'kind':'RESEARCH'}
        after=self.w.progress(self.key,self.iid)
        self.assertEqual(before['commit'],after['commit'])
        self.assertEqual(after['project_execution']['running_coordinators'],1)
        self.assertNotEqual(before['control_fingerprint'],after['control_fingerprint'])
        self.assertEqual(after['survey']['instance_id'],self.iid)
