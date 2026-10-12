"""Phase 0 offline checks only: no legacy research runtime or paid model calls."""

import ast
import hashlib
import importlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import tomllib
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "docs" / "reference" / "PMRS-Next_Phase1"
BASELINE_COMMIT = "e4de0210f9985224e030ac4cfd2f7e2904005b37"
BASELINE_TREE = "c17a592ff0a4906afa7a6423535f41c67c926128"


class Phase0StaticChecks(unittest.TestCase):
    def test_distribution_and_console_scripts(self):
        config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(config["project"]["name"], "pure-math-research-harness")
        self.assertEqual(config["project"]["version"], "0.0.0")
        self.assertEqual(config["project"]["scripts"]["pmrh"], "pmrh.cli:main")
        self.assertEqual(config["tool"]["setuptools"]["packages"]["find"]["include"],
                         ["pmrh*", "research_studio*"])
        self.assertIn("research-studio", config["project"]["scripts"])
        self.assertIn("pmrs-desktop", config["project"]["scripts"])
        self.assertTrue((ROOT / "research_studio").is_dir())

    def test_new_cli_statically_does_not_import_runtime(self):
        for name in ("__init__.py", "cli.py", "__main__.py"):
            parsed = ast.parse((ROOT / "pmrh" / name).read_text(encoding="utf-8"))
            for node in ast.walk(parsed):
                if isinstance(node, ast.Import):
                    names = [entry.name for entry in node.names]
                    self.assertTrue(all(x in ("argparse", "sys") for x in names), names)
                elif isinstance(node, ast.ImportFrom):
                    self.assertTrue(node.level > 0 and node.module in ("cli", None),
                                    f"Unexpected import in {name}: {ast.dump(node)}")
                elif isinstance(node, (ast.Call,)) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, {"eval", "exec", "__import__"})

    def test_original_archive_sha256_unchanged(self):
        checksum = (ARCHIVE / "SHA256SUMS.txt").read_text(encoding="utf-8")
        paths = []
        for line in checksum.splitlines():
            expected, name = line.split("  ", 1)
            self.assertEqual(len(expected), 64)
            self.assertEqual(Path(name).name, name)
            actual = hashlib.sha256((ARCHIVE / name).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, name)
            paths.append(name)
        self.assertEqual(len(paths), 7)
        self.assertEqual(len(list(ARCHIVE.iterdir())), 8)
        manifest = json.loads((ARCHIVE / "audit-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["baseline_commit"], BASELINE_COMMIT)
        self.assertEqual(manifest["baseline_tree"], BASELINE_TREE)
        self.assertEqual(manifest["planned_pull_requests"], 18)
        self.assertEqual(manifest["new_software_acceptance_entries"], 58)
        self.assertEqual(manifest["inherited_guide_acceptance_entries"], 46)

    def test_acceptance_ids_and_no_false_pass(self):
        plan = (ARCHIVE / "02-Implementation-Plan.zh-CN.md").read_text(encoding="utf-8")
        import re
        section = plan.split("### 15.2 最低软件验收矩阵", 1)[1].split("### 15.3", 1)[0]
        new_ids = re.findall(r"^\| ([A-Z]\d{2}) \|", section, re.MULTILINE)
        inherited = plan.split("### 15.3 既有指南 46 项验收的继承映射", 1)[1].split("### 15.4", 1)[0]
        inherited_ids = re.findall(r"^\| (GUIDE:[KCP]\d{2}) \|", inherited, re.MULTILINE)
        self.assertEqual(len(new_ids), len(set(new_ids)))
        self.assertEqual(len(inherited_ids), len(set(inherited_ids)))
        self.assertEqual(len(new_ids), 58)
        self.assertEqual(len(inherited_ids), 46)
        plan_dev = (ROOT / "docs" / "development" / "ROADMAP.md").read_text(encoding="utf-8")
        for number in range(1, 19):
            self.assertIn(f"DEV-PR-{number:02d}", plan_dev)

    def test_new_package_import_does_not_start_runtime(self):
        with mock.patch.object(socket, "socket", side_effect=AssertionError("no socket")), \
             mock.patch.object(subprocess, "Popen", side_effect=AssertionError("no process")), \
             mock.patch.object(threading.Thread, "start", side_effect=AssertionError("no thread")):
            package = importlib.import_module("pmrh")
            cli = importlib.import_module("pmrh.cli")
            self.assertEqual(package.__version__, "0.0.0")
            self.assertTrue(callable(cli.main))
            self.assertFalse(any(s == "research_studio" or s.startswith("research_studio.")
                                 for s in sys.modules), "legacy runtime unexpectedly imported")

    def test_cli_smoke_in_isolated_home(self):
        with tempfile.TemporaryDirectory(prefix="pmrh-phase0-") as scratch:
            parent = Path(scratch)
            env = os.environ.copy()
            for key, sub in (("HOME", "home"), ("XDG_CONFIG_HOME", "config"),
                             ("XDG_DATA_HOME", "data"), ("XDG_CACHE_HOME", "cache"),
                             ("TMPDIR", "tmp")):
                path = parent / sub
                path.mkdir()
                env[key] = str(path)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            env["PYTHONNOUSERSITE"] = "1"
            env["PIP_NO_INDEX"] = "1"
            tracked = [parent / s for s in ("home", "config", "data", "cache", "tmp")]
            def footprint():
                return tuple(sorted(str(p.relative_to(parent)) for folder in tracked
                                    for p in folder.rglob("*")))
            before = footprint()
            for args, expected_code, expected_text in (
                (["--help"], 0, "Phase 0 bootstrap only"),
                (["--version"], 0, "pmrh 0.0.0"),
                (["status"], 2, "unsupported/not implemented"),
            ):
                result = subprocess.run([sys.executable, "-B", "-m", "pmrh", *args],
                                        cwd=ROOT, env=env, capture_output=True,
                                        text=True, check=False, timeout=10)
                self.assertEqual(result.returncode, expected_code,
                                 (args, result.stdout, result.stderr))
                self.assertIn(expected_text, result.stdout + result.stderr)
            self.assertEqual(before, footprint(), "CLI wrote to isolated HOME/XDG/TMP")


if __name__ == "__main__":
    unittest.main()
