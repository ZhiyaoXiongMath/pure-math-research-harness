"""Detailed capabilities and exact acceptable-value negotiation inputs."""
from __future__ import annotations

from . import enums as E
from .core import ExactRef, TimePoint
from .wire import DTO, frozen_dto, identifier, nonnegative, require


@frozen_dto
class CapabilityManifest(DTO):
    execution_mode: E.ExecutionMode
    adapter_version: str
    backend_build_or_hash: str
    platform: str
    evidence_origin: E.EvidenceOrigin
    observation_timestamp: TimePoint
    test_receipt_refs: tuple[ExactRef, ...]
    continuation: E.Continuation
    steering: E.Steering
    cancellation: E.Cancellation
    dispatch_idempotency: E.DispatchIdempotency
    root_turn_gate: E.RootTurnGate
    tool_isolation: E.ToolIsolation
    raw_input_capture: E.RawInputCapture
    usage_coverage: E.UsageCoverage
    internal_delegation: E.InternalDelegation
    structured_output: E.StructuredOutput
    budget_gate: E.BudgetGate
    hard_budget_units: tuple[E.BudgetUnit, ...]

    def _validate(self) -> None:
        for value in (self.adapter_version, self.backend_build_or_hash, self.platform):
            identifier(value)
        if self.tool_isolation is E.ToolIsolation.TESTED_ON_PLATFORM:
            require(self.evidence_origin is not E.EvidenceOrigin.STATIC_DECLARATION
                    and bool(self.test_receipt_refs),
                    "Platform-tested isolation needs observation receipts, not a static declaration.")
        if self.evidence_origin is not E.EvidenceOrigin.STATIC_DECLARATION:
            require(bool(self.test_receipt_refs), "Observed capability manifests need evidence receipts.")
        require(len(set(self.hard_budget_units)) == len(self.hard_budget_units),
                "Hard budget units must not repeat.")
        if self.budget_gate is E.BudgetGate.UNSUPPORTED:
            require(not self.hard_budget_units, "Unsupported gate cannot enforce a hard budget.")
        if self.budget_gate is E.BudgetGate.INVOCATION_ADMISSION:
            require(set(self.hard_budget_units) <= {E.BudgetUnit.AGENT_INVOCATION},
                    "Invocation admission does not enforce internal inference or token budgets.")
        if self.budget_gate is E.BudgetGate.CALLER_INFERENCE_GATE:
            require(self.execution_mode is E.ExecutionMode.PMRS_MANAGED_LOOP,
                    "Caller inference gate cannot claim ownership of a managed agent's internal loop.")
            require(self.root_turn_gate is E.RootTurnGate.CALLER_CONTROLLED,
                    "Caller inference gating needs caller-controlled turns.")
        if self.budget_gate is E.BudgetGate.NATIVE_INFERENCE_GATE:
            require(self.execution_mode is E.ExecutionMode.MANAGED_AGENT
                    and self.root_turn_gate is E.RootTurnGate.NATIVE_GATED,
                    "Managed inference gating requires a native gated backend.")
        if any(u in self.hard_budget_units for u in (E.BudgetUnit.INFERENCE_REQUEST, E.BudgetUnit.TOKEN)):
            require(self.budget_gate in (E.BudgetGate.CALLER_INFERENCE_GATE, E.BudgetGate.NATIVE_INFERENCE_GATE)
                    and self.usage_coverage is E.UsageCoverage.INFERENCE_LEVEL,
                    "Hard inference/token limits require explicit enforcement and inference-level coverage.")


@frozen_dto
class BudgetRequirement(DTO):
    unit: E.BudgetUnit
    limit: int
    enforcement: E.BudgetEnforcement

    def _validate(self) -> None:
        nonnegative(self.limit)


@frozen_dto
class CapabilityRequirements(DTO):
    """Every accepted alternative is explicit; no implicit strength ordering."""
    execution_mode: E.ExecutionMode
    evidence_origins: tuple[E.EvidenceOrigin, ...]
    continuation: tuple[E.Continuation, ...]
    steering: tuple[E.Steering, ...]
    cancellation: tuple[E.Cancellation, ...]
    dispatch_idempotency: tuple[E.DispatchIdempotency, ...]
    root_turn_gate: tuple[E.RootTurnGate, ...]
    tool_isolation: tuple[E.ToolIsolation, ...]
    raw_input_capture: tuple[E.RawInputCapture, ...]
    usage_coverage: tuple[E.UsageCoverage, ...]
    internal_delegation: tuple[E.InternalDelegation, ...]
    structured_output: tuple[E.StructuredOutput, ...]
    required_platform: str | None
    required_backend_build: str | None
    budget: BudgetRequirement

    def _validate(self) -> None:
        for name in ("evidence_origins", "continuation", "steering", "cancellation",
                     "dispatch_idempotency", "root_turn_gate", "tool_isolation",
                     "raw_input_capture", "usage_coverage", "internal_delegation", "structured_output"):
            values = getattr(self, name)
            require(bool(values) and len(values) == len(set(values)),
                    "Each capability needs nonempty, unique accepted alternatives.")
        for value in (self.required_platform, self.required_backend_build):
            if value is not None:
                identifier(value)
