"""Explicit synthetic authority only; storage, reducers and publisher are real."""
import base64
from dataclasses import replace
from pathlib import Path
import subprocess
import sys

from pmrh.adapters.storage import format as F
from pmrh.adapters.storage.repositories import DiskStorage, TrustedReadContext
from pmrh.application.unit_of_work import UnitOfWork
from pmrh.ports.dto import core as C, control as P, enums as E, events as V, storage as T
from research_studio.store import Store
from research_studio.engine import Engine
from research_studio.util import canonical, sha

NOW = C.TimePoint(utc='2026-10-15T00:00:00Z', clock_source=E.ClockSource.SYNTHETIC)
UNOBSERVED = C.ObservedIdentifier(kind=E.ObservationKind.UNOBSERVED, value=None)


class LocalPolicy:
    """Fixture decisions are independently registered, current and revocable.

    This is not production authentication, budgets or epoch fencing. Mutation
    in concurrency tests holds the same project lock as commit verification.
    """
    def __init__(self, store, scope):
        self.scope = scope
        self.enabled = True
        self.epoch = 1
        self.version = 0
        self.issued = {}
        self.store = store
        self.grant = F.exact(scope.project_id, 'synthetic:grant', store.put_blob(b'SYNTHETIC_TEST_ONLY grant'))
        self.principal = F.exact(scope.project_id, 'synthetic:principal', store.put_blob(b'SYNTHETIC_TEST_ONLY principal'))

    def intent(self, staged, batch):
        return P.OperationIntent(scope=staged.transaction.expected.boundary.scope, operation=E.Operation.COMMIT,
            operation_id=batch.operation_id, payload_digest=staged.wire_digest(),
            owner_epoch=staged.transaction.expected.owner_epoch,
            expected_control_version=staged.transaction.expected.expected_control_version,
            budget_grant_ref=self.grant, budget_unit=E.BudgetUnit.AGENT_INVOCATION, budget_units_requested=0,
            reservation_ref=None, capability_requirements=None, capability_manifest_ref=None, claimed_principal_ref=None)

    def authorize(self, intent):
        ref = F.exact(self.scope.project_id, 'synthetic:decision:'+str(len(self.issued)),
                      self.store.put_blob(canonical(intent.to_wire())))
        permit = P.OperationPermit(permit_id='synthetic:permit:'+str(len(self.issued)), decision_ref=ref,
            principal_ref=self.principal, intent=intent, issued_at=NOW,
            expires_at=C.TimePoint(utc='2026-10-16T00:00:00Z', clock_source=E.ClockSource.SYNTHETIC))
        self.issued[permit.permit_id] = permit
        return permit

    def verify(self, permit, intent):
        error = None
        if not self.enabled or intent.scope != self.scope or intent.budget_grant_ref != self.grant:
            error = E.ErrorCode.AUTHORIZATION_REQUIRED
        elif intent.owner_epoch != self.epoch or intent.expected_control_version != self.version:
            error = E.ErrorCode.STALE_CONTROL_VERSION
        elif permit is None or self.issued.get(permit.permit_id) != permit or permit.intent != intent:
            error = E.ErrorCode.AUTHORIZATION_REQUIRED
        if error:
            return C.port_error(error, E.Operation.COMMIT, scope=intent.scope)
        return P.PermitVerification(intent=intent, decision_ref=permit.decision_ref,
                                    checked_at=NOW, status=E.DecisionStatus.ALLOWED)


def assemble(store, iid, *, install=False):
    scope = C.Scope(project_id=store.read_snapshot()['project_id'], instance_id=iid)
    policy = LocalPolicy(store, scope)
    context = TrustedReadContext(scope, F.policy_bytes(scope), lambda: policy.enabled,
                                 (lambda: True) if install else None)
    storage = DiskStorage(store.root, context=context)
    if install:
        boundary = storage.bind_synthetic_scope()
        assert isinstance(boundary, T.ReadBoundary), boundary
    uow = UnitOfWork(storage, policy=policy, intent_builder=policy.intent)
    return storage, policy, uow


