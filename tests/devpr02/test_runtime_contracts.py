"""Positive and adversarial contract calls through runnable offline Fakes."""
from __future__ import annotations

from dataclasses import replace
import unittest

import pmrh.ports as Ports
from pmrh.ports.dto import control as P, core as C, enums as E, execution as X
from . import fixtures as F, scenarios as Q
from .fake_engine import FakeOrchestrationEngine
from .fake_policy import FakeClock, FakePolicyGateway, trusted_policy
from .fake_runtime import FakeAgentRunner, FakeModelProvider
from .fake_storage import FakeStore, FakeEvidenceRepository, FakeEventRepository, FakeUnitOfWork


class RunnerContracts(unittest.TestCase):
    def setUp(self):
        self.policy = trusted_policy()
        self.runner = FakeAgentRunner(self.policy)
        self.prepared = self.runner.prepare(F.spec())

    def start(self):
        return self.runner.start(self.prepared, Q.permit(self.policy, self.runner.start_intent(self.prepared)))

    def assertError(self, result, code):
        self.assertIsInstance(result, C.ErrorEnvelope)
        self.assertEqual(result.code, code)

    def test_all_eight_public_protocols_have_callable_Fakes(self):
        store = FakeStore()
        repo = FakeEventRepository(store)
        values = ((Ports.AgentRunner, self.runner), (Ports.ModelProvider, FakeModelProvider(trusted_policy(mode=E.ExecutionMode.PMRS_MANAGED_LOOP))),
                  (Ports.EvidenceRepository, FakeEvidenceRepository(store)), (Ports.EventRepository, repo),
                  (Ports.PolicyGateway, self.policy), (Ports.UnitOfWork, FakeUnitOfWork(store, self.policy)),
                  (Ports.Clock, FakeClock()), (Ports.OrchestrationEngine, FakeOrchestrationEngine(repo, self.policy)))
        for protocol, fake in values:
            with self.subTest(port=protocol.__name__):
                self.assertIsInstance(fake, protocol)
        # Calls all DTO-bearing positive methods; the runtime-check alone is not the evidence.
        self.assertGreaterEqual(len(Q.catalog()), 50)
        self.assertEqual(self.runner.describe_capabilities(), F.manifest())

    def test_prepare_is_explicit_local_validation_not_inference(self):
        self.assertEqual(self.runner.send_effects, 0)
        self.assertEqual(self.prepared.preparation_effect, E.PreparationEffect.VALIDATION_ONLY)
        self.assertEqual(self.runner.prepare(F.spec()), self.prepared)
        self.assertEqual(self.runner.prepare_effects, 1)
        self.assertEqual(self.policy.decision_writes, 0)

    def test_missing_authorization_is_refused(self):
        self.assertError(self.runner.start(self.prepared, None), E.ErrorCode.AUTHORIZATION_REQUIRED)
        self.assertEqual(self.runner.send_effects, 0)

    def test_model_principal_epoch_grant_strings_do_not_create_trust(self):
        untrusted = FakePolicyGateway()
        intent = replace(untrusted.intent(self.prepared, E.Operation.START, self.prepared.spec.request_id),
                         claimed_principal_ref=F.PRINCIPAL)
        decision = untrusted.authorize(intent)
        self.assertEqual(decision.status, E.DecisionStatus.DENIED)
        self.assertIsNone(decision.permit)
        legitimate = Q.permit(self.policy, self.runner.start_intent(self.prepared))
        # Even a structurally correct copied permit has no authority in another untrusted context.
        copied = P.OperationPermit.from_json(legitimate.to_json())
        self.assertError(untrusted.verify(copied, intent), E.ErrorCode.AUTHORIZATION_REQUIRED)
        forged = replace(legitimate, permit_id="synthetic:invented-permit")
        self.assertError(self.runner.start(self.prepared, forged), E.ErrorCode.AUTHORIZATION_REQUIRED)
        self.assertEqual(self.runner.send_effects, 0)

    def test_stale_control_and_owner_epoch_rechecked_at_send_boundary(self):
        permit = Q.permit(self.policy, self.runner.start_intent(self.prepared))
        self.policy.control = replace(self.policy.control, owner_epoch=2, control_version=8)
        self.assertError(self.runner.start(self.prepared, permit), E.ErrorCode.STALE_CONTROL_VERSION)
        self.assertEqual(self.runner.send_effects, 0)

    def test_pause_and_expired_permit_refuse_new_dispatch(self):
        permit = Q.permit(self.policy, self.runner.start_intent(self.prepared))
        self.policy.control = replace(self.policy.control, state=E.ControlState.PAUSED)
        self.assertError(self.runner.start(self.prepared, permit), E.ErrorCode.AUTHORIZATION_REQUIRED)
        self.policy.control = F.CONTROL
        self.policy.clock.advance(3601)
        self.assertError(self.runner.start(self.prepared, permit), E.ErrorCode.AUTHORIZATION_REQUIRED)
        self.assertEqual(self.runner.send_effects, 0)

    def test_permit_bound_to_payload_operation_and_scope(self):
        intent = self.runner.start_intent(self.prepared)
        permit = Q.permit(self.policy, intent)
        for forged in (replace(permit, intent=replace(intent, payload_digest="0" * 64)),
                       replace(permit, intent=replace(intent, operation=E.Operation.INSPECT)),
                       replace(permit, intent=replace(intent, scope=replace(intent.scope, instance_id="synthetic:other")))):
            self.assertError(self.runner.start(self.prepared, forged), E.ErrorCode.AUTHORIZATION_REQUIRED)
        self.assertEqual(self.runner.send_effects, 0)

    def test_same_payload_same_key_has_one_fake_send(self):
        permit = Q.permit(self.policy, self.runner.start_intent(self.prepared))
        first = self.runner.start(self.prepared, permit)
        second = self.runner.start(self.prepared, permit)
        self.assertEqual(first, second)
        self.assertEqual(self.runner.send_effects, 1)

    def test_same_key_different_frozen_payload_conflicts(self):
        self.start()
        changed = self.runner.prepare(replace(F.spec(), purpose="synthetic:different-purpose"))
        result = self.runner.start(changed, Q.permit(self.policy, self.runner.start_intent(changed)))
        self.assertError(result, E.ErrorCode.IDEMPOTENCY_CONFLICT)
        self.assertEqual(self.runner.send_effects, 1)

    def test_not_sent_requires_confirmation_and_is_not_unknown(self):
        self.runner.dispatch_outcome = E.DispatchState.NOT_SENT
        result = self.start()
        self.assertEqual(result.status, E.DispatchState.NOT_SENT)
        self.assertEqual(result.error.code, E.ErrorCode.NOT_SENT)
        self.assertTrue(result.error.raw_evidence_refs)
        self.assertEqual(result.error.recovery_safety, E.RecoverySafety.NEW_ADMISSION_REQUIRED)
        self.assertEqual(self.runner.send_effects, 0)
        self.assertIsNone(result.handle.backend_invocation_id.value)

    def test_unknown_recovery_and_repeated_start_do_not_resample(self):
        self.runner.dispatch_outcome = E.DispatchState.SEND_OUTCOME_UNKNOWN
        result = self.start()
        evidence = X.RecoveryEvidence(identity=result.handle.identity, mode=E.RecoveryMode.INSPECT_ONLY,
                                       raw_evidence_refs=result.raw_evidence_refs, original_capture=None)
        for _ in range(3):
            recovered = self.runner.recover(result.handle, evidence)
            self.assertEqual(recovered.handle, result.handle)
            self.assertEqual(recovered.observation.state, E.ExecutionState.UNKNOWN)
            self.assertEqual(recovered.error.code, E.ErrorCode.SEND_OUTCOME_UNKNOWN)
            self.assertFalse(recovered.external_resend)
        self.assertEqual(self.start(), result)
        self.assertEqual(self.runner.send_effects, 1)

    def test_new_key_cannot_redispatch_existing_unknown_invocation(self):
        self.runner.dispatch_outcome = E.DispatchState.SEND_OUTCOME_UNKNOWN
        self.start()
        changed = self.runner.prepare(replace(F.spec(), idempotency_key="synthetic:new-key"))
        result = self.runner.start(changed, Q.permit(self.policy, self.runner.start_intent(changed)))
        self.assertError(result, E.ErrorCode.IDEMPOTENCY_CONFLICT)
        self.assertEqual(self.runner.send_effects, 1)

    def test_read_operations_do_not_dispatch_or_reconcile(self):
        handle = self.start().handle
        count = self.runner.send_effects
        for _ in range(3):
            self.runner.describe_capabilities()
            self.runner.inspect(handle)
            self.runner.events(handle, F.cursor(E.StreamKind.RUNNER, handle.identity.invocation_id))
        self.assertEqual(self.runner.send_effects, count)
        unknown = replace(handle, backend_invocation_id=F.observed("synthetic:unknown-handle"))
        self.assertError(self.runner.inspect(unknown), E.ErrorCode.UNOBSERVED)

    def test_runner_cursor_gap_is_not_empty_or_advanced(self):
        handle = self.start().handle
        cursor = F.cursor(E.StreamKind.RUNNER, handle.identity.invocation_id)
        page = self.runner.events(handle, cursor)
        self.assertEqual(page.status, E.PageStatus.COMPLETE)
        self.assertEqual(page.events[0].raw_event_ref, page.events[0].envelope.raw_evidence_ref)
        empty = self.runner.events(handle, page.next_cursor)
        self.assertEqual(empty.status, E.PageStatus.EMPTY)
        self.runner.first_available = 2
        gap = self.runner.events(handle, cursor)
        self.assertEqual(gap.status, E.PageStatus.GAP)
        self.assertEqual(gap.gap.first_missing_sequence, 1)
        self.assertEqual(gap.next_cursor, cursor)
        self.assertError(self.runner.events(handle, replace(cursor, stream_id="synthetic:another-stream")), E.ErrorCode.INVALID_CURSOR)

    def test_cancel_acknowledgement_is_not_observed_termination(self):
        handle = self.start().handle
        permit = Q.permit(self.policy, self.runner.cancel_intent(handle))
        result = self.runner.cancel(handle, permit)
        self.assertEqual(result.request_status, E.CancelStatus.REQUEST_ACKNOWLEDGED)
        self.assertEqual(result.termination, E.ObservationKind.UNOBSERVED)
        self.assertEqual(self.runner.inspect(handle).state, E.ExecutionState.RUNNING)
        self.assertEqual(self.runner.cancel(handle, permit), result)
        self.assertEqual(self.runner.cancel_effects, 1)

    def test_steering_saved_delivery_and_idempotency_are_separate(self):
        handle = self.start().handle
        message = X.SteeringMessage(message_id="synthetic:msg", content_ref=F.ref("guidance"),
                                     kind=E.GuidanceKind.GUIDANCE_PROPOSAL, idempotency_key="synthetic:msg-key")
        permit = Q.permit(self.policy, self.runner.steer_intent(handle, message))
        receipt = self.runner.steer(handle, message, permit)
        self.assertEqual(receipt.status, E.GuidanceStatus.SAVED)
        self.assertIsNone(receipt.consumer_confirmation_ref)
        self.assertEqual(self.runner.steer(handle, message, permit), receipt)
        changed = replace(message, content_ref=F.ref("changed-guidance"))
        result = self.runner.steer(handle, changed, Q.permit(self.policy, self.runner.steer_intent(handle, changed)))
        self.assertError(result, E.ErrorCode.IDEMPOTENCY_CONFLICT)
        self.assertEqual(self.runner.steer_effects, 1)

    def test_unsupported_capabilities_fail_without_fallback(self):
        before = self.runner.prepare_effects
        self.runner.manifest = replace(self.runner.manifest, steering=E.Steering.UNSUPPORTED)
        self.assertError(self.runner.prepare(F.spec()), E.ErrorCode.UNSUPPORTED_CAPABILITY)
        self.assertEqual(self.runner.prepare_effects, before)
        self.assertEqual(self.runner.send_effects, 0)
        self.runner.manifest = self.policy.manifest
        handle = self.start().handle
        self.runner.manifest = replace(self.runner.manifest, cancellation=E.Cancellation.UNSUPPORTED)
        self.assertError(self.runner.cancel(handle, Q.permit(self.policy, self.runner.cancel_intent(handle))), E.ErrorCode.UNSUPPORTED_CAPABILITY)
        self.assertEqual(self.runner.cancel_effects, 0)

    def test_capture_and_recovery_retain_raw_identity_not_scientific_qualification(self):
        handle = self.start().handle
        self.assertError(self.runner.seal_capture(handle), E.ErrorCode.UNOBSERVED)
        original = Q.capture(handle)
        self.runner.record_capture_fixture(handle, original)
        self.assertEqual(self.runner.seal_capture(handle), original)
        evidence = X.RecoveryEvidence(identity=handle.identity, mode=E.RecoveryMode.READ_ORIGINAL_CAPTURE,
                                       raw_evidence_refs=original.raw_event_refs, original_capture=original)
        result = self.runner.recover(handle, evidence)
        self.assertEqual(result.capture.raw_output_ref, original.raw_output_ref)
        self.assertEqual(result.capture.qualification, "RAW_CAPTURE_ONLY")
        corrupt = replace(original, raw_output_ref=F.ref("different-output"))
        self.assertError(self.runner.recover(handle, replace(evidence, original_capture=corrupt)), E.ErrorCode.CORRUPT_CAPTURE)
        self.assertEqual(self.runner.send_effects, 1)

    def test_observed_zero_budget_cannot_authorize_a_send(self):
        base = F.spec()
        required = replace(base.capability_requirements, budget=replace(base.capability_requirements.budget, limit=0))
        prepared = self.runner.prepare(replace(base, capability_requirements=required))
        decision = self.policy.authorize(self.runner.start_intent(prepared))
        self.assertEqual(decision.status, E.DecisionStatus.DENIED)
        self.assertEqual(self.runner.send_effects, 0)


