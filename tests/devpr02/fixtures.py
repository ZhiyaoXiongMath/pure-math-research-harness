"""Explicit synthetic identities. Never load user projects or host configuration."""
from __future__ import annotations

from dataclasses import replace
import hashlib

from pmrh.ports.dto import capability as K, core as C, enums as E, events as V, specs as S, storage as T


SCOPE = C.Scope(project_id="synthetic:project", instance_id="synthetic:instance")


def ref(name: str, raw: bytes | None = None, revision: str = "v1") -> C.ExactRef:
    return C.ExactRef(project_id=SCOPE.project_id, object_id="synthetic:" + name,
                      revision=revision, sha256=hashlib.sha256(raw if raw is not None else name.encode()).hexdigest())


NOW = C.TimePoint(utc="2026-10-13T00:00:00Z", clock_source=E.ClockSource.SYNTHETIC)
GRANT = ref("grant")
PRINCIPAL = ref("operator")
VISIBILITY = ref("visibility")
CONTROL = C.ControlSnapshot(scope=SCOPE, logical_main_id="synthetic:main", owner_epoch=1,
                            control_version=7, state=E.ControlState.ACTIVE, source_commit_ref=ref("initial-commit"))
BOUNDARY = T.ReadBoundary(scope=SCOPE, journal_id="synthetic:journal", commit_ref=CONTROL.source_commit_ref,
                          through_journal_sequence=0, visibility_policy_ref=VISIBILITY)


def unknown() -> C.ObservedIdentifier:
    return C.ObservedIdentifier(kind=E.ObservationKind.UNOBSERVED, value=None)


def observed(value: str) -> C.ObservedIdentifier:
    return C.ObservedIdentifier(kind=E.ObservationKind.OBSERVED, value=value)


def manifest(mode: E.ExecutionMode = E.ExecutionMode.MANAGED_AGENT) -> K.CapabilityManifest:
    loop = mode is E.ExecutionMode.PMRS_MANAGED_LOOP
    return K.CapabilityManifest(
        execution_mode=mode, adapter_version="synthetic:adapter-v1", backend_build_or_hash="synthetic:build-1",
        platform="synthetic:offline-platform", evidence_origin=E.EvidenceOrigin.OFFLINE_PROBE,
        observation_timestamp=NOW, test_receipt_refs=(ref("capability-receipt"),),
        continuation=E.Continuation.SAME_SESSION, steering=E.Steering.NEXT_TURN,
        cancellation=E.Cancellation.REQUEST_ONLY, dispatch_idempotency=E.DispatchIdempotency.RECEIPT_QUERY_ONLY,
        root_turn_gate=E.RootTurnGate.CALLER_CONTROLLED if loop else E.RootTurnGate.UNAVAILABLE,
        tool_isolation=E.ToolIsolation.TESTED_ON_PLATFORM, raw_input_capture=E.RawInputCapture.EXACT_FROZEN_AND_DYNAMIC,
        usage_coverage=E.UsageCoverage.INFERENCE_LEVEL if loop else E.UsageCoverage.TURN_AGGREGATE,
        internal_delegation=E.InternalDelegation.CONTROLLED if loop else E.InternalDelegation.OPAQUE,
        structured_output=E.StructuredOutput.VALIDATED_CAPTURE,
        budget_gate=E.BudgetGate.CALLER_INFERENCE_GATE if loop else E.BudgetGate.INVOCATION_ADMISSION,
        hard_budget_units=(E.BudgetUnit.INFERENCE_REQUEST, E.BudgetUnit.TOKEN) if loop else (E.BudgetUnit.AGENT_INVOCATION,))


def requirements(value: K.CapabilityManifest | None = None) -> K.CapabilityRequirements:
    m = value or manifest()
    return K.CapabilityRequirements(
        execution_mode=m.execution_mode, evidence_origins=(E.EvidenceOrigin.OFFLINE_PROBE,),
        continuation=(m.continuation,), steering=(m.steering,), cancellation=(m.cancellation,),
        dispatch_idempotency=(m.dispatch_idempotency,), root_turn_gate=(m.root_turn_gate,),
        tool_isolation=(m.tool_isolation,), raw_input_capture=(m.raw_input_capture,),
        usage_coverage=(m.usage_coverage,), internal_delegation=(m.internal_delegation,),
        structured_output=(m.structured_output,), required_platform=m.platform,
        required_backend_build=m.backend_build_or_hash,
        budget=K.BudgetRequirement(unit=m.hard_budget_units[0], limit=10, enforcement=E.BudgetEnforcement.HARD))


