"""Closed synthetic observation extension over the single native journal.

This module validates identities and published closure, not human authority.
Only the out-of-band assembly may authorize access or install a fixture policy.
"""
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import base64

from pmrh.domain.primitives import canonical, loads, require, sha, PMRSError
from pmrh.ports.dto import core as C, enums as E, events as V, storage as T
from pmrh.ports.dto.wire import ContractViolation, MAX_JSON_BYTES, MAX_TUPLE_ITEMS, _wire_budget, identifier
from .native_format import COMMIT_SCHEMA
from .io import _ConfinedReader

EXTENDED_SCHEMA = 'pmrh.commit/1'
EVENT_SCHEMA = 'pmrh.storage-event/1'
POLICY_SCHEMA = 'pmrh.storage-visibility/1'
MANIFEST_SCHEMA = 'pmrh.storage-batch/1'
BIND = 'PMRH_PORT_SCOPE_BOUND'
BATCH = 'PMRH_PORT_BATCH_COMMITTED'
DELTA_FIELDS = ('knowledge_delta_ref', 'control_delta_ref', 'report_delta_ref', 'registry_delta_ref')


def checked(condition, code='CORRUPT_CAPTURE'):
    require(condition, code, 'Storage contract validation failed')


def exact(project, object_id, digest):
    return C.ExactRef(project_id=project, object_id=object_id, revision='sha256:'+digest, sha256=digest)


def commit_ref(project, head):
    return exact(project, 'journal:'+project, head['commit'])


def policy_bytes(scope):
    return canonical({'schema': POLICY_SCHEMA, 'scope': scope.to_wire(),
                      'profile': 'SYNTHETIC_TEST_ONLY', 'read_rule': 'EXPLICIT_SCOPE_REGISTRATION',
                      'classification': 'SYNTHETIC_TEST_ONLY'})


def policy_ref(scope, digest):
    return exact(scope.project_id, 'visibility:'+scope.instance_id, digest)


def envelope_ref(scope, event):
    return exact(scope.project_id, 'observation:'+sha(event.event_id.encode()), event.wire_digest())


def stream_id(scope, ref):
    return 'ports-observations/1:'+sha(canonical([scope.project_id, scope.instance_id, ref.to_wire()]))


def journal_time(entry):
    value = datetime.fromisoformat(entry['at'].replace('Z', '+00:00'))
    checked(value.tzinfo is not None)
    return C.TimePoint(utc=value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z'),
                       clock_source=E.ClockSource.JOURNAL)


def decode(raw, schema, fields):
    checked(len(raw) <= MAX_JSON_BYTES)
    value = loads(raw, maximum=MAX_JSON_BYTES)
    _wire_budget(value, wire=True)
    checked(type(value) is dict and set(value) == set(fields))
    checked(value['schema'] == schema, 'UNSUPPORTED_SCHEMA_VERSION')
    checked(canonical(value) == raw)
    return value


def validate_entry(entry):
    checked(type(entry['events']) is list, 'JOURNAL_INVALID')
    checked(type(entry['sequence']) is int and entry['sequence'] >= 1, 'JOURNAL_INVALID')
    for event in entry['events']:
        checked(type(event) is dict, 'JOURNAL_INVALID')
        kind = event.get('type')
        if (isinstance(kind, str) and kind.startswith('PMRH_PORT_') or
                isinstance(event.get('schema'), str) and event['schema'].startswith('pmrh.storage-event/')):
            checked(entry['schema'] == EXTENDED_SCHEMA, 'JOURNAL_INVALID')
            checked(kind in (BIND, BATCH), 'UNSUPPORTED_SCHEMA_VERSION')
            key = 'policy_sha256' if kind == BIND else 'manifest_sha256'
            checked(set(event) == {'schema', 'type', key}, 'JOURNAL_INVALID')
            checked(event['schema'] == EVENT_SCHEMA, 'UNSUPPORTED_SCHEMA_VERSION')
            digest = event[key]
            checked(type(digest) is str and len(digest) == 64 and
                    all(c in '0123456789abcdef' for c in digest), 'JOURNAL_INVALID')
            checked(entry['actor'] == 'SYNTHETIC_TEST_ONLY', 'JOURNAL_INVALID')
            checked(entry['previous_commit'] is not None and
                    entry['base_knowledge_commit'] == entry['previous_commit']['commit'], 'JOURNAL_INVALID')
            checked(not any(entry[f] for f in DELTA_FIELDS) and not entry['accepted_request_bindings'],
                    'JOURNAL_INVALID')


