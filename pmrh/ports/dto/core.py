"""Pure identities, observations, safe errors and independent state axes."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from . import enums as E
from .wire import DTO, digest, frozen_dto, identifier, nonnegative, require


@frozen_dto
class ExactRef(DTO):
    """An existing object's exact revision and bytes; never a storage path."""
    project_id: str
    object_id: str
    revision: str
    sha256: str

    def _validate(self) -> None:
        identifier(self.project_id)
        identifier(self.object_id)
        identifier(self.revision)
        digest(self.sha256)


@frozen_dto
class Scope(DTO):
    project_id: str
    instance_id: str

    def _validate(self) -> None:
        identifier(self.project_id)
        identifier(self.instance_id)


@frozen_dto
class TimePoint(DTO):
    """UTC observation, not causal ordering. The original text is preserved."""
    utc: str
    clock_source: E.ClockSource

    def _validate(self) -> None:
        require(self.utc.endswith("Z") and "T" in self.utc,
                "Timestamp must be an explicit UTC ISO-8601 instant.")
        try:
            value = datetime.fromisoformat(self.utc[:-1] + "+00:00")
        except ValueError:
            require(False, "Malformed UTC timestamp.")
        require(value.tzinfo is not None, "Timestamp timezone is required.")


@frozen_dto
class ObservedIdentifier(DTO):
    kind: E.ObservationKind
    value: str | None

    def _validate(self) -> None:
        require((self.kind is E.ObservationKind.OBSERVED) == (self.value is not None),
                "Observed identifiers require a value; unobserved/inapplicable identifiers do not.")
        if self.value is not None:
            identifier(self.value)


@frozen_dto
class Quantity(DTO):
    kind: E.ObservationKind
    value: int | None

    def _validate(self) -> None:
        require((self.kind is E.ObservationKind.OBSERVED) == (self.value is not None),
                "Observed quantity requires an integer, including measured zero.")
        if self.value is not None:
            nonnegative(self.value)


@frozen_dto
class InvocationIdentity(DTO):
    scope: Scope
    logical_agent_id: str
    invocation_id: str
    request_id: str
    execution_id: str
    attempt_id: str

    def _validate(self) -> None:
        for value in (self.logical_agent_id, self.invocation_id, self.request_id,
                      self.execution_id, self.attempt_id):
            identifier(value)


@frozen_dto
class ControlSnapshot(DTO):
    scope: Scope
    logical_main_id: str
    owner_epoch: int
    control_version: int
    state: E.ControlState
    source_commit_ref: ExactRef

    def _validate(self) -> None:
        identifier(self.logical_main_id)
        require(self.owner_epoch >= 1, "Owner epoch must be positive.")
        nonnegative(self.control_version)
        require(self.source_commit_ref.project_id == self.scope.project_id,
                "Control snapshot commit belongs to another project.")


@frozen_dto
class StateAxes(DTO):
    """Independent facts; no cross-axis success transition is implied."""
    control: E.ControlState
    execution: E.ExecutionState
    admission: E.AdmissionState
    science: E.ScienceState
    science_scope_ref: ExactRef | None

    def _validate(self) -> None:
        if self.science in (E.ScienceState.SUPPORTED_ON_SCOPE, E.ScienceState.REFUTED_ON_SCOPE):
            require(self.science_scope_ref is not None, "Scoped science state needs an exact scope.")


