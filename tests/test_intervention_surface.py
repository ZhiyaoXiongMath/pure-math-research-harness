"""Finite local intervention acceptance: native Web/CLI plans and resource continuation."""
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import closing
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from research_studio import demo
from research_studio.workspace import Workspace
from research_studio.ui import app_handler
from research_studio.util import canonical


class InterventionSurface(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.w=Workspace(Path(self.tmp.name)/'workspace')
        self.server=ThreadingHTTPServer(('127.0.0.1',0),app_handler(self.w,'synthetic-bootstrap'))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.origin='http://127.0.0.1:'+str(self.server.server_port);self.headers={}
        _,session,headers=self.req('POST','/api/session',{'token':'synthetic-bootstrap'})
        self.headers={'Cookie':headers['Set-Cookie'].split(';')[0],'X-PMRS-CSRF':session['csrf']}
        self.ordinal=0
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
    def req(self,method,path,p=None):
        headers={'Origin':self.origin,'Content-Type':'application/json',**self.headers}
        if hasattr(self,'ordinal'):
            self.ordinal+=1;headers['Idempotency-Key']='intervention-operation-'+str(self.ordinal).zfill(8)
        with closing(http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=15)) as client:
            client.request(method,path,canonical(p) if p is not None else None,headers)
            response=client.getresponse();raw=response.read()
            return response.status,json.loads(raw) if response.getheader('Content-Type','').startswith('application/json') else raw,dict(response.getheaders())
    def create(self,kind):
        payload={'kind':kind,'title':'Synthetic '+kind,'text':demo.ARITHMETIC.decode(),
            'survey_scope':{'topic':'Finite sums','questions':['What is the role of zero?'],'delivery_goal':'KNOWLEDGE_ONLY'}}
        code,result,_=self.req('POST','/api/action/example',payload);self.assertEqual(code,200,result)
        return result
    def test_http_all_three_plans_are_real_native_authorizations_without_calls(self):
        for kind,stage,role in [('TRW','P3','PLAN'),('TFDW','D1','LEARN'),('SURVEY','S1','SEARCH_PLAN')]:
            made=self.create(kind);store=self.w.project(made['project'])
            payload={'project':made['project'],'instance':made['instance_id'],'intent':'Finite explicit teaching plan',
                'max_calls':8,'max_workers':8,'run':False,
                'items':[{'key':'first','stage':stage,'role':role,'intent':'Investigate the additive identity using the required definitions.'}]}
            with patch.object(self.w,'launch') as launch,patch('research_studio.runner.CodexExecutor.execute',side_effect=AssertionError('no real model')):
                code,result,_=self.req('POST','/api/action/plan-work',payload)
                self.assertEqual(code,200,result);launch.assert_not_called()
            snapshot=store.read_snapshot();self.assertEqual(snapshot['max_workers'],8)
            self.assertEqual(result['model_calls'],0);self.assertFalse(snapshot['requests'])
            binding=result['bindings'][0];consumer=snapshot['obligations'][binding['obligation_id']]['definition']['consumer_bindings'][0]
            self.assertEqual((consumer['stage_id'],consumer['role']),(stage,role))
            _,status,_=self.req('GET','/api/status?project='+made['project']+'&instance='+made['instance_id'])
            self.assertEqual((status['budget']['project_max_workers'],status['budget']['host_model_pool']),(8,10))
            self.assertEqual(status['pending_work'][0]['binding_id'],binding['binding_id'])
            before_grants=snapshot['budget_grants']
            code,deferred,_=self.req('POST','/api/action/defer-work',{'project':made['project'],'instance':made['instance_id'],
                'binding_id':binding['binding_id'],'reason':'Explicit finite test deferral; no claim of scientific completion.'})
            self.assertEqual(code,200,deferred);self.assertEqual(deferred['model_calls'],0)
            after=store.read_snapshot();self.assertIn(binding['binding_id'],after['retired_consumers'])
            self.assertEqual(after['budget_grants'],before_grants);self.assertFalse(after['requests'])
            _,status,_=self.req('GET','/api/status?project='+made['project']+'&instance='+made['instance_id'])
            self.assertEqual(status['pending_work'],[])
    def test_cli_plan_keeps_lower_project_limit_and_rejects_nine(self):
        made=self.create('TRW');store=self.w.project(made['project']);iid=made['instance_id']
        self.w.engine.plan_work(store,iid,'Two-slot initial authorization',[{'key':'a','stage':'P3','role':'PLAN','intent':'Compare routes to the additive identity.'}],max_calls=4,max_workers=2,policy=demo.policy())
        items=Path(self.tmp.name)/'items.json';items.write_text(json.dumps([{'key':'b','stage':'P7','role':'DIRECT','intent':'Analyze the identity directly from the group axioms.','framework_scope':'Abelian group identity uniqueness'}]))
        command=[sys.executable,'-m','research_studio','plan-work',str(store.root),'--instance',iid,'--intent','Preserve saved concurrency','--items',str(items),'--max-calls','3']
        run=subprocess.run(command,text=True,capture_output=True);self.assertEqual(run.returncode,0,run.stderr)
        result=json.loads(run.stdout);self.assertEqual(result['model_calls'],0)
        snapshot=store.read_snapshot();self.assertEqual(snapshot['max_workers'],2);self.assertFalse(snapshot['requests'])
        bad=subprocess.run(command+['--max-workers','9'],text=True,capture_output=True);self.assertNotEqual(bad.returncode,0)
        self.assertEqual(store.read_snapshot(),snapshot)
        deferred=subprocess.run([sys.executable,'-m','research_studio','defer-work',str(store.root),
            '--instance',iid,'--binding',result['bindings'][0]['binding_id'],'--reason','Preserve this explicit deferred duty.'],text=True,capture_output=True)
        self.assertEqual(deferred.returncode,0,deferred.stderr);self.assertEqual(json.loads(deferred.stdout)['model_calls'],0)
        self.assertEqual(store.read_snapshot()['budget_grants'],snapshot['budget_grants'])
    def test_normal_http_start_drives_three_workflows_without_manual_stages(self):
        from tests.test_autoflow import response
        from research_studio.runner import FakeExecutor
        from research_studio.survey import TEACHING_TEXT
        for kind in ('TRW','TFDW','SURVEY'):
            with self.subTest(kind=kind):
                made=self.create(kind);store=self.w.project(made['project']);sources=[]
                if kind=='SURVEY':
                    code,source,_=self.req('POST','/api/action/add-source',{'project':made['project'],'instance':made['instance_id'],
                        'text':TEACHING_TEXT,'filename':'Selected synthetic teaching material','media_type':'text/plain'})
                    self.assertEqual(code,200,source);sources=[source['source_ref']]
                fake=FakeExecutor(response if kind!='TFDW' else demo.response)
                with patch('research_studio.demo.executor',return_value=fake):
                    code,result,_=self.req('POST','/api/action/start',{'project':made['project'],'instance':made['instance_id'],
                        'intent':'Investigate this exact finite teaching objective.','max_calls':8,'max_workers':2,'source_refs':sources})
                    self.assertEqual(code,200,result)
                    deadline=time.monotonic()+20
                    while self.w.live_jobs() and time.monotonic()<deadline:time.sleep(.02)
                self.assertFalse(self.w.live_jobs());snapshot=store.read_snapshot()
                _,status,_=self.req('GET','/api/status?project='+made['project']+'&instance='+made['instance_id'])
                self.assertIn(status['round_result']['state'],{'READY_FOR_DECISION','HUMAN_INPUT_REQUIRED','BUDGET_EXHAUSTED'},status)
                self.assertFalse(snapshot['reports']);self.assertEqual(len(snapshot['missions']),1)
                self.assertGreater(fake.calls,0);self.assertEqual(fake.network_calls,0)
                if kind=='TRW':self.assertTrue({'P1','P2','P3','P4','P11'} <= {t['stage_id'] for t in snapshot['tasks'].values()})
                if kind=='SURVEY':self.assertTrue(snapshot['survey_snapshots'])
                self.assertTrue(snapshot['round_deliveries']);store.audit()

    def test_web_resource_wait_continues_same_authorized_operation(self):
        made=self.create('TRW');store=self.w.project(made['project']);iid=made['instance_id']
        self.w.engine.start_round(store,iid,'Synthetic resource wait',max_calls=1,policy=demo.policy())
        seen=[]
        def operation(current,instance_id,**options):
            seen.append((str(current.root),instance_id))
            return {'state':'RESOURCE_WAIT','request_id':'same-frozen-request','model_calls':0} if len(seen)==1 else {'state':'WAIT','tasks':[],'model_calls':0}
        with patch.object(self.w.engine,'run_round',side_effect=operation):
            job=self.w.launch(made['project'],iid);deadline=time.monotonic()+5
            while self.w.live_jobs() and time.monotonic()<deadline:time.sleep(.02)
        self.assertEqual(len(seen),2);self.assertEqual(seen[0],seen[1]);self.assertEqual(job['state'],'WAITING')
        self.assertEqual(store.read_snapshot()['usage']['model_calls'],0)

if __name__=='__main__':unittest.main()
