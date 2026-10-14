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


class _Unavailable(Exception):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def _reason(exc):
    if isinstance(exc, _Unavailable):
        return exc.reason
    if isinstance(exc, FileNotFoundError):
        return 'NOT_FOUND'
    if isinstance(exc, PermissionError):
        return 'PERMISSION_DENIED'
    if isinstance(exc, OSError):
        return 'PATH_UNSAFE' if exc.errno in (errno.ELOOP, errno.ENOTDIR) else 'IO_UNAVAILABLE'
    if isinstance(exc, PMRSError):
        return {'SNAPSHOT_NOT_FOUND': 'SNAPSHOT_NOT_FOUND', 'INSTANCE_UNKNOWN': 'INSTANCE_NOT_FOUND',
                'NATIVE_SCHEMA_REQUIRED': 'UNSUPPORTED_PROJECT_FORMAT',
                'COMMIT_CHANGED': 'COMMIT_CHANGED', 'BLOB_CHANGED': 'BLOB_CHANGED',
                'CHECKPOINT_CHANGED': 'CHECKPOINT_CHANGED'}.get(exc.code, 'INVALID_PROJECT_DATA')
    return 'INVALID_PROJECT_DATA'


def _observed_at():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


class _ConfinedReader:
    """Private, query-lifetime POSIX reader; every component uses O_NOFOLLOW.

    Directory descriptors pin the selected directory objects across renames.
    Limits include unsuccessful/missing reads. No lock, mkdir, repair or fallback
    pathname read is available. Hardlinked files are conservatively refused.
    """
    def __init__(self, root, *, max_bytes=128 * 1024**2, max_files=4096):
        raw = os.fspath(root)
        if not isinstance(raw, str) or not raw or '\x00' in raw or '\\' in raw or '..' in Path(raw).parts:
            raise _Unavailable('PATH_UNSAFE')
        self.root = Path(raw).absolute()
        self.remaining_bytes = max_bytes
        self.remaining_files = max_files
        self.fd = None

    def __enter__(self):
        if not all(hasattr(os, name) for name in ('O_NOFOLLOW', 'O_DIRECTORY', 'O_NONBLOCK')):
            raise _Unavailable('CONFINED_READ_UNSUPPORTED')
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        fd = os.open(self.root.anchor, flags)
        try:
            for part in self.root.parts[1:]:
                nxt = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = nxt
            self.fd = fd
            return self
        except BaseException:
            os.close(fd)
            raise

    def __exit__(self, *args):
        os.close(self.fd)
        self.fd = None

    def read(self, relative, maximum=64 * 1024**2, *, missing_ok=False):
        if self.fd is None:
            raise _Unavailable('READ_CONTEXT_CLOSED')
        if not isinstance(relative, str) or not relative or '\x00' in relative or '\\' in relative:
            raise _Unavailable('PATH_UNSAFE')
        path = PurePosixPath(relative)
        if path.is_absolute() or '..' in path.parts or str(path) != relative or relative == '.':
            raise _Unavailable('PATH_UNSAFE')
        if self.remaining_files <= 0:
            raise _Unavailable('QUERY_READ_LIMIT')
        self.remaining_files -= 1
        fd = os.dup(self.fd)
        try:
            for part in path.parts[:-1]:
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = nxt
            file_fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            try:
                before = os.fstat(file_fd)
                if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                    raise _Unavailable('UNSAFE_FILE_TYPE')
                limit = min(maximum, self.remaining_bytes)
                if before.st_size > limit:
                    raise _Unavailable('QUERY_READ_LIMIT')
                chunks = []
                size = 0
                while True:
                    chunk = os.read(file_fd, min(65536, limit + 1 - size))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > limit:
                        raise _Unavailable('QUERY_READ_LIMIT')
                after = os.fstat(file_fd)
                if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                        after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                    raise _Unavailable('FILE_CHANGED_DURING_READ')
                self.remaining_bytes -= size
                return b''.join(chunks)
            finally:
                os.close(file_fd)
        except FileNotFoundError:
            if missing_ok:
                return None
            raise
        finally:
            os.close(fd)


@contextmanager
def _snapshot(project, as_of=None):
    # Static, named compatibility edge. Never load Workspace or construct a
    # new storage engine, and never modify global legacy I/O functions.
    from .store import Store
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
    from . import host_pool, main_session, views
    result = {'schema': 'pmrh.status/1', 'available': False, 'instance_id': instance_id,
              'read_only': True, 'automatic_retry': False,
              'runtime': {'observation': 'UNOBSERVED', 'reason': 'BACKEND_NOT_QUERIED'},
              'configuration': {'observation': 'UNOBSERVED', 'reason': 'NOT_REQUIRED_FOR_JOURNAL_QUERY'},
              'query_model_calls': {'count': None, 'measurement': 'NOT_INSTRUMENTED'}}
    try:
        if not isinstance(instance_id, str) or not 0 < len(instance_id) <= 256:
            raise _Unavailable('INVALID_INSTANCE_SELECTOR')
        with _snapshot(project, as_of) as (store, snapshot):
            value = views.status(snapshot, store, instance_id=instance_id, verify_report_files=False)
            value.pop('model_calls', None)
            instance = snapshot['instances'][instance_id]
            main = (main_session.view(store, instance_id, snapshot=snapshot)
                    if instance['kind'] in {'TRH', 'FDH'} else None)
            if main is not None:
                main.pop('model_calls', None)
            for row in value['execution']['requests']:
                original = snapshot['requests'][row['request_id']]
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
