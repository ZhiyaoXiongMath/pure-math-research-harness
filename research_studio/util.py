"""Bounded deterministic encodings and file operations; no execution helpers."""
from __future__ import annotations
from pmrh.domain.primitives import (
    MAX_JSON,
    PMRSError,
    ResearchStudioError,
    canonical,
    identity,
    loads,
    require,
    sha,
    sha256_bytes,
)
import hashlib
import errno
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile
from datetime import datetime, timezone


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
