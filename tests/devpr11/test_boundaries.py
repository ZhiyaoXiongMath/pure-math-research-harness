"""Actual task/human read consumers and narrow authority boundaries."""
from copy import deepcopy
import json
import tempfile
import unittest
from pmrh.domain.primitives import canonical,PMRSError
from pmrh.domain.fastmath.model import FastMathError,FastReadContext
from research_studio import knowledge_access as Q,communication as M
from research_studio.task_tools import TaskTools,tool_definitions
from .fixtures import Harness,six_entries,delta_for


def source21_P01_01_02_large_material_TaskTools_pair():
    """Explicit selector only: real full material, bounded delivery, no budget reset."""
    from pathlib import Path
    from research_studio import changes,demo,execution,input_delivery,tasks
    from research_studio.engine import Engine
    from research_studio.store import Store
    from pmrh.domain.primitives import sha
    from tests.devpr05.fixtures import scientific_policy
    check=unittest.TestCase()
    with tempfile.TemporaryDirectory() as tmp:
        engine=Engine();store=engine.create(Path(tmp)/'native',demo.ARITHMETIC,synthetic=True)
        target=next(iter(store.read_snapshot()['records']))
        iid=engine.new_workflow(store,'TRH',target_ref=target)['instance_id']
        needle=b'Source21LateNeedle';offset=9*1024**2-len(needle)
        raw=b'x'*offset+needle;check.assertEqual(len(raw),9*1024**2)
        source=store.commit(changes.prepare_material_input(store.read_snapshot(),raw,
            'Source21 complete synthetic material','text/plain',blob_get=store.read_blob))['source_ref']
        policy=scientific_policy();policy['communication']={}
        # Configure this new synthetic fixture's startup capacity before its
        # first authorization. Its default 64KiB dynamic allowance is never
        # increased; all 9MiB must really fit the initial full-material packet.
        policy['capacity']={**policy['capacity'],'context_window_tokens':16*1024**2,
            'capacity_revision':'source21-synthetic-full-material-16MiB'}
        engine.start_round(store,iid,'Read the complete synthetic source within the frozen tool allowance.',
            source_refs=[source],max_calls=2,max_workers=1,max_research_attempts=1,allow_reports=False,policy=policy)
        prepared=engine.prepare(store,iid)['prepared'];check.assertEqual(len(prepared),1)
        task=tasks.load(store,prepared[0]['task_id']);frozen=deepcopy(task)
        material=next(row for row in task['input_manifest'] if row.get('ref')==source)
        check.assertFalse(material.get('body_coverage'))
        check.assertIn(sha(raw),task['material_refs'])
        check.assertEqual(store.read_blob(task['material_refs'][sha(raw)]['sha256']),raw)
        check.assertEqual(task['communication_contract']['max_dynamic_input_tokens'],65536)
        reserved=execution.reserve(store,task['request_id'],execution_kind='SYNTHETIC_TEST_ONLY')
        eid=reserved['execution_id'];rid=task['request_id']
        store.commit_execution(execution.event('SENT',dict(request_id=rid,execution_id=eid)))
        store=Store(store.root);tools=TaskTools(store,rid,eid)
        before=store.read_snapshot();head=(store.root/'HEAD').read_bytes();history=store.history()
        # Human full-get is allowed; a task's exact full-get fails before a
        # delivery. This direct read must preserve HEAD/history/usage entirely.
        whole=Q.web_tool(store,'get',{'ref':[source],'instance_id':[iid]})
        check.assertEqual(whole['body'].encode(),raw);check.assertEqual(whole['body_sha256'],sha(raw))
        check.assertEqual(whole['read_scope'],'EXACT_REGISTERED_OCCURRENCE')
        with check.assertRaises(PMRSError) as caught:Q.get(store,source,task=task)
        check.assertEqual(caught.exception.code,'DYNAMIC_INPUT_LIMIT')
        check.assertEqual((store.root/'HEAD').read_bytes(),head);check.assertEqual(store.history(),history)
        check.assertEqual(store.read_snapshot(),before)
        deliveries=[]
        for query,matching in (('source21lateneedle',True),('source21 absent sentinel',False)):
            human=Q.web_tool(store,'search',{'q':[query],'target_ref':[source],'instance_id':[iid]})
            did,response=tools.call('knowledge_search',{'query':query,'target_ref':source});deliveries.append(did)
            check.assertFalse(response['isError'],response)
            page=json.loads(response['content'][0]['text'])['result']
            for actual in (human,page):
                check.assertEqual(actual['body_bytes_read_this_call'],len(raw))
                check.assertTrue(actual['complete_for_this_call_scope'])
                check.assertEqual(len(actual['results']),int(matching))
                if matching:
                    hit=actual['results'][0];loc=hit['locator']
                    check.assertEqual(hit['ref'],source)
                    check.assertEqual((loc['start'],loc['end']),(offset,len(raw)))
                    check.assertEqual(loc['quoted_sha256'],sha(needle))
                    check.assertEqual(raw[loc['start']:loc['end']],needle)
                    check.assertGreater(loc['start'],8*1024**2)
            row=store.read_snapshot()['input_deliveries'][did]
            check.assertEqual(store.read_blob(row['response_ref']),canonical(response))
            check.assertEqual(row['supplements'],[])
            input_delivery.confirm(store,rid,eid,did)
        before=store.read_snapshot();head=(store.root/'HEAD').read_bytes();history=store.history()
        rows={k:v for k,v in before.get('input_deliveries',{}).items() if v['request_id']==rid}
        used=sum(row['bytes'] for row in rows.values())
        check.assertLess(task['communication_contract']['max_dynamic_input_tokens']-used,len(raw))
        did,response=tools.call('knowledge_get',{'ref':source});deliveries.append(did)
        check.assertTrue(response['isError'],response)
        result=json.loads(response['content'][0]['text'])['result']
        check.assertEqual(result['error'],'DYNAMIC_INPUT_LIMIT');check.assertNotIn('body',result)
        check.assertNotIn(needle.decode(),canonical(response).decode())
        after=store.read_snapshot();row=after['input_deliveries'][did]
        # The bounded error itself is honestly persisted/charged. No scientific
        # receipt, full-body supplement, request usage or grant is manufactured.
        check.assertNotEqual((store.root/'HEAD').read_bytes(),head)
        check.assertEqual(len(store.history()),len(history)+1)
        check.assertEqual(row['bytes'],len(canonical(response)));check.assertLess(row['bytes'],1024)
        check.assertEqual(row['supplements'],[])
        check.assertEqual(store.read_blob(row['response_ref']),canonical(response))
        for key in ('records','sources','supports','qualifications','accepted_requests','requests','tasks','budget_grants','project_budget'):
            check.assertEqual(after.get(key),before.get(key),key)
        actual={k:v for k,v in after['input_deliveries'].items() if v['request_id']==rid}
        check.assertEqual(set(actual)-set(rows),{did})
        check.assertEqual(sum(v['bytes'] for v in actual.values()),used+row['bytes'])
        input_delivery.confirm(store,rid,eid,did);input_delivery.seal(store,rid,eid)
        replay=Store(store.root).read_snapshot()
        check.assertEqual(replay['tasks'][task['task_id']],frozen)
        check.assertTrue(replay['input_windows'][rid]['sealed'])
        check.assertEqual(replay['input_windows'][rid]['dynamic_input_bytes'],used+row['bytes'])
        check.assertTrue(all(replay['input_deliveries'][d]['supplements']==[] for d in deliveries))


