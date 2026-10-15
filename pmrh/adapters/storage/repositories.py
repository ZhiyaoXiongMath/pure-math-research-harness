"""Real disk evidence/event repositories and the injected local transaction capability."""
from contextlib import contextmanager
from dataclasses import dataclass, replace
import base64

from pmrh.domain.primitives import canonical, PMRSError, sha
from pmrh.ports.dto import core as C, enums as E, events as V, storage as T
from pmrh.ports.dto.wire import ContractViolation
from .io import _ConfinedReader, _Unavailable
from .journal import Journal
from . import format as F


@dataclass(frozen=True)
class TrustedReadContext:
    """Out-of-band, local assembly only. Persisted labels cannot construct this.

    allow_read and allow_install are trusted local decisions, never project
    callbacks. Production installation is absent. Revocation and policy changes
    must share the project's writer exclusion contract with permit verification.
    """
    scope: C.Scope
    policy_raw: bytes
    allow_read: object
    allow_install: object = None

    def authorize(self, scope):
        F.checked(scope == self.scope and callable(self.allow_read) and self.allow_read() is True,
                  'AUTHORIZATION_REQUIRED')
        F.checked(self.policy_raw == F.policy_bytes(scope), 'AUTHORIZATION_REQUIRED')


def failure(exc, operation, scope=None):
    if isinstance(exc, FileNotFoundError):
        code = E.ErrorCode.NOT_FOUND
    elif isinstance(exc, (OSError, _Unavailable)):
        code = E.ErrorCode.UNOBSERVED
    else:
        raw = getattr(exc, 'code', None)
        try:
            code = E.ErrorCode(raw)
        except (ValueError, TypeError):
            code = (E.ErrorCode.UNOBSERVED if raw in ('RESOURCE_LIMIT', 'RESOURCE_DISK_LOW', 'FILE_UNAVAILABLE')
                    else E.ErrorCode.CORRUPT_CAPTURE)
    return C.port_error(code, operation, scope=scope)


READ_FAILURES = (PMRSError, ContractViolation, OSError, _Unavailable, ValueError,
                 TypeError, KeyError, AttributeError, RecursionError)


