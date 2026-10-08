"""Controlled author transport, native report lifecycle and real isolated PDFs.

These captures test software contracts only. Synthetic reviews do not establish
mathematical correctness or constitute a real model or literature assessment.
"""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from research_studio import assistant, changes, contracts as C, demo, execution, reports, scheduler
from research_studio.engine import Engine
from research_studio.runner import FakeExecutor, SimulatedCrash
from research_studio.util import canonical, loads, PMRSError, sha
from tests.test_final_reports import actual_render
from tests.test_survey import ready_survey


def controlled_response(store):
    """Reusable for the HTTP/browser fixture: real files, no external calls."""
    def response(task, snapshot):
        if task.get('purpose')=='PROJECT_ASSISTANT':
            return canonical({'schema':assistant.RESPONSE_SCHEMA,'request_id':task['request_id'],
                'reply':'The requested report edit is scoped to the selected original manuscript. This is a controlled software fixture.',
                'facts':[],'inferences':[],'unknowns':[],'advice':[],'report_proposal':None})
        payload=reports.demo_payload(task,snapshot,blob_get=store.read_blob)
        ctx=task['report_context'];revision=ctx.get('revision_request')
        requirements=''
        if revision:
            assert set(revision['requirement_refs'])<=set(ctx['files'].values())
            requirements='\n'.join(store.read_blob(ref).decode() for ref in revision['requirement_refs'])
        if revision and task['role']=='REPORT_AUTHOR':
            text=requirements+'\n'+store.read_blob(revision['instruction_ref']).decode()
            addition=('The alpha requirement remains in this exposition.\n' if 'alpha' in text.lower() else '')
            addition+=('The beta clarification is also retained.\n' if 'beta' in text.lower() else '')
            addition=addition or 'The selected exposition is clarified without new research.\n'
            if revision['scope']['kind']=='SECTIONS':
                raw=store.read_blob(revision['base']['raw_body_sha256'])
                payload={'profile':ctx['profile'],'replacements':[{'section_id':row['id'],
                    'body':raw[row['start_byte']:row['end_byte']].decode()+'\n'+addition}
                    for row in revision['scope']['ranges']]}
            elif revision['base'].get('raw_body_sha256'):
                payload={'profile':ctx['profile'],'body':store.read_blob(revision['base']['raw_body_sha256']).decode()+'\n'+addition,
                    **deepcopy(revision['base']['metadata'])}
                if ctx['profile']=='minimal' and ctx.get('workflow_kind')!='SURVEY':
                    payload.update(parent_lecture=ctx['parent_lecture'],shared_statements=deepcopy(ctx['shared_statements']),notation_tex=ctx['notation_tex'])
        if revision and task['role']=='REPORT_SEMANTIC':
            actual=store.read_blob(ctx['files']['body.tex']).decode()
            for marker in ('alpha','beta'):
                if marker in requirements.lower():assert marker in actual.lower(),marker+' requirement missing from actual manuscript'
        return canonical({'schema':C.RESPONSE_SCHEMA,'task_id':task['task_id'],'request_id':task['request_id'],
            'payload_kind':'REPORT_OUTPUT' if task['role']=='REPORT_AUTHOR' else 'REPORT_REVIEW','payload':payload})
    return response


def paused_report(path, *, survey_profile=None, research_calls=6):
    """A completed native report and exhausted research budget; never real work."""
    engine=Engine()
    if survey_profile:
        from research_studio import survey
        store,iid,_=ready_survey(path,survey_profile)
        survey.start_activity(store,iid,'S5','Explicit selected synthetic report.',max_calls=3,policy=demo.policy())
    else:
        store=engine.create(path,demo.ARITHMETIC,synthetic=True)
        target=next(iter(store.read_snapshot()['records']))
        iid=engine.new_workflow(store,'TRW',target_ref=target)['instance_id']
        engine.authorize(store,iid,{'intent':'Produce only the controlled initial report.',
            'authorized_scope':{'target_refs':[target],'reports':True,'allow_derived_work':True},'obligations':[]},
            {'max_calls':research_calls,'max_workers':2,'execution_policy':demo.policy()})
    result=reports.run(store,iid,executor=FakeExecutor(controlled_response(store)),policy=demo.policy(),renderer=actual_render)
    assert result['state']=='COMPLETED_CURRENT_REPORT',result
    engine.pause(store,iid,'Keep research paused during explicitly authorized report editing.')
    return store,iid,result['report_id']