def publication_schema(store, previous, events):
    from .control_fast import publication_schema as fast_publication_schema
    combined = fast_publication_schema(store, previous, events)
    if combined is not None:
        return combined
    control = previous is not None and store._commit_record(previous)['schema'] == 'pmrh.commit/2'
    proposed_control = any(e.get('schema') == 'pmrh.control-event/1' for e in events)
    if control or proposed_control:
        checked(not any(e.get('type') in (BIND, BATCH) for e in events), 'UNSUPPORTED_CAPABILITY')
        checked(getattr(store, '_control_publication', None) is not None, 'AUTHORIZATION_REQUIRED')
        checked(len(events) == 1 and proposed_control and not getattr(store, '_fixture_publication', False), 'UNSUPPORTED_CAPABILITY')
        checked(previous is not None and store._commit_record(previous)['schema'] != EXTENDED_SCHEMA, 'UNSUPPORTED_CAPABILITY')
        return 'pmrh.commit/2'
    extended = previous is not None and store._commit_record(previous)['schema'] == EXTENDED_SCHEMA
    port = any(e.get('type') in (BIND, BATCH) for e in events)
    if port:
        checked(getattr(store, '_fixture_publication', False), 'AUTHORIZATION_REQUIRED')
    return EXTENDED_SCHEMA if extended or port else COMMIT_SCHEMA


def validate_batch(batch, expected, index):
    """Closed raw-observation subset; no science/control/dispatch reducer."""
    batch.to_wire()  # Reapply the complete aggregate bound.
    scope = expected.boundary.scope
    checked(expected.boundary.visibility_policy_ref == index.policies[scope]['ref'])
    available = set(index.registrations.get(scope, {}))
    for write in batch.evidence:
        ref = write.evidence_ref
        checked(ref.project_id == scope.project_id, 'AUTHORIZATION_REQUIRED')
        checked(ref.object_id.startswith(('raw-evidence:', 'synthetic:')), 'INVALID_FIELD')
        key = (ref.project_id, ref.object_id, ref.revision)
        checked(index.identities.get(key, ref.sha256) == ref.sha256, 'IDEMPOTENCY_CONFLICT')
        T.evidence_bytes(write.content_base64)
        available.add(ref)
    for event in batch.events:
        checked(event.event_id not in index.event_ids, 'IDEMPOTENCY_CONFLICT')
        checked(event.scope() == scope and event.visibility_policy_ref == expected.boundary.visibility_policy_ref,
                'AUTHORIZATION_REQUIRED')
        checked(event.event_domain is E.EventDomain.DIAGNOSTIC and event.event_type == 'EVIDENCE_RECORDED',
                'UNSUPPORTED_CAPABILITY')
        checked(event.status is E.EventStatus.OBSERVATION and event.aggregate_sequence is None and
                event.journal_sequence is None and event.commit_ref is None and event.committed_at is None and
                event.journal_id.kind is not E.ObservationKind.OBSERVED, 'UNTRUSTED_EVENT')
        checked(event.operation_id == batch.operation_id and event.idempotency_key == batch.idempotency_key,
                'IDEMPOTENCY_CONFLICT')
        checked(event.owner_epoch in (None, expected.owner_epoch) and
                event.control_version in (None, expected.expected_control_version), 'STALE_CONTROL_VERSION')
        checked(all(getattr(event, name) is None for name in
                    ('invocation_id', 'execution_id', 'request_id', 'attempt_id', 'activation_id',
                     'logical_main_id', 'backend_binding_ref', 'actor_principal_ref')), 'UNTRUSTED_EVENT')
        checked(all(getattr(event, name).kind is not E.ObservationKind.OBSERVED for name in
                    ('backend_id', 'provider_id', 'provider_request_id')), 'UNTRUSTED_EVENT')
        checked(event.actor_kind in ('MODEL', 'ADAPTER', 'SYNTHETIC') and
                event.trust_origin in (E.TrustOrigin.EXTERNAL_OBSERVATION, E.TrustOrigin.MODEL_PROPOSAL,
                                       E.TrustOrigin.SYNTHETIC_TEST_ONLY) and
                event.classification is E.Classification.SYNTHETIC_TEST_ONLY, 'UNTRUSTED_EVENT')
        checked(event.payload_ref in available and event.raw_evidence_ref in available, 'NOT_FOUND')


