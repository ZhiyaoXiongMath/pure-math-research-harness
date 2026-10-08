"""Durable outcome recovery across real desktop restarts and changed origins."""
from contextlib import closing
from http.server import ThreadingHTTPServer
import http.client
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from research_studio.ui import app_handler
from research_studio.util import PMRSError, atomic, canonical, identity
from research_studio.workspace import Workspace


class DurableOperationRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.w=Workspace(Path(self.tmp.name)/'workspace')
        self.payload={'kind':'TRW','title':'恢复结果','text':'For every integer n, n + 0 = n.'}

    def test_discovery_acknowledgement_and_explicit_new_operation(self):
        key='lost-response-1234567890'
        first=self.w.action('create',self.payload,key);store=self.w.project(first['project']);before=store.read_snapshot()
        restarted=Workspace(self.w.root)
        self.assertEqual(restarted.workspace_id,self.w.workspace_id)
        rows=restarted.operations();self.assertEqual(len(rows['operations']),1)
        row=rows['operations'][0];self.assertEqual(row['id'],identity(key));self.assertEqual(row['name'],'create')
        self.assertEqual(row['payload'],{});self.assertNotIn('text',canonical(rows).decode())
        receipt=restarted.operation_status(operation_id=row['id'])
        self.assertEqual(receipt['result'],first);self.assertEqual(receipt['operation']['id'],row['id'])
        self.assertFalse(receipt['acknowledged'])
        original=(self.w.root/'actions'/(row['id']+'.json')).read_bytes()
        self.assertEqual(restarted.action('create',self.payload,key),first)
        with self.assertRaisesRegex(PMRSError,'ACTION_CONFLICT'):restarted.acknowledge_operation(row['id'],'incorrect')
        ack=restarted.acknowledge_operation(row['id'],row['digest'])
        self.assertEqual(restarted.acknowledge_operation(row['id'],row['digest']),ack)
        self.assertEqual(restarted.operations()['operations'],[])
        self.assertTrue(restarted.operation_status(key)['acknowledged'])
        self.assertEqual((self.w.root/'actions'/(row['id']+'.json')).read_bytes(),original)
        self.assertEqual(store.read_snapshot(),before)
        new=restarted.action('create',self.payload,'explicit-new-1234567890')
        self.assertNotEqual(new['project'],first['project']);self.assertEqual(len(restarted.list()['projects']),2)
        self.assertEqual(len(restarted.operations()['operations']),1)
        self.assertNotEqual(Workspace(Path(self.tmp.name)/'other').workspace_id,self.w.workspace_id)
        self.assertEqual((self.w.root/'runtime/workspace.json').stat().st_mode&0o777,0o600)

    def test_pending_and_partial_failure_are_never_replayed_by_discovery(self):
        key='pending-operation-1234567890'
        with patch.object(self.w,'_action',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):self.w.action('create',self.payload,key)
        row=self.w.operations()['operations'][0];self.assertEqual(row['state'],'PENDING')
        with self.assertRaisesRegex(PMRSError,'ACTION_UNCERTAIN'):self.w.acknowledge_operation(row['id'],row['digest'])
        with self.assertRaisesRegex(PMRSError,'ACTION_UNCERTAIN'):self.w.action('create',self.payload,key)
        self.assertEqual(self.w.list()['projects'],[])
        action=self.w._action
        def partially_completed(name,p,k):
            action(name,p,k)
            raise OSError('Response preparation failed after the native commit')
        with patch.object(self.w,'_action',side_effect=partially_completed):
            with self.assertRaises(OSError):self.w.action('create',self.payload,'partial-failure-1234567890')
        restarted=Workspace(self.w.root);self.assertEqual(len(restarted.list()['projects']),1)
        snapshot=restarted.project(restarted.list()['projects'][0]['key']).read_snapshot()
        failed=next(row for row in restarted.operations()['operations'] if row['state']=='FAILED')
        with patch.object(restarted,'_action',side_effect=AssertionError('Read or acknowledgement must not dispatch')):
            self.assertEqual(restarted.operation_status(operation_id=failed['id'])['state'],'FAILED')
            restarted.acknowledge_operation(failed['id'],failed['digest'])
            with self.assertRaisesRegex(PMRSError,'ACTION_UNCERTAIN'):restarted.action('create',self.payload,'partial-failure-1234567890')
        self.assertEqual(restarted.project(restarted.list()['projects'][0]['key']).read_snapshot(),snapshot)
        self.assertEqual([r['state'] for r in restarted.operations()['operations']],['PENDING'])

    def test_missing_receipt_metadata_is_rejected_without_replaying(self):
        key='invalid-metadata-request-1234567890'
        self.w.action('create',self.payload,key)
        oid=identity(key)
        path=self.w.root/'actions'/(oid+'.json');receipt=json.loads(path.read_text());receipt.pop('operation')
        atomic(path,canonical(receipt));raw=path.read_bytes()
        with self.assertRaisesRegex(PMRSError,'OPERATION_RECEIPT_INVALID'):self.w.operation_status(key)
        self.assertEqual(path.read_bytes(),raw)


class OperationRecoveryHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.w=Workspace(Path(self.tmp.name)/'workspace')
        self.server=ThreadingHTTPServer(('127.0.0.1',0),app_handler(self.w,'bootstrap-secret'))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.stop)
        self.port=self.server.server_port;self.origin='http://127.0.0.1:'+str(self.port)
        self.cookie='';self.csrf='';self.workspace_id=self.w.workspace_id
        code,response,headers=self.req('POST','/api/session',{'token':'bootstrap-secret'},authenticated=False)
        self.assertEqual(code,200);self.assertEqual(response['workspace_id'],self.workspace_id)
        self.cookie=headers['Set-Cookie'].split(';')[0];self.csrf=response['csrf']

    def stop(self):
        self.server.shutdown();self.server.server_close();self.thread.join(5)

    def req(self,method,path,data=None,*,authenticated=True,origin=None,csrf=None,workspace_id=None,key='http-operation-1234567890'):
        headers={'Origin':origin or self.origin,'Content-Type':'application/json','Idempotency-Key':key}
        if authenticated:headers.update({'Cookie':self.cookie,'X-PMRS-CSRF':self.csrf if csrf is None else csrf,
                                         'X-PMRS-Workspace':workspace_id or self.workspace_id})
        with closing(http.client.HTTPConnection('127.0.0.1',self.port,timeout=10)) as c:
            c.request(method,path,canonical(data) if data is not None else None,headers)
            r=c.getresponse();return r.status,json.loads(r.read()),dict(r.getheaders())

    def test_authenticated_discovery_and_ack_obey_all_write_boundaries(self):
        payload={'kind':'TRW','title':'HTTP recovery','text':'For every integer n, n + 0 = n.'}
        status,created,_=self.req('POST','/api/action/create',payload);self.assertEqual(status,200)
        status,listing,_=self.req('GET','/api/operations');self.assertEqual(status,200)
        row=listing['operations'][0];body={'id':row['id'],'digest':row['digest']}
        receipt=self.req('GET','/api/operation?id='+row['id'])[1]
        self.assertEqual(receipt['result'],created)
        for options,error in (({'authenticated':False},'SESSION_REQUIRED'),({'csrf':'bad'},'CSRF_INVALID'),
                              ({'origin':'http://127.0.0.1:1'},'UNAUTHORIZED'),({'workspace_id':'WS-'+'f'*32},'WORKSPACE_MISMATCH')):
            status,result,_=self.req('POST','/api/operation/ack',body,**options)
            self.assertEqual((status,result['error']),(403,error))
        self.assertFalse(self.w.operation_status(operation_id=row['id'])['acknowledged'])
        self.assertEqual(self.req('GET','/api/operations',authenticated=False)[0],403)
        self.assertEqual(self.req('GET','/api/operation?id='+row['id'],workspace_id='WS-'+'f'*32)[0],403)
        self.assertEqual(self.req('POST','/api/action/create',payload,workspace_id='WS-'+'f'*32,key='wrong-workspace-1234567890')[0],403)
        self.assertEqual(len(self.w.list()['projects']),1)
        self.assertEqual(self.req('POST','/api/operation/ack',body)[1]['state'],'ACKNOWLEDGED')
        self.assertEqual(self.req('POST','/api/operation/ack',body)[1]['state'],'ACKNOWLEDGED')
        self.assertEqual(self.req('GET','/api/operations')[1]['operations'],[])
        self.assertEqual(len(list((self.w.root/'actions').glob('*.json'))),1)
        with patch('research_studio.codex_client.status',side_effect=AssertionError('No CLI inspection for graph')):
            status,graph,_=self.req('GET','/api/workflow-graph')
        self.assertEqual(status,200);self.assertIn('policy',graph);self.assertEqual(len(graph['workflows']),3)


