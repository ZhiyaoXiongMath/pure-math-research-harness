#!/usr/bin/env python3
"""Fixed DEV-PR-02 synthetic test entrypoint; reuses the unchanged DEV-PR-01 guard.

The only child is stdlib unittest discovery in tests/devpr02. No suite, script,
project, backend or arbitrary command can be selected. Python-level guard only,
not an OS security sandbox. CI infrastructure may use the network separately.
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

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import offline_test as baseline
from scripts.verify_devpr02_artifacts import source_fingerprints

SCHEMA = "pmrh.devpr02-ci-receipt/1.0"
COMMAND_TAIL = ["-B", "-m", "unittest", "discover", "-s", "tests/devpr02", "-p", "test_*.py", "-t", ".", "-v"]
KNOWN_UNEXECUTED = [
    "PRODUCTION_AUTHENTICATION_FENCING_AND_BUDGET_TRANSACTIONS",
    "JOURNAL_BLOB_CRASH_RECOVERY_AND_MIGRATION",
    "REAL_CODEX_NATIVE_ROOT_TURN_GATE_AND_PROVIDER_API",
    "REAL_MODEL_USAGE_AND_BILLING_TELEMETRY",
    "OS_LEVEL_HOSTILE_PROCESS_ISOLATION",
    "LEGACY_FULL_PRODUCT_SUITE_AND_REAL_RESEARCH",
    "FUTURE_58_PLUS_46_ACCEPTANCE_MATRIX",
]


def _text(value) -> str:
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else (value or "")


def execute(*, out: Path, forbidden_roots: list[str] | None = None) -> dict:
    # Reuse the exact preflight and pinned descriptor writer; never modify the
    # old suite allowlist. A failed preflight has no child or output side effect.
    out_fd = baseline._isolated_artifact_directory(out)
    try:
        before = source_fingerprints(ROOT)
        with tempfile.TemporaryDirectory(prefix="pmrh-devpr02-offline-") as folder:
            environment = baseline.environment(Path(folder), forbidden_roots=forbidden_roots)
            command = [sys.executable, *COMMAND_TAIL]
            error = None
            try:
                run = subprocess.run(command, cwd=ROOT, env=environment, text=True,
                                     capture_output=True, timeout=120, check=False)
                stdout, stderr, exit_code = _text(run.stdout), _text(run.stderr), run.returncode
            except subprocess.TimeoutExpired as exc:
                stdout, stderr, exit_code = _text(exc.stdout), _text(exc.stderr), None
                error = {"kind": "TIMEOUT", "phase": "unittest_child", "timeout_seconds": 120}
            except (OSError, subprocess.SubprocessError):
                stdout, stderr, exit_code = "", "", None
                error = {"kind": "PROCESS_START_OR_TRANSPORT_ERROR", "phase": "unittest_child"}
            if error is not None:
                stderr += "\nPMRH_CONTRACT_EXECUTION_ERROR=" + json.dumps(error, sort_keys=True) + "\n"
            raw = (stdout + "\n" + stderr).encode("utf-8")
            matches = re.findall(r"\bRan (\d+) tests? in [^\n]+", stderr)
            count = int(matches[-1]) if matches else (None if error else 0)
            unchanged = before == source_fingerprints(ROOT)
            success = error is None and exit_code == 0 and count is not None and count > 0 and "\nOK\n" in stderr and unchanged
            status = "PASS" if success else ("ERROR" if error else "FAIL")
            version = str(sys.version_info.major) + "." + str(sys.version_info.minor)
            sha = environment["PMRH_SOURCE_SHA"]
            result = {
                "schema_version": SCHEMA, "dto_schema_version": "pmrh.ports/1.0", "suite": "devpr02",
                "source_sha": sha, "checkout_sha": os.environ.get("PMRH_CHECKOUT_SHA", "UNVERIFIED_LOCAL"),
                "checkout_tree": os.environ.get("PMRH_CHECKOUT_TREE", "UNVERIFIED_LOCAL"),
                "test_command": command,
                "test_environment": {"python": sys.version, "platform": sys.platform,
                                     "python_minor": version, "environment_keys": sorted(environment),
                                     "isolated_home": True, "synthetic_only": True,
                                     "guard": "PYTHON_LEVEL_DEFENSE_IN_DEPTH_ONLY_NOT_OS_SANDBOX",
                                     "ci_infrastructure_network": "NOT_MEASURED"},
                "test_count": count, "pass_fail_status": status, "exit_code": exit_code,
                "execution_error": error, "source_unchanged": unchanged,
                "source_files_sha256": before, "raw_log_sha256": hashlib.sha256(raw).hexdigest(),
                "artifact_identity": "pmrh-devpr02-contracts-" + sha + "-py" + version,
                "known_unexecuted_checks": KNOWN_UNEXECUTED,
                "research_model_calls": baseline.model_measurement(),
            }
            baseline._write_artifact_fd(out_fd, "unittest.log", raw)
            baseline._write_artifact_fd(out_fd, "receipt.json", (json.dumps(result, indent=2, sort_keys=True) + "\n").encode())
            print("PMRH_CONTRACT_TEST=" + json.dumps(result, sort_keys=True), flush=True)
            if not success:
                print(stderr[-18000:], file=sys.stderr)
            return result
    finally:
        os.close(out_fd)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--forbidden-root", action="append", default=[])
    args = parser.parse_args(argv)
    return 0 if execute(out=args.out, forbidden_roots=args.forbidden_root)["pass_fail_status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