@dataclass
class Index:
    project: str
    heads: dict = field(default_factory=dict)
    policies: dict = field(default_factory=dict)
    registrations: dict = field(default_factory=dict)
    identities: dict = field(default_factory=dict)
    streams: dict = field(default_factory=dict)
    batches: dict = field(default_factory=dict)
    event_ids: set = field(default_factory=set)
    envelope_ids: set = field(default_factory=set)
    transaction_ids: set = field(default_factory=set)
    closure: set = field(default_factory=set)
    counts: dict = field(default_factory=dict)

    def boundary(self, scope, head):
        checked(scope in self.policies, 'UNSUPPORTED_CAPABILITY')
        digest = head['commit'] if isinstance(head, dict) else head
        checked(digest in self.heads, 'NOT_FOUND')
        selected = self.heads[digest]
        binding = self.policies[scope]
        checked(selected['sequence'] >= binding['sequence'], 'NOT_FOUND')
        ref = binding['ref']
        return T.ReadBoundary(scope=scope, journal_id=stream_id(scope, ref),
                              commit_ref=commit_ref(self.project, selected),
                              through_journal_sequence=self.counts[digest].get(scope, 0),
                              visibility_policy_ref=ref)

    def check_boundary(self, boundary):
        checked(boundary == self.boundary(boundary.scope, boundary.commit_ref.sha256), 'NOT_FOUND')
        return self.heads[boundary.commit_ref.sha256]['sequence']

    def receipt(self, row, *, duplicate=False):
        staged = row['staged']
        batch = row['batch']
        checked(batch is not None, 'UNOBSERVED')
        return T.CommitReceipt(operation_id=batch.operation_id, batch_digest=staged.batch_digest,
            previous_boundary=staged.transaction.expected.boundary,
            boundary=self.boundary(staged.transaction.expected.boundary.scope, row['head']),
            duplicate_status=E.DuplicateStatus.EXACT_DUPLICATE if duplicate else E.DuplicateStatus.NEW,
            committed_at=journal_time(row['entry']), event_ids=tuple(e.event_id for e in batch.events))


