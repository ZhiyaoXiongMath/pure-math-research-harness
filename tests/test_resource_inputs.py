"""Bounded native input preparation; no model transport or host exhaustion."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
import os
from research_studio import changes, context, demo, execution, reports, resources, runner, scheduler, survey
from research_studio.store import Store
from research_studio.util import canonical, PMRSError, sha
from tests.test_survey import ready_survey


class ResourceInputs(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        env=patch.dict(os.environ,{'PMRS_HOST_POOL_ROOT':str(self.root/'host-pool')});env.start();self.addCleanup(env.stop)

    def material(self,store,raw,title='Synthetic material'):
        return store.commit(changes.prepare_material_input(store.read_snapshot(),raw,title,'text/plain',blob_get=store.read_blob))['source_ref']

    def test_oversize_native_input_is_rejected_before_any_body_read(self):
        store=Store.create(self.root/'p','Input budget',synthetic=True)
        source=self.material(store,b'x'*(1024*1024))
        calls=[]
        def get(digest):calls.append(digest);return store.read_blob(digest)
        with self.assertRaisesRegex(PMRSError,'CONTEXT_LIMIT'):
            context.build_packet(store.read_snapshot(),[],get,required_source_refs=[source],max_bytes=512*1024,
                                 blob_size=lambda h:resources.blob_info(store,h)['bytes'])
        self.assertEqual(calls,[])

    def test_duplicate_source_bytes_are_read_once_and_metadata_is_budgeted(self):
        store=Store.create(self.root/'p','Unique input',synthetic=True);raw=b'Shared exact source.\n'*100
        first=self.material(store,raw,'First occurrence');second=self.material(store,raw,'Second occurrence')
        calls=[]
        def get(digest):calls.append(digest);return store.read_blob(digest)
        packet=context.build_packet(store.read_snapshot(),[],get,required_source_refs=[first,second],
                                    blob_size=lambda h:resources.blob_info(store,h)['bytes'])
        self.assertEqual(calls,[sha(raw)]);self.assertEqual(len(packet['sources']),2)
        state=store.read_snapshot();state['sources'][first]['title']='x'*4096;calls.clear()
        with self.assertRaisesRegex(PMRSError,'CONTEXT_LIMIT'):
            context.build_packet(state,[],get,required_source_refs=[first],max_bytes=1024,
                                 blob_size=lambda h:resources.blob_info(store,h)['bytes'])
        self.assertFalse(calls)

    def test_serialization_preflight_counts_utf8_escapes_and_rejects_before_canonical(self):
        value={'quote':'"\\\n\x00汉字' * 100,'list':[1,None,False,1.25]}
        self.assertEqual(resources.json_bytes(value,65536),len(canonical(value)))
        with patch('research_studio.resources.canonical',side_effect=AssertionError('full serialization was attempted')):
            with self.assertRaisesRegex(PMRSError,'RESOURCE_LIMIT'):
                resources.bounded_canonical({'body':'x'*1000},100)

    def test_two_preparation_leases_wait_and_failure_releases_reservation(self):
        with resources.reserve(self.root,owner='one',temporary_bytes=1,memory_bytes=1):
            with resources.reserve(self.root,owner='two',temporary_bytes=1,memory_bytes=1):
                with self.assertRaisesRegex(PMRSError,'RESOURCE_WAIT'):
                    with resources.reserve(self.root,owner='third',temporary_bytes=1,memory_bytes=1):pass
            with self.assertRaisesRegex(RuntimeError,'injected'):
                with resources.reserve(self.root,owner='failure',temporary_bytes=1,memory_bytes=1):raise RuntimeError('injected')
            with resources.reserve(self.root,owner='replacement',temporary_bytes=1,memory_bytes=1):pass
        self.assertEqual(resources.resource_status()['leases'],[])
        with resources.reserve(self.root,owner='one-worker',temporary_bytes=1,memory_bytes=1,max_preparations=1):
            with self.assertRaisesRegex(PMRSError,'RESOURCE_WAIT'):
                with resources.reserve(self.root,owner='second-worker',temporary_bytes=1,memory_bytes=1,max_preparations=1):pass

    def test_disk_and_interrupted_copy_never_publish_partial_input(self):
        source=self.root/'source';source.write_bytes(b'abc'*100000);destination=self.root/'work'/'copy'
        with patch('research_studio.resources.shutil.disk_usage') as usage:
            usage.return_value.free=resources.DISK_MARGIN_BYTES
            with self.assertRaisesRegex(PMRSError,'RESOURCE_DISK_LOW'):resources.disk_preflight(self.root,1)
        with patch('research_studio.resources.os.link',side_effect=OSError(28,'injected no space')):
            with self.assertRaisesRegex(PMRSError,'RESOURCE_DISK_LOW'):
                resources.copy_file(source,destination,1024*1024,sha(source.read_bytes()))
        self.assertFalse(destination.exists());self.assertFalse(list(destination.parent.glob('.prepare-*')))
        copied=resources.copy_file(source,destination,1024*1024,sha(source.read_bytes()))
        self.assertEqual(copied['copied_bytes'],source.stat().st_size)
        self.assertNotEqual(source.stat().st_ino,destination.stat().st_ino)

    def test_task_materialization_streams_files_without_read_blob_collection(self):
        store=Store.create(self.root/'p','Streaming preparation',synthetic=True)
        raw=b'x'*(2*1024*1024);source=store.blob(raw);packet=store.blob(canonical({'input_manifest':[]}));prompt=store.blob(b'Check exact material.')
        task={'task_id':'TASK-streaming','input_packet_ref':packet,'prompt_ref':prompt,
              'report_context':{'files':{'source.bin':source}}}
        work=store.root/'runs'/'TASK-streaming'/'work'
        with patch.object(store,'read_blob',side_effect=AssertionError('whole material collection read')):
            made=runner.materialize_task_inputs(store,task,work)
        self.assertEqual(made['peak_copy_chunk_bytes'],resources.CHUNK_BYTES)
        runner.verify_task_inputs(work,made['files'])
        self.assertEqual(resources.hash_file(work/'report-inputs/source.bin',len(raw)),source)
        self.assertNotEqual((store.root/'blobs'/source).stat().st_ino,(work/'report-inputs/source.bin').stat().st_ino)

    def test_visual_task_has_no_full_literature_packet_and_settled_cache_is_rebuildable(self):
        store,iid,evidence=ready_survey(self.root/'p')
        survey.start_activity(store,iid,'S5','Authorize bounded synthetic report.',max_calls=3,policy=demo.policy())
        result=reports.run(store,iid,executor=demo.executor(),policy=demo.policy(),max_tasks=2)
        prepared=reports.prepare(store,iid,report_id=result['report_id'])
        self.assertEqual(prepared['role'],'REPORT_VISUAL')
        self.assertNotIn('snapshot.json',prepared['report_context']['files'])
        self.assertFalse(any(name.startswith(('source-','record-')) for name in prepared['report_context']['files']))
        reports._assign_role(store,iid,prepared)
        plan=scheduler.plan(store.read_snapshot(),[iid],demo.policy())
        selected=scheduler.commit_dispatch(store,plan,policy=demo.policy())['prepared'][0]
        task=store.read_snapshot()['tasks'][selected['task_id']]
        import json
        packet=json.loads(store.read_blob(task['input_packet_ref']))
        self.assertNotIn('body_text',packet);self.assertNotIn('source_bytes_base64',packet)
        self.assertEqual(packet['material_refs'],task['material_refs'])
        self.assertNotIn('report_files_base64',packet)
        work=store.root/'runs'/task['task_id']/'work';runner.materialize_task_inputs(store,task,work)
        self.assertTrue(runner.cleanup_task_inputs(store,task['task_id'])['protected'])
        (work/'response.json').write_text('Synthetic preserved response file.')
        (work.parent/'command.json').write_text('[]')
        demo.executor().execute(store,task['task_id'])
        self.assertFalse((work/'packet.json').exists());self.assertTrue((work/'response.json').exists())
        self.assertTrue((work.parent/'command.json').exists())
        self.assertTrue(store.read_blob(task['input_packet_ref']))
        again=execution.recover(store,task['request_id']);self.assertEqual(again['state'],'EXACT_DUPLICATE')

    def test_unknown_inputs_are_protected_and_cleanup_failure_cannot_repeat_settlement(self):
        store,iid,_=ready_survey(self.root/'p')
        survey.start_activity(store,iid,'S5','Authorize a controlled recovery test.',max_calls=3,policy=demo.policy())
        prepared=reports.prepare(store,iid);reports._assign_role(store,iid,prepared)
        plan=scheduler.plan(store.read_snapshot(),[iid],demo.policy())
        made=scheduler.commit_dispatch(store,plan,policy=demo.policy())['prepared'][0]
        task=store.read_snapshot()['tasks'][made['task_id']]
        work=store.root/'runs'/task['task_id']/'work';runner.materialize_task_inputs(store,task,work)
        crashing=runner.FakeExecutor(demo.response,fault_at='AFTER_RESERVATION_BEFORE_SEND')
        with self.assertRaises(runner.SimulatedCrash):crashing.execute(store,task['task_id'])
        state=store.read_snapshot();request=state['requests'][task['request_id']]
        store.commit_execution(execution.event('UNKNOWN',{'request_id':request['request_id'],
            'execution_id':request['execution_id'],'reason':'Controlled unknown transport; no repeat is authorized.'}))
        self.assertTrue(runner.cleanup_task_inputs(store,task['task_id'])['protected'])
        self.assertTrue((work/'packet.json').exists())
        # An original transport result arrives later. A failure to reclaim its
        # cache cannot undo the accepted result or manufacture a second call.
        from copy import deepcopy
        fixture_task=deepcopy(task)
        fixture_task['report_context']['statement_bodies']={ref:store.read_blob(digest).decode()
            for ref,digest in task['report_context'].get('statement_refs',{}).items()}
        raw=demo.response(fixture_task,store.read_snapshot())
        execution.capture(store,request['request_id'],raw,execution_id=request['execution_id'])
        with patch('research_studio.runner.cleanup_task_inputs',side_effect=OSError('injected cache cleanup failure')):
            result=execution.recover(store,request['request_id'])
        self.assertEqual(result['state'],'ACCEPTED');self.assertEqual(result['cache_cleanup']['state'],'PRESERVED')
        calls=store.read_snapshot()['usage']['model_calls']
        self.assertEqual(execution.recover(store,request['request_id'])['state'],'EXACT_DUPLICATE')
        self.assertEqual(store.read_snapshot()['usage']['model_calls'],calls)
        self.assertFalse((work/'packet.json').exists())

    def test_command_publication_failure_preserves_prepared_request_for_same_retry(self):
        store,iid,_=ready_survey(self.root/'p')
        policy=demo.policy();policy['executor_contract']={'executor':'codex','sandbox':'required','environment_revision':'controlled-no-transport-test'}
        survey.start_activity(store,iid,'S5','Authorize one controlled preparation failure test.',max_calls=1,policy=policy)
        prepared=reports.prepare(store,iid);reports._assign_role(store,iid,prepared)
        plan=scheduler.plan(store.read_snapshot(),[iid],policy)
        made=scheduler.commit_dispatch(store,plan,policy=policy)['prepared'][0]
        immutable=runner.immutable
        def fail_command(path,data):
            if Path(path).name=='command.json':raise PMRSError('RESOURCE_DISK_LOW','Controlled publication failure.')
            return immutable(path,data)
        from research_studio import task_tools
        popen=runner.subprocess.Popen
        allowed_probe=task_tools.server_command(store.root/'execution'/'tool-capabilities'/(made['request_id']+'.json'))
        def only_local_probe(command,*args,**kwargs):
            # Request-scoped MCP initialization is local and unbilled. The
            # model command must remain forbidden until publication succeeds.
            self.assertEqual(command,allowed_probe,'No model transport may start')
            return popen(command,*args,**kwargs)
        with patch('research_studio.runner.doctor',return_value={'ready':True,'binary':'/bin/true'}), \
             patch('research_studio.runner.immutable',side_effect=fail_command), \
             patch('research_studio.runner.subprocess.Popen',side_effect=only_local_probe):
            result=runner.CodexExecutor('/bin/true').execute(store,made['task_id'])
            self.assertEqual((result['state'],result['code']),('RESOURCE_WAIT','RESOURCE_DISK_LOW'))
        self.assertEqual(store.read_snapshot()['requests'][made['request_id']]['execution_state'],'PREPARED')
        self.assertFalse((store.root/'runs'/made['task_id']/'work').exists())
        self.assertEqual(resources.resource_status()['leases'],[])
