#!/usr/bin/env python3
"""Restricted, opt-in, synthetic-only DEV-PR-01 offline unittest launcher.

Default suite is narrowly allowlisted. Never dispatch the historical runner,
real research tests, Codex, or any research CLI. sitecustomize is a Python
defense-in-depth guard, NOT an operating-system sandbox.
"""
from __future__ import annotations

import argparse
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
    began = time.monotonic()
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
                  "research_model_calls": 0 if successful else "UNOBSERVED",
                  "synthetic_only": True,
                  "security_guarantee": "PYTHON_LEVEL_DEFENSE_IN_DEPTH_ONLY_NOT_OS_SANDBOX",
                  "environment_keys": sorted(env),
                  "output_sha256": hashlib.sha256(transcript).hexdigest()}
        if out is not None:
            out = out.resolve()
            if out == ROOT or ROOT in out.parents:
                raise ValueError("--out cannot write inside the source tree")
            if out == Path.home().resolve() or out == Path.home().resolve().parent:
                raise ValueError("--out may not target HOME")
            out.mkdir(parents=True, exist_ok=True)
            (out / "unittest.log").write_bytes(transcript)
            (out / "receipt.json").write_text(json.dumps(result, indent=2) + "\n",
                                               encoding="utf-8")
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
