"""Closed schemas, deep value immutability, safe errors and precise observations."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
import json
import unittest

from pmrh.ports.dto import core as C, enums as E, events as V, execution as X, specs as S
from pmrh.ports.dto.wire import ContractViolation, SCHEMA_VERSION, _REGISTRY, decode_wire
from . import fixtures as F, scenarios as Q


class DTOContracts(unittest.TestCase):
    def test_every_public_DTO_has_constructible_roundtrip_sample(self):
        examples = Q.catalog()
        self.assertEqual(set(examples), set(_REGISTRY.values()))
        self.assertGreaterEqual(len(examples), 50)
        for cls, value in examples.items():
            with self.subTest(dto=cls.__name__):
                wire = value.to_wire()
                self.assertEqual(value, cls.from_json(json.dumps(wire)))
                self.assertEqual(value, decode_wire(wire))
                self.assertEqual(value.wire_digest(), cls.from_json(value.to_json()).wire_digest())
                self.assertEqual(wire["schema_version"], SCHEMA_VERSION)
                self.assertFalse(hasattr(value, "__dict__"))

    def test_all_AgentInvocationSpec_required_identity_groups_present(self):
        expected = set("schema_version project_id instance_id research_goal_id logical_agent_id role stage_responsibility purpose invocation_id request_id execution_id attempt_id owner_epoch expected_control_version original_scope_ref method_version guidance_version input_manifest_ref read_set_digest visibility_policy_ref output_contract_ref communication_contract_ref runner_binding_ref authorized_model_selection_ref budget_grant_ref budget_unit reservation_ref sandbox_policy_ref tool_capability_ref idempotency_key parent_invocation_ref correlation_id".split())
        self.assertLessEqual(expected, {f.name for f in fields(S.AgentInvocationSpec)})
        for name in expected - {"schema_version"}:
            wire = F.spec().to_wire()
            del wire[name]
            with self.subTest(field=name), self.assertRaises(ContractViolation) as error:
                S.AgentInvocationSpec.from_wire(wire)
            self.assertEqual(error.exception.code, E.ErrorCode.MISSING_FIELD)

    def test_constructor_missing_fields_rejected(self):
        with self.assertRaises(TypeError):
            S.AgentInvocationSpec(project_id=F.SCOPE.project_id)

    def test_strict_types_no_bool_number_or_string_coercion(self):
        for bad in (True, "1", 1.0, [], {}, object()):
            with self.subTest(value_type=type(bad).__name__), self.assertRaises(ContractViolation):
                replace(F.spec(), owner_epoch=bad)
        with self.assertRaises(ContractViolation):
            replace(F.spec(), role="WORKER")
        with self.assertRaises(ContractViolation):
            replace(F.spec().model_selection, parameters=list(F.spec().model_selection.parameters))

    def test_deep_immutability_and_external_wire_containers_detached(self):
        original = F.spec()
        wire = original.to_wire()
        decoded = S.AgentInvocationSpec.from_wire(wire)
        wire["model_selection"]["parameters"][0]["value"] = 999999
        wire["capability_requirements"]["steering"].append("LIVE_TURN")
        self.assertEqual(original, decoded)
        with self.assertRaises(FrozenInstanceError):
            decoded.model_selection.parameters[0].value = 2
        with self.assertRaises(TypeError):
            decoded.model_selection.parameters[0] = S.ModelParameter(name="other", value=2)
        with self.assertRaises(FrozenInstanceError):
            decoded.owner_epoch = 99
        changed = decoded.to_wire()
        changed["input_manifest_ref"]["object_id"] = "synthetic:changed"
        self.assertEqual(original, decoded)

    def test_no_arbitrary_SDK_Store_process_or_mutable_payload(self):
        class Store:
            pass
        for bad in (Store(), object(), lambda: None, {"mutable": []}, [1, 2], b"bytes"):
            with self.subTest(type=type(bad).__name__), self.assertRaises(ContractViolation):
                S.ModelParameter(name="configuration", value=bad)
        with self.assertRaises(ContractViolation):
            replace(F.spec(), input_manifest_ref=Store())
        wire = F.spec().to_wire()
        wire["model_selection"]["parameters"][0]["value"] = Store()
        with self.assertRaises(ContractViolation):
            S.AgentInvocationSpec.from_wire(wire)

    def test_unknown_top_and_nested_schema_versions_rejected_explicitly(self):
        for version in ("pmrh.ports/2.0", "pmrh.ports/1.1", "pmrs.ports/1.0", None, 1):
            with self.subTest(version=version), self.assertRaises(ContractViolation) as error:
                replace(F.spec(), schema_version=version)
            self.assertEqual(error.exception.code, E.ErrorCode.UNSUPPORTED_SCHEMA_VERSION)
        # Optional nested refs must not lose the version error in union dispatch.
        wire = F.spec().to_wire()
        wire["model_selection"]["response_schema_ref"]["schema_version"] = "pmrh.ports/99"
        with self.assertRaises(ContractViolation) as error:
            S.AgentInvocationSpec.from_wire(wire)
        self.assertEqual(error.exception.code, E.ErrorCode.UNSUPPORTED_SCHEMA_VERSION)

    def test_no_unknown_member_duplicate_JSON_or_dynamic_type_loader(self):
        wire = F.spec().to_wire()
        wire["secret_untrusted_key"] = "sensitive-fixture-do-not-echo"
        with self.assertRaises(ContractViolation) as error:
            S.AgentInvocationSpec.from_wire(wire)
        self.assertNotIn("sensitive-fixture", str(error.exception))
        self.assertNotIn("secret_untrusted_key", str(error.exception))
        text = F.spec().to_json().replace('"schema_version":"pmrh.ports/1.0"',
            '"schema_version":"pmrh.ports/1.0","schema_version":"pmrh.ports/1.0"', 1)
        with self.assertRaises(ContractViolation):
            S.AgentInvocationSpec.from_json(text)
        with self.assertRaises(ContractViolation):
            decode_wire({"schema_version": SCHEMA_VERSION, "dto_type": "import_os_and_execute"})

    def test_invalid_JSON_nan_and_unicode_rejected(self):
        for text in ("not-json", "{", '{"x": NaN}', '"\\ud800"'):
            with self.subTest(text=text), self.assertRaises(ContractViolation):
                C.Scope.from_json(text)

    def test_null_unknown_and_measured_zero_remain_distinct(self):
        zero = C.Quantity(kind=E.ObservationKind.OBSERVED, value=0)
        unknown = C.Quantity(kind=E.ObservationKind.UNOBSERVED, value=None)
        absent = C.Quantity(kind=E.ObservationKind.NOT_APPLICABLE, value=None)
        self.assertNotEqual(zero, unknown)
        self.assertNotEqual(unknown, absent)
        self.assertEqual(C.Quantity.from_json(zero.to_json()).value, 0)
        for kind, value in ((E.ObservationKind.OBSERVED, None), (E.ObservationKind.UNOBSERVED, 0),
                            (E.ObservationKind.OBSERVED, True), (E.ObservationKind.OBSERVED, -1)):
            with self.assertRaises(ContractViolation):
                C.Quantity(kind=kind, value=value)

    def test_nullable_fields_have_explicit_rules_and_no_auto_identity(self):
        original = F.spec()
        self.assertIsNone(original.parent_invocation_ref)
        self.assertEqual(original.guidance_version, 0)
        with self.assertRaises(ContractViolation):
            replace(original, stage_responsibility=None)
        main = replace(original, role=E.AgentRole.MAIN, stage_responsibility=None)
        self.assertIsNone(main.stage_responsibility)
        self.assertIsNone(F.envelope().provider_request_id.value)
        with self.assertRaises(ContractViolation):
            C.ObservedIdentifier(kind=E.ObservationKind.UNOBSERVED, value="invented-provider-id")

    def test_original_evidence_revision_and_selection_are_not_renumbered(self):
        reference = replace(F.ref("old-evidence"), revision="legacy:KR@revision-000042")
        self.assertEqual(C.ExactRef.from_json(reference.to_json()), reference)
        with self.assertRaises(ContractViolation):
            replace(F.spec(), model_selection=replace(F.model(), model_id="synthetic:downgrade"))
        with self.assertRaises(ContractViolation):
            replace(F.model(), parameters=(S.ModelParameter(name="api_key", value="synthetic-secret"),))

    def test_safe_error_catalog_all_codes_and_no_automatic_retry(self):
        for code in E.ErrorCode:
            value = C.port_error(code, E.Operation.START, identity=F.spec().identity(),
                                 evidence=(F.ref("confirm-not-sent"),) if code is E.ErrorCode.NOT_SENT else ())
            self.assertEqual(C.ErrorEnvelope.from_json(value.to_json()), value)
            self.assertFalse(value.automatic_retry)
            with self.assertRaises(ContractViolation):
                replace(value, message="private-research-body-or-secret")
        with self.assertRaises(ContractViolation):
            C.port_error(E.ErrorCode.NOT_SENT, E.Operation.START)
        unknown = C.port_error(E.ErrorCode.SEND_OUTCOME_UNKNOWN, E.Operation.START)
        self.assertEqual(unknown.recovery_safety, E.RecoverySafety.DO_NOT_RESEND)
        with self.assertRaises(ContractViolation):
            replace(unknown, recovery_safety=E.RecoverySafety.NEW_ADMISSION_REQUIRED)

    def test_raw_capture_is_not_scientific_qualification(self):
        capture = Q.catalog()[X.CaptureReceipt]
        self.assertEqual(capture.qualification, "RAW_CAPTURE_ONLY")
        with self.assertRaises(ContractViolation):
            replace(capture, qualification="CHECKED")
        self.assertFalse(hasattr(capture, "science"))
        axes = C.StateAxes(control=E.ControlState.PAUSED, execution=E.ExecutionState.TERMINATED,
                            admission=E.AdmissionState.PENDING, science=E.ScienceState.OPEN, science_scope_ref=None)
        self.assertEqual(C.StateAxes.from_json(axes.to_json()).science, E.ScienceState.OPEN)
        with self.assertRaises(ValueError):
            E.ScienceState("ACCEPTED")

    def test_guidance_delivery_does_not_establish_read_or_adopted(self):
        receipt = X.SteeringReceipt(identity=F.spec().identity(), message_id="synthetic:m",
                                    status=E.GuidanceStatus.DELIVERED, evidence_refs=(F.ref("delivery"),),
                                    consumer_confirmation_ref=None)
        for status in (E.GuidanceStatus.READ, E.GuidanceStatus.CONSIDERED, E.GuidanceStatus.ADOPTED):
            with self.subTest(status=status), self.assertRaises(ContractViolation):
                replace(receipt, status=status)
        adopted = replace(receipt, status=E.GuidanceStatus.ADOPTED, consumer_confirmation_ref=F.ref("main-confirmation"))
        self.assertEqual(adopted.status, E.GuidanceStatus.ADOPTED)

    def test_external_log_cannot_be_a_committed_authoritative_event(self):
        event = F.envelope()
        with self.assertRaises(ContractViolation):
            replace(event, status=E.EventStatus.COMMITTED)
        with self.assertRaises(ContractViolation):
            replace(event, status=E.EventStatus.COMMITTED, journal_id=F.observed("synthetic:journal"),
                    journal_sequence=1, aggregate_sequence=1, commit_ref=F.ref("commit"), committed_at=F.NOW,
                    actor_kind="MODEL", trust_origin=E.TrustOrigin.MODEL_PROPOSAL)
        with self.assertRaises(ContractViolation):
            V.RunnerEvent(sequence=1, kind=E.RunnerEventKind.TERMINATED,
                          envelope=replace(event, event_domain=E.EventDomain.SCIENCE), raw_event_ref=event.raw_evidence_ref)

    def test_event_and_capture_reject_wrong_scope_or_digest(self):
        with self.assertRaises(ContractViolation):
            replace(F.envelope(), payload_sha256="0" * 64)
        with self.assertRaises(ContractViolation):
            replace(F.spec(), input_manifest_ref=replace(F.ref("input"), project_id="synthetic:other-project"))
        with self.assertRaises(ContractViolation):
            C.TimePoint(utc="2026-10-13T00:00:00", clock_source=E.ClockSource.SYNTHETIC)
