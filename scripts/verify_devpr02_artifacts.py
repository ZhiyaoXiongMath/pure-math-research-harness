#!/usr/bin/env python3
"""Read-only, fail-closed DEV-PR-02 evidence verifier. Never repairs artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

REQUIRED = ("ast/dependency-graph.json", "ast/architecture-audit.md", "offline/receipt.json", "offline/unittest.log")
SOURCE_SCRIPTS = ("scripts/offline_contracts.py", "scripts/verify_devpr02_artifacts.py",
                  "scripts/offline_test.py", "scripts/offline_guard/sitecustomize.py", "scripts/architecture_deps.py")


def source_fingerprints(root: Path) -> dict[str, str]:
    paths = [*sorted((root / "pmrh/ports").rglob("*.py")), *sorted((root / "tests/devpr02").rglob("*.py")),
             *(root / path for path in SOURCE_SCRIPTS), root / "pmrh/__init__.py"]
    result = {}
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise ValueError("A required contract source is absent or a symbolic link")
        result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not any(p.startswith("tests/devpr02/test_") for p in result):
        raise ValueError("No contract tests were found")
    return dict(sorted(result.items()))


def validate(root: Path, expected_sha: str, expected_tree: str, source_root: Path) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", expected_sha) or not re.fullmatch(r"[0-9a-f]{40}", expected_tree):
        raise ValueError("Exact source commit and tree SHA required")
    payloads, digests = {}, {}
    for relative in REQUIRED:
        path = root / relative
        if path.is_symlink() or path.parent.is_symlink() or not path.is_file():
            raise ValueError("Required contract artifact missing or linked: " + relative)
        raw = path.read_bytes()
        if not raw:
            raise ValueError("Required contract artifact empty: " + relative)
        payloads[relative] = raw
        digests[relative] = hashlib.sha256(raw).hexdigest()
    receipt = json.loads(payloads["offline/receipt.json"])
    if receipt.get("schema_version") != "pmrh.devpr02-ci-receipt/1.0" or receipt.get("dto_schema_version") != "pmrh.ports/1.0":
        raise ValueError("Contract receipt schema mismatch")
    if receipt.get("suite") != "devpr02" or receipt.get("pass_fail_status") != "PASS":
        raise ValueError("Contract tests did not PASS")
    if receipt.get("source_sha") != expected_sha or receipt.get("checkout_sha") != expected_sha or receipt.get("checkout_tree") != expected_tree:
        raise ValueError("Receipt source commit/tree mismatch")
    if receipt.get("exit_code") != 0 or receipt.get("execution_error") is not None or receipt.get("source_unchanged") is not True:
        raise ValueError("Child failed or changed the source")
    expected_tail = ["-B", "-m", "unittest", "discover", "-s", "tests/devpr02", "-p", "test_*.py", "-t", ".", "-v"]
    if receipt.get("test_command", [])[1:] != expected_tail:
        raise ValueError("Unapproved contract test command")
    env = receipt.get("test_environment", {})
    if env.get("guard") != "PYTHON_LEVEL_DEFENSE_IN_DEPTH_ONLY_NOT_OS_SANDBOX" or env.get("isolated_home") is not True or env.get("synthetic_only") is not True:
        raise ValueError("Contract environment scope mismatch")
    if env.get("ci_infrastructure_network") != "NOT_MEASURED":
        raise ValueError("Unmeasured CI infrastructure network was misrepresented")
    minor = env.get("python_minor")
    if not isinstance(minor, str) or not re.fullmatch(r"3\.(?:1[1-9]|[2-9][0-9])", minor):
        raise ValueError("Python 3.11+ evidence required")
    if receipt.get("artifact_identity") != "pmrh-devpr02-contracts-" + expected_sha + "-py" + minor:
        raise ValueError("Artifact identity mismatch")
    measurement = receipt.get("research_model_calls", {})
    if measurement.get("count", "INVALID") is not None or measurement.get("zero_calls_verified") is not False or measurement.get("observed_provider_events") != "NOT_MEASURED":
        raise ValueError("Unmeasured model usage was misrepresented")
    required_unexecuted = {"PRODUCTION_AUTHENTICATION_FENCING_AND_BUDGET_TRANSACTIONS",
                          "JOURNAL_BLOB_CRASH_RECOVERY_AND_MIGRATION", "REAL_CODEX_NATIVE_ROOT_TURN_GATE_AND_PROVIDER_API",
                          "REAL_MODEL_USAGE_AND_BILLING_TELEMETRY", "OS_LEVEL_HOSTILE_PROCESS_ISOLATION",
                          "LEGACY_FULL_PRODUCT_SUITE_AND_REAL_RESEARCH", "FUTURE_58_PLUS_46_ACCEPTANCE_MATRIX"}
    if set(receipt.get("known_unexecuted_checks", [])) != required_unexecuted:
        raise ValueError("Unexecuted check boundaries missing")
    actual_sources = source_fingerprints(source_root)
    if receipt.get("source_files_sha256") != actual_sources:
        raise ValueError("Contract source fingerprints mismatch")
    graph = json.loads(payloads["ast/dependency-graph.json"])
    if graph.get("schema") != "pmrh.ast-import-baseline/1" or graph.get("architecture_violations") != [] or graph.get("syntax_errors") != []:
        raise ValueError("AST contract gate failed")
    for field in ("direct_graph", "transitive_graph", "strongly_connected_components", "source_sha256", "named_architectural_couplings"):
        if field not in graph:
            raise ValueError("AST evidence incomplete")
    if graph.get("counts", {}).get("unresolved_new_layer_imports") != 0:
        raise ValueError("New package contains unresolved imports")
    if any(graph["source_sha256"].get(name) != value for name, value in actual_sources.items()):
        raise ValueError("AST graph and tested source fingerprints differ")
    if any(item.get("status") != "MATCHED_DIRECT_EDGE" for item in graph["named_architectural_couplings"]):
        raise ValueError("A legacy named coupling vanished")
    if b"DEV-PR-01" not in payloads["ast/architecture-audit.md"]:
        raise ValueError("Inherited architecture report identity missing")
    raw_log = payloads["offline/unittest.log"]
    if receipt.get("raw_log_sha256") != digests["offline/unittest.log"]:
        raise ValueError("Raw contract log digest mismatch")
    footers = re.findall(rb"\bRan (\d+) tests? in [^\n]+\n\nOK(?:\s|$)", raw_log)
    names = re.findall(rb"^test_[^\n]+ \.\.\. ok$", raw_log, re.MULTILINE)
    if not footers:
        raise ValueError("Raw unittest success footer absent")
    count = int(footers[-1])
    if type(receipt.get("test_count")) is not int or receipt["test_count"] != count or count < 1 or len(names) != count:
        raise ValueError("Actual individual test log count differs from receipt")
    return {"schema_version": "pmrh.devpr02-artifact-gate/1.0", "status": "PASS", "source_sha": expected_sha,
            "source_tree": expected_tree, "test_count": count, "files": digests,
            "artifact_identity": receipt["artifact_identity"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--expected-head-sha", required=True)
    parser.add_argument("--expected-tree-sha", required=True)
    args = parser.parse_args(argv)
    try:
        receipt = validate(args.root, args.expected_head_sha, args.expected_tree_sha, args.source_root)
    except (OSError, ValueError, TypeError, KeyError):
        print("PMRH_DEVPR02_ARTIFACT_GATE=FAIL", file=sys.stderr)
        return 1
    print("PMRH_DEVPR02_ARTIFACT_GATE=" + json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
