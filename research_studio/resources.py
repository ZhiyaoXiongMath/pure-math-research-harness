"""Small bounded preparation helpers; no scientific policy or host limits change."""
from contextlib import contextmanager
from pathlib import Path
import fcntl
import hashlib
import json
import os
import shutil
import stat
import tempfile
import uuid
from .util import PMRSError, atomic, canonical, fsync_dir, read, require, safe_path

MIB = 1024 * 1024
CHUNK_BYTES = 256 * 1024
CONTEXT_BYTES = 32 * MIB
METADATA_BYTES = 8 * MIB
SERIALIZED_BYTES = 64 * MIB
MAX_PREPARATIONS = 2
MAX_PREPARATION_MEMORY = 256 * MIB
TOTAL_PREPARATION_MEMORY = 512 * MIB
MAX_TEMPORARY_BYTES = 512 * MIB
TOTAL_TEMPORARY_BYTES = 1024 * MIB
DISK_MARGIN_BYTES = 512 * MIB


def file_info(path):
    path = safe_path(Path(path))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode), 'RESOURCE_FILE_INVALID', 'Preparation requires a regular immutable input file.')
        return {'bytes': info.st_size, 'device': info.st_dev, 'inode': info.st_ino}
    finally:
        os.close(fd)


def blob_info(store, digest):
    require(isinstance(digest, str) and len(digest) == 64 and all(c in '0123456789abcdef' for c in digest),
            'BLOB_ID_INVALID', 'Expected SHA-256 digest')
    return file_info(safe_path(store.root, 'blobs/' + digest))


def hash_file(path, max_bytes):
    path = safe_path(Path(path)); digest = hashlib.sha256(); count = 0
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_size <= max_bytes, 'RESOURCE_LIMIT', 'Input exceeds the declared file budget.')
        while True:
            data = stream.read(min(CHUNK_BYTES, max_bytes + 1 - count))
            if not data: break
            count += len(data)
            require(count <= max_bytes, 'RESOURCE_LIMIT', 'Input grew beyond the declared file budget.')
            digest.update(data)
        require(count == info.st_size, 'ORIGINAL_BYTES_MISMATCH', 'Input changed while it was read.')
    return digest.hexdigest()


def copy_file(source, destination, max_bytes, expected_sha256=None):
    """One bounded independent copy, atomically published; never link a source blob."""
    source = safe_path(Path(source)); destination = safe_path(Path(destination))
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        actual = hash_file(destination, max_bytes)
        require(expected_sha256 is not None and actual == expected_sha256, 'IMMUTABLE_CONFLICT', 'Prepared input differs from its frozen hash.')
        return {'sha256': actual, 'bytes': file_info(destination)['bytes'], 'read_bytes': 0, 'copied_bytes': 0}
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    temporary = None; count = 0; digest = hashlib.sha256()
    try:
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_size <= max_bytes, 'RESOURCE_LIMIT', 'Input exceeds the declared copy budget.')
            target_fd, temporary = tempfile.mkstemp(prefix='.prepare-', dir=destination.parent)
            with os.fdopen(target_fd, 'wb') as target:
                while True:
                    data = stream.read(min(CHUNK_BYTES, max_bytes + 1 - count))
                    if not data: break
                    count += len(data)
                    require(count <= max_bytes, 'RESOURCE_LIMIT', 'Input grew beyond the declared copy budget.')
                    digest.update(data); target.write(data)
                require(count == info.st_size, 'ORIGINAL_BYTES_MISMATCH', 'Input changed while it was copied.')
                actual = digest.hexdigest()
                require(expected_sha256 is None or actual == expected_sha256, 'ORIGINAL_BYTES_MISMATCH', 'Input hash differs from the frozen material.')
                target.flush(); os.fsync(target.fileno()); os.fchmod(target.fileno(), 0o400)
            try: os.link(temporary, destination)
            except FileExistsError:
                require(hash_file(destination, max_bytes) == actual, 'IMMUTABLE_CONFLICT', 'Concurrent prepared input differs.')
            fsync_dir(destination.parent)
        return {'sha256': actual, 'bytes': count, 'read_bytes': count, 'copied_bytes': count}
    except OSError as exc:
        if exc.errno == 28:
            raise PMRSError('RESOURCE_DISK_LOW', 'Input preparation ran out of space; prior evidence is preserved. Free space and resume the original request.') from exc
        raise
    finally:
        if temporary is not None:
            try: os.unlink(temporary)
            except FileNotFoundError: pass


