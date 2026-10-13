"""Raw observation and committed event identities, bounded cursors and gaps."""
from __future__ import annotations

from typing import Literal

from . import enums as E
from .core import ExactRef, ObservedIdentifier, Scope, TimePoint
from .wire import DTO, frozen_dto, identifier, nonnegative, require


@frozen_dto
class EventEnvelope(DTO):
    event_id: str
    event_type: str
    event_domain: E.EventDomain
    status: E.EventStatus
    project_id: str
    instance_id: str
    journal_id: ObservedIdentifier
    aggregate_id: str
    aggregate_sequence: int | None
    journal_sequence: int | None
    commit_ref: ExactRef | None
    occurred_at: TimePoint | None
    observed_at: TimePoint
    committed_at: TimePoint | None
    clock_source: E.ClockSource
    actor_principal_ref: ExactRef | None
    actor_kind: Literal["HUMAN", "MODEL", "ADAPTER", "APPLICATION", "SYNTHETIC"]
    correlation_id: str
    causation_id: str | None
    operation_id: str | None
    idempotency_key: str | None
    invocation_id: str | None
    execution_id: str | None
    request_id: str | None
    attempt_id: str | None
    activation_id: str | None
    logical_main_id: str | None
    owner_epoch: int | None
    control_version: int | None
    backend_id: ObservedIdentifier
    provider_id: ObservedIdentifier
    provider_request_id: ObservedIdentifier
    backend_binding_ref: ExactRef | None
    payload_ref: ExactRef
    raw_evidence_ref: ExactRef
    payload_sha256: str
    classification: E.Classification
    trust_origin: E.TrustOrigin
    visibility_policy_ref: ExactRef

    def scope(self) -> Scope:
        return Scope(project_id=self.project_id, instance_id=self.instance_id)

    def _validate(self) -> None:
        for value in (self.event_id, self.event_type, self.project_id, self.instance_id,
                      self.aggregate_id, self.correlation_id):
            identifier(value)
        for value in (self.causation_id, self.operation_id, self.idempotency_key, self.invocation_id,
                      self.execution_id, self.request_id, self.attempt_id, self.activation_id,
                      self.logical_main_id):
            if value is not None:
                identifier(value)
        for value in (self.owner_epoch, self.aggregate_sequence, self.journal_sequence):
            require(value is None or value >= 1, "Known event sequence/epoch must be positive.")
        if self.control_version is not None:
            nonnegative(self.control_version)
        require(self.payload_sha256 == self.payload_ref.sha256, "Payload digest and exact reference disagree.")
        require(all(ref is None or ref.project_id == self.project_id for ref in
                    (self.commit_ref, self.actor_principal_ref, self.backend_binding_ref,
                     self.payload_ref, self.raw_evidence_ref, self.visibility_policy_ref)),
                "Event references cross the project boundary.")
        if self.status is E.EventStatus.COMMITTED:
            require(self.journal_id.kind is E.ObservationKind.OBSERVED
                    and self.journal_sequence is not None and self.aggregate_sequence is not None
                    and self.commit_ref is not None and self.committed_at is not None,
                    "Committed events require exact journal, sequence, commit and commit-time identity.")
            require(self.trust_origin in (E.TrustOrigin.AUTHENTICATED_APPLICATION,
                                          E.TrustOrigin.SYNTHETIC_TEST_ONLY)
                    and self.actor_kind in ("APPLICATION", "SYNTHETIC"),
                    "External logs/model proposals cannot claim committed authority.")
        else:
            require(self.journal_sequence is None and self.commit_ref is None and self.committed_at is None,
                    "Observation envelopes do not carry authoritative commit metadata.")


@frozen_dto
class EventCursor(DTO):
    scope: Scope
    stream_kind: E.StreamKind
    stream_id: str
    after_sequence: int
    last_event_id: str | None

    def _validate(self) -> None:
        identifier(self.stream_id)
        nonnegative(self.after_sequence)
        require((self.after_sequence == 0) == (self.last_event_id is None),
                "A nonzero cursor must bind the preceding event identity.")
        if self.last_event_id is not None:
            identifier(self.last_event_id)


@frozen_dto
class EventGap(DTO):
    first_missing_sequence: int
    last_missing_sequence: int
    reason: E.GapReason
    resnapshot_ref: ExactRef | None

    def _validate(self) -> None:
        require(1 <= self.first_missing_sequence <= self.last_missing_sequence,
                "Gap range must identify an actual missing interval.")


