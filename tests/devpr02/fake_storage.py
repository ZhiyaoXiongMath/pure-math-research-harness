"""Synthetic immutable snapshots and single-process atomic commit test double.

This is not journal/blob adaptation, crash-safe persistence, multiwriter locking
or real transactional authorization. DEV-PR-05/06 must implement those separately.
"""
from __future__ import annotations

import base64
from dataclasses import replace
import hashlib

from pmrh.ports.dto import control as P, core as C, enums as E, events as V, storage as T
from . import fixtures as F
from .fake_policy import FakePolicyGateway


class FakeStore:
    def __init__(self):
        self.boundary = F.BOUNDARY
        self.evidence: dict[C.ExactRef, bytes] = {}
        self.events: tuple[V.EventEnvelope, ...] = ()
        self.snapshots = {self.boundary: ({}, ())}
        self.commits: dict[str, T.CommitReceipt] = {}
        self.writes = 0
        self.reconciliations = 0


class FakeEvidenceRepository:
    def __init__(self, store: FakeStore):
        self.store = store
        self.reads = 0

    def read(self, evidence_ref: C.ExactRef, boundary: T.ReadBoundary, *,
             offset: int = 0, max_bytes: int = 65536) -> T.EvidenceSlice | C.ErrorEnvelope:
        self.reads += 1
        error = lambda code: C.port_error(code, E.Operation.READ_EVIDENCE, scope=boundary.scope)
        snapshot = self.store.snapshots.get(boundary)
        if snapshot is None or evidence_ref not in snapshot[0]:
            return error(E.ErrorCode.NOT_FOUND)
        if (type(offset) is not int or type(max_bytes) is not int or offset < 0
                or not 1 <= max_bytes <= T.MAX_EVIDENCE_BYTES):
            return error(E.ErrorCode.INVALID_FIELD)
        raw = snapshot[0][evidence_ref]
        if hashlib.sha256(raw).hexdigest() != evidence_ref.sha256:
            return error(E.ErrorCode.CORRUPT_CAPTURE)
        if offset > len(raw):
            return error(E.ErrorCode.INVALID_FIELD)
        chunk = raw[offset:offset + max_bytes]
        return T.EvidenceSlice(evidence_ref=evidence_ref, boundary=boundary, offset=offset,
                               total_bytes=len(raw), content_base64=base64.b64encode(chunk).decode("ascii"),
                               slice_sha256=hashlib.sha256(chunk).hexdigest())


class FakeEventRepository:
    def __init__(self, store: FakeStore):
        self.store = store
        self.first_available = 1
        self.duplicate_event_ids: tuple[str, ...] = ()
        self.reads = 0

    def read_events(self, cursor: V.EventCursor, boundary: T.ReadBoundary, *,
                    limit: int = 256) -> V.EventPage | C.ErrorEnvelope:
        self.reads += 1
        error = lambda code: C.port_error(code, E.Operation.READ_EVENTS, scope=boundary.scope)
        snapshot = self.store.snapshots.get(boundary)
        if snapshot is None:
            return error(E.ErrorCode.NOT_FOUND)
        if (cursor.scope != boundary.scope or cursor.stream_kind is not E.StreamKind.JOURNAL
                or cursor.stream_id != boundary.journal_id or type(limit) is not int or not 1 <= limit <= 256
                or cursor.after_sequence > boundary.through_journal_sequence):
            return error(E.ErrorCode.INVALID_CURSOR)
        events = snapshot[1]
        if cursor.after_sequence and events[cursor.after_sequence - 1].event_id != cursor.last_event_id:
            return error(E.ErrorCode.INVALID_CURSOR)
        if cursor.after_sequence < boundary.through_journal_sequence and cursor.after_sequence + 1 < self.first_available:
            gap = V.EventGap(first_missing_sequence=cursor.after_sequence + 1,
                             last_missing_sequence=min(self.first_available - 1, boundary.through_journal_sequence),
                             reason=E.GapReason.RETENTION, resnapshot_ref=boundary.commit_ref)
            return V.EventPage(requested_cursor=cursor, next_cursor=cursor, status=E.PageStatus.GAP,
                                events=(), duplicate_event_ids=(), gap=gap)
        selected = events[cursor.after_sequence:cursor.after_sequence + limit]
        nxt = (replace(cursor, after_sequence=selected[-1].journal_sequence, last_event_id=selected[-1].event_id)
               if selected else cursor)
        return V.EventPage(requested_cursor=cursor, next_cursor=nxt,
                            status=E.PageStatus.COMPLETE if selected else E.PageStatus.EMPTY,
                            events=selected, duplicate_event_ids=self.duplicate_event_ids, gap=None)

    def verify_event(self, event: V.EventEnvelope, boundary: T.ReadBoundary) -> T.EventVerification | C.ErrorEnvelope:
        self.reads += 1
        snapshot = self.store.snapshots.get(boundary)
        if snapshot is None or event not in snapshot[1]:
            return C.port_error(E.ErrorCode.UNTRUSTED_EVENT, E.Operation.ACCEPT_EVENT, scope=boundary.scope)
        return T.EventVerification(event_id=event.event_id, boundary=boundary, verified=True)