def project(root, *, extended=True):
    store = Engine().create(Path(root), b'For every integer n, n + 0 = n.', synthetic=True)
    target = next(iter(store.read_snapshot()['records']))
    iid = Engine().new_workflow(store, 'TRH', target_ref=target)['instance_id']
    storage, policy, uow = assemble(store, iid, install=extended)
    return store, iid, storage, policy, uow


def evidence(scope, name='one', data=b'Exact synthetic original', revision='1'):
    ref = C.ExactRef(project_id=scope.project_id, object_id='raw-evidence:'+name,
                     revision=revision, sha256=sha(data))
    return T.EvidenceWrite(evidence_ref=ref, content_base64=base64.b64encode(data).decode('ascii'))


def batch(boundary, name='one', *, count=1, data=b'Exact synthetic original'):
    write = evidence(boundary.scope, name, data)
    events = []
    for n in range(count):
        events.append(V.EventEnvelope(event_id='event:'+name+':'+str(n), event_type='EVIDENCE_RECORDED',
            event_domain=E.EventDomain.DIAGNOSTIC, status=E.EventStatus.OBSERVATION,
            project_id=boundary.scope.project_id, instance_id=boundary.scope.instance_id,
            journal_id=UNOBSERVED, aggregate_id='aggregate:synthetic', aggregate_sequence=None,
            journal_sequence=None, commit_ref=None, occurred_at=None, observed_at=NOW, committed_at=None,
            clock_source=E.ClockSource.SYNTHETIC, actor_principal_ref=None, actor_kind='SYNTHETIC',
            correlation_id='correlation:'+name, causation_id=None, operation_id='operation:'+name,
            idempotency_key='key:'+name, invocation_id=None, execution_id=None, request_id=None,
            attempt_id=None, activation_id=None, logical_main_id=None, owner_epoch=None, control_version=None,
            backend_id=UNOBSERVED, provider_id=UNOBSERVED, provider_request_id=UNOBSERVED,
            backend_binding_ref=None, payload_ref=write.evidence_ref, raw_evidence_ref=write.evidence_ref,
            payload_sha256=write.evidence_ref.sha256, classification=E.Classification.SYNTHETIC_TEST_ONLY,
            trust_origin=E.TrustOrigin.SYNTHETIC_TEST_ONLY, visibility_policy_ref=boundary.visibility_policy_ref))
    return T.CommitBatch(operation_id='operation:'+name, idempotency_key='key:'+name,
                         evidence=(write,), events=tuple(events))


def expected(boundary, policy):
    return T.VersionExpectation(boundary=boundary, owner_epoch=policy.epoch, expected_control_version=policy.version)


def stage(uow, policy, boundary, value):
    tx = uow.begin(expected(boundary, policy)); assert isinstance(tx, T.TransactionHandle), tx
    staged = uow.stage(tx, value); assert isinstance(staged, T.StagingReceipt), staged
    permit = policy.authorize(uow.commit_intent(tx))
    return tx, permit


def commit(uow, policy, boundary, value):
    tx, permit = stage(uow, policy, boundary, value)
    return uow.commit(tx, permit)


def cursor(boundary):
    return V.EventCursor(scope=boundary.scope, stream_kind=E.StreamKind.JOURNAL,
                         stream_id=boundary.journal_id, after_sequence=0, last_event_id=None)


def child(mode, *args, wait=True):
    command = [sys.executable, '-B', '/source/tests/devpr05/child.py', mode, *map(str, args)]
    if wait:
        return subprocess.run(command, capture_output=True, text=True, timeout=30)
    return subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def scientific_policy():
    from research_studio import demo
    value = demo.policy()
    value['model_capabilities'] = {**value['model_capabilities'], 'revision': 'dev05-explicit-synthetic-1',
                                  'ultra_configuration_ready': True, 'internal_delegation': True}
    return value
