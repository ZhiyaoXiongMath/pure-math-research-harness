"""Current authorization and coordination of closed synthetic control commands.

Authentication sessions are out-of-band registrations, never deserialized
permits or model assertions. This bounded fixture authority is not a production
identity provider. Concrete storage and static native assembly are injected.
"""
from copy import deepcopy
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
import secrets

from pmrh.domain.primitives import canonical, require, sha


def checked(condition, code='AUTHORIZATION_REQUIRED'):
    require(condition, code, 'Current synthetic control authority required')


@dataclass(frozen=True, eq=False)
class Session:
    """Object identity binds one independently authenticated fixture session."""
    session_id: str


class AuthorityRegistry:
    def __init__(self, *, clock=None):
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._sessions = {}
        self._manifests = {}
        self._producers = {}

    def authenticate(self, *, scope, root_binding_id, principal_ref, authn_evidence_ref,
                     authority_ref, actions, issued_at, expires_at, owner_id=None,
                     human=False, proposal_only=False, request_ids=None, acting_request_id=None):
        """Trusted assembly only. None of these values comes from a command."""
        checked(issued_at < expires_at and type(actions) in (set, frozenset))
        checked(type(human) is bool and type(proposal_only) is bool)
        session = Session('fixture-session:'+secrets.token_hex(24))
        self._sessions[session] = dict(scope=deepcopy(scope), root_binding_id=root_binding_id,
            principal_ref=deepcopy(principal_ref), authn_evidence_ref=deepcopy(authn_evidence_ref),
            authority_ref=deepcopy(authority_ref), actions=frozenset(actions), issued_at=issued_at,
            expires_at=expires_at, owner_id=owner_id, human=human, proposal_only=proposal_only,
            request_ids=None if request_ids is None else frozenset(request_ids), active=True)
        self._sessions[session]['acting_request_id'] = acting_request_id
        return session

    def acting_request(self, session):
        checked(type(session) is Session and session in self._sessions)
        return self._sessions[session]['acting_request_id']

    def revoke(self, session):
        checked(session in self._sessions)
        self._sessions[session]['active'] = False

    def register_manifest(self, manifest_ref, binding_ref, *, producer_ref, spec_ref, identity):
        self._manifests[canonical(spec_ref)] = dict(manifest_ref=deepcopy(manifest_ref),
            binding_ref=deepcopy(binding_ref), producer_ref=deepcopy(producer_ref),
            identity=deepcopy(identity), active=True)

    def revoke_manifest(self, spec_ref):
        checked(canonical(spec_ref) in self._manifests)
        self._manifests[canonical(spec_ref)]['active'] = False

    def register_original(self, receipt_ref, *, producer_ref, binding_ref, identity, raw_refs, local_unsent=False):
        """Independent synthetic channel attestation; DTO labels grant nothing."""
        key = canonical(receipt_ref)
        row = dict(producer_ref=deepcopy(producer_ref), binding_ref=deepcopy(binding_ref),
                   identity=deepcopy(identity), raw_refs=deepcopy(raw_refs), local_unsent=local_unsent)
        checked(key not in self._producers or self._producers[key] == row)
        self._producers[key] = row

    def original(self, receipt_ref, *, producer_ref, binding_ref, identity):
        row = self._producers.get(canonical(receipt_ref))
        checked(row is not None and row['producer_ref'] == producer_ref and
                row['binding_ref'] == binding_ref and row['identity'] == identity, 'UNTRUSTED_EVENT')
        return deepcopy(row)

    def manifest(self, spec_ref, *, current=True):
        row = self._manifests.get(canonical(spec_ref))
        checked(row is not None and (not current or row['active']))
        return deepcopy(row)

    def authenticate_current(self, session, action, scope, root_binding_id, *, request_id=None):
        checked(type(session) is Session and session in self._sessions)
        row = self._sessions[session]
        checked(row['active'] and row['scope'] == scope and row['root_binding_id'] == root_binding_id)
        checked(row['issued_at'] <= self.clock() < row['expires_at'])
        checked(action in row['actions'])
        checked(not row['proposal_only'] or action in {'GUIDANCE_SAVED','RECOVER_RECEIPT'})
        checked(row['request_ids'] is None or request_id in row['request_ids'])
        return deepcopy(row)


class Control:
    """One command, current authentication, and one native HEAD publication."""
    def __init__(self, storage, pool, registry, *, binding_id):
        checked(type(registry) is AuthorityRegistry)
        checked(binding_id in pool.roots)
        self.storage = storage
        self.pool = pool
        self.registry = registry
        self.binding_id = binding_id
        self._context = ContextVar('pmrh_control_context', default=None)
        storage.service = self
        storage.store._control_service = self

    @contextmanager
    def native_context(self, session, *, operation_id, idempotency_key, scope,
                       expected_head, owner_epoch, control_version,
                       grant_ref=None, manifest_ref=None):
        """Explicit host call context for the compatible direct native bridges."""
        frame = dict(session=session, operation_id=operation_id, idempotency_key=idempotency_key,
            scope=deepcopy(scope), expected_head=expected_head, owner_epoch=owner_epoch,
            control_version=control_version, grant_ref=deepcopy(grant_ref), manifest_ref=deepcopy(manifest_ref))
        token = self._context.set(frame)
        try:
            yield
        finally:
            self._context.reset(token)

    def native(self, action, payload):
        frame = self._context.get()
        checked(frame is not None)
        command = {key: deepcopy(frame[key]) for key in ('operation_id', 'idempotency_key', 'scope',
                   'expected_head', 'owner_epoch', 'control_version')}
        command.update(schema='pmrh.control-event/1', type=action, payload=deepcopy(payload))
        return self.apply(command, frame['session'], grant_ref=frame['grant_ref'], manifest_ref=frame['manifest_ref'])

    def apply(self, command, session, *, grant_ref=None, manifest_ref=None):
        self.storage.validate_command(command)
        # Authentication, including an independently bound acting invocation,
        # runs inside egress/pool/project before every duplicate lookup.
        return self.storage.execute(self, command, session, grant_ref, manifest_ref)

    def recover_receipt(self, scope, operation_id, session):
        self.registry.authenticate_current(session, 'RECOVER_RECEIPT', scope, self.binding_id)
        return self.storage.recover_receipt(self, scope, operation_id, session)

    def acquire_slot(self, request_id):
        frame=self._context.get();checked(frame is not None)
        return self.storage.acquire_native_slot(self,request_id,frame)

    def release_slot(self, request_id):
        frame=self._context.get();checked(frame is not None)
        return self.storage.release_slot(self,frame['scope'],request_id,frame['session'],
            expected_epoch=frame['owner_epoch'],expected_version=frame['control_version'])

    def send(self, command, session, *, grant_ref, manifest_ref, boundary):
        """The boundary is a separately installed bounded synthetic capability.

        The storage service owns the OS lock until after its first effect. A
        duplicate or UNKNOWN outcome never calls the boundary again.
        """
        checked(command['type'] == 'SEND_STARTED', 'UNSUPPORTED_CAPABILITY')
        self.storage.validate_command(command)
        return self.storage.execute(self, command, session, grant_ref, manifest_ref, boundary=boundary)
