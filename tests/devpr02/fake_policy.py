"""In-memory authorization fixture, NOT a production security implementation."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from pmrh.ports.capabilities import check_capabilities
from pmrh.ports.dto import capability as K, control as P, core as C, enums as E, execution as X, specs as S
from pmrh.ports.dto.wire import DTO
from . import fixtures as F

# An out-of-band test object, not a wire field or deployable credential.
TRUSTED_TEST_CONTEXT = object()


class FakeClock:
    def __init__(self, instant: C.TimePoint = F.NOW):
        self.instant = instant
        self.elapsed = 0

    def now(self) -> C.TimePoint:
        return self.instant

    def monotonic_ns(self) -> int:
        return self.elapsed

    def advance(self, seconds: int) -> None:
        if type(seconds) is not int or seconds < 0:
            raise ValueError("synthetic clock advance must be nonnegative")
        value = datetime.fromisoformat(self.instant.utc.replace("Z", "+00:00")) + timedelta(seconds=seconds)
        self.instant = C.TimePoint(utc=value.isoformat().replace("+00:00", "Z"), clock_source=E.ClockSource.SYNTHETIC)
        self.elapsed += seconds * 1_000_000_000


class FakePolicyGateway:
    """Only a separately registered fixture context can obtain/use a fake permit.

    Grants, manifests, decisions and principal identities come from this fixture
    registry, never the caller's principal/grant strings. No authentication,
    OS fencing, production budget reservations or remote revocation is proven.
    """
    def __init__(self, clock: FakeClock | None = None, *, context=None,
                 control: C.ControlSnapshot = F.CONTROL,
                 manifest: K.CapabilityManifest | None = None):
        self.clock = clock or FakeClock()
        self.context = context
        self.control = control
        self.manifest = manifest or F.manifest()
        self.manifest_ref = replace(F.ref("verified-manifest"), sha256=self.manifest.wire_digest())
        self.principal = F.PRINCIPAL
        self.grant = F.GRANT
        self.grant_limit = 10
        self.issued: dict[str, P.OperationPermit] = {}
        self.decision_writes = 0

    def intent(self, payload: DTO, operation: E.Operation, operation_id: str, *,
               epoch: int | None = None, version: int | None = None,
               scope: C.Scope | None = None, unit: E.BudgetUnit = E.BudgetUnit.AGENT_INVOCATION,
               grant: C.ExactRef | None = None) -> P.OperationIntent:
        required = None
        reservation = None
        units = 0
        if operation in (E.Operation.START, E.Operation.STREAM):
            spec = payload.spec if isinstance(payload, X.PreparedInvocation) else payload
            if not isinstance(spec, (S.AgentInvocationSpec, S.InferenceSpec)):
                raise ValueError("dispatch intent requires a frozen synthetic request")
            required = spec.capability_requirements
            reservation = spec.reservation_ref
            unit = required.budget.unit
            units = 1
            grant = spec.budget_grant_ref
            epoch = spec.owner_epoch
            version = spec.expected_control_version
            scope = spec.identity().scope if isinstance(spec, S.AgentInvocationSpec) else spec.identity.scope
        return P.OperationIntent(
            scope=scope or self.control.scope, operation=operation, operation_id=operation_id,
            payload_digest=payload.wire_digest(), owner_epoch=self.control.owner_epoch if epoch is None else epoch,
            expected_control_version=self.control.control_version if version is None else version,
            budget_grant_ref=grant or self.grant, budget_unit=unit, budget_units_requested=units,
            reservation_ref=reservation, capability_requirements=required,
            capability_manifest_ref=self.manifest_ref if required is not None else None,
            claimed_principal_ref=None)

    def _reason(self, intent: P.OperationIntent) -> C.ErrorEnvelope | None:
        def fail(code):
            return C.port_error(code, intent.operation, scope=intent.scope, operation_id=intent.operation_id)
        if self.context is not TRUSTED_TEST_CONTEXT:
            return fail(E.ErrorCode.AUTHORIZATION_REQUIRED)
        if (intent.scope != self.control.scope or intent.budget_grant_ref != self.grant
                or intent.claimed_principal_ref not in (None, self.principal)):
            return fail(E.ErrorCode.AUTHORIZATION_REQUIRED)
        if (intent.owner_epoch != self.control.owner_epoch
                or intent.expected_control_version != self.control.control_version):
            return fail(E.ErrorCode.STALE_CONTROL_VERSION)
        if intent.operation in (E.Operation.START, E.Operation.STREAM, E.Operation.NEXT_ACTIONS, E.Operation.RESUME_EXECUTION):
            if self.control.state is not E.ControlState.ACTIVE:
                return fail(E.ErrorCode.AUTHORIZATION_REQUIRED)
        if intent.capability_requirements is not None:
            if intent.capability_manifest_ref != self.manifest_ref:
                return fail(E.ErrorCode.AUTHORIZATION_REQUIRED)
            error = check_capabilities(self.manifest, intent.capability_requirements,
                                       operation=intent.operation, scope=intent.scope)
            if error is not None:
                return error
            if (intent.budget_unit not in self.manifest.hard_budget_units
                    or intent.budget_units_requested > min(self.grant_limit, intent.capability_requirements.budget.limit)):
                return fail(E.ErrorCode.AUTHORIZATION_REQUIRED)
        return None

    def authorize(self, intent: P.OperationIntent) -> P.AuthorizationDecision:
        error = self._reason(intent)
        if error is not None:
            return P.AuthorizationDecision(intent=intent, status=E.DecisionStatus.DENIED, permit=None, error=error)
        self.decision_writes += 1
        number = str(self.decision_writes)
        issued = self.clock.now()
        expires = datetime.fromisoformat(issued.utc.replace("Z", "+00:00")) + timedelta(hours=1)
        permit = P.OperationPermit(
            permit_id="synthetic:permit-" + number, decision_ref=F.ref("decision-" + number),
            principal_ref=self.principal, intent=intent, issued_at=issued,
            expires_at=C.TimePoint(utc=expires.isoformat().replace("+00:00", "Z"), clock_source=E.ClockSource.SYNTHETIC))
        self.issued[permit.permit_id] = permit
        return P.AuthorizationDecision(intent=intent, status=E.DecisionStatus.ALLOWED, permit=permit, error=None)

    def verify(self, permit: P.OperationPermit | None, intent: P.OperationIntent) -> P.PermitVerification | C.ErrorEnvelope:
        error = self._reason(intent)
        if error is not None:
            return error
        now = datetime.fromisoformat(self.clock.now().utc.replace("Z", "+00:00"))
        if (permit is None or self.issued.get(permit.permit_id) != permit or permit.intent != intent
                or permit.principal_ref != self.principal
                or datetime.fromisoformat(permit.expires_at.utc.replace("Z", "+00:00")) <= now):
            return C.port_error(E.ErrorCode.AUTHORIZATION_REQUIRED, intent.operation,
                                scope=intent.scope, operation_id=intent.operation_id)
        return P.PermitVerification(intent=intent, decision_ref=permit.decision_ref,
                                    checked_at=self.clock.now(), status=E.DecisionStatus.ALLOWED)


def trusted_policy(*, mode: E.ExecutionMode = E.ExecutionMode.MANAGED_AGENT) -> FakePolicyGateway:
    return FakePolicyGateway(context=TRUSTED_TEST_CONTEXT, manifest=F.manifest(mode))
