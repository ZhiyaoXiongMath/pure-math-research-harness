"""Real disk admission of sealed original tasks, using existing kernel fixtures.

The fixture publishes explicit synthetic frozen tasks; it does not execute a
scheduler, Runner or model. All admission checks and disk publication are real.
"""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from research_studio import changes, contracts as C
from research_studio.util import canonical, loads, PMRSError, sha
from tests.test_final_kernel import Fixture, statement, argument
from . import fixtures as F


def mutate(store, edit):
    # Test-only fixture publication, not an application state-patch interface.
    with store._locked():
        before=store.read_snapshot(); after=deepcopy(before);edit(after)
        return store._publish(before['_head'],before,after,actor='SYNTHETIC_TEST_ONLY',events=[{'type':'TEST_FIXTURE'}])


def sealed(root, *, actor='WORKER', mode='PINNED', guard=None, with_records=False, reduction=False):
    store,iid,_,_,_=F.project(root,extended=False)
    if actor == 'MAIN':
        # One genuinely prepared synthetic MAIN capture, with explicit fixture
        # capability evidence. No Runner or external execution is invoked.
        from research_studio import tasks, execution, demo
        policy=F.scientific_policy()
        engine=F.Engine()
        engine.start_round(store,iid,'Inspect the exact synthetic target.',max_calls=3,policy=policy)
        made=engine.prepare(store,iid,policy=policy)
        task=tasks.load(store,made['prepared'][0]['task_id'])
        assert task['actor_kind']=='MAIN'
        reserved=execution.reserve(store,task['request_id'],execution_kind='SYNTHETIC_TEST_ONLY')
        envelope=loads(demo.response(task,store.read_snapshot(),blob_get=store.read_blob))
        payload=envelope['payload']; authored=payload.get('knowledge_change',payload)
        # The demo's historical ACCOUNT action is not in the current schema.
        # Author this synthetic candidate before capture; sealed bytes stay exact.
        authored['strategy_proposal']['next_action']='CONTINUE'
        raw=canonical(envelope)
        execution.capture(store,task['request_id'],raw,execution_id=reserved['execution_id'])
        proposal=changes.validate_response(task,store.read_snapshot(),raw,'live',store.read_blob)
        return store,iid,task,raw,proposal
    fixture=Fixture();fixture.s=store.read_snapshot()
    fixture.blobs={p.name:p.read_bytes() for p in (store.root/'blobs').iterdir()}
    target=next(iter(fixture.s['records']))
    task=fixture.task([target]);task.update(instance_id=iid,actor_kind=actor)
    task['read_set'][0]['selection_binding']['mode']=mode
    # Original packet/prompt files are required by the audit consumer.
    task['input_packet_ref']=store.put_blob(b'SYNTHETIC_TEST_ONLY frozen packet')
    task['prompt_ref']=store.put_blob(b'SYNTHETIC_TEST_ONLY frozen prompt')
    fixture.s['instances'][iid]['status']='ACTIVE'
    if guard=='write':
        task['write_guards']=[{'object_id':task['read_set'][0]['selection_binding']['object_id'],'expected_parent':target}]
    if guard=='query':
        members=[target]
        task['query_guards']=[{'query_kind':'TARGET_SET','scope_binding':{'instance_id':iid},
                               'member_refs':members,'member_digest':C.digest(members)}]
    if guard=='support':
        arg=fixture.add(argument(target,records=fixture.s['records']))
        fixture.s['supports']['SUP-fixture']={'support_id':'SUP-fixture','statement_ref':target,
            'argument_ref':arg,'qualification_refs':[],'open_assumption_refs':[]}
        task['read_set'][0]['required_support_refs']=['SUP-fixture']
    if guard=='obligation':
        fixture.s['obligations']['O']={'definition':{'obligation_id':'O','definition_revision':1,
            'type':'ESTABLISH','consumer_bindings':[],'criterion_body_ref':store.put_blob(b'Exact fixture duty')},
            'projection':{'work_state':'OPEN','resolution':'UNRESOLVED','attempt_refs':[],'evidence_refs':[]}}
        task['obligation_bindings']=[{'binding_id':'B','obligation_id':'O','expected_definition_revision':1}]
    fixture.s['tasks'][task['task_id']]=deepcopy(task)
    operations=[]
    if with_records:
        for n in range(2):
            _,record,body=statement('For every integer n, n + '+str(n+1)+' is an integer.')
            operations.append({'op':'NEW','local_key':'s'+str(n),'kind':'Statement','context_refs':[],
                               'body':body.decode(),'data':record['data']})
    if reduction:
        from research_studio.knowledge import locator
        body='This exact AND reduction preserves its declared conclusion.'
        loc=locator(body)
        duty={'status':'NOT_REQUIRED','reason_locator':loc,'evidence_refs':[]}
        inference={'premise_refs':[],'conclusion_ref':'local:s0','operator':'AND',
                   'alternative_argument_refs':[],'additional_assumption_refs':[],
                   'lifting_check':deepcopy(duty),'compatibility_check':deepcopy(duty)}
        operations[1]={'op':'NEW','local_key':'a','kind':'Argument','context_refs':[],'body':body,
            'data':{'conclusion_ref':'local:s0','premise_bindings':[],'steps':[],
                    'discharged_assumptions':[],'open_conditions':[],'witness_bindings':[],
                    'mode':'REDUCTION','mode_payload':{'inference_spec':inference}}}
    effects=[]
    if guard=='obligation':
        effects=[{'binding_id':'B','expected_definition_revision':1,'work_disposition':'NO_RESULT',
            'resolution_proposal':'UNRESOLVED','evidence_refs':[],'remaining_conditions':['An exact proof remains open.'],
            'blocker_proposals':[]}]
    raw=fixture.raw(task,operations,effects,outcome='RESULT' if operations else 'NO_RESULT')
    capture=store.put_blob(raw)
    fixture.s['requests'][task['request_id']]={'request_id':task['request_id'],'task_id':task['task_id'],
        'instance_id':iid,'execution_state':'CAPTURED','capture_ref':capture,'execution_kind':'SYNTHETIC_TEST_ONLY',
        'acceptance_state':'PENDING','fenced':False}
    for digest,data in fixture.blobs.items():store.put_blob(data)
    with store._locked():
        before=store.read_snapshot()
        store._publish(before['_head'],before,fixture.s,actor='SYNTHETIC_TEST_ONLY',events=[{'type':'TEST_FIXTURE'}])
    proposal=changes.validate_response(task,store.read_snapshot(),raw,'live',store.read_blob)
    return store,iid,task,raw,proposal