@frozen_dto
class RunnerEvent(DTO):
    sequence: int
    kind: E.RunnerEventKind
    envelope: EventEnvelope
    raw_event_ref: ExactRef

    def _validate(self) -> None:
        require(self.sequence >= 1, "Runner stream sequence must be positive.")
        require(self.envelope.status is E.EventStatus.OBSERVATION
                and self.envelope.event_domain in (E.EventDomain.EXECUTION, E.EventDomain.METERING),
                "Runner events are observations, not scientific acceptance.")
        require(self.raw_event_ref == self.envelope.raw_evidence_ref,
                "Raw runner event identity differs from its envelope.")
        require(all(x is not None for x in (self.envelope.invocation_id, self.envelope.execution_id,
                                           self.envelope.request_id, self.envelope.attempt_id)),
                "Runner events require complete invocation identity.")


@frozen_dto
class ProviderEvent(DTO):
    sequence: int
    inference_id: str
    kind: E.ProviderEventKind
    envelope: EventEnvelope
    raw_event_ref: ExactRef
    actual_model_id: ObservedIdentifier

    def _validate(self) -> None:
        require(self.sequence >= 1, "Provider stream sequence must be positive.")
        identifier(self.inference_id)
        require(self.envelope.status is E.EventStatus.OBSERVATION
                and self.envelope.event_domain in (E.EventDomain.EXECUTION, E.EventDomain.METERING),
                "Provider events cannot confer scientific or commit authority.")
        require(self.raw_event_ref == self.envelope.raw_evidence_ref,
                "Raw provider event identity differs from its envelope.")


def _page_invariants(page, kind: E.StreamKind) -> None:
    before, after = page.requested_cursor, page.next_cursor
    require(before.scope == after.scope and before.stream_id == after.stream_id
            and before.stream_kind is kind and after.stream_kind is kind,
            "A page cannot change cursor scope or stream.")
    require(after.after_sequence >= before.after_sequence, "Cursor cannot move backwards.")
    if page.status is E.PageStatus.GAP:
        require(page.gap is not None and not page.events and after == before,
                "A gap requires explicit metadata and cannot silently advance the cursor.")
        require(page.gap.first_missing_sequence > before.after_sequence,
                "Reported gap must follow the requested cursor.")
    elif page.status is E.PageStatus.EMPTY:
        require(page.gap is None and not page.events and before == after,
                "Empty pages must preserve the cursor and cannot conceal a gap.")
    else:
        require(page.gap is None and bool(page.events), "Complete page requires events, not a gap.")
        expected = before.after_sequence + 1
        for item in page.events:
            envelope = item if kind is E.StreamKind.JOURNAL else item.envelope
            sequence = envelope.journal_sequence if kind is E.StreamKind.JOURNAL else item.sequence
            require(sequence == expected and envelope.scope() == before.scope,
                    "Page sequence or scope is discontinuous; return GAP instead.")
            if kind is E.StreamKind.JOURNAL:
                require(envelope.status is E.EventStatus.COMMITTED
                        and envelope.journal_id.value == before.stream_id,
                        "Journal pages require committed events from the exact journal.")
            elif kind is E.StreamKind.RUNNER:
                require(envelope.invocation_id == before.stream_id,
                        "Runner page event belongs to another invocation stream.")
            elif kind is E.StreamKind.PROVIDER:
                require(item.inference_id == before.stream_id,
                        "Provider page event belongs to another inference stream.")
            expected += 1
        last = page.events[-1] if kind is E.StreamKind.JOURNAL else page.events[-1].envelope
        require(after.after_sequence == expected - 1 and after.last_event_id == last.event_id,
                "Next cursor does not identify the last returned event.")
    require(len(set(page.duplicate_event_ids)) == len(page.duplicate_event_ids),
            "Duplicate-event observation IDs must be unique.")
    for event_id in page.duplicate_event_ids:
        identifier(event_id)


@frozen_dto
class EventPage(DTO):
    requested_cursor: EventCursor
    next_cursor: EventCursor
    status: E.PageStatus
    events: tuple[EventEnvelope, ...]
    duplicate_event_ids: tuple[str, ...]
    gap: EventGap | None

    def _validate(self) -> None:
        _page_invariants(self, E.StreamKind.JOURNAL)


@frozen_dto
class RunnerEventPage(DTO):
    requested_cursor: EventCursor
    next_cursor: EventCursor
    status: E.PageStatus
    events: tuple[RunnerEvent, ...]
    duplicate_event_ids: tuple[str, ...]
    gap: EventGap | None

    def _validate(self) -> None:
        _page_invariants(self, E.StreamKind.RUNNER)


@frozen_dto
class ProviderEventPage(DTO):
    requested_cursor: EventCursor
    next_cursor: EventCursor
    status: E.PageStatus
    events: tuple[ProviderEvent, ...]
    duplicate_event_ids: tuple[str, ...]
    gap: EventGap | None

    def _validate(self) -> None:
        _page_invariants(self, E.StreamKind.PROVIDER)
