"""Finite assistant paths through native requests and real controlled transport."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json,os,subprocess,sys,time,unittest
from research_studio import assistant,demo,execution,host_pool,resources,scheduler
from research_studio.engine import Engine
from research_studio.runner import CodexExecutor
from research_studio.store import Store
from research_studio.util import PMRSError,canonical,loads
from tests.test_model_pool import fixture,prepare,TRANSPORT,events,peaks,evidence


class AssistantKernel(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        environment=patch.dict(os.environ,{'PMRS_HOST_POOL_ROOT':str(self.root/'pool'),'PMRS_CONTROLLED_TRANSPORT':str(self.root/'transport')})
        environment.start();self.addCleanup(environment.stop)

    def policy(self):
        p=demo.policy();p['executor_contract']={'executor':'codex','sandbox':'required','environment_revision':'controlled-assistant-transport'};return p

    def project(self):return Store.create(self.root/'project','Assistant controlled fixture',synthetic=True)

    def prepared(self,store,text='Explain this state. Do not start research.',*,context=None,calls=3):
        sid=assistant.open_session(store,context or {},'open')['session_id'];assistant.authorize(store,sid,calls,'grant')
        turn=assistant.submit(store,sid,text,'message');task=assistant._freeze(store,turn['turn_id'],self.policy())
        return sid,turn['turn_id'],task

    def transport(self,stores,exit_code=0,delay=.01):
        root=self.root/'transport';root.mkdir();(root/'responses').mkdir();binary=root/'transport'
        binary.write_text(TRANSPORT.replace('work=pathlib.Path','sys.stdin.buffer.read()\nwork=pathlib.Path'));binary.chmod(0o700)
        (root/'config.json').write_text(json.dumps({'delay':delay,'delays':{},'exit_code':exit_code}))
        for store in stores:
            for task in store.read_snapshot()['tasks'].values():
                raw=assistant.demo_response(task,store.read_snapshot()) if assistant.is_task(task) else demo.response(task,store.read_snapshot())
                (root/'responses'/task['request_id']).write_bytes(raw)
        return binary

    def run_actual(self,store,turn_id,binary):
        with patch('research_studio.runner.doctor',return_value={'ready':True,'binary':str(binary)}):
            return assistant.run_turn(store,turn_id,executor=CodexExecutor(str(binary),timeout=10),policy=self.policy())

    def test_fixed_real_send_parameters_zero_research_budget_and_operation_identity(self):
        store=self.project();before=store.read_snapshot();sid,tid,task=self.prepared(store)
        binary=self.transport([store]);result=self.run_actual(store,tid,binary)
        self.assertEqual(result['state'],'ACCEPTED');self.assertEqual(result['model_calls'],1)
        command=loads((store.root/'runs'/task['task_id']/'command.json').read_bytes())
        self.assertEqual(command[command.index('--model')+1],'gpt-6-astra');self.assertIn('model_reasoning_effort="xhigh"',command)
        self.assertEqual(task['role'],'PROJECT_ASSISTANT');self.assertIsNone(task['stage_id']);self.assertIsNone(task['mission_id'])
        evidence('assistant-real-parameters',{'task_id':task['task_id'],'request_id':task['request_id'],'command':command,'model_calls':result['model_calls']})
        snapshot=store.read_snapshot();self.assertEqual(snapshot['project_budget'],before['project_budget']);self.assertFalse(snapshot['missions'])
        self.assertEqual(snapshot['records'],before['records']);self.assertEqual(scheduler.project_remaining(snapshot),0)
        self.assertEqual(assistant.status(store,sid)['budget']['used'],1)
        again=assistant.submit(store,sid,'Explain this state. Do not start research.','message')
        self.assertEqual(again['request_id'],task['request_id']);self.assertEqual(self.run_actual(Store(store.root),tid,binary)['state'],'ACCEPTED')
        self.assertEqual(len(events(self.root/'transport/events.jsonl')),2);store.audit()
        with self.assertRaisesRegex(PMRSError,'OPERATION_KEY_CONFLICT'):assistant.submit(store,sid,'Different message','message')
        other=Store.create(self.root/'other','Unrelated fixture',synthetic=True)
        with self.assertRaisesRegex(PMRSError,'REQUEST_UNKNOWN'):assistant.open_session(other,{'request_id':task['request_id']},'wrong-project')

    def test_real_capability_mismatch_and_independent_finite_allowance_fail_before_send(self):
        store=self.project();sid=assistant.open_session(store,{},'open')['session_id'];tid=assistant.submit(store,sid,'Explain without actions.','m')['turn_id']
        with patch('research_studio.runner.subprocess.Popen',side_effect=AssertionError('No authorized supported request')):
            self.assertEqual(assistant.run_turn(store,tid,policy=self.policy())['error']['code'],'ASSISTANT_BUDGET_EXHAUSTED')
            assistant.authorize(store,sid,1,'grant');bad=self.policy();bad['model_capabilities']['models']['gpt-6-astra']['reasoning_efforts']=['high']
            self.assertEqual(assistant.run_turn(store,tid,policy=bad)['error']['code'],'MODEL_CONFIGURATION_UNSUPPORTED')
        self.assertFalse(store.read_snapshot()['requests']);self.assertEqual(assistant.status(store,sid)['budget']['remaining'],1)
        assistant.run_turn(store,tid,executor=assistant.demo_executor(),policy=demo.policy())
        second=assistant.submit(store,sid,'Explain the next state.','second')['turn_id']
        self.assertEqual(assistant.run_turn(store,second,policy=self.policy())['error']['code'],'ASSISTANT_BUDGET_EXHAUSTED')
        snapshot=deepcopy(store.read_snapshot());snapshot['project_total_budget']={'max_calls':1}
        self.assertEqual(scheduler.aggregate_project_remaining(snapshot),0)

    def test_unknown_evidence_diagnosis_preserves_paused_research_and_is_not_authority(self):
        store,iid,policy=fixture(self.root/'project',1,2);science=prepare(store,iid,policy)[0]
        reserved=execution.reserve(store,science['request_id'],execution_kind='SYNTHETIC_TEST_ONLY')
        store.commit_execution(execution.event('UNKNOWN',{'request_id':science['request_id'],'execution_id':reserved['execution_id'],'reason':'Controlled uncertainty'}))
        Engine().pause(store,iid,'Keep original science paused while diagnosing.');before=store.read_snapshot()
        sid,tid,task=self.prepared(store,'Why is this UNKNOWN? Do not modify any report.',context={'request_id':science['request_id']})
        binary=self.transport([store]);path=self.root/'transport/responses'/task['request_id'];value=loads(path.read_bytes())
        value['report_proposal']={'user_authorized':True,'report_id':'forged','action':'revise'};path.write_bytes(canonical(value))
        self.assertEqual(self.run_actual(store,tid,binary)['state'],'ACCEPTED')
        self.assertIsNone(assistant.revision_authorization(store,tid))
        after=store.read_snapshot();self.assertEqual(after['instances'][iid]['status'],'PAUSED');self.assertEqual(after['requests'][science['request_id']],before['requests'][science['request_id']])
        response=assistant.status(store,sid)['messages'][-1]['structured'];self.assertTrue(response['unknowns'])
        evidence=loads(store.read_blob(task['evidence_ref']));row=next(x for x in evidence['items'] if x['id']=='request:'+science['request_id'])
        self.assertEqual(row['value']['execution_state'],'UNKNOWN');self.assertEqual(len(after['requests']),2)
        self.assertEqual(scheduler.project_remaining(after),scheduler.project_remaining(before))

    def test_assistant_capture_wait_and_unknown_recover_original_only(self):
        for mode in ('capture','unknown'):
            with self.subTest(mode=mode),TemporaryDirectory(dir=self.root) as tmp:
                base=Path(tmp);store=Store.create(base/'project','Recovery fixture',synthetic=True)
                sid,tid,task=self.prepared(store);transport=self.root/'transport'
                if transport.exists():
                    import shutil
                    shutil.rmtree(transport)
                binary=self.transport([store],exit_code=17 if mode=='unknown' else 0)
                if mode=='capture':
                    with patch('research_studio.assistant.recover',side_effect=PMRSError('RESOURCE_DISK_LOW','Controlled capture admission wait')):
                        result=self.run_actual(store,tid,binary)
                    self.assertEqual(result['state'],'RESOURCE_WAIT');self.assertEqual(result['execution_state'],'CAPTURED')
                    with patch('research_studio.runner.subprocess.Popen',side_effect=AssertionError('Original capture recovery cannot resend')):
                        self.assertEqual(self.run_actual(Store(store.root),tid,binary)['state'],'ACCEPTED')
                else:
                    self.assertEqual(self.run_actual(store,tid,binary)['state'],'UNKNOWN')
                    self.assertEqual(host_pool.status()['active'],1)
                    with patch('research_studio.runner.subprocess.Popen',side_effect=AssertionError('UNKNOWN cannot resend')):
                        self.assertEqual(self.run_actual(Store(store.root),tid,binary)['state'],'UNKNOWN')
                    raw=(transport/'responses'/task['request_id']).read_bytes();execution.capture(store,task['request_id'],raw)
                    self.assertEqual(assistant.run_turn(store,tid,executor=assistant.demo_executor())['state'],'ACCEPTED')
                self.assertEqual(len([e for e in events(transport/'events.jsonl') if e['phase']=='start']),1)
                self.assertEqual(assistant.status(store,sid)['budget']['used'],1);self.assertEqual(host_pool.status()['active'],0)
                evidence('assistant-original-'+mode,{'request_id':task['request_id'],'task_id':task['task_id'],'transport_events':events(transport/'events.jsonl'),
                    'final_request':store.read_snapshot()['requests'][task['request_id']],'budget':assistant.status(store,sid)['budget']})

    def test_separate_process_science_and_assistant_share_exact_lower_project_slot(self):
        store,iid,policy=fixture(self.root/'project',1,1);science=prepare(store,iid,policy)[0]
        sid,tid,task=self.prepared(store,context={'instance_id':iid});binary=self.transport([store])
        config=loads((self.root/'transport/config.json').read_bytes());release=self.root/'release';config['release_file']=str(release)
        (self.root/'transport/config.json').write_bytes(canonical(config))
        process=subprocess.Popen([sys.executable,'-B','-m','tests.test_model_pool','worker',str(store.root),iid,str(binary),'1'],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
        try:
            deadline=time.monotonic()+10
            while not events(self.root/'transport/events.jsonl') and time.monotonic()<deadline:time.sleep(.02)
            self.assertEqual(host_pool.status()['active'],1)
            waiting=self.run_actual(store,tid,binary);self.assertEqual(waiting['state'],'RESOURCE_WAIT');self.assertEqual(waiting['request_id'],task['request_id'])
            self.assertEqual(host_pool.status()['slots'][0]['project'],host_pool.project_key(store))
            release.touch();stdout,stderr=process.communicate(timeout=10);self.assertEqual(process.returncode,0,stderr)
            self.assertEqual(self.run_actual(store,tid,binary)['state'],'ACCEPTED')
        finally:
            if process.poll() is None:process.terminate();process.wait(timeout=3)
        rows=events(self.root/'transport/events.jsonl');self.assertEqual(peaks(rows)[0],1)
        self.assertEqual({row['project'] for row in rows},{str(store.root)})
        self.assertEqual(len(store.read_snapshot()['requests']),2);self.assertEqual(host_pool.status()['active'],0)
        evidence('assistant-shared-project-slot',{'transport_events':rows,'peak_actual_clients':peaks(rows)[0],'configured_project_limit':1,
            'waiting_request_id':waiting['request_id'],'assistant_request_id':task['request_id'],'real_external_model_calls':0})

    def test_conversation_refs_preserve_long_requirements_and_history_pages_are_bounded(self):
        store=self.project();sid=assistant.open_session(store,{},'open')['session_id'];assistant.authorize(store,sid,4,'grant')
        large='Keep every original theorem and symbol unchanged. '+('Exact finite requirement text. '*6000)
        for n,text in enumerate((large,'Why is the queue waiting?','Discuss the evidence only.')):
            tid=assistant.submit(store,sid,text,'message-'+str(n))['turn_id'];self.assertEqual(assistant.run_turn(store,tid)['state'],'ACCEPTED')
        snapshot=store.read_snapshot();self.assertNotIn(large.encode(),canonical(snapshot['assistant_sessions']))
        self.assertNotIn(large.encode(),canonical(snapshot['assistant_turns']))
        users=[snapshot['assistant_messages'][mid] for mid in snapshot['assistant_sessions'][sid]['message_ids'] if snapshot['assistant_messages'][mid]['role']=='user']
        last=snapshot['tasks'][snapshot['assistant_turns'][tid]['task_id']];packet=loads(store.read_blob(last['input_packet_ref']))
        self.assertTrue({users[0]['body_ref'],users[2]['body_ref']}<=set(packet['material_refs']))
        self.assertNotIn(users[1]['body_ref'],packet['material_refs']);self.assertLess(len(canonical(packet)),16384)
        self.assertNotIn('body_text',canonical(packet).decode())
        read=store.read_blob;seen=[]
        def counted(digest):seen.append(digest);return read(digest)
        with patch.object(store,'read_blob',side_effect=counted):page=assistant.status(store,sid,offset=4,limit=2)
        message_hashes={m.get('body_ref') or m['capture_ref'] for m in snapshot['assistant_messages'].values()}
        self.assertEqual(len(page['messages']),2);self.assertEqual(len([digest for digest in seen if digest in message_hashes]),2)
        self.assertEqual(page['requirement_message_ids'],[mid for mid in snapshot['assistant_sessions'][sid]['message_ids'] if snapshot['assistant_messages'][mid]['role']=='user'])
        old_replies={m['capture_ref'] for m in snapshot['assistant_messages'].values() if m['role']=='assistant'}
        self.assertFalse(old_replies&set(packet['material_refs']))
        latest_reply=snapshot['assistant_messages'][snapshot['assistant_sessions'][sid]['message_ids'][-1]]['capture_ref']
        follow=assistant.submit(store,sid,'Please explain your previous suggestions; do not modify.','referenced-advice')['turn_id']
        self.assertEqual(assistant.run_turn(store,follow)['state'],'ACCEPTED')
        updated=store.read_snapshot();follow_task=updated['tasks'][updated['assistant_turns'][follow]['task_id']]
        follow_packet=loads(store.read_blob(follow_task['input_packet_ref']))
        self.assertEqual(old_replies&set(follow_packet['material_refs']),{latest_reply})
        self.assertIn(users[0]['body_ref'],follow_packet['material_refs'])
        evidence('assistant-conversation-refs',{'long_user_bytes':len(large.encode()),'unrelated_turn_packet_bytes':len(canonical(packet)),
            'referenced_advice_packet_bytes':len(canonical(follow_packet)),'messages_read_for_two_row_page':len([digest for digest in seen if digest in message_hashes]),
            'unreferenced_old_reply_blobs_in_packet':len(old_replies&set(packet['material_refs'])),
            'explicitly_referenced_reply_blobs':list(old_replies&set(follow_packet['material_refs'])),'long_requirement_body_ref':users[0]['body_ref']})
        assistant.record_error(store,tid,'CONTROLLED','token=credential-value password=secret-value Bearer secret-bearer')
        exported=canonical(assistant.export_summary(store,sid)).decode()
        self.assertNotIn('credential-value',exported);self.assertNotIn('secret-value',exported);self.assertNotIn('secret-bearer',exported)
        self.assertNotIn(large,exported)

    def test_paused_report_format_repair_retains_exact_finite_report_domain(self):
        from research_studio import reports
        from research_studio.runner import FakeExecutor,SimulatedCrash
        from tests.test_assistant_reports import paused_report,revision_message,controlled_response
        controlled_policy=self.policy()
        with patch('research_studio.demo.policy',return_value=controlled_policy):
            store,iid,rid=paused_report(self.root/'project',survey_profile='minimal')
            _,_,auth=revision_message(store,iid,rid,'minimal','Please revise only section 3 and clarify its explanation.',calls=3)
            reports.revise_from_assistant(store,auth)
            with self.assertRaises(SimulatedCrash):
                reports.run(store,iid,report_id=rid,executor=FakeExecutor(controlled_response(store),fault_at='AFTER_FREEZE'))
        snapshot=store.read_snapshot();request=next(r for r in snapshot['requests'].values() if r['execution_state']=='PREPARED')
        task=snapshot['tasks'][request['task_id']]
        # The original native grant and freeze select the controlled isolated
        # Codex contract. Initial scientific/report evidence is synthetic only.
        binary=self.transport([])
        (self.root/'transport/responses'/request['request_id']).write_bytes(b'{"bad":true}')
        executor=CodexExecutor(str(binary),timeout=10)
        with patch('research_studio.runner.doctor',return_value={'ready':True,'binary':str(binary)}):
            with self.assertRaisesRegex(PMRSError,'UNKNOWN_FIELD'):
                executor.execute(store,task['task_id'])
        original=store.read_snapshot()['requests'][request['request_id']]
        repaired=execution.prepare_repair(store,request['request_id'],'FORMAT')
        snapshot=store.read_snapshot();repair_task=snapshot['tasks'][repaired['task_id']];repair=snapshot['requests'][repaired['request_id']]
        self.assertEqual(repair['budget_domain'],'REPORT');self.assertEqual(repair['budget_grant_id'],request['budget_grant_id'])
        self.assertEqual(repair['sample_slot'],request['sample_slot']);self.assertEqual(scheduler.budget_remaining(snapshot,repair['budget_grant_id']),1)
        (self.root/'transport/responses'/repair['request_id']).write_bytes(controlled_response(store)(repair_task,snapshot))
        with patch('research_studio.runner.doctor',return_value={'ready':True,'binary':str(binary)}):
            self.assertEqual(executor.execute(store,repair_task['task_id'])['state'],'ACCEPTED')
        snapshot=store.read_snapshot();self.assertEqual(snapshot['instances'][iid]['status'],'PAUSED')
        self.assertEqual(scheduler.project_remaining(snapshot),0);self.assertEqual(store.read_blob(original['capture_ref']),b'{"bad":true}')
        with self.assertRaisesRegex(PMRSError,'REPAIR_LIMIT'):execution.prepare_repair(store,request['request_id'],'FORMAT')
        self.assertEqual(len([e for e in events(self.root/'transport/events.jsonl') if e['phase']=='start']),2)
        evidence('assistant-report-format-repair',{'original_request_id':request['request_id'],'repair_request_id':repair['request_id'],
            'budget_domain':repair['budget_domain'],'budget_grant_id':repair['budget_grant_id'],'remaining':scheduler.budget_remaining(snapshot,repair['budget_grant_id']),
            'science_remaining':scheduler.project_remaining(snapshot),'science_state':snapshot['instances'][iid]['status'],'transport_events':events(self.root/'transport/events.jsonl')})
        def failed_renderer(*args,**kwargs):raise PMRSError('REPORT_RENDER_FAILED','Controlled local renderer failure; token=fixture-secret')
        with self.assertRaisesRegex(PMRSError,'REPORT_RENDER_FAILED'):
            reports.render(store,failed_renderer,iid,'minimal',report_id=rid)
        store.commit_report(reports._event('REPORT_FAILED',rid,{'code':'REPORT_RENDER_FAILED','message':'Controlled local renderer failure; token=fixture-secret'},'minimal'))
        sid=assistant.open_session(store,{'request_id':repair['request_id'],'report_id':rid,'profile':'minimal'},'failed-report-diagnosis')['session_id']
        assistant.authorize(store,sid,1,'failed-report-budget')
        tid=assistant.submit(store,sid,'Why did this report fail? Do not modify it.','failed-report-message')['turn_id']
        self.assertEqual(assistant.run_turn(store,tid,executor=assistant.demo_executor())['state'],'ACCEPTED')
        state=store.read_snapshot();task=state['tasks'][state['assistant_turns'][tid]['task_id']]
        diagnostics=loads(store.read_blob(task['evidence_ref']))
        report_evidence=next(row['value'] for row in diagnostics['items'] if row['id']=='report:'+rid)
        self.assertEqual(report_evidence['failure_history'][-1]['code'],'REPORT_RENDER_FAILED')
        self.assertIn('Controlled local renderer failure',report_evidence['failure_history'][-1]['message'])
        self.assertNotIn('fixture-secret',canonical(diagnostics).decode())
        request_evidence=next(row['value'] for row in diagnostics['items'] if row['id']=='request:'+repair['request_id'])
        self.assertEqual(request_evidence['receipt_ref'],state['requests'][repair['request_id']]['receipt_ref'])
        self.assertFalse(report_evidence['diagnostic_coverage']['semantic_review_available'])
        self.assertIsNone(assistant.revision_authorization(store,tid))
        evidence('assistant-report-failure-diagnosis',diagnostics)
        store.audit()

    def test_report_scope_requires_original_explicit_extent_and_conflict_resolution(self):
        from research_studio import reports
        from tests.test_assistant_reports import paused_report,revision_message
        store,iid,rid=paused_report(self.root/'project',survey_profile='minimal')
        before=store.read_snapshot()['reports'][rid]['profiles']['minimal']['revision']
        with self.assertRaisesRegex(PMRSError,'ASSISTANT_SCOPE_REQUIRED'):
            revision_message(store,iid,rid,'minimal','Please edit it.',operation='ambiguous')
        sid,_,full=revision_message(store,iid,rid,'minimal','Please revise the whole report.',operation='full')
        self.assertEqual(full['scope'],{'kind':'FULL'})
        with self.assertRaisesRegex(PMRSError,'ASSISTANT_SCOPE_REQUIRED'):
            revision_message(store,iid,rid,'minimal','请继续只修订第 3 节，其他章节不动。',session_id=sid,operation='conflict')
        _,_,narrow=revision_message(store,iid,rid,'minimal','请改为只修订第 3 节，其他章节不动。',session_id=sid,operation='clarified')
        sections=reports.revision_target(store,iid,rid,'minimal')['sections'];third=next(row['id'] for row in sections if row['number']==3)
        self.assertEqual(narrow['scope'],{'kind':'SECTIONS','sections':[third]})
        _,_,guide=revision_message(store,iid,rid,'minimal','请继续只修订第 3 节，其他章节不动。',operation='guide')
        self.assertEqual(guide['scope'],{'kind':'SECTIONS','sections':[third]})
        sid=assistant.open_session(store,{'instance_id':iid,'report_id':rid,'profile':'minimal'},'discussion')['session_id']
        assistant.authorize(store,sid,2,'discussion-budget')
        discussion=assistant.submit(store,sid,'Discussion only: also retain beta and leave all other sections unchanged.','discussion-first')
        self.assertEqual(assistant.run_turn(store,discussion['turn_id'])['state'],'ACCEPTED')
        self.assertIsNone(assistant.revision_authorization(store,discussion['turn_id']))
        _,_,completed_scope=revision_message(store,iid,rid,'minimal','Please revise only section 3 and retain the above requirements.',session_id=sid,operation='discussion-target')
        self.assertEqual(completed_scope['scope'],{'kind':'SECTIONS','sections':[third]})
        snapshot=store.read_snapshot();self.assertEqual(snapshot['reports'][rid]['profiles']['minimal']['revision'],before)
        self.assertFalse(any(grant.get('budget_domain')=='REPORT' for grant in snapshot['budget_grants'].values()))


if __name__=='__main__':unittest.main()
