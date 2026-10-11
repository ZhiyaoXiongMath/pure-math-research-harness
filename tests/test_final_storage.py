"""POSIX journal publication, fault recovery and measured delta growth."""
from pathlib import Path
import tempfile
import unittest
from copy import deepcopy
import resource
import time
import json
from contextlib import closing
from research_studio.store import Store
from research_studio.engine import Engine
from research_studio import changes,workflow_instances as W,demo
from research_studio.util import canonical,sha,loads,PMRSError


class JournalTests(unittest.TestCase):
    def test_faults_at_blobs_records_commit_and_head_preserve_whole_transaction(self):
        for boundary in ('after_blobs','after_records','after_commit','before_head','after_head'):
            with self.subTest(boundary=boundary),tempfile.TemporaryDirectory() as tmp:
                store=Store.create(Path(tmp)/'p','Fault test',synthetic=True);before=store.read_snapshot();raw=b'For every integer n, n + 0 = n.'
                proposal=changes.prepare_source_input(before,raw,blob_get=store.read_blob)
                def crash(point):
                    if point==boundary:raise RuntimeError('injected '+point)
                store._test_fault_hook=crash
                with self.assertRaises(RuntimeError):store.commit(proposal)
                reopened=Store(store.root);state=reopened.read_snapshot();reopened.audit()
                if boundary=='after_head':self.assertEqual(len(state['records']),1);self.assertEqual(len(state['sources']),1)
                else:self.assertEqual(state['knowledge_commit'],before['knowledge_commit']);self.assertEqual(state['records'],{});self.assertEqual(state['sources'],{})
                originals={p.name:sha(p.read_bytes()) for p in (store.root/'blobs').iterdir()}
                inventory=reopened.orphans();self.assertTrue(inventory['dry_run']);self.assertEqual(inventory['deleted'],0)
                self.assertEqual(originals,{p.name:sha(p.read_bytes()) for p in (store.root/'blobs').iterdir()})
                self.assertEqual(list(store.root.glob('**/HEAD')),[store.root/'HEAD'])
    def test_science_control_boundary_record_bytes_and_checkpoint_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=Engine().create(Path(tmp)/'p',demo.ARITHMETIC,synthetic=True);target=next(iter(s.read_snapshot()['records']))
            i=Engine().new_workflow(s,'TRH',target_ref=target)['instance_id'];before=s.read_snapshot()
            with self.assertRaisesRegex(PMRSError,'STATE_PATCH_FORBIDDEN'):Store.create(Path(tmp)/'bad','bad',initial={'records':{}})
            with self.assertRaises(PMRSError):s.commit({'outcome':'ACCEPTED','records':{}})
            with self.assertRaises(PMRSError):s.commit_control({'event_type':'PATCH','records':{}})
            for x in range(130):
                snap=s.read_snapshot();s.commit_control(W.event(snap,'PAUSE',{'reason':'Explicit pause '+str(x)},instance_id=i))
            self.assertEqual(before['records'],s.read_snapshot()['records']);s.audit()
            # Content hashes are not chronological. Tamper the newest native
            # checkpoint actually used by the current read/audit, rather than
            # an arbitrary hash-sorted historical projection.
            head=loads((s.root/'HEAD').read_bytes())
            while not (s.root/'checkpoints'/(head['commit']+'.json')).exists():
                head=s._commit_record(head)['previous_commit']
            checkpoint=s.root/'checkpoints'/(head['commit']+'.json')
            data=loads(checkpoint.read_bytes());data['state']['title']='Tampered';data['state_sha256']=sha(canonical(data['state']));checkpoint.write_bytes(canonical(data))
            with self.assertRaisesRegex(PMRSError,'CHECKPOINT_CHANGED'):s.audit()
    def test_missing_projection_rebuild_and_actual_source_tamper_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=Engine().create(Path(tmp)/'p',demo.ARITHMETIC);before=s.read_snapshot();s.rebuild_projection()
            for p in (s.root/'.runtime').glob('projection*'):p.unlink()
            s.rebuild_projection();self.assertEqual(before['knowledge_commit'],s.read_snapshot()['knowledge_commit']);s.audit()
            source=next(iter(before['sources'].values()));path=s.root/'blobs'/source['blob_hash'];path.write_bytes(b'Changed original')
            with self.assertRaisesRegex(PMRSError,'BLOB_CHANGED'):s.audit()
    def test_supplied_record_file_change_blocks_capture_admission(self):
        from research_studio import scheduler,tasks,execution
        with tempfile.TemporaryDirectory() as tmp:
            s=Engine().create(Path(tmp)/'p',demo.ARITHMETIC,synthetic=True);target=next(iter(s.read_snapshot()['records']))
            e=Engine();i=e.new_workflow(s,'TRH',target_ref=target)['instance_id'];e.start_round(s,i,'Investigate',max_calls=2,policy=demo.policy())
            made=e.prepare(s,i);t=tasks.load(s,made['prepared'][0]['task_id']);r=execution.reserve(s,t['request_id'],execution_kind='SYNTHETIC_TEST_ONLY')
            execution.capture(s,t['request_id'],demo.response(t,s.read_snapshot()),execution_id=r['execution_id'])
            path=s.root/'records'/(target+'.json');data=loads(path.read_bytes());data['kind']='Context';path.write_bytes(canonical(data))
            with self.assertRaises(PMRSError):execution.recover(s,t['request_id'])
            self.assertIsNotNone(s.read_snapshot()['requests'][t['request_id']]['capture_ref'])
    def test_projection_symlinks_corruption_and_live_sidecars_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);s=Engine().create(root/'p',demo.ARITHMETIC);before=s.read_snapshot()['knowledge_commit']
            outside=root/'outside';outside.mkdir();runtime=s.root/'.runtime';saved=s.root/'.runtime-old';runtime.rename(saved);runtime.symlink_to(outside,target_is_directory=True)
            with self.assertRaises(PMRSError):s.rebuild_projection()
            self.assertFalse(list(outside.iterdir()));runtime.unlink();saved.rename(runtime)
            secret=outside/'untouched';secret.write_bytes(b'Original outside content');projection=runtime/'projection.sqlite';projection.symlink_to(secret)
            with self.assertRaises(PMRSError):s.rebuild_projection()
            self.assertEqual(secret.read_bytes(),b'Original outside content');projection.unlink()
            projection.write_bytes(b'broken SQLite');s.rebuild_projection()
            import sqlite3
            with closing(sqlite3.connect(projection)) as c:self.assertEqual(c.execute('pragma integrity_check').fetchone()[0],'ok')
            for suffix in ('-wal','-shm','-journal'):
                side=Path(str(projection)+suffix);side.write_bytes(b'live sidecar')
                with self.assertRaisesRegex(PMRSError,'PROJECTION_SIDECAR_PRESENT'):s.rebuild_projection()
                side.unlink()
            self.assertEqual(before,s.read_snapshot()['knowledge_commit']);s.audit()

    def test_atomic_multi_record_capture_and_obligation_effects_at_each_fault(self):
        from research_studio import tasks,execution
        from research_studio.knowledge import locator
        for boundary in ('after_blobs','after_records','after_commit','before_head','after_head'):
            with self.subTest(boundary=boundary),tempfile.TemporaryDirectory() as tmp:
                e=Engine();s=e.create(Path(tmp)/'p',demo.ARITHMETIC,synthetic=True);target=next(iter(s.read_snapshot()['records']))
                iid=e.new_workflow(s,'TRH',target_ref=target)['instance_id'];e.start_round(s,iid,'Investigate',max_calls=2,policy=demo.policy())
                made=e.prepare(s,iid);t=tasks.load(s,made['prepared'][0]['task_id']);raw=loads(demo.response(t,s.read_snapshot()))
                body='For every integer m, m + 1 is an integer.';loc=locator(body)
                raw['payload']['operations'].append({'op':'NEW','local_key':'extra','kind':'Statement','context_refs':[],'body':body,'data':{'statement_locator':loc,'scope_context_refs':[],'hypothesis_locators':[],'conclusion_locators':[loc],'quantifier_locators':[loc],'form':'CONJECTURE','representation':'AUTHORED','source_binding':None}})
                raw=canonical(raw);r=execution.reserve(s,t['request_id'],execution_kind='SYNTHETIC_TEST_ONLY');execution.capture(s,t['request_id'],raw,execution_id=r['execution_id'])
                before=s.read_snapshot();proposal=changes.validate_response(t,before,raw,'live',s.read_blob)
                def fail(point):
                    if point==boundary:raise RuntimeError(point)
                s._test_fault_hook=fail
                with self.assertRaises(RuntimeError):s.commit(proposal)
                reopened=Store(s.root);after=reopened.read_snapshot();reopened.audit()
                if boundary=='after_head':
                    self.assertEqual(len(after['records']),len(before['records'])+2)
                    self.assertEqual(after['requests'][t['request_id']]['execution_state'],'SETTLED')
                    self.assertNotEqual(after['obligations'],before['obligations'])
                else:
                    self.assertEqual(after['knowledge_commit'],before['knowledge_commit'])
                    self.assertEqual(after['records'],before['records']);self.assertEqual(after['obligations'],before['obligations'])
                    self.assertEqual(after['requests'][t['request_id']]['execution_state'],'CAPTURED')
                self.assertEqual(reopened.read_blob(after['requests'][t['request_id']]['capture_ref']),raw)

    def test_n03_ten_thousand_records_thousand_delta_controls_measured(self):
        with tempfile.TemporaryDirectory() as tmp:
            start=time.monotonic();store=Store.create(Path(tmp)/'p','Measured local journal')
            for offset in range(0,10000,64):
                snapshot=store.read_snapshot();state=snapshot
                for n in range(offset,min(offset+64,10000)):
                    p=changes.prepare_source_input(state,('Original bounded record '+str(n)+'.').encode(),source_id='SO-'+str(n),blob_get=store.read_blob)
                    for h,raw in p['blobs'].items():self.assertEqual(store.put_blob(raw),h)
                    state=changes.apply_validated(state,p)
                # Storage-pressure fixture only. Every original was validated above;
                # this private writer never becomes a public bulk-state API.
                with store._locked():store._publish(snapshot['_head'],snapshot,state,actor='TEST_FIXTURE',events=[{'type':'GENERATED_NATIVE_PRESSURE_FIXTURE','count':min(64,10000-offset)}])
            s=store.read_snapshot();self.assertEqual(len(s['records']),10000)
            target=next(iter(s['records']));i=Engine().new_workflow(store,'TRH',target_ref=target)['instance_id']
            body_refs={r['body_sha256'] for r in s['records'].values()};body_hashes={h:sha(store.read_blob(h)) for h in body_refs}
            baseline=store.read_snapshot();begin=baseline['_snapshot_sequence'];journal_bytes=[];delta_bytes=[]
            for n in range(1000):
                state=store.read_snapshot();result=store.commit_control(W.event(state,'PAUSE',{'reason':'Control-only pause '+str(n)},instance_id=i))
                entry=loads((store.root/Store(store.root)._head()['path']).read_bytes())
                self.assertIsNone(entry['knowledge_delta_ref']);self.assertIsNone(entry['report_delta_ref']);self.assertIsNone(entry['registry_delta_ref'])
                journal_bytes.append(len(canonical(entry)));delta_bytes.append(len(store.read_blob(entry['control_delta_ref'])))
            final=Store(store.root).read_snapshot();self.assertEqual(final['_snapshot_sequence'],begin+1000);self.assertEqual(final['records'],s['records'])
            self.assertEqual(body_hashes,{h:sha(store.read_blob(h)) for h in body_refs});self.assertEqual(len(body_refs),10000)
            self.assertLess(max(delta_bytes),min(delta_bytes)*2);store.audit()
            print(json.dumps({'measurement':'N03','records':10000,'control_commits':1000,'body_blobs':len(body_refs),'journal_bytes':sum(journal_bytes),'delta_bytes':sum(delta_bytes),'elapsed_seconds':time.monotonic()-start,'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}),flush=True)

if __name__=='__main__':unittest.main()