class DiskStorage:
    """Root is selected by composition, never by a DTO or manifest."""
    def __init__(self, root, *, context=None):
        self.root = root
        self.context = context
        self.writer = Journal(root)

    def authorize(self, scope):
        F.checked(type(self.context) is TrustedReadContext, 'AUTHORIZATION_REQUIRED')
        self.context.authorize(scope)

    @contextmanager
    def view(self, scope, *, gaps=False):
        self.authorize(scope)
        with _ConfinedReader(self.root) as reader:
            store = Journal(reader.root, reader=reader)
            store._allow_event_gaps = gaps
            state = store.read_snapshot()
            F.checked(state['project_id'] == scope.project_id and state.get('synthetic_test_only') is True,
                      'AUTHORIZATION_REQUIRED')
            index = store._last_index
            F.checked(scope in index.policies, 'UNSUPPORTED_CAPABILITY')
            F.checked(index.policies[scope]['raw'] == self.context.policy_raw, 'AUTHORIZATION_REQUIRED')
            yield store, state, index

    def current_boundary(self):
        try:
            F.checked(self.context is not None, 'AUTHORIZATION_REQUIRED')
            with self.view(self.context.scope) as (_, state, index):
                return index.boundary(self.context.scope, state['_head'])
        except READ_FAILURES as exc:
            return failure(exc, E.Operation.INSPECT)

    def validate_boundary(self, expected):
        with self.view(expected.boundary.scope) as (_, _, index):
            index.check_boundary(expected.boundary)

    def locked(self):
        return self.writer._locked()

    def publish(self, staged, batch):
        """Called with shared writer lock held, after current permit verification."""
        expected = staged.transaction.expected; scope = expected.boundary.scope
        with self.view(scope) as (_, state, index):
            index.check_boundary(expected.boundary)
            old = index.batches.get(batch.idempotency_key)
            if old is not None:
                F.checked(old['staged'].transaction.expected == expected and old['batch'] == batch and
                          old['staged'].batch_digest == staged.batch_digest, 'IDEMPOTENCY_CONFLICT')
                return index.receipt(old, duplicate=True)
            F.checked(index.boundary(scope, state['_head']) == expected.boundary, 'VERSION_CONFLICT')
            F.validate_batch(batch, expected, index)
        # All validation precedes publication. Immutable leftovers are orphans.
        for write in batch.evidence:
            F.checked(self.writer.put_blob(T.evidence_bytes(write.content_base64)) == write.evidence_ref.sha256)
        observations = []
        for event in batch.events:
            ref = F.envelope_ref(scope, event)
            F.checked(self.writer.put_blob(canonical(event.to_wire())) == ref.sha256)
            observations.append(ref.to_wire())
        # Reconstruct the original v1 batch from the sealed on-disk objects
        # before publishing its manifest/HEAD, without duplicated payload storage.
        with _ConfinedReader(self.root) as reader:
            sealed_store = Journal(reader.root, reader=reader)
            sealed_writes = tuple(T.EvidenceWrite(evidence_ref=w.evidence_ref,
                content_base64=base64.b64encode(sealed_store.read_blob(w.evidence_ref.sha256)).decode('ascii'))
                for w in batch.evidence)
            sealed_events = tuple(V.EventEnvelope.from_json(sealed_store.read_blob(e.wire_digest()).decode('utf-8'))
                                  for e in batch.events)
            reconstructed = T.CommitBatch(operation_id=batch.operation_id, idempotency_key=batch.idempotency_key,
                                           evidence=sealed_writes, events=sealed_events)
            F.checked(reconstructed == batch and reconstructed.wire_digest() == staged.batch_digest)
        manifest = {'schema': F.MANIFEST_SCHEMA, 'staging_receipt': staged.to_wire(),
                    'operation_id': batch.operation_id, 'idempotency_key': batch.idempotency_key,
                    'evidence_refs': [w.evidence_ref.to_wire() for w in batch.evidence],
                    'observation_refs': observations}
        raw = canonical(manifest)
        F.decode(raw, F.MANIFEST_SCHEMA, manifest.keys())
        digest = self.writer.put_blob(raw)
        self.writer._fault('after_blobs')
        self.writer._fixture_publication = True
        try:
            result = self.writer._publish(state['_head'], state, state, actor='SYNTHETIC_TEST_ONLY',
                events=[{'schema': F.EVENT_SCHEMA, 'type': F.BATCH, 'manifest_sha256': digest}])
        finally:
            self.writer._fixture_publication = False
        with self.view(scope) as (_, _, index):
            row = index.batches[batch.idempotency_key]
            F.checked(row['head']['commit'] == result['commit'])
            return index.receipt(row)

    def bind_synthetic_scope(self):
        """Explicit trusted fixture setup, outside the v1 write API."""
        F.checked(type(self.context) is TrustedReadContext, 'AUTHORIZATION_REQUIRED')
        context = self.context; self.authorize(context.scope)
        F.checked(callable(context.allow_install) and context.allow_install() is True, 'AUTHORIZATION_REQUIRED')
        with self.locked():
            state = self.writer.read_snapshot()
            F.checked(state.get('synthetic_test_only') is True and state['project_id'] == context.scope.project_id and
                      context.scope.instance_id in state['instances'], 'AUTHORIZATION_REQUIRED')
            index = self.writer._last_index
            if context.scope in index.policies:
                F.checked(index.policies[context.scope]['raw'] == context.policy_raw)
                return index.boundary(context.scope, state['_head'])
            digest = self.writer.put_blob(context.policy_raw)
            self.writer._fixture_publication = True
            try:
                self.writer._publish(state['_head'], state, state, actor='SYNTHETIC_TEST_ONLY',
                    events=[{'schema': F.EVENT_SCHEMA, 'type': F.BIND, 'policy_sha256': digest}])
            finally:
                self.writer._fixture_publication = False
        return self.current_boundary()