class DesktopOriginRecoveryTests(unittest.TestCase):
    def test_response_loss_real_service_restart_changed_port_recovers_without_resend(self):
        self.restart_case({'kind':'TRW','title':'Lost response restart','text':'For every integer n, n + 0 = n.'})

    def test_survey_response_loss_restart_new_origin_and_new_intent(self):
        self.restart_case({'kind':'SURVEY','title':'Survey response recovery','survey_scope':{
            'topic':'Finite geometric sums','questions':['What is the exact finite sum including q=1?']}})

    def restart_case(self,payload):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'workspace';log=Path(tmp)/'desktop.log';processes=[]
            package_root=Path(__file__).resolve().parents[1]
            def stop(proc):
                if proc.poll() is None:
                    proc.send_signal(signal.SIGINT)
                    try:proc.wait(10)
                    except subprocess.TimeoutExpired:proc.kill();proc.wait(5);self.fail('Desktop failed to stop gracefully')
            def start():
                with log.open('ab') as output:
                    proc=subprocess.Popen([sys.executable,'-B','-m','research_studio.desktop','--serve','--workspace',str(root)],
                        cwd=package_root,stdin=subprocess.DEVNULL,stdout=output,stderr=output,start_new_session=True)
                processes.append(proc)
                deadline=time.monotonic()+15
                while time.monotonic()<deadline:
                    path=root/'runtime/service.json'
                    if path.exists():
                        record=json.loads(path.read_text())
                        if record['pid']==proc.pid:return proc,record
                    self.assertIsNone(proc.poll(),'Desktop exited before publishing its private service identity')
                    time.sleep(.02)
                self.fail('Desktop startup timed out')
            def request(record,method,path,body=None,cookie='',csrf='',workspace_id='',key='restart-action-1234567890',drop=False):
                port=int(record['url'].rsplit(':',1)[1]);headers={'Origin':record['url'],'Content-Type':'application/json','Idempotency-Key':key}
                if cookie:headers.update({'Cookie':cookie,'X-PMRS-CSRF':csrf,'X-PMRS-Workspace':workspace_id})
                with closing(http.client.HTTPConnection('127.0.0.1',port,timeout=10)) as c:
                    c.request(method,path,body=canonical(body) if body is not None else None,headers=headers)
                    if drop:return None
                    r=c.getresponse();return r.status,json.loads(r.read()),dict(r.getheaders())
            def login(record):
                code,result,headers=request(record,'POST','/api/session',{'token':record['token']})
                self.assertEqual(code,200)
                return headers['Set-Cookie'].split(';')[0],result['csrf'],result['workspace_id']
            try:
                first,r1=start();auth1=login(r1)
                # Send the actual production POST, close before reading its response.
                request(r1,'POST','/api/action/create',payload,*auth1,drop=True)
                receipt_file=root/'actions'/(identity('restart-action-1234567890')+'.json')
                deadline=time.monotonic()+10
                while time.monotonic()<deadline:
                    if receipt_file.exists() and json.loads(receipt_file.read_text())['state']=='COMPLETED':break
                    time.sleep(.02)
                native=json.loads(receipt_file.read_text());self.assertEqual(native['state'],'COMPLETED')
                old=Workspace(root);created=native['result'];snapshot=old.project(created['project']).read_snapshot()
                original_receipt=receipt_file.read_bytes();stop(first)
                self.assertFalse((root/'runtime/service.json').exists())
                # Hold the former port so the actual restart must use a new origin.
                with closing(socket.socket()) as reserved:
                    reserved.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
                    reserved.bind(('127.0.0.1',int(r1['url'].rsplit(':',1)[1])));reserved.listen(1)
                    second,r2=start();self.assertNotEqual(r1['url'],r2['url']);self.assertNotEqual(r1['token'],r2['token'])
                    auth2=login(r2);self.assertEqual(auth1[2],auth2[2])
                    # New-origin client knows only workspace identity, no original key or form.
                    code,listing,_=request(r2,'GET','/api/operations',None,*auth2);self.assertEqual(code,200)
                    self.assertEqual(len(listing['operations']),1);row=listing['operations'][0]
                    code,recovered,_=request(r2,'GET','/api/operation?id='+row['id'],None,*auth2)
                    self.assertEqual(code,200);self.assertEqual(recovered['result'],created)
                    self.assertEqual(recovered['operation']['payload'],{})
                    ack={'id':row['id'],'digest':row['digest']}
                    self.assertEqual(request(r2,'POST','/api/operation/ack',ack,*auth2)[0],200)
                    self.assertEqual(request(r2,'GET','/api/operations',None,*auth2)[1]['operations'],[])
                    current=Workspace(root);self.assertEqual(current.project(created['project']).read_snapshot(),snapshot)
                    self.assertEqual(receipt_file.read_bytes(),original_receipt)
                    self.assertEqual(snapshot['requests'],{});self.assertEqual(snapshot['usage']['model_calls'],0)
                    self.assertTrue(current.project(created['project']).audit()['valid'])
                    # Explicit new intent uses a new key, even for identical input.
                    code,new,_=request(r2,'POST','/api/action/create',payload,*auth2,key='new-intent-1234567890')
                    self.assertEqual(code,200);self.assertNotEqual(new['project'],created['project'])
                    self.assertEqual(len(current.list()['projects']),2)
                    stop(second)
            finally:
                for proc in processes:stop(proc)
