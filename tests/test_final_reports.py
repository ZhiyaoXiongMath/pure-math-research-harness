"""Native reporting, persisted independent captures and actual all-page rendering."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from research_studio import reports,report_catalog,demo,changes,contracts as C,execution
from research_studio.engine import Engine
from research_studio.runner import FakeExecutor,SimulatedCrash
from research_studio.render import Renderer
from research_studio.util import canonical,sha,PMRSError

RENDER_CACHE={}
def actual_render(body,*,synthetic=False):
    key=sha(body)
    if key not in RENDER_CACHE:RENDER_CACHE[key]=Renderer()(body,synthetic=synthetic)
    return deepcopy(RENDER_CACHE[key])

class FinalReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.e=Engine()
        self.store=self.e.create(Path(self.tmp.name)/'project',demo.ARITHMETIC,synthetic=True)
        self.target=next(iter(self.store.read_snapshot()['records']));self.iid=self.e.new_workflow(self.store,'TRW',target_ref=self.target)['instance_id']
        self.e.authorize(self.store,self.iid,{'intent':'Produce an honest scoped report with a finite test budget.',
          'authorized_scope':{'target_refs':[self.target],'reports':True,'allow_derived_work':True},'obligations':[]},
          {'max_calls':32,'max_workers':2,'execution_policy':demo.policy()})
    def state(self):return self.store.read_snapshot()
    def entry(self):
        s=self.state();return s['reports'][s['active_reports'][self.iid]]
    def run_report(self,factory=demo.response,**kwargs):
        ex=FakeExecutor(factory);result=reports.run(self.store,self.iid,executor=ex,policy=demo.policy(),renderer=actual_render,**kwargs)
        return result,ex
    def frozen_task(self):
        ex=FakeExecutor(demo.response,fault_at='AFTER_FREEZE')
        with self.assertRaises(SimulatedCrash):reports.run(self.store,self.iid,executor=ex,policy=demo.policy(),renderer=actual_render)
        s=self.state();return next(s['tasks'][r['task_id']] for r in s['requests'].values() if r['execution_state']=='PREPARED')
    def preflight(self,t,payload):
        kind='REPORT_OUTPUT' if t['role']=='REPORT_AUTHOR' else 'REPORT_REVIEW'
        raw=canonical({'schema':C.RESPONSE_SCHEMA,'task_id':t['task_id'],'request_id':t['request_id'],'payload_kind':kind,'payload':payload})
        return changes.validate_response(t,self.state(),raw,blob_get=self.store.read_blob)

    def test_real_pdf_png_native_pair_exact_sequence_and_repeat_zero_calls(self):
        before=deepcopy(self.state()['records']);result,ex=self.run_report();self.assertEqual(result['state'],'COMPLETED_CURRENT_REPORT')
        s=self.state();tasks=[s['tasks'][tid] for tid in result['tasks']]
        self.assertEqual([(t['role'],t['report_context']['profile']) for t in tasks],[(r,p) for p in ('lecture','minimal') for r in ('REPORT_AUTHOR','REPORT_SEMANTIC','REPORT_VISUAL')])
        self.assertEqual(s['records'],before);self.assertFalse(s['supports']);self.assertEqual(s['instances'][self.iid]['target_ref'],self.target)
        for profile in self.entry()['profiles'].values():
            self.assertTrue(reports.profile_complete(profile));self.assertFalse(profile['render']['synthetic'])
            self.assertTrue(profile['render']['environment']['namespace_isolated']);self.assertTrue(profile['render']['environment']['all_pages_rendered'])
            self.assertTrue(self.store.read_blob(profile['render']['pdf_sha256']).startswith(b'%PDF-'))
            body=self.store.read_blob(profile['body_sha256']).decode();self.assertIn('Statement 1 (Open)',body);self.assertNotRegex(body,r'[\u3400-\u9fff]')
            for page in profile['render']['pages']:
                self.assertTrue(self.store.read_blob(page['sha256']).startswith(b'\x89PNG\r\n\x1a\n'));self.assertEqual(profile['visual'][page['id']]['sha256'],page['sha256'])
        self.assertEqual([t['model_policy']['reasoning_effort'] for t in tasks],['xhigh','xhigh','high']*2)
        self.assertTrue(all(s['requests'][t['request_id']]['receipt_ref'] for t in tasks))
        self.assertEqual(ex.calls,6);before=self.store._head();again,ex2=self.run_report();self.assertEqual(ex2.calls,0);self.assertEqual(before,self.store._head());self.store.audit()

    def test_every_actual_page_batched_with_adjacent_context(self):
        def many(task,state):
            payload=reports.demo_payload(task,state)
            if task['role']=='REPORT_AUTHOR':payload['body']+=''.join('\\newpage\nPage '+str(n)+' has an explicitly open research boundary.\n' for n in range(2,18))
            return canonical({'schema':C.RESPONSE_SCHEMA,'task_id':task['task_id'],'request_id':task['request_id'],
                'payload_kind':'REPORT_OUTPUT' if task['role']=='REPORT_AUTHOR' else 'REPORT_REVIEW','payload':payload})
        result,ex=self.run_report(many);self.assertEqual(result['state'],'COMPLETED_CURRENT_REPORT');self.assertEqual(ex.calls,10)
        tasks=[self.state()['tasks'][tid] for tid in result['tasks']]
        for p in ('lecture','minimal'):
            visual=[t['report_context'] for t in tasks if t['role']=='REPORT_VISUAL' and t['report_context']['profile']==p]
            self.assertEqual([len(c['pages']) for c in visual],[8,8,1]);self.assertTrue(visual[0]['context_pages'])
            self.assertEqual(len(self.entry()['profiles'][p]['visual']),17)
        entry=self.entry();profile=entry['profiles']['lecture'];changed=deepcopy(profile['render'])
        changed['pages'][8]['sha256']=changed['pages'][0]['sha256'];changed['identity']='changed-one-page'
        event=reports._event('REPORT_RENDERED',entry['report_id'],{'content_key':reports.content_key(profile),'render':changed,'files':{},'blobs':[]},'lecture')
        updated=reports.apply_event(self.state(),event)['reports'][entry['report_id']]['profiles']['lecture']
        self.assertEqual(updated['semantic'],profile['semantic']);self.assertEqual(len(updated['visual']),14)
        for index in (7,8,9):self.assertNotIn(changed['pages'][index]['id'],updated['visual'])
        self.assertFalse(reports.profile_complete(updated))

    def test_report_objection_creates_open_research_duty_atomically(self):
        def objection(t,s):
            if t['role']!='REPORT_SEMANTIC':return demo.response(t,s)
            payload={'profile':t['report_context']['profile'],'verdict':'REVISE','uncheckable':[],
             'findings':[{'code':'NEW_LEMMA_REQUIRED','anchor':'Statement S1','severity':'BLOCKING','description':'A uniform estimate is missing from the supplied argument.'}]}
            return canonical({'schema':C.RESPONSE_SCHEMA,'task_id':t['task_id'],'request_id':t['request_id'],'payload_kind':'REPORT_REVIEW','payload':payload})
        result,ex=self.run_report(objection);self.assertEqual(result['state'],'REPORT_BLOCKED');entry=self.entry();self.assertFalse(entry['profiles']['minimal']['body_sha256'])
        item=entry['open_research_requests'][0];duty=self.state()['obligations'][item['obligation_id']]
        self.assertEqual(duty['definition']['type'],'ESTABLISH');self.assertEqual(duty['projection']['work_state'],'OPEN');self.assertEqual(duty['projection']['resolution'],'UNRESOLVED')
        self.assertFalse(duty['definition']['consumer_bindings']);self.assertIn(b'uniform estimate',self.store.read_blob(duty['definition']['criterion_body_ref']))
        self.assertTrue(entry['profiles']['lecture']['body_sha256']);self.assertFalse(self.state()['supports']);self.assertEqual(self.state()['instances'][self.iid]['status'],'ACTIVE')
        request=self.state()['requests'][item['request_id']];self.assertEqual(request['acceptance_state'],'ACCEPTED');self.assertTrue(request['receipt_ref']);self.store.audit()
        from research_studio import views,workflow_instances as W
        head=self.store._head();state=self.state();oid=item['obligation_id']
        self.assertIn(oid,[o['obligation_id'] for o in views.frontier(state,self.store.read_blob,instance_id=self.iid)['obligations']])
        self.assertIn(oid,[o['obligation_id'] for o in W.decision_basis(state,self.iid)['open_obligation_refs']])
        self.assertEqual(self.store._head(),head);self.assertFalse(state['obligations'][oid]['definition']['consumer_bindings'])
        changed=deepcopy(state);changed['reports'][entry['report_id']]['open_research_requests'][0]['request_id']='unbound-request'
        self.assertNotIn(oid,W.report_obligation_ids(changed,self.iid))
        other=self.e.new_workflow(self.store,'TRW',target_ref=self.target)['instance_id'];state=self.state()
        self.assertNotIn(oid,[o['obligation_id'] for o in views.frontier(state,self.store.read_blob,instance_id=other)['obligations']])
        self.assertNotIn(oid,[o['obligation_id'] for o in W.decision_basis(state,other)['open_obligation_refs']])


    def test_capture_crash_recovery_and_unknown_never_resends(self):
        ex=FakeExecutor(demo.response,fault_at='AFTER_CAPTURE_RECEIPT_BEFORE_ADMISSION')
        with self.assertRaises(SimulatedCrash):reports.run(self.store,self.iid,executor=ex,policy=demo.policy(),renderer=actual_render)
        s=self.state();request=next(iter(s['requests'].values()));self.assertEqual(request['execution_state'],'CAPTURED');capture=request['capture_ref']
        result,fresh=self.run_report();self.assertEqual(result['state'],'COMPLETED_CURRENT_REPORT');self.assertEqual(fresh.calls,5);self.assertEqual(self.state()['requests'][request['request_id']]['capture_ref'],capture)
        reports.revise(self.store,self.iid,'lecture','Repair the explicitly selected presentation.')
        ex=FakeExecutor(demo.response,fault_at='AFTER_RESERVATION_BEFORE_SEND')
        with self.assertRaises(SimulatedCrash):reports.run(self.store,self.iid,executor=ex,policy=demo.policy(),renderer=actual_render)
        request=next(r for r in self.state()['requests'].values() if r['execution_state']=='RESERVED')
        self.store.commit_execution(execution.event('UNKNOWN',{'request_id':request['request_id'],'execution_id':request['execution_id'],'reason':'No completion evidence.'}))
        result,fresh=self.run_report();self.assertEqual(result['code'],'UNKNOWN_REQUIRES_EVIDENCE');self.assertEqual(fresh.calls,0)

    def test_exact_shared_math_terminal_lf_only_and_old_body_preserved(self):
        self.run_report(max_tasks=3);t=self.frozen_task();self.assertEqual(t['report_context']['profile'],'minimal');p=reports.demo_payload(t,self.state())
        bad=deepcopy(p);bad['notation_tex']+=' Different meaning.'
        with self.assertRaisesRegex(PMRSError,'REPORT_MINIMAL_PARENT_MISMATCH'):self.preflight(t,bad)
        bad=deepcopy(p);bad['shared_statements'][0]['statement_tex']='A different quantified assertion.'
        with self.assertRaisesRegex(PMRSError,'REPORT_MINIMAL_PARENT_MISMATCH'):self.preflight(t,bad)
        p['notation_tex']+='\n';p['shared_statements'][0]['statement_tex']+='\n';plan=self.preflight(t,p)
        self.assertEqual(len(plan['report_event']['payload']['result']['lf_transport']),2)
        self.assertEqual(plan['report_event']['payload']['result']['shared_statements'],self.entry()['profiles']['lecture']['shared_statements'])
        old=self.entry()['profiles']['lecture']['body_sha256'];reports.revise(self.store,self.iid,'lecture','Exact bounded revision.')
        self.assertEqual(self.entry()['profiles']['lecture']['history'][0]['body_sha256'],old);self.assertTrue(self.store.read_blob(old))
        for n in range(3):reports.revise(self.store,self.iid,'lecture','Same finite repair allowance '+str(n)+'.')
        with self.assertRaisesRegex(PMRSError,'REPORT_REPAIR_LIMIT'):reports.revise(self.store,self.iid,'lecture','No unlimited repairs.')

    def test_strict_contract_no_science_tex_language_or_false_pass(self):
        t=self.frozen_task();p=reports.demo_payload(t,self.state());bad=deepcopy(p);bad['operations']=[]
        with self.assertRaisesRegex(PMRSError,'REPORT_NO_NEW_SCIENCE'):self.preflight(t,bad)
        bad=deepcopy(p);bad['coverage']={}
        with self.assertRaisesRegex(PMRSError,'REPORT_COVERAGE'):self.preflight(t,bad)
        bad=deepcopy(p);bad['body']+=r'\input{/etc/passwd}'
        with self.assertRaisesRegex(PMRSError,'PDF_TEX_UNSUPPORTED'):self.preflight(t,bad)
        bad=deepcopy(p);bad['body']+=' 新写中文证明。'
        with self.assertRaisesRegex(PMRSError,'LANGUAGE_MISMATCH'):self.preflight(t,bad)
        self.run_report(max_tasks=1);t=self.frozen_task();p=reports.demo_payload(t,self.state());self.assertEqual(t['role'],'REPORT_SEMANTIC')
        p['uncheckable']=['A premise remains unread.']
        with self.assertRaisesRegex(PMRSError,'REPORT_CONTRADICTORY_PASS'):self.preflight(t,p)
        self.run_report(max_tasks=1);t=self.frozen_task();p=reports.demo_payload(t,self.state());self.assertEqual(t['role'],'REPORT_VISUAL');p['pages'][0]['sha256']='0'*64
        with self.assertRaisesRegex(PMRSError,'REPORT_PAGE_IDENTITY'):self.preflight(t,p)

    def test_independent_capture_cannot_be_forged_or_used_in_real_project(self):
        self.run_report(max_tasks=1);t=self.frozen_task();payload=reports.demo_payload(t,self.state());raw=canonical({'schema':C.RESPONSE_SCHEMA,'task_id':t['task_id'],'request_id':t['request_id'],'payload_kind':'REPORT_REVIEW','payload':payload})
        reservation=execution.reserve(self.store,t['request_id'],execution_kind='SYNTHETIC_TEST_ONLY');execution.capture(self.store,t['request_id'],raw,execution_id=reservation['execution_id'])
        s=self.state();proposal=changes.validate_response(t,s,raw,'live',self.store.read_blob)
        forged=deepcopy(s);forged['review_executions'].clear()
        with self.assertRaisesRegex(PMRSError,'REPORT_INDEPENDENCE_REQUIRED'):changes.apply_validated(forged,proposal)
        forged=deepcopy(s);forged['synthetic_test_only']=False
        with self.assertRaisesRegex(PMRSError,'REPORT_REVIEW_SOURCE_REQUIRED'):changes.apply_validated(forged,proposal)
        self.assertEqual(execution.recover(self.store,t['request_id'])['state'],'ACCEPTED')

    def test_catalog_pure_scoped_classes_and_damage_is_visible(self):
        rid=reports.create(self.store,self.iid);head=self.store._head()
        for _ in range(3):reports.catalog(self.store);reports.prepare(self.store,self.iid,check_only=True)
        self.assertEqual(head,self.store._head());self.assertEqual(self.state()['usage']['model_calls'],0)
        s=self.state();entry=s['reports'][rid]
        self.assertEqual(report_catalog.classify(self.store,s,{'historical_only':True}),'UNKNOWN_FORMAT')
        self.assertEqual(report_catalog.classify(self.store,s,{'schema':'unknown'}),'UNKNOWN_FORMAT')
        self.assertEqual(report_catalog.classify(self.store,s,entry),'RECOVERABLE_ACTIVE_CANDIDATE')
        self.store.commit(changes.prepare_material_input(s,b'Unrelated supporting material.',blob_get=self.store.read_blob))
        self.assertEqual(reports.create(self.store,self.iid),rid)
        changed=self.state();changed['records'][self.target]['data']['form']='CONJECTURE'
        self.assertEqual(report_catalog.classify(self.store,changed,entry),'STALE_CANDIDATE')
        path=next(iter(entry['files']));(self.store.root/path).write_bytes((self.store.root/path).read_bytes()+b' ')
        self.assertEqual(reports.catalog(self.store)[0]['classification'],'DAMAGED_ACTIVE_ARTIFACT')
        self.assertEqual(report_catalog.classify(self.store,changed,entry),'DAMAGED_ACTIVE_ARTIFACT')
        with self.assertRaisesRegex(PMRSError,'DAMAGED_ACTIVE_ARTIFACT'):reports.create(self.store,self.iid)
        decision=self.e.decide(self.store,self.iid,'CONTINUE','Continue from the intact exact knowledge basis.',snapshot_commit=self.state()['knowledge_commit'])
        self.assertTrue(decision['decision_id']);self.assertFalse(self.entry()['profiles']['minimal']['body_sha256'])
        reports.abandon(self.store,self.iid,'The active original snapshot was changed; preserve the damage record.')
        self.assertNotEqual(reports.create(self.store,self.iid),rid)

    def test_completed_pdf_tamper_and_layout_vs_math_invalidation(self):
        self.run_report();entry=self.entry();p=entry['profiles']['lecture'];rid=entry['report_id'];s=self.state()
        changed=deepcopy(p['render']);changed['identity']='layout-change';changed['environment']['layout_version']='new-fonts'
        e=reports._event('REPORT_RENDERED',rid,{'content_key':reports.content_key(p),'render':changed,'files':{},'blobs':[]},'lecture')
        layout=reports.apply_event(s,e);self.assertEqual(layout['reports'][rid]['profiles']['lecture']['semantic'],p['semantic'])
        changed['semantic_policy']='new-mathematical-macro-semantics';e=reports._event('REPORT_RENDERED',rid,{'content_key':reports.content_key(p),'render':changed,'files':{},'blobs':[]},'lecture')
        math=reports.apply_event(s,e);self.assertIsNone(math['reports'][rid]['profiles']['lecture']['semantic']);self.assertFalse(math['reports'][rid]['profiles']['lecture']['visual'])
        pdf=next(path for path in entry['files'] if path.endswith('.pdf'));(self.store.root/pdf).write_bytes(b'%PDF-corrupt')
        self.assertEqual(reports.catalog(self.store)[0]['classification'],'DAMAGED_ACTIVE_ARTIFACT')
        with self.assertRaisesRegex(PMRSError,'REPORT_NOT_CURRENT'):reports.finish(self.store,self.iid)

    def test_native_early_delivery_is_honest_and_fake_report_does_not_qualify(self):
        result,ex=self.run_report();self.assertEqual(result['state'],'COMPLETED_CURRENT_REPORT')
        self.assertEqual({r['classification'] for r in reports.catalog(self.store)},{'COMPLETED_CURRENT_REPORT'})
        s=self.state();self.assertFalse({v['stage_id'] for v in s['visits'].values()}&{'P9','P10','P11','P12'})
        before=len(s['tasks']);decision=self.e.decide(self.store,self.iid,'CONTINUE','Use the exact open knowledge basis.',snapshot_commit=s['knowledge_commit'])
        self.assertTrue(decision['decision_id']);self.assertEqual(len(self.state()['tasks']),before)
        with self.assertRaisesRegex(PMRSError,'REPORT_UNKNOWN|DECISION_BASIS_INVALID|CONTROL_EVENT_INVALID'):
            self.e.decide(self.store,self.iid,'CONTINUE','A fake attachment cannot qualify.',snapshot_commit=self.state()['knowledge_commit'],report_ref='made-up-report')

    def test_native_early_decision_missing_failed_and_explicit_report_first(self):
        decision=self.e.decide(self.store,self.iid,'CONTINUE','Continue before any report from the intact exact open knowledge basis.',snapshot_commit=self.state()['knowledge_commit'])
        self.assertTrue(decision['decision_id']);self.assertFalse(self.state()['reports']);self.assertFalse(self.state()['requests'])
        result,_=self.run_report();self.assertEqual(result['state'],'COMPLETED_CURRENT_REPORT')
        iid=self.e.new_workflow(self.store,'TRW',target_ref=self.target)['instance_id']
        self.e.authorize(self.store,iid,{'intent':'Explicitly require the scoped report before continuing.','report_first_actions':['CONTINUE'],
          'authorized_scope':{'target_refs':[self.target],'reports':True},'obligations':[]},{'max_calls':12,'max_workers':2,'execution_policy':demo.policy()})
        with self.assertRaisesRegex(PMRSError,'REPORT_BLOCKED'):
            self.e.decide(self.store,iid,'CONTINUE','The explicit precondition is still missing.',snapshot_commit=self.state()['knowledge_commit'])
        def defect(t,s):
            if t['role']!='REPORT_SEMANTIC':return demo.response(t,s)
            payload={'profile':t['report_context']['profile'],'verdict':'REVISE','uncheckable':[],
               'findings':[{'code':'NEW_LEMMA_REQUIRED','anchor':'Statement S1','severity':'BLOCKING','description':'A required uniform argument is absent.'}]}
            return canonical({'schema':C.RESPONSE_SCHEMA,'task_id':t['task_id'],'request_id':t['request_id'],'payload_kind':'REPORT_REVIEW','payload':payload})
        blocked=reports.run(self.store,iid,executor=FakeExecutor(defect),policy=demo.policy(),renderer=actual_render)
        self.assertEqual(blocked['state'],'REPORT_BLOCKED');rid=blocked['report_id'];old=self.state()['reports'][rid]['profiles']['lecture']['body_sha256']
        with self.assertRaisesRegex(PMRSError,'REPORT_BLOCKED'):
            self.e.decide(self.store,iid,'CONTINUE','The failed report cannot satisfy an explicit gate.',snapshot_commit=self.state()['knowledge_commit'],report_ref=rid)
        reports.revise(self.store,iid,'lecture','Report the unresolved gap honestly without claiming it is proved.')
        completed=reports.run(self.store,iid,executor=demo.executor(),policy=demo.policy(),renderer=actual_render)
        self.assertEqual(completed['state'],'COMPLETED_CURRENT_REPORT')
        self.assertEqual(self.state()['reports'][rid]['profiles']['lecture']['history'][0]['body_sha256'],old)
        self.assertTrue(self.e.decide(self.store,iid,'CONTINUE','The explicit scoped report condition is now met.',snapshot_commit=self.state()['knowledge_commit'],report_ref=rid)['decision_id'])
        self.assertFalse({v['stage_id'] for v in self.state()['visits'].values()}&{'P9','P10','P11','P12'})
        self.assertTrue(any(o['definition']['type']=='ESTABLISH' and o['projection']['work_state']=='OPEN' for o in self.state()['obligations'].values()))

    def test_visual_warning_revise_does_not_complete_or_start_minimal(self):
        def warning(t,s):
            payload=reports.demo_payload(t,s)
            if t['role']=='REPORT_VISUAL':payload['pages'][0].update(verdict='REVISE',findings=[{'code':'LEGIBILITY','anchor':'page-1','severity':'WARNING','description':'Increase the displayed formula size.'}])
            return canonical({'schema':C.RESPONSE_SCHEMA,'task_id':t['task_id'],'request_id':t['request_id'],'payload_kind':'REPORT_OUTPUT' if t['role']=='REPORT_AUTHOR' else 'REPORT_REVIEW','payload':payload})
        result,ex=self.run_report(warning);self.assertEqual(result['state'],'REPORT_BLOCKED');self.assertEqual(ex.calls,3)
        self.assertFalse(reports.profile_complete(self.entry()['profiles']['lecture']));self.assertFalse(self.entry()['profiles']['minimal']['body_sha256'])

    def test_tfdw_zero_candidate_report_and_failure_decision_variants(self):
        iid=self.e.new_workflow(self.store,'TFDW',discovery_scope=demo.discovery_scope('Explore possible formulations without inventing candidates.'))['instance_id']
        self.e.authorize(self.store,iid,{'intent':'Report this exact zero-candidate discovery scope.',
          'authorized_scope':{'target_refs':[],'reports':True},'obligations':[]},{'max_calls':12,'max_workers':2,'execution_policy':demo.policy()})
        result=reports.run(self.store,iid,executor=demo.executor(),policy=demo.policy(),renderer=actual_render)
        self.assertEqual(result['state'],'COMPLETED_CURRENT_REPORT');entry=self.state()['reports'][result['report_id']]
        self.assertFalse(entry['scope']['candidate_refs']);self.assertFalse(self.state()['candidates'])
        self.assertTrue(all(reports.profile_complete(p) for p in entry['profiles'].values()));self.assertTrue(all(self.state()['tasks'][tid]['stage_id']=='D5' for tid in result['tasks']))
        decision=self.e.decide(self.store,iid,'CONTINUE_DISCOVERY','The exact open discovery scope remains unresolved.',snapshot_commit=self.state()['knowledge_commit']);self.assertTrue(decision['decision_id'])
        reports.revise(self.store,iid,'lecture','Expose a concrete research source error.')
        def defect(t,s):
            if t['role']!='REPORT_SEMANTIC':return demo.response(t,s)
            p={'profile':t['report_context']['profile'],'verdict':'REVISE','uncheckable':[], 'findings':[{'code':'SOURCE_PROOF_ERROR','anchor':'Scope','severity':'BLOCKING','description':'The source proof does not address the present formulation.'}]}
            return canonical({'schema':C.RESPONSE_SCHEMA,'task_id':t['task_id'],'request_id':t['request_id'],'payload_kind':'REPORT_REVIEW','payload':p})
        blocked=reports.run(self.store,iid,executor=FakeExecutor(defect),policy=demo.policy(),renderer=actual_render);self.assertEqual(blocked['state'],'REPORT_BLOCKED')
        before=len(self.state()['requests']);decision=self.e.decide(self.store,iid,'CONTINUE_DISCOVERY','Continue the valid scoped research basis despite this report defect.',snapshot_commit=self.state()['knowledge_commit'])
        self.assertTrue(decision['decision_id']);self.assertEqual(len(self.state()['requests']),before);self.assertFalse(self.state()['candidates'])

    def test_unrelated_workflow_commit_is_current_then_relevant_argument_is_stale(self):
        rid=reports.create(self.store,self.iid);old=deepcopy(self.entry());before=report_catalog.fingerprint(self.state(),old['scope'])
        other=self.e.new_workflow(self.store,'TFDW',discovery_scope=demo.discovery_scope('Discover a separate matrix formulation.'))['instance_id']
        self.e.start_round(self.store,other,'Explore the separate formulation.',max_calls=3,policy=demo.policy());self.e.run_round(self.store,other,executor=demo.executor())
        self.assertEqual(report_catalog.fingerprint(self.state(),old['scope']),before);self.assertEqual(reports.catalog(self.store,instance_id=self.iid)[0]['classification'],'RECOVERABLE_ACTIVE_CANDIDATE')
        self.e.start_round(self.store,self.iid,'Investigate the exact original arithmetic target.',max_calls=3,policy=demo.policy());self.e.run_round(self.store,self.iid,executor=demo.executor())
        self.assertNotEqual(report_catalog.fingerprint(self.state(),old['scope']),before)
        self.assertEqual(next(r for r in reports.catalog(self.store) if r['report_id']==rid)['classification'],'STALE_CANDIDATE');self.assertEqual(self.state()['reports'][rid],old)
        self.assertNotEqual(reports.create(self.store,self.iid),rid)
        for path,digest in old['files'].items():self.assertEqual(sha((self.store.root/path).read_bytes()),digest)

    def test_original_chinese_complete_report_stays_english_and_budget_stops(self):
        raw='任意光滑对象是否具备此性质？'.encode();store=self.e.create(Path(self.tmp.name)/'chinese',raw,synthetic=True)
        target=next(iter(store.read_snapshot()['records']));iid=self.e.new_workflow(store,'TRW',target_ref=target)['instance_id']
        self.e.authorize(store,iid,{'intent':'Report only the supplied original question and exact open boundary.',
            'authorized_scope':{'target_refs':[target],'reports':True},'obligations':[]},{'max_calls':6,'execution_policy':demo.policy()})
        result=reports.run(store,iid,executor=demo.executor(),policy=demo.policy(),renderer=actual_render);self.assertEqual(result['state'],'COMPLETED_CURRENT_REPORT')
        entry=store.read_snapshot()['reports'][result['report_id']];self.assertEqual(store.read_blob(store.read_snapshot()['records'][target]['body_sha256']),raw)
        for profile in entry['profiles'].values():
            self.assertNotRegex(store.read_blob(profile['body_sha256']).decode(),r'[\u3400-\u9fff]');self.assertEqual(profile['omissions'][0]['ref'],target)
        reports.revise(store,iid,'lecture','Attempt one explicitly bounded revision after the budget has been used.')
        fresh=demo.executor();result=reports.run(store,iid,executor=fresh,policy=demo.policy(),renderer=actual_render)
        self.assertEqual(result['state'],'WAIT');self.assertEqual(fresh.calls,0);self.assertTrue(any(r.get('code') in ('BUDGET_EXHAUSTED','BUDGET_OR_WORKER_LIMIT') for r in result['reasons']))

    def test_budget_block_and_original_chinese_stays_source_bound(self):
        t=self.frozen_task();s=self.state();request=s['requests'][t['request_id']]
        # A held request stays visible; the report pipeline never resets its grant.
        reservation=execution.reserve(self.store,t['request_id'],execution_kind='SYNTHETIC_TEST_ONLY')
        result,ex=self.run_report();self.assertEqual(result['code'],'EXISTING_REQUEST');self.assertEqual(ex.calls,0)
        raw='任意光滑对象是否具备此性质？'.encode();receipt=self.store.commit(changes.prepare_source_input(self.state(),raw))
        original=self.state()['sources'][receipt['source_ref']]['blob_hash'];self.assertEqual(self.store.read_blob(original),raw)
        self.assertEqual(self.state()['records'][receipt['target_ref']]['data']['representation'],'SOURCE_BOUND')

if __name__=='__main__':unittest.main()
