"""Technical orchestration Fake: consumes explicitly registered MAIN choices."""
from __future__ import annotations

from dataclasses import replace

from pmrh.ports.dto import control as P, core as C, enums as E, events as V, orchestration as O, storage as T
from . import fixtures as F
from .fake_policy import FakePolicyGateway
from .fake_storage import FakeEventRepository


class FakeOrchestrationEngine:
    def __init__(self, repository: FakeEventRepository, policy: FakePolicyGateway):
        self.repository, self.policy = repository, policy
        self.accepted: dict[str, str] = {}
        self.decisions: dict[C.ExactRef, tuple[O.TechnicalAction, ...]] = {}
        self.checkpoints: dict[str, O.EngineCheckpoint] = {}
        self.cursor = F.cursor()
        self.in_flight = ()
        self.quiesced = False
        self.trigger_effects = self.plan_effects = 0
        self.plans: dict[str, tuple[str, O.ActionPlan]] = {}

    def accept_event(self, event: V.EventEnvelope, boundary: T.ReadBoundary) -> O.EventAcceptance | C.ErrorEnvelope:
        if boundary.scope != self.policy.control.scope:
            return C.port_error(E.ErrorCode.UNTRUSTED_EVENT, E.Operation.ACCEPT_EVENT, scope=boundary.scope)
        check = self.repository.verify_event(event, boundary)
        if isinstance(check, C.ErrorEnvelope):
            return check
        previous = self.accepted.get(event.event_id)
        if previous is not None:
            if previous != event.wire_digest():
                return C.port_error(E.ErrorCode.IDEMPOTENCY_CONFLICT, E.Operation.ACCEPT_EVENT, scope=boundary.scope)
            return O.EventAcceptance(event_id=event.event_id, duplicate_status=E.DuplicateStatus.EXACT_DUPLICATE, boundary=boundary)
        if event.journal_sequence != self.cursor.after_sequence + 1:
            return C.port_error(E.ErrorCode.EVENT_GAP, E.Operation.ACCEPT_EVENT, scope=boundary.scope)
        self.accepted[event.event_id] = event.wire_digest()
        self.cursor = replace(self.cursor, after_sequence=event.journal_sequence, last_event_id=event.event_id)
        self.trigger_effects += 1
        return O.EventAcceptance(event_id=event.event_id, duplicate_status=E.DuplicateStatus.NEW, boundary=boundary)

    def action_intent(self, request: O.ActionRequest) -> P.OperationIntent:
        return self.policy.intent(request, E.Operation.NEXT_ACTIONS, request.operation_id,
                                  epoch=request.control.owner_epoch, version=request.control.control_version,
                                  scope=request.control.scope)

    def next_actions(self, request: O.ActionRequest, permit: P.OperationPermit | None) -> O.ActionPlan | C.ErrorEnvelope:
        check = self.policy.verify(permit, self.action_intent(request))
        if isinstance(check, C.ErrorEnvelope):
            return check
        if self.quiesced or request.control != self.policy.control:
            return C.port_error(E.ErrorCode.AUTHORIZATION_REQUIRED, E.Operation.NEXT_ACTIONS, scope=request.control.scope)
        if request.boundary not in self.repository.store.snapshots:
            return C.port_error(E.ErrorCode.NOT_FOUND, E.Operation.NEXT_ACTIONS, scope=request.control.scope)
        if request.proposed_actions and self.decisions.get(request.main_decision_ref) != request.proposed_actions:
            return C.port_error(E.ErrorCode.AUTHORIZATION_REQUIRED, E.Operation.NEXT_ACTIONS, scope=request.control.scope)
        old = self.plans.get(request.operation_id)
        if old is not None:
            return old[1] if old[0] == request.wire_digest() else C.port_error(
                E.ErrorCode.IDEMPOTENCY_CONFLICT, E.Operation.NEXT_ACTIONS, scope=request.control.scope)
        plan = O.ActionPlan(operation_id=request.operation_id, control=request.control,
                             actions=request.proposed_actions, decision_ref=request.main_decision_ref)
        self.plans[request.operation_id] = (request.wire_digest(), plan)
        self.plan_effects += 1
        return plan

    def checkpoint(self) -> O.EngineCheckpoint:
        checkpoint = O.EngineCheckpoint(
            checkpoint_id="synthetic:checkpoint-" + str(len(self.checkpoints) + 1),
            engine_schema_version="pmrh.execution-checkpoint/1", control=self.policy.control,
            boundary=self.repository.store.boundary, event_cursor=self.cursor,
            accepted_event_ids=tuple(self.accepted), in_flight_handles=self.in_flight, quiesced=self.quiesced)
        self.checkpoints[checkpoint.checkpoint_id] = checkpoint
        return checkpoint

    def resume_intent(self, checkpoint: O.EngineCheckpoint) -> P.OperationIntent:
        return self.policy.intent(checkpoint, E.Operation.RESUME_EXECUTION, checkpoint.checkpoint_id,
                                  epoch=checkpoint.control.owner_epoch, version=checkpoint.control.control_version,
                                  scope=checkpoint.control.scope)

    def resume_execution(self, checkpoint: O.EngineCheckpoint,
                         permit: P.OperationPermit | None) -> O.ActionPlan | C.ErrorEnvelope:
        check = self.policy.verify(permit, self.resume_intent(checkpoint))
        if isinstance(check, C.ErrorEnvelope):
            return check
        if self.checkpoints.get(checkpoint.checkpoint_id) != checkpoint:
            return C.port_error(E.ErrorCode.AUTHORIZATION_REQUIRED, E.Operation.RESUME_EXECUTION)
        # Resume never replays a dispatch or overrides current quiescence.
        # Existing in-flight identities remain available for explicit reattachment.
        return O.ActionPlan(operation_id=checkpoint.checkpoint_id, control=self.policy.control,
                             actions=(), decision_ref=None)

    def quiesce_intent(self, request: O.QuiesceRequest) -> P.OperationIntent:
        return self.policy.intent(request, E.Operation.QUIESCE, request.operation_id,
                                  epoch=request.control.owner_epoch, version=request.control.control_version,
                                  scope=request.control.scope)

    def quiesce(self, request: O.QuiesceRequest,
                permit: P.OperationPermit | None) -> O.QuiesceReceipt | C.ErrorEnvelope:
        check = self.policy.verify(permit, self.quiesce_intent(request))
        if isinstance(check, C.ErrorEnvelope):
            return check
        self.quiesced = True
        return O.QuiesceReceipt(scope=self.policy.control.scope, new_dispatch_blocked=True,
                                 in_flight_handles=self.in_flight)
