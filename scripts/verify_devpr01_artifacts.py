#!/usr/bin/env python3
"""Hard CI gate: required DEV-PR-01 AST and offline receipts must be complete.

Pure standard-library read-only verification. A partially uploaded folder, a
successful test command with no receipt, a mismatched log hash, or an incorrect
source SHA cannot pass. The uploader is a separate CI step that must succeed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

try:
    from scripts.verify_devpr02_artifacts import validate_named_couplings
except ModuleNotFoundError:
    from verify_devpr02_artifacts import validate_named_couplings

REQUIRED = (
    "ast/dependency-graph.json",
    "ast/architecture-audit.md",
    "offline/receipt.json",
    "offline/unittest.log",
)


def validate(root: Path, expected_sha: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise ValueError("expected HEAD must be an exact 40-char Git SHA")
    data = {}
    digests = {}
    for relative in REQUIRED:
        file = root / relative
        if file.is_symlink() or not file.is_file():
            raise ValueError("required CI artifact missing or symbolic link: " + relative)
        blob = file.read_bytes()
        if not blob:
            raise ValueError("required CI artifact empty: " + relative)
        data[relative] = blob
        digests[relative] = hashlib.sha256(blob).hexdigest()

    graph = json.loads(data["ast/dependency-graph.json"])
    if graph.get("schema") != "pmrh.ast-import-baseline/1":
        raise ValueError("AST artifact schema mismatch")
    for required in ("direct_graph", "transitive_graph", "strongly_connected_components",
                     "source_sha256", "legacy_migration_blockers",
                     "named_architectural_couplings", "architecture_violations"):
        if required not in graph:
            raise ValueError("AST artifact missing field: " + required)
    if graph["architecture_violations"] or graph.get("syntax_errors"):
        raise ValueError("AST artifact contains architecture violations or parse failures")
    if graph.get("counts", {}).get("unresolved_new_layer_imports", 0):
        raise ValueError("AST artifact has unresolved imports in new layered package")
    validate_named_couplings(graph)
    if b"DEV-PR-01" not in data["ast/architecture-audit.md"]:
        raise ValueError("Markdown architecture report identity missing")

    receipt = json.loads(data["offline/receipt.json"])
    if receipt.get("schema") != "pmrh.offline-test-receipt/1":
        raise ValueError("offline receipt schema mismatch")
    if receipt.get("suite") != "devpr01" or receipt.get("status") != "PASS":
        raise ValueError("synthetic-only offline tests did not PASS")
    if receipt.get("source_sha") != expected_sha:
        raise ValueError("receipt HEAD SHA differs from the exact PR source SHA")
    if receipt.get("exit_code") != 0 or receipt.get("execution_error") is not None:
        raise ValueError("offline receipt has a child execution failure")
    if not receipt.get("synthetic_only") or receipt.get("security_guarantee") != (
        "PYTHON_LEVEL_DEFENSE_IN_DEPTH_ONLY_NOT_OS_SANDBOX"
    ):
        raise ValueError("offline receipt scope/security qualification mismatch")
    if receipt.get("research_model_calls", {}).get("count", "INVALID") is not None:
        raise ValueError("offline receipt falsely claims a measured provider call count")
    if receipt.get("research_model_calls", {}).get("zero_calls_verified") is not False:
        raise ValueError("offline receipt misstates external model-call verification")

    log = data["offline/unittest.log"]
    if receipt.get("output_sha256") != digests["offline/unittest.log"]:
        raise ValueError("raw unittest log checksum mismatch")
    completed = re.findall(rb"\bRan (\d+) tests? in [^\n]+\n\nOK(?:\s|$)", log)
    if not completed:
        raise ValueError("required raw unittest success footer missing")
    observed = int(completed[-1])
    if receipt.get("tests") != observed or observed < 1:
        raise ValueError("unittest raw log count differs from receipt or is zero")

    return {"schema": "pmrh.ci-artifact-gate/1",
            "status": "PASS",
            "source_sha": expected_sha,
            "tests": observed,
            "files": digests}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--expected-head-sha", required=True)
    args = p.parse_args(argv)
    try:
        evidence = validate(args.root, args.expected_head_sha)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print("PMRH_REQUIRED_ARTIFACTS=FAIL: " + str(exc), file=sys.stderr)
        return 1
    print("PMRH_REQUIRED_ARTIFACTS=" + json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
