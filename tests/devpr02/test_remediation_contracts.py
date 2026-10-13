"""MAIN-directed REV02 wire, stream and inference-identity counterexamples.

Synthetic values only. Original review probe IDs are retained in test comments.
No backend, storage adapter, network, or research workspace is used.
"""
from __future__ import annotations

import base64
from dataclasses import replace
import json
import unittest

from pmrh.ports.dto import core as C, enums as E, events as V, specs as S, storage as T
from pmrh.ports.dto.wire import ContractViolation, MAX_JSON_BYTES, SCHEMA_VERSION, decode_wire
from . import fixtures as F, scenarios as Q
from .fake_policy import trusted_policy
from .fake_runtime import FakeAgentRunner, FakeModelProvider


def batch(count, size=1024):
    raw = b'x' * size
    writes = tuple(T.EvidenceWrite(evidence_ref=F.ref('large-' + str(i), raw),
                                  content_base64=base64.b64encode(raw).decode()) for i in range(count))
    value = T.CommitBatch(operation_id='synthetic:large-op', idempotency_key='synthetic:large-key',
                          evidence=writes, events=())
    # Build the adversarial aggregate independently of the encoder under test.
    wire = dict(dto_type='CommitBatch', schema_version=SCHEMA_VERSION,
                operation_id=value.operation_id, idempotency_key=value.idempotency_key,
                evidence=[item.to_wire() for item in writes], events=[])
    return value, wire


def page(kind):
    spec = F.inference()
    stream = F.spec().invocation_id if kind is E.StreamKind.RUNNER else spec.inference_id
    cursor = F.cursor(kind, stream)
    items = []
    for sequence in (1, 2):
        env = replace(F.envelope(identity=spec.identity), event_id='synthetic:event-' + str(sequence))
        if kind is E.StreamKind.RUNNER:
            item = V.RunnerEvent(sequence=sequence, kind=E.RunnerEventKind.STARTED,
                                 envelope=env, raw_event_ref=env.raw_evidence_ref)
        else:
            item = V.ProviderEvent(sequence=sequence, inference_id=stream,
                                   kind=E.ProviderEventKind.REQUEST_OBSERVED, envelope=env,
                                   raw_event_ref=env.raw_evidence_ref, actual_model_id=F.unknown())
        items.append(item)
    cls = V.RunnerEventPage if kind is E.StreamKind.RUNNER else V.ProviderEventPage
    return cls(requested_cursor=cursor, next_cursor=replace(cursor, after_sequence=2,
               last_event_id=items[-1].envelope.event_id), status=E.PageStatus.COMPLETE,
               events=tuple(items), duplicate_event_ids=(), gap=None)


