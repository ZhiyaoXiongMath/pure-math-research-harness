"""Fail-closed Python-level guard for the narrow DEV-PR-01 unittest process.

This is NOT an OS sandbox: native code, inherited descriptors, malicious Python
and processes outside this interpreter can bypass monkeypatches. CI must run
only synthetic tests and must not mount real research projects or credentials.
"""
from __future__ import annotations

import builtins
import io
import os
from pathlib import Path
import socket
import subprocess
import sys

if os.environ.get("PMRH_OFFLINE_GUARD") != "1":
    raise RuntimeError("offline sitecustomize loaded without an explicit guard request")

ROOT = Path(os.environ["PMRH_SOURCE_ROOT"]).resolve()
SANDBOX = Path(os.environ["PMRH_SANDBOX_ROOT"]).resolve()
ORIGINAL_HOME = Path(os.environ["PMRH_ORIGINAL_HOME"]).resolve()
SYSTEM_READ_ROOTS = tuple(Path(p).resolve() for p in
                          {sys.base_prefix, sys.prefix, "/etc", "/lib", "/lib64"})
# Extra forbidden roots are defense-in-depth, not a project discovery service.
FORBIDDEN = tuple(Path(p).resolve() for p in
                  os.environ.get("PMRH_FORBIDDEN_ROOTS", "").split(os.pathsep) if p)


def inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def guard_path(path, *, write=False):
    if isinstance(path, int):
        # Existing pre-opened descriptors cannot be secured by this guard.
        return
    try:
        location = Path(os.fspath(path)).resolve()
    except (TypeError, ValueError):
        raise PermissionError("PMRH offline test guard: unrecognized path") from None
    if inside(location, SANDBOX):
        return
    if inside(location, ROOT):
        if not write:
            return
        raise PermissionError("PMRH offline test guard: source tree is read-only")
    if inside(location, ORIGINAL_HOME) or any(inside(location, x) for x in FORBIDDEN):
        raise PermissionError("PMRH offline test guard: private path denied")
    if not write and any(inside(location, x) for x in SYSTEM_READ_ROOTS):
        return
    raise PermissionError("PMRH offline test guard: path outside isolated allowlist")


def mode_is_write(mode) -> bool:
    return any(c in str(mode) for c in "wax+")


real_builtin_open = builtins.open
real_io_open = io.open
real_os_open = os.open
real_listdir = os.listdir
real_scandir = os.scandir


def guarded_open(path, mode="r", *args, **kwargs):
    guard_path(path, write=mode_is_write(mode))
    return real_builtin_open(path, mode, *args, **kwargs)


def guarded_io_open(path, mode="r", *args, **kwargs):
    guard_path(path, write=mode_is_write(mode))
    return real_io_open(path, mode, *args, **kwargs)


def path_with_dirfd(path, dir_fd=None):
    if dir_fd is None:
        return path
    if isinstance(path, int):
        raise PermissionError("PMRH offline test guard: opaque fd path denied")
    try:
        base = Path(os.readlink("/proc/self/fd/" + str(dir_fd)))
    except (OSError, ValueError):
        raise PermissionError("PMRH offline test guard: unresolved dir_fd") from None
    return base / os.fspath(path)


def guarded_os_open(path, flags, *args, **kwargs):
    writing = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT |
                            os.O_TRUNC | os.O_APPEND))
    guard_path(path_with_dirfd(path, kwargs.get("dir_fd")), write=writing)
    return real_os_open(path, flags, *args, **kwargs)


def guarded_listdir(path="."):
    guard_path(path)
    return real_listdir(path)


def guarded_scandir(path="."):
    guard_path(path)
    return real_scandir(path)


def denied(*args, **kwargs):
    raise PermissionError("PMRH offline test guard: network/process capability denied")


builtins.open = guarded_open
io.open = guarded_io_open
os.open = guarded_os_open
os.listdir = guarded_listdir
os.scandir = guarded_scandir
socket.socket = denied
socket.create_connection = denied
socket.socketpair = denied
if hasattr(socket, "fromfd"):
    socket.fromfd = denied
subprocess.Popen = denied
os.system = denied
os.popen = denied
for name in ("fork", "forkpty", "posix_spawn", "posix_spawnp", "spawnl", "spawnle",
             "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe",
             "execv", "execve", "execvp", "execvpe", "execl", "execle",
             "execlp", "execlpe"):
    if hasattr(os, name):
        setattr(os, name, denied)


# Pathlib and shutil can mutate files without builtins.open. Cover the common
# Python OS mutations too. Descriptor-only operations and native extensions
# remain outside this process-level guard's security guarantee.
def guarded_unary(fn):
    def wrapper(path, *args, **kwargs):
        guard_path(path_with_dirfd(path, kwargs.get("dir_fd")), write=True)
        return fn(path, *args, **kwargs)
    return wrapper


for name in ("mkdir", "rmdir", "remove", "unlink", "chmod", "chown",
             "utime", "truncate"):
    if hasattr(os, name):
        setattr(os, name, guarded_unary(getattr(os, name)))


def guarded_move(fn):
    def wrapper(source, destination, *args, **kwargs):
        guard_path(path_with_dirfd(source, kwargs.get("src_dir_fd")), write=True)
        guard_path(path_with_dirfd(destination, kwargs.get("dst_dir_fd")), write=True)
        return fn(source, destination, *args, **kwargs)
    return wrapper


for name in ("rename", "replace"):
    if hasattr(os, name):
        setattr(os, name, guarded_move(getattr(os, name)))


if hasattr(os, "symlink"):
    real_symlink = os.symlink

    def guarded_symlink(src, dst, *args, **kwargs):
        guard_path(path_with_dirfd(dst, kwargs.get("dir_fd")), write=True)
        return real_symlink(src, dst, *args, **kwargs)

    os.symlink = guarded_symlink

if hasattr(os, "link"):
    real_link = os.link

    def guarded_link(src, dst, *args, **kwargs):
        guard_path(path_with_dirfd(src, kwargs.get("src_dir_fd")))
        guard_path(path_with_dirfd(dst, kwargs.get("dst_dir_fd")), write=True)
        return real_link(src, dst, *args, **kwargs)

    os.link = guarded_link
