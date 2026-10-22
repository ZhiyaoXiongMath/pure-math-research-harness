"""Shared native publication and descriptor-confined reads; no runtime imports."""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
from typing import Protocol
import errno,json,os,stat,tempfile,shutil
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
from pmrh.domain.primitives import MAX_JSON, PMRSError, canonical, loads, require, sha

def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def safe_path(root: Path, relative: str = "") -> Path:
    root = Path(root).absolute()
    require(not any(p.is_symlink() for p in (root, *root.parents)), "SYMLINK_REJECTED", str(root))
    root = root.resolve()
    if relative:
        q = PurePosixPath(relative)
        require(not q.is_absolute() and ".." not in q.parts and "\\" not in relative
                and str(q) == relative and "\x00" not in relative,
                "PATH_INVALID", relative)
        root = root.joinpath(*q.parts)
        require(not any(p.is_symlink() for p in (root, *root.parents)), "SYMLINK_REJECTED", relative)
    return root

def read(path: Path, maximum=MAX_JSON) -> bytes:
    path = safe_path(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as f:
            s = os.fstat(f.fileno())
            require(stat.S_ISREG(s.st_mode) and s.st_size <= maximum, "FILE_INVALID", str(path))
            b = f.read(maximum + 1)
            require(len(b) <= maximum, "FILE_LIMIT", str(path))
            return b
    except OSError as exc:
        raise PMRSError("FILE_UNAVAILABLE", str(path)) from exc

def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def _same_file_bytes(path, data):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode), 'FILE_INVALID', 'Immutable content must be a regular file.')
        if info.st_size != len(data): return False
        for offset in range(0, len(data), 256 * 1024):
            if stream.read(min(256 * 1024, len(data) - offset)) != data[offset:offset + 256 * 1024]: return False
        return not stream.read(1)

def _publication_temp(prefix, directory):
    try:
        return tempfile.mkstemp(prefix=prefix, dir=directory)
    except OSError as exc:
        if exc.errno in (errno.ENOSPC, errno.EDQUOT):
            raise PMRSError('RESOURCE_DISK_LOW', 'Publication could not allocate temporary space. Existing evidence is preserved; free space and recover the original operation.') from exc
        raise

