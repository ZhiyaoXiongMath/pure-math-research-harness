"""Independent review synthetic MAJOR counterexamples (SEC-01, AST-01, AST-02).

Before code fixes these were expected to fail, documenting the review defects.
No actual scientific project files or model execution are involved.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts import architecture_deps as deps

ROOT = Path(__file__).resolve().parents[2]
POLICY = {
    "legacy_exception_id": "LEGACY-SYNTHETIC",
    "legacy_baseline_commit": "e4de0210f9985224e030ac4cfd2f7e2904005b37",
    "legacy_owners": {x: "DEV-PR-18" for x in (
        "domain", "ports", "application", "adapters", "orchestration",
        "observability", "interfaces", "legacy", "retire", "bootstrap", "unassigned")},
}


class IndependentMajors(unittest.TestCase):
    def test_SEC_01_forbid_source_hardlink_to_scratch_without_changing_sha(self):
        source = ROOT / "pmrh/__init__.py"
        original = hashlib.sha256(source.read_bytes()).hexdigest()
        with TemporaryDirectory(prefix="pmrh-review-sec-01-") as folder:
            target = Path(folder) / "hardlink_alias.py"
            try:
                with self.assertRaises(PermissionError):
                    os.link(source, target)
                self.assertFalse(target.exists())
                with self.assertRaises(PermissionError):
                    source.write_text("NEVER WRITE TO REAL REPO")
            finally:
                self.assertEqual(original, hashlib.sha256(source.read_bytes()).hexdigest())
            # Positive: normal, original-inode-independent synthetic scratch write.
            scratch = Path(folder) / "ordinary-synthetic.txt"
            scratch.write_text("allowed")
            self.assertEqual(scratch.read_text(), "allowed")

    def make_tree(self):
        scratch = TemporaryDirectory(prefix="pmrh-review-ast-")
        self.addCleanup(scratch.cleanup)
        root = Path(scratch.name)
        def put(name, code):
            p = root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(code)
        put("docs/reference/PMRS-Next_Phase1/source-inventory.json",
            json.dumps({"modules": []}))
        return root, put

    def test_AST_01_function_alias_literal_import_must_be_rejected(self):
        root, put = self.make_tree()
        put("pmrh/domain/reader.py",
            'from importlib import import_module as load\nload("pmrh.adapters")\n')
        put("pmrh/adapters/backend.py", "VALUE = 1\n")
        result = deps.run(root, POLICY)
        self.assertTrue(any(v.get("reason") == "forbidden_new_layer_direction"
                            and v.get("source") == "pmrh/domain/reader.py"
                            for v in result["architecture_violations"]),
                        "Unreported known illegal alias dynamic import")
        # No unintended loading of the actual product Python package.
        self.assertTrue(any(e["target"] == "@namespace/pmrh/adapters"
                            for e in result["direct_imports"]))

    def test_AST_02_unclassified_root_bridge_must_be_rejected(self):
        root, put = self.make_tree()
        put("pmrh/domain/reader.py", "import pmrh.bridge\n")
        put("pmrh/bridge.py", "import pmrh.adapters\n")
        put("pmrh/adapters/backend.py", "VALUE = 1\n")
        result = deps.run(root, POLICY)
        reasons = {v["reason"] for v in result["architecture_violations"]}
        self.assertTrue(reasons.intersection({
            "unclassified_pmrh_module",
            "unclassified_dependency_endpoint",
            "forbidden_transitive_dependency",
        }), "No violation: domain->unclassified bridge->adapters")
        self.assertIn("pmrh/bridge.py",
                      result["direct_graph"]["pmrh/domain/reader.py"])
        self.assertIn("@namespace/pmrh/adapters",
                      result["direct_graph"]["pmrh/bridge.py"])

    def test_positive_legitimate_layer_graph_remains_permitted(self):
        root, put = self.make_tree()
        put("pmrh/__init__.py", "__version__ = 'synthetic'\n")
        put("pmrh/__main__.py", "from .cli import main\n")
        put("pmrh/cli.py", "from . import __version__\n")
        put("pmrh/application/service.py", "from pmrh import ports\n")
        put("pmrh/ports/api.py", "from pmrh.domain import model\n")
        put("pmrh/domain/model.py", "CONTRACT = True\n")
        result = deps.run(root, POLICY)
        self.assertEqual(result["architecture_violations"], [])
        self.assertEqual(result["syntax_errors"], [])


if __name__ == "__main__":
    unittest.main()
