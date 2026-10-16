import errno
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pmrh.adapters.storage import format as Fmt
from pmrh.adapters.storage.io import _ConfinedReader, _Unavailable
from pmrh.adapters.storage.repositories import EvidenceRepository
from pmrh.ports.dto import core as C, storage as T
from research_studio.util import canonical, loads, sha, PMRSError
from . import fixtures as F


class Formats(unittest.TestCase):
    def test_frozen_native_oracle_bytes_and_old_reader(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); results=[]
            for variant in ('baseline','facade'):
                output=root/(variant+'.json')
                child=F.child('oracle',variant,'trace',root/variant,output)
                self.assertEqual(child.returncode,0,child.stderr)
                results.append(json.loads(output.read_text()))
            self.assertEqual(results[0],results[1])
            out=root/'read.json'
            child=F.child('oracle','baseline','read',root/'facade',out)
            self.assertEqual(child.returncode,0,child.stderr);self.assertTrue(json.loads(out.read_text())['ok'])

    def test_sticky_extension_and_old_reader_writer_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);store,iid,disk,policy,uow=F.project(root/'p',extended=False)
            old=store.read_snapshot()['knowledge_commit']
            disk.bind_synthetic_scope() if disk.context.allow_install else None
            disk,policy,uow=F.assemble(store,iid,install=True)
            with patch('research_studio.store.CHECKPOINT_INTERVAL',1):F.Engine().pause(store,iid,'Sticky checkpoint')
            entry=store._commit_record(store._head());self.assertEqual(entry['schema'],Fmt.EXTENDED_SCHEMA)
            self.assertEqual(store.read_snapshot(old)['knowledge_commit'],old)
            before=(store.root/'HEAD').read_bytes()
            for action in ('read','historical:'+old,'write'):
                out=root/(str(len(action))+'.json')
                child=F.child('oracle','baseline',action,store.root,out)
                self.assertEqual(child.returncode,0,child.stderr)
                self.assertEqual(json.loads(out.read_text()),{'ok':False,'code':'JOURNAL_INVALID'})
                self.assertEqual((store.root/'HEAD').read_bytes(),before)
            # A forged later old-schema checkpoint cannot conceal the extension.
            entry['schema']='pmrs.commit/4.2.2';raw=canonical(entry);digest=sha(raw)
            head={'sequence':entry['sequence'],'commit':digest,'path':f"journal/{entry['sequence']:012d}-{digest}.json"}
            (store.root/head['path']).write_bytes(raw);(store.root/'HEAD').write_bytes(canonical(head))
            with self.assertRaisesRegex(PMRSError,'JOURNAL_INVALID'):store.read_snapshot()

    def test_smuggled_unknown_and_malformed_extension_rejected(self):
        for kind in ('old-schema','unknown-event','unknown-policy','extra-field'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp:
                store,iid,disk,policy,uow=F.project(Path(tmp)/'p')
                entry=store._commit_record(store._head())
                event=next(e for e in entry['events'] if e.get('type')==Fmt.BIND)
                if kind=='old-schema':entry['schema']='pmrs.commit/4.2.2'
                elif kind=='unknown-event':event['type']='PMRH_PORT_PRIVILEGE_GRANTED'
                elif kind=='extra-field':event['callback']='do-not-import'
                else:
                    raw=loads(store.read_blob(event['policy_sha256']));raw['schema']='pmrh.storage-visibility/999'
                    event['policy_sha256']=store.put_blob(canonical(raw))
                raw=canonical(entry);digest=sha(raw);head={'sequence':entry['sequence'],'commit':digest,
                    'path':f"journal/{entry['sequence']:012d}-{digest}.json"}
                (store.root/head['path']).write_bytes(raw);(store.root/'HEAD').write_bytes(canonical(head))
                with self.assertRaises(PMRSError):store.read_snapshot()

    def test_policy_needs_trusted_context_not_a_synthetic_marker(self):
        from pmrh.adapters.storage.repositories import DiskStorage, TrustedReadContext
        with tempfile.TemporaryDirectory() as tmp:
            store,iid,disk,policy,uow=F.project(Path(tmp)/'p',extended=False)
            with self.assertRaisesRegex(PMRSError,'AUTHORIZATION_REQUIRED'):disk.bind_synthetic_scope()
            with self.assertRaisesRegex(PMRSError,'AUTHORIZATION_REQUIRED'):DiskStorage(store.root).bind_synthetic_scope()
            self.assertIsInstance(disk.current_boundary(),C.ErrorEnvelope)

    def test_checkpoint_and_sqlite_disposable_but_corruption_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            store,iid,disk,policy,uow=F.project(Path(tmp)/'p')
            boundary=disk.current_boundary();receipt=F.commit(uow,policy,boundary,F.batch(boundary))
            before=store.read_snapshot();authoritative={str(p.relative_to(store.root)):p.read_bytes()
                for d in ('journal','blobs','records') for p in (store.root/d).iterdir()}
            store.rebuild_projection()
            (store.root/'.runtime/projection.sqlite').unlink()
            for p in (store.root/'checkpoints').glob('*.json'):p.unlink()
            self.assertEqual(store.read_snapshot(),before);store.rebuild_projection()
            self.assertEqual(authoritative,{str(p.relative_to(store.root)):p.read_bytes()
                for d in ('journal','blobs','records') for p in (store.root/d).iterdir()})
            with patch('research_studio.store.CHECKPOINT_INTERVAL',1):F.Engine().pause(store,iid,'New checkpoint')
            head=store._head();path=store.root/'checkpoints'/(head['commit']+'.json')
            value=loads(path.read_bytes());value['state']['title']='tampered'
            value['state_sha256']=sha(canonical(value['state']));path.write_bytes(canonical(value))
            with self.assertRaisesRegex(PMRSError,'CHECKPOINT_CHANGED'):store.read_snapshot()

    def test_confined_no_writes_links_limits_and_change_during_read(self):
        from tests.devpr03.fixtures import footprint
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);store,iid,disk,policy,uow=F.project(root/'p')
            boundary=disk.current_boundary();batch=F.batch(boundary);receipt=F.commit(uow,policy,boundary,batch)
            before=footprint(store.root)
            with patch('fcntl.flock',side_effect=AssertionError('read must not lock')):
                EvidenceRepository(disk).read(batch.evidence[0].evidence_ref,receipt.boundary)
            self.assertEqual(footprint(store.root),before)
            missing=root/'missing'
            with self.assertRaises(FileNotFoundError):
                with _ConfinedReader(missing):pass
            self.assertFalse(missing.exists())
            path=store.root/'blobs'/batch.evidence[0].evidence_ref.sha256
            os.link(path,root/'hardlink')
            self.assertIsInstance(EvidenceRepository(disk).read(batch.evidence[0].evidence_ref,receipt.boundary),C.ErrorEnvelope)
            (root/'hardlink').unlink()
            raw=path.read_bytes();path.unlink();outside=root/'outside';outside.write_bytes(raw);path.symlink_to(outside)
            self.assertIsInstance(EvidenceRepository(disk).read(batch.evidence[0].evidence_ref,receipt.boundary),C.ErrorEnvelope)
            path.unlink();path.write_bytes(raw)
            for maximum in (0,1):
                with _ConfinedReader(store.root,max_bytes=maximum) as reader:
                    with self.assertRaises(_Unavailable):reader.read('HEAD')
            with _ConfinedReader(store.root,max_files=0) as reader:
                with self.assertRaises(_Unavailable):reader.read('HEAD')
            with _ConfinedReader(store.root) as reader:
                with self.assertRaises(_Unavailable):reader.read('../outside')
                actual=os.read;changed=False
                def race(fd,n):
                    nonlocal changed
                    value=actual(fd,n)
                    if not changed:path.write_bytes(raw+b'changed');changed=True
                    return value
                with patch('os.read',race):
                    with self.assertRaises(_Unavailable):reader.read('blobs/'+path.name)

    def test_enospc_edquot_and_post_replace_fsync_uncertainty(self):
        from pmrh.adapters.storage import io
        for err in (errno.ENOSPC,errno.EDQUOT):
            with self.subTest(errno=err),tempfile.TemporaryDirectory() as tmp:
                store,iid,disk,policy,uow=F.project(Path(tmp)/'p')
                boundary=disk.current_boundary();batch=F.batch(boundary)
                tx,permit=F.stage(uow,policy,boundary,batch);head=store._head()
                with patch('os.link',side_effect=OSError(err,'synthetic full disk')):
                    result=uow.commit(tx,permit)
                self.assertIsInstance(result,C.ErrorEnvelope);self.assertEqual(store._head(),head)
                self.assertIsInstance(uow.commit(tx,permit),T.CommitReceipt)
        with tempfile.TemporaryDirectory() as tmp:
            store,iid,disk,policy,uow=F.project(Path(tmp)/'p')
            boundary=disk.current_boundary();batch=F.batch(boundary);tx,permit=F.stage(uow,policy,boundary,batch)
            original=io.fsync_dir
            def fail(directory):
                if Path(directory)==store.root:raise OSError(errno.ENOSPC,'HEAD directory sync uncertain')
                return original(directory)
            with patch.object(io,'fsync_dir',fail):result=uow.commit(tx,permit)
            self.assertIsInstance(result,C.ErrorEnvelope)
            disk2,policy2,uow2=F.assemble(F.Store(store.root),iid)
            recovered=F.commit(uow2,policy2,boundary,batch)
            self.assertEqual(recovered.duplicate_status.value,'EXACT_DUPLICATE')

    def test_private_replay_and_backup_retain_extended_closure(self):
        from research_studio.research_audit import bootstrap
        from research_studio.portability import export_project,verify_backup
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);store,iid,disk,policy,uow=F.project(root/'p')
            boundary=disk.current_boundary();F.commit(uow,policy,boundary,F.batch(boundary))
            before=store.read_snapshot();at=store._commit_record(store._head())['at']
            clock=bootstrap(store,before,iid,at)
            self.assertEqual(clock['reconstructed_through_commit'],before['knowledge_commit'])
            export_project(store,root/'backup.zip')
            manifest,files=verify_backup(root/'backup.zip')
            self.assertEqual(manifest['head'],before['_head'])
            self.assertEqual(files['HEAD'],(store.root/'HEAD').read_bytes())
            for digest in store._last_index.closure:self.assertIn('blobs/'+digest,files)

    def test_original_bounded_publisher_definitions(self):
        # Explicitly selected definitions; no discovery of legacy or stress suites.
        from tests.test_final_storage import JournalTests
        from tests.test_resource_storage import ResourceStorage
        for cls,name in [(JournalTests,'test_faults_at_blobs_records_commit_and_head_preserve_whole_transaction'),
                         (JournalTests,'test_missing_projection_rebuild_and_actual_source_tamper_detection'),
                         (JournalTests,'test_projection_symlinks_corruption_and_live_sidecars_fail_closed'),
                         (ResourceStorage,'test_disk_preflight_rejects_before_new_blob_and_preserves_head'),
                         (ResourceStorage,'test_failed_immutable_publication_does_not_expose_half_file'),
                         (ResourceStorage,'test_checkpoint_read_race_replays_instead_of_losing_history')]:
            with self.subTest(original=name):getattr(cls(),name)()
