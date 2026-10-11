"""Real HTTP sessions and native workflow writes; no paid model transport."""
import base64
from http.server import ThreadingHTTPServer
import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from copy import deepcopy
from contextlib import closing
from research_studio import demo,views,changes,execution
from research_studio.workspace import Workspace
from research_studio.ui import app_handler
from research_studio.engine import Engine
from research_studio.util import canonical,sha,PMRSError


class WebApplicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.w=Workspace(Path(self.tmp.name)/'workspace')
        self.server=ThreadingHTTPServer(('127.0.0.1',0),app_handler(self.w,'bootstrap-secret'))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.origin='http://127.0.0.1:'+str(self.server.server_port);self.cookie='';self.csrf=''
        status,d,headers=self.req('POST','/api/session',{'token':'bootstrap-secret'},session=False)
        self.assertEqual(status,200);self.cookie=headers['Set-Cookie'].split(';')[0];self.csrf=d['csrf']
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
    def req(self,method,path,p=None,*,session=True,origin=None,csrf=None,key='stable-operation-12345678'):
        headers={'Origin':origin or self.origin,'Content-Type':'application/json','Idempotency-Key':key}
        if session:headers.update(Cookie=self.cookie,**{'X-PMRS-CSRF':self.csrf if csrf is None else csrf})
        with closing(http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=30)) as c:
            c.request(method,path,body=canonical(p) if p is not None else None,headers=headers);r=c.getresponse();raw=r.read();h=dict(r.getheaders())
            return r.status,json.loads(raw) if h.get('Content-Type','').startswith('application/json') else raw,h
    def create(self,kind='TRH'):
        p={'kind':kind,'title':'<script>alert(1)</script> 原始项目','text':demo.ARITHMETIC.decode() if kind=='TRH' else 'Positive definite symmetric matrices and their eigenvalues.'}
        code,r,h=self.req('POST','/api/action/example',p,key='create-'+kind+'-1234567890123456');self.assertEqual(code,200,r)
        return r
    def test_authenticated_business_actions_csrf_origin_and_idempotence(self):
        p={'kind':'TRH','title':'Example','text':'For every n, n + 0 = n.'}
        for kw in ({'session':False},{'csrf':'bad'},{'origin':'https://evil.invalid'}):
            code,r,_=self.req('POST','/api/action/create',p,**kw);self.assertEqual(code,403,r)
        self.assertEqual(self.w.list()['projects'],[])
        first=self.req('POST','/api/action/create',p)[1];second=self.req('POST','/api/action/create',p)[1]
        self.assertEqual(first,second);self.assertEqual(len(self.w.list()['projects']),1)
        self.assertEqual(self.req('POST','/api/action/create',{**p,'title':'different'})[1]['error'],'ACTION_CONFLICT')
        replay=Workspace(self.w.root).action('create',p,'stable-operation-12345678');self.assertEqual(replay,first)
        self.assertIn('HttpOnly',self.req('POST','/api/session',{'token':'bootstrap-secret'},session=False)[2]['Set-Cookie'])
    def test_read_only_status_pages_and_frozen_cursor_do_not_admit_capture(self):
        created=self.create();store=self.w.project(created['project']);iid=created['instance_id'];e=Engine()
        e.start_round(store,iid,'Investigate the exact question',max_calls=3,policy=demo.policy())
        made=e.prepare(store,iid);tid=made['prepared'][0]['task_id'];rid=made['prepared'][0]['request_id']
        from research_studio.runner import FakeExecutor,SimulatedCrash
        with self.assertRaises(SimulatedCrash):FakeExecutor(demo.response,fault_at='AFTER_CAPTURE_RECEIPT_BEFORE_ADMISSION').execute(store,tid)
        e.pause(store,iid,'Keep captured result without admitting')
        before={str(p.relative_to(store.root)):sha(p.read_bytes()) for p in store.root.rglob('*') if p.is_file()}
        commit=store.read_snapshot()['knowledge_commit'];base='?project='+created['project']+'&instance='+iid+'&commit='+commit
        for _ in range(3):
            for endpoint in ('status','current','frontier','sources','reports'):
                code,d,_=self.req('GET','/api/'+endpoint+base);self.assertEqual(code,200,d)
                self.assertEqual(d['commit'],commit)
            code,d,_=self.req('GET','/api/status'+base);self.assertEqual(d['execution']['running_processes'],0)
            self.assertEqual(d['acceptance']['pending_captures'],1)
        after={str(p.relative_to(store.root)):sha(p.read_bytes()) for p in store.root.rglob('*') if p.is_file()}
        self.assertEqual(before,after);self.assertEqual(store.read_snapshot()['requests'][rid]['execution_state'],'CAPTURED')
        store.commit(changes.prepare_material_input(store.read_snapshot(),b'New unrelated material',blob_get=store.read_blob))
        self.assertEqual(self.req('GET','/api/current'+base)[1]['commit'],commit)
    def test_exact_scope_body_paths_and_hostile_text_are_not_html(self):
        created=self.create();store=self.w.project(created['project']);iid=created['instance_id'];s=store.read_snapshot()
        other=store.commit(changes.prepare_source_input(s,b'Private unrelated statement',blob_get=store.read_blob))['target_ref']
        base='?project='+created['project']+'&instance='+iid
        self.assertEqual(self.req('GET','/api/body'+base+'&ref='+other)[0],403)
        code,d,h=self.req('GET','/api/status'+base);self.assertEqual(d['title'],'<script>alert(1)</script> 原始项目')
        self.assertIn("script-src 'self'",h['Content-Security-Policy'])
        for path in ('/static/../project.json','/static/%2e%2e/HEAD','/api/download?file=../HEAD','/api/status?project=../../other'):
            self.assertGreaterEqual(self.req('GET',path)[0],400)
        self.assertEqual(self.req('GET','/api/status'+base,session=False)[0],403)
        code,script,_=self.req('GET','/static/workbench.js');self.assertEqual(code,200);self.assertNotIn(b'innerHTML',script)
    def test_public_handoff_and_binary_upload_preserve_target(self):
        created=self.create();store=self.w.project(created['project']);iid=created['instance_id'];target=store.read_snapshot()['instances'][iid]['target_ref']
        code,r,_=self.req('POST','/api/action/handoff',{'project':created['project'],'instance':iid,'direction':'TRH_TO_FDH','brief':'Explore precise variants and counterexamples.','discovery_scope':demo.discovery_scope('Explore precise variants and counterexamples.'),'note':'Study variations without changing the original target.'},key='handoff-123456789012345678')
        self.assertEqual(code,200,r);s=store.read_snapshot();self.assertEqual(s['instances'][iid]['target_ref'],target);self.assertEqual(s['instances'][r['instance_id']]['status'],'PAUSED')
        raw=b'%PDF-1.5\n\x00\xff original binary bytes';before=len(s['records'])
        code,r,_=self.req('POST','/api/action/add-source',{'project':created['project'],'filename':'paper.pdf','media_type':'application/pdf','data':base64.b64encode(raw).decode()},key='material-123456789012345678')
        self.assertEqual(code,200,r);s=store.read_snapshot();self.assertEqual(len(s['records']),before);self.assertEqual(store.read_blob(s['sources'][r['source_ref']]['blob_hash']),raw)
    def test_export_restore_creates_new_workspace_entry_with_original_untouched(self):
        c=self.create();s=self.w.project(c['project']);before=s.read_snapshot()['knowledge_commit']
        code,result,_=self.req('POST','/api/action/export',{'project':c['project']},key='backup-123456789012345678');self.assertEqual(code,200,result)
        code,raw,_=self.req('GET',result['download']);self.assertEqual(code,200)
        code,upload,_=self.req('POST','/api/action/upload-archive',{'data':base64.b64encode(raw).decode(),'mode':'restore'},key='upload-123456789012345678');self.assertEqual(code,200,upload)
        code,r,_=self.req('POST','/api/action/restore',{'upload_id':upload['upload_id']},key='restore-123456789012345678');self.assertEqual(code,200,r)
        self.assertNotEqual(c['project'],r['project']);self.assertEqual(s.read_snapshot()['knowledge_commit'],before)
        restored=self.w.project(r['project']);self.assertEqual(restored.read_snapshot()['records'],s.read_snapshot()['records']);restored.audit()
    def test_native_backup_over_32_mib_restores_over_http_without_raising_material_limit(self):
        import io
        import zipfile
        import random
        from research_studio.portability import export_project
        from research_studio.store import Store
        from research_studio.util import loads,MAX_JSON
        with patch('research_studio.runner.CodexExecutor.execute',side_effect=AssertionError('Upload and restore cannot call a model')):
            engine=Engine();original=engine.create(Path(self.tmp.name)/'large-native',demo.ARITHMETIC,synthetic=True)
            target=next(r for r,v in original.read_snapshot()['records'].items() if v['kind']=='Statement')
            engine.new_workflow(original,'TRH',target_ref=target)
            random_source=random.Random(4000)
            for index in range(3):
                raw_material=random_source.randbytes(17*1024**2)
                original.commit(changes.prepare_material_input(original.read_snapshot(),raw_material,title=f'Generated binary {index}',media_type='application/octet-stream',blob_get=original.read_blob))
            before=original.read_snapshot()
            archive=Path(self.tmp.name)/'large-native-backup.zip'
            exported=export_project(original,archive);raw=archive.read_bytes()
            self.assertGreater(len(raw),32*1024**2)
            self.assertLessEqual(len(raw),128*1024**2)
            self.assertEqual(sha(raw),exported['sha256'])
            if 4*((len(raw)+2)//3)<=64*1024**2:
                # Preserve every native member byte and manifest while removing
                # ZIP compression, so the real HTTP envelope crosses 64 MiB.
                stream=io.BytesIO()
                with zipfile.ZipFile(io.BytesIO(raw)) as original_zip,zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_STORED) as stored_zip:
                    for member in original_zip.infolist():stored_zip.writestr(member.filename,original_zip.read(member))
                raw=stream.getvalue()
            payload={'data':base64.b64encode(raw).decode(),'mode':'restore'}
            envelope=canonical(payload)
            self.assertGreater(len(envelope),64*1024**2)
            self.assertLessEqual(len(raw),128*1024**2)
            self.assertLessEqual(len(envelope),172*1024**2)
            self.assertEqual(MAX_JSON,64*1024**2)
            with self.assertRaisesRegex(PMRSError,'JSON_LIMIT'):loads(envelope)
            with self.assertRaisesRegex(PMRSError,'JSON_LIMIT'):loads(b'{"ok":1}',maximum=2)
            with self.assertRaisesRegex(PMRSError,'JSON_DUPLICATE_KEY'):loads(b'{"a":1,"a":2}',maximum=172*1024**2)
            with self.assertRaisesRegex(PMRSError,'JSON_INVALID'):loads(b'{"a":NaN}',maximum=172*1024**2)
            code,uploaded,_=self.req('POST','/api/action/upload-archive',
                payload,key='native-large-upload-1234567890123456')
            self.assertEqual(code,200,{'response':uploaded,'archive_bytes':len(raw),'envelope_bytes':len(envelope)})
            self.assertEqual(uploaded['mode'],'restore')
            self.assertFalse(uploaded['summary']['processes_restored'])
            code,result,_=self.req('POST','/api/action/restore',
                {'upload_id':uploaded['upload_id']},key='native-large-restore-1234567890123456')
            self.assertEqual(code,200,result)
            restored=self.w.project(result['project']);after=restored.read_snapshot()
            self.assertEqual(after['records'],before['records'])
            self.assertEqual(after['sources'],before['sources'])
            self.assertTrue(after['instances'])
            self.assertTrue(all(i['status']=='PAUSED' for i in after['instances'].values()))
            self.assertEqual(after['requests'],{})
            self.assertEqual(after['project_budget'],before['project_budget'])
            self.assertEqual(after['usage']['model_calls'],0)
            for record in before['records'].values():
                self.assertEqual(restored.read_blob(record['body_sha256']),original.read_blob(record['body_sha256']))
            for material in before['sources'].values():
                self.assertEqual(restored.read_blob(material['blob_hash']),original.read_blob(material['blob_hash']))
            self.assertTrue(restored.audit()['valid'])
            self.assertEqual(original.read_snapshot()['knowledge_commit'],before['knowledge_commit'])
            restored_head=after['knowledge_commit']
            too_large=b'x'*(32*1024**2+1)
            code,rejected,_=self.req('POST','/api/action/add-source',
                {'project':result['project'],'filename':'oversized-material.txt','media_type':'text/plain',
                 'data':base64.b64encode(too_large).decode()},key='native-large-material-1234567890123456')
            self.assertEqual(code,400,rejected)
            self.assertEqual(rejected['error'],'PAYLOAD_LIMIT')
            self.assertEqual(restored.read_snapshot()['knowledge_commit'],restored_head)
            self.assertFalse(self.w.live_jobs())

    def test_pending_operation_is_not_blindly_repeated_after_restart(self):
        from research_studio.util import identity,atomic
        p={'title':'Test','text':'Original target','kind':'TRH'};key='crashed-operation-12345678'
        atomic(self.w.root/'actions'/(identity(key)+'.json'),canonical({'digest':identity({'action':'create','payload':p}),'state':'PENDING','operation':{'id':identity(key),'name':'create','payload':p,'created_at':'2026-10-08T00:00:00Z'}}))
        with self.assertRaisesRegex(PMRSError,'ACTION_UNCERTAIN'):Workspace(self.w.root).action('create',p,key)
        self.assertEqual(self.w.list()['projects'],[])

    def test_report_requested_during_research_preserves_stale_snapshot_and_explicit_retry(self):
        created=self.create();entered=threading.Event();release=threading.Event();original=demo.response
        def delayed(task,snapshot):
            if not entered.is_set():entered.set();self.assertTrue(release.wait(15))
            return original(task,snapshot)
        with patch('research_studio.demo.response',side_effect=delayed):
            code,result,_=self.req('POST','/api/action/start',{'project':created['project'],'instance':created['instance_id'],
                'intent':'Study the exact arithmetic example','max_calls':16,'max_workers':1,'report_first':True},key='start-report-1234567890123456')
            self.assertEqual(code,200,result);self.assertTrue(entered.wait(10))
            code,result,_=self.req('POST','/api/action/report',{'project':created['project'],'instance':created['instance_id']},key='request-report-1234567890123456')
            self.assertEqual(code,200,result);self.assertTrue(result['report_id'].startswith('REPORT-'))
            self.assertTrue(self.w.jobs[(created['project'],created['instance_id'])]['report_requested']);release.set()
            deadline=time.monotonic()+60
            while self.w.live_jobs() and time.monotonic()<deadline:time.sleep(.02)
        self.assertFalse(self.w.live_jobs());job=self.w.jobs[(created['project'],created['instance_id'])]
        self.assertEqual(job['state'],'WAITING',job);self.assertEqual(job['result']['state'],'STALE_CANDIDATE',job)
        store=self.w.project(created['project']);original_report=result['report_id'];old=store.read_snapshot()['reports'][original_report]
        self.assertTrue(job['result']['requires_explicit_new_report'])
        self.assertFalse(any(t.get('report_context',{}).get('report_id')==original_report for t in store.read_snapshot()['tasks'].values()))
        code,replanned,_=self.req('POST','/api/action/report',{'project':created['project'],'instance':created['instance_id']},key='explicit-current-report-1234567890')
        self.assertEqual(code,200,replanned);self.assertNotEqual(replanned['report_id'],original_report)
        deadline=time.monotonic()+60
        while self.w.live_jobs() and time.monotonic()<deadline:time.sleep(.02)
        self.assertEqual(self.w.jobs[(created['project'],created['instance_id'])]['result']['state'],'COMPLETED_CURRENT_REPORT',self.w.jobs[(created['project'],created['instance_id'])])
        self.assertEqual(store.read_snapshot()['reports'][original_report],old)
        code,rows,_=self.req('GET','/api/reports?project='+created['project']+'&instance='+created['instance_id'])
        self.assertEqual(code,200,rows);complete=[r for r in rows['reports'] if r['classification']=='COMPLETED_CURRENT_REPORT']
        self.assertEqual(len(complete),1);self.assertEqual(len(complete[0]['downloads']),2)
        for item in complete[0]['downloads']:
            code,pdf,_=self.req('GET',item['url']);self.assertEqual(code,200);self.assertTrue(pdf.startswith(b'%PDF-'))
        store=self.w.project(created['project']);s=store.read_snapshot();entry=s['reports'][complete[0]['report_id']]
        artifact=next(store.root/p for p in entry['files'] if p.endswith('.pdf'));raw=artifact.read_bytes();artifact.write_bytes(raw+b'changed')
        code,result,_=self.req('POST','/api/action/end',{'project':created['project'],'instance':created['instance_id'],'commit':s['knowledge_commit']},key='damaged-end-1234567890123456')
        self.assertEqual(code,400,result);self.assertEqual(result['error'],'REPORT_BLOCKED');self.assertEqual(store.read_snapshot()['knowledge_commit'],s['knowledge_commit'])
        artifact.write_bytes(raw)
        code,result,_=self.req('POST','/api/action/end',{'project':created['project'],'instance':created['instance_id'],'commit':s['knowledge_commit']},key='intact-end-1234567890123456')
        self.assertEqual(code,200,result);self.assertEqual(result['decision_basis']['report_ref'],entry['report_id']);self.assertEqual(store.read_snapshot()['instances'][created['instance_id']]['status'],'ENDED')

    def test_backend_restart_marks_reserved_unknown_without_resend_and_retains_capture(self):
        from research_studio.runner import FakeExecutor,SimulatedCrash
        from research_studio.scheduler import project_remaining
        c=self.create();store=self.w.project(c['project']);e=Engine();iid=c['instance_id']
        e.start_round(store,iid,'Recover precisely once',max_calls=3,policy=demo.policy())
        task=e.prepare(store,iid)['prepared'][0]
        with self.assertRaises(SimulatedCrash):FakeExecutor(demo.response,fault_at='AFTER_RESERVATION_BEFORE_SEND').execute(store,task['task_id'])
        before=store.read_snapshot();remaining=project_remaining(before)
        w2=Workspace(self.w.root);result=w2.recover_backend_state();after=store.read_snapshot()
        self.assertEqual(result,{'uncertain_requests':[task['request_id']],'resent':0,'admitted':0})
        self.assertEqual(after['requests'][task['request_id']]['execution_state'],'UNKNOWN');self.assertEqual(project_remaining(after),remaining)
        self.assertEqual(after['records'],before['records']);self.assertEqual(w2.recover_backend_state()['uncertain_requests'],[])
        code,status,_=self.req('GET','/api/status?project='+c['project']+'&instance='+iid)
        self.assertEqual(code,200);self.assertEqual(status['execution']['unknown'],1);self.assertEqual(status['execution']['running_processes'],0)

    def test_n31_native_partial_scope_family_method_source_pagination_and_diff(self):
        from tests.fixtures.builders.native_reader import build
        key='WP-'+'d'*32;store,refs=build(self.w.root/'projects'/key);s=store.read_snapshot();original=s['knowledge_commit']
        base='?project='+key+'&instance='+refs['instance_id'];rows=[];offset=0
        while offset is not None:
            code,page,_=self.req('GET','/api/current'+base+'&limit=1&offset='+str(offset));self.assertEqual(code,200,page)
            self.assertEqual(len(page['records']),1);rows.extend(page['records']);offset=page['next_offset']
        self.assertEqual({r['ref'] for r in rows},views.scope_refs(s,refs['instance_id'])&set(s['records']))
        for row in rows:
            code,body,_=self.req('GET','/api/body'+base+'&ref='+row['ref']);self.assertEqual(code,200,body)
            self.assertEqual(body['body'].encode(),store.read_blob(s['records'][row['ref']]['body_sha256']))
        a1=next(r for r in rows if r['ref']==refs['argument_refs'][0]);self.assertEqual(a1['source_uses'][0]['usage'][0]['usage_mode'],'METHOD_INSPIRATION')
        self.assertEqual(a1['result_families'][0]['authority'],'NAVIGATION_ONLY');self.assertEqual(len(a1['result_families'][0]['members']),3)
        code,sources,_=self.req('GET','/api/sources'+base);self.assertEqual(code,200,sources)
        chinese=next(r for r in sources['sources'] if r['source_ref']==refs['source_ref']);self.assertEqual(sha(chinese['text'].encode()),refs['original_source_sha256'])
        self.assertEqual(chinese['authority'],'SOURCE_CLAIM_NOT_NATIVE_PROOF')
        code,partial,_=self.req('GET','/api/current'+base+'&commit='+refs['partial_commit']);self.assertEqual(code,200,partial)
        partial_statement=next(r for r in partial['records'] if r['ref']==refs['target_ref'])
        self.assertTrue(any(b['checked_scope'] for b in partial_statement['support_boundaries']))
        self.assertTrue(any(b['not_checked'] for b in partial_statement['support_boundaries']))
        code,delta,_=self.req('GET','/api/diff'+base+'&from='+refs['before_commit']);self.assertEqual(code,200,delta)
        self.assertTrue(delta['content_added']);self.assertEqual(delta['support_withdrawals'][0]['support_id'],refs['support_refs'][0]);self.assertIsNone(delta['automatic_new_theorem_count'])
        code,frontier,_=self.req('GET','/api/frontier'+base);self.assertEqual(code,200,frontier);self.assertTrue(frontier['obligations'])
        self.assertEqual(store.read_snapshot()['knowledge_commit'],original);store.audit()


