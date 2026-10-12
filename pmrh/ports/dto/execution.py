"""Runner/provider results: dispatch ambiguity, guidance, capture and usage."""
from __future__ import annotations

from typing import Literal

from . import enums as E
from .core import ErrorEnvelope, ExactRef, InvocationIdentity, ObservedIdentifier, Quantity, TimePoint
from .specs import AgentInvocationSpec
from .wire import DTO, frozen_dto, identifier, require


@frozen_dto
class PreparedInvocation(DTO):
    prepared_id: str
    spec: AgentInvocationSpec
    spec_digest: str
    prepared_at: TimePoint
    preparation_effect: E.PreparationEffect
    local_preparation_refs: tuple[ExactRef, ...]

    def _validate(self) -> None:
        identifier(self.prepared_id)
        require(self.spec_digest == self.spec.wire_digest(), "Prepared request digest does not match its spec.")
        if self.preparation_effect is E.PreparationEffect.LOCAL_STAGING:
            require(bool(self.local_preparation_refs), "Declared local staging needs preparation receipts.")


@frozen_dto
class InvocationHandle(DTO):
    identity: InvocationIdentity
    backend_binding_ref: ExactRef
    backend_invocation_id: ObservedIdentifier

    def _validate(self) -> None:
        require(self.backend_binding_ref.project_id == self.identity.scope.project_id,
                "Backend binding crosses the invocation project.")


@frozen_dto
class DispatchReceipt(DTO):
    status: E.DispatchState
    handle: InvocationHandle
    observed_at: TimePoint
    raw_evidence_refs: tuple[ExactRef, ...]
    error: ErrorEnvelope | None

    def _validate(self) -> None:
        if self.status is E.DispatchState.SENT:
            require(bool(self.raw_evidence_refs) and self.error is None,
                    "SENT requires a confirming receipt and no send error.")
        else:
            code = (E.ErrorCode.NOT_SENT if self.status is E.DispatchState.NOT_SENT
                    else E.ErrorCode.SEND_OUTCOME_UNKNOWN)
            require(self.error is not None and self.error.code is code
                    and self.error.identity == self.handle.identity,
                    "Dispatch uncertainty must retain matching error and invocation identity.")
            if self.status is E.DispatchState.NOT_SENT:
                require(bool(self.raw_evidence_refs) and self.raw_evidence_refs == self.error.raw_evidence_refs,
                        "NOT_SENT requires identical confirming evidence, not a guess.")


@frozen_dto
class ExecutionObservation(DTO):
    identity: InvocationIdentity
    state: E.ExecutionState
    observed_at: TimePoint
    raw_evidence_refs: tuple[ExactRef, ...]
    actual_model_id: ObservedIdentifier
    provider_request_id: ObservedIdentifier

    def _validate(self) -> None:
        if self.state not in (E.ExecutionState.UNOBSERVED, E.ExecutionState.UNKNOWN):
            require(bool(self.raw_evidence_refs), "Observed execution state requires raw evidence.")


@frozen_dto
class SteeringMessage(DTO):
    message_id: str
    content_ref: ExactRef
    kind: E.GuidanceKind
    idempotency_key: str

    def _validate(self) -> None:
        identifier(self.message_id)
        identifier(self.idempotency_key)


@frozen_dto
class SteeringReceipt(DTO):
    identity: InvocationIdentity
    message_id: str
    status: E.GuidanceStatus
    evidence_refs: tuple[ExactRef, ...]
    consumer_confirmation_ref: ExactRef | None

    def _validate(self) -> None:
        identifier(self.message_id)
        require(bool(self.evidence_refs), "Guidance status requires actual evidence.")
        if self.status not in (E.GuidanceStatus.SAVED, E.GuidanceStatus.DELIVERED):
            require(self.consumer_confirmation_ref is not None,
                    "Delivery alone cannot establish read, considered or adopted status.")


