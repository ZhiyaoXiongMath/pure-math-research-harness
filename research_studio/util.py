"""Bounded deterministic encodings and file operations; no execution helpers."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile
from datetime import datetime, timezone

MAX_JSON = 64 * 1024 * 1024
class PMRSError(ValueError):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message
        super().__init__(f"{code}: {message}")
ResearchStudioError = PMRSError

def require(condition, code, message):
    if not condition:
        raise PMRSError(code, message)

def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
sha256_bytes = sha

def identity(value, prefix="") -> str:
    return prefix + sha(canonical(value))

def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def loads(data: bytes | str, *, maximum=MAX_JSON):
    require(len(data) <= maximum, "JSON_LIMIT", "JSON exceeds the bounded parser size")
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "JSON_DUPLICATE_KEY", key)
            result[key] = value
        return result
    try:
        return json.loads(data, object_pairs_hook=pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, PMRSError):
            raise
        raise PMRSError("JSON_INVALID", str(exc)) from exc

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

def immutable(path: Path, data: bytes):
    path = safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        require(read(path, max(MAX_JSON, len(data))) == data, "IMMUTABLE_CONFLICT", str(path))
        return
    fd, tmp = tempfile.mkstemp(prefix=".publish-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        try:
            os.link(tmp, path)
        except FileExistsError:
            require(read(path, max(MAX_JSON, len(data))) == data, "IMMUTABLE_CONFLICT", str(path))
        fsync_dir(path.parent)
    finally:
        Path(tmp).unlink(missing_ok=True)

def atomic(path: Path, data: bytes):
    path = safe_path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".head-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path); fsync_dir(path.parent)
    finally:
        Path(tmp).unlink(missing_ok=True)