class NativeReaderTests(unittest.TestCase):
    def test_chinese_original_search_body_source_and_projection_rebuild(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw='研究可去奇点：保持原有假设与量词。'.encode();s=Engine().create(Path(tmp)/'p',raw)
            state=s.read_snapshot();before=canonical(state['records']);source=next(iter(state['sources'].values()))
            self.assertEqual(s.read_blob(source['blob_hash']),raw)
            found=views.current(state,s.read_blob,query='removability');self.assertTrue(found['records'])
            path=s.rebuild_projection();self.assertEqual(canonical(s.read_snapshot()['records']),before);self.assertEqual(s.read_snapshot()['knowledge_commit'],state['knowledge_commit'])
            self.assertEqual(s.audit()['records'],1)
    def test_real_diff_distinguishes_new_reused_source_and_control_changes(self):
        from research_studio import demo
        with tempfile.TemporaryDirectory() as tmp:
            e=Engine();s=e.create(Path(tmp)/'p',demo.ARITHMETIC,synthetic=True);target=next(iter(s.read_snapshot()['records']))
            iid=e.new_workflow(s,'TRH',target_ref=target)['instance_id'];baseline=s.read_snapshot()
            e.start_round(s,iid,'Investigate arithmetic',max_calls=4,policy=demo.policy());after_control=s.read_snapshot()
            d=views.diff(baseline,after_control,instance_id=iid);self.assertEqual(d['classification'],'CONTROL_ONLY');self.assertEqual(d['content_added'],[])
            e.run_round(s,iid,executor=demo.executor());after=s.read_snapshot();d=views.diff(baseline,after,instance_id=iid)
            self.assertTrue(d['content_added']);self.assertIsNone(d['automatic_new_theorem_count']);self.assertEqual(d['originality'],'NOT_AUTOMATICALLY_CERTIFIED')
            records=deepcopy(after['records'])
            s.commit(changes.prepare_material_input(after,'附加的可去奇点材料'.encode(),title='原文',media_type='text/plain',blob_get=s.read_blob));added_source=s.read_snapshot()
            self.assertEqual(added_source['records'],records);self.assertEqual(views.diff(after,added_source)['content_added'],[])
            before=s.read_snapshot();s.rebuild_projection();self.assertEqual(views.diff(before,s.read_snapshot())['classification'],'CONTROL_ONLY')
            e.pause(s,iid,'Pause');self.assertEqual(views.diff(before,s.read_snapshot())['content_added'],[])

    def test_n42_result_family_never_transfers_equivalence_or_qualification(self):
        from tests.test_final_kernel import AssuranceContextTests,statement
        from research_studio import assurance,knowledge
        helper=AssuranceContextTests();f,t1,a1,sid1,scope1=helper.build();helper.review(f,sid1,scope1)
        t2=f.add(statement('There exists one y for all x.'))
        before=deepcopy(f.s);f.s['result_families']={'family':knowledge.result_family({'family_id':'family','members':[{'record_ref':t1,'display_role':'MAIN_RESULT'},{'record_ref':t2,'display_role':'COROLLARY'}]},f.s['records'])}
        self.assertEqual(before['records'],f.s['records']);self.assertEqual(before['qualifications'],f.s['qualifications']);self.assertEqual(before['relations'],f.s['relations'])
        req1=assurance.requirement('PROOF_SUPPORT',scope1);self.assertEqual(assurance.evaluate(t2,{'required_assurance':req1},f.s)['support_state'],'NO_ARGUMENT')
        self.assertEqual(views.diff(before,f.s)['content_added'],[])
        a2,sid2,req2=helper.add_path(f,t2,'A separate argument for the second precise statement.')
        before_withdrawal=deepcopy(f.s);f.s['withdrawals']['W']={'support_id':sid1,'scope':scope1,'active':True}
        self.assertEqual(assurance.evaluate_requirement(f.s,sid1,req1,'p')['result'],'WITHDRAWN')
        self.assertEqual(assurance.evaluate_requirement(f.s,sid2,req2,'p')['result'],'QUALIFIED')
        delta=views.diff(before_withdrawal,f.s);self.assertEqual(delta['support_withdrawals'][0]['support_id'],sid1)
        rows=views.current(f.s,f.get)['records'];self.assertTrue(next(r for r in rows if r['ref']==t2)['result_families'])
        self.assertEqual(f.s['relations'],before['relations']);self.assertIsNone(delta['automatic_new_theorem_count'])

    def test_reused_scientific_content_links_production_without_new_theorem(self):
        from tests.test_final_kernel import Fixture,statement
        f=Fixture();ref,record,body=statement();op={'op':'NEW','local_key':'s','kind':'Statement','context_refs':[],'body':body.decode(),'data':record['data']}
        t=f.task(request='one');f.accept(t,f.raw(t,[op]));before=deepcopy(f.s)
        t=f.task(request='two');f.accept(t,f.raw(t,[op]));delta=views.diff(before,f.s)
        self.assertEqual(delta['content_added'],[]);self.assertEqual(delta['content_reused'],[ref]);self.assertIsNone(delta['automatic_new_theorem_count'])

    def test_cli_readers_and_required_instance_do_not_call_executor(self):
        from research_studio.cli import parser,execute
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'p';s=Engine().create(root,b'For all integers n, n + 0 = n.')
            before=s.read_snapshot()['knowledge_commit']
            for argv in (['status',str(root)],['workflow','list',str(root)],['knowledge','current',str(root)],['audit',str(root)]):
                result=execute(parser().parse_args(argv));self.assertIsInstance(result,dict)
            self.assertEqual(s.read_snapshot()['knowledge_commit'],before)
            with self.assertRaises(SystemExit):parser().parse_args(['prepare',str(root)])

if __name__=='__main__':unittest.main()
