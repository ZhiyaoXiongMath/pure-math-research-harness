"""Scripted offline runtime doubles. Counters measure Fake effects, not model calls."""
from __future__ import annotations

from dataclasses import replace
from typing import Iterator

from pmrh.ports.capabilities import check_capabilities
from pmrh.ports.dto import capability as K, control as P, core as C, enums as E, events as V, execution as X, specs as S
from . import fixtures as F
from .fake_policy import FakePolicyGateway


class FakeAgentRunner:
    def __init__(self, policy: FakePolicyGateway):
        self.policy = policy
        self.manifest = policy.manifest
        self.dispatch_outcome = E.DispatchState.SENT
        self.prepared: dict[str, X.PreparedInvocation] = {}
        self.dispatches: dict[str, tuple[str, X.DispatchReceipt]] = {}
        self.handles: dict[str, X.InvocationHandle] = {}
        self.observations: dict[str, X.ExecutionObservation] = {}
        self.event_records: dict[str, tuple[V.RunnerEvent, ...]] = {}
        self.captures: dict[str, X.CaptureReceipt] = {}
        self.guidance: dict[tuple[str, str], tuple[str, X.SteeringReceipt]] = {}
        self.cancellations: dict[str, X.CancellationReceipt] = {}
        self.first_available = 1
        self.prepare_effects = self.send_effects = self.steer_effects = self.cancel_effects = 0

    def describe_capabilities(self) -> K.CapabilityManifest:
        return self.manifest

    def prepare(self, spec: S.AgentInvocationSpec) -> X.PreparedInvocation | C.ErrorEnvelope:
        error = check_capabilities(self.manifest, spec.capability_requirements, scope=spec.identity().scope)
        if error is not None:
            return error
        if spec.identity().scope != self.policy.control.scope:
            return C.port_error(E.ErrorCode.AUTHORIZATION_REQUIRED, E.Operation.PREPARE, identity=spec.identity())
        key = spec.wire_digest()
        if key not in self.prepared:
            self.prepared[key] = X.PreparedInvocation(prepared_id="synthetic:prepared-" + key[:24], spec=spec,
                                                       spec_digest=key, prepared_at=self.policy.clock.now(),
                                                       preparation_effect=E.PreparationEffect.VALIDATION_ONLY,
                                                       local_preparation_refs=())
            self.prepare_effects += 1
        return self.prepared[key]

    def start_intent(self, prepared: X.PreparedInvocation) -> P.OperationIntent:
        return self.policy.intent(prepared, E.Operation.START, prepared.spec.request_id)

    def start(self, prepared: X.PreparedInvocation,
              permit: P.OperationPermit | None) -> X.DispatchReceipt | C.ErrorEnvelope:
        spec = prepared.spec
        identity = spec.identity()
        if self.prepared.get(prepared.spec_digest) != prepared:
            return C.port_error(E.ErrorCode.AUTHORIZATION_REQUIRED, E.Operation.START, identity=identity)
        check = self.policy.verify(permit, self.start_intent(prepared))
        if isinstance(check, C.ErrorEnvelope):
            return check
        changed = check_capabilities(self.manifest, spec.capability_requirements,
                                     operation=E.Operation.START, scope=identity.scope)
        if changed is not None:
            return changed
        old = self.dispatches.get(spec.idempotency_key)
        if old is not None:
            return (old[1] if old[0] == spec.wire_digest() else
                    C.port_error(E.ErrorCode.IDEMPOTENCY_CONFLICT, E.Operation.START, identity=identity))
        if identity.invocation_id in self.handles:
            return C.port_error(E.ErrorCode.IDEMPOTENCY_CONFLICT, E.Operation.START, identity=identity)
        sent = self.dispatch_outcome is E.DispatchState.SENT
        handle = X.InvocationHandle(identity=identity, backend_binding_ref=spec.runner_binding_ref,
                                    backend_invocation_id=F.observed("synthetic:backend-invocation-" + str(self.send_effects + 1)) if sent else F.unknown())
        raw = (F.ref("send-observation-" + self.dispatch_outcome.value),)
        error = None
        if not sent:
            code = E.ErrorCode.NOT_SENT if self.dispatch_outcome is E.DispatchState.NOT_SENT else E.ErrorCode.SEND_OUTCOME_UNKNOWN
            error = C.port_error(code, E.Operation.START, identity=identity, evidence=raw)
        receipt = X.DispatchReceipt(status=self.dispatch_outcome, handle=handle,
                                     observed_at=self.policy.clock.now(), raw_evidence_refs=raw, error=error)
        self.dispatches[spec.idempotency_key] = (spec.wire_digest(), receipt)
        self.handles[identity.invocation_id] = handle
        state = E.ExecutionState.RUNNING if sent else (E.ExecutionState.PREPARED if self.dispatch_outcome is E.DispatchState.NOT_SENT
                                                       else E.ExecutionState.UNKNOWN)
        self.observations[identity.invocation_id] = X.ExecutionObservation(
            identity=identity, state=state, observed_at=self.policy.clock.now(), raw_evidence_refs=raw,
            actual_model_id=F.unknown(), provider_request_id=F.unknown())
        env = replace(F.envelope(identity=identity),
                      event_id="synthetic:runner-event-" + identity.wire_digest()[:32])
        self.event_records[identity.invocation_id] = ((V.RunnerEvent(sequence=1, kind=E.RunnerEventKind.STARTED,
                                                                     envelope=env, raw_event_ref=env.raw_evidence_ref),)
                                                     if sent else ())
        if self.dispatch_outcome is not E.DispatchState.NOT_SENT:
            self.send_effects += 1
        return receipt

    def _known(self, handle: X.InvocationHandle) -> bool:
        return self.handles.get(handle.identity.invocation_id) == handle

    def events(self, handle: X.InvocationHandle, cursor: V.EventCursor) -> V.RunnerEventPage | C.ErrorEnvelope:
        if not self._known(handle):
            return C.port_error(E.ErrorCode.UNOBSERVED, E.Operation.EVENTS, identity=handle.identity)
        records = self.event_records[handle.identity.invocation_id]
        if (cursor.scope != handle.identity.scope or cursor.stream_kind is not E.StreamKind.RUNNER
                or cursor.stream_id != handle.identity.invocation_id or cursor.after_sequence > len(records)
                or (cursor.after_sequence and records[cursor.after_sequence - 1].envelope.event_id != cursor.last_event_id)):
            return C.port_error(E.ErrorCode.INVALID_CURSOR, E.Operation.EVENTS, identity=handle.identity)
        if cursor.after_sequence < len(records) and cursor.after_sequence + 1 < self.first_available:
            return V.RunnerEventPage(requested_cursor=cursor, next_cursor=cursor, status=E.PageStatus.GAP,
                                      events=(), duplicate_event_ids=(),
                                      gap=V.EventGap(first_missing_sequence=cursor.after_sequence + 1,
                                                     last_missing_sequence=min(self.first_available - 1, len(records)),
                                                     reason=E.GapReason.RETENTION, resnapshot_ref=None))
        selected = records[cursor.after_sequence:cursor.after_sequence + 256]
        nxt = replace(cursor, after_sequence=selected[-1].sequence, last_event_id=selected[-1].envelope.event_id) if selected else cursor
        return V.RunnerEventPage(requested_cursor=cursor, next_cursor=nxt,
                                  status=E.PageStatus.COMPLETE if selected else E.PageStatus.EMPTY,
                                  events=selected, duplicate_event_ids=(), gap=None)

    def inspect(self, handle: X.InvocationHandle) -> X.ExecutionObservation | C.ErrorEnvelope:
        if not self._known(handle):
            return C.port_error(E.ErrorCode.UNOBSERVED, E.Operation.INSPECT, identity=handle.identity)
        return self.observations[handle.identity.invocation_id]

    def steer_intent(self, handle: X.InvocationHandle, message: X.SteeringMessage) -> P.OperationIntent:
        return self.policy.intent(message, E.Operation.STEER, handle.identity.invocation_id + ":" + message.message_id)

    def steer(self, handle: X.InvocationHandle, message: X.SteeringMessage,
              permit: P.OperationPermit | None) -> X.SteeringReceipt | C.ErrorEnvelope:
        if not self._known(handle):
            return C.port_error(E.ErrorCode.UNOBSERVED, E.Operation.STEER, identity=handle.identity)
        check = self.policy.verify(permit, self.steer_intent(handle, message))
        if isinstance(check, C.ErrorEnvelope):
            return check
        if self.manifest.steering is E.Steering.UNSUPPORTED:
            return C.port_error(E.ErrorCode.UNSUPPORTED_CAPABILITY, E.Operation.STEER, identity=handle.identity)
        if message.content_ref.project_id != handle.identity.scope.project_id:
            return C.port_error(E.ErrorCode.AUTHORIZATION_REQUIRED, E.Operation.STEER, identity=handle.identity)
        key = (handle.identity.invocation_id, message.idempotency_key)
        old = self.guidance.get(key)
        if old is not None:
            return old[1] if old[0] == message.wire_digest() else C.port_error(E.ErrorCode.IDEMPOTENCY_CONFLICT,
                                                                             E.Operation.STEER, identity=handle.identity)
        receipt = X.SteeringReceipt(identity=handle.identity, message_id=message.message_id,
                                     status=E.GuidanceStatus.SAVED, evidence_refs=(F.ref("saved-guidance"),),
                                     consumer_confirmation_ref=None)
        self.guidance[key] = (message.wire_digest(), receipt)
        self.steer_effects += 1
        return receipt

    def cancel_intent(self, handle: X.InvocationHandle) -> P.OperationIntent:
        return self.policy.intent(handle, E.Operation.CANCEL, handle.identity.invocation_id + ":cancel")

    def cancel(self, handle: X.InvocationHandle,
               permit: P.OperationPermit | None) -> X.CancellationReceipt | C.ErrorEnvelope:
        if not self._known(handle):
            return C.port_error(E.ErrorCode.UNOBSERVED, E.Operation.CANCEL, identity=handle.identity)
        check = self.policy.verify(permit, self.cancel_intent(handle))
        if isinstance(check, C.ErrorEnvelope):
            return check
        if self.manifest.cancellation is E.Cancellation.UNSUPPORTED:
            return C.port_error(E.ErrorCode.UNSUPPORTED_CAPABILITY, E.Operation.CANCEL, identity=handle.identity)
        key = handle.identity.invocation_id
        if key not in self.cancellations:
            self.cancellations[key] = X.CancellationReceipt(
                identity=handle.identity, request_status=E.CancelStatus.REQUEST_ACKNOWLEDGED,
                termination=E.ObservationKind.UNOBSERVED, request_evidence_refs=(F.ref("cancel-ack"),),
                termination_evidence_refs=())
            self.cancel_effects += 1
        return self.cancellations[key]

    def recover(self, handle: X.InvocationHandle, evidence: X.RecoveryEvidence) -> X.RecoveryReceipt | C.ErrorEnvelope:
        if not self._known(handle) or evidence.identity != handle.identity:
            return C.port_error(E.ErrorCode.UNOBSERVED, E.Operation.RECOVER, identity=handle.identity)
        if evidence.mode is E.RecoveryMode.REATTACH_EXISTING and self.manifest.continuation is E.Continuation.UNSUPPORTED:
            return C.port_error(E.ErrorCode.UNSUPPORTED_CAPABILITY, E.Operation.RECOVER, identity=handle.identity)
        original = self.captures.get(handle.identity.invocation_id)
        if evidence.original_capture is not None and evidence.original_capture != original:
            return C.port_error(E.ErrorCode.CORRUPT_CAPTURE, E.Operation.RECOVER, identity=handle.identity)
        observation = self.observations[handle.identity.invocation_id]
        error = (C.port_error(E.ErrorCode.SEND_OUTCOME_UNKNOWN, E.Operation.RECOVER, identity=handle.identity)
                 if observation.state is E.ExecutionState.UNKNOWN else None)
        return X.RecoveryReceipt(handle=handle, observation=observation, capture=original, error=error)

    def seal_capture(self, handle: X.InvocationHandle) -> X.CaptureReceipt | C.ErrorEnvelope:
        if not self._known(handle):
            return C.port_error(E.ErrorCode.UNOBSERVED, E.Operation.SEAL_CAPTURE, identity=handle.identity)
        return self.captures.get(handle.identity.invocation_id) or C.port_error(
            E.ErrorCode.UNOBSERVED, E.Operation.SEAL_CAPTURE, identity=handle.identity)

    def record_capture_fixture(self, handle: X.InvocationHandle, capture: X.CaptureReceipt) -> None:
        """Explicit synthetic backend-observation injection, not a Port method."""
        if not self._known(handle) or capture.identity != handle.identity:
            raise ValueError("capture fixture belongs to another invocation")
        key = handle.identity.invocation_id
        existing = self.captures.get(key)
        if existing is not None and existing != capture:
            raise ValueError("original capture fixture is immutable")
        self.captures[key] = capture
        self.observations[key] = replace(self.observations[key], state=E.ExecutionState.CAPTURED,
                                         raw_evidence_refs=capture.raw_event_refs)


