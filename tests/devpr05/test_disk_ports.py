import base64
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pmrh.adapters.storage.repositories import EvidenceRepository, EventRepository, DiskStorage
from pmrh.application.unit_of_work import UnitOfWork
from pmrh.ports.dto import core as C, enums as E, storage as T
from . import fixtures as F


class DiskPorts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store, self.iid, self.disk, self.policy, self.uow = F.project(Path(self.tmp.name)/'p')
        self.boundary = self.disk.current_boundary()
        self.evidence = EvidenceRepository(self.disk); self.events = EventRepository(self.disk)

    def assertError(self, result, code):
        self.assertIsInstance(result, C.ErrorEnvelope)
        self.assertEqual(result.code.value, code)

    def test_real_stage_rollback_commit_slice_and_envelope(self):
        batch = F.batch(self.boundary, count=2)
        before = (self.store.root/'HEAD').read_bytes()
        tx, permit = F.stage(self.uow, self.policy, self.boundary, batch)
        self.assertError(self.evidence.read(batch.evidence[0].evidence_ref, self.boundary), 'NOT_FOUND')
        self.assertEqual((self.store.root/'HEAD').read_bytes(), before)
        self.assertEqual(self.uow.stage(tx, batch).batch_digest, batch.wire_digest())
        self.assertError(self.uow.stage(tx, F.batch(self.boundary, 'changed')), 'IDEMPOTENCY_CONFLICT')
        self.uow.rollback(tx)
        self.assertError(self.uow.commit(tx, permit), 'TRANSACTION_CLOSED')
        tx, permit = F.stage(self.uow, self.policy, self.boundary, batch)
        receipt = self.uow.commit(tx, permit); self.assertIsInstance(receipt, T.CommitReceipt)
        self.assertError(self.uow.rollback(tx), 'TRANSACTION_CLOSED')
        chunk = self.evidence.read(batch.evidence[0].evidence_ref, receipt.boundary, offset=2, max_bytes=4)
        self.assertEqual(base64.b64decode(chunk.content_base64), b'act ')
        self.assertEqual(chunk.total_bytes, len(b'Exact synthetic original'))
        page = self.events.read_events(F.cursor(receipt.boundary), receipt.boundary)
        self.assertEqual([e.journal_sequence for e in page.events], [1, 2])
        self.assertEqual([e.aggregate_sequence for e in page.events], [1, 2])
        for event in page.events:
            self.assertTrue(self.events.verify_event(event, receipt.boundary).verified)
            self.assertEqual(event.observed_at, F.NOW)
            self.assertEqual(event.committed_at.clock_source, E.ClockSource.JOURNAL)
        ref = F.F.envelope_ref(self.boundary.scope, batch.events[0])
        original = self.evidence.read(ref, receipt.boundary, max_bytes=1024*1024)
        self.assertEqual(base64.b64decode(original.content_base64), batch.events[0].to_json().encode())
        self.assertNotIn(ref.sha256, self.store.orphans()['unreferenced_blobs'])
        self.assertTrue(self.store.audit()['valid'])

    def test_evidence_only_and_persistent_identity_conflict(self):
        batch = F.batch(self.boundary, count=0)
        receipt = F.commit(self.uow, self.policy, self.boundary, batch)
        self.assertEqual(receipt.event_ids, ())
        self.assertEqual(receipt.boundary.through_journal_sequence, 0)
        changed = replace(F.batch(receipt.boundary, 'two', count=0), evidence=(F.evidence(self.boundary.scope, data=b'changed'),))
        self.assertError(F.commit(self.uow, self.policy, receipt.boundary, changed), 'IDEMPOTENCY_CONFLICT')

    def test_current_authority_and_permit_transaction_binding(self):
        batch = F.batch(self.boundary)
        tx, permit = F.stage(self.uow, self.policy, self.boundary, batch)
        self.assertError(self.uow.commit(tx, None), 'AUTHORIZATION_REQUIRED')
        tx2, permit2 = F.stage(self.uow, self.policy, self.boundary, batch)
        self.assertError(self.uow.commit(tx2, permit), 'AUTHORIZATION_REQUIRED')
        with self.disk.locked(): self.policy.version += 1
        self.assertError(self.uow.commit(tx2, permit2), 'STALE_CONTROL_VERSION')
        with self.disk.locked(): self.policy.version -= 1
        receipt = self.uow.commit(tx, permit); self.assertIsInstance(receipt, T.CommitReceipt)
        tx3, permit3 = F.stage(self.uow, self.policy, self.boundary, batch)
        with self.disk.locked(): self.policy.enabled = False
        self.assertError(self.uow.commit(tx3, permit3), 'AUTHORIZATION_REQUIRED')
        self.assertError(self.evidence.read(batch.evidence[0].evidence_ref, receipt.boundary), 'AUTHORIZATION_REQUIRED')
        self.assertError(DiskStorage(self.store.root).current_boundary(), 'AUTHORIZATION_REQUIRED')

    def test_unsupported_science_human_and_publication_fields(self):
        base = F.batch(self.boundary)
        variants = [replace(base.events[0], actor_kind='HUMAN'),
                    replace(base.events[0], event_type='THEOREM_ACCEPTED'),
                    replace(base.events[0], logical_main_id='MAIN-forged'),
                    replace(base.events[0], aggregate_sequence=1),
                    replace(base.events[0], operation_id='operation:other'),
                    replace(base.events[0], owner_epoch=99)]
        before = (self.store.root/'HEAD').read_bytes()
        for event in variants:
            with self.subTest(event=event):
                result = F.commit(self.uow, self.policy, self.boundary, replace(base, events=(event,)))
                self.assertIsInstance(result, C.ErrorEnvelope)
                self.assertEqual((self.store.root/'HEAD').read_bytes(), before)
        reserved = replace(base.evidence[0].evidence_ref, object_id='KR-'+'a'*64)
        unsupported = replace(base, events=(), evidence=(replace(base.evidence[0], evidence_ref=reserved),))
        self.assertError(F.commit(self.uow, self.policy, self.boundary, unsupported), 'INVALID_FIELD')
        unknown = replace(base.events[0], payload_ref=F.evidence(self.boundary.scope,'missing').evidence_ref)
        self.assertError(F.commit(self.uow, self.policy, self.boundary, replace(base,events=(unknown,))), 'NOT_FOUND')

    def test_future_orphan_cross_scope_and_forged_boundary(self):
        batch = F.batch(self.boundary); receipt = F.commit(self.uow, self.policy, self.boundary, batch)
        ref = batch.evidence[0].evidence_ref
        self.assertError(self.evidence.read(ref, self.boundary), 'NOT_FOUND')
        orphan = F.evidence(self.boundary.scope, 'orphan', b'Orphan')
        self.store.put_blob(b'Orphan')
        self.assertError(self.evidence.read(orphan.evidence_ref, receipt.boundary), 'NOT_FOUND')
        forged = replace(receipt.boundary, through_journal_sequence=100)
        self.assertError(self.evidence.read(ref, forged), 'NOT_FOUND')
        forged_ref = replace(receipt.boundary.commit_ref, object_id='synthetic:fake-commit')
        self.assertError(self.evidence.read(ref, replace(receipt.boundary,commit_ref=forged_ref)), 'NOT_FOUND')
        iid2 = F.Engine().new_workflow(self.store, 'TRH', target_ref=next(iter(self.store.read_snapshot()['records'])))['instance_id']
        disk2, policy2, uow2 = F.assemble(self.store, iid2, install=True)
        boundary2 = disk2.current_boundary()
        self.assertError(EvidenceRepository(disk2).read(ref, boundary2), 'NOT_FOUND')
        shared = replace(F.batch(boundary2, 'shared', count=0), evidence=batch.evidence)
        shared_receipt = F.commit(uow2, policy2, boundary2, shared)
        self.assertIsInstance(EvidenceRepository(disk2).read(ref, shared_receipt.boundary), T.EvidenceSlice)
        self.assertError(self.evidence.read(ref, shared_receipt.boundary), 'AUTHORIZATION_REQUIRED')

    def test_bounds_tampering_and_exact_event_verification(self):
        batch = F.batch(self.boundary); receipt = F.commit(self.uow, self.policy, self.boundary, batch)
        ref = batch.evidence[0].evidence_ref
        for kwargs in ({'offset':-1},{'offset':True},{'offset':1000},{'max_bytes':0},{'max_bytes':1024*1024+1}):
            self.assertError(self.evidence.read(ref, receipt.boundary, **kwargs), 'INVALID_FIELD')
        page = self.events.read_events(F.cursor(receipt.boundary), receipt.boundary)
        event = page.events[0]
        for changes in ({'actor_kind':'APPLICATION'}, {'correlation_id':'forged'}, {'aggregate_sequence':2},
                        {'observed_at':replace(F.NOW, utc='2026-10-15T01:00:00Z')}, {'event_type':'OTHER'},
                        {'trust_origin':E.TrustOrigin.AUTHENTICATED_APPLICATION}):
            self.assertError(self.events.verify_event(replace(event, **changes), receipt.boundary), 'UNTRUSTED_EVENT')
        (self.store.root/'blobs'/ref.sha256).write_bytes(b'corrupted')
        self.assertError(self.evidence.read(ref, receipt.boundary), 'CORRUPT_CAPTURE')

    def test_closed_handles_aggregate_bound_and_post_head_uncertainty(self):
        from pmrh.ports.dto.wire import ContractViolation
        batch = F.batch(self.boundary)
        tx, permit = F.stage(self.uow, self.policy, self.boundary, batch)
        forged = replace(tx, expected=replace(tx.expected, owner_epoch=2))
        self.assertError(self.uow.stage(forged,batch),'TRANSACTION_CLOSED')
        self.assertError(self.uow.commit(forged,permit),'TRANSACTION_CLOSED')
        with self.assertRaises(ContractViolation):F.evidence(self.boundary.scope,data=b'x'*(1024*1024+1))
        writes=tuple(F.evidence(self.boundary.scope,'large'+str(n),b'x'*(1024*1024)) for n in range(7))
        with self.assertRaises(ContractViolation):
            T.CommitBatch(operation_id='large',idempotency_key='large',evidence=writes,events=()).to_wire()
        def lost(where):
            if where=='after_head':raise RuntimeError('lost local reply')
        self.disk.writer._test_fault_hook=lost
        self.assertError(self.uow.commit(tx,permit),'UNOBSERVED')
        self.assertError(self.uow.rollback(tx),'TRANSACTION_CLOSED')
        self.disk.writer._test_fault_hook=None
        result=self.uow.commit(tx,permit)
        self.assertEqual(result.duplicate_status,E.DuplicateStatus.EXACT_DUPLICATE)
