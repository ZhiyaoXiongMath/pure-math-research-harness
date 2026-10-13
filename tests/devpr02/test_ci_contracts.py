"""Controlled entrypoint and evidence-gate regressions; only synthetic scratch data."""
from __future__ import annotations

from contextlib import contextmanager, redirect_stderr, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

from scripts import architecture_deps, offline_test, offline_contracts
from scripts import verify_devpr02_artifacts as verifier

ROOT = Path(__file__).resolve().parents[2]
SHA, TREE = "a" * 40, "b" * 40


@contextmanager
def changed_attribute(obj, key, value):
    former = getattr(obj, key)
    setattr(obj, key, value)
    try:
        yield
    finally:
        setattr(obj, key, former)


@contextmanager
def changed_environment(key, value):
    former = os.environ.get(key)
    os.environ[key] = value
    try:
        yield
    finally:
        if former is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = former


class OfflineContractEntryTests(unittest.TestCase):
    def test_actual_child_guard_blocks_network_process_and_source_write(self):
        self.assertEqual(os.environ.get("PMRH_OFFLINE_GUARD"), "1")
        self.assertEqual(os.environ.get("PMRH_SYNTHETIC_ONLY"), "1")
        self.assertNotEqual(os.environ["HOME"], os.environ["PMRH_ORIGINAL_HOME"])
        with self.assertRaises(PermissionError):
            socket.socket()
        with self.assertRaises(PermissionError):
            subprocess.Popen([sys.executable, "--version"])
        sentinel = ROOT / "pmrh/_devpr02_forbidden_sentinel.txt"
        self.assertFalse(sentinel.exists())
        with self.assertRaises(PermissionError):
            sentinel.write_text("synthetic guard test")
        self.assertFalse(sentinel.exists())

    def test_original_suite_allowlist_and_fixed_new_command_unchanged(self):
        self.assertEqual(set(offline_test.SUITES), {"devpr01"})
        self.assertEqual(offline_contracts.COMMAND_TAIL,
                         ["-B", "-m", "unittest", "discover", "-s", "tests/devpr02", "-p", "test_*.py", "-t", ".", "-v"])
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            offline_contracts.main(["--suite", "legacy"])
        self.assertNotEqual(error.exception.code, 0)

    def artifact_directory(self):
        temp = tempfile.TemporaryDirectory(prefix="pmrh-devpr01-artifacts-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        out = root / "offline"
        out.mkdir()
        return root, out

    def execute_stub(self, stub):
        root, out = self.artifact_directory()
        with changed_environment("PMRH_TEST_ARTIFACT_ROOT", str(root)), \
             changed_attribute(offline_contracts.subprocess, "run", stub), \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            result = offline_contracts.execute(out=out)
        return result, out

    def test_timeout_preserves_partial_raw_log_and_structured_ERROR(self):
        def fail(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd=["synthetic"], timeout=120,
                                            output=b"synthetic partial output", stderr=b"synthetic partial stderr")
        receipt, out = self.execute_stub(fail)
        self.assertEqual(receipt["pass_fail_status"], "ERROR")
        self.assertIsNone(receipt["test_count"])
        self.assertEqual(receipt["execution_error"]["kind"], "TIMEOUT")
        raw = (out / "unittest.log").read_bytes()
        self.assertIn(b"synthetic partial output", raw)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), receipt["raw_log_sha256"])
        self.assertEqual(json.loads((out / "receipt.json").read_text())["pass_fail_status"], "ERROR")

    def test_process_start_error_has_receipt_without_raw_exception_secret(self):
        def fail(*args, **kwargs):
            raise OSError("synthetic-sensitive-exception-do-not-echo")
        receipt, out = self.execute_stub(fail)
        self.assertEqual(receipt["pass_fail_status"], "ERROR")
        self.assertEqual(receipt["execution_error"]["kind"], "PROCESS_START_OR_TRANSPORT_ERROR")
        self.assertNotIn("sensitive-exception", (out / "unittest.log").read_text())
        self.assertIsNone(receipt["research_model_calls"]["count"])
        self.assertFalse(receipt["research_model_calls"]["zero_calls_verified"])

    def test_child_failure_cannot_be_reported_as_PASS(self):
        def fail(*args, **kwargs):
            return SimpleNamespace(stdout="", stderr="Ran 1 test in 0.01s\n\nFAILED (failures=1)\n", returncode=1)
        receipt, out = self.execute_stub(fail)
        self.assertEqual(receipt["pass_fail_status"], "FAIL")
        self.assertEqual(receipt["test_count"], 1)
        self.assertTrue((out / "receipt.json").is_file())

    def test_bad_output_path_refused_before_any_child_call(self):
        root, _ = self.artifact_directory()
        calls = []
        def forbidden(*args, **kwargs):
            calls.append(1)
            raise AssertionError("Child must not run after failed output preflight")
        with changed_environment("PMRH_TEST_ARTIFACT_ROOT", str(root)), \
             changed_attribute(offline_contracts.subprocess, "run", forbidden), \
             self.assertRaises((ValueError, PermissionError)):
            offline_contracts.execute(out=ROOT / "pmrh")
        self.assertEqual(calls, [])

    def test_A01_full_inherited_AST_has_no_new_port_violations(self):
        policy = json.loads((ROOT / "config/architecture-exceptions.json").read_text())
        result = architecture_deps.run(ROOT, policy)
        self.assertEqual(result["architecture_violations"], [])
        self.assertEqual(result["syntax_errors"], [])
        self.assertTrue(any(path.startswith("pmrh/ports/") for path in result["source_sha256"]))


class ArtifactGateTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="pmrh-devpr02-gate-fixture-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / "source"
        for relative in (*verifier.SOURCE_SCRIPTS, "pmrh/__init__.py", "pmrh/ports/example.py", "tests/devpr02/test_example.py"):
            path = self.source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# SYNTHETIC_TEST_ONLY\n")
        (self.source / "tests/devpr02/test_example.py").write_text(
            "import unittest\nclass Example(unittest.TestCase):\n    def test_fixture(self): pass\n")
        (self.root / "ast").mkdir()
        (self.root / "offline").mkdir()
        sources = verifier.source_fingerprints(self.source)
        self.graph = {"schema": "pmrh.ast-import-baseline/1", "architecture_violations": [], "syntax_errors": [],
                      "direct_graph": {}, "transitive_graph": {}, "strongly_connected_components": [],
                      "source_sha256": sources, "named_architectural_couplings": [],
                      "counts": {"unresolved_new_layer_imports": 0}}
        (self.root / "ast/dependency-graph.json").write_text(json.dumps(self.graph))
        (self.root / "ast/architecture-audit.md").write_text("# DEV-PR-01 synthetic architecture fixture\n")
        self.log = b"test_fixture (tests.devpr02.test_example.Example.test_fixture) ... ok\n\n----------------------------------------------------------------------\nRan 1 test in 0.001s\n\nOK\n"
        (self.root / "offline/unittest.log").write_bytes(self.log)
        self.receipt = {
            "schema_version": "pmrh.devpr02-ci-receipt/1.0", "dto_schema_version": "pmrh.ports/1.0", "suite": "devpr02",
            "source_sha": SHA, "checkout_sha": SHA, "checkout_tree": TREE,
            "pass_fail_status": "PASS", "exit_code": 0, "execution_error": None, "source_unchanged": True,
            "test_command": ["synthetic-python", *offline_contracts.COMMAND_TAIL],
            "test_environment": {"guard": "PYTHON_LEVEL_DEFENSE_IN_DEPTH_ONLY_NOT_OS_SANDBOX", "isolated_home": True,
                                 "synthetic_only": True, "python_minor": "3.11", "ci_infrastructure_network": "NOT_MEASURED"},
            "artifact_identity": "pmrh-devpr02-contracts-" + SHA + "-py3.11",
            "research_model_calls": {"count": None, "zero_calls_verified": False, "observed_provider_events": "NOT_MEASURED"},
            "known_unexecuted_checks": offline_contracts.KNOWN_UNEXECUTED, "source_files_sha256": sources,
            "raw_log_sha256": hashlib.sha256(self.log).hexdigest(), "test_count": 1,
        }
        self.save()

    def save(self):
        (self.root / "offline/receipt.json").write_text(json.dumps(self.receipt))

    def validate(self):
        return verifier.validate(self.root, SHA, TREE, self.source)

    def test_complete_raw_evidence_bundle_passes(self):
        self.assertEqual(self.validate()["status"], "PASS")

    def test_missing_artifact_and_log_corruption_fail(self):
        for relative in verifier.REQUIRED:
            path = self.root / relative
            original = path.read_bytes()
            path.unlink()
            with self.assertRaises(ValueError):
                self.validate()
            path.write_bytes(original)
        (self.root / "offline/unittest.log").write_bytes(self.log + b"altered")
        with self.assertRaises(ValueError):
            self.validate()

    def test_source_SHA_tree_and_individual_test_count_mismatches_fail(self):
        for field, value in (("source_sha", "c" * 40), ("checkout_tree", "d" * 40), ("test_count", 99)):
            original = self.receipt[field]
            self.receipt[field] = value
            self.save()
            with self.assertRaises(ValueError):
                self.validate()
            self.receipt[field] = original
        self.save()
        path = self.source / "pmrh/ports/example.py"
        path.write_text("# different synthetic source\n")
        with self.assertRaises(ValueError):
            self.validate()

    def test_unmeasured_model_calls_cannot_be_zero_or_future_gates_PASS(self):
        self.receipt["research_model_calls"]["count"] = 0
        self.save()
        with self.assertRaises(ValueError):
            self.validate()
        self.receipt["research_model_calls"]["count"] = None
        self.receipt["known_unexecuted_checks"] = []
        self.save()
        with self.assertRaises(ValueError):
            self.validate()

    def test_AST_violation_is_not_ignored(self):
        self.graph["architecture_violations"] = [{"reason": "synthetic forbidden import"}]
        (self.root / "ast/dependency-graph.json").write_text(json.dumps(self.graph))
        with self.assertRaises(ValueError):
            self.validate()