def scan(store, history, apply_delta, *, allow_missing_envelopes=False):
    """Verify full extended ancestry independent of native checkpoint shortcuts.

    Missing envelopes may establish a GAP only in a confined event read. Such
    an incomplete index cannot certify receipts, ordinary evidence or writes.
    """
    marker = store._marker()
    index = Index(marker['project_id'])
    if not any(entry['schema'] == EXTENDED_SCHEMA for _, entry in history):
        return index
    if store._reader is None:
        with _ConfinedReader(store.root) as reader:
            confined = type(store)(reader.root, reader=reader)
            for head, entry in history:
                checked(confined._commit_record(head) == entry)
            return scan(confined, history, apply_delta, allow_missing_envelopes=allow_missing_envelopes)
    checked(marker.get('synthetic_test_only') is True, 'AUTHORIZATION_REQUIRED')
    state, aggregates = {}, {}
    for head, entry in history:
        index.heads[head['commit']] = head
        if entry['schema'] == EXTENDED_SCHEMA:
            journal_time(entry)
        for f in DELTA_FIELDS:
            if entry[f]:
                apply_delta(state, loads(store.read_blob(entry[f])))
        checked(state.get('project_id') == index.project and state.get('synthetic_test_only') is True)
        for ordinal, event in enumerate(entry['events']):
            kind = event.get('type')
            if kind == BIND:
                digest = event['policy_sha256']; raw = store._read_blob(digest, MAX_JSON_BYTES)
                value = decode(raw, POLICY_SCHEMA, ('schema', 'scope', 'profile', 'read_rule', 'classification'))
                scope = C.Scope.from_wire(value['scope'])
                checked(scope.project_id == index.project and scope.instance_id in state.get('instances', {}))
                checked(raw == policy_bytes(scope) and scope not in index.policies)
                ref = policy_ref(scope, digest)
                index.policies[scope] = {'ref': ref, 'raw': raw, 'sequence': head['sequence']}
                index.registrations[scope] = {ref: head['sequence']}
                index.streams[scope] = []
                index.closure.add(digest)
            elif kind == BATCH:
                digest = event['manifest_sha256']; raw = store._read_blob(digest, MAX_JSON_BYTES)
                manifest = decode(raw, MANIFEST_SCHEMA, ('schema', 'staging_receipt', 'operation_id',
                                  'idempotency_key', 'evidence_refs', 'observation_refs'))
                identifier(manifest['operation_id']); identifier(manifest['idempotency_key'])
                staged = T.StagingReceipt.from_wire(manifest['staging_receipt'])
                checked(staged.transaction.transaction_id not in index.transaction_ids)
                index.transaction_ids.add(staged.transaction.transaction_id)
                expected = staged.transaction.expected; scope = expected.boundary.scope
                checked(scope in index.policies)
                checked(entry['previous_commit'] is not None)
                checked(expected.boundary == index.boundary(scope, entry['previous_commit']))
                checked(type(manifest['evidence_refs']) is list and type(manifest['observation_refs']) is list and
                        len(manifest['evidence_refs']) <= MAX_TUPLE_ITEMS and len(manifest['observation_refs']) <= MAX_TUPLE_ITEMS)
                writes, observations, refs = [], [], []
                for wire in manifest['evidence_refs']:
                    ref = C.ExactRef.from_wire(wire)
                    data = store._read_blob(ref.sha256, T.MAX_EVIDENCE_BYTES)
                    writes.append(T.EvidenceWrite(evidence_ref=ref, content_base64=base64.b64encode(data).decode('ascii')))
                    index.closure.add(ref.sha256)
                for wire in manifest['observation_refs']:
                    ref = C.ExactRef.from_wire(wire); refs.append(ref)
                    checked(ref.object_id not in index.envelope_ids)
                    index.envelope_ids.add(ref.object_id)
                    checked(ref.project_id == scope.project_id and ref.revision == 'sha256:'+ref.sha256 and
                            ref.object_id.startswith('observation:'))
                    try:
                        data = store._read_blob(ref.sha256, MAX_JSON_BYTES)
                    except (FileNotFoundError, PMRSError) as exc:
                        if not allow_missing_envelopes or isinstance(exc, PMRSError) and exc.code != 'FILE_UNAVAILABLE':
                            raise
                        observations.append(None)
                    else:
                        observation = V.EventEnvelope.from_json(data.decode('utf-8'))
                        checked(data == canonical(observation.to_wire()) and ref == envelope_ref(scope, observation))
                        observations.append(observation)
                    index.closure.add(ref.sha256)
                missing = any(e is None for e in observations)
                batch = None if missing else T.CommitBatch(operation_id=manifest['operation_id'],
                    idempotency_key=manifest['idempotency_key'], evidence=tuple(writes), events=tuple(observations))
                if batch is not None:
                    checked(batch.wire_digest() == staged.batch_digest)
                    validate_batch(batch, expected, index)
                else:
                    # Validate every still-observable field; never certify a partial batch digest.
                    known = tuple(e for e in observations if e is not None)
                    if writes or known:
                        partial = T.CommitBatch(operation_id=manifest['operation_id'], idempotency_key=manifest['idempotency_key'],
                                                evidence=tuple(writes), events=known)
                        validate_batch(partial, expected, index)
                key = manifest['idempotency_key']
                checked(type(key) is str and key not in index.batches)
                index.batches[key] = {'staged': staged, 'batch': batch, 'head': head, 'entry': entry,
                                      'manifest': manifest, 'ordinal': ordinal}
                for write in writes:
                    ref = write.evidence_ref
                    identity = (ref.project_id, ref.object_id, ref.revision)
                    checked(index.identities.get(identity, ref.sha256) == ref.sha256)
                    index.identities[identity] = ref.sha256
                    index.registrations[scope].setdefault(ref, head['sequence'])
                for position, (observation, ref) in enumerate(zip(observations, refs)):
                    rows = index.streams[scope]
                    published = None
                    if observation is not None:
                        checked(observation.event_id not in index.event_ids)
                        index.event_ids.add(observation.event_id)
                        aggregate = (scope, observation.aggregate_id)
                        aggregates[aggregate] = aggregates.get(aggregate, 0) + 1
                        # Earlier unavailable attribution prevents a trustworthy aggregate count.
                        if not any(row['raw'] is None for row in rows):
                            published = replace(observation, status=E.EventStatus.COMMITTED,
                                journal_id=C.ObservedIdentifier(kind=E.ObservationKind.OBSERVED,
                                    value=stream_id(scope, index.policies[scope]['ref'])),
                                journal_sequence=len(rows)+1, aggregate_sequence=aggregates[aggregate],
                                commit_ref=commit_ref(index.project, head), committed_at=journal_time(entry),
                                actor_kind='SYNTHETIC', trust_origin=E.TrustOrigin.SYNTHETIC_TEST_ONLY)
                    rows.append({'raw': observation, 'event': published, 'head': head,
                                 'event_ordinal': ordinal, 'manifest_ordinal': position, 'ref': ref})
                    index.registrations[scope].setdefault(ref, head['sequence'])
                index.closure.add(digest)
        index.counts[head['commit']] = {scope: len(rows) for scope, rows in index.streams.items()}
    return index
