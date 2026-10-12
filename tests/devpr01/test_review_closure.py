"""Synthetic independent-review closure tests (four MAJOR and two MINOR).

Only tiny temporary files and in-process stubs; no network, scientific
project, real model, legacy test runner or external child invocation.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from scripts import architecture_deps as deps
from scripts import offline_test
from scripts import verify_devpr01_artifacts as verifier


HEAD = "a" * 40
POLICY = {
    "legacy_exception_id": "SYNTHETIC-ONLY",
    "legacy_baseline_commit": "e4de0210f9985224e030ac4cfd2f7e2904005b37",
    "legacy_owners": {name: "DEV-PR-18" for name in
                      ("domain", "application", "ports", "adapters",
                       "orchestration", "observability", "interfaces",
                       "legacy", "retire", "bootstrap", "unassigned")},
}


@contextmanager
def temporary_attribute(obj, key, value):
    previous = getattr(obj, key)
    setattr(obj, key, value)
    try:
        yield
    finally:
        setattr(obj, key, previous)


@contextmanager
def temporary_environment(key, value):
    former = os.environ.get(key)
    os.environ[key] = value
    try:
        yield
    finally:
        if former is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = former


class ASTReviewClosure(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="pmrh-review-ast-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.put("docs/reference/PMRS-Next_Phase1/source-inventory.json",
                 json.dumps({"modules": []}))

    def put(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def scan(self, policy=None):
        return deps.run(self.root, policy or POLICY)

    def test_AST_01_importlib_function_direct_and_as_alias(self):
        self.put("pmrh/domain/reader.py",
                 'from importlib import import_module as load\n'
                 'load("pmrh.adapters")\n'
                 'from importlib import import_module\n'
                 'import_module("pmrh.adapters")\n')
        self.put("pmrh/adapters/backend.py", "VALUE = 1\n")
        result = self.scan()
        arrows = [x for x in result["direct_imports"]
                  if x["source"] == "pmrh/domain/reader.py" and x["kind"] == "dynamic_literal"]
        self.assertEqual(len(arrows), 2)
        self.assertTrue(all(x["target"] == "@namespace/pmrh/adapters" for x in arrows))
        self.assertTrue(any(x["reason"] == "forbidden_new_layer_direction"
                            for x in result["architecture_violations"]))

    def test_AST_01_module_alias_and_builtin_direct_legal_patterns(self):
        self.put("pmrh/domain/reader.py",
                 'import importlib as il\n'
                 'il.import_module("pmrh.adapters")\n'
                 '__import__("pmrh.adapters")\n')
        self.put("pmrh/adapters/backend.py", "VALUE = 1\n")
        result = self.scan()
        self.assertEqual(sum(x["kind"] == "dynamic_literal"
                             and x["target"] == "@namespace/pmrh/adapters"
                             for x in result["direct_imports"]), 2)

    def test_AST_01_unresolved_nonliteral_and_shadowed_fail_closed(self):
        self.put("pmrh/domain/reader.py",
                 "from importlib import import_module as load\n"
                 "load = lambda value: value\n"
                 "load('pmrh.adapters')\n"
                 "import importlib as il\n"
                 "il.import_module(variable_name)\n")
        self.put("pmrh/adapters/backend.py", "VALUE = 1\n")
        result = self.scan()
        unresolved = {x["kind"] for x in result["dynamic_unresolved"]}
        self.assertIn("dynamic_binding_shadowed", unresolved)
        self.assertIn("dynamic_nonliteral", unresolved)
        self.assertEqual(result["counts"]["unresolved_new_layer_imports"], 2)
        self.assertEqual(sum(x["reason"] == "unresolved_dynamic_import"
                             for x in result["architecture_violations"]), 2)

    def test_AST_01_unrelated_same_named_function_is_not_importlib(self):
        self.put("pmrh/domain/helpers.py", "def load(x):\n    return x\n")
        self.put("pmrh/application/service.py",
                 "from pmrh.domain.helpers import load\n"
                 "value = load('pmrh.adapters')\n")
        self.put("pmrh/adapters/backend.py", "VALUE = 1\n")
        result = self.scan()
        self.assertEqual(result["architecture_violations"], [])
        self.assertEqual(result["dynamic_unresolved"], [])

    def test_AST_02_bridge_transitive_violation_and_unclassified_root(self):
        self.put("pmrh/domain/reader.py", "import pmrh.bridge\n")
        self.put("pmrh/bridge.py", "import pmrh.adapters\n")
        self.put("pmrh/adapters/backend.py", "VALUE = 1\n")
        result = self.scan()
        reasons = {x["reason"] for x in result["architecture_violations"]}
        self.assertIn("unclassified_pmrh_module", reasons)
        self.assertIn("unclassified_dependency_endpoint", reasons)
        self.assertIn("forbidden_transitive_dependency", reasons)
        self.assertIn("@namespace/pmrh/adapters",
                      result["transitive_graph"]["pmrh/domain/reader.py"])

    def test_AST_02_unknown_root_even_without_imports_is_review_required(self):
        self.put("pmrh/orphan.py", "VALUE = 'synthetic'\n")
        result = self.scan()
        self.assertIn("unclassified_pmrh_module",
                      {x["reason"] for x in result["architecture_violations"]})

    def test_AST_02_root_initializer_cannot_hide_adapter_import(self):
        self.put("pmrh/__init__.py", "import pmrh.adapters\n")
        self.put("pmrh/adapters/backend.py", "VALUE = 1\n")
        result = self.scan()
        self.assertIn("forbidden_new_layer_direction",
                      {x["reason"] for x in result["architecture_violations"]})

    def test_AST_02_root_metadata_and_cli_entrypoints_remain_legal(self):
        self.put("pmrh/__init__.py", "__version__ = 'test'\n")
        self.put("pmrh/__main__.py", "from .cli import main\n")
        self.put("pmrh/cli.py", "from . import __version__\n")
        self.put("pmrh/application/service.py", "from pmrh.ports import contracts\n")
        self.put("pmrh/ports/contracts.py", "from pmrh.domain import types\n")
        self.put("pmrh/domain/types.py", "VALUE = 1\n")
        result = self.scan()
        self.assertEqual(result["architecture_violations"], [])
        self.assertFalse(result["dynamic_unresolved"])

    def test_AST_03_named_same_layer_coupling_separately_visible(self):
        source = self.put("research_studio/store.py", "from . import native_main\n")
        target = self.put("research_studio/native_main.py", "VALUE = 'synthetic'\n")
        manifest = [{"path": p.relative_to(self.root).as_posix(),
                     "target": "adapters/storage" if p == source else "adapters/codex",
                     "bytes": p.stat().st_size} for p in (source, target)]
        self.put("docs/reference/PMRS-Next_Phase1/source-inventory.json",
                 json.dumps({"modules": manifest}))
        policy = {**POLICY, "named_blockers": [
            {"source": "research_studio/store.py",
             "target": "research_studio/native_main.py",
             "owner": "DEV-PR-05", "reason": "synthetic same layer"}]}
        result = self.scan(policy)
        self.assertEqual(result["legacy_migration_blockers"], [])
        matched = result["named_architectural_couplings"][0]
        self.assertEqual(matched["status"], "MATCHED_DIRECT_EDGE")
        self.assertEqual(matched["cross_layer_occurrences"], 0)
        self.assertEqual(matched["direct_occurrences"], 1)
        self.assertEqual(result["architecture_violations"], [])

    def test_AST_03_missing_named_coupling_cannot_be_silent(self):
        self.put("research_studio/store.py", "VALUE = 'synthetic'\n")
        p = self.root / "research_studio/store.py"
        self.put("docs/reference/PMRS-Next_Phase1/source-inventory.json",
                 json.dumps({"modules": [{"path": "research_studio/store.py",
                                          "target": "adapters/storage",
                                          "bytes": p.stat().st_size}]}))
        policy = {**POLICY, "named_blockers": [
            {"source": "research_studio/store.py",
             "target": "research_studio/native_main.py",
             "owner": "DEV-PR-05", "reason": "synthetic absent edge"}]}
        result = self.scan(policy)
        self.assertEqual(result["named_architectural_couplings"][0]["status"],
                         "MISSING_DIRECT_EDGE")
        self.assertIn("missing_named_legacy_coupling",
                      {x["reason"] for x in result["architecture_violations"]})


class OfflineReceiptReviewClosure(unittest.TestCase):
    def artifact_root(self):
        directory = tempfile.TemporaryDirectory(prefix="pmrh-devpr01-artifacts-")
        self.addCleanup(directory.cleanup)
        out = Path(directory.name) / "offline"
        out.mkdir()
        return Path(directory.name), out

    def test_TEST_01_timeout_creates_structured_error_and_preserves_partial_log(self):
        root, out = self.artifact_root()
        def timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(
                cmd=["synthetic-only"], timeout=120,
                output=b"synthetic captured stdout", stderr=b"synthetic stderr")
        with temporary_environment("PMRH_TEST_ARTIFACT_ROOT", str(root)), \
             temporary_attribute(offline_test.subprocess, "run", timeout):
            result = offline_test.execute("devpr01", out=out)
        self.assertEqual(result["status"], "ERROR")
        self.assertIsNone(result["tests"])
        self.assertIsNone(result["exit_code"])
        self.assertEqual(result["execution_error"]["kind"], "TIMEOUT")
        self.assertTrue(result["execution_error"]["partial_stdout_captured"])
        self.assertFalse(result["research_model_calls"]["zero_calls_verified"])
        self.assertIsNone(result["research_model_calls"]["count"])
        raw = (out / "unittest.log").read_bytes()
        self.assertIn(b"synthetic captured stdout", raw)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), result["output_sha256"])
        self.assertEqual(json.loads((out / "receipt.json").read_text())["status"], "ERROR")

    def test_TEST_01_subprocess_start_error_creates_structured_receipt(self):
        root, out = self.artifact_root()
        def error(*args, **kwargs):
            raise OSError("synthetic spawn refused")
        with temporary_environment("PMRH_TEST_ARTIFACT_ROOT", str(root)), \
             temporary_attribute(offline_test.subprocess, "run", error):
            result = offline_test.execute("devpr01", out=out)
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(result["execution_error"]["kind"], "PROCESS_START_OR_TRANSPORT_ERROR")
        self.assertIsNone(result["tests"])
        self.assertTrue((out / "unittest.log").is_file())
        self.assertTrue((out / "receipt.json").is_file())


class CIArtifactReviewClosure(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="pmrh-review-ci-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "ast").mkdir()
        (self.root / "offline").mkdir()
        self.graph = {
            "schema": "pmrh.ast-import-baseline/1",
            "direct_graph": {},
            "transitive_graph": {},
            "strongly_connected_components": [],
            "source_sha256": {"pmrh/__init__.py": "0" * 64},
            "legacy_migration_blockers": [],
            "named_architectural_couplings": [],
            "architecture_violations": [],
            "syntax_errors": [],
            "counts": {"unresolved_new_layer_imports": 0},
        }
        (self.root / "ast/dependency-graph.json").write_text(json.dumps(self.graph))
        (self.root / "ast/architecture-audit.md").write_text("# DEV-PR-01 synthetic report\n")
        self.log = b"test_synthetic ... ok\n\n----------------------------------------------------------------------\nRan 2 tests in 0.001s\n\nOK\n"
        (self.root / "offline/unittest.log").write_bytes(self.log)
        self.receipt = {
            "schema": "pmrh.offline-test-receipt/1",
            "suite": "devpr01",
            "status": "PASS",
            "source_sha": HEAD,
            "exit_code": 0,
            "execution_error": None,
            "synthetic_only": True,
            "security_guarantee": "PYTHON_LEVEL_DEFENSE_IN_DEPTH_ONLY_NOT_OS_SANDBOX",
            "research_model_calls": {"count": None, "measurement": "NOT_INSTRUMENTED",
                                     "zero_calls_verified": False},
            "tests": 2,
            "output_sha256": hashlib.sha256(self.log).hexdigest(),
        }
        (self.root / "offline/receipt.json").write_text(json.dumps(self.receipt))

    def validate(self):
        return verifier.validate(self.root, HEAD)

    def test_CI_01_positive_four_file_bundle_passes(self):
        accepted = self.validate()
        self.assertEqual(accepted["status"], "PASS")
        self.assertEqual(accepted["tests"], 2)
        self.assertEqual(len(accepted["files"]), 4)

    def test_CI_01_missing_receipt_and_missing_raw_log_both_fail(self):
        for file in ("offline/receipt.json", "offline/unittest.log"):
            path = self.root / file
            old = path.read_bytes()
            path.unlink()
            try:
                with self.assertRaisesRegex(ValueError, "required CI artifact"):
                    self.validate()
            finally:
                path.write_bytes(old)

    def test_CI_01_only_AST_outputs_cannot_be_green(self):
        for name in ("offline/receipt.json", "offline/unittest.log"):
            (self.root / name).unlink()
        with self.assertRaisesRegex(ValueError, "required CI artifact"):
            self.validate()

    def test_CI_01_log_tampering_and_wrong_source_fail(self):
        (self.root / "offline/unittest.log").write_bytes(self.log + b"TAMPERED")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            self.validate()
        (self.root / "offline/unittest.log").write_bytes(self.log)
        self.receipt["source_sha"] = "b" * 40
        (self.root / "offline/receipt.json").write_text(json.dumps(self.receipt))
        with self.assertRaisesRegex(ValueError, "HEAD SHA"):
            self.validate()

    def test_CI_01_misleading_receipt_or_AST_violation_fail(self):
        self.receipt["status"] = "ERROR"
        (self.root / "offline/receipt.json").write_text(json.dumps(self.receipt))
        with self.assertRaisesRegex(ValueError, "did not PASS"):
            self.validate()
        self.receipt["status"] = "PASS"
        (self.root / "offline/receipt.json").write_text(json.dumps(self.receipt))
        self.graph["architecture_violations"].append({"reason": "synthetic-banned"})
        (self.root / "ast/dependency-graph.json").write_text(json.dumps(self.graph))
        with self.assertRaisesRegex(ValueError, "architecture violations"):
            self.validate()

    def test_CI_01_workflow_has_no_swallowed_copy_or_warning_upload(self):
        workflow = (Path(__file__).resolve().parents[2] /
                    ".github/workflows/devpr01-offline.yml").read_text()
        # GitHub expressions and comments can contain ||; reject ignored
        # copy failures in executable command lines, not explanatory prose.
        for line in workflow.splitlines():
            if "cp -a" in line or "cp --" in line:
                self.assertNotIn("|| true", line)
                self.assertNotIn("2>/dev/null", line)
        self.assertNotIn("if-no-files-found: warn", workflow)
        self.assertIn("if-no-files-found: error", workflow)
        self.assertIn("verify_devpr01_artifacts.py", workflow)


if __name__ == "__main__":
    unittest.main()