def model() -> S.ModelSelection:
    return S.ModelSelection(provider_id="synthetic:provider", model_id="synthetic:model-1",
                            effort="synthetic:effort", service_tier=None, endpoint_ref=ref("endpoint"),
                            credential_ref=ref("credential-reference-only"), tool_definition_refs=(ref("tool"),),
                            response_schema_ref=ref("output-schema"),
                            parameters=(S.ModelParameter(name="max_output", value=100),))


def spec(mode: E.ExecutionMode = E.ExecutionMode.MANAGED_AGENT) -> S.AgentInvocationSpec:
    selected = model()
    required = requirements(manifest(mode))
    return S.AgentInvocationSpec(
        project_id=SCOPE.project_id, instance_id=SCOPE.instance_id, research_goal_id="synthetic:goal",
        logical_agent_id="synthetic:worker", role=E.AgentRole.WORKER, stage_responsibility="TRH-P08",
        purpose="synthetic:contract-test", invocation_id="synthetic:invocation-1", request_id="synthetic:request-1",
        execution_id="synthetic:execution-1", attempt_id="synthetic:attempt-1", owner_epoch=1,
        expected_control_version=7, original_scope_ref=ref("original-scope"), method_version="synthetic:method-1",
        guidance_version=0, input_manifest_ref=ref("inputs"), read_set_digest=ref("read-set").sha256,
        visibility_policy_ref=VISIBILITY, output_contract_ref=ref("output-contract"),
        communication_contract_ref=ref("communication-contract"), runner_binding_ref=ref("runner-binding"),
        authorized_model_selection_ref=replace(ref("model-selection"), sha256=selected.wire_digest()),
        budget_grant_ref=GRANT, budget_unit=required.budget.unit, reservation_ref=ref("reservation"),
        sandbox_policy_ref=ref("sandbox"), tool_capability_ref=ref("tool-capability"),
        idempotency_key="synthetic:dispatch-key", parent_invocation_ref=None, correlation_id="synthetic:correlation",
        execution_mode=mode, model_selection=selected, capability_requirements=required)


def inference() -> S.InferenceSpec:
    s = spec(E.ExecutionMode.PMRS_MANAGED_LOOP)
    return S.InferenceSpec(identity=s.identity(), inference_id="synthetic:inference-1", owner_epoch=s.owner_epoch,
                           expected_control_version=s.expected_control_version, model_selection=s.model_selection,
                           input_manifest_ref=s.input_manifest_ref, output_contract_ref=s.output_contract_ref,
                           visibility_policy_ref=s.visibility_policy_ref, budget_grant_ref=s.budget_grant_ref,
                           reservation_ref=s.reservation_ref, idempotency_key="synthetic:inference-key",
                           correlation_id=s.correlation_id, capability_requirements=s.capability_requirements)


def envelope(number: int = 1, *, identity: C.InvocationIdentity | None = None,
             event_domain: E.EventDomain = E.EventDomain.EXECUTION) -> V.EventEnvelope:
    i = identity or spec().identity()
    payload = ref("payload-" + str(number))
    return V.EventEnvelope(
        event_id="synthetic:event-" + str(number), event_type="synthetic:output", event_domain=event_domain,
        status=E.EventStatus.OBSERVATION, project_id=i.scope.project_id, instance_id=i.scope.instance_id,
        journal_id=unknown(), aggregate_id=i.execution_id, aggregate_sequence=None, journal_sequence=None,
        commit_ref=None, occurred_at=None, observed_at=NOW, committed_at=None, clock_source=E.ClockSource.SYNTHETIC,
        actor_principal_ref=None, actor_kind="SYNTHETIC", correlation_id="synthetic:correlation", causation_id=None,
        operation_id="synthetic:operation-" + str(number), idempotency_key="synthetic:event-key-" + str(number),
        invocation_id=i.invocation_id, execution_id=i.execution_id, request_id=i.request_id, attempt_id=i.attempt_id,
        activation_id=None, logical_main_id="synthetic:main", owner_epoch=1, control_version=7,
        backend_id=observed("synthetic:backend"), provider_id=unknown(), provider_request_id=unknown(),
        backend_binding_ref=ref("runner-binding"), payload_ref=payload, raw_evidence_ref=ref("raw-event-" + str(number)),
        payload_sha256=payload.sha256, classification=E.Classification.SYNTHETIC_TEST_ONLY,
        trust_origin=E.TrustOrigin.SYNTHETIC_TEST_ONLY, visibility_policy_ref=VISIBILITY)


def cursor(kind: E.StreamKind = E.StreamKind.JOURNAL, stream: str = "synthetic:journal") -> V.EventCursor:
    return V.EventCursor(scope=SCOPE, stream_kind=kind, stream_id=stream, after_sequence=0, last_event_id=None)
