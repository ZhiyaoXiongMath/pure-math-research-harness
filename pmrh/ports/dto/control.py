"""Authorization decision data, never a bearer credential or trusted principal."""
from __future__ import annotations

from . import enums as E
from .capability import CapabilityRequirements
from .core import ErrorEnvelope, ExactRef, Scope, TimePoint
from .wire import DTO, digest, frozen_dto, identifier, nonnegative, require


@frozen_dto
class OperationIntent(DTO):
    scope: Scope
    operation: E.Operation
    operation_id: str
    payload_digest: str
    owner_epoch: int
    expected_control_version: int
    budget_grant_ref: ExactRef
    budget_unit: E.BudgetUnit
    budget_units_requested: int
    reservation_ref: ExactRef | None
    capability_requirements: CapabilityRequirements | None
    capability_manifest_ref: ExactRef | None
    claimed_principal_ref: ExactRef | None

    def _validate(self) -> None:
        identifier(self.operation_id)
        digest(self.payload_digest)
        require(self.owner_epoch >= 1, "Owner epoch must be positive.")
        nonnegative(self.expected_control_version)
        nonnegative(self.budget_units_requested)
        require(self.budget_grant_ref.project_id == self.scope.project_id,
                "Budget grant crosses the operation project.")
        for ref in (self.claimed_principal_ref, self.reservation_ref, self.capability_manifest_ref):
            require(ref is None or ref.project_id == self.scope.project_id,
                    "Authorization reference crosses the operation project.")
        if self.operation in (E.Operation.START, E.Operation.STREAM):
            require(self.reservation_ref is not None and self.capability_requirements is not None
                    and self.capability_manifest_ref is not None and self.budget_units_requested >= 1,
                    "External dispatch needs explicit capability and reserved budget requirements.")
        if self.capability_requirements is not None:
            require(self.capability_requirements.budget.unit is self.budget_unit,
                    "Authorization must not change budget units.")


@frozen_dto
class OperationPermit(DTO):
    """Reverify through PolicyGateway at the side-effect boundary.

    This value is not authorization. Authenticate the out-of-band caller, look
    up the decision, compare scope/action/payload/grant/control and apply fencing.
    """
    permit_id: str
    decision_ref: ExactRef
    principal_ref: ExactRef
    intent: OperationIntent
    issued_at: TimePoint
    expires_at: TimePoint

    def _validate(self) -> None:
        identifier(self.permit_id)
        require(self.decision_ref.project_id == self.intent.scope.project_id
                and self.principal_ref.project_id == self.intent.scope.project_id,
                "Permit scope and decision identity disagree.")


@frozen_dto
class AuthorizationDecision(DTO):
    intent: OperationIntent
    status: E.DecisionStatus
    permit: OperationPermit | None
    error: ErrorEnvelope | None

    def _validate(self) -> None:
        if self.status is E.DecisionStatus.ALLOWED:
            require(self.permit is not None and self.permit.intent == self.intent and self.error is None,
                    "Allowed decisions require an exact matching permit.")
        else:
            require(self.permit is None and self.error is not None,
                    "Denied decisions require a reason and no permit.")


@frozen_dto
class PermitVerification(DTO):
    intent: OperationIntent
    decision_ref: ExactRef
    checked_at: TimePoint
    status: E.DecisionStatus

    def _validate(self) -> None:
        require(self.status is E.DecisionStatus.ALLOWED,
                "Rejected verification is represented by an explicit PortError.")
        require(self.decision_ref.project_id == self.intent.scope.project_id,
                "Verification decision crosses the operation scope.")
