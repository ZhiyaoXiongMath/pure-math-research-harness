"""Public synchronous Ports, contract version 1.0.

Adapters must normalize failures into ErrorEnvelope, including stream failures.
No generic retry policy is implicit. Protocol conformance checks method shape,
not backend capability, authorization, mathematical validity or durability.
"""
from __future__ import annotations

from typing import Iterator, Protocol, runtime_checkable

from .dto.capability import CapabilityManifest
from .dto.control import AuthorizationDecision, OperationIntent, OperationPermit, PermitVerification
from .dto.core import ErrorEnvelope, ExactRef, TimePoint
from .dto.events import EventCursor, EventEnvelope, EventPage, ProviderEvent, RunnerEventPage
from .dto.execution import (
    CancellationReceipt, CaptureReceipt, DispatchReceipt, ExecutionObservation,
    InvocationHandle, PreparedInvocation, RawUsageEvidence, RecoveryEvidence,
    RecoveryReceipt, SteeringMessage, SteeringReceipt, UsageObservation,
)
from .dto.orchestration import (
    ActionPlan, ActionRequest, EngineCheckpoint, EventAcceptance, QuiesceReceipt, QuiesceRequest,
)
from .dto.specs import AgentInvocationSpec, InferenceSpec, ModelDescription, ModelSelection, RequestValidation
from .dto.storage import (
    CommitBatch, CommitReceipt, EvidenceSlice, EventVerification, ReadBoundary,
    RollbackReceipt, StagingReceipt, TransactionHandle, VersionExpectation,
)


@runtime_checkable
class AgentRunner(Protocol):
    def describe_capabilities(self) -> CapabilityManifest: ...
    def prepare(self, spec: AgentInvocationSpec) -> PreparedInvocation | ErrorEnvelope:
        """Declared local preparation only; never starts inference."""
        ...
    def start(self, prepared: PreparedInvocation, permit: OperationPermit | None) -> DispatchReceipt | ErrorEnvelope: ...
    def events(self, handle: InvocationHandle, cursor: EventCursor) -> RunnerEventPage | ErrorEnvelope: ...
    def inspect(self, handle: InvocationHandle) -> ExecutionObservation | ErrorEnvelope:
        """Read existing observations; never start another turn."""
        ...
    def steer(self, handle: InvocationHandle, message: SteeringMessage,
              permit: OperationPermit | None) -> SteeringReceipt | ErrorEnvelope: ...
    def cancel(self, handle: InvocationHandle, permit: OperationPermit | None) -> CancellationReceipt | ErrorEnvelope: ...
    def recover(self, handle: InvocationHandle, evidence: RecoveryEvidence) -> RecoveryReceipt | ErrorEnvelope:
        """Inspect, reattach, or read original capture; no resampling/resend."""
        ...
    def seal_capture(self, handle: InvocationHandle) -> CaptureReceipt | ErrorEnvelope:
        """Seal original raw identities; no scientific admission or qualification."""
        ...


@runtime_checkable
class ModelProvider(Protocol):
    """Direct PMRH-managed inference only, not hidden managed-agent internals."""
    def describe_model(self, model_selection: ModelSelection) -> ModelDescription | ErrorEnvelope: ...
    def validate_request(self, inference_spec: InferenceSpec) -> RequestValidation | ErrorEnvelope: ...
    def stream(self, inference_spec: InferenceSpec, inference_permit: OperationPermit | None) -> Iterator[ProviderEvent | ErrorEnvelope]:
        """At most one admitted attempt. Iteration errors retain original identity.

        Recheck authorization at the actual send boundary even for lazy streams.
        Disable implicit SDK retries; UNKNOWN cannot cause another sampling.
        """
        ...
    def inspect(self, provider_request_id: str) -> ExecutionObservation | ErrorEnvelope: ...
    def cancel(self, provider_request_id: str,
               permit: OperationPermit | None = None) -> CancellationReceipt | ErrorEnvelope:
        """Optional argument preserves the one-argument call, which fails closed."""
        ...
    def normalize_usage(self, raw_evidence: RawUsageEvidence) -> UsageObservation | ErrorEnvelope: ...


@runtime_checkable
class OrchestrationEngine(Protocol):
    def accept_event(self, event: EventEnvelope, boundary: ReadBoundary) -> EventAcceptance | ErrorEnvelope: ...
    def next_actions(self, request: ActionRequest, permit: OperationPermit | None) -> ActionPlan | ErrorEnvelope: ...
    def checkpoint(self) -> EngineCheckpoint | ErrorEnvelope: ...
    def resume_execution(self, checkpoint: EngineCheckpoint,
                         permit: OperationPermit | None) -> ActionPlan | ErrorEnvelope: ...
    def quiesce(self, request: QuiesceRequest, permit: OperationPermit | None) -> QuiesceReceipt | ErrorEnvelope: ...


@runtime_checkable
class EvidenceRepository(Protocol):
    """Reads only; no repair, journal reconciliation or index rebuild."""
    def read(self, evidence_ref: ExactRef, boundary: ReadBoundary, *,
             offset: int = 0, max_bytes: int = 65536) -> EvidenceSlice | ErrorEnvelope: ...


@runtime_checkable
class EventRepository(Protocol):
    """Reads exact committed snapshots; event DTO labels cannot authenticate."""
    def read_events(self, cursor: EventCursor, boundary: ReadBoundary, *,
                    limit: int = 256) -> EventPage | ErrorEnvelope: ...
    def verify_event(self, event: EventEnvelope, boundary: ReadBoundary) -> EventVerification | ErrorEnvelope: ...


@runtime_checkable
class PolicyGateway(Protocol):
    """Bind an authenticated caller out of band; never trust model principal text.

    Permit lookup, grant/capability/budget/control revalidation and fencing are
    future trusted implementations. A caller cannot mint authority by decoding
    OperationPermit, setting a trust-origin label or implementing this Protocol.
    """
    def authorize(self, intent: OperationIntent) -> AuthorizationDecision: ...
    def verify(self, permit: OperationPermit | None,
               intent: OperationIntent) -> PermitVerification | ErrorEnvelope: ...


@runtime_checkable
class UnitOfWork(Protocol):
    """Future atomic boundary. Stage has no committed visibility; rollback is local.

    Commit performs current authorization and compare-and-set checks together.
    Conflicts change no committed state. Do not wait for a model/network inside
    a storage writer transaction. Cross-store/global-pool atomicity is NOT promised.
    """
    def begin(self, expected: VersionExpectation) -> TransactionHandle | ErrorEnvelope: ...
    def stage(self, transaction: TransactionHandle, batch: CommitBatch) -> StagingReceipt | ErrorEnvelope: ...
    def commit(self, transaction: TransactionHandle,
               permit: OperationPermit | None) -> CommitReceipt | ErrorEnvelope: ...
    def rollback(self, transaction: TransactionHandle) -> RollbackReceipt | ErrorEnvelope: ...


@runtime_checkable
class Clock(Protocol):
    def now(self) -> TimePoint: ...
    def monotonic_ns(self) -> int:
        """Local elapsed-time observation, not cross-process causal sequence."""
        ...