# Messages are a fixed safe vocabulary, never raw exception text or model output.
_ERROR_MESSAGES = {
    E.ErrorCode.UNSUPPORTED_CAPABILITY: "Required capability is unavailable. Select an explicitly authorized compatible backend.",
    E.ErrorCode.AUTHORIZATION_REQUIRED: "Trusted authorization is missing or does not match this operation. Obtain a new decision.",
    E.ErrorCode.STALE_CONTROL_VERSION: "Control version or owner epoch is stale. Read current control and seek new admission.",
    E.ErrorCode.IDEMPOTENCY_CONFLICT: "An idempotency identity was reused for different content. Do not dispatch.",
    E.ErrorCode.NOT_SENT: "Evidence confirms this attempt was not sent. Any new attempt requires explicit admission.",
    E.ErrorCode.SEND_OUTCOME_UNKNOWN: "Sending outcome is unknown. Preserve the original identity and inspect; do not resend.",
    E.ErrorCode.UNOBSERVED: "No supported observation is available. This does not establish execution failure.",
    E.ErrorCode.EVENT_GAP: "Event coverage has a gap. Read a consistent snapshot before advancing the cursor.",
    E.ErrorCode.UNSUPPORTED_SCHEMA_VERSION: "Schema version is unsupported. Use a compatible reader; do not migrate automatically.",
    E.ErrorCode.CORRUPT_CAPTURE: "Raw capture verification failed. Quarantine and verify the original; never reconstruct from a summary.",
    E.ErrorCode.INVALID_WIRE: "Wire representation is invalid. Check the documented closed schema.",
    E.ErrorCode.INVALID_FIELD: "A field violates the contract. Check the documented field constraints.",
    E.ErrorCode.MISSING_FIELD: "A required field is missing. Supply an explicitly bound value.",
    E.ErrorCode.TYPE_MISMATCH: "A field has the wrong type. Do not coerce implementation objects into DTOs.",
    E.ErrorCode.NOT_FOUND: "The requested exact object is not available at this read boundary. No repair was attempted.",
    E.ErrorCode.VERSION_CONFLICT: "The expected committed version differs. Read a new snapshot and resubmit explicitly.",
    E.ErrorCode.TRANSACTION_CLOSED: "The transaction is closed or unknown. Do not reuse it for new writes.",
    E.ErrorCode.INVALID_CURSOR: "Cursor scope or position is invalid. Obtain a cursor for this exact stream.",
    E.ErrorCode.UNTRUSTED_EVENT: "The event is not verified as committed by the trusted repository. Do not treat a log line as authority.",
}
_RECOVERY = {
    E.ErrorCode.NOT_SENT: E.RecoverySafety.NEW_ADMISSION_REQUIRED,
    E.ErrorCode.SEND_OUTCOME_UNKNOWN: E.RecoverySafety.DO_NOT_RESEND,
    E.ErrorCode.AUTHORIZATION_REQUIRED: E.RecoverySafety.REAUTHORIZE,
    E.ErrorCode.STALE_CONTROL_VERSION: E.RecoverySafety.REAUTHORIZE,
    E.ErrorCode.UNOBSERVED: E.RecoverySafety.READ_ONLY,
    E.ErrorCode.EVENT_GAP: E.RecoverySafety.RESNAPSHOT,
    E.ErrorCode.CORRUPT_CAPTURE: E.RecoverySafety.VERIFY_ORIGINAL_CAPTURE,
}


@frozen_dto
class ErrorEnvelope(DTO):
    code: E.ErrorCode
    operation: E.Operation
    scope: Scope | None
    operation_id: str | None
    identity: InvocationIdentity | None
    raw_evidence_refs: tuple[ExactRef, ...]
    recovery_safety: E.RecoverySafety
    message: str
    automatic_retry: Literal[False] = False

    def _validate(self) -> None:
        require(self.message == _ERROR_MESSAGES[self.code],
                "Diagnostics must use the safe message catalog, not private content.")
        require(self.recovery_safety == _RECOVERY.get(
            self.code, E.RecoverySafety.NO_AUTOMATIC_RECOVERY),
            "Recovery description is inconsistent with the error.")
        if self.operation_id is not None:
            identifier(self.operation_id)
        if self.code is E.ErrorCode.NOT_SENT:
            require(bool(self.raw_evidence_refs), "NOT_SENT needs confirmation evidence.")
        if self.identity is not None:
            require(self.scope == self.identity.scope, "Error scope and identity disagree.")
        if self.scope is not None:
            require(all(r.project_id == self.scope.project_id for r in self.raw_evidence_refs),
                    "Error evidence must belong to the identified project.")


PortError = ErrorEnvelope


def port_error(code: E.ErrorCode, operation: E.Operation, *, scope: Scope | None = None,
               operation_id: str | None = None, identity: InvocationIdentity | None = None,
               evidence: tuple[ExactRef, ...] = ()) -> ErrorEnvelope:
    return ErrorEnvelope(code=code, operation=operation,
                         scope=identity.scope if identity is not None else scope,
                         operation_id=operation_id, identity=identity,
                         raw_evidence_refs=evidence,
                         recovery_safety=_RECOVERY.get(code, E.RecoverySafety.NO_AUTOMATIC_RECOVERY),
                         message=_ERROR_MESSAGES[code])
