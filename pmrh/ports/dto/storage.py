"""Read boundaries and future atomic writes. No connection, Store or file handle."""
from __future__ import annotations

import base64
import binascii
import hashlib

from . import enums as E
from .core import ExactRef, Scope, TimePoint
from .events import EventEnvelope
from .wire import DTO, digest, frozen_dto, identifier, nonnegative, require

MAX_EVIDENCE_BYTES = 1024 * 1024


def evidence_bytes(encoded: str) -> bytes:
    require(len(encoded) <= 4 * ((MAX_EVIDENCE_BYTES + 2) // 3), "Evidence slice exceeds byte bound.")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        require(False, "Evidence is not canonical base64.", E.ErrorCode.CORRUPT_CAPTURE)
    require(base64.b64encode(raw).decode("ascii") == encoded and len(raw) <= MAX_EVIDENCE_BYTES,
            "Evidence encoding is noncanonical or exceeds the byte bound.", E.ErrorCode.CORRUPT_CAPTURE)
    return raw


@frozen_dto
class ReadBoundary(DTO):
    scope: Scope
    journal_id: str
    commit_ref: ExactRef
    through_journal_sequence: int
    visibility_policy_ref: ExactRef

    def _validate(self) -> None:
        identifier(self.journal_id)
        nonnegative(self.through_journal_sequence)
        require(self.commit_ref.project_id == self.scope.project_id
                and self.visibility_policy_ref.project_id == self.scope.project_id,
                "Read boundary references cross the project.")


@frozen_dto
class EvidenceSlice(DTO):
    evidence_ref: ExactRef
    boundary: ReadBoundary
    offset: int
    total_bytes: int
    content_base64: str
    slice_sha256: str

    def _validate(self) -> None:
        nonnegative(self.offset)
        nonnegative(self.total_bytes)
        raw = evidence_bytes(self.content_base64)
        require(self.offset + len(raw) <= self.total_bytes, "Evidence slice exceeds the original extent.")
        require(hashlib.sha256(raw).hexdigest() == self.slice_sha256,
                "Evidence slice digest mismatch.", E.ErrorCode.CORRUPT_CAPTURE)
        if self.offset == 0 and len(raw) == self.total_bytes:
            require(self.slice_sha256 == self.evidence_ref.sha256,
                    "Full evidence digest mismatch.", E.ErrorCode.CORRUPT_CAPTURE)
        require(self.evidence_ref.project_id == self.boundary.scope.project_id,
                "Evidence is outside the project read boundary.")


@frozen_dto
class EvidenceWrite(DTO):
    evidence_ref: ExactRef
    content_base64: str

    def _validate(self) -> None:
        require(hashlib.sha256(evidence_bytes(self.content_base64)).hexdigest() == self.evidence_ref.sha256,
                "Immutable evidence bytes do not match their declared digest.", E.ErrorCode.CORRUPT_CAPTURE)


@frozen_dto
class VersionExpectation(DTO):
    boundary: ReadBoundary
    owner_epoch: int
    expected_control_version: int

    def _validate(self) -> None:
        require(self.owner_epoch >= 1, "Owner epoch must be positive.")
        nonnegative(self.expected_control_version)


@frozen_dto
class TransactionHandle(DTO):
    transaction_id: str
    expected: VersionExpectation

    def _validate(self) -> None:
        identifier(self.transaction_id)


@frozen_dto
class CommitBatch(DTO):
    """Proposed raw evidence and observation events, not yet committed authority."""
    operation_id: str
    idempotency_key: str
    evidence: tuple[EvidenceWrite, ...]
    events: tuple[EventEnvelope, ...]

    def _validate(self) -> None:
        identifier(self.operation_id)
        identifier(self.idempotency_key)
        require(bool(self.evidence or self.events), "Empty commits are not implicit maintenance.")
        require(len({(r.evidence_ref.project_id, r.evidence_ref.object_id, r.evidence_ref.revision)
                     for r in self.evidence}) == len(self.evidence), "Batch repeats an exact evidence identity.")
        require(len({e.event_id for e in self.events}) == len(self.events), "Batch repeats an event ID.")
        require(all(e.status is E.EventStatus.OBSERVATION for e in self.events),
                "Only the committing repository may attach authoritative commit metadata.")


@frozen_dto
class StagingReceipt(DTO):
    transaction: TransactionHandle
    batch_digest: str
    state: E.TransactionState

    def _validate(self) -> None:
        digest(self.batch_digest)
        require(self.state is E.TransactionState.OPEN, "Staging is not a commit.")


@frozen_dto
class CommitReceipt(DTO):
    operation_id: str
    batch_digest: str
    previous_boundary: ReadBoundary
    boundary: ReadBoundary
    duplicate_status: E.DuplicateStatus
    committed_at: TimePoint
    event_ids: tuple[str, ...]

    def _validate(self) -> None:
        identifier(self.operation_id)
        digest(self.batch_digest)
        require(self.previous_boundary.scope == self.boundary.scope
                and self.previous_boundary.journal_id == self.boundary.journal_id,
                "A transaction cannot cross project or journal boundaries.")
        require(self.boundary.through_journal_sequence >= self.previous_boundary.through_journal_sequence,
                "Committed journal sequence cannot regress.")
        for event_id in self.event_ids:
            identifier(event_id)


@frozen_dto
class RollbackReceipt(DTO):
    transaction_id: str
    state: E.TransactionState

    def _validate(self) -> None:
        identifier(self.transaction_id)
        require(self.state is E.TransactionState.ROLLED_BACK, "Rollback receipt must say rolled back.")


@frozen_dto
class EventVerification(DTO):
    event_id: str
    boundary: ReadBoundary
    verified: bool

    def _validate(self) -> None:
        identifier(self.event_id)
        require(self.verified, "Unverified events return UNTRUSTED_EVENT, not a success receipt.")