def revision_message(store,iid,rid,profile,text,*,session_id=None,calls=6,operation='revision-message'):
    if session_id is None:
        session_id=assistant.open_session(store,{'instance_id':iid,'report_id':rid,'profile':profile},operation_id=operation+'-session')['session_id']
    assistant.authorize(store,session_id,1,operation+'-assistant-budget')
    turn=assistant.submit(store,session_id,text,operation,report_allowance=calls)
    result=assistant.run_turn(store,turn['turn_id'],executor=FakeExecutor(controlled_response(store)),policy=demo.policy())
    assert result.get('acceptance_state')=='ACCEPTED',result
    return session_id,turn['turn_id'],assistant.revision_authorization(store,turn['turn_id'])


class AssistantReportRevisions(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def execute(self,store,iid,rid,**kwargs):
        executor=kwargs.pop('executor',FakeExecutor(controlled_response(store)))
        result=reports.run(store,iid,report_id=rid,executor=executor,renderer=kwargs.pop('renderer',actual_render),**kwargs)
        return result,executor

    def test_a3_two_revisions_read_actual_old_body_and_cumulative_user_requirements(self):
        store,iid,rid=paused_report(self.root/'project')
        sid,tid,auth=revision_message(store,iid,rid,'lecture','Please revise the whole report and include the alpha requirement.',operation='first')
        old=reports.revision_target(store,iid,rid,'lecture')
        request=reports.revise_from_assistant(store,auth)
        result,executor=self.execute(store,iid,rid)
        self.assertEqual(result['state'],'COMPLETED_CURRENT_REPORT');self.assertEqual(executor.calls,6)
        assistant.record_action(store,tid,{**request,'result':result})
        sid,tid,auth2=revision_message(store,iid,rid,'lecture','Please revise the whole report again and add the beta clarification; retain the earlier requirements.',session_id=sid,operation='second')
        self.assertGreaterEqual(len(auth2['requirement_refs']),2)
        reports.revise_from_assistant(store,auth2);result,executor=self.execute(store,iid,rid)
        self.assertEqual(result['state'],'COMPLETED_CURRENT_REPORT');self.assertEqual(executor.calls,6)
        state=store.read_snapshot();entry=state['reports'][rid];p=entry['profiles']['lecture']
        body=store.read_blob(p['raw_body_sha256'])
        self.assertIn(b'alpha requirement',body);self.assertIn(b'beta clarification',body)
        self.assertEqual(p['revision'],2);self.assertEqual(p['history'][0]['raw_body_sha256'],old['raw_body_sha256'])
        self.assertTrue(store.read_blob(p['history'][0]['render']['pdf_sha256']).startswith(b'%PDF-'))
        tasks=[state['tasks'][tid] for tid in result['tasks']]
        for task in tasks:
            if task['role'] in {'REPORT_AUTHOR','REPORT_SEMANTIC'}:
                ctx=task['report_context'];self.assertIn('old-body.tex',ctx['files'])
                self.assertEqual(store.read_blob(ctx['files']['old-body.tex']),store.read_blob(ctx['revision_request']['base']['raw_body_sha256']))
                self.assertTrue(set(auth2['requirement_refs'])<=set(ctx['files'].values()))
        self.assertEqual(entry['profiles']['minimal']['parent_lecture'],reports.content_key(p))
        self.assertEqual(entry['profiles']['minimal']['shared_statements'],p['shared_statements'])
        self.assertEqual(p['semantic']['revision_check']['verdict'],'SATISFIED')
        self.assertEqual(state['instances'][iid]['status'],'PAUSED');store.audit()

    def test_a4_local_section_splice_preserves_other_bytes_and_only_survey_selected_profile(self):
        store,iid,rid=paused_report(self.root/'survey',survey_profile='thematic')
        target=reports.revision_target(store,iid,rid,'thematic');old=store.read_blob(target['raw_body_sha256'])
        _,_,auth=revision_message(store,iid,rid,'thematic','Please revise only section 3 and add the alpha explanation. Leave every other section unchanged.',calls=3)
        requested=reports.revise_from_assistant(store,auth);self.assertEqual(requested['synchronized_profiles'],['thematic'])
        with self.assertRaises(SimulatedCrash):
            self.execute(store,iid,rid,executor=FakeExecutor(controlled_response(store),fault_at='AFTER_FREEZE'))
        state=store.read_snapshot();request=next(r for r in state['requests'].values() if r['execution_state']=='PREPARED')
        task=state['tasks'][request['task_id']]
        wrong={'profile':'thematic','replacements':[{'section_id':target['sections'][0]['id'],'body':'\\section{Introduction}\nUnrequested replacement.\n'}]}
        raw=canonical({'schema':C.RESPONSE_SCHEMA,'task_id':task['task_id'],'request_id':task['request_id'],'payload_kind':'REPORT_OUTPUT','payload':wrong})
        with self.assertRaisesRegex(PMRSError,'REPORT_REVISION_RANGE'):changes.validate_response(task,state,raw,blob_get=store.read_blob)
        result,executor=self.execute(store,iid,rid);self.assertEqual(result['state'],'COMPLETED_CURRENT_REPORT');self.assertEqual(executor.calls,3)
        state=store.read_snapshot();p=state['reports'][rid]['profiles']['thematic'];new=store.read_blob(p['raw_body_sha256'])
        selected=target['sections'][2];prefix=old[:selected['start_byte']];suffix=old[selected['end_byte']:]
        self.assertTrue(new.startswith(prefix));self.assertTrue(new.endswith(suffix));self.assertNotEqual(new,old)
        self.assertTrue(p['revision_check']['non_target_bytes_preserved']);self.assertEqual(set(state['reports'][rid]['profiles']),{'thematic'})
        self.assertFalse(p['render']['synthetic']);self.assertTrue(p['render']['environment']['all_pages_rendered'])
        self.assertEqual(p['shared_statements'],p['history'][0]['shared_statements']);store.audit()

    def test_a7_paused_exhausted_research_gets_only_finite_report_grant(self):
        store,iid,rid=paused_report(self.root/'project');before=store.read_snapshot()
        self.assertEqual(scheduler.project_remaining(before),0)
        _,turn_id,auth=revision_message(store,iid,rid,'lecture','Please revise the whole report for clearer exposition.',calls=None)
        with self.assertRaisesRegex(PMRSError,'REPORT_BUDGET_REQUIRED'):reports.revise_from_assistant(store,auth)
        self.assertEqual(store.read_snapshot()['reports'][rid]['profiles']['lecture']['revision'],0)
        assistant.set_report_allowance(store,turn_id,1,'explicit-report-allowance')
        request=reports.revise_from_assistant(store,auth,report_calls=1)
        partial,first=self.execute(store,iid,rid);self.assertEqual(partial['state'],'WAIT');self.assertEqual(first.calls,1)
        frozen=store.read_snapshot()['tasks'][partial['tasks'][0]];frozen_bytes=canonical(frozen)
        assistant.set_report_allowance(store,turn_id,5,'explicit-extra-report-allowance')
        extension=reports.extend_revision_budget(store,rid,auth)
        self.assertEqual(extension['state'],'REPORT_BUDGET_EXTENDED')
        duplicate=reports.extend_revision_budget(store,rid,auth)
        self.assertEqual(duplicate['state'],'REPORT_BUDGET_UNCHANGED')
        result,executor=self.execute(store,iid,rid);self.assertEqual(result['state'],'COMPLETED_CURRENT_REPORT');self.assertEqual(executor.calls,5)
        after=store.read_snapshot();self.assertEqual(after['project_budget'],before['project_budget'])
        self.assertEqual(canonical(after['tasks'][frozen['task_id']]),frozen_bytes)
        self.assertEqual(set(after['missions']),set(before['missions']))
        for mid,mission in after['missions'].items():
            self.assertEqual({k:v for k,v in mission.items() if k!='stage_visit_ids'},
                {k:v for k,v in before['missions'][mid].items() if k!='stage_visit_ids'})
        new_visits=set(after['visits'])-set(before['visits'])
        self.assertTrue(all(after['visits'][vid]['stage_id']=='P13' for vid in new_visits))
        self.assertEqual(after['records'],before['records'])
        self.assertEqual(after['instances'][iid],before['instances'][iid]);self.assertEqual(scheduler.project_remaining(after),0)
        requests=[after['requests'][after['tasks'][tid]['request_id']] for tid in partial['tasks']+result['tasks']]
        self.assertTrue(all(r['budget_domain']=='REPORT' and r['budget_grant_id']==request['budget_grant_id'] for r in requests))
        self.assertEqual(scheduler.budget_remaining(after,request['budget_grant_id']),0)

    def test_applicable_original_report_allowance_is_reused_without_budget_expansion(self):
        store,iid,rid=paused_report(self.root/'project',research_calls=12);before=store.read_snapshot()
        _,_,auth=revision_message(store,iid,rid,'lecture','Please revise the whole report for clearer exposition.',calls=None)
        revision=reports.revise_from_assistant(store,auth)
        mission=before['missions'][before['instances'][iid]['current_mission_id']]
        self.assertEqual(revision['budget_grant_id'],mission['budget_grant_id'])
        result,executor=self.execute(store,iid,rid);self.assertEqual(result['state'],'COMPLETED_CURRENT_REPORT');self.assertEqual(executor.calls,6)
        after=store.read_snapshot();self.assertEqual(after['project_budget'],before['project_budget'])
        self.assertFalse([g for g in after['budget_grants'].values() if g.get('purpose')=='REPORT'])
        self.assertTrue(all(after['requests'][after['tasks'][tid]['request_id']].get('budget_domain','SCIENCE')=='SCIENCE' for tid in result['tasks']))
        self.assertEqual(scheduler.project_remaining(after),0);self.assertEqual(after['instances'][iid]['status'],'PAUSED')

    def test_exhausted_reused_science_allowance_switches_only_future_report_roles(self):
        store,iid,rid=paused_report(self.root/'project',research_calls=7)
        _,turn_id,auth=revision_message(store,iid,rid,'lecture','Please revise the whole report for clearer exposition.',calls=None)
        original=reports.revise_from_assistant(store,auth)
        partial,first=self.execute(store,iid,rid);self.assertEqual(partial['state'],'WAIT');self.assertEqual(first.calls,1)
        before=store.read_snapshot();author=before['tasks'][partial['tasks'][0]]
        self.assertEqual(author['budget_domain'],'SCIENCE')
        assistant.set_report_allowance(store,turn_id,5,'independent-report-remainder')
        extension=reports.extend_revision_budget(store,rid,auth)
        self.assertNotEqual(extension['budget_grant_id'],original['budget_grant_id'])
        result,fresh=self.execute(store,iid,rid);self.assertEqual(result['state'],'COMPLETED_CURRENT_REPORT');self.assertEqual(fresh.calls,5)
        after=store.read_snapshot();self.assertEqual(after['tasks'][author['task_id']],author)
        self.assertEqual(after['project_budget'],before['project_budget']);self.assertEqual(scheduler.project_remaining(after),0)
        self.assertTrue(all(after['tasks'][tid]['budget_domain']=='REPORT' for tid in result['tasks']))

    def test_a9_long_old_manuscript_and_three_turn_requirements_use_exact_blob_references(self):
        engine=Engine();store=engine.create(self.root/'long',demo.ARITHMETIC,synthetic=True)
        target=next(iter(store.read_snapshot()['records']))
        iid=engine.new_workflow(store,'TRW',target_ref=target)['instance_id']
        engine.authorize(store,iid,{'intent':'Prepare the controlled old report manuscript only.',
            'authorized_scope':{'target_refs':[target],'reports':True,'allow_derived_work':True},'obligations':[]},
            {'max_calls':1,'max_workers':1,'execution_policy':demo.policy()})
        rid=reports.create(store,iid);prepared=reports.advance(store,iid,rid)
        policy={**demo.policy(),'only_obligation_ids':[prepared['obligation_id']]}
        made=scheduler.commit_dispatch(store,scheduler.plan(store.read_snapshot(),[iid],policy),policy=policy)
        tid=made['prepared'][0]['task_id']
        paragraph='This pedagogical discussion preserves the supplied source boundaries and does not establish any missing inference.\n'
        def long_author(task,state):
            payload=reports.demo_payload(task,state,blob_get=store.read_blob)
            payload['body']=payload['body'].replace('\\section{Evidence and open work}',paragraph*950+'\\section{Evidence and open work}')
            return canonical({'schema':C.RESPONSE_SCHEMA,'task_id':task['task_id'],'request_id':task['request_id'],'payload_kind':'REPORT_OUTPUT','payload':payload})
        result=FakeExecutor(long_author).execute(store,tid);self.assertEqual(result['state'],'ACCEPTED')
        engine.pause(store,iid,'Only inspect and prepare an explicit report revision.')
        p=store.read_snapshot()['reports'][rid]['profiles']['lecture'];raw=store.read_blob(p['raw_body_sha256'])
        self.assertGreater(len(raw),100_000);self.assertIsNone(p['render'])
        session=assistant.open_session(store,{'instance_id':iid,'report_id':rid,'profile':'lecture'},'long-session')['session_id']
        assistant.authorize(store,session,3,'three-discussions')
        messages=['Please discuss the alpha wording requirement; do not modify the report yet.',
            'Please discuss retaining the beta terminology; do not modify the report yet.',
            'Please revise only section 3, retain the alpha and beta requirements, and leave all other sections unchanged.']
        for index,text in enumerate(messages):
            turn=assistant.submit(store,session,text,'long-turn-'+str(index),report_allowance=6 if index==2 else None)
            result=assistant.run_turn(store,turn['turn_id'],executor=FakeExecutor(controlled_response(store)),policy=demo.policy())
            self.assertEqual(result['acceptance_state'],'ACCEPTED')
        authorization=assistant.revision_authorization(store,turn['turn_id'])
        reports.revise_from_assistant(store,authorization)
        step=reports.advance(store,iid,rid);policy={**demo.policy(),'only_obligation_ids':[step['obligation_id']]}
        made=scheduler.commit_dispatch(store,scheduler.plan(store.read_snapshot(),[iid],policy),policy=policy)
        task=store.read_snapshot()['tasks'][made['prepared'][0]['task_id']];wire=store.read_blob(task['input_packet_ref'])
        self.assertIn(p['raw_body_sha256'],task['material_refs']);self.assertIn(p['body_sha256'],task['material_refs'])
        self.assertEqual(len({item['path'] for item in task['material_refs'].values()}),len(task['material_refs']))
        self.assertNotIn(raw,wire);self.assertNotIn(raw,canonical(task))
        self.assertLess(len(wire),len(raw)//2);self.assertLess(len(canonical(task)),len(raw)//2)
        self.assertEqual(len(authorization['requirement_refs']),3)
        self.assertTrue(set(authorization['requirement_refs'])<=set(task['report_context']['files'].values()))
        self.assertEqual([store.read_blob(ref).decode() for ref in authorization['requirement_refs']],messages)
        self.assertEqual(store.read_snapshot()['requests'][task['request_id']]['execution_state'],'PREPARED')
        self.assertEqual(store.read_snapshot()['instances'][iid]['status'],'PAUSED')
        print('A9_LONG_OLD_MANUSCRIPT '+canonical({'raw_body_bytes':len(raw),'expanded_body_bytes':len(store.read_blob(p['body_sha256'])),
            'frozen_packet_metadata_bytes':len(wire),'frozen_task_metadata_bytes':len(canonical(task)),
            'material_count':len(task['material_refs']),'unique_material_bytes':sum(v['bytes'] for v in task['material_refs'].values()),
            'requirement_refs':len(authorization['requirement_refs']),'assistant_turns':3,'old_author_calls':1,'revision_author_calls':0}).decode().strip())

    def test_stale_exact_revision_and_forged_scope_do_not_create_grants_or_edits(self):
        store,iid,rid=paused_report(self.root/'project')
        _,_,auth=revision_message(store,iid,rid,'lecture','Please revise only section 3 and leave other sections unchanged.')
        head=store._head();forged=deepcopy(auth);forged['scope']={'kind':'FULL'}
        with self.assertRaisesRegex(PMRSError,'ASSISTANT_AUTHORIZATION_REQUIRED'):reports.revise_from_assistant(store,forged)
        self.assertEqual(store._head(),head)
        reports.revise(store,iid,'lecture','An independent explicit native edit superseded the discussed manuscript.',report_id=rid)
        head=store._head()
        with self.assertRaisesRegex(PMRSError,'REPORT_CONTENT_STALE'):reports.revise_from_assistant(store,auth)
        self.assertEqual(store._head(),head);self.assertEqual(store.read_snapshot()['instances'][iid]['status'],'PAUSED')

    def test_a8_capture_render_resource_wait_and_unknown_preserve_original_request(self):
        store,iid,rid=paused_report(self.root/'survey',survey_profile='minimal')
        _,_,auth=revision_message(store,iid,rid,'minimal','Please revise only section 3 and clarify its explanation.',calls=6)
        reports.revise_from_assistant(store,auth)
        crashing=FakeExecutor(controlled_response(store),fault_at='AFTER_CAPTURE_RECEIPT_BEFORE_ADMISSION')
        with self.assertRaises(SimulatedCrash):self.execute(store,iid,rid,executor=crashing)
        state=store.read_snapshot();request=next(r for r in state['requests'].values() if r['execution_state']=='CAPTURED');capture=request['capture_ref']
        original_task=canonical(state['tasks'][request['task_id']]);calls=len(state['requests'])
        def low_disk(*args,**kwargs):raise PMRSError('RESOURCE_DISK_LOW','Controlled local publication wait.')
        result,fresh=self.execute(store,iid,rid,renderer=low_disk)
        self.assertEqual(result['state'],'RESOURCE_WAIT');self.assertEqual(fresh.calls,0)
        state=store.read_snapshot();self.assertEqual(len(state['requests']),calls)
        self.assertEqual(state['requests'][request['request_id']]['capture_ref'],capture)
        self.assertEqual(canonical(state['tasks'][request['task_id']]),original_task)
        def renderer_failure(*args,**kwargs):raise PMRSError('REPORT_RENDER_FAILED','Controlled renderer failure after captured author.')
        with self.assertRaisesRegex(PMRSError,'REPORT_RENDER_FAILED'):self.execute(store,iid,rid,renderer=renderer_failure)
        result,fresh=self.execute(store,iid,rid);self.assertEqual(result['state'],'COMPLETED_CURRENT_REPORT');self.assertEqual(fresh.calls,2)
        _,_,auth2=revision_message(store,iid,rid,'minimal','Please revise only section 3 again and clarify its explanation.',calls=3,operation='unknown')
        reports.revise_from_assistant(store,auth2)
        uncertain=FakeExecutor(controlled_response(store),fault_at='AFTER_RESERVATION_BEFORE_SEND')
        with self.assertRaises(SimulatedCrash):self.execute(store,iid,rid,executor=uncertain)
        state=store.read_snapshot();request=next(r for r in state['requests'].values() if r['execution_state']=='RESERVED')
        store.commit_execution(execution.event('UNKNOWN',{'request_id':request['request_id'],'execution_id':request['execution_id'],'reason':'Controlled missing transport evidence.'}))
        result,fresh=self.execute(store,iid,rid);self.assertEqual(result['code'],'UNKNOWN_REQUIRES_EVIDENCE');self.assertEqual(fresh.calls,0)
        self.assertEqual(store.read_snapshot()['instances'][iid]['status'],'PAUSED')