class WireRemediation(unittest.TestCase):
    def test_small_multi_slice_roundtrip_all_public_boundaries(self):
        value, wire = batch(3)
        self.assertEqual(T.CommitBatch.from_wire(wire), value)
        self.assertEqual(decode_wire(wire), value)
        self.assertEqual(T.CommitBatch.from_json(value.to_json()), value)
        self.assertEqual(value.to_wire(), wire)

    def test_WIRE19_20_21_aggregate_decode_limits_are_identical(self):
        value, wire = batch(7, T.MAX_EVIDENCE_BYTES)
        text = json.dumps(wire, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        self.assertGreater(len(text.encode()), MAX_JSON_BYTES)
        for read in (lambda: T.CommitBatch.from_wire(wire), lambda: decode_wire(wire),
                     lambda: T.CommitBatch.from_json(text)):
            with self.subTest(entry=read), self.assertRaises(ContractViolation) as failure:
                read()
            self.assertEqual(failure.exception.code, E.ErrorCode.INVALID_FIELD)

    def test_WIRE22_encoder_refuses_unreadable_aggregate_including_digest(self):
        value, _ = batch(7, T.MAX_EVIDENCE_BYTES)
        for encode in (value.to_wire, value.to_json, value.wire_digest):
            with self.subTest(entry=encode), self.assertRaises(ContractViolation) as failure:
                encode()
            self.assertEqual(failure.exception.code, E.ErrorCode.INVALID_FIELD)

    def test_exact_8MiB_boundary_roundtrip_and_one_byte_over(self):
        value, wire = batch(6, T.MAX_EVIDENCE_BYTES)
        canonical = lambda w: json.dumps(w, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        over = len(canonical(wire).encode()) - MAX_JSON_BYTES
        # Base64 changes by four bytes per three source bytes. Adjust one legal
        # slice, then use <=3 identifier characters to hit the aggregate limit.
        raw = b'x' * (T.MAX_EVIDENCE_BYTES - 3 * ((over + 3) // 4))
        tail = T.EvidenceWrite(evidence_ref=F.ref('large-5', raw),
                              content_base64=base64.b64encode(raw).decode())
        wire['evidence'][-1] = tail.to_wire()
        padding = MAX_JSON_BYTES - len(canonical(wire).encode())
        self.assertTrue(0 <= padding < 4)
        exact = replace(value, evidence=value.evidence[:-1] + (tail,),
                        operation_id=value.operation_id + 'p' * padding)
        text = exact.to_json()
        self.assertEqual(len(text.encode()), MAX_JSON_BYTES)
        self.assertEqual(T.CommitBatch.from_json(text), exact)
        self.assertEqual(decode_wire(exact.to_wire()), exact)
        bad = replace(exact, operation_id=exact.operation_id + 'x')
        bad_wire = dict(exact.to_wire(), operation_id=bad.operation_id)
        for entry in (bad.to_wire, bad.to_json, lambda: T.CommitBatch.from_wire(bad_wire),
                      lambda: decode_wire(bad_wire), lambda: T.CommitBatch.from_json(canonical(bad_wire))):
            with self.subTest(entry=entry), self.assertRaises(ContractViolation):
                entry()

    def test_unicode_and_escaped_content_use_UTF8_canonical_size(self):
        unit = '\n"\\汉😀'
        params = tuple(S.ModelParameter(name='p' + str(i), value=unit * 128) for i in range(4096))
        value = replace(F.model(), parameters=params)
        text = value.to_json()
        self.assertLessEqual(len(text.encode('utf-8')), MAX_JSON_BYTES)
        self.assertEqual(S.ModelSelection.from_json(text), value)
        params = tuple(replace(item, value=unit * 160) for item in params)
        bad = replace(value, parameters=params)
        wire = F.model().to_wire(); wire['parameters'] = [item.to_wire() for item in params]
        bad_text = json.dumps(wire, ensure_ascii=False, separators=(',', ':'))
        self.assertLess(len(bad_text), MAX_JSON_BYTES)
        self.assertGreater(len(bad_text.encode('utf-8')), MAX_JSON_BYTES)
        for entry in (bad.to_json, lambda: S.ModelSelection.from_wire(wire),
                      lambda: decode_wire(wire), lambda: S.ModelSelection.from_json(bad_text)):
            with self.assertRaises(ContractViolation):
                entry()

    def test_deep_and_cyclic_object_input_fails_with_contract_error(self):
        nested = []; nested.append(nested)
        wire = F.SCOPE.to_wire(); wire['injected'] = nested
        for entry in (lambda: C.Scope.from_wire(wire), lambda: decode_wire(wire)):
            with self.assertRaises(ContractViolation):
                entry()
        with self.assertRaises(ContractViolation):
            C.Scope.from_json('[' * 1000 + '0' + ']' * 1000)

    def test_aggregate_node_budget_is_not_a_per_slice_check(self):
        wire = F.SCOPE.to_wire()
        wire['injected'] = [[None] * 4096] * 128
        for entry in (lambda: C.Scope.from_wire(wire), lambda: decode_wire(wire),
                      lambda: C.Scope.from_json(json.dumps(wire))):
            with self.assertRaises(ContractViolation):
                entry()


class EventRemediation(unittest.TestCase):
    def test_correct_stream_multi_event_pages_roundtrip(self):
        for kind in (E.StreamKind.RUNNER, E.StreamKind.PROVIDER):
            value = page(kind)
            self.assertEqual(type(value).from_json(value.to_json()), value)
            self.assertEqual(decode_wire(value.to_wire()), value)

    def test_EVENT_RUNNER_cross_and_mixed_invocations_rejected(self):
        value = page(E.StreamKind.RUNNER)
        wrong = replace(value.events[1], envelope=replace(value.events[1].envelope,
                                                        invocation_id='synthetic:other'))
        for events in ((replace(wrong, sequence=1), wrong), (value.events[0], wrong)):
            with self.assertRaises(ContractViolation):
                replace(value, events=events)

    def test_EVENT_PROVIDER_cross_and_mixed_inferences_rejected(self):
        value = page(E.StreamKind.PROVIDER)
        wrong = replace(value.events[1], inference_id='synthetic:other')
        for events in ((replace(wrong, sequence=1), wrong), (value.events[0], wrong)):
            with self.assertRaises(ContractViolation):
                replace(value, events=events)

    def test_cross_stream_rejected_by_both_wire_and_JSON_entrypoints(self):
        for kind in (E.StreamKind.RUNNER, E.StreamKind.PROVIDER):
            value = page(kind); wire = value.to_wire()
            if kind is E.StreamKind.RUNNER:
                wire['events'][1]['envelope']['invocation_id'] = 'synthetic:other'
            else:
                wire['events'][1]['inference_id'] = 'synthetic:other'
            for entry in (lambda: type(value).from_wire(wire), lambda: decode_wire(wire),
                          lambda: type(value).from_json(json.dumps(wire))):
                with self.assertRaises(ContractViolation):
                    entry()

    def test_fake_runner_return_path_cannot_emit_corrupted_stream(self):
        policy = trusted_policy(); runner = FakeAgentRunner(policy)
        prepared = runner.prepare(F.spec())
        handle = runner.start(prepared, Q.permit(policy, runner.start_intent(prepared))).handle
        cursor = F.cursor(E.StreamKind.RUNNER, handle.identity.invocation_id)
        good = runner.events(handle, cursor)
        self.assertEqual(good.events[0].envelope.invocation_id, cursor.stream_id)
        event = good.events[0]
        runner.event_records[handle.identity.invocation_id] = (
            replace(event, envelope=replace(event.envelope, invocation_id='synthetic:other')),)
        with self.assertRaises(ContractViolation):
            runner.events(handle, cursor)
        self.assertEqual(runner.send_effects, 1)

    def test_fake_provider_events_make_only_their_own_valid_page(self):
        policy = trusted_policy(mode=E.ExecutionMode.PMRS_MANAGED_LOOP)
        provider = FakeModelProvider(policy); spec = F.inference()
        events = tuple(provider.stream(spec, Q.permit(policy, provider.stream_intent(spec))))
        cursor = F.cursor(E.StreamKind.PROVIDER, spec.inference_id)
        value = V.ProviderEventPage(requested_cursor=cursor,
            next_cursor=replace(cursor, after_sequence=1, last_event_id=events[-1].envelope.event_id),
            status=E.PageStatus.COMPLETE, events=events, duplicate_event_ids=(), gap=None)
        self.assertEqual(decode_wire(value.to_wire()), value)
        with self.assertRaises(ContractViolation):
            replace(value, requested_cursor=replace(cursor, stream_id='synthetic:other'),
                    next_cursor=replace(value.next_cursor, stream_id='synthetic:other'))


class UnknownRemediation(unittest.TestCase):
    def setUp(self):
        self.policy = trusted_policy(mode=E.ExecutionMode.PMRS_MANAGED_LOOP)
        self.provider = FakeModelProvider(self.policy)
        self.spec = F.inference()

    def send(self, spec):
        return tuple(self.provider.stream(spec, Q.permit(self.policy, self.provider.stream_intent(spec))))[0]

    def check_identity(self, error, spec, operation=E.Operation.STREAM):
        self.assertIsInstance(error, C.ErrorEnvelope)
        self.assertEqual(error.operation, operation)
        self.assertEqual(error.operation_id, spec.inference_id)
        self.assertEqual(error.identity, spec.identity)
        self.assertEqual(decode_wire(error.to_wire()), error)
        self.assertEqual(C.ErrorEnvelope.from_json(error.to_json()), error)

    def test_UNKNOWN02_distinct_inferences_remain_distinct_without_remote_ids(self):
        self.provider.dispatch_outcome = E.DispatchState.SEND_OUTCOME_UNKNOWN
        other = replace(self.spec, inference_id='synthetic:inference-2', idempotency_key='synthetic:key-2')
        first, second = self.send(self.spec), self.send(other)
        for error, spec in ((first, self.spec), (second, other)):
            self.check_identity(error, spec)
            self.assertEqual(error.code, E.ErrorCode.SEND_OUTCOME_UNKNOWN)
            self.assertEqual(error.recovery_safety, E.RecoverySafety.DO_NOT_RESEND)
        self.assertNotEqual(first, second)
        self.assertEqual(len(self.provider.requests), 0)
        self.assertEqual(self.provider.send_effects, 2)

    def test_UNKNOWN01_key_change_and_identical_retry_do_not_resend(self):
        self.provider.dispatch_outcome = E.DispatchState.SEND_OUTCOME_UNKNOWN
        first = self.send(self.spec)
        self.assertEqual(self.send(self.spec), first)
        new_key = replace(self.spec, idempotency_key='synthetic:key-2')
        conflict = self.send(new_key)
        self.check_identity(conflict, new_key)
        self.assertEqual(conflict.code, E.ErrorCode.IDEMPOTENCY_CONFLICT)
        self.assertEqual(self.provider.send_effects, 1)
        self.assertEqual(len(self.provider.requests), 0)

    def test_same_key_changed_payload_conflict_identifies_refused_inference(self):
        self.send(self.spec)
        other = replace(self.spec, inference_id='synthetic:inference-2')
        error = self.send(other)
        self.check_identity(error, other)
        self.assertEqual(error.code, E.ErrorCode.IDEMPOTENCY_CONFLICT)
        self.assertEqual(self.provider.send_effects, 1)

    def test_confirmed_NOT_SENT_retains_local_identity_and_evidence(self):
        self.provider.dispatch_outcome = E.DispatchState.NOT_SENT
        error = self.send(self.spec)
        self.check_identity(error, self.spec)
        self.assertEqual(error.code, E.ErrorCode.NOT_SENT)
        self.assertTrue(error.raw_evidence_refs)
        self.assertEqual(self.provider.send_effects, 0)

    def test_early_validation_authorization_and_stale_refusals_keep_spec_identity(self):
        error = tuple(self.provider.stream(self.spec, None))[0]
        self.check_identity(error, self.spec)
        self.assertEqual(error.code, E.ErrorCode.AUTHORIZATION_REQUIRED)
        permit = Q.permit(self.policy, self.provider.stream_intent(self.spec))
        self.policy.control = replace(self.policy.control, control_version=8)
        error = tuple(self.provider.stream(self.spec, permit))[0]
        self.check_identity(error, self.spec)
        self.assertEqual(error.code, E.ErrorCode.STALE_CONTROL_VERSION)
        unsupported = replace(self.spec, model_selection=replace(self.spec.model_selection, model_id='synthetic:unsupported'))
        error = self.provider.validate_request(unsupported)
        self.check_identity(error, unsupported, E.Operation.VALIDATE_REQUEST)
        error = tuple(self.provider.stream(unsupported, None))[0]
        self.check_identity(error, unsupported)
        self.assertEqual(error.code, E.ErrorCode.UNSUPPORTED_CAPABILITY)
        self.assertEqual(self.provider.send_effects, 0)

    def test_capability_validation_refusal_retains_inference(self):
        self.provider.manifest = F.manifest(E.ExecutionMode.MANAGED_AGENT)
        error = self.provider.validate_request(self.spec)
        self.check_identity(error, self.spec, E.Operation.VALIDATE_REQUEST)
        error = tuple(self.provider.stream(self.spec, None))[0]
        self.check_identity(error, self.spec)
        self.assertEqual(error.code, E.ErrorCode.UNSUPPORTED_CAPABILITY)
        self.assertEqual(self.provider.send_effects, 0)

    def test_known_inference_error_cannot_drop_operation_id_on_wire(self):
        self.provider.dispatch_outcome = E.DispatchState.SEND_OUTCOME_UNKNOWN
        error = self.send(self.spec)
        with self.assertRaises(ContractViolation):
            replace(error, operation_id=None)
        wire = error.to_wire(); wire['operation_id'] = None
        with self.assertRaises(ContractViolation):
            C.ErrorEnvelope.from_wire(wire)
        with self.assertRaises(ContractViolation):
            C.port_error(E.ErrorCode.SEND_OUTCOME_UNKNOWN, E.Operation.STREAM, identity=self.spec.identity)