class BoundaryTests(unittest.TestCase):
    def test_FM18_no_duck_typed_service_or_forged_read_context(self):
        from pmrh.application.fastmath import FastMathService
        with self.assertRaises(FastMathError):FastMathService(object(),object())
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);main,worker=h.running_pair();s=h.store.read_snapshot();delta=delta_for(s,worker['task'],six_entries(s,worker['task']))
            context=FastReadContext(h.project,h.iid,worker['task']['mission_id'],worker['task']['task_id'])
            before=h.store._head()
            with self.assertRaises(FastMathError):h.store.fastmath_service().prepare_delta(delta,read_context=context,as_of_commit=s['knowledge_commit'])
            h.storage.fast.bind_read_context(context,h.service)
            prepared=h.store.fastmath_service().prepare_delta(delta,read_context=context,as_of_commit=s['knowledge_commit'])
            self.assertEqual(prepared.value(),delta);self.assertEqual(h.store._head(),before)

    def test_FM16_FM26_current_task_identity_revocation_and_exposure(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);main,worker=h.running_pair(communication=True);task=main['task']
            first=Q.search(h.store,'',task=task,limit=1)
            self.assertEqual(first['as_of_commit'],h.store._head()['commit'])
            forged=deepcopy(task);forged['mission_id']='cross-mission'
            with self.assertRaises(PMRSError):Q.search(h.store,'',task=forged)
            reason=h.blob('revoke',b'Explicit synthetic revocation',raw=True);grant=h.grant()
            h.control.apply(h.command('GRANT_REVOKED',dict(budget_grant_id='BUDGET-synthetic',expected_revision=1,reason_ref=reason)),h.operator,grant_ref=grant)
            with self.assertRaises(PMRSError):Q.search(h.store,'',task=task,continuation=first['continuation'])

    def test_FM25_wrong_capture_and_proposal_only_worker_cannot_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);main,worker=h.running_pair();s=h.store.read_snapshot()
            prepared,captured,args=h.capture_fast(worker,delta_for(s,worker['task'],six_entries(s,worker['task'])))
            altered=h.blob('altered',canonical({'payload':{'fast_delta':{}}}),raw=True)
            head=h.store._head()
            with self.assertRaises(FastMathError):h.store.fastmath_service().capture_delta(prepared,**{**args,'capture_ref':altered})
            forged=h.session(proposal_only=True,actions={'FAST_PROPOSAL_CAPTURED','FAST_DELTA_APPLIED','RECOVER_RECEIPT'})
            with self.assertRaises(FastMathError):h.store.fastmath_service().capture_delta(prepared,**{**args,'session':forged})
            self.assertEqual(h.store._head(),head)

    def test_FM27_TaskTools_actual_delivered_results_for_all_six(self):
        # Separate real frozen input windows avoid treating an exhausted dynamic
        # allowance as authorization to enlarge it for the assertion.
        for wanted in ('KnowledgeModule','Transition','ResearchMap','Frontier/Probe','ReaderProfile','RefinementBinding'):
            with self.subTest(kind=wanted),tempfile.TemporaryDirectory() as tmp:
                h=Harness(tmp);main,worker=h.running_pair(communication=True);s=h.store.read_snapshot();entries=six_entries(s,worker['task'])
                _,captured,_=h.capture_fast(worker,delta_for(s,worker['task'],entries));h.apply_fast(captured['proposal_ref'],main);h.reopen()
                ref=next(e['ref'] for e in entries if e['body']['kind']==wanted)
                tools=TaskTools(h.store,main['spec'].request_id,main['spec'].execution_id)
                frame=h.command('COMMUNICATION_APPLIED',{'native_event':{}})
                args={k:frame[k] for k in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
                with h.control.native_context(h.service,**args,grant_ref=h.grant(),manifest_ref=main['manifest_ref']):
                    delivery,response=tools.call('knowledge_get',{'ref':ref})
                delivered=json.loads(response['content'][0]['text'])
                self.assertFalse(response['isError']);self.assertEqual(delivered['result']['ref'],ref)
                state=h.store.read_snapshot();self.assertEqual(h.store.read_blob(state['input_deliveries'][delivery]['response_ref']),canonical(response))
                schemas={d['name']:d['inputSchema'] for d in tools.definitions}
                self.assertIn('continuation',schemas['knowledge_search']['properties'])
                with self.assertRaises(PMRSError):Q.get(h.store,ref,task={**main['task'],'task_id':'invented'})

    def test_FM27_native_attachment_get_keys_remain_compatible(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);main,worker=h.running_pair(communication=True);s=h.store.read_snapshot();target=s['instances'][h.iid]['target_ref']
            frame=h.command('COMMUNICATION_APPLIED',{'native_event':{}})
            args={k:frame[k] for k in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
            with h.control.native_context(h.service,**args,grant_ref=h.grant(),manifest_ref=worker['manifest_ref']):
                sent=M.send(h.store,worker['spec'].request_id,worker['spec'].execution_id,to='main',body='Exact native target attachment.',
                    idempotency_key='native-attachment',record_refs=[target])
            result=M.read_message(h.store,main['spec'].request_id,main['spec'].execution_id,sent['message_id'],attachment_ref=target)['attachment']
            self.assertTrue({'kind','ref','revision','record','body','body_sha256','status','index_as_of','read_scope'}<=set(result))
            self.assertEqual(result['ref'],target)
            with self.assertRaises(PMRSError):M.read_message(h.store,main['spec'].request_id,main['spec'].execution_id,sent['message_id'],attachment_ref='FM-'+'0'*64)


    def test_FM16_FM27_actual_TaskTools_omitted_and_forged_scope_pairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);main,worker=h.running_pair(communication=True)
            target=h.store.read_snapshot()['instances'][h.iid]['target_ref']
            tools=TaskTools(h.store,main['spec'].request_id,main['spec'].execution_id)
            for args,expected_error in (({'ref':target},False),
                    ({'ref':target,'instance_id':None},True),
                    ({'ref':target,'instance_id':'foreign'},True),
                    ({'ref':target,'mission_id':'foreign'},True),
                    ({'ref':'FM-'+'0'*64},True)):
                with self.subTest(arguments=args):
                    frame=h.command('COMMUNICATION_APPLIED',{'native_event':{}})
                    context={k:frame[k] for k in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
                    with h.control.native_context(h.service,**context,grant_ref=h.grant(),manifest_ref=main['manifest_ref']):
                        delivery,response=tools.call('knowledge_get',args)
                    self.assertEqual(response['isError'],expected_error)
                    payload=json.loads(response['content'][0]['text'])
                    if not expected_error:self.assertEqual(payload['result']['ref'],target)
                    else:self.assertNotIn('body',payload.get('result',payload))
                    state=h.store.read_snapshot()
                    self.assertEqual(h.store.read_blob(state['input_deliveries'][delivery]['response_ref']),canonical(response))


    def test_P01_07_08_actual_TaskTools_native_range_and_current_revocation(self):
        from pmrh.domain.primitives import sha
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);main,worker=h.running_pair(communication=True)
            state=h.store.read_snapshot();target=state['instances'][h.iid]['target_ref']
            raw=h.store.read_blob(state['records'][target]['body_sha256'])
            tools=TaskTools(h.store,main['spec'].request_id,main['spec'].execution_id)
            window=dict(start=0,end=5,unit='UTF8_BYTE')
            frame=h.command('COMMUNICATION_APPLIED',{'native_event':{}})
            args={k:frame[k] for k in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
            with h.control.native_context(h.service,**args,grant_ref=h.grant(),manifest_ref=main['manifest_ref']):
                delivery,response=tools.call('knowledge_get',{'ref':target,'body_range':window})
            self.assertFalse(response['isError']);result=json.loads(response['content'][0]['text'])['result']
            self.assertEqual(result['body'].encode(),raw[:5]);self.assertFalse(result['body_complete'])
            self.assertEqual(result['body_sha256'],sha(raw));self.assertEqual(result['verified_full_body_sha256'],sha(raw))
            self.assertEqual(result['range_locator']['quoted_sha256'],sha(raw[:5]))
            from research_studio import input_delivery
            self.assertEqual(result['read_scope'],'PARTIAL_BODY_RANGE')
            self.assertEqual(result['body_range'],window)
            state=h.store.read_snapshot();delivered=state['input_deliveries'][delivery]
            self.assertEqual(delivered['supplements'],[])
            self.assertEqual(h.store.read_blob(delivered['response_ref']),canonical(response))
            self.assertEqual(input_delivery.supplied_records(state,main['task'],h.store.read_blob,live=True),set())
            self.assertEqual(input_delivery.supplied_sources(state,main['task'],h.store.read_blob,live=True),set())
            # Seal via the same public native call chain, then capture/reopen.
            # The immutable manifest binds the exact range response; whole-blob
            # verification never becomes whole-body scientific exposure.
            frame=h.command('COMMUNICATION_APPLIED',{'native_event':{}})
            args={k:frame[k] for k in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
            with h.control.native_context(h.service,**args):
                binding=input_delivery.seal(h.store,main['spec'].request_id,main['spec'].execution_id)
            h.capture(main);state=h.reopen()
            self.assertEqual(input_delivery.capture_binding(state,main['spec'].request_id),binding)
            sealed=state['input_windows'][main['spec'].request_id]['manifest']['deliveries']
            row=next(d for d in sealed if d['delivery_id']==delivery)
            self.assertEqual(row['supplements'],[])
            self.assertEqual(row['bytes'],len(canonical(response)))
            replayed=json.loads(h.store.read_blob(row['response_ref']))
            exposed=json.loads(replayed['content'][0]['text'])['result']
            self.assertEqual(exposed['body_range'],window);self.assertEqual(exposed['body'].encode(),raw[:5])
            self.assertEqual(input_delivery.supplied_records(state,main['task'],h.store.read_blob),set())
            self.assertEqual(input_delivery.supplied_sources(state,main['task'],h.store.read_blob),set())
            old=result['as_of_commit'];reason=h.blob('range-revoke',b'Explicit synthetic revocation',raw=True)
            h.control.apply(h.command('GRANT_REVOKED',dict(budget_grant_id='BUDGET-synthetic',expected_revision=1,reason_ref=reason)),h.operator,grant_ref=h.grant())
            with self.assertRaises(PMRSError):Q.get(h.store,target,task=main['task'],body_range=window,as_of_commit=old)


    def test_P01_07_range_delivery_respects_actual_frozen_input_budget(self):
        from research_studio import input_delivery
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);main,worker=h.running_pair(communication=True)
            state=h.store.read_snapshot();target=state['instances'][h.iid]['target_ref']
            tools=TaskTools(h.store,main['spec'].request_id,main['spec'].execution_id)
            contract=main['task']['communication_contract'];successful=0;limited=False
            # Exercise the real frozen allowance; do not mutate task/reader state.
            for n in range(contract['max_tool_calls']+1):
                frame=h.command('COMMUNICATION_APPLIED',{'native_event':{}})
                args={k:frame[k] for k in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
                with h.control.native_context(h.service,**args,grant_ref=h.grant(),manifest_ref=main['manifest_ref']):
                    did,response=tools.call('knowledge_get',{'ref':target,'body_range':dict(start=0,end=5,unit='UTF8_BYTE')})
                payload=json.loads(response['content'][0]['text'])
                if response['isError']:
                    error=payload.get('error',payload.get('result',{}).get('error'))
                    self.assertIn(error,{'DYNAMIC_INPUT_LIMIT','DYNAMIC_TRAJECTORY_LIMIT'})
                    self.assertNotIn('body',payload.get('result',payload));limited=True;break
                successful+=1
                self.assertEqual(payload['result']['read_scope'],'PARTIAL_BODY_RANGE')
            self.assertGreater(successful,0);self.assertTrue(limited)
            rows=input_delivery.manifest(h.store.read_snapshot(),main['spec'].request_id)
            self.assertLessEqual(sum(d['bytes'] for d in rows),contract['max_dynamic_input_tokens'])
            self.assertLessEqual(sum(d['trajectory_bytes'] for d in rows),contract['tool_trajectory_reserve_tokens'])
            self.assertTrue(all(d['supplements']==[] for d in rows))



    def test_source18_P01_07_public_frozen_partial_packet_cannot_deliver_full_body(self):
        from pathlib import Path
        from pmrh.domain.primitives import sha
        from research_studio import changes,demo,execution,input_delivery,knowledge,tasks
        from research_studio.engine import Engine
        from research_studio.store import Store
        from tests.devpr05.fixtures import scientific_policy
        with tempfile.TemporaryDirectory() as tmp:
            engine=Engine();store=engine.create(Path(tmp)/'native',demo.ARITHMETIC,synthetic=True)
            target=next(iter(store.read_snapshot()['records']))
            iid=engine.new_workflow(store,'TRH',target_ref=target)['instance_id']
            piece=b'Exact selected passage.';tail=b' Unprovided source18 appendix sentinel.';raw=piece+tail
            source=store.commit(changes.prepare_material_input(store.read_snapshot(),raw,'Bounded synthetic supplement','text/plain',blob_get=store.read_blob))['source_ref']
            policy=scientific_policy();policy['communication']={}
            engine.start_round(store,iid,'Read only the exact selected supplemental passage.',source_refs=[source],
                max_calls=2,max_workers=1,max_research_attempts=1,allow_reports=False,policy=policy)
            before=store.read_snapshot();definition=next(iter(before['obligations'].values()))['definition']
            binding=definition['consumer_bindings'][0]['binding_id']
            selection={source:dict(coverage='DECLARED_RANGE',locators=[knowledge.locator(raw,0,len(piece))],reason='This bounded duty uses only the declared passage.')}
            execution.replan_unsent_materials(store,iid,binding,selection,'Freeze the exact authorized passage before request preparation.')
            prepared=engine.prepare(store,iid)['prepared'];self.assertEqual(len(prepared),1)
            task=tasks.load(store,prepared[0]['task_id']);frozen=deepcopy(task)
            material=next(row for row in task['input_manifest'] if row.get('ref')==source)
            self.assertTrue(material['body_coverage']);self.assertEqual(material['body_coverage']['coverage'],'DECLARED_RANGE')
            self.assertNotIn(sha(raw),task['material_refs']);self.assertIn(sha(piece),task['material_refs'])
            self.assertEqual(store.read_blob(task['material_refs'][sha(piece)]['sha256']),piece)
            self.assertEqual(store.read_snapshot()['budget_grants'],before['budget_grants'])
            reserved=execution.reserve(store,task['request_id'],execution_kind='SYNTHETIC_TEST_ONLY')
            store.commit_execution(execution.event('SENT',dict(request_id=task['request_id'],execution_id=reserved['execution_id'])))
            tools=TaskTools(store,task['request_id'],reserved['execution_id']);deliveries=[]
            for args in ({'ref':source},{'ref':source,'body_range':dict(start=0,end=len(piece),unit='UTF8_BYTE')}):
                did,response=tools.call('knowledge_get',args);deliveries.append(did)
                self.assertTrue(response['isError'],response)
                result=json.loads(response['content'][0]['text'])['result'];self.assertEqual(result['error'],'KNOWLEDGE_SCOPE_LIMIT')
                self.assertNotIn('body',result);self.assertNotIn(tail.decode(),canonical(response).decode())
                row=store.read_snapshot()['input_deliveries'][did];self.assertEqual(row['supplements'],[])
                input_delivery.confirm(store,task['request_id'],reserved['execution_id'],did)
            did,response=tools.call('knowledge_search',{'query':'source18 appendix sentinel'});deliveries.append(did)
            self.assertFalse(response['isError'],response);page=json.loads(response['content'][0]['text'])['result']
            self.assertEqual(page['results'],[]);self.assertIn(source,page['categories']['partial_material_excluded'])
            self.assertNotIn(source,{row['ref'] for row in page['scanned_ranges_this_call']})
            # Trusted human project access is independent upstream authority;
            # it does not widen this task's persisted partial packet.
            human=Q.web_tool(Store(store.root),'get',{'ref':[source],'instance_id':[iid]})
            self.assertEqual(human['body'].encode(),raw)
            did,response=tools.call('knowledge_get',{'ref':target});self.assertFalse(response['isError'],response)
            self.assertTrue(json.loads(response['content'][0]['text'])['result']['body'])
            input_delivery.seal(store,task['request_id'],reserved['execution_id'])
            reopened=Store(store.root).read_snapshot()
            self.assertEqual(reopened['tasks'][task['task_id']],frozen)
            self.assertTrue(reopened['input_windows'][task['request_id']]['sealed'])
            self.assertTrue(all(reopened['input_deliveries'][did]['supplements']==[] for did in deliveries))
            self.assertEqual(reopened['tasks'][task['task_id']]['source_excerpts'][source],task['source_excerpts'][source])


    def test_source16_P01_08_checkpoint_loss_range_and_current_grant(self):
        from research_studio.store import Store
        from pmrh.domain.primitives import sha
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);main,worker=h.running_pair(communication=True);state=h.reopen()
            target=state['instances'][h.iid]['target_ref'];raw=h.store.read_blob(state['records'][target]['body_sha256'])
            pinned=state['knowledge_commit'];window=dict(start=0,end=5,unit='UTF8_BYTE')
            for path in (h.store.root/'checkpoints').glob('*.json'):path.unlink()
            human=Q.web_tool(Store(h.store.root),'get',{'ref':[target],'instance_id':[h.iid],
                'as_of_commit':[pinned],'body_range':[json.dumps(window)]})
            self.assertEqual(human['body'].encode(),raw[:5]);self.assertEqual(human['verified_full_body_sha256'],sha(raw))
            def read_range():
                command=h.command('COMMUNICATION_APPLIED',{})
                frame={k:command[k] for k in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
                with h.control.native_context(h.service,**frame,grant_ref=h.grant(),manifest_ref=main['manifest_ref']):
                    return TaskTools(h.store,main['spec'].request_id,main['spec'].execution_id).call('knowledge_get',
                        {'ref':target,'body_range':window,'as_of_commit':pinned})
            did,response=read_range();self.assertFalse(response['isError'],response)
            value=json.loads(response['content'][0]['text'])['result']
            self.assertEqual(value['body'],human['body']);self.assertEqual(value['read_scope'],'PARTIAL_BODY_RANGE')
            self.assertEqual(h.store.read_snapshot()['input_deliveries'][did]['supplements'],[])
            reason=h.blob('source16-range-revoke',b'Explicit synthetic revocation',raw=True)
            h.control.apply(h.command('GRANT_REVOKED',dict(budget_grant_id='BUDGET-synthetic',expected_revision=1,reason_ref=reason)),h.operator,grant_ref=h.grant())
            with self.assertRaises(PMRSError):Q.get(Store(h.store.root),target,task=main['task'],body_range=window,as_of_commit=pinned)
            revoked=h.store.read_snapshot();head=h.store._head()
            with self.assertRaises(PMRSError) as denied:read_range()
            self.assertEqual(denied.exception.code,'CONTROL_INVALID')
            self.assertEqual(h.store._head(),head)
            self.assertEqual(h.store.read_snapshot()['input_deliveries'],revoked['input_deliveries'])
            self.assertEqual(h.store.read_blob(state['records'][target]['body_sha256']),raw)


    def test_source16_FM16_isolated_review_has_no_fast_title_count_or_body(self):
        from .fixtures import native_qualified_pair,scientific_worker
        from .test_domain import rehash
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);seed=native_qualified_pair(h);main=seed['main']
            worker=scientific_worker(h,main,'source16-fast-author')
            state=h.reopen();module=six_entries(state,worker['task'])[0]
            module['body']['payload']['title']='source16 hidden fast title'
            module['body']['body']='source16 hidden fast body';rehash(module)
            _,capture,_=h.capture_fast(worker,delta_for(state,worker['task'],[module]))
            h.apply_fast(capture['proposal_ref'],main)
            human=Q.web_tool(h.store,'get',{'ref':[module['ref']],'instance_id':[h.iid]})
            self.assertEqual(human['payload']['title'],'source16 hidden fast title')
            self.assertEqual(human['body'],'source16 hidden fast body')
            review=scientific_worker(h,main,'source16-isolated-reader',role='PROOF',
                inputs=[seed['target'],seed['paths'][0]['argument_ref']])
            self.assertEqual(review['task']['communication_contract']['mode'],'REVIEW_ISOLATED')
            tools=TaskTools(h.store,review['spec'].request_id,review['spec'].execution_id)
            def call(name,arguments):
                command=h.command('COMMUNICATION_APPLIED',{})
                frame={k:command[k] for k in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
                with h.control.native_context(h.service,**frame,grant_ref=h.grant(),manifest_ref=review['manifest_ref']):
                    did,response=tools.call(name,arguments)
                row=h.store.read_snapshot()['input_deliveries'][did]
                self.assertEqual(h.store.read_blob(row['response_ref']),canonical(response));self.assertEqual(row['supplements'],[])
                return response,json.loads(response['content'][0]['text'])['result']
            response,page=call('knowledge_search',{'query':'','kind':'KnowledgeModule'})
            self.assertFalse(response['isError'],response);self.assertEqual(page['results'],[])
            self.assertEqual(page['scanned_ranges_this_call'],[]);self.assertEqual(page['next_position'],0)
            self.assertEqual(page['not_scanned_by_this_call'],dict(before=[0,0],after=[0,0]))
            self.assertEqual(page['body_bytes_read_this_call'],0)
            for hidden in ('source16 hidden fast title','source16 hidden fast body',module['ref']):
                self.assertNotIn(hidden,canonical(response).decode())
            response,denied=call('knowledge_get',{'ref':module['ref']})
            self.assertTrue(response['isError']);self.assertEqual(denied['error'],'KNOWLEDGE_FORBIDDEN')
            self.assertNotIn('body',denied)
            self.assertIn(seed['target'],Q.allowed_refs(h.store.read_snapshot(),review['task']))

    def test_source07_native_TaskTools_scope_and_closed_window_pairs(self):
        from .fixtures import native_running_main
        from research_studio import input_delivery
        from research_studio.store import Store
        with tempfile.TemporaryDirectory() as tmp:
            engine,store,iid,task,eid=native_running_main(tmp)
            state=Store(store.root).read_snapshot();target=state['instances'][iid]['target_ref']
            grant=state['budget_grants'][state['requests'][task['request_id']]['budget_grant_id']]
            self.assertNotIn('grant_status',grant)
            self.assertTrue(all(e['schema']=='pmrs.commit/4.2.2' for _,e in store.history()))
            tools=TaskTools(Store(store.root),task['request_id'],eid)
            did,response=tools.call('knowledge_get',{'ref':target})
            self.assertFalse(response['isError'],response)
            result=json.loads(response['content'][0]['text'])['result']
            self.assertEqual(result['ref'],target);self.assertEqual(result['read_scope'],'EXACT_BODY')
            state=Store(store.root).read_snapshot()
            self.assertEqual(store.read_blob(state['input_deliveries'][did]['response_ref']),canonical(response))
            self.assertEqual(Q.web_tool(Store(store.root),'get',{'ref':[target],'instance_id':[iid]})['body'],result['body'])
            for field in ('instance_id','mission_id','budget_grant','request_id'):
                forged=deepcopy(task);forged[field]='foreign'
                with self.subTest(field=field),self.assertRaises(PMRSError):Q.get(Store(store.root),target,task=forged)
            for extra in ({'instance_id':None},{'instance_id':'foreign'},{'mission_id':'foreign'}):
                _,denied=tools.call('knowledge_get',dict(ref=target,**extra))
                self.assertTrue(denied['isError']);self.assertNotIn('body',json.loads(denied['content'][0]['text']).get('result',{}))
            first=Q.search(Store(store.root),'',task=task,limit=1)
            input_delivery.seal(store,task['request_id'],eid)
            with self.assertRaises(PMRSError):Q.get(Store(store.root),target,task=task)
            with self.assertRaises(PMRSError):Q.search(Store(store.root),'',task=task,continuation=first['continuation'])

    def test_source07_native_pause_fence_and_superseded_grant_pairs(self):
        from .fixtures import native_running_main
        from research_studio import workflow_instances as W
        from research_studio.store import Store
        for boundary in ('PAUSE','CANCEL_REQUEST','SUPERSEDE_MISSION'):
            with self.subTest(boundary=boundary),tempfile.TemporaryDirectory() as tmp:
                engine,store,iid,task,eid=native_running_main(tmp)
                state=store.read_snapshot();target=state['instances'][iid]['target_ref']
                self.assertEqual(Q.get(Store(store.root),target,task=task)['ref'],target)
                first=Q.search(Store(store.root),'',task=task,limit=1)
                if boundary=='PAUSE':engine.pause(store,iid,'Synthetic read permission boundary.')
                elif boundary=='CANCEL_REQUEST':
                    store.commit_control(W.event(state,'CANCEL_REQUEST',dict(request_id=task['request_id'],reason='Synthetic exact request fence.'),instance_id=iid))
                else:
                    engine.authorize(store,iid,dict(intent='Separate synthetic mission; no old request authority.',
                        authorized_scope={'target_refs':[target]},obligations=[]),dict(max_calls=1,max_workers=1,execution_policy=engine.policy(store,iid)))
                    current=store.read_snapshot();mid=current['instances'][iid]['current_mission_id']
                    self.assertNotEqual(current['missions'][mid]['budget_grant_id'],state['requests'][task['request_id']]['budget_grant_id'])
                head=store._head()
                with self.assertRaises(PMRSError):Q.get(Store(store.root),target,task=task,as_of_commit=first['as_of_commit'])
                with self.assertRaises(PMRSError):Q.search(Store(store.root),'',task=task,continuation=first['continuation'])
                self.assertEqual(store._head(),head)
                # TaskTools itself also enforces the current input window. A
                # denied transport may refuse persistence rather than emit data.
                tools=TaskTools(Store(store.root),task['request_id'],eid)
                try:_,response=tools.call('knowledge_get',{'ref':target})
                except PMRSError as exc:self.assertIn(exc.code,{'TASK_FENCED','INPUT_WINDOW_SEALED'})
                else:
                    self.assertTrue(response['isError'])
                    self.assertNotIn('body',json.loads(response['content'][0]['text']).get('result',{}))

    def test_source07_control_profiles_ACTIVE_then_revoked_continuation(self):
        from tests.devpr06.test_control import Harness as ControlHarness
        from research_studio.store import Store
        for fixture,schema in ((ControlHarness,'pmrh.commit/2'),(Harness,'pmrh.control-fast.commit/1')):
            with self.subTest(schema=schema),tempfile.TemporaryDirectory() as tmp:
                h=fixture(tmp);h.authorize(3,communication=True)
                main=h.prepare();h.send(main);h.dispatch(main,'SENT');task=main['task']
                state=h.store.read_snapshot();target=state['instances'][h.iid]['target_ref']
                self.assertEqual(h.store.history()[-1][1]['schema'],schema)
                self.assertEqual(state['budget_grants']['BUDGET-synthetic']['grant_status'],'ACTIVE')
                self.assertEqual(Q.get(Store(h.store.root),target,task=task)['ref'],target)
                first=Q.search(Store(h.store.root),'',task=task,limit=1)
                reason=h.blob('source07-revoke',b'Synthetic explicit revocation',raw=True)
                h.control.apply(h.command('GRANT_REVOKED',dict(budget_grant_id='BUDGET-synthetic',expected_revision=1,reason_ref=reason)),h.operator,grant_ref=h.grant())
                with self.assertRaises(PMRSError):Q.get(Store(h.store.root),target,task=task,as_of_commit=first['as_of_commit'])
                with self.assertRaises(PMRSError):Q.search(Store(h.store.root),'',task=task,continuation=first['continuation'])

    def test_source07_native_report_only_paused_read_then_abandon(self):
        from pathlib import Path
        from tests.devpr05.fixtures import scientific_policy
        from research_studio import reports,demo,execution,changes
        from research_studio.engine import Engine
        from research_studio.store import Store
        with tempfile.TemporaryDirectory() as tmp:
            engine=Engine();store=engine.create(Path(tmp)/'native',demo.ARITHMETIC,synthetic=True)
            target=next(iter(store.read_snapshot()['records']));iid=engine.new_workflow(store,'TRH',target_ref=target)['instance_id']
            policy=scientific_policy();policy['communication']={}
            engine.authorize(store,iid,dict(intent='Synthetic manuscript authorization.',authorized_scope={'target_refs':[target],'reports':True,'allow_derived_work':True},obligations=[]),
                dict(max_calls=4,max_workers=2,execution_policy=policy))
            rid=reports.create(store,iid)
            def prepare_role():
                ready=reports.advance(store,iid,rid);self.assertEqual(ready['state'],'REPORT_TASK_READY')
                made=engine.prepare(store,iid,{**policy,'only_obligation_ids':[ready['obligation_id']]})['prepared']
                self.assertEqual(len(made),1);task=store.read_snapshot()['tasks'][made[0]['task_id']]
                self.assertEqual(task['role'],'REPORT_AUTHOR')
                reserve=execution.reserve(store,task['request_id'],execution_kind='SYNTHETIC_TEST_ONLY')
                store.commit_execution(execution.event('SENT',dict(request_id=task['request_id'],execution_id=reserve['execution_id'])))
                return task,reserve['execution_id']
            task,eid=prepare_role();raw=demo.response(task,store.read_snapshot(),blob_get=store.read_blob)
            execution.capture(store,task['request_id'],raw,execution_id=eid)
            store.commit(changes.validate_response(task,store.read_snapshot(),raw,'live',store.read_blob))
            self.assertEqual(store.read_snapshot()['requests'][task['request_id']]['acceptance_state'],'ACCEPTED')
            engine.pause(store,iid,'Research remains paused during explicit report-only revision.')
            old=reports.revision_target(store,iid,rid,'lecture')
            reports.revise_direct(store,iid,rid,'lecture',old['revision'],'Clarify the synthetic exposition without changing the scientific claim.',
                {'kind':'FULL'},3,operation_id='source07-report-revision',body_hash=old['body_hash'])
            task,eid=prepare_role();state=Store(store.root).read_snapshot()
            self.assertEqual(state['instances'][iid]['status'],'PAUSED')
            self.assertTrue(reports.dispatch_authorized(state,task))
            self.assertEqual(reports.dispatch_budget(state,task),state['requests'][task['request_id']]['budget_grant_id'])
            self.assertEqual(Q.get(Store(store.root),target,task=task)['ref'],target)
            # Existing TaskTools transport still requires ACTIVE; knowledge read
            # compatibility does not change that report transport restriction.
            with self.assertRaises(PMRSError):M.bound_request(state,task['request_id'],eid)
            reports.abandon(store,iid,'Explicit synthetic report authorization withdrawal.',report_id=rid)
            with self.assertRaises(PMRSError):Q.get(Store(store.root),target,task=task)
