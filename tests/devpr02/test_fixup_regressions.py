"""Developer review regressions supplement, never replace, the initial negative tests."""
from dataclasses import replace
import json
from pathlib import Path
import unittest

from pmrh.ports.dto import core as C, enums as E, specs as S, storage as T
from pmrh.ports.dto.wire import ContractViolation
from scripts import architecture_deps
from . import fixtures as F, scenarios as Q
from .fake_policy import trusted_policy
from .fake_runtime import FakeModelProvider
from .fake_storage import FakeStore, FakeUnitOfWork


class FixupRegressions(unittest.TestCase):
    def test_nested_missing_member_preserves_precise_error_code(self):
        wire = F.spec().to_wire()
        del wire["model_selection"]["response_schema_ref"]["revision"]
        with self.assertRaises(ContractViolation) as error:
            S.AgentInvocationSpec.from_wire(wire)
        self.assertEqual(error.exception.code, E.ErrorCode.MISSING_FIELD)

    def test_oversized_integer_is_rejected_as_contract_error(self):
        with self.assertRaises(ContractViolation):
            S.ModelParameter(name="limit", value=2 ** 63)
        text = '{"value":' + "1" * 10000 + '}'
        with self.assertRaises(ContractViolation):
            C.Quantity.from_json(text)

    def test_model_refusal_is_a_provider_observation_not_authorization_failure(self):
        policy = trusted_policy(mode=E.ExecutionMode.PMRS_MANAGED_LOOP)
        provider = FakeModelProvider(policy)
        provider.scripted_event_kind = E.ProviderEventKind.REFUSAL
        spec = F.inference()
        event = tuple(provider.stream(spec, Q.permit(policy, provider.stream_intent(spec))))[0]
        self.assertEqual(event.kind, E.ProviderEventKind.REFUSAL)
        self.assertFalse(isinstance(event, C.ErrorEnvelope))
        self.assertEqual(event.envelope.status, E.EventStatus.OBSERVATION)
        self.assertEqual(provider.send_effects, 1)

    def test_commit_permit_cannot_be_retargeted_to_another_expected_snapshot(self):
        store, policy = FakeStore(), trusted_policy()
        uow = FakeUnitOfWork(store, policy)
        def stage(batch, boundary):
            tx = uow.begin(T.VersionExpectation(boundary=boundary, owner_epoch=1, expected_control_version=7))
            uow.stage(tx, batch)
            return tx
        old = stage(Q.batch(2), F.BOUNDARY)
        permit = Q.permit(policy, uow.commit_intent(old))
        first = stage(Q.batch(), store.boundary)
        self.assertIsInstance(uow.commit(first, Q.permit(policy, uow.commit_intent(first))), T.CommitReceipt)
        retargeted = stage(Q.batch(2), store.boundary)
        self.assertEqual(uow.commit(retargeted, permit).code, E.ErrorCode.AUTHORIZATION_REQUIRED)
        self.assertEqual(store.writes, 1)

    def test_ports_do_not_introduce_a_cyclic_dependency_component(self):
        root = Path(__file__).resolve().parents[2]
        policy = json.loads((root / "config/architecture-exceptions.json").read_text())
        result = architecture_deps.run(root, policy)
        cycles = [group for group in result["strongly_connected_components"]
                  if len(group) > 1 and any(path.startswith("pmrh/ports/") for path in group)]
        self.assertEqual(cycles, [])
