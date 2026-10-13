"""Pure capability negotiation; no model/backend substitutions or probing."""
from __future__ import annotations

from .dto import enums as E
from .dto.capability import CapabilityManifest, CapabilityRequirements
from .dto.core import ErrorEnvelope, Scope, port_error


def check_capabilities(manifest: CapabilityManifest, requirements: CapabilityRequirements,
                       *, operation: E.Operation = E.Operation.PREPARE,
                       scope: Scope | None = None) -> ErrorEnvelope | None:
    """None means this manifest satisfies the declared contract, not real-world proof.

    An untrusted caller can manufacture a manifest: the trusted application must
    bind its provenance, platform and evidence receipts separately. Limit zero
    is a real zero; authorization still has to refuse consumption of that grant.
    """
    matched = manifest.execution_mode is requirements.execution_mode
    matched = matched and manifest.evidence_origin in requirements.evidence_origins
    if requirements.required_platform is not None:
        matched = matched and manifest.platform == requirements.required_platform
    if requirements.required_backend_build is not None:
        matched = matched and manifest.backend_build_or_hash == requirements.required_backend_build
    for name in ("continuation", "steering", "cancellation", "dispatch_idempotency", "root_turn_gate",
                 "tool_isolation", "raw_input_capture", "usage_coverage", "internal_delegation", "structured_output"):
        matched = matched and getattr(manifest, name) in getattr(requirements, name)
    if requirements.budget.enforcement is E.BudgetEnforcement.HARD:
        matched = matched and requirements.budget.unit in manifest.hard_budget_units
        if requirements.budget.unit in (E.BudgetUnit.INFERENCE_REQUEST, E.BudgetUnit.TOKEN):
            expected_gate = (E.BudgetGate.NATIVE_INFERENCE_GATE
                             if manifest.execution_mode is E.ExecutionMode.MANAGED_AGENT
                             else E.BudgetGate.CALLER_INFERENCE_GATE)
            matched = (matched and manifest.budget_gate is expected_gate
                       and manifest.usage_coverage is E.UsageCoverage.INFERENCE_LEVEL)
    return None if matched else port_error(E.ErrorCode.UNSUPPORTED_CAPABILITY, operation, scope=scope)