def immutable(path: Path, data: bytes):
    path = safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        require(_same_file_bytes(path, data), "IMMUTABLE_CONFLICT", str(path))
        return
    fd, tmp = _publication_temp(".publish-", path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        try:
            os.link(tmp, path)
        except FileExistsError:
            require(_same_file_bytes(path, data), "IMMUTABLE_CONFLICT", str(path))
        fsync_dir(path.parent)
    except OSError as exc:
        if exc.errno in (errno.ENOSPC, errno.EDQUOT):
            raise PMRSError('RESOURCE_DISK_LOW', 'Storage publication could not finish. Existing committed data is preserved; free space and recover the original operation before retrying.') from exc
        raise
    finally:
        Path(tmp).unlink(missing_ok=True)

def atomic(path: Path, data: bytes):
    path = safe_path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = _publication_temp(".head-", path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path); fsync_dir(path.parent)
    except OSError as exc:
        if exc.errno in (errno.ENOSPC, errno.EDQUOT):
            raise PMRSError('RESOURCE_DISK_LOW', 'Atomic publication could not finish. Inspect the original operation after freeing space; do not create a replacement model request.') from exc
        raise
    finally:
        Path(tmp).unlink(missing_ok=True)

SERIALIZED_BYTES = 64 * 1024 * 1024
DISK_MARGIN_BYTES = 512 * 1024 * 1024

def json_bytes(value, max_bytes, *, code='RESOURCE_LIMIT'):
    """Count canonical JSON before creating its full str/bytes representations."""
    total = 0
    def add(n):
        nonlocal total
        total += n
        require(total <= max_bytes, code, 'Complete task metadata or serialization exceeds its byte budget; narrow the explicit scope or use a CoveragePlan.')
    def visit(item):
        if isinstance(item, str):
            add(2)
            for pos in range(0, len(item), 16384):
                add(len(json.dumps(item[pos:pos + 16384], ensure_ascii=False).encode('utf-8')) - 2)
        elif isinstance(item, dict):
            add(2 + max(0, len(item) - 1))
            for key, child in item.items():
                require(isinstance(key, str), code, 'JSON metadata keys must be text.')
                visit(key); add(1); visit(child)
        elif isinstance(item, (list, tuple)):
            add(2 + max(0, len(item) - 1))
            for child in item: visit(child)
        else: add(len(canonical(item)))
    visit(value)
    return total

def bounded_canonical(value, max_bytes=SERIALIZED_BYTES, *, code='RESOURCE_LIMIT'):
    expected = json_bytes(value, max_bytes, code=code)
    result = canonical(value)
    require(len(result) == expected, code, 'Canonical serialization size differs from its preflight.')
    return result

def disk_preflight(path, temporary_bytes):
    require(type(temporary_bytes) is int and 0 <= temporary_bytes,
            'RESOURCE_LIMIT', 'Temporary preparation budget is outside the supported range.')
    path = Path(path)
    while not path.exists(): path = path.parent
    free = shutil.disk_usage(path).free
    require(free >= temporary_bytes + DISK_MARGIN_BYTES, 'RESOURCE_DISK_LOW',
            'Preparation needs more free disk space, including its safety margin. Prior work is preserved; free space and resume the original request.')
    return {'free_bytes': free, 'temporary_bytes': temporary_bytes, 'margin_bytes': DISK_MARGIN_BYTES}

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

@dataclass
class _BodyReadBudget:
    """One query's body payload and separately counted EOF integrity probes."""
    remaining_bytes: int = 4294967296
    remaining_files: int = 64
    integrity_probe_bytes: int = 0
    integrity_probe_attempts: int = 0

    def __post_init__(self):
        self._validate()

    def _validate(self):
        for value,maximum in ((self.remaining_bytes,4294967296),(self.remaining_files,64),
                              (self.integrity_probe_bytes,64),(self.integrity_probe_attempts,64)):
            if type(value) is not int or not 0 <= value <= maximum:
                raise _Unavailable('BODY_BUDGET_INVALID')
        if self.integrity_probe_bytes > self.integrity_probe_attempts:
            raise _Unavailable('BODY_BUDGET_INVALID')


@dataclass(frozen=True)
class _VerifiedBodyRead:
    sha256: str
    size: int
    result: object


class _BodyVisitor(Protocol):
    """Trusted private accumulator, never a serialized/plugin callback.

    feed retains tentative bounded data only; it cannot deliver results.
    finish is called only after full EOF, expected SHA and unchanged stat.
    """
    def feed(self, chunk: bytes, byte_offset: int) -> None: ...
    def finish(self) -> object: ...
    def abort(self) -> None: ...


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

    def _open_regular(self, relative: str):
        # Validate eagerly, before callers debit an attempted file. Opening is
        # deferred until __enter__, after that debit. Both read paths share it.
        if self.fd is None:
            raise _Unavailable('READ_CONTEXT_CLOSED')
        if not isinstance(relative, str) or not relative or '\x00' in relative or '\\' in relative:
            raise _Unavailable('PATH_UNSAFE')
        path = PurePosixPath(relative)
        if path.is_absolute() or '..' in path.parts or str(path) != relative or relative == '.':
            raise _Unavailable('PATH_UNSAFE')
        @contextmanager
        def opened():
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
                    yield file_fd, before
                finally:
                    os.close(file_fd)
            finally:
                os.close(fd)
        return opened()

    def _check_unchanged(self, fd: int, before, *, identity: bool = False) -> None:
        after = os.fstat(fd)
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise _Unavailable('FILE_CHANGED_DURING_READ')
        if identity and ((before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
                         or not stat.S_ISREG(after.st_mode) or after.st_nlink != 1):
            raise _Unavailable('FILE_CHANGED_DURING_READ')

    def read(self, relative, maximum=64 * 1024**2, *, missing_ok=False):
        opening = self._open_regular(relative)
        if self.remaining_files <= 0:
            raise _Unavailable('QUERY_READ_LIMIT')
        self.remaining_files -= 1
        try:
            with opening as (file_fd, before):
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
                self._check_unchanged(file_fd, before)
                self.remaining_bytes -= size
                return b''.join(chunks)
        except FileNotFoundError:
            if missing_ok:
                return None
            raise

    def read_verified_body(self, expected_sha256: str, *, budget: _BodyReadBudget,
                           visitor: _BodyVisitor, maximum: int = 4294967296) -> _VerifiedBodyRead:
        """Authenticate the complete pinned blob before releasing visitor output.

        Payload <=4GiB/query, <=64 attempted files; a separate real read(1)
        proves EOF per blob even at the exact payload limit. No public chunks.
        Failed streams charge bytes actually read and discard tentative data.
        """
        try:
            require(type(expected_sha256) is str and len(expected_sha256)==64 and
                    all(c in '0123456789abcdef' for c in expected_sha256),
                    'BLOB_ID_INVALID', 'Expected SHA-256 digest')
            if type(budget) is not _BodyReadBudget or type(maximum) is not int or not 0 <= maximum <= 4294967296:
                raise _Unavailable('BODY_BUDGET_INVALID')
            budget._validate()
            opening = self._open_regular('blobs/'+expected_sha256)
            if budget.remaining_files <= 0:
                raise _Unavailable('QUERY_READ_LIMIT')
            budget.remaining_files -= 1
            with opening as (file_fd, before):
                if before.st_size > min(maximum,budget.remaining_bytes):
                    raise _Unavailable('QUERY_READ_LIMIT')
                size = 0; digest = hashlib.sha256(); visitor_error = None
                while size < before.st_size:
                    chunk = os.read(file_fd,min(65536,before.st_size-size))
                    if not chunk:
                        raise _Unavailable('BLOB_CHANGED')
                    budget.remaining_bytes -= len(chunk)
                    digest.update(chunk)
                    if visitor_error is None:
                        try:visitor.feed(chunk,size)
                        except Exception as exc:visitor_error = exc
                    size += len(chunk)
                if budget.integrity_probe_attempts >= 64:
                    raise _Unavailable('QUERY_READ_LIMIT')
                budget.integrity_probe_attempts += 1
                extra = os.read(file_fd,1)
                budget.integrity_probe_bytes += len(extra)
                if extra:
                    raise _Unavailable('BLOB_CHANGED')
                self._check_unchanged(file_fd,before,identity=True)
                if size != before.st_size or digest.hexdigest() != expected_sha256:
                    raise _Unavailable('BLOB_CHANGED')
                if visitor_error is not None:raise visitor_error
                result = visitor.finish()
                return _VerifiedBodyRead(expected_sha256,size,result)
        except BaseException:
            try:visitor.abort()
            except BaseException:pass  # Preserve the original failure verbatim.
            raise
