"""Reusable positive synthetic scenarios and an exhaustive DTO sample catalog."""
from __future__ import annotations

import base64
from dataclasses import fields, replace

from pmrh.ports.dto import control as P, core as C, enums as E, events as V, execution as X, orchestration as O, storage as T
from pmrh.ports.dto.wire import DTO
from . import fixtures as F
from .fake_engine import FakeOrchestrationEngine
from .fake_policy import trusted_policy
from .fake_runtime import FakeAgentRunner, FakeModelProvider
from .fake_storage import FakeStore, FakeEvidenceRepository, FakeEventRepository, FakeUnitOfWork


def permit(policy, intent):
    decision = policy.authorize(intent)
    if decision.status is not E.DecisionStatus.ALLOWED:
        raise AssertionError("Synthetic positive authorization was denied: " + decision.error.code.value)
    return decision.permit


def batch(number: int = 1) -> T.CommitBatch:
    event = F.envelope(number)
    return T.CommitBatch(operation_id="synthetic:commit-op-" + str(number), idempotency_key="synthetic:batch-key-" + str(number),
                         evidence=tuple(T.EvidenceWrite(evidence_ref=reference,
                                                        content_base64=base64.b64encode(text.encode()).decode("ascii"))
                                        for reference, text in ((event.payload_ref, "payload-" + str(number)),
                                                                (event.raw_evidence_ref, "raw-event-" + str(number)))),
                         events=(event,))


def capture(handle: X.InvocationHandle) -> X.CaptureReceipt:
    return X.CaptureReceipt(capture_id="synthetic:capture-1", identity=handle.identity,
                            raw_output_ref=F.ref("raw-output"), actual_input_manifest_ref=F.ref("inputs"),
                            raw_event_refs=(F.ref("raw-completion-event"),), sealed_at=F.NOW)


def usage(identity: C.InvocationIdentity, mode: E.ExecutionMode) -> X.UsageObservation:
    loop = mode is E.ExecutionMode.PMRS_MANAGED_LOOP
    return X.UsageObservation(identity=identity, execution_mode=mode,
                              coverage=E.UsageCoverage.INFERENCE_LEVEL if loop else E.UsageCoverage.TURN_AGGREGATE,
                              observed_at=F.NOW, raw_evidence_refs=(F.ref("raw-usage"),),
                              values=(X.UsageDatum(metric=E.UsageMetric.INPUT_TOKENS,
                                                    quantity=C.Quantity(kind=E.ObservationKind.OBSERVED, value=0)),
                                      X.UsageDatum(metric=E.UsageMetric.INFERENCE_REQUESTS,
                                                    quantity=C.Quantity(kind=E.ObservationKind.OBSERVED if loop else E.ObservationKind.UNOBSERVED,
                                                                        value=1 if loop else None))),
                              parent_usage_ref=None, inclusion=E.UsageInclusion.RELATION_UNKNOWN)


def collect_values(value, result: dict[type, DTO]) -> None:
    if isinstance(value, DTO):
        result[type(value)] = value
        for field in fields(value):
            collect_values(getattr(value, field.name), result)
    elif type(value) in (tuple, list):
        for item in value:
            collect_values(item, result)