class EvidenceRepository:
    def __init__(self, storage):
        self.storage = storage

    def read(self, evidence_ref, boundary, *, offset=0, max_bytes=65536):
        try:
            self.storage.authorize(boundary.scope)
            F.checked(type(offset) is int and offset >= 0 and type(max_bytes) is int and
                      1 <= max_bytes <= T.MAX_EVIDENCE_BYTES, 'INVALID_FIELD')
            with self.storage.view(boundary.scope) as (store, _, index):
                sequence = index.check_boundary(boundary)
                registration = index.registrations[boundary.scope].get(evidence_ref)
                F.checked(registration is not None and registration <= sequence, 'NOT_FOUND')
                raw = store.read_blob(evidence_ref.sha256)
                F.checked(offset <= len(raw), 'INVALID_FIELD')
                piece = raw[offset:offset+max_bytes]
                return T.EvidenceSlice(evidence_ref=evidence_ref, boundary=boundary, offset=offset,
                    total_bytes=len(raw), content_base64=base64.b64encode(piece).decode('ascii'), slice_sha256=sha(piece))
        except READ_FAILURES as exc:
            return failure(exc, E.Operation.READ_EVIDENCE, getattr(boundary, 'scope', None))


class EventRepository:
    def __init__(self, storage):
        self.storage = storage

    def read_events(self, cursor, boundary, *, limit=256):
        try:
            self.storage.authorize(boundary.scope)
            F.checked(cursor.scope == boundary.scope and cursor.stream_kind is E.StreamKind.JOURNAL and
                      cursor.stream_id == boundary.journal_id and type(limit) is int and 1 <= limit <= 256 and
                      cursor.after_sequence <= boundary.through_journal_sequence, 'INVALID_CURSOR')
            with self.storage.view(boundary.scope, gaps=True) as (_, _, index):
                index.check_boundary(boundary)
                rows = index.streams[boundary.scope][:boundary.through_journal_sequence]
                if cursor.after_sequence:
                    previous = rows[cursor.after_sequence-1]['raw']
                    F.checked(previous is not None and previous.event_id == cursor.last_event_id, 'INVALID_CURSOR')
                selected = rows[cursor.after_sequence:cursor.after_sequence+limit]
                missing = [cursor.after_sequence+i+1 for i, row in enumerate(selected) if row['raw'] is None]
                if missing:
                    first = last = missing[0]
                    while last+1 in missing:
                        last += 1
                    return V.EventPage(requested_cursor=cursor, next_cursor=cursor, status=E.PageStatus.GAP,
                        events=(), duplicate_event_ids=(), gap=V.EventGap(first_missing_sequence=first,
                            last_missing_sequence=last, reason=E.GapReason.SOURCE_DROPPED,
                            resnapshot_ref=boundary.commit_ref))
                F.checked(all(row['event'] is not None for row in selected), 'UNOBSERVED')
                events = tuple(row['event'] for row in selected)
                next_cursor = (replace(cursor, after_sequence=events[-1].journal_sequence,
                    last_event_id=events[-1].event_id) if events else cursor)
                return V.EventPage(requested_cursor=cursor, next_cursor=next_cursor,
                    status=E.PageStatus.COMPLETE if events else E.PageStatus.EMPTY,
                    events=events, duplicate_event_ids=(), gap=None)
        except READ_FAILURES as exc:
            return failure(exc, E.Operation.READ_EVENTS, getattr(boundary, 'scope', None))

    def verify_event(self, event, boundary):
        try:
            with self.storage.view(boundary.scope) as (_, _, index):
                index.check_boundary(boundary)
                rows = index.streams[boundary.scope][:boundary.through_journal_sequence]
                F.checked(any(row['event'] == event for row in rows), 'UNTRUSTED_EVENT')
                return T.EventVerification(event_id=event.event_id, boundary=boundary, verified=True)
        except READ_FAILURES as exc:
            error = failure(exc, E.Operation.ACCEPT_EVENT, getattr(boundary, 'scope', None))
            if error.code is E.ErrorCode.AUTHORIZATION_REQUIRED:
                return error
            return C.port_error(E.ErrorCode.UNTRUSTED_EVENT, E.Operation.ACCEPT_EVENT,
                                scope=getattr(boundary, 'scope', None))