class FakeUnitOfWork:
    def __init__(self, store: FakeStore, policy: FakePolicyGateway):
        self.store, self.policy = store, policy
        self.transactions: dict[str, tuple[T.TransactionHandle, T.CommitBatch | None]] = {}
        self.serial = 0

    def begin(self, expected: T.VersionExpectation) -> T.TransactionHandle | C.ErrorEnvelope:
        if expected.boundary.scope != self.policy.control.scope:
            return C.port_error(E.ErrorCode.AUTHORIZATION_REQUIRED, E.Operation.BEGIN_TRANSACTION,
                                scope=expected.boundary.scope)
        self.serial += 1
        tx = T.TransactionHandle(transaction_id="synthetic:tx-" + str(self.serial), expected=expected)
        self.transactions[tx.transaction_id] = (tx, None)
        return tx

    def _batch(self, tx: T.TransactionHandle):
        entry = self.transactions.get(tx.transaction_id)
        return entry[1] if entry is not None and entry[0] == tx else None

    def stage(self, transaction: T.TransactionHandle, batch: T.CommitBatch) -> T.StagingReceipt | C.ErrorEnvelope:
        entry = self.transactions.get(transaction.transaction_id)
        if entry is None or entry[0] != transaction:
            return C.port_error(E.ErrorCode.TRANSACTION_CLOSED, E.Operation.STAGE_TRANSACTION)
        if entry[1] is not None and entry[1] != batch:
            return C.port_error(E.ErrorCode.IDEMPOTENCY_CONFLICT, E.Operation.STAGE_TRANSACTION)
        self.transactions[transaction.transaction_id] = (transaction, batch)
        return T.StagingReceipt(transaction=transaction, batch_digest=batch.wire_digest(), state=E.TransactionState.OPEN)

    def commit_intent(self, tx: T.TransactionHandle) -> P.OperationIntent:
        batch = self._batch(tx)
        if batch is None:
            raise ValueError("synthetic transaction has no staged batch")
        return self.policy.intent(batch, E.Operation.COMMIT, batch.operation_id,
                                  epoch=tx.expected.owner_epoch, version=tx.expected.expected_control_version,
                                  scope=tx.expected.boundary.scope)

    def commit(self, transaction: T.TransactionHandle,
               permit: P.OperationPermit | None) -> T.CommitReceipt | C.ErrorEnvelope:
        batch = self._batch(transaction)
        if batch is None:
            return C.port_error(E.ErrorCode.TRANSACTION_CLOSED, E.Operation.COMMIT)
        check = self.policy.verify(permit, self.commit_intent(transaction))
        if isinstance(check, C.ErrorEnvelope):
            return check
        old = self.store.commits.get(batch.idempotency_key)
        if old is not None:
            if old.batch_digest != batch.wire_digest():
                return C.port_error(E.ErrorCode.IDEMPOTENCY_CONFLICT, E.Operation.COMMIT)
            del self.transactions[transaction.transaction_id]
            return replace(old, duplicate_status=E.DuplicateStatus.EXACT_DUPLICATE)
        if transaction.expected.boundary != self.store.boundary:
            return C.port_error(E.ErrorCode.VERSION_CONFLICT, E.Operation.COMMIT)
        scope = self.store.boundary.scope
        data = dict(self.store.evidence)
        by_id = {(r.project_id, r.object_id, r.revision): r for r in data}
        for write in batch.evidence:
            ref = write.evidence_ref
            previous = by_id.get((ref.project_id, ref.object_id, ref.revision))
            if ref.project_id != scope.project_id or (previous is not None and previous != ref):
                return C.port_error(E.ErrorCode.IDEMPOTENCY_CONFLICT, E.Operation.COMMIT, scope=scope)
            data[ref] = T.evidence_bytes(write.content_base64)
        seen = {event.event_id for event in self.store.events}
        for event in batch.events:
            if (event.scope() != scope or event.event_id in seen or event.payload_ref not in data
                    or event.raw_evidence_ref not in data or event.visibility_policy_ref != self.store.boundary.visibility_policy_ref):
                return C.port_error(E.ErrorCode.IDEMPOTENCY_CONFLICT, E.Operation.COMMIT, scope=scope)
        now = self.policy.clock.now()
        commit_ref = F.ref("commit-" + str(self.store.writes + 1), batch.to_json().encode())
        events = list(self.store.events)
        for event in batch.events:
            aggregate_seq = sum(e.aggregate_id == event.aggregate_id for e in events) + 1
            events.append(replace(event, status=E.EventStatus.COMMITTED, journal_id=F.observed(self.store.boundary.journal_id),
                                  aggregate_sequence=aggregate_seq, journal_sequence=len(events) + 1,
                                  commit_ref=commit_ref, committed_at=now, actor_kind="SYNTHETIC",
                                  trust_origin=E.TrustOrigin.SYNTHETIC_TEST_ONLY))
        boundary = replace(self.store.boundary, commit_ref=commit_ref, through_journal_sequence=len(events))
        receipt = T.CommitReceipt(operation_id=batch.operation_id, batch_digest=batch.wire_digest(),
                                  previous_boundary=self.store.boundary, boundary=boundary,
                                  duplicate_status=E.DuplicateStatus.NEW, committed_at=now,
                                  event_ids=tuple(e.event_id for e in batch.events))
        # The only publication point; all checks precede this in-memory update.
        self.store.evidence, self.store.events, self.store.boundary = data, tuple(events), boundary
        self.store.snapshots[boundary] = (dict(data), tuple(events))
        self.store.commits[batch.idempotency_key] = receipt
        self.store.writes += 1
        del self.transactions[transaction.transaction_id]
        return receipt

    def rollback(self, transaction: T.TransactionHandle) -> T.RollbackReceipt | C.ErrorEnvelope:
        entry = self.transactions.get(transaction.transaction_id)
        if entry is None or entry[0] != transaction:
            return C.port_error(E.ErrorCode.TRANSACTION_CLOSED, E.Operation.ROLLBACK)
        del self.transactions[transaction.transaction_id]
        return T.RollbackReceipt(transaction_id=transaction.transaction_id, state=E.TransactionState.ROLLED_BACK)