def catalog() -> dict[type, DTO]:
    p = trusted_policy()
    r = FakeAgentRunner(p)
    prepared = r.prepare(F.spec())
    intent = r.start_intent(prepared)
    decision = p.authorize(intent)
    verification = p.verify(decision.permit, intent)
    dispatch = r.start(prepared, decision.permit)
    handle = dispatch.handle
    runner_page = r.events(handle, F.cursor(E.StreamKind.RUNNER, handle.identity.invocation_id))
    message = X.SteeringMessage(message_id="synthetic:message", content_ref=F.ref("guidance"),
                                 kind=E.GuidanceKind.HUMAN_GUIDANCE, idempotency_key="synthetic:message-key")
    steering = r.steer(handle, message, permit(p, r.steer_intent(handle, message)))
    cancellation = r.cancel(handle, permit(p, r.cancel_intent(handle)))
    captured = capture(handle)
    r.record_capture_fixture(handle, captured)
    recovery_evidence = X.RecoveryEvidence(identity=handle.identity, mode=E.RecoveryMode.READ_ORIGINAL_CAPTURE,
                                           raw_evidence_refs=captured.raw_event_refs, original_capture=captured)
    recovered = r.recover(handle, recovery_evidence)
    pp = trusted_policy(mode=E.ExecutionMode.PMRS_MANAGED_LOOP)
    provider = FakeModelProvider(pp)
    inference = F.inference()
    description = provider.describe_model(inference.model_selection)
    validated = provider.validate_request(inference)
    provider_events = tuple(provider.stream(inference, permit(pp, provider.stream_intent(inference))))
    pc = F.cursor(E.StreamKind.PROVIDER, inference.inference_id)
    provider_page = V.ProviderEventPage(requested_cursor=pc,
                                         next_cursor=replace(pc, after_sequence=1, last_event_id=provider_events[0].envelope.event_id),
                                         status=E.PageStatus.COMPLETE, events=provider_events, duplicate_event_ids=(), gap=None)
    raw_usage = X.RawUsageEvidence(identity=inference.identity, evidence_ref=F.ref("raw-usage"),
                                    normalizer_version="synthetic:normalizer-1")
    measured = usage(inference.identity, E.ExecutionMode.PMRS_MANAGED_LOOP)
    provider.usage_records[raw_usage] = measured
    normalized = provider.normalize_usage(raw_usage)
    store = FakeStore()
    evidence_repo, event_repo = FakeEvidenceRepository(store), FakeEventRepository(store)
    uow = FakeUnitOfWork(store, p)
    expectation = T.VersionExpectation(boundary=store.boundary, owner_epoch=1, expected_control_version=7)
    tx = uow.begin(expectation)
    changes = batch()
    staged = uow.stage(tx, changes)
    committed = uow.commit(tx, permit(p, uow.commit_intent(tx)))
    page = event_repo.read_events(F.cursor(), store.boundary)
    verified_event = event_repo.verify_event(page.events[0], store.boundary)
    evidence = evidence_repo.read(changes.evidence[0].evidence_ref, store.boundary)
    rollback = uow.rollback(uow.begin(replace(expectation, boundary=store.boundary)))
    engine = FakeOrchestrationEngine(event_repo, p)
    accepted = engine.accept_event(page.events[0], store.boundary)
    action = O.TechnicalAction(action_id="synthetic:action", kind=E.TechnicalActionKind.DISPATCH_PREPARED,
                               prepared=prepared, existing_handle=None)
    choice = F.ref("main-decision")
    engine.decisions[choice] = (action,)
    request = O.ActionRequest(operation_id="synthetic:action-op", control=p.control, boundary=store.boundary,
                               main_decision_ref=choice, proposed_actions=(action,), limit=1)
    plan = engine.next_actions(request, permit(p, engine.action_intent(request)))
    checkpoint = engine.checkpoint()
    quiesce_request = O.QuiesceRequest(operation_id="synthetic:pause-op", control=p.control, reason="PAUSE")
    quiesced = engine.quiesce(quiesce_request, permit(p, engine.quiesce_intent(quiesce_request)))
    axes = C.StateAxes(control=E.ControlState.PAUSED, execution=E.ExecutionState.RUNNING,
                        admission=E.AdmissionState.PENDING, science=E.ScienceState.OPEN, science_scope_ref=None)
    gap = V.EventGap(first_missing_sequence=1, last_missing_sequence=2, reason=E.GapReason.RETENTION,
                      resnapshot_ref=store.boundary.commit_ref)
    error = C.port_error(E.ErrorCode.SEND_OUTCOME_UNKNOWN, E.Operation.START, identity=handle.identity)
    result: dict[type, DTO] = {}
    collect_values([prepared, intent, decision, verification, dispatch, runner_page, message, steering, cancellation,
                    captured, recovery_evidence, recovered, description, validated, provider_page, raw_usage, normalized,
                    tx, changes, staged, committed, page, verified_event, evidence, rollback, accepted, request, plan,
                    checkpoint, quiesce_request, quiesced, axes, gap, error, inference], result)
    return result
