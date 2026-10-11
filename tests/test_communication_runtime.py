"""Real child-process MCP communication; only the model transport is synthetic."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json,os,sys,subprocess,unittest
from research_studio import communication as comm,input_delivery,task_tools,usage_ledger,execution,runner,demo,knowledge_access
from research_studio.util import canonical,PMRSError,sha
from tests.test_model_pool import fixture,prepare

TRANSPORT=r'''#!/usr/bin/env python3
import fcntl,json,os,pathlib,subprocess,sys,time
args=sys.argv;work=pathlib.Path(args[args.index('-C')+1]);task=json.loads((work/'task.json').read_text())
root=pathlib.Path(os.environ['PMRS_COMM_TRANSPORT']);config=json.loads((root/'config.json').read_text())
options={args[i+1].split('=',1)[0]:args[i+1].split('=',1)[1] for i,x in enumerate(args[:-1]) if x=='-c'}
command=[json.loads(options['mcp_servers.pmrs.command'])]+json.loads(options['mcp_servers.pmrs.args'])
server=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
counter=0
def rpc(method,params):
 global counter
 counter+=1;server.stdin.write((json.dumps({'jsonrpc':'2.0','id':counter,'method':method,'params':params})+'\n').encode());server.stdin.flush()
 raw=server.stdout.readline()
 if not raw:raise RuntimeError(server.stderr.read().decode())
 reply=json.loads(raw);assert reply['id']==counter
 return reply['result']
def tool(name,params):
 reply=rpc('tools/call',{'name':name,'arguments':params})
 return json.loads(reply['content'][0]['text'])
rpc('initialize',{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'controlled-worker','version':'1'}})
names=[x['name'] for x in rpc('tools/list',{})['tools']];assert 'research_messages_send' in names
print(json.dumps({'type':'thread.started','thread_id':'thread-'+task['request_id']}),flush=True)
print(json.dumps({'type':'turn.started','turn_id':'t1'}),flush=True)
with (root/'overlap.jsonl').open('a') as f:
 fcntl.flock(f,fcntl.LOCK_EX);f.write(json.dumps({'request_id':task['request_id'],'event':'started','time':time.monotonic()})+'\n');f.flush()
start=time.monotonic()
while len((root/'overlap.jsonl').read_text().splitlines())<2 and time.monotonic()-start<5:time.sleep(.02)
if task['request_id']==config['sender']:
 sent=tool('research_messages_send',{'to':config['recipient'],'body':'Candidate interface: the synthetic integration remainder must stay explicit.','kind':'INTERMEDIATE_RESULT','idempotency_key':'one-hint'})
 repeated=tool('research_messages_send',{'to':config['recipient'],'body':'Candidate interface: the synthetic integration remainder must stay explicit.','kind':'INTERMEDIATE_RESULT','idempotency_key':'one-hint'})
 assert sent['result']['message_id']==repeated['result']['message_id']
 time.sleep(.25)
else:
 rows=[]
 for i in range(4):
  rows=tool('research_messages_list',{})['result']['messages']
  if rows:break
  time.sleep(.05)
 assert rows
 message=tool('research_messages_read',{'message_id':rows[0]['message_id']})
 assert 'integration remainder' in message['result']['body']
 tool('research_messages_ack',{'message_id':rows[0]['message_id'],'disposition':'REJECTED','reason':'Synthetic hint was inspected; no mathematical claim is adopted.'})
 exact=tool('knowledge_get',{'ref':task['target_refs'][0]});assert exact['result']['body']
server.stdin.close();server.wait(timeout=5);assert server.returncode==0
pathlib.Path(args[args.index('-o')+1]).write_bytes((root/task['request_id']).read_bytes())
print(json.dumps({'type':'turn.completed','turn_id':'t1','usage':{'input_tokens':20,'output_tokens':5,'cached_input_tokens':3,'reasoning_output_tokens':2}}),flush=True)
with (root/'overlap.jsonl').open('a') as f:
 fcntl.flock(f,fcntl.LOCK_EX);f.write(json.dumps({'request_id':task['request_id'],'event':'finished','time':time.monotonic()})+'\n');f.flush()
'''


class CommunicationRuntime(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        env=patch.dict(os.environ,{'PMRS_HOST_POOL_ROOT':str(self.root/'host'),'PMRS_COMM_TRANSPORT':str(self.root/'transport')})
        env.start();self.addCleanup(env.stop)

    def prepared(self,count=2):
        store,iid,policy=fixture(self.root/'project',count,count);rows=prepare(store,iid,policy)
        return store,iid,rows

    def test_two_running_child_processes_use_mcp_before_capture_and_replay(self):
        store,iid,rows=self.prepared();ids=[r['request_id'] for r in rows]
        comm.bind_group(store,ids,'Synthetic common interface','Validate a legally cooperating transport pair.')
        root=self.root/'transport';root.mkdir();binary=root/'transport';binary.write_text(TRANSPORT);binary.chmod(0o700)
        (root/'config.json').write_text(json.dumps({'sender':ids[0],'recipient':ids[1]}))
        for task in store.read_snapshot()['tasks'].values():(root/task['request_id']).write_bytes(demo.response(task,store.read_snapshot()))
        with patch('research_studio.runner.doctor',return_value={'ready':True,'binary':str(binary)}),ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(runner.CodexExecutor(str(binary),timeout=15).execute,store,r['task_id']) for r in rows]
            results=[f.result() for f in futures]
        self.assertEqual([r['state'] for r in results],['ACCEPTED','ACCEPTED'])
        s=store.read_snapshot();self.assertEqual(len(s['research_messages']),1)
        self.assertTrue(any(a['disposition']=='REJECTED' for a in s['message_acks'].values()))
        for rid in ids:
            self.assertEqual(s['requests'][rid]['execution_state'],'SETTLED')
            self.assertEqual(s['requests'][rid]['delivery_manifest_hash'],input_delivery.capture_binding(s,rid)['delivery_manifest_hash'])
            self.assertEqual(s['requests'][rid]['usage']['input_tokens'],20)
        self.assertFalse(comm.independence_status(s,rows[1]['task_id'])['independent'])
        times=[json.loads(x) for x in (root/'overlap.jsonl').read_text().splitlines()]
        self.assertLess(max(x['time'] for x in times if x['event']=='started'),min(x['time'] for x in times if x['event']=='finished'))
        self.assertEqual(usage_ledger.summary(s)['model_calls'],0)
        self.assertEqual(usage_ledger.summary(s)['synthetic_requests'],2)
        # Full native replay, not merely a warmed SQL projection.
        audit=store.audit();self.assertTrue(audit)

    def test_prepared_delivery_seal_late_confirmation_withdrawal_and_capacity(self):
        store,iid,rows=self.prepared();ids=[r['request_id'] for r in rows]
        comm.bind_group(store,ids,'Bounded pair','Track possible exposure and withdrawals.')
        for rid in ids:execution.reserve(store,rid,execution_kind='SYNTHETIC_TEST_ONLY')
        s=store.read_snapshot();a,b=[s['requests'][r]['execution_id'] for r in ids]
        mid=comm.send(store,ids[0],a,to=ids[1],body='A tentative bounded candidate.',idempotency_key='candidate')['message_id']
        result=comm.read_message(store,ids[1],b,mid)
        did,response=input_delivery.prepare(store,ids[1],b,'research_messages_read',result,message_ids=[mid])
        binding=input_delivery.seal(store,ids[1],b)
        comm.withdraw(store,ids[0],a,mid,'The candidate has an unproved step.')
        input_delivery.confirm(store,ids[1],b,did)
        self.assertEqual(binding,input_delivery.capture_binding(store.read_snapshot(),ids[1]))
        self.assertTrue(store.read_snapshot()['communication_impacts'])
        with self.assertRaisesRegex(PMRSError,'WITHDRAWN_MESSAGE_UNRESOLVED'):
            s=store.read_snapshot();comm.validate_dispositions(s,s['tasks'][rows[1]['task_id']],[],resolved_refs=set())
        with self.assertRaisesRegex(PMRSError,'INPUT_WINDOW_SEALED'):
            input_delivery.prepare(store,ids[1],b,'knowledge_get',{})

    def test_only_sealed_exact_tool_bodies_supply_dynamic_scientific_refs(self):
        store,iid,rows=self.prepared(1);row=rows[0];rid=row['request_id']
        execution.reserve(store,rid,execution_kind='SYNTHETIC_TEST_ONLY');s=store.read_snapshot()
        task=s['tasks'][row['task_id']];eid=s['requests'][rid]['execution_id'];ref=task['target_refs'][0]
        navigation=knowledge_access.search(store,task=task)
        input_delivery.prepare(store,rid,eid,'knowledge_search',navigation)
        self.assertEqual(input_delivery.supplied_records(store.read_snapshot(),task,store.read_blob),set())
        full=knowledge_access.get(store,ref,task=task)
        did,_=input_delivery.prepare(store,rid,eid,'knowledge_get',full)
        with self.assertRaisesRegex(PMRSError,'INPUT_WINDOW_UNSEALED'):
            input_delivery.supplied_records(store.read_snapshot(),task,store.read_blob)
        input_delivery.confirm(store,rid,eid,did);input_delivery.seal(store,rid,eid)
        sealed=store.read_snapshot()
        self.assertEqual(input_delivery.supplied_records(sealed,task,store.read_blob),{ref})
        changed=deepcopy(sealed);changed['records'][ref]['test_metadata_change']=True
        with self.assertRaisesRegex(PMRSError,'STALE_DYNAMIC_INPUT'):
            input_delivery.supplied_records(changed,task,store.read_blob)
        changed=deepcopy(sealed);changed['input_windows'][rid]['input_window_seal']='forged'
        with self.assertRaisesRegex(PMRSError,'ORIGINAL_BYTES_MISMATCH'):
            input_delivery.capture_binding(changed,rid)

    def test_knowledge_isolation_precedes_summary_and_partial_scope_never_expands(self):
        store,iid,rows=self.prepared(1);s=store.read_snapshot();task=deepcopy(s['tasks'][rows[0]['task_id']]);ref=task['target_refs'][0]
        task['communication_contract']['mode']='REVIEW_ISOLATED'
        s['supports']['prior-verdict']={'statement_ref':ref,'result':'QUALIFIED','private_conclusion':'Prior reviewer approved this proof.'}
        self.assertEqual(knowledge_access._record_status(s,ref,task)['support'],[])
        for entry in task['input_manifest']:
            if entry.get('ref')==ref:entry['body_coverage']={'state':'PARTIAL_TARGET_BODY','locators':[]}
        with self.assertRaisesRegex(PMRSError,'KNOWLEDGE_SCOPE_LIMIT'):knowledge_access.get(store,ref,task=task)
        result=knowledge_access.search(store,task=task)
        self.assertEqual(next(row for row in result['results'] if row['ref']==ref)['excerpt'],'')

    def test_initial_reading_reserve_depends_on_actual_reachable_work_and_charges_calls(self):
        store,iid,rows=self.prepared(1);snapshot=store.read_snapshot();task=snapshot['tasks'][rows[0]['task_id']]
        consumer={'instance_id':iid,'mission_id':task['mission_id'],'stage_id':'P1','role':'PLAN'}
        empty=deepcopy(snapshot);empty['tasks']={};empty['requests']={}
        contract=comm.frozen_contract(empty,consumer,initial_material_complete=True)
        self.assertEqual((contract['profile'],contract['max_dynamic_input_tokens'],contract['tool_trajectory_reserve_tokens']),
                         ('INITIAL_MATERIAL_READING',2048,1024))
        self.assertNotIn('profile',comm.frozen_contract(snapshot,consumer,initial_material_complete=True))
        self.assertNotIn('profile',comm.frozen_contract(empty,consumer,initial_material_complete=False))
        self.assertNotIn('profile',comm.frozen_contract(empty,{**consumer,'communication_group':'group'},initial_material_complete=True))
        empty['tasks']={'prior-main':{**consumer,'task_id':'prior-main','actor_kind':'MAIN','request_id':'prior-main'}}
        empty['requests']={'prior-main':{'execution_state':'SETTLED'}}
        self.assertNotIn('profile',comm.frozen_contract(empty,consumer,initial_material_complete=True))
        rid=task['request_id'];execution.reserve(store,rid,execution_kind='SYNTHETIC_TEST_ONLY')
        service=task_tools.TaskTools(store,rid,snapshot['requests'][rid]['execution_id'])
        before=store.read_snapshot()
        with self.assertRaisesRegex(PMRSError,'DYNAMIC_TRAJECTORY_LIMIT'):
            service.call('research_messages_send',{'to':'main','body':'x'*4096,'idempotency_key':'too-large'})
        self.assertEqual(store.read_snapshot().get('research_messages',{}),before.get('research_messages',{}))

    def test_independent_modes_reject_main_paraphrase_and_hide_before_summary(self):
        store,iid,rows=self.prepared();s=store.read_snapshot();ids=[r['request_id'] for r in rows]
        # Pure policy matrix does not manufacture executed scientific requests.
        for rid in ids:s['requests'][rid]['execution_state']='SENT'
        main=s['tasks'][rows[0]['task_id']];other=s['tasks'][rows[1]['task_id']];main['actor_kind']='MAIN'
        for mode in ('INDEPENDENT_EXPLORE','REVIEW_ISOLATED'):
            other['communication_contract']['mode']=mode
            body=b'Another branch found the intended conclusion.';body_ref=store.put_blob(body)
            row={'schema':comm.SCHEMA,'message_id':'MESSAGE-test','sender_request_id':ids[0],
                 'sender_execution_id':s['requests'][ids[0]]['execution_id'],'sender_task_id':main['task_id'],
                 'instance_id':iid,'mission_id':main['mission_id'],'recipient':comm._recipient(s,main,ids[1]),
                 'kind':'LEAD','body_ref':body_ref,'record_refs':[],'reply_to':None,'host_sanitized':False,
                 'exposure_domains':comm.exposure_domains(s,ids[0])}
            with self.assertRaisesRegex(PMRSError,'COMMUNICATION_FORBIDDEN'):
                comm.apply_event(s,comm.event('MESSAGE_PUBLISHED',row),store.read_blob)
            with self.assertRaisesRegex(PMRSError,'COMMUNICATION_FORBIDDEN'):
                comm.apply_event(s,comm.event('COLLAB_GROUP_BOUND',{'group_id':'bad','request_ids':ids,'topic':'Bad','reason':'Not authorized to turn independent work into cooperation.'}),store.read_blob)

    def test_main_original_inflight_cross_mission_status_preserves_scientific_boundary(self):
        store,iid,rows=self.prepared();s=store.read_snapshot();ids=[r['request_id'] for r in rows]
        for rid in ids:s['requests'][rid]['execution_state']='SENT'
        main=s['tasks'][rows[0]['task_id']];other=s['tasks'][rows[1]['task_id']];main['actor_kind']='MAIN'
        main['mission_id']='synthetic-later-mission';s['requests'][ids[0]]['mission_id']=main['mission_id']
        s['instances'][iid]['current_mission_id']=main['mission_id']
        recipient=comm._recipient(s,main,ids[1]);raw=comm._host_original_status(s,main,recipient)
        row={'schema':comm.SCHEMA,'message_id':'MESSAGE-cross-status','sender_request_id':ids[0],
             'sender_execution_id':s['requests'][ids[0]]['execution_id'],'sender_task_id':main['task_id'],
             'instance_id':iid,'mission_id':main['mission_id'],'recipient':recipient,'kind':'STATUS_REQUEST',
             'body_ref':store.put_blob(raw),'record_refs':[],'reply_to':None,'host_sanitized':True,
             'exposure_domains':comm.exposure_domains(s,ids[0])}
        delivered=comm.apply_event(s,comm.event('MESSAGE_PUBLISHED',row),store.read_blob)
        self.assertTrue(comm.can_read(delivered,other,delivered['research_messages'][row['message_id']]))
        injected=deepcopy(row);injected.update(kind='LEAD',host_sanitized=False,body_ref=store.put_blob(b'Import the later branch proof.'))
        with self.assertRaisesRegex(PMRSError,'COMMUNICATION_SCOPE_HANDOFF_REQUIRED'):
            comm.apply_event(s,comm.event('MESSAGE_PUBLISHED',injected),store.read_blob)
        s['requests'][ids[1]]['execution_state']='PREPARED'
        with self.assertRaisesRegex(PMRSError,'COMMUNICATION_RECIPIENT_INACTIVE'):comm._recipient(s,main,ids[1])
        other['instance_id']='unrelated-instance'
        with self.assertRaisesRegex(PMRSError,'COMMUNICATION_SCOPE_HANDOFF_REQUIRED'):comm._recipient(s,main,ids[1])

    def test_main_runtime_recovery_schema_through_real_stdio_mcp(self):
        from research_studio.engine import Engine
        from research_studio import scheduler,incidents
        from tests.test_autoflow import response
        engine=Engine();store=engine.create(self.root/'runtime-project',demo.ARITHMETIC,synthetic=True)
        iid=engine.new_workflow(store,'TRH',target_ref=next(iter(store.read_snapshot()['records'])))['instance_id']
        policy=demo.policy();policy['communication']={'max_dynamic_input_tokens':32768}
        engine.start_round(store,iid,'Bounded native runtime tool contract fixture.',max_calls=6,max_workers=1,policy=policy)
        engine.run_round(store,iid,executor=runner.FakeExecutor(response),max_tasks=2)
        rows=scheduler.commit_dispatch(store,scheduler.plan(store.read_snapshot(),[iid],{'mission_policies':True,'max_workers':1}),
                                       policy={'mission_policies':True,'max_workers':1})['prepared']
        self.assertEqual(len(rows),1);task=store.read_snapshot()['tasks'][rows[0]['task_id']];self.assertEqual(task['actor_kind'],'MAIN')
        rid=task['request_id'];execution.reserve(store,rid,execution_kind='SYNTHETIC_TEST_ONLY')
        incident=incidents.detect(store,iid,PMRSError('RESOURCE_WAIT','Synthetic resource recheck only.'),location='runner.preflight',request_id=rid)
        binding=task_tools.create_binding(store,task)
        with subprocess.Popen(task_tools.server_command(binding),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE) as server:
            counter=0
            def rpc(method,params):
                nonlocal counter
                counter+=1;server.stdin.write(canonical({'jsonrpc':'2.0','id':counter,'method':method,'params':params})+b'\n');server.stdin.flush()
                reply=json.loads(server.stdout.readline());self.assertEqual(reply['id'],counter);return reply['result']
            def call(name,args):return json.loads(rpc('tools/call',{'name':name,'arguments':args})['content'][0]['text'])['result']
            rpc('initialize',{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'runtime-fixture','version':'1'}})
            definitions=rpc('tools/list',{})['tools'];schema=next(x['inputSchema'] for x in definitions if x['name']=='runtime_propose_recovery')
            self.assertEqual(schema['properties']['expected_revision']['type'],'integer');self.assertIn('option',schema['required'])
            inspected=call('runtime_inspect_incident',{});self.assertEqual(inspected['incidents'][0]['incident_id'],incident['incident_id'])
            options=call('runtime_list_recovery_options',{'incident_id':incident['incident_id']})
            proposed=call('runtime_propose_recovery',{'incident_id':incident['incident_id'],'option':'CHECK_RESOURCE',
                           'expected_revision':options['expected_revision'],'idempotency_key':'runtime-check','arguments':{}})
            self.assertEqual(proposed['status'],'EXECUTED');self.assertEqual(proposed['result']['disposition'],'RECHECKED_WITHOUT_DISPATCH')
            server.stdin.close();server.wait(timeout=5);self.assertEqual(server.returncode,0)
        snapshot=store.read_snapshot();self.assertEqual(len(snapshot['recovery_proposals']),1)
        delivered=[d['tool_name'] for d in snapshot['input_deliveries'].values() if d['request_id']==rid]
        self.assertEqual(delivered,['runtime_inspect_incident','runtime_list_recovery_options','runtime_propose_recovery'])
        self.assertTrue(store.audit())

    def test_usage_cumulative_duplicate_unknown_and_distinct_turns(self):
        store,iid,rows=self.prepared(1);rid=rows[0]['request_id'];execution.reserve(store,rid,execution_kind='MODEL')
        eid=store.read_snapshot()['requests'][rid]['execution_id'];root=store.root/'runs'/rows[0]['task_id'];root.mkdir(parents=True)
        lines=[{'type':'thread.started','thread_id':'test-thread'},{'type':'turn.started','turn_id':'a'},
               {'type':'token_count','info':{'total_token_usage':{'input_tokens':10,'output_tokens':2}}},
               {'type':'turn.completed','turn_id':'a','usage':{'input_tokens':20,'output_tokens':3}},
               {'type':'turn.completed','turn_id':'a','usage':{'input_tokens':20,'output_tokens':3}},
               {'type':'turn.started','turn_id':'b'},{'type':'turn.completed','turn_id':'b','usage':{'input_tokens':5,'output_tokens':1}}]
        (root/'events.jsonl').write_bytes(b''.join(canonical(x)+b'\n' for x in lines))
        usage_ledger.ingest_log(store,rid,eid,final=True);before=store.read_snapshot()
        usage_ledger.ingest_log(store,rid,eid,final=True);s=store.read_snapshot()
        self.assertEqual(usage_ledger.request_usage(s,rid)['input_tokens'],25)
        self.assertEqual(usage_ledger.summary(s)['actual_started'],2)
        self.assertEqual(s['backend_usage'],before['backend_usage'])
        self.assertIsNone(usage_ledger.request_usage(s,rid)['reasoning_output_tokens'])
        self.assertEqual(usage_ledger.summary(s)['known_output_tokens'],4)
        with (root/'events.jsonl').open('ab') as stream:
            stream.write(canonical({'type':'turn.completed','turn_id':'b','usage':{'input_tokens':4,'output_tokens':1}})+b'\n')
        usage_ledger.ingest_log(store,rid,eid,final=True);conflict=store.read_snapshot()
        self.assertIsNone(usage_ledger.request_usage(conflict,rid)['input_tokens'])
        self.assertIsNone(usage_ledger.summary(conflict)['input_tokens'])

    def test_child_exiting_before_response_preserves_unknown_and_never_resends(self):
        store,iid,rows=self.prepared(1);row=rows[0]
        binary=self.root/'premature-exit';binary.write_text('#!/usr/bin/env python3\nimport os\nos.close(0)\nos._exit(7)\n');binary.chmod(0o700)
        executor=runner.CodexExecutor(str(binary),timeout=5)
        with patch('research_studio.runner.doctor',return_value={'ready':True,'binary':str(binary)}):
            with self.assertRaises((PMRSError,BrokenPipeError)):executor.execute(store,row['task_id'])
        snapshot=store.read_snapshot();request=snapshot['requests'][row['request_id']]
        self.assertEqual(request['execution_state'],'UNKNOWN');self.assertIsNone(request['capture_ref'])
        with patch('research_studio.runner.subprocess.Popen',side_effect=AssertionError('An uncertain original request cannot start a child again')):
            with self.assertRaisesRegex(PMRSError,'EXISTING_REQUEST'):executor.execute(store,row['task_id'])
        self.assertEqual(len(store.read_snapshot()['requests']),1)

    def test_coordinator_status_uses_lock_and_reads_create_nothing(self):
        store,iid,rows=self.prepared(1);path=store.root/'execution'/'coordinator.lock'
        self.assertFalse(runner.coordinator_status(store)['active']);self.assertFalse(path.exists())
        with runner.coordinator(store):
            self.assertTrue(runner.coordinator_status(store)['active'])
            with self.assertRaisesRegex(PMRSError,'COORDINATOR_BUSY'):
                with runner.coordinator(store):pass
        self.assertFalse(runner.coordinator_status(store)['active'])


if __name__=='__main__':unittest.main()
