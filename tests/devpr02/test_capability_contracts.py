"""A04/B04 contract-level positive and negative capability negotiation."""
from __future__ import annotations

from dataclasses import replace
import unittest

from pmrh.ports.capabilities import check_capabilities
from pmrh.ports.dto import capability as K, core as C, enums as E, execution as X
from pmrh.ports.dto.wire import ContractViolation
from . import fixtures as F, scenarios as Q


class CapabilityContracts(unittest.TestCase):
    def test_explicit_managed_and_loop_modes_pass_only_their_own_requirements(self):
        managed, loop = F.manifest(), F.manifest(E.ExecutionMode.PMRS_MANAGED_LOOP)
        self.assertIsNone(check_capabilities(managed, F.requirements(managed)))
        self.assertIsNone(check_capabilities(loop, F.requirements(loop)))
        self.assertEqual(check_capabilities(managed, F.requirements(loop)).code, E.ErrorCode.UNSUPPORTED_CAPABILITY)
        self.assertEqual(check_capabilities(loop, F.requirements(managed)).code, E.ErrorCode.UNSUPPORTED_CAPABILITY)

    def test_B04_managed_aggregate_cannot_satisfy_hard_inference_budget(self):
        requirements = replace(F.requirements(), budget=K.BudgetRequirement(
            unit=E.BudgetUnit.INFERENCE_REQUEST, limit=3, enforcement=E.BudgetEnforcement.HARD))
        result = check_capabilities(F.manifest(), requirements)
        self.assertEqual(result.code, E.ErrorCode.UNSUPPORTED_CAPABILITY)
        self.assertEqual(F.manifest().usage_coverage, E.UsageCoverage.TURN_AGGREGATE)

    def test_false_hard_budget_manifest_is_rejected_on_construction(self):
        for changes in ({"hard_budget_units": (E.BudgetUnit.INFERENCE_REQUEST,)},
                        {"budget_gate": E.BudgetGate.CALLER_INFERENCE_GATE},
                        {"budget_gate": E.BudgetGate.NATIVE_INFERENCE_GATE}):
            with self.subTest(changes=changes), self.assertRaises(ContractViolation):
                replace(F.manifest(), **changes)

    def test_explicit_native_enforcement_contract_does_not_imply_real_backend_test(self):
        native = replace(F.manifest(), root_turn_gate=E.RootTurnGate.NATIVE_GATED,
                         budget_gate=E.BudgetGate.NATIVE_INFERENCE_GATE, usage_coverage=E.UsageCoverage.INFERENCE_LEVEL,
                         hard_budget_units=(E.BudgetUnit.INFERENCE_REQUEST,))
        self.assertIsNone(check_capabilities(native, F.requirements(native)))
        self.assertEqual(native.evidence_origin, E.EvidenceOrigin.OFFLINE_PROBE)
        self.assertNotEqual(native.evidence_origin, E.EvidenceOrigin.RUNTIME_OBSERVATION)

    def test_no_stock_backend_substitute_for_native_root_turn_gate(self):
        required = replace(F.requirements(), root_turn_gate=(E.RootTurnGate.NATIVE_GATED,))
        self.assertEqual(check_capabilities(F.manifest(), required).code, E.ErrorCode.UNSUPPORTED_CAPABILITY)

    def test_each_named_capability_is_independently_negotiated(self):
        cases = {"continuation": E.Continuation.DURABLE_AFTER_RESTART, "steering": E.Steering.LIVE_TURN,
                 "cancellation": E.Cancellation.DESCENDANT_AWARE, "dispatch_idempotency": E.DispatchIdempotency.PROVIDER_SUPPORTED,
                 "root_turn_gate": E.RootTurnGate.NATIVE_GATED, "tool_isolation": E.ToolIsolation.UNSUPPORTED,
                 "raw_input_capture": E.RawInputCapture.PARTIAL, "usage_coverage": E.UsageCoverage.INFERENCE_LEVEL,
                 "internal_delegation": E.InternalDelegation.CONTROLLED, "structured_output": E.StructuredOutput.SCHEMA_SUBSET}
        for name, value in cases.items():
            with self.subTest(capability=name):
                requirements = replace(F.requirements(), **{name: (value,)})
                self.assertEqual(check_capabilities(F.manifest(), requirements).code, E.ErrorCode.UNSUPPORTED_CAPABILITY)
        self.assertFalse(hasattr(F.manifest(), "supports_everything"))

    def test_static_declaration_is_not_offline_or_runtime_observation(self):
        static = replace(F.manifest(), evidence_origin=E.EvidenceOrigin.STATIC_DECLARATION,
                         tool_isolation=E.ToolIsolation.DOCUMENTED_ONLY, test_receipt_refs=())
        self.assertEqual(check_capabilities(static, F.requirements()).code, E.ErrorCode.UNSUPPORTED_CAPABILITY)
        with self.assertRaises(ContractViolation):
            replace(F.manifest(), test_receipt_refs=())
        # A documentation-only assertion must not self-label platform testing.
        with self.assertRaises(ContractViolation):
            replace(F.manifest(), evidence_origin=E.EvidenceOrigin.STATIC_DECLARATION, test_receipt_refs=())

    def test_platform_build_and_origin_mismatches_fail_closed(self):
        for changes in ({"required_platform": "synthetic:other-platform"},
                        {"required_backend_build": "synthetic:other-build"},
                        {"evidence_origins": (E.EvidenceOrigin.RUNTIME_OBSERVATION,)}):
            self.assertEqual(check_capabilities(F.manifest(), replace(F.requirements(), **changes)).code,
                             E.ErrorCode.UNSUPPORTED_CAPABILITY)

    def test_partial_usage_cannot_invent_inference_zero_or_double_count(self):
        usage = Q.usage(F.spec().identity(), E.ExecutionMode.MANAGED_AGENT)
        fake_zero = X.UsageDatum(metric=E.UsageMetric.INFERENCE_REQUESTS,
                                 quantity=C.Quantity(kind=E.ObservationKind.OBSERVED, value=0))
        with self.assertRaises(ContractViolation):
            replace(usage, values=(fake_zero,))
        with self.assertRaises(ContractViolation):
            replace(usage, inclusion=E.UsageInclusion.INCLUDED_IN_PARENT)
        self.assertEqual(usage.inclusion, E.UsageInclusion.RELATION_UNKNOWN)
        self.assertIsNone(usage.values[1].quantity.value)
