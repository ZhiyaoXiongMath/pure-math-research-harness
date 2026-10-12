"""Technical orchestration inputs; Research MAIN chooses the scientific work."""
from __future__ import annotations

from typing import Literal

from . import enums as E
from .core import ControlSnapshot, ExactRef, Scope
from .events import EventCursor
from .execution import InvocationHandle, PreparedInvocation
from .storage import ReadBoundary
from .wire import DTO, frozen_dto, identifier, require


@frozen_dto
class TechnicalAction(DTO):
    action_id: str
    kind: E.TechnicalActionKind
    prepared: PreparedInvocation | None
    existing_handle: InvocationHandle | None

    def _validate(self) -> None:
        identifier(self.action_id)
        if self.kind is E.TechnicalActionKind.DISPATCH_PREPARED:
            require(self.prepared is not None and self.existing_handle is None,
                    "Dispatch action requires an already frozen MAIN-selected invocation.")
        elif self.kind in (E.TechnicalActionKind.CAPTURE_EXISTING, E.TechnicalActionKind.REATTACH_EXISTING):
            require(self.existing_handle is not None and self.prepared is None,
                    "Recovery action requires an existing execution, not a new request.")
        else:
            require(self.prepared is None and self.existing_handle is None, "Wait does not imply a dispatch.")


@frozen_dto
class ActionRequest(DTO):
    operation_id: str
    control: ControlSnapshot
    boundary: ReadBoundary
    main_decision_ref: ExactRef | None
    proposed_actions: tuple[TechnicalAction, ...]
    limit: int

    def _validate(self) -> None:
        identifier(self.operation_id)
        require(self.control.scope == self.boundary.scope, "Control and evidence scopes disagree.")
        require(1 <= self.limit <= 256, "Action output must be explicitly bounded.")
        require(len(self.proposed_actions) <= self.limit, "Proposed actions exceed the declared bound.")
        require(len({a.action_id for a in self.proposed_actions}) == len(self.proposed_actions),
                "Action IDs must be unique.")
        if self.proposed_actions:
            require(self.main_decision_ref is not None, "Actions require an exact MAIN decision reference.")
        for action in self.proposed_actions:
            if action.prepared is not None:
                require(action.prepared.spec.identity().scope == self.control.scope,
                        "A dispatch action crosses the selected instance.")
            if action.existing_handle is not None:
                require(action.existing_handle.identity.scope == self.control.scope,
                        "An existing execution crosses the selected instance.")


@frozen_dto
class ActionPlan(DTO):
    operation_id: str
    control: ControlSnapshot
    actions: tuple[TechnicalAction, ...]
    decision_ref: ExactRef | None
    generates_research_decisions: Literal[False] = False

    def _validate(self) -> None:
        identifier(self.operation_id)
        if self.actions:
            require(self.decision_ref is not None, "Actions cannot originate from stage-number rules.")


@frozen_dto
class EventAcceptance(DTO):
    event_id: str
    duplicate_status: E.DuplicateStatus
    boundary: ReadBoundary

    def _validate(self) -> None:
        identifier(self.event_id)


@frozen_dto
class EngineCheckpoint(DTO):
    checkpoint_id: str
    engine_schema_version: Literal["pmrh.execution-checkpoint/1"]
    control: ControlSnapshot
    boundary: ReadBoundary
    event_cursor: EventCursor
    accepted_event_ids: tuple[str, ...]
    in_flight_handles: tuple[InvocationHandle, ...]
    quiesced: bool

    def _validate(self) -> None:
        identifier(self.checkpoint_id)
        require(self.control.scope == self.boundary.scope == self.event_cursor.scope,
                "Checkpoint scopes disagree.")
        require(self.event_cursor.stream_kind is E.StreamKind.JOURNAL
                and self.event_cursor.stream_id == self.boundary.journal_id,
                "Checkpoint cursor must bind the authoritative journal.")
        require(self.event_cursor.after_sequence <= self.boundary.through_journal_sequence,
                "Checkpoint cannot advance beyond the evidence boundary.")
        for event_id in self.accepted_event_ids:
            identifier(event_id)
        require(all(h.identity.scope == self.control.scope for h in self.in_flight_handles),
                "Checkpoint contains an execution from another instance.")


@frozen_dto
class QuiesceRequest(DTO):
    operation_id: str
    control: ControlSnapshot
    reason: Literal["PAUSE", "END", "BACKEND_CHANGE"]

    def _validate(self) -> None:
        identifier(self.operation_id)


@frozen_dto
class QuiesceReceipt(DTO):
    scope: Scope
    new_dispatch_blocked: Literal[True]
    in_flight_handles: tuple[InvocationHandle, ...]
    termination: Literal["NOT_IMPLIED"] = "NOT_IMPLIED"
