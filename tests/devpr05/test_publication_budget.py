"""Bounded real-disk publication must never strand an unreadable HEAD."""
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pmrh.adapters.storage.io import _ConfinedReader
from pmrh.adapters.storage.journal import Journal
from pmrh.adapters.storage.repositories import DiskStorage, EvidenceRepository
from pmrh.domain.primitives import PMRSError, loads
from pmrh.ports.dto import core as C, enums as E, storage as T
from . import fixtures as F


@contextmanager
def reduced_budget(*, max_files=4096, max_bytes=128*1024**2):
    """Lower the real reader's limits in every caller; never bypass its I/O."""
    original = _ConfinedReader.__init__
    def limited(self, root, **kwargs):
        kwargs['max_files'] = min(kwargs.get('max_files',4096),max_files)
        kwargs['max_bytes'] = min(kwargs.get('max_bytes',128*1024**2),max_bytes)
        original(self,root,**kwargs)
    with patch.object(_ConfinedReader,'__init__',limited):
        yield


def read_cost(root):
    with _ConfinedReader(root) as reader:
        Journal(reader.root,reader=reader).read_snapshot()
        return 4096-reader.remaining_files,128*1024**2-reader.remaining_bytes


class PublicationBudget(unittest.TestCase):
    def assert_readable(self,store,disk,boundary):
        fresh=DiskStorage(store.root,context=disk.context)
        self.assertEqual(fresh.current_boundary(),boundary)
        self.assertEqual(F.Store(store.root).read_snapshot()['_head']['commit'],boundary.commit_ref.sha256)
        with _ConfinedReader(store.root) as reader:
            state=Journal(reader.root,reader=reader).read_snapshot()
            self.assertEqual(state['_head']['commit'],boundary.commit_ref.sha256)

    def test_one_valid_4096_reference_batch_rejects_before_head(self):
        with tempfile.TemporaryDirectory() as tmp:
            store,iid,disk,policy,uow=F.project(Path(tmp)/'p')
            boundary=disk.current_boundary();head=(store.root/'HEAD').read_bytes()
            batch=T.CommitBatch(operation_id='review:budget',idempotency_key='review:budget',
                evidence=tuple(F.evidence(boundary.scope,'budget-'+str(n),b'') for n in range(4096)),events=())
            self.assertEqual(len(batch.evidence),4096)
            self.assertLess(len(batch.to_json().encode()),8*1024**2)
            self.assertEqual(T.CommitBatch.from_json(batch.to_json()),batch)
            tx,permit=F.stage(uow,policy,boundary,batch)
            result=uow.commit(tx,permit)
            self.assertIsInstance(result,C.ErrorEnvelope)
            self.assertEqual(result.code,E.ErrorCode.UNOBSERVED)  # Fixed v1 vocabulary.
            self.assertEqual((store.root/'HEAD').read_bytes(),head)
            self.assert_readable(store,disk,boundary)
            candidates=list((store.root/'journal').glob(f"{loads(head)['sequence']+1:012d}-*.json"))
            self.assertEqual(len(candidates),1)  # Real journal exists, still an orphan.
            orphan_raw=candidates[0].read_bytes()
            candidate={'sequence':loads(head)['sequence']+1,'commit':candidates[0].stem.split('-',1)[1],
                       'path':str(candidates[0].relative_to(store.root))}
            with disk.locked(),self.assertRaisesRegex(PMRSError,'RESOURCE_LIMIT'):
                disk.writer._preflight_extended_head(candidate)
            with self.assertRaisesRegex(PMRSError,'SNAPSHOT_NOT_FOUND'):
                F.Store(store.root).read_snapshot(candidate['commit'])
            self.assertEqual(EvidenceRepository(disk).read(batch.evidence[0].evidence_ref,boundary).code,E.ErrorCode.NOT_FOUND)
            self.assertEqual(uow.commit(tx,permit).code,E.ErrorCode.UNOBSERVED)
            disk2,policy2,uow2=F.assemble(F.Store(store.root),iid)
            self.assertEqual(F.commit(uow2,policy2,boundary,batch).code,E.ErrorCode.UNOBSERVED)
            self.assertEqual((store.root/'HEAD').read_bytes(),head)
            # Rejected immutable files cannot poison a later small publication.
            small=F.batch(boundary,'after-rejection')
            receipt=F.commit(uow2,policy2,boundary,small)
            self.assertIsInstance(receipt,T.CommitReceipt)
            self.assert_readable(store,disk2,receipt.boundary)
            self.assertEqual(candidates[0].read_bytes(),orphan_raw)

    def test_normal_batches_stop_before_cumulative_file_or_byte_exhaustion(self):
        for dimension in ('files','bytes'):
            with self.subTest(dimension=dimension),tempfile.TemporaryDirectory() as tmp:
                store,iid,disk,policy,uow=F.project(Path(tmp)/'p')
                files,size=read_cost(store.root)
                limits=({'max_files':files+24} if dimension=='files' else {'max_bytes':size+96*1024})
                accepted=[];rejected=False
                with reduced_budget(**limits):
                    for n in range(8):
                        boundary=disk.current_boundary();self.assertIsInstance(boundary,T.ReadBoundary)
                        head=(store.root/'HEAD').read_bytes()
                        batch=F.batch(boundary,'bounded-'+str(n),count=0,
                                      data=(b'x'*(32*1024) if dimension=='bytes' else b'normal bounded evidence'))
                        tx,permit=F.stage(uow,policy,boundary,batch)
                        result=uow.commit(tx,permit)
                        if isinstance(result,C.ErrorEnvelope):
                            rejected=True
                            self.assertEqual(result.code,E.ErrorCode.UNOBSERVED)
                            self.assertEqual((store.root/'HEAD').read_bytes(),head)
                            self.assert_readable(store,disk,boundary)
                            self.assertEqual(uow.commit(tx,permit).code,E.ErrorCode.UNOBSERVED)
                            self.assertEqual((store.root/'HEAD').read_bytes(),head)
                            break
                        self.assertIsInstance(result,T.CommitReceipt)
                        accepted.append((boundary,batch,result))
                        self.assert_readable(store,disk,result.boundary)
                    self.assertTrue(rejected,'Bounded fixture must reach the real reader limit')
                    self.assertTrue(accepted,'Paired normal publications must succeed first')
                    original,batch,receipt=accepted[-1]
                    disk2,policy2,uow2=F.assemble(F.Store(store.root),iid)
                    duplicate=F.commit(uow2,policy2,original,batch)
                    self.assertEqual(duplicate,replace(receipt,duplicate_status=E.DuplicateStatus.EXACT_DUPLICATE))

    def test_later_legacy_and_checkpoint_commits_share_prepublication_limit(self):
        from research_studio import changes
        for interval in (128,1):
            with self.subTest(checkpoint=interval==1),tempfile.TemporaryDirectory() as tmp:
                store,iid,disk,policy,uow=F.project(Path(tmp)/'p')
                boundary=disk.current_boundary();head=(store.root/'HEAD').read_bytes()
                proposal=changes.prepare_source_input(store.read_snapshot(),b'Another exact synthetic source.',
                    source_id='SO-budget',blob_get=store.read_blob)
                files,_=read_cost(store.root)
                with reduced_budget(max_files=files),patch('research_studio.store.CHECKPOINT_INTERVAL',interval):
                    with self.assertRaisesRegex(PMRSError,'RESOURCE_LIMIT'):store.commit(proposal)
                    self.assertEqual((store.root/'HEAD').read_bytes(),head)
                    self.assert_readable(store,disk,boundary)
                candidates=list((store.root/'journal').glob(f"{loads(head)['sequence']+1:012d}-*.json"))
                self.assertEqual(len(candidates),1)
                digest=candidates[0].stem.split('-',1)[1]
                self.assertEqual((store.root/'checkpoints'/(digest+'.json')).exists(),interval==1)
                self.assertNotIn('SO-budget',store.read_snapshot()['sources'])

    def test_success_and_durable_retry_survive_discarding_all_checkpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            store,iid,disk,policy,uow=F.project(Path(tmp)/'p')
            original=disk.current_boundary();batch=F.batch(original,'checkpoint-free')
            with patch('pmrh.adapters.storage.journal.CHECKPOINT_INTERVAL',1),\
                 patch('research_studio.store.CHECKPOINT_INTERVAL',1):
                receipt=F.commit(uow,policy,original,batch)
                self.assertIsInstance(receipt,T.CommitReceipt)
                F.Engine().pause(store,iid,'Later extended native checkpoint')
                boundary=disk.current_boundary();self.assertIsInstance(boundary,T.ReadBoundary)
                before=store.read_snapshot()
                checkpoints=list((store.root/'checkpoints').glob('*.json'));self.assertTrue(checkpoints)
                for path in checkpoints:path.unlink()
                self.assert_readable(store,disk,boundary)
                self.assertEqual(F.Store(store.root).read_snapshot(),before)
                disk2,policy2,uow2=F.assemble(F.Store(store.root),iid)
                duplicate=F.commit(uow2,policy2,original,batch)
                self.assertEqual(duplicate,replace(receipt,duplicate_status=E.DuplicateStatus.EXACT_DUPLICATE))
                self.assertEqual(disk2.current_boundary(),boundary)