def copy_blob(store, digest, destination, max_bytes=SERIALIZED_BYTES):
    blob_info(store, digest)
    return copy_file(store.root / 'blobs' / digest, destination, max_bytes, digest)


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
    require(type(temporary_bytes) is int and 0 <= temporary_bytes <= TOTAL_TEMPORARY_BYTES,
            'RESOURCE_LIMIT', 'Temporary preparation budget is outside the supported range.')
    path = Path(path)
    while not path.exists(): path = path.parent
    free = shutil.disk_usage(path).free
    require(free >= temporary_bytes + DISK_MARGIN_BYTES, 'RESOURCE_DISK_LOW',
            'Preparation needs more free disk space, including its safety margin. Prior work is preserved; free space and resume the original request.')
    return {'free_bytes': free, 'temporary_bytes': temporary_bytes, 'margin_bytes': DISK_MARGIN_BYTES}


def _process_start(pid):
    try: return Path('/proc/' + str(pid) + '/stat').read_text().rsplit(')', 1)[1].split()[19]
    except (OSError, IndexError): return None


@contextmanager
def reserve(root, *, owner, temporary_bytes, memory_bytes, max_preparations=MAX_PREPARATIONS):
    """Project-local OS-locked reservations; stale process leases are reclaimable."""
    require(type(max_preparations) is int and 1<=max_preparations<=MAX_PREPARATIONS,'RESOURCE_LIMIT','Preparation concurrency must respect the existing project limit, at most two.')
    require(isinstance(owner, str) and 0 < len(owner) <= 200, 'RESOURCE_LIMIT', 'A bounded preparation owner is required.')
    require(type(temporary_bytes) is int and 0 <= temporary_bytes <= MAX_TEMPORARY_BYTES
            and type(memory_bytes) is int and 0 <= memory_bytes <= MAX_PREPARATION_MEMORY,
            'RESOURCE_LIMIT', 'This preparation exceeds the supported per-task resource budget.')
    folder = safe_path(Path(root), '.runtime/resources'); folder.mkdir(parents=True, exist_ok=True)
    lock_path = folder / 'reservations.lock'; ledger = folder / 'reservations.json'
    token = uuid.uuid4().hex; pid = os.getpid(); start = _process_start(pid)
    require(start is not None, 'RESOURCE_WAIT', 'Cannot establish this preparation process identity.')
    @contextmanager
    def locked():
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'a+b') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            rows = json.loads(read(ledger, 65536)) if ledger.exists() else {}
            rows = {k: v for k, v in rows.items() if _process_start(v['pid']) == v['process_start']}
            yield rows
            atomic(ledger, canonical(rows))
    with locked() as rows:
        require(len(rows) < max_preparations and sum(r['memory_bytes'] for r in rows.values()) + memory_bytes <= TOTAL_PREPARATION_MEMORY
                and sum(r['temporary_bytes'] for r in rows.values()) + temporary_bytes <= TOTAL_TEMPORARY_BYTES,
                'RESOURCE_WAIT', 'Other preparations hold the available resource budget. Wait for them to finish, then resume this original request.')
        disk_preflight(root, sum(r['temporary_bytes'] for r in rows.values()) + temporary_bytes)
        rows[token] = {'pid': pid, 'process_start': start, 'owner': owner, 'temporary_bytes': temporary_bytes, 'memory_bytes': memory_bytes}
    try:
        yield {'token': token, 'temporary_bytes': temporary_bytes, 'memory_bytes': memory_bytes}
    finally:
        with locked() as rows: rows.pop(token, None)


def directory_usage(path, *, max_bytes, max_files=4096):
    """Bound task-owned working output without traversing links or user data."""
    size=0;count=0;pending=[Path(path)]
    while pending:
        current=pending.pop()
        with os.scandir(current) as entries:
            for entry in entries:
                count+=1
                require(count<=max_files,'RESOURCE_LIMIT','Task working directory exceeds its file-count budget.')
                if entry.is_dir(follow_symlinks=False):pending.append(Path(entry.path))
                else:size+=entry.stat(follow_symlinks=False).st_size
                require(size<=max_bytes,'RESOURCE_LIMIT','Task working directory exceeds its reserved disk budget; original request outcome must be inspected before retry.')
    return {'bytes':size,'files':count}