class Admission(unittest.TestCase):
    def test_unrelated_commit_same_original_and_durable_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            store,iid,task,raw,proposal=sealed(Path(tmp)/'p',with_records=True)
            frozen=canonical(task);base=task['knowledge_commit'];before=store.read_snapshot()
            store.commit(changes.prepare_source_input(before,b'Unrelated original source.',source_id='SO-unrelated',blob_get=store.read_blob))
            result=store.commit(proposal);state=store.read_snapshot()
            self.assertEqual(len(result['content_added']),2)
            self.assertEqual(state['requests'][task['request_id']]['acceptance_state'],'ACCEPTED')
            self.assertEqual(state['knowledge_changes'][-1]['base_knowledge_commit'],base)
            self.assertEqual(canonical(state['tasks'][task['task_id']]),frozen)
            self.assertEqual(store.read_blob(state['requests'][task['request_id']]['capture_ref']),raw)
            head=store._head();duplicate=F.Store(store.root).commit(proposal)
            self.assertEqual(duplicate['receipt_id'],result['receipt_id']);self.assertEqual(store._head(),head)
            self.assertTrue(store.audit()['valid'])

    def test_relevant_guards_reject_without_global_invalidation(self):
        for guard,code in [('current','STALE_READ'),('write','WRITE_CAS_CONFLICT'),('query','STALE_QUERY'),
                           ('obligation','STALE_OBLIGATION_DEFINITION'),('support','STALE_READ')]:
            with self.subTest(guard=guard),tempfile.TemporaryDirectory() as tmp:
                store,iid,task,raw,proposal=sealed(Path(tmp)/'p',mode='CURRENT' if guard=='current' else 'PINNED',guard=guard)
                oid=task['read_set'][0]['selection_binding']['object_id']
                def edit(state):
                    if guard in ('current','write'):state['objects'][oid]['selected_revision']='KR-'+'f'*64
                    elif guard=='query':state['instances'][iid]['target_ref']='KR-'+'f'*64
                    elif guard=='obligation':state['obligations']['O']['definition']['definition_revision']+=1
                    else:state['withdrawals']['W']={'support_id':'SUP-fixture','active':True}
                mutate(store,edit);before=store.read_snapshot()
                with self.assertRaisesRegex(PMRSError,code):store.commit(proposal)
                self.assertEqual(store.read_snapshot(),before)
                self.assertEqual(store.read_blob(sha(raw)),raw)
                self.assertEqual(store.read_snapshot()['records'],before['records'])

    def test_paused_sealed_worker_admitted_main_and_unsealed_rejected(self):
        # The same fixture must pass real admission while MAIN remains active.
        with tempfile.TemporaryDirectory() as tmp:
            store,iid,task,raw,proposal=sealed(Path(tmp)/'p',actor='MAIN')
            self.assertEqual(store.commit(proposal)['outcome'],'COMMITTED')
            self.assertEqual(store.read_blob(sha(raw)),raw)
        for actor in ('WORKER','MAIN'):
            with self.subTest(actor=actor),tempfile.TemporaryDirectory() as tmp:
                store,iid,task,raw,proposal=sealed(Path(tmp)/'p',actor=actor)
                F.Engine().pause(store,iid,'Keep the original sealed capture during pause.')
                if actor=='WORKER':self.assertEqual(store.commit(proposal)['outcome'],'COMMITTED')
                else:
                    head=store._head()
                    with self.assertRaisesRegex(PMRSError,'TASK_FENCED'):store.commit(proposal)
                    self.assertEqual(store._head(),head);self.assertEqual(store.read_blob(sha(raw)),raw)
        with tempfile.TemporaryDirectory() as tmp:
            store,iid,task,raw,proposal=sealed(Path(tmp)/'p')
            def unseal(state):
                state['instances'][iid]['status']='PAUSED';state['requests'][task['request_id']]['execution_state']='PREPARED'
            mutate(store,unseal)
            with self.assertRaisesRegex(PMRSError,'TASK_FENCED'):store.commit(proposal)

    def test_original_capture_and_record_tamper_reject(self):
        for target in ('capture','record'):
            with self.subTest(target=target),tempfile.TemporaryDirectory() as tmp:
                store,iid,task,raw,proposal=sealed(Path(tmp)/'p')
                before=store._head()
                path=(store.root/'blobs'/sha(raw) if target=='capture' else
                      store.root/'records'/(task['read_set'][0]['record_ref']+'.json'))
                path.write_bytes(b'Changed original')
                with self.assertRaises(PMRSError):store.commit(proposal)
                self.assertEqual(store._head(),before)

    def test_multi_record_and_receipt_faults_are_atomic(self):
        for point in ('after_blobs','after_records','after_commit','before_head','after_head'):
            with self.subTest(point=point),tempfile.TemporaryDirectory() as tmp:
                store,iid,task,raw,proposal=sealed(Path(tmp)/'p',with_records=True,guard='obligation')
                before=store.read_snapshot()
                def fail(where):
                    if point==where:raise RuntimeError(point)
                store._test_fault_hook=fail
                with self.assertRaises(RuntimeError):store.commit(proposal)
                reopened=F.Store(store.root);after=reopened.read_snapshot()
                if point=='after_head':
                    self.assertEqual(len(after['records']),len(before['records'])+2)
                    self.assertIn(task['request_id'],after['accepted_requests'])
                    self.assertNotEqual(after['obligations'],before['obligations'])
                    self.assertEqual(after['requests'][task['request_id']]['execution_state'],'SETTLED')
                else:self.assertEqual(after,before)
                self.assertEqual(reopened.read_blob(sha(raw)),raw)
                reopened.commit(proposal);head=reopened._head();reopened.commit(proposal)
                self.assertEqual(reopened._head(),head);self.assertTrue(reopened.audit()['valid'])

    def test_registry_forbids_external_callbacks_and_generic_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=F.Store.create(Path(tmp)/'p','Registry',synthetic=True)
            with self.assertRaises(PMRSError):store.commit({'records':{}})
            with self.assertRaises(PMRSError):store.commit_control({'event_type':'PATCH','payload':{}})
            with self.assertRaises(PMRSError):store._typed_commit({},lambda s,e:s,frozenset(),'Control')
            with self.assertRaises(PMRSError):store._typed_commit({},None,frozenset(),'unknown')
            # Real reducer with a malicious cross-collection result is rejected.
            from unittest.mock import patch
            from research_studio import workflow_instances
            def corrupt(s,e):s['records']={'forged':{}};return s
            from research_studio.store import CONTROL_MAPS
            from research_studio.research_audit import MAPS
            with patch.object(workflow_instances,'apply_control',corrupt):
                with self.assertRaisesRegex(PMRSError,'CAPABILITY_VIOLATION'):
                    store._typed_commit({},None,CONTROL_MAPS|MAPS,'Control')

    def test_real_disk_kr_and_inference_identities_are_not_file_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            store,iid,task,raw,proposal=sealed(Path(tmp)/'p',with_records=True,reduction=True)
            receipt=store.commit(proposal);state=store.read_snapshot()
            self.assertEqual(len(receipt['content_added']),2)
            argument_ref=next(ref for ref in receipt['content_added'] if state['records'][ref]['kind']=='Argument')
            inference_id=C.inference_identity(argument_ref)
            self.assertIn(inference_id,state['inferences'])
            self.assertEqual(state['inferences'][inference_id]['argument_ref'],argument_ref)
            record=store.read_record(argument_ref)
            file_bytes=(store.root/'records'/(argument_ref+'.json')).read_bytes()
            self.assertEqual(file_bytes,canonical(record))
            self.assertEqual(C.scientific_identity(record),argument_ref)
            self.assertNotEqual(argument_ref[3:],sha(file_bytes))
            self.assertNotEqual(inference_id[3:],sha(file_bytes))
            self.assertTrue(store.audit()['valid'])
