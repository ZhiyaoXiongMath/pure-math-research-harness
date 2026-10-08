"""Finite synthetic T7/T9/T10 regressions; no paid model or stress workload."""
from copy import deepcopy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from research_studio import changes, context, demo, execution, knowledge, relations, reports, resources, runner, scheduler, tasks
from research_studio.engine import Engine
from research_studio.util import canonical, PMRSError, sha
from tests.test_final_kernel import Fixture, statement, argument
from tests.test_final_reports import actual_render


class InterventionInputs(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        env=patch.dict(os.environ,{'PMRS_HOST_POOL_ROOT':str(self.root/'pool')});env.start();self.addCleanup(env.stop)

    def project(self):
        engine=Engine();store=engine.create(self.root/'project',demo.ARITHMETIC,synthetic=True)
        target=next(iter(store.read_snapshot()['records']));iid=engine.new_workflow(store,'TRW',target_ref=target)['instance_id']
        return engine,store,iid,target

    def material(self,store,body,title):
        return store.commit(changes.prepare_material_input(store.read_snapshot(),body,title,'text/plain',blob_get=store.read_blob))['source_ref']

    def freeze_one(self,store,iid):
        plan=scheduler.plan(store.read_snapshot(),[iid],demo.policy());self.assertTrue(plan['selected'],plan['waits'])
        plan['selected']=plan['selected'][:1];plan['actions']=[]
        row=scheduler.commit_dispatch(store,plan,policy=demo.policy())['prepared'][0]
        return tasks.load(store,row['task_id'])

    def report_project(self):
        engine,store,iid,target=self.project()
        engine.authorize(store,iid,{'intent':'Finite synthetic report resource recovery.',
            'authorized_scope':{'target_refs':[target],'reports':True,'allow_derived_work':True},'obligations':[]},
            {'max_calls':8,'max_workers':2,'execution_policy':demo.policy()})
        return store,iid

    def test_t7_necessary_target_premise_and_reverse_evidence_closure(self):
        f=Fixture();target=f.add(statement());premise=f.add(statement('The exact necessary premise holds.'))
        _,row,body=argument(target);row['data']['premise_bindings']=[{'premise_ref':premise,'kind':'CONDITIONAL_CANDIDATE',
            'context_ref':None,'scope_locator':None,'binding_mode':'PINNED','support_ref':None,'assumption_locator':None}]
        row['data']['open_conditions']=[{'condition_ref':premise,'locator':knowledge.locator(body.decode())}]
        proof=f.add(knowledge.make_record('Argument',body.decode(),row['data'],[]))
        negative=f.add(argument(target,'This synthetic opposing argument retains an unresolved counterexample boundary.'))
        unrelated=f.add(statement('This unrelated library item is not needed.'))
        edge=relations.relation(negative,target,'COUNTEREXAMPLE_TO');f.s['relations'].append(edge)
        packet=context.build_packet(f.s,[proof],f.get)
        self.assertEqual(set(packet['records']),{target,premise,proof,negative})
        self.assertNotIn(unrelated,packet['records']);self.assertIn(edge,packet['relations'])
        self.assertEqual(set(packet['bodies']),{f.s['records'][r]['body_sha256'] for r in packet['records']})

    def test_t7_available_library_is_not_implicit_input_and_budget_is_actual(self):
        e,store,iid,target=self.project();wanted=self.material(store,b'Necessary source text.\n','Selected')
        unwanted=[self.material(store,(str(i)+' unrelated ').encode()*8192,'Unselected '+str(i)) for i in range(8)]
        e.start_round(store,iid,'Use only the selected exact source and fixed target.',source_refs=[wanted],max_calls=1,policy=demo.policy())
        task=self.freeze_one(store,iid);packet=json.loads(store.read_blob(task['input_packet_ref']))
        refs={r['ref'] for r in task['input_manifest']}
        self.assertIn(wanted,refs);self.assertIn(target,refs);self.assertFalse(set(unwanted)&refs)
        self.assertNotIn('body_text',packet);self.assertNotIn('source_bytes_base64',packet)
        self.assertEqual(packet['material_refs'],task['material_refs'])
        prompt=store.read_blob(task['prompt_ref']).decode();budget,details=tasks.request_budget(task,prompt,packet,demo.policy()['capacity'],
            reserved_output_tokens=task['context_budget']['reserved_output_tokens'],safety_margin_tokens=1024)
        self.assertEqual(task['context_budget'],budget);self.assertEqual(task['context_budget_details'],details)
        actual_metadata=len(canonical(task))+len(prompt.encode())+len(canonical(packet))+len(tasks.INPUT_BOOTSTRAP.encode())
        self.assertEqual(budget['input_tokens'],actual_metadata+sum(x['bytes'] for x in task['material_refs'].values()))

    def test_t7_utf8_binary_png_and_128k_output_reserve_are_disclosed(self):
        text='Exact UTF-8: 汉字 "\\\n'.encode()*257;png=b'\x89PNG\r\n\x1a\n'+b'x'*997
        packet={'input_representation':'BLOB_REFERENCES_V1','material_refs':{
            sha(text):{'bytes':len(text),'media_type':'text/plain'},sha(png):{'bytes':len(png),'media_type':'image/png'}}}
        capacity={**demo.policy()['capacity'],'model_max_output_tokens':128000,'context_window_tokens':500000}
        budget,details=tasks.request_budget({},'Read exact files.',packet,capacity,reserved_output_tokens=128000,safety_margin_tokens=1024)
        self.assertEqual(details['material_text_bytes'],len(text));self.assertEqual(details['image_file_bytes'],len(png))
        self.assertEqual(details['separate_material_input_bound'],len(text)+4*((len(png)+2)//3))
        self.assertEqual(details['image_accounting'],'BASE64_SIZE_ALLOWANCE_NOT_EXACT_VISION_TOKENS')
        self.assertEqual(budget['reserved_output_tokens'],128000)
        limit=budget['input_tokens']+128000+1024
        tasks.request_budget({},'Read exact files.',packet,{**capacity,'context_window_tokens':limit},reserved_output_tokens=128000,safety_margin_tokens=1024)
        with self.assertRaisesRegex(PMRSError,'CONTEXT_LIMIT'):
            tasks.request_budget({},'Read exact files.',packet,{**capacity,'context_window_tokens':limit-1},reserved_output_tokens=128000,safety_margin_tokens=1024)

    def test_t9_ten_tasks_share_one_blob_and_materialize_one_readable_copy(self):
        e,store,iid,_=self.project();body=b'Synthetic common exact source.\n';body=(body*((1024*1024)//len(body)+1))[:1024*1024]
        source=self.material(store,body,'Shared one MiB source');digest=sha(body);frozen=[]
        for n in range(10):
            e.start_round(store,iid,'Synthetic distinct bounded question '+str(n)+'.',stage='P4',role='RESEARCH',source_refs=[source],max_calls=1,policy=demo.policy())
            task=self.freeze_one(store,iid);frozen.append(task)
            self.assertLess(len(store.read_blob(task['input_packet_ref'])),65536)
            self.assertIn(digest,task['material_refs']);self.assertEqual(task['material_refs'][digest]['bytes'],len(body))
            self.assertEqual(demo.executor().execute(store,task['task_id'])['state'],'ACCEPTED')
        self.assertEqual(len({t['task_id'] for t in frozen}),10)
        self.assertLess(sum(len(store.read_blob(t['input_packet_ref'])) for t in frozen),len(body))
        task=frozen[-1];work=store.root/'runs'/task['task_id']/'work'
        made=runner.materialize_task_inputs(store,task,work);runner.verify_task_inputs(work,made['files'])
        path=work/task['material_refs'][digest]['path'];self.assertEqual(path.read_bytes(),body)
        self.assertEqual(path.stat().st_mode&0o777,0o400);self.assertNotEqual(path.stat().st_ino,(store.root/'blobs'/digest).stat().st_ino)
        self.assertEqual(sum(row['sha256']==digest for row in made['files'].values()),1)
        path.chmod(0o600);path.write_bytes(b'x'*len(body))
        with self.assertRaisesRegex(PMRSError,'ORIGINAL_BYTES_MISMATCH'):runner.verify_task_inputs(work,made['files'])

    def test_t10_render_wait_resumes_same_body_without_author_recall_or_lock(self):
        store,iid=self.report_project();seen=[]
        def response(task,snapshot):
            with runner.coordinator(store):seen.append('model-lock-free')
            return demo.response(task,snapshot)
        def waiting(body,**kwargs):
            with runner.coordinator(store):seen.append('render-lock-free')
            raise PMRSError('RESOURCE_WAIT','Injected temporary renderer capacity wait.')
        ex=runner.FakeExecutor(response);result=reports.run(store,iid,executor=ex,policy=demo.policy(),renderer=waiting)
        self.assertEqual(result['state'],'RESOURCE_WAIT');self.assertEqual(ex.calls,1);rid=result['report_id']
        entry=store.read_snapshot()['reports'][rid];before=deepcopy(entry['profiles']['lecture'])
        self.assertTrue(before['body_sha256']);self.assertFalse(entry['failure_history'])
        rendered=reports.render(store,actual_render,iid,'lecture',report_id=rid)
        self.assertEqual(rendered['report_id'],rid);self.assertEqual(ex.calls,1)
        after=store.read_snapshot()['reports'][rid]['profiles']['lecture']
        self.assertEqual((after['body_sha256'],after['revision'],after['author_request_id']),
                         (before['body_sha256'],before['revision'],before['author_request_id']))
        self.assertEqual(seen,['model-lock-free','render-lock-free']);self.assertEqual(reports.prepare(store,iid,report_id=rid)['role'],'REPORT_SEMANTIC')

    def test_t10_report_assignment_is_not_self_stale_and_old_draft_is_not_dispatched(self):
        store,iid=self.report_project();rid=reports.create(store,iid);original=deepcopy(store.read_snapshot()['reports'][rid])
        with runner.coordinator(store):result=reports.advance(store,iid,rid)
        self.assertEqual(result['state'],'REPORT_TASK_READY');self.assertEqual(result['model_calls'],0)
        self.assertTrue(reports.dispatch_current(store.read_snapshot(),result['report_context']))
        task=self.freeze_one(store,iid);self.assertTrue(reports.dispatch_current(store.read_snapshot(),task['report_context']))
        reports.revise(store,iid,'lecture','Explicitly replace this draft before sending its prepared request.',report_id=rid)
        with self.assertRaisesRegex(PMRSError,'REPORT_CONTENT_STALE'):reports.dispatch_current(store.read_snapshot(),task['report_context'])
        self.assertEqual(store.read_snapshot()['reports'][rid]['snapshot_ref'],original['snapshot_ref'])
        self.assertEqual(store.read_snapshot()['usage']['model_calls'],0)

    def test_t10_small_checkpoint_limit_keeps_capture_then_recovers_exactly_once(self):
        e,store,iid,_=self.project();e.start_round(store,iid,'Synthetic checkpoint threshold recovery.',max_calls=1,policy=demo.policy())
        task=self.freeze_one(store,iid);ex=runner.FakeExecutor(demo.response,fault_at='AFTER_CAPTURE_RECEIPT_BEFORE_ADMISSION')
        with self.assertRaises(runner.SimulatedCrash):ex.execute(store,task['task_id'])
        before=store.read_snapshot();head=store._head();request=before['requests'][task['request_id']];capture=request['capture_ref']
        with patch('research_studio.store.CHECKPOINT_INTERVAL',1),patch('research_studio.store.CHECKPOINT_STATE_BYTES',1024):
            with self.assertRaisesRegex(PMRSError,'RESOURCE_LIMIT'):execution.recover(store,task['request_id'])
        after=store.read_snapshot();self.assertEqual(store._head(),head);self.assertEqual(after['records'],before['records'])
        self.assertEqual(after['requests'][task['request_id']]['execution_state'],'CAPTURED')
        self.assertEqual(after['requests'][task['request_id']]['capture_ref'],capture)
        self.assertEqual(execution.recover(store,task['request_id'])['state'],'ACCEPTED')
        self.assertEqual(execution.recover(store,task['request_id'])['state'],'EXACT_DUPLICATE')
        self.assertEqual(ex.calls,1);self.assertEqual(store.read_snapshot()['usage'],before['usage'])
        self.assertEqual(len(store.read_snapshot()['requests']),1);store.audit()

    def test_report_wait_counts_only_this_execution_and_recovery_does_not_recount(self):
        store,iid=self.report_project();calls=[]
        class WaitAfterSecondCapture:
            def execute(inner,project,tid):
                calls.append(tid)
                if len(calls)==1:return demo.executor().execute(project,tid)
                fake=runner.FakeExecutor(demo.response,fault_at='AFTER_CAPTURE_RECEIPT_BEFORE_ADMISSION')
                with self.assertRaises(runner.SimulatedCrash):fake.execute(project,tid)
                task=tasks.load(project,tid)
                return {'state':'RESOURCE_WAIT','code':'RESOURCE_DISK_LOW','task_id':tid,
                        'request_id':task['request_id'],'retryable':True,'model_calls':1}
        first=reports.run(store,iid,executor=WaitAfterSecondCapture(),policy=demo.policy(),renderer=actual_render)
        self.assertEqual(first['state'],'RESOURCE_WAIT');self.assertEqual(first['model_calls'],2)
        self.assertEqual(len(first['tasks']),1);self.assertEqual(len(calls),2)
        request=store.read_snapshot()['requests'][first['request_id']]
        self.assertEqual(request['execution_state'],'CAPTURED');capture=request['capture_ref']
        class WaitBeforeSend:
            def execute(inner,project,tid):
                return {'state':'RESOURCE_WAIT','code':'RESOURCE_WAIT','task_id':tid,'model_calls':0}
        second=reports.run(store,iid,report_id=first['report_id'],executor=WaitBeforeSend(),policy=demo.policy(),renderer=actual_render)
        self.assertEqual(second['state'],'RESOURCE_WAIT');self.assertEqual(second['model_calls'],0)
        after=store.read_snapshot()['requests'][first['request_id']]
        self.assertEqual(after['execution_state'],'SETTLED');self.assertEqual(after['capture_ref'],capture)
        self.assertEqual(len(calls),2);self.assertEqual(len(store.read_snapshot()['requests']),3)
