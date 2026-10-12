"""DEV-PR-01 security and AST regression tests: synthetic inputs exclusively.

Executed ONLY by scripts/offline_test.py with the offline sitecustomize guard.
No real project, native binary, scientific job, model SDK or network fixture.
"""
from __future__ import annotations

import ast
import builtins
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest

from scripts import architecture_deps as deps
from scripts import offline_test

REPO = Path(__file__).resolve().parents[2]


class PythonOfflineBoundaryTests(unittest.TestCase):
    def test_01_guard_is_active_and_environment_contains_no_credentials(self):
        self.assertEqual(os.environ.get("PMRH_OFFLINE_GUARD"), "1")
        self.assertEqual(os.environ.get("PMRH_SYNTHETIC_ONLY"), "1")
        self.assertEqual(builtins.open.__module__, "sitecustomize")
        for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GITHUB_TOKEN",
                     "GH_TOKEN", "AWS_SECRET_ACCESS_KEY", "CODEX_HOME"):
            self.assertNotIn(name, os.environ)
        self.assertNotEqual(str(Path.home().resolve()),
                            os.environ["PMRH_ORIGINAL_HOME"])

    def test_02_network_open_is_denied(self):
        with self.assertRaises(PermissionError):
            socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        with self.assertRaises(PermissionError):
            socket.create_connection(("127.0.0.1", 9), timeout=0.1)
        with self.assertRaises(PermissionError):
            socket.socketpair()

    def test_03_external_process_and_shell_are_denied(self):
        with self.assertRaises(PermissionError):
            subprocess.Popen([sys.executable, "--version"])
        with self.assertRaises(PermissionError):
            subprocess.run([sys.executable, "--version"])
        with self.assertRaises(PermissionError):
            os.system("echo should-never-run")
        if hasattr(os, "fork"):
            with self.assertRaises(PermissionError):
                os.fork()

    def test_04_actual_home_reads_and_writes_denied(self):
        secret = Path(os.environ["PMRH_ORIGINAL_HOME"]) / "synthetic-sensitive-name"
        with self.assertRaises(PermissionError):
            secret.read_text()
        with self.assertRaises(PermissionError):
            secret.write_text("must-not-exist")
        with self.assertRaises(PermissionError):
            os.open(secret, os.O_RDONLY)
        with self.assertRaises(PermissionError):
            os.listdir(secret.parent)

    def test_05_source_tree_and_project_paths_default_denied(self):
        with self.assertRaises(PermissionError):
            (REPO / "DO_NOT_CREATE_DEVPR01").write_text("forbidden")
        # A hypothetical project outside source, HOME and fixture is denied
        # without examining its existence.
        project = Path(tempfile.gettempdir()).parent / "synthetic-formal-project"
        with self.assertRaises(PermissionError):
            (project / "proof.json").write_text("forbidden")
        self.assertEqual((REPO / "pmrh/__init__.py").read_text().count("__version__"), 1)

    def test_06_synthetic_fixture_is_writable(self):
        with tempfile.TemporaryDirectory(prefix="pmrh-allowed-") as d:
            p = Path(d) / "synthetic.json"
            p.write_text('{"synthetic": true}', encoding="utf-8")
            self.assertTrue(json.loads(p.read_text())["synthetic"])

    def test_07_arbitrary_test_selector_not_available(self):
        self.assertEqual(set(offline_test.SUITES), {"devpr01"})
        self.assertEqual(offline_test.SUITES["devpr01"][0], "tests/devpr01")
        with self.assertRaises(SystemExit) as error:
            offline_test.main(["--suite", "test_final_native_boundaries"])
        self.assertEqual(error.exception.code, 2)

    def test_08_historical_runner_has_unsafe_execution_path(self):
        source = (REPO / "scripts/test-runner.py").read_text()
        parsed = ast.parse(source)
        self.assertTrue(any(isinstance(n, ast.Call) and
                            isinstance(n.func, ast.Attribute) and
                            n.func.attr == "run" and
                            isinstance(n.func.value, ast.Name) and
                            n.func.value.id == "subprocess" for n in ast.walk(parsed)))
        self.assertIn("os.environ", source)
        self.assertIn("out.parent.mkdir", source)
        # Its 'paid_model_calls: 0' receipt is a report, not prevention.
        self.assertIn("'paid_model_calls': 0", source)


class SyntheticASTTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix="pmrh-ast-fixture-")
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        self.policy = {
            "legacy_exception_id": "LEGACY-SYNTHETIC-FROZEN",
            "legacy_baseline_commit": "e4de0210f9985224e030ac4cfd2f7e2904005b37",
            "legacy_owners": {**{k: "DEV-PR-18" for k in
                                 ("domain", "ports", "application", "adapters",
                                  "orchestration", "legacy", "observability",
                                  "interfaces", "retire", "bootstrap", "unassigned")},
                              "domain": "DEV-PR-04", "adapters": "DEV-PR-07"},
        }

    def put(self, path, source):
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(source, encoding="utf-8")
        return p

    def inventory(self, mapping):
        items = [{"path": path, "target": target,
                  "bytes": (self.root / path).stat().st_size}
                 for path, target in mapping.items()]
        self.put("docs/reference/PMRS-Next_Phase1/source-inventory.json",
                 json.dumps({"modules": items}))

    def test_09_direct_transitive_relative_lazy_and_dynamic_literal(self):
        self.put("pmrh/__init__.py", "")
        self.put("pmrh/domain/__init__.py", "")
        self.put("pmrh/domain/a.py", "from . import b\n")
        self.put("pmrh/domain/b.py",
                 "def f():\n    from pmrh.domain import c\n"
                 "import importlib\nx = importlib.import_module('pmrh.domain.a')\n")
        self.put("pmrh/domain/c.py", "import pmrh.domain.a\n")
        paths, edges, _, dynamic, errors, _, _ = deps.graph_from(self.root)
        self.assertFalse(errors)
        triples = {(e["source"], e["target"]) for e in edges}
        self.assertIn(("pmrh/domain/a.py", "pmrh/domain/b.py"), triples)
        self.assertIn(("pmrh/domain/b.py", "pmrh/domain/c.py"), triples)
        self.assertIn(("pmrh/domain/c.py", "pmrh/domain/a.py"), triples)
        self.assertTrue(any(e["kind"] == "dynamic_literal" for e in edges))
        self.assertEqual(dynamic, [])
        adjacent = {p.relative_to(self.root).as_posix(): set() for p in paths}
        for edge in edges:
            adjacent[edge["source"]].add(edge["target"])
        comp = deps.components(sorted(adjacent), adjacent)
        self.assertTrue(any(set(x) == {"pmrh/domain/a.py", "pmrh/domain/b.py",
                                      "pmrh/domain/c.py"} for x in comp))
        transitive = deps.closure(list(adjacent), adjacent)
        self.assertIn("pmrh/domain/c.py", transitive["pmrh/domain/a.py"])

    def test_10_new_layer_dependency_direction_fails_closed(self):
        self.put("pmrh/domain/rules.py", "from pmrh.adapters import codex\n")
        self.put("pmrh/adapters/codex.py", "x = 1\n")
        self.inventory({})
        report = deps.run(self.root, self.policy)
        reasons = {v["reason"] for v in report["architecture_violations"]}
        self.assertIn("forbidden_new_layer_direction", reasons)
        self.assertEqual(report["counts"]["architecture_violations"], 1)

    def test_11_forbidden_capability_and_legacy_backreference(self):
        self.put("pmrh/ports/spec.py", "import socket\n")
        self.put("pmrh/domain/rules.py", "import sqlite3\n")
        self.put("research_studio/old.py", "import pmrh.ports.spec\n")
        self.inventory({"research_studio/old.py": "application/execution"})
        result = deps.run(self.root, self.policy)
        kinds = [x["reason"] for x in result["architecture_violations"]]
        self.assertEqual(kinds.count("prohibited_capability_import"), 2)
        self.assertIn("legacy_may_not_depend_on_new_package", kinds)

    def test_12_existing_legacy_cross_layer_edges_are_exact_and_owned(self):
        self.put("research_studio/__init__.py", "")
        self.put("research_studio/store.py", "from . import native_main\n")
        self.put("research_studio/native_main.py", "STATE = 'synthetic'\n")
        self.inventory({"research_studio/__init__.py": "package",
                        "research_studio/store.py": "adapters/storage",
                        "research_studio/native_main.py": "adapters/codex"})
        report = deps.run(self.root, self.policy)
        self.assertEqual(report["architecture_violations"], [])
        # Same broad 'adapters' destination requires finer ownership/PR review.
        self.assertEqual(report["legacy_migration_blockers"], [])
        self.put("research_studio/native_main.py", "STATE = 'synthetic'\n"
                 "def wait(): pass\n")
        report = deps.run(self.root, self.policy)
        self.assertIn("legacy_inventory_mismatch",
                      [v["reason"] for v in report["architecture_violations"]])

    def test_13_dynamic_nonliteral_and_syntax_error_are_visible(self):
        self.put("pmrh/domain/rules.py", "import importlib\n\ndef f(name):\n"
                 "    return importlib.import_module(name)\n")
        self.put("pmrh/domain/broken.py", "def a(:\n pass\n")
        self.inventory({})
        report = deps.run(self.root, self.policy)
        self.assertEqual(report["counts"]["parse_failures"], 1)
        self.assertEqual(report["counts"]["nonliteral_imports"], 1)
        self.assertEqual(report["dynamic_unresolved"][0]["kind"], "dynamic_nonliteral")

    def test_14_legacy_cross_layer_migration_debt_is_identified(self):
        self.put("research_studio/__init__.py", "")
        self.put("research_studio/engine.py", "from . import store\n")
        self.put("research_studio/store.py", "pass\n")
        self.inventory({"research_studio/__init__.py": "package",
                        "research_studio/engine.py": "application/research",
                        "research_studio/store.py": "adapters/storage"})
        report = deps.run(self.root, self.policy)
        blockers = report["legacy_migration_blockers"]
        self.assertEqual(len(blockers), 1)
        self.assertEqual(blockers[0]["owner"], "DEV-PR-18")
        self.assertEqual(blockers[0]["target"], "research_studio/store.py")
        self.assertEqual(blockers[0]["exception_id"], "LEGACY-SYNTHETIC-FROZEN")


if __name__ == "__main__":
    unittest.main()
