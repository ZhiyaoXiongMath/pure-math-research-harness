"""Frozen requests: exact scientific inputs, model selection and control binding."""
from __future__ import annotations

from . import enums as E
from .capability import CapabilityManifest, CapabilityRequirements
from .core import ExactRef, InvocationIdentity, Scope
from .wire import DTO, digest, frozen_dto, identifier, nonnegative, require


@frozen_dto
class ModelParameter(DTO):
    """Typed immutable scalar configuration; prompts and credentials use refs."""
    name: str
    value: str | int | bool | None

    def _validate(self) -> None:
        identifier(self.name)
        if type(self.value) is str:
            require(len(self.value) <= 1024, "Model parameter value is too long.")


@frozen_dto
class ModelSelection(DTO):
    provider_id: str
    model_id: str
    effort: str | None
    service_tier: str | None
    endpoint_ref: ExactRef
    credential_ref: ExactRef
    tool_definition_refs: tuple[ExactRef, ...]
    response_schema_ref: ExactRef | None
    parameters: tuple[ModelParameter, ...]

    def _validate(self) -> None:
        identifier(self.provider_id)
        identifier(self.model_id)
        for value in (self.effort, self.service_tier):
            if value is not None:
                identifier(value)
        require(len({p.name for p in self.parameters}) == len(self.parameters),
                "Model parameters must have distinct names.")
        blocked = {"token", "api_key", "secret", "credential", "authorization", "password"}
        require(not any(p.name.lower() in blocked for p in self.parameters),
                "Credential values are prohibited; use credential_ref.")


@frozen_dto
class AgentInvocationSpec(DTO):
    project_id: str
    instance_id: str
    research_goal_id: str
    logical_agent_id: str
    role: E.AgentRole
    stage_responsibility: str | None
    purpose: str
    invocation_id: str
    request_id: str
    execution_id: str
    attempt_id: str
    owner_epoch: int
    expected_control_version: int
    original_scope_ref: ExactRef
    method_version: str
    guidance_version: int
    input_manifest_ref: ExactRef
    read_set_digest: str
    visibility_policy_ref: ExactRef
    output_contract_ref: ExactRef
    communication_contract_ref: ExactRef
    runner_binding_ref: ExactRef
    authorized_model_selection_ref: ExactRef
    budget_grant_ref: ExactRef
    budget_unit: E.BudgetUnit
    reservation_ref: ExactRef
    sandbox_policy_ref: ExactRef
    tool_capability_ref: ExactRef
    idempotency_key: str
    parent_invocation_ref: ExactRef | None
    correlation_id: str
    execution_mode: E.ExecutionMode
    model_selection: ModelSelection
    capability_requirements: CapabilityRequirements

    def identity(self) -> InvocationIdentity:
        return InvocationIdentity(scope=Scope(project_id=self.project_id, instance_id=self.instance_id),
                                  logical_agent_id=self.logical_agent_id, invocation_id=self.invocation_id,
                                  request_id=self.request_id, execution_id=self.execution_id,
                                  attempt_id=self.attempt_id)

    def _validate(self) -> None:
        for value in (self.project_id, self.instance_id, self.research_goal_id, self.logical_agent_id,
                      self.purpose, self.invocation_id, self.request_id, self.execution_id,
                      self.attempt_id, self.method_version, self.idempotency_key, self.correlation_id):
            identifier(value)
        if self.stage_responsibility is not None:
            identifier(self.stage_responsibility)
        if self.role in (E.AgentRole.WORKER, E.AgentRole.INDEPENDENT_REVIEWER):
            require(self.stage_responsibility is not None, "Worker/reviewer responsibility cannot be inferred.")
        require(self.owner_epoch >= 1, "Owner epoch must be positive.")
        nonnegative(self.expected_control_version)
        nonnegative(self.guidance_version)
        digest(self.read_set_digest)
        for name in ("original_scope_ref", "input_manifest_ref", "visibility_policy_ref", "output_contract_ref",
                     "communication_contract_ref", "runner_binding_ref", "authorized_model_selection_ref",
                     "budget_grant_ref", "reservation_ref", "sandbox_policy_ref", "tool_capability_ref",
                     "parent_invocation_ref"):
            ref = getattr(self, name)
            require(ref is None or ref.project_id == self.project_id, "Invocation reference crosses its project boundary.")
        require(self.execution_mode is self.capability_requirements.execution_mode,
                "Execution mode differs from frozen capability requirements.")
        require(self.budget_unit is self.capability_requirements.budget.unit,
                "Budget unit differs from the frozen requirement.")
        require(self.authorized_model_selection_ref.sha256 == self.model_selection.wire_digest(),
                "Frozen model selection differs from its exact reference.")


@frozen_dto
class InferenceSpec(DTO):
    identity: InvocationIdentity
    inference_id: str
    owner_epoch: int
    expected_control_version: int
    model_selection: ModelSelection
    input_manifest_ref: ExactRef
    output_contract_ref: ExactRef
    visibility_policy_ref: ExactRef
    budget_grant_ref: ExactRef
    reservation_ref: ExactRef
    idempotency_key: str
    correlation_id: str
    capability_requirements: CapabilityRequirements

    def _validate(self) -> None:
        for value in (self.inference_id, self.idempotency_key, self.correlation_id):
            identifier(value)
        require(self.owner_epoch >= 1, "Owner epoch must be positive.")
        nonnegative(self.expected_control_version)
        require(self.capability_requirements.execution_mode is E.ExecutionMode.PMRS_MANAGED_LOOP,
                "A direct ModelProvider request is not a managed agent invocation.")
        require(all(getattr(self, name).project_id == self.identity.scope.project_id for name in
                    ("input_manifest_ref", "output_contract_ref", "visibility_policy_ref",
                     "budget_grant_ref", "reservation_ref")), "Inference references cross the request scope.")


@frozen_dto
class ModelDescription(DTO):
    selection: ModelSelection
    supported_parameter_names: tuple[str, ...]
    capabilities: CapabilityManifest
    actual_model: str | None

    def _validate(self) -> None:
        require(self.actual_model is None, "Describe reports requested support, not an observed inference model.")
        for name in self.supported_parameter_names:
            identifier(name)


@frozen_dto
class RequestValidation(DTO):
    request_digest: str
    capabilities: CapabilityManifest
    requires_inference_permit: bool

    def _validate(self) -> None:
        digest(self.request_digest)
        require(self.requires_inference_permit, "Request validation cannot waive trusted inference admission.")