class ProviderContracts(unittest.TestCase):
    def setUp(self):
        self.policy = trusted_policy(mode=E.ExecutionMode.PMRS_MANAGED_LOOP)
        self.provider = FakeModelProvider(self.policy)
        self.spec = F.inference()

    def stream(self, spec=None):
        spec = spec or self.spec
        return tuple(self.provider.stream(spec, Q.permit(self.policy, self.provider.stream_intent(spec))))

    def test_describe_and_validate_are_not_inference_or_authorization(self):
        self.assertIsNone(self.provider.describe_model(self.spec.model_selection).actual_model)
        self.assertTrue(self.provider.validate_request(self.spec).requires_inference_permit)
        result = tuple(self.provider.stream(self.spec, None))
        self.assertEqual(result[0].code, E.ErrorCode.AUTHORIZATION_REQUIRED)
        self.assertEqual(self.provider.send_effects, 0)

    def test_requested_model_is_not_echoed_as_observed_model(self):
        self.provider.scripted_actual_model = "synthetic:different-observed-model"
        events = self.stream()
        self.assertNotEqual(events[0].actual_model_id.value, self.spec.model_selection.model_id)
        self.assertEqual(events[0].actual_model_id.kind, E.ObservationKind.OBSERVED)
        self.assertEqual(self.spec.model_selection, F.model())
        # This is capture of a discrepancy, not acceptance of that model substitution.

    def test_no_silent_model_downgrade_or_parameter_fallback(self):
        changed = replace(self.spec, model_selection=replace(F.model(), effort="synthetic:unsupported"))
        error = self.provider.validate_request(changed)
        self.assertEqual(error.code, E.ErrorCode.UNSUPPORTED_CAPABILITY)
        self.assertEqual(self.provider.send_effects, 0)

    def test_stream_inspect_cancel_and_usage_are_callable(self):
        event = self.stream()[0]
        request_id = event.envelope.provider_request_id.value
        self.assertIsNotNone(request_id)
        self.assertEqual(self.provider.inspect(request_id).state, E.ExecutionState.RUNNING)
        self.assertEqual(self.provider.cancel(request_id).code, E.ErrorCode.AUTHORIZATION_REQUIRED)
        result = self.provider.cancel(request_id, Q.permit(self.policy, self.provider.cancel_intent(request_id)))
        self.assertEqual(result.termination, E.ObservationKind.UNOBSERVED)
        self.assertEqual(self.provider.inspect(request_id).state, E.ExecutionState.RUNNING)
        raw = X.RawUsageEvidence(identity=self.spec.identity, evidence_ref=F.ref("raw-usage"), normalizer_version="synthetic:normalizer-1")
        self.assertEqual(self.provider.normalize_usage(raw).code, E.ErrorCode.UNOBSERVED)
        measured = Q.usage(self.spec.identity, E.ExecutionMode.PMRS_MANAGED_LOOP)
        self.provider.usage_records[raw] = measured
        self.assertEqual(self.provider.normalize_usage(raw), measured)
        self.assertEqual(measured.values[0].quantity.value, 0)

    def test_provider_same_key_deduplicates_different_payload_conflicts(self):
        first = self.stream()
        self.assertEqual(self.stream(), first)
        conflict = self.stream(replace(self.spec, input_manifest_ref=F.ref("other-inputs")))
        self.assertEqual(conflict[0].code, E.ErrorCode.IDEMPOTENCY_CONFLICT)
        self.assertEqual(self.provider.send_effects, 1)

    def test_provider_unknown_has_no_invented_provider_id_or_implicit_retry(self):
        self.provider.dispatch_outcome = E.DispatchState.SEND_OUTCOME_UNKNOWN
        first = self.stream()
        self.assertEqual(first[0].code, E.ErrorCode.SEND_OUTCOME_UNKNOWN)
        self.assertEqual(first[0].recovery_safety, E.RecoverySafety.DO_NOT_RESEND)
        self.assertEqual(self.stream(), first)
        self.assertEqual(self.provider.requests, {})
        self.assertEqual(self.provider.inspect("synthetic:unknown-provider-request").code, E.ErrorCode.UNOBSERVED)
        self.assertEqual(self.provider.send_effects, 1)

    def test_new_key_cannot_resend_same_unknown_inference_identity(self):
        self.provider.dispatch_outcome = E.DispatchState.SEND_OUTCOME_UNKNOWN
        self.stream()
        result = self.stream(replace(self.spec, idempotency_key="synthetic:changed-key"))
        self.assertEqual(result[0].code, E.ErrorCode.IDEMPOTENCY_CONFLICT)
        self.assertEqual(self.provider.send_effects, 1)

    def test_provider_confirmed_not_sent_is_distinct(self):
        self.provider.dispatch_outcome = E.DispatchState.NOT_SENT
        result = self.stream()[0]
        self.assertEqual(result.code, E.ErrorCode.NOT_SENT)
        self.assertTrue(result.raw_evidence_refs)
        self.assertEqual(self.provider.send_effects, 0)

    def test_managed_agent_internal_usage_is_not_direct_provider_metering(self):
        managed = Q.usage(F.spec().identity(), E.ExecutionMode.MANAGED_AGENT)
        direct = Q.usage(self.spec.identity, E.ExecutionMode.PMRS_MANAGED_LOOP)
        self.assertIsNone(managed.values[1].quantity.value)
        self.assertEqual(direct.values[1].quantity.value, 1)
        self.assertEqual(managed.inclusion, E.UsageInclusion.RELATION_UNKNOWN)
        self.assertEqual(managed.coverage, E.UsageCoverage.TURN_AGGREGATE)
        bad_provider = FakeModelProvider(trusted_policy())
        self.assertEqual(bad_provider.validate_request(self.spec).code, E.ErrorCode.UNSUPPORTED_CAPABILITY)