@frozen_dto
class CancellationReceipt(DTO):
    identity: InvocationIdentity
    request_status: E.CancelStatus
    termination: E.ObservationKind
    request_evidence_refs: tuple[ExactRef, ...]
    termination_evidence_refs: tuple[ExactRef, ...]

    def _validate(self) -> None:
        if self.request_status in (E.CancelStatus.REQUEST_ACKNOWLEDGED, E.CancelStatus.REQUEST_NOT_SENT):
            require(bool(self.request_evidence_refs), "Known cancellation request status needs evidence.")
        require((self.termination is E.ObservationKind.OBSERVED) == bool(self.termination_evidence_refs),
                "Cancellation acknowledgement is not evidence of termination.")
        require(self.termination is not E.ObservationKind.NOT_APPLICABLE,
                "Execution termination must be observed or unobserved.")


@frozen_dto
class CaptureReceipt(DTO):
    capture_id: str
    identity: InvocationIdentity
    raw_output_ref: ExactRef
    actual_input_manifest_ref: ExactRef
    raw_event_refs: tuple[ExactRef, ...]
    sealed_at: TimePoint
    qualification: Literal["RAW_CAPTURE_ONLY"] = "RAW_CAPTURE_ONLY"

    def _validate(self) -> None:
        identifier(self.capture_id)
        require(bool(self.raw_event_refs), "A capture needs original event evidence.")
        require(all(ref.project_id == self.identity.scope.project_id for ref in
                    (self.raw_output_ref, self.actual_input_manifest_ref, *self.raw_event_refs)),
                "Capture references cross the invocation project.")


@frozen_dto
class RecoveryEvidence(DTO):
    identity: InvocationIdentity
    mode: E.RecoveryMode
    raw_evidence_refs: tuple[ExactRef, ...]
    original_capture: CaptureReceipt | None

    def _validate(self) -> None:
        if self.original_capture is not None:
            require(self.original_capture.identity == self.identity,
                    "Recovery must retain the original invocation identity.")
        if self.mode is E.RecoveryMode.READ_ORIGINAL_CAPTURE:
            require(self.original_capture is not None, "Original-capture recovery needs a capture receipt.")


@frozen_dto
class RecoveryReceipt(DTO):
    handle: InvocationHandle
    observation: ExecutionObservation
    capture: CaptureReceipt | None
    error: ErrorEnvelope | None
    external_resend: Literal[False] = False

    def _validate(self) -> None:
        require(self.observation.identity == self.handle.identity, "Recovery observation identity changed.")
        if self.capture is not None:
            require(self.capture.identity == self.handle.identity, "Recovery capture identity changed.")
        if self.error is not None:
            require(self.error.identity == self.handle.identity, "Recovery error identity changed.")


@frozen_dto
class UsageDatum(DTO):
    metric: E.UsageMetric
    quantity: Quantity


@frozen_dto
class UsageObservation(DTO):
    identity: InvocationIdentity
    execution_mode: E.ExecutionMode
    coverage: E.UsageCoverage
    observed_at: TimePoint
    raw_evidence_refs: tuple[ExactRef, ...]
    values: tuple[UsageDatum, ...]
    parent_usage_ref: ExactRef | None
    inclusion: E.UsageInclusion

    def _validate(self) -> None:
        require(len({v.metric for v in self.values}) == len(self.values), "Usage metric occurs twice.")
        if any(v.quantity.kind is E.ObservationKind.OBSERVED for v in self.values):
            require(bool(self.raw_evidence_refs) and self.coverage is not E.UsageCoverage.NONE,
                    "Measured usage, including zero, needs raw coverage evidence.")
        if self.inclusion is E.UsageInclusion.INCLUDED_IN_PARENT:
            require(self.parent_usage_ref is not None, "Included usage needs an exact parent reference.")
        if self.coverage is not E.UsageCoverage.INFERENCE_LEVEL:
            require(all(v.quantity.kind is not E.ObservationKind.OBSERVED for v in self.values
                        if v.metric is E.UsageMetric.INFERENCE_REQUESTS),
                    "Aggregate/opaque usage cannot claim an observed internal inference count.")


@frozen_dto
class RawUsageEvidence(DTO):
    """Only raw immutable evidence identity; the provider parses its own capture."""
    identity: InvocationIdentity
    evidence_ref: ExactRef
    normalizer_version: str

    def _validate(self) -> None:
        identifier(self.normalizer_version)
        require(self.evidence_ref.project_id == self.identity.scope.project_id,
                "Usage evidence crosses the invocation project.")
