"""DEV03 compatibility slice: confined I/O and one journal-bound status query.

No replay implementation lives here. Store verifies its original commit/blob
format and replays its original deltas using the supplied read-only context.
The global pool is an independent observation, never part of that transaction.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import errno
import os
from pathlib import Path, PurePosixPath
import stat

from pmrh.ports.dto.core import StateAxes, port_error
from pmrh.ports.dto import enums as E
from .util import PMRSError, canonical


from pmrh.adapters.storage.io import _Unavailable as _Unavailable


from pmrh.adapters.storage.io import _reason as _reason


from pmrh.adapters.storage.io import _observed_at as _observed_at


from pmrh.adapters.storage.io import _ConfinedReader as _ConfinedReader


@contextmanager
def _snapshot(project, as_of=None):
    # Static, named compatibility edge. Never load Workspace or construct a
    # new storage engine, and never modify global legacy I/O functions.
    from pmrh.adapters.storage.journal import Journal as Store
    if as_of is not None and (not isinstance(as_of, str) or len(as_of) != 64 or
                              any(c not in '0123456789abcdef' for c in as_of)):
        raise _Unavailable('INVALID_AS_OF')
    with _ConfinedReader(project) as reader:
        store = Store(reader.root, reader=reader)
        snapshot = store.read_snapshot(as_of)
        yield store, snapshot


def _state_axes(instance, request):
    # There is no safe total mapping of the legacy vocabulary. In particular,
    # SETTLED is not an observed process termination and missing admission is
    # not PENDING. Preserve legacy values and expose absence of a typed mapping.
    try:
        return StateAxes(control=E.ControlState(instance['status']),
                         execution=E.ExecutionState(request['execution_state']),
                         admission=E.AdmissionState(request['acceptance_state']),
                         science=E.ScienceState.UNOBSERVED, science_scope_ref=None).to_wire()
    except (KeyError, ValueError):
        return None


def status(project, instance_id, *, as_of=None):
    """Return existing project facts; unavailable data never becomes healthy zero."""
    from pmrh.adapters.storage import pool_read as host_pool
    from pmrh.application import read_projections as views
    result = {'schema': 'pmrh.status/1', 'available': False, 'instance_id': instance_id,
              'read_only': True, 'automatic_retry': False,
              'runtime': {'observation': 'UNOBSERVED', 'reason': 'BACKEND_NOT_QUERIED'},
              'configuration': {'observation': 'UNOBSERVED', 'reason': 'NOT_REQUIRED_FOR_JOURNAL_QUERY'},
              'query_model_calls': {'count': None, 'measurement': 'NOT_INSTRUMENTED'}}
    try:
        if not isinstance(instance_id, str) or not 0 < len(instance_id) <= 256:
            raise _Unavailable('INVALID_INSTANCE_SELECTOR')
        with _snapshot(project, as_of) as (store, snapshot):
            value = views.status(snapshot, instance_id=instance_id)
            value.pop('model_calls', None)
            instance = snapshot['instances'][instance_id]
            main = (views.main_view(snapshot, instance_id)
                    if instance['kind'] in {'TRH', 'FDH'} else None)
            if main is not None:
                main.pop('model_calls', None)
            for row in value['execution']['requests']:
                original = snapshot['requests'][row['request_id']]
                row['acceptance_state'] = original.get('acceptance_state')
                row['acceptance_state_unavailable_reason'] = (
                    None if 'acceptance_state' in original else 'NOT_RECORDED')
                row['state_axes'] = _state_axes(instance, original)
                row['state_axes_unavailable_reason'] = (
                    None if row['state_axes'] is not None else 'LEGACY_VALUES_NOT_REPRESENTABLE')
            # Refuse malformed Unicode/nonfinite values before exposing a
            # successful status that the CLI cannot serialize faithfully.
            canonical({'value': value, 'main': main})
            result.update(value, available=True, unavailable_reason=None, main=main,
                          snapshot={'project_commit': snapshot['knowledge_commit'],
                                    'sequence': snapshot['_snapshot_sequence'],
                                    'consistent_project_view': True, 'cross_store_atomicity': False})
    except (_Unavailable, PMRSError, OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError) as exc:
        reason = _reason(exc)
        code = E.ErrorCode.NOT_FOUND if reason in ('NOT_FOUND', 'SNAPSHOT_NOT_FOUND', 'INSTANCE_NOT_FOUND') else E.ErrorCode.UNOBSERVED
        result.update(available=False, unavailable_reason=reason,
                      error=port_error(code, E.Operation.INSPECT).to_wire())
    result['host_pool'] = host_pool.read_status()
    return result