class FakeModelProvider:
    def __init__(self, policy: FakePolicyGateway):
        self.policy = policy
        self.manifest = policy.manifest
        self.supported_selection = F.model()
        self.scripted_actual_model = "synthetic:model-1"
        self.scripted_event_kind = E.ProviderEventKind.REQUEST_OBSERVED
        # Register an attempted inference even when no provider ID is observed.
        self.inference_keys: dict[str, str] = {}
        self.dispatch_outcome = E.DispatchState.SENT
        self.requests: dict[str, tuple[S.InferenceSpec, X.ExecutionObservation]] = {}
        self.operations: dict[str, tuple[str, tuple[V.ProviderEvent | C.ErrorEnvelope, ...]]] = {}
        self.usage_records: dict[X.RawUsageEvidence, X.UsageObservation] = {}
        self.cancellations: dict[str, X.CancellationReceipt] = {}
        self.send_effects = self.cancel_effects = 0

    def describe_model(self, model_selection: S.ModelSelection) -> S.ModelDescription | C.ErrorEnvelope:
        if model_selection != self.supported_selection:
            return C.port_error(E.ErrorCode.UNSUPPORTED_CAPABILITY, E.Operation.DESCRIBE)
        return S.ModelDescription(selection=model_selection, supported_parameter_names=("max_output",),
                                  capabilities=self.manifest, actual_model=None)

    def validate_request(self, inference_spec: S.InferenceSpec) -> S.RequestValidation | C.ErrorEnvelope:
        error = check_capabilities(self.manifest, inference_spec.capability_requirements,
                                   operation=E.Operation.VALIDATE_REQUEST, scope=inference_spec.identity.scope)
        if error is not None:
            return replace(error, identity=inference_spec.identity,
                           operation_id=inference_spec.inference_id)
        if isinstance(self.describe_model(inference_spec.model_selection), C.ErrorEnvelope):
            return C.port_error(E.ErrorCode.UNSUPPORTED_CAPABILITY, E.Operation.VALIDATE_REQUEST,
                                identity=inference_spec.identity, operation_id=inference_spec.inference_id)
        return S.RequestValidation(request_digest=inference_spec.wire_digest(), capabilities=self.manifest,
                                     requires_inference_permit=True)

    def stream_intent(self, spec: S.InferenceSpec) -> P.OperationIntent:
        return self.policy.intent(spec, E.Operation.STREAM, spec.inference_id)

    def stream(self, inference_spec: S.InferenceSpec,
               inference_permit: P.OperationPermit | None) -> Iterator[V.ProviderEvent | C.ErrorEnvelope]:
        spec = inference_spec
        check = self.validate_request(spec)
        if not isinstance(check, C.ErrorEnvelope):
            check = self.policy.verify(inference_permit, self.stream_intent(spec))
        if isinstance(check, C.ErrorEnvelope):
            # Normalize upstream validation/policy rejection to the operation
            # being attempted, retaining evidence and the exact local inference.
            return iter((replace(check, operation=E.Operation.STREAM,
                                 scope=spec.identity.scope, identity=spec.identity,
                                 operation_id=spec.inference_id),))
        old = self.operations.get(spec.idempotency_key)
        if old is not None:
            return iter(old[1] if old[0] == spec.wire_digest() else
                        (C.port_error(E.ErrorCode.IDEMPOTENCY_CONFLICT, E.Operation.STREAM, identity=spec.identity,
                                      operation_id=spec.inference_id),))
        if spec.inference_id in self.inference_keys:
            return iter((C.port_error(E.ErrorCode.IDEMPOTENCY_CONFLICT, E.Operation.STREAM, identity=spec.identity,
                                      operation_id=spec.inference_id),))
        if self.dispatch_outcome is not E.DispatchState.NOT_SENT:
            self.send_effects += 1
        if self.dispatch_outcome is not E.DispatchState.SENT:
            code = E.ErrorCode.NOT_SENT if self.dispatch_outcome is E.DispatchState.NOT_SENT else E.ErrorCode.SEND_OUTCOME_UNKNOWN
            events = (C.port_error(code, E.Operation.STREAM, identity=spec.identity,
                                   operation_id=spec.inference_id, evidence=(F.ref("provider-send-observation"),)),)
        else:
            provider_id = "synthetic:provider-request-" + str(self.send_effects)
            env = replace(F.envelope(identity=spec.identity),
                          operation_id=spec.inference_id,
                          event_id="synthetic:provider-event-" + spec.wire_digest()[:32],
                          provider_id=F.observed("synthetic:provider"),
                          provider_request_id=F.observed(provider_id))
            events = (V.ProviderEvent(sequence=1, inference_id=spec.inference_id,
                                       kind=self.scripted_event_kind, envelope=env,
                                       raw_event_ref=env.raw_evidence_ref, actual_model_id=F.observed(self.scripted_actual_model)),)
            observation = X.ExecutionObservation(identity=spec.identity, state=E.ExecutionState.RUNNING,
                                                   observed_at=self.policy.clock.now(), raw_evidence_refs=(env.raw_evidence_ref,),
                                                   actual_model_id=F.observed(self.scripted_actual_model),
                                                   provider_request_id=F.observed(provider_id))
            self.requests[provider_id] = (spec, observation)
        self.inference_keys[spec.inference_id] = spec.idempotency_key
        self.operations[spec.idempotency_key] = (spec.wire_digest(), events)
        return iter(events)

    def inspect(self, provider_request_id: str) -> X.ExecutionObservation | C.ErrorEnvelope:
        entry = self.requests.get(provider_request_id)
        return entry[1] if entry else C.port_error(E.ErrorCode.UNOBSERVED, E.Operation.INSPECT,
                                                operation_id=provider_request_id)

    def cancel_intent(self, provider_request_id: str) -> P.OperationIntent:
        return self.policy.intent(F.observed(provider_request_id), E.Operation.CANCEL, provider_request_id + ":cancel")

    def cancel(self, provider_request_id: str,
               permit: P.OperationPermit | None = None) -> X.CancellationReceipt | C.ErrorEnvelope:
        entry = self.requests.get(provider_request_id)
        if entry is None:
            return C.port_error(E.ErrorCode.UNOBSERVED, E.Operation.CANCEL, operation_id=provider_request_id)
        check = self.policy.verify(permit, self.cancel_intent(provider_request_id))
        if isinstance(check, C.ErrorEnvelope):
            return replace(check, scope=entry[0].identity.scope, identity=entry[0].identity,
                           operation_id=entry[0].inference_id)
        if self.manifest.cancellation is E.Cancellation.UNSUPPORTED:
            return C.port_error(E.ErrorCode.UNSUPPORTED_CAPABILITY, E.Operation.CANCEL,
                                identity=entry[0].identity, operation_id=entry[0].inference_id)
        if provider_request_id not in self.cancellations:
            self.cancellations[provider_request_id] = X.CancellationReceipt(
                identity=entry[0].identity, request_status=E.CancelStatus.REQUEST_ACKNOWLEDGED,
                termination=E.ObservationKind.UNOBSERVED, request_evidence_refs=(F.ref("provider-cancel-ack"),),
                termination_evidence_refs=())
            self.cancel_effects += 1
        return self.cancellations[provider_request_id]

    def normalize_usage(self, raw_evidence: X.RawUsageEvidence) -> X.UsageObservation | C.ErrorEnvelope:
        return self.usage_records.get(raw_evidence) or C.port_error(E.ErrorCode.UNOBSERVED,
                                                                  E.Operation.NORMALIZE_USAGE, identity=raw_evidence.identity)
