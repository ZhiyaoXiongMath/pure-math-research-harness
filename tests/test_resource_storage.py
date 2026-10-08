"""Bounded disposable projections and real publication-failure recovery."""
import errno
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from research_studio import demo, execution, reports, survey, workflow_instances as W
from research_studio.engine import Engine
from research_studio.runner import FakeExecutor, SimulatedCrash
from research_studio.store import Store, CHECKPOINT_RETAIN, CHECKPOINT_CACHE_BYTES
from research_studio.util import PMRSError, atomic, immutable, sha
from tests.test_survey import ready_survey


class ResourceStorage(unittest.TestCase):
    def test_visual_capture_rechecks_damaged_pages_after_input_reduction(self):
        with tempfile.TemporaryDirectory() as tmp:
            store,iid,_=ready_survey(Path(tmp)/'p')
            survey.start_activity(store,iid,'S5','Check actual selected synthetic pages.',max_calls=4,policy=demo.policy())
            reports.run(store,iid,executor=demo.executor(),policy=demo.policy(),max_tasks=2)
            executor=FakeExecutor(demo.response,fault_at='AFTER_CAPTURE_RECEIPT_BEFORE_ADMISSION')
            with self.assertRaises(SimulatedCrash):reports.run(store,iid,executor=executor,policy=demo.policy())
            state=store.read_snapshot();entry=state['reports'][state['active_reports'][iid]]
            request=next(r for r in state['requests'].values() if r['execution_state']=='CAPTURED')
            task=state['tasks'][request['task_id']];self.assertEqual(task['role'],'REPORT_VISUAL')
            self.assertFalse(task['read_set'])
            digest=entry['profiles']['minimal']['render']['pages'][0]['sha256']
            page=store.root/'blobs'/digest;original=page.read_bytes();page.write_bytes(original+b'changed')
            with self.assertRaisesRegex(PMRSError,'BLOB_CHANGED'):execution.recover(store,request['request_id'])
            self.assertEqual(store.read_snapshot()['reports'][entry['report_id']]['profiles']['minimal']['visual'],{})
            page.write_bytes(original)
            # Restoring bytes does not rewrite an already settled failed review.
            self.assertEqual(execution.recover(store,request['request_id'])['state'],'REJECTED_CONTRACT')
            self.assertEqual(executor.calls,1);self.assertTrue(store.audit()['valid'])

    def test_checkpoint_retention_replays_old_state_and_preserves_report_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            store,iid,_=ready_survey(Path(tmp)/'p')
            survey.start_activity(store,iid,'S5','Render one explicitly selected synthetic report.',max_calls=3,policy=demo.policy())
            result=reports.run(store,iid,executor=demo.executor(),policy=demo.policy())
            self.assertEqual(result['state'],'COMPLETED_CURRENT_REPORT')
            saved=store.read_snapshot();old=saved['knowledge_commit'];entry=saved['reports'][result['report_id']]
            hashes={h:sha(store.read_blob(h)) for h in entry['blobs']}
            source_hashes={r['blob_hash']:sha(store.read_blob(r['blob_hash'])) for r in saved['sources'].values()}
            with patch('research_studio.store.CHECKPOINT_INTERVAL',4):
                for n in range(25):
                    s=store.read_snapshot();store.commit_control(W.event(s,'PAUSE',{'reason':'Explicit cache-boundary pause '+str(n)},instance_id=iid))
            cache=list((store.root/'checkpoints').glob('*.json'))
            self.assertLessEqual(len(cache),CHECKPOINT_RETAIN)
            self.assertLessEqual(sum(p.stat().st_size for p in cache),CHECKPOINT_CACHE_BYTES)
            self.assertEqual(Store(store.root).read_snapshot(old),saved)
            self.assertEqual({h:sha(store.read_blob(h)) for h in hashes},hashes)
            self.assertEqual({h:sha(store.read_blob(h)) for h in source_hashes},source_hashes)
            self.assertEqual(reports.classify(store,store.read_snapshot(),entry),'COMPLETED_CURRENT_REPORT')
            self.assertTrue(store.audit()['valid'])

    def test_disk_preflight_rejects_before_new_blob_and_preserves_head(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store.create(Path(tmp)/'p','Synthetic disk boundary',synthetic=True)
            before=store.read_snapshot();blobs={p.name for p in (store.root/'blobs').iterdir()}
            with patch('research_studio.resources.shutil.disk_usage',return_value=SimpleNamespace(free=0)):
                with self.assertRaisesRegex(PMRSError,'RESOURCE_DISK_LOW'):
                    store.put_blob(b'Not yet published.')
            self.assertEqual(store.read_snapshot(),before)
            self.assertEqual({p.name for p in (store.root/'blobs').iterdir()},blobs)

    def test_enospc_before_head_recovers_the_same_capture_without_resending(self):
        with tempfile.TemporaryDirectory() as tmp:
            e=Engine();store=e.create(Path(tmp)/'p',demo.ARITHMETIC,synthetic=True)
            target=next(iter(store.read_snapshot()['records']))
            iid=e.new_workflow(store,'TRW',target_ref=target)['instance_id']
            e.start_round(store,iid,'Investigate the exact synthetic statement.',max_calls=2,policy=demo.policy())
            tid=e.prepare(store,iid)['prepared'][0]['task_id']
            executor=FakeExecutor(demo.response,fault_at='AFTER_CAPTURE_RECEIPT_BEFORE_ADMISSION')
            with self.assertRaises(SimulatedCrash):executor.execute(store,tid)
            before=store.read_snapshot();rid=before['tasks'][tid]['request_id'];capture=before['requests'][rid]['capture_ref']
            replace=os.replace;failed=False
            def fail_head(source,target):
                nonlocal failed
                if Path(target)==store.root/'HEAD' and not failed:
                    failed=True;raise OSError(errno.ENOSPC,'Injected transient disk-full publication')
                return replace(source,target)
            with patch('research_studio.util.os.replace',side_effect=fail_head):
                with self.assertRaisesRegex(PMRSError,'RESOURCE_DISK_LOW'):execution.recover(store,rid)
            self.assertEqual(store.read_snapshot(),before)
            self.assertEqual(sha(store.read_blob(capture)),capture)
            self.assertFalse(list(store.root.rglob('.head-*')))
            self.assertFalse(list(store.root.rglob('.publish-*')))
            restored=Store(store.root);result=execution.recover(restored,rid)
            self.assertEqual(result['state'],'ACCEPTED');self.assertEqual(executor.calls,1)
            self.assertEqual(restored.read_snapshot()['requests'][rid]['capture_ref'],capture)
            execution.recover(restored,rid);self.assertEqual(executor.calls,1)
            self.assertTrue(restored.audit()['valid'])

    def test_failed_immutable_publication_does_not_expose_half_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination=Path(tmp)/'blob'
            with patch('research_studio.util.os.link',side_effect=OSError(errno.ENOSPC,'Injected disk-full link')):
                with self.assertRaisesRegex(PMRSError,'RESOURCE_DISK_LOW'):immutable(destination,b'Complete original')
            self.assertFalse(destination.exists());self.assertEqual(list(Path(tmp).iterdir()),[])
            immutable(destination,b'Complete original')
            inode=destination.stat().st_ino;immutable(destination,b'Complete original')
            self.assertEqual(destination.stat().st_ino,inode)

    def test_checkpoint_read_race_replays_instead_of_losing_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store.create(Path(tmp)/'p','Checkpoint read race',synthetic=True);before=store.read_snapshot()
            checkpoint=next((store.root/'checkpoints').glob('*.json'))
            from research_studio import store as module
            real_read=module.read;removed=False
            def race(path,*args,**kwargs):
                nonlocal removed
                if Path(path)==checkpoint and not removed:
                    removed=True;checkpoint.unlink()
                return real_read(path,*args,**kwargs)
            with patch('research_studio.store.read',side_effect=race):
                self.assertEqual(store.read_snapshot(),before)
            self.assertTrue(removed);self.assertTrue(store.audit()['valid'])
