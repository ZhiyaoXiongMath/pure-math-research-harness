"""Exact read boundaries, atomic Fake commits, event admission and MAIN decisions."""
from __future__ import annotations

import base64
from dataclasses import replace
import unittest

from pmrh.ports.dto import core as C, enums as E, events as V, orchestration as O, storage as T
from pmrh.ports.dto.wire import ContractViolation
from . import fixtures as F, scenarios as Q
from .fake_engine import FakeOrchestrationEngine
from .fake_policy import FakeClock, trusted_policy
from .fake_runtime import FakeAgentRunner
from .fake_storage import FakeStore, FakeEvidenceRepository, FakeEventRepository, FakeUnitOfWork


class StorageAndEngineContracts(unittest.TestCase):
    def setUp(self):
        self.store = FakeStore()
        self.policy = trusted_policy()
        self.uow = FakeUnitOfWork(self.store, self.policy)
        self.evidence = FakeEvidenceRepository(self.store)
        self.events = FakeEventRepository(self.store)
        self.engine = FakeOrchestrationEngine(self.events, self.policy)

    def stage(self, batch, boundary=None):
        expected = T.VersionExpectation(boundary=boundary or self.store.boundary, owner_epoch=1, expected_control_version=7)
        tx = self.uow.begin(expected)
        self.uow.stage(tx, batch)
        return tx

    def commit(self, batch, boundary=None):
        tx = self.stage(batch, boundary)
        return self.uow.commit(tx, Q.permit(self.policy, self.uow.commit_intent(tx)))

    def test_read_missing_data_is_not_repair_or_write(self):
        self.assertEqual(self.evidence.read(F.ref("missing"), F.BOUNDARY).code, E.ErrorCode.NOT_FOUND)
        page = self.events.read_events(F.cursor(), F.BOUNDARY)
        self.assertEqual(page.status, E.PageStatus.EMPTY)
        self.assertEqual(page.next_cursor, F.cursor())
        self.assertEqual(self.store.writes, 0)
        self.assertEqual(self.store.reconciliations, 0)

    def test_atomic_commit_exact_read_slice_and_old_snapshot_boundary(self):
        first = self.commit(Q.batch())
        self.assertEqual(first.duplicate_status, E.DuplicateStatus.NEW)
        reference = Q.batch().evidence[0].evidence_ref
        self.assertEqual(self.evidence.read(reference, F.BOUNDARY).code, E.ErrorCode.NOT_FOUND)
        head = self.evidence.read(reference, first.boundary, max_bytes=3)
        self.assertEqual(base64.b64decode(head.content_base64), b"pay")
        self.commit(Q.batch(2))
        tail = self.evidence.read(reference, first.boundary, offset=3)
        self.assertEqual(base64.b64decode(tail.content_base64), b"load-1")
        self.assertEqual(tail.evidence_ref, reference)
        self.assertEqual(tail.boundary, first.boundary)
        before = self.store.writes
        self.evidence.read(reference, first.boundary)
        self.events.read_events(F.cursor(), first.boundary)
        self.assertEqual(self.store.writes, before)
        self.assertEqual(self.store.reconciliations, 0)

    def test_staged_writes_invisible_until_commit_and_rollback_has_no_effect(self):
        tx = self.stage(Q.batch())
        self.assertEqual(self.store.writes, 0)
        self.assertEqual(self.evidence.read(Q.batch().evidence[0].evidence_ref, self.store.boundary).code, E.ErrorCode.NOT_FOUND)
        receipt = self.uow.rollback(tx)
        self.assertEqual(receipt.state, E.TransactionState.ROLLED_BACK)
        self.assertEqual(self.uow.commit(tx, None).code, E.ErrorCode.TRANSACTION_CLOSED)
        self.assertEqual(self.store.boundary, F.BOUNDARY)

    def test_stale_compare_and_set_is_atomic_conflict_not_partial_commit(self):
        first, second = self.stage(Q.batch()), self.stage(Q.batch(2))
        self.uow.commit(first, Q.permit(self.policy, self.uow.commit_intent(first)))
        error = self.uow.commit(second, Q.permit(self.policy, self.uow.commit_intent(second)))
        self.assertEqual(error.code, E.ErrorCode.VERSION_CONFLICT)
        self.assertEqual(self.store.writes, 1)
        self.assertEqual(len(self.store.events), 1)
        self.assertNotIn(Q.batch(2).evidence[0].evidence_ref, self.store.evidence)

    def test_commit_requires_current_authorization_and_control(self):
        tx = self.stage(Q.batch())
        self.assertEqual(self.uow.commit(tx, None).code, E.ErrorCode.AUTHORIZATION_REQUIRED)
        permit = Q.permit(self.policy, self.uow.commit_intent(tx))
        self.policy.control = replace(self.policy.control, control_version=8)
        self.assertEqual(self.uow.commit(tx, permit).code, E.ErrorCode.STALE_CONTROL_VERSION)
        self.assertEqual(self.store.writes, 0)

    def test_idempotent_commit_preserves_original_commit_identity(self):
        first = self.commit(Q.batch())
        duplicate = self.commit(Q.batch(), F.BOUNDARY)
        self.assertEqual(duplicate.duplicate_status, E.DuplicateStatus.EXACT_DUPLICATE)
        self.assertEqual(duplicate.boundary, first.boundary)
        self.assertEqual(self.store.writes, 1)
        changed = replace(Q.batch(2), idempotency_key=Q.batch().idempotency_key)
        self.assertEqual(self.commit(changed).code, E.ErrorCode.IDEMPOTENCY_CONFLICT)
        self.assertEqual(self.store.writes, 1)

    def test_exact_revision_cannot_be_overwritten_with_new_bytes(self):
        self.commit(Q.batch())
        original = Q.batch().evidence[0].evidence_ref
        changed_ref = replace(F.ref("replacement", b"different"), object_id=original.object_id, revision=original.revision)
        changed = T.CommitBatch(operation_id="synthetic:replace-op", idempotency_key="synthetic:replace-key",
                                evidence=(T.EvidenceWrite(evidence_ref=changed_ref, content_base64=base64.b64encode(b"different").decode()),), events=())
        self.assertEqual(self.commit(changed).code, E.ErrorCode.IDEMPOTENCY_CONFLICT)
        self.assertEqual(self.store.evidence[original], b"payload-1")

    def test_corrupt_capture_is_refused_without_repair(self):
        with self.assertRaises(ContractViolation):
            T.EvidenceWrite(evidence_ref=F.ref("original"), content_base64=base64.b64encode(b"other").decode())
        committed = self.commit(Q.batch())
        reference = Q.batch().evidence[0].evidence_ref
        self.store.snapshots[committed.boundary][0][reference] = b"synthetic-corruption"
        before = self.store.writes
        self.assertEqual(self.evidence.read(reference, committed.boundary).code, E.ErrorCode.CORRUPT_CAPTURE)
        self.assertEqual(self.store.writes, before)
        self.assertEqual(self.store.reconciliations, 0)

    def test_explicit_cursor_gap_pagination_and_duplicate_delivery(self):
        self.commit(Q.batch())
        self.commit(Q.batch(2))
        first = self.events.read_events(F.cursor(), self.store.boundary, limit=1)
        second = self.events.read_events(first.next_cursor, self.store.boundary, limit=1)
        self.assertEqual(first.events[0].journal_sequence, 1)
        self.assertEqual(second.events[0].journal_sequence, 2)
        self.events.duplicate_event_ids = (first.events[0].event_id,)
        replay = self.events.read_events(second.next_cursor, self.store.boundary)
        self.assertEqual(replay.status, E.PageStatus.EMPTY)
        self.assertEqual(replay.duplicate_event_ids, (first.events[0].event_id,))
        self.events.first_available = 2
        gap = self.events.read_events(F.cursor(), self.store.boundary)
        self.assertEqual(gap.status, E.PageStatus.GAP)
        self.assertEqual(gap.next_cursor, F.cursor())
        self.assertEqual(gap.gap.resnapshot_ref, self.store.boundary.commit_ref)

    def test_bad_cursor_visibility_and_discontinuous_page_refused(self):
        self.commit(Q.batch())
        wrong = replace(F.cursor(), after_sequence=1, last_event_id="synthetic:wrong-id")
        self.assertEqual(self.events.read_events(wrong, self.store.boundary).code, E.ErrorCode.INVALID_CURSOR)
        boundary = replace(self.store.boundary, visibility_policy_ref=F.ref("different-visibility"))
        self.assertEqual(self.events.read_events(F.cursor(), boundary).code, E.ErrorCode.NOT_FOUND)
        self.commit(Q.batch(2))
        with self.assertRaises(ContractViolation):
            V.EventPage(requested_cursor=F.cursor(), next_cursor=replace(F.cursor(), after_sequence=2,
                                                                        last_event_id=self.store.events[-1].event_id),
                         status=E.PageStatus.COMPLETE, events=(self.store.events[-1],), duplicate_event_ids=(), gap=None)

    def test_engine_checks_actual_repository_not_COMMITTED_label(self):
        self.commit(Q.batch())
        event = self.store.events[0]
        forged = replace(event, event_type="synthetic:forged-control-event")
        self.assertEqual(self.engine.accept_event(forged, self.store.boundary).code, E.ErrorCode.UNTRUSTED_EVENT)
        self.assertEqual(self.engine.trigger_effects, 0)
        self.assertEqual(self.engine.accept_event(event, self.store.boundary).duplicate_status, E.DuplicateStatus.NEW)
        self.assertEqual(self.engine.accept_event(event, self.store.boundary).duplicate_status, E.DuplicateStatus.EXACT_DUPLICATE)
        self.assertEqual(self.engine.trigger_effects, 1)

    def test_engine_out_of_order_is_explicit_gap(self):
        self.commit(Q.batch())
        self.commit(Q.batch(2))
        self.assertEqual(self.engine.accept_event(self.store.events[-1], self.store.boundary).code, E.ErrorCode.EVENT_GAP)
        self.assertEqual(self.engine.trigger_effects, 0)

    def test_engine_never_selects_P08_or_P09_without_registered_MAIN_decision(self):
        runner = FakeAgentRunner(self.policy)
        prepared = runner.prepare(F.spec())
        action = O.TechnicalAction(action_id="synthetic:chosen-action", kind=E.TechnicalActionKind.DISPATCH_PREPARED,
                                   prepared=prepared, existing_handle=None)
        decision = F.ref("main-choice")
        request = O.ActionRequest(operation_id="synthetic:actions", control=self.policy.control, boundary=self.store.boundary,
                                   main_decision_ref=decision, proposed_actions=(action,), limit=1)
        permit = Q.permit(self.policy, self.engine.action_intent(request))
        self.assertEqual(self.engine.next_actions(request, permit).code, E.ErrorCode.AUTHORIZATION_REQUIRED)
        self.engine.decisions[decision] = (action,)
        plan = self.engine.next_actions(request, permit)
        self.assertEqual(plan.actions, (action,))
        self.assertFalse(plan.generates_research_decisions)
        self.assertEqual(runner.send_effects, 0)
        self.assertEqual(self.engine.next_actions(request, permit), plan)
        self.assertEqual(self.engine.plan_effects, 1)

    def test_checkpoint_cannot_override_quiescence_or_replay_dispatch(self):
        runner = FakeAgentRunner(self.policy)
        prepared = runner.prepare(F.spec())
        runner.dispatch_outcome = E.DispatchState.SEND_OUTCOME_UNKNOWN
        handle = runner.start(prepared, Q.permit(self.policy, runner.start_intent(prepared))).handle
        self.engine.in_flight = (handle,)
        checkpoint = self.engine.checkpoint()
        request = O.QuiesceRequest(operation_id="synthetic:pause", control=self.policy.control, reason="PAUSE")
        receipt = self.engine.quiesce(request, Q.permit(self.policy, self.engine.quiesce_intent(request)))
        self.assertTrue(receipt.new_dispatch_blocked)
        self.assertEqual(receipt.termination, "NOT_IMPLIED")
        resumed = self.engine.resume_execution(checkpoint, Q.permit(self.policy, self.engine.resume_intent(checkpoint)))
        self.assertEqual(resumed.actions, ())
        self.assertTrue(self.engine.quiesced)
        self.assertEqual(self.engine.in_flight, (handle,))
        self.assertEqual(runner.send_effects, 1)
        permit = Q.permit(self.policy, self.engine.resume_intent(checkpoint))
        self.policy.control = replace(self.policy.control, owner_epoch=2, control_version=8)
        self.assertEqual(self.engine.resume_execution(checkpoint, permit).code, E.ErrorCode.STALE_CONTROL_VERSION)

    def test_fake_clock_is_injectable_and_does_not_read_wall_time(self):
        clock = FakeClock()
        self.assertEqual(clock.now(), F.NOW)
        self.assertEqual(clock.monotonic_ns(), 0)
        clock.advance(2)
        self.assertEqual(clock.now().utc, "2026-10-13T00:00:02Z")
        self.assertEqual(clock.monotonic_ns(), 2_000_000_000)
        with self.assertRaises(ValueError):
            clock.advance(-1)
