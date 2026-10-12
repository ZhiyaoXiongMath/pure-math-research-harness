#!/usr/bin/env python3
"""Restricted, opt-in, synthetic-only DEV-PR-01 offline unittest launcher.

Default suite is narrowly allowlisted. Never dispatch the historical runner,
real research tests, Codex, or any research CLI. sitecustomize is a Python
defense-in-depth guard, NOT an operating-system sandbox.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
SUITES = {"devpr01": ("tests/devpr01", "test_*.py")}
BLOCKED_ARGUMENTS = {"--runner", "--legacy", "--model", "--project", "--goal",
                     "--script", "--shell", "--native", "--network"}



def _isolated_artifact_directory(out: Path) -> int:
    """Preflight an *existing* directory; return a symlink-safe directory fd.

    The caller/CI provisions PMRH_TEST_ARTIFACT_ROOT in a fresh, dedicated
    system-temporary directory. Neither --out nor this routine can create it.
    An environment variable is not an OS security principal: only trusted
    operator/CI configuration can designate the root.
    """
    configured = os.environ.get("PMRH_TEST_ARTIFACT_ROOT")
    if not configured:
        raise ValueError("--out requires an explicitly provisioned PMRH_TEST_ARTIFACT_ROOT")
    allowed = Path(configured)
    destination = Path(out)
    for name, value in (("PMRH_TEST_ARTIFACT_ROOT", allowed), ("--out", destination)):
        if not value.is_absolute() or any(p in (".", "..") for p in value.parts):
            raise ValueError(name + " must be an absolute, traversal-free directory path")
    safe_tmp = Path(tempfile.gettempdir()).resolve()
    # A dedicated, unpredictable folder DIRECTLY beneath the system temp
    # parent prevents designating HOME or an arbitrary pre-existing project
    # subtree as the artifacts root.
    if allowed.parent != safe_tmp or not re.fullmatch(
        r"pmrh-devpr01-artifacts-[A-Za-z0-9_-]{6,}", allowed.name
    ):
        raise ValueError("artifact root must be a dedicated system-temp directory")
    if allowed not in destination.parents:
        raise ValueError("--out must be a strict descendant of the isolated artifact root")
    protected = (ROOT.resolve(), Path.home().resolve(),
                 Path(os.environ.get("PMRH_ORIGINAL_HOME", str(Path.home()))).resolve())
    for directory in (allowed, destination):
        if any(directory == x or directory.is_relative_to(x)
               or x.is_relative_to(directory) for x in protected):
            raise ValueError("artifact output overlaps source tree or real HOME")
    if not (hasattr(os, "O_DIRECTORY") and hasattr(os, "O_NOFOLLOW")):
        raise ValueError("--out requires POSIX no-follow directory verification")

    # Traverse every component below the operator-provisioned system temp
    # directory via O_NOFOLLOW. Each component is opened relative to the
    # previous directory descriptor, not through a racy resolved pathname.
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        fd = os.open(safe_tmp, flags)
    except OSError as exc:
        raise ValueError("system temporary directory is unavailable or a symlink") from exc
    try:
        for part in destination.relative_to(safe_tmp).parts:
            nxt = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = nxt
        # Existing receipt files must never be clobbered, including dangling
        # symlinks. The eventual writes use O_EXCL|O_NOFOLLOW and this fd.
        for filename in ("unittest.log", "receipt.json"):
            try:
                os.stat(filename, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise ValueError("refusing to overwrite an existing test artifact: " + filename)
        return fd
    except Exception as exc:
        os.close(fd)
        if isinstance(exc, OSError):
            raise ValueError("artifact path is absent, non-directory or uses a symlink") from exc
        raise


def _write_artifact_fd(directory_fd: int, filename: str, payload: bytes):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    fd = os.open(filename, flags, 0o600, dir_fd=directory_fd)
    with os.fdopen(fd, "wb") as f:
        f.write(payload)


def model_measurement() -> dict:
    """Static controls and observed provider usage are distinct evidence axes."""
    return {
        "count": None,
        "measurement": "NOT_INSTRUMENTED",
        "observed_provider_events": "NOT_MEASURED",
        "static_scope": "ALLOWLISTED_SYNTHETIC_TEST_DISCOVERY_ONLY",
        "python_runtime_controls": "COMMON_SOCKET_AND_PROCESS_ENTRYPOINTS_BLOCKED",
        "zero_calls_verified": False,
    }


def environment(scratch: Path, *, forbidden_roots: list[str] | None = None) -> dict:
    original_home = Path.home().resolve()
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
           "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
           "PYTHONDONTWRITEBYTECODE": "1",
           "PYTHONNOUSERSITE": "1",
           "PIP_NO_INDEX": "1",
           "PIP_DISABLE_PIP_VERSION_CHECK": "1",
           "PMRH_OFFLINE_GUARD": "1",
           "PMRH_SYNTHETIC_ONLY": "1",
           "PMRH_SOURCE_ROOT": str(ROOT),
           "PMRH_SANDBOX_ROOT": str(scratch),
           "PMRH_ORIGINAL_HOME": str(original_home),
           "PMRH_FORBIDDEN_ROOTS": os.pathsep.join(forbidden_roots or []),
           "PYTHONPATH": os.pathsep.join([str(ROOT / "scripts/offline_guard"), str(ROOT)]),
           "PMRH_SOURCE_SHA": os.environ.get("PMRH_SOURCE_SHA", "UNVERIFIED_LOCAL")}
    for name in ("HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME",
                 "XDG_DATA_HOME", "TMPDIR", "TMP", "TEMP"):
        folder = scratch / name.lower()
        folder.mkdir(exist_ok=True)
        env[name] = str(folder)
    return env


def execute(suite: str, *, out: Path | None = None,
            forbidden_roots: list[str] | None = None) -> dict:
    if suite not in SUITES:
        raise ValueError("suite is not in the synthetic-only allowlist")
    # Validate and pin the destination BEFORE allocating scratch, executing
    # tests or writing any path. Failed preflight must be side-effect free.
    out_fd = _isolated_artifact_directory(out) if out is not None else None
    began = time.monotonic()
    try:
        return _execute_guarded(suite, began=began, out_fd=out_fd,
                                forbidden_roots=forbidden_roots)
    finally:
        if out_fd is not None:
            os.close(out_fd)


def _execute_guarded(suite: str, *, began: float, out_fd: int | None,
                     forbidden_roots: list[str] | None) -> dict:
    with tempfile.TemporaryDirectory(prefix="pmrh-devpr01-offline-") as td:
        scratch = Path(td)
        env = environment(scratch, forbidden_roots=forbidden_roots)
        source_dir, filename_pattern = SUITES[suite]
        cmd = [sys.executable, "-B", "-m", "unittest", "discover", "-s",
               source_dir, "-p", filename_pattern, "-t", ".", "-v"]
        run = subprocess.run(cmd, cwd=ROOT, env=env, text=True,
                             capture_output=True, timeout=120, check=False)
        transcript = (run.stdout + "\n" + run.stderr).encode()
        count_match = re.search(r"\bRan (\d+) tests?\b", run.stderr)
        tests = int(count_match.group(1)) if count_match else 0
        successful = run.returncode == 0 and tests > 0 and "\nOK" in run.stderr
        result = {"schema": "pmrh.offline-test-receipt/1",
                  "suite": suite, "source_sha": env["PMRH_SOURCE_SHA"],
                  "python": sys.version, "tests": tests,
                  "status": "PASS" if successful else "FAIL",
                  "exit_code": run.returncode,
                  "elapsed_seconds": round(time.monotonic() - began, 4),
                  "child_processes": 1,
                  "research_model_calls": model_measurement(),
                  "synthetic_only": True,
                  "security_guarantee": "PYTHON_LEVEL_DEFENSE_IN_DEPTH_ONLY_NOT_OS_SANDBOX",
                  "environment_keys": sorted(env),
                  "output_sha256": hashlib.sha256(transcript).hexdigest()}
        if out_fd is not None:
            _write_artifact_fd(out_fd, "unittest.log", transcript)
            _write_artifact_fd(out_fd, "receipt.json",
                               (json.dumps(result, indent=2) + "\n").encode("utf-8"))
        print("PMRH_OFFLINE_TEST=" + json.dumps(result, sort_keys=True), flush=True)
        if not successful:
            print(run.stderr[-9000:], file=sys.stderr)
        return result


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument("--suite", default="devpr01", choices=sorted(SUITES))
    p.add_argument("--out", type=Path)
    p.add_argument("--forbidden-root", action="append", default=[],
                   help="Additional filesystem root to deny in guarded unittest process")
    args, unexpected = p.parse_known_args(argv)
    if unexpected or any(x in BLOCKED_ARGUMENTS for x in (argv or [])):
        p.error("arbitrary/unreviewed test selection and runtime arguments are prohibited")
    return 0 if execute(args.suite, out=args.out,
                        forbidden_roots=args.forbidden_root)["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
