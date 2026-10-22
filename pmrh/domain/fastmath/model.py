"""Immutable fast proposals. These values confer neither proof nor authority."""
from copy import deepcopy
from dataclasses import dataclass
from pmrh.domain.primitives import canonical, sha

SCHEMA = 'pmrh.fastmath/1'
DELTA_SCHEMA = 'pmrh.fast-delta/1'
KINDS = frozenset(('KnowledgeModule', 'Transition', 'ResearchMap', 'Frontier/Probe',
                   'ReaderProfile', 'RefinementBinding'))
MAX_BODY = 64 * 1024
MAX_DELTA = 512 * 1024
MAX_REVISIONS = 64
MAX_LINKS = 256
MAX_REFS = 4096
MAX_DEPTH = 32
MAX_ID = 256
ERRORS = frozenset(('FAST_SCHEMA_INVALID', 'FAST_AUTHORITY_DENIED', 'FAST_STATE_DENIED',
    'FAST_VERSION_CONFLICT', 'FAST_IDEMPOTENCY_CONFLICT', 'FAST_CAPTURE_MISMATCH',
    'FAST_REF_UNAVAILABLE', 'FAST_LIMIT_EXCEEDED', 'FAST_INTEGRITY_ERROR'))


class FastMathError(ValueError):
    def __init__(self, code, message):
        if code not in ERRORS:
            raise ValueError('Unknown fast error code')
        self.code = code
        super().__init__(code + ': ' + message)


def check(value, message, code='FAST_SCHEMA_INVALID'):
    if not value:
        raise FastMathError(code, message)


def revision_ref(body):
    return 'FM-' + sha(canonical(body))


def claim_fingerprint(slot):
    return sha(canonical(slot))


def make_revision(*, object_id, kind, scope, payload, body, author_attempt,
                  original_target_ref, d0_ref, reason, predecessor=None, dependencies=()):
    """Construct bytes only; validation requires the exact selected snapshot."""
    value = dict(schema=SCHEMA, object_id=object_id, kind=kind, scope=deepcopy(scope),
        predecessor=predecessor, payload=deepcopy(payload), payload_sha256=sha(canonical(payload)),
        body=body, body_sha256=sha(body.encode('utf-8')), author_attempt=deepcopy(author_attempt),
        original_target_ref=original_target_ref, d0_ref=deepcopy(d0_ref), reason=reason,
        dependencies=list(dependencies))
    return {'ref': revision_ref(value), 'body': value}


@dataclass(frozen=True)
class PreparedFastDelta:
    """Exact immutable proposal bytes; possession is not authorization."""
    raw: bytes
    sha256: str
    as_of_commit: str

    def value(self):
        import json
        return json.loads(self.raw)


@dataclass(frozen=True, eq=False)
class FastReadContext:
    """Trusted local read selection, re-resolved against persisted tasks."""
    project_id: str
    instance_id: str
    mission_id: str
    task_id: str
