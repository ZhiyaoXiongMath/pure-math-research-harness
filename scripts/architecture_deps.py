#!/usr/bin/env python3
"""Complete local Python AST import graph and PMRH layer boundary gate.

Reads files as text; NEVER imports repository application or test modules.
Legacy placement is an estimated migration target, not a claim that split
modules already satisfy the future architecture.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys
try:
    from scripts import domain_scope, storage_scope, control_scope, fastmath_scope
except ModuleNotFoundError:
    import domain_scope, storage_scope, control_scope, fastmath_scope

IGNORED_DIRS = {".git", ".venv", "venv", "__pycache__", ".tox", "build", "dist"}
LAYERS = {"domain", "ports", "application", "orchestration", "adapters",
          "observability", "interfaces", "legacy", "bootstrap"}
# A dependency is an arrow from the importing module to the imported module.
ALLOWED = {
    "domain": {"domain"},
    "ports": {"ports", "domain"},
    "application": {"application", "ports", "domain"},
    "orchestration": {"orchestration", "ports", "domain"},
    "adapters": {"adapters", "ports", "domain"},
    "observability": {"observability", "ports", "domain"},
    "interfaces": {"interfaces", "application", "ports", "domain"},
    "legacy": {"legacy", "ports", "domain"},
    "bootstrap": set(LAYERS) | {"root_initializer"},
    "root_initializer": {"root_initializer"},
}
# The root initializer contains only inert identity metadata. Real CLI roots
# are explicitly mapped; no unapproved root module acts as a layer bridge.
for _allow in ALLOWED.values():
    _allow.add("root_initializer")
ROOT_MODULE_LAYERS = {
    "__init__.py": "root_initializer",
    "__main__.py": "bootstrap",
    "cli.py": "bootstrap",
}
FORBIDDEN_IMPORTS = {
    "domain": {"os", "pathlib", "io", "tempfile", "shutil", "threading", "multiprocessing", "ctypes", "subprocess", "socket", "sqlite3", "http", "urllib", "requests",
               "openai", "anthropic", "codex", "langgraph", "deepagents",
               "fastapi", "flask", "boto3"},
    "ports": {"subprocess", "socket", "sqlite3", "http", "urllib", "requests",
              "openai", "anthropic", "codex", "langgraph", "deepagents",
              "fastapi", "flask", "boto3"},
}
RISK_IMPORTS = {"subprocess", "socket", "http", "urllib", "requests", "openai",
                "anthropic", "codex", "tempfile", "fcntl", "os", "pathlib"}
OWNER_BY_TARGET = {
    "domain": "DEV-PR-04", "ports": "DEV-PR-02",
    "application": "DEV-PR-06", "orchestration": "DEV-PR-08",
    "adapters": "DEV-PR-07", "observability": "DEV-PR-09",
    "interfaces": "DEV-PR-09", "legacy": "DEV-PR-10",
    "retire": "DEV-PR-14", "bootstrap": "DEV-PR-18",
}


def source_files(root: Path) -> list[Path]:
    return sorted((p for p in root.rglob("*.py")
                   if not any(part in IGNORED_DIRS for part in p.relative_to(root).parts)),
                  key=lambda p: p.relative_to(root).as_posix())


def name_of(relative: Path) -> str | None:
    parts = list(relative.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    if not parts or not all(x.isidentifier() for x in parts):
        return None
    return ".".join(parts)


def catalog(root: Path, paths: list[Path]) -> dict[str, str]:
    """Index real modules AND implicit namespace-package directories.

    A directory with Python descendants may be imported as a package even if
    it lacks __init__.py. Virtual entries identify namespaces explicitly; they
    do not pretend that a non-existent Python source file was parsed.
    """
    result = {}
    namespace_dirs = set()
    for path in paths:
        relative = path.relative_to(root)
        name = name_of(relative)
        if name is not None:
            result[name] = relative.as_posix()
        parent = relative.parent
        while parent != Path("."):
            if all(segment.isidentifier() for segment in parent.parts):
                namespace_dirs.add(parent)
            parent = parent.parent
    for directory in sorted(namespace_dirs):
        name = ".".join(directory.parts)
        result.setdefault(name, "@namespace/" + directory.as_posix())
    return result


def relative_base(source_name: str | None, is_package: bool,
                  module: str | None, level: int) -> str | None:
    if not level:
        return module or ""
    if source_name is None:
        return None
    pkg = source_name.split(".") if is_package else source_name.split(".")[:-1]
    if level > len(pkg):
        return None
    base = pkg[:len(pkg) - level + 1]
    if module:
        base.extend(module.split("."))
    return ".".join(base)



def dynamic_import_bindings(parsed: ast.AST):
    """Conservatively detect importlib imports, including aliases.

    Any alias rebound in the same file is classified unresolved rather than
    being trusted as a definite importlib call. This does not execute Python.
    """
    modules, functions, builtins_modules, foreign, writes = set(), set(), set(), set(), set()
    for node in ast.walk(parsed):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".", 1)[0]
                if alias.name == "importlib" or (alias.name.startswith("importlib.") and not alias.asname):
                    modules.add(bound)
                elif alias.name == "builtins" or (alias.name.startswith("builtins.") and not alias.asname):
                    builtins_modules.add(bound)
                else:
                    foreign.add(bound)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                bound = alias.asname or alias.name
                if node.level == 0 and node.module == "importlib" and alias.name == "import_module":
                    functions.add(bound)
                elif node.level == 0 and node.module == "builtins" and alias.name == "__import__":
                    functions.add(bound)
                else:
                    foreign.add(bound)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            writes.add(node.id)
        elif isinstance(node, ast.arg):
            writes.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            writes.add(node.name)
    return modules, functions, builtins_modules, ((modules | functions | builtins_modules) & (writes | foreign))


def graph_from(root: Path):
    paths = source_files(root)
    modules = catalog(root, paths)
    edges, external, nonliteral, syntax_errors = [], [], [], []
    digests = {}
    for path in paths:
        rel = path.relative_to(root).as_posix()
        raw = path.read_bytes()
        digests[rel] = hashlib.sha256(raw).hexdigest()
        try:
            parsed = ast.parse(raw, filename=rel)
        except (SyntaxError, UnicodeError, ValueError) as exc:
            syntax_errors.append({"path": rel, "error": str(exc)})
            continue
        mod = name_of(path.relative_to(root))
        is_package = path.name == "__init__.py"
        module_aliases, function_aliases, builtins_aliases, shadowed = dynamic_import_bindings(parsed)
        for node in ast.walk(parsed):
            requests = []
            if isinstance(node, ast.Import):
                for alias in node.names:
                    requests.append((alias.name, "import", node.lineno))
            elif isinstance(node, ast.ImportFrom):
                base = relative_base(mod, is_package, node.module, node.level)
                if base is None:
                    nonliteral.append({"source": rel, "line": node.lineno,
                                       "kind": "invalid_relative_import"})
                    continue
                requests.append((base, "from", node.lineno))
                for alias in node.names:
                    if alias.name == "*":
                        nonliteral.append({"source": rel, "line": node.lineno,
                                           "kind": "star_import", "module": base})
                    else:
                        requests.append(((base + "." if base else "") + alias.name,
                                         "from_member", node.lineno))
            elif isinstance(node, ast.Call):
                f = node.func
                binding = None
                if isinstance(f, ast.Name) and (f.id == "__import__" or f.id in function_aliases):
                    binding = f.id
                elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                    if f.attr == "import_module" and f.value.id in module_aliases:
                        binding = f.value.id
                    elif f.attr == "__import__" and f.value.id in builtins_aliases:
                        binding = f.value.id
                if binding is not None:
                    if binding in shadowed:
                        nonliteral.append({"source": rel, "line": node.lineno,
                                           "kind": "dynamic_binding_shadowed",
                                           "binding": binding})
                        continue
                    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                        name = node.args[0].value
                        if name.startswith("."):
                            args = node.args
                            pkgarg = args[1] if len(args) > 1 else next(
                                (kw.value for kw in node.keywords if kw.arg == "package"), None)
                            if isinstance(pkgarg, ast.Constant) and isinstance(pkgarg.value, str):
                                depth = len(name) - len(name.lstrip("."))
                                name = relative_base(pkgarg.value, True, name.lstrip("."), depth)
                            else:
                                nonliteral.append({"source": rel, "line": node.lineno,
                                                   "kind": "dynamic_relative_package"})
                                continue
                        if name:
                            requests.append((name, "dynamic_literal", node.lineno))
                        else:
                            nonliteral.append({"source": rel, "line": node.lineno,
                                               "kind": "dynamic_empty_name"})
                    else:
                        nonliteral.append({"source": rel, "line": node.lineno,
                                           "kind": "dynamic_nonliteral"})
            for target_name, kind, lineno in requests:
                if not target_name:
                    continue
                target = modules.get(target_name)
                if target is not None:
                    if target != rel:
                        edges.append({"source": rel, "target": target, "import": target_name,
                                      "kind": kind, "line": lineno})
                else:
                    # For multi-part imports of an external module, classify
                    # the import by its first segment, never execute it.
                    external.append({"source": rel, "import": target_name,
                                     "kind": kind, "line": lineno})
    edges.sort(key=lambda x: (x["source"], x["target"], x["line"], x["kind"]))
    return paths, edges, external, nonliteral, syntax_errors, digests, modules


def components(nodes: list[str], adjacency: dict[str, set[str]]) -> list[list[str]]:
    """Tarjan strongly connected components, including isolated vertices."""
    counter = 0
    indices, low, stack, on_stack, result = {}, {}, [], set(), []

    def visit(v):
        nonlocal counter
        indices[v] = low[v] = counter
        counter += 1
        stack.append(v)
        on_stack.add(v)
        for w in sorted(adjacency[v]):
            if w not in indices:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on_stack:
                low[v] = min(low[v], indices[w])
        if low[v] == indices[v]:
            comp = []
            while True:
                w = stack.pop()
                on_stack.remove(w)
                comp.append(w)
                if w == v:
                    break
            result.append(sorted(comp))

    for node in sorted(nodes):
        if node not in indices:
            visit(node)
    return sorted(result, key=lambda x: (-len(x), x))


def closure(nodes: list[str], adjacency: dict[str, set[str]]) -> dict[str, list[str]]:
    result = {}
    for node in sorted(nodes):
        seen, todo = set(), list(adjacency[node])
        while todo:
            dep = todo.pop()
            if dep not in seen:
                seen.add(dep)
                todo.extend(adjacency[dep] - seen)
        seen.discard(node)
        result[node] = sorted(seen)
    return result


def layer(path: str) -> str | None:
    if path.startswith("@namespace/"):
        path = path[len("@namespace/"):] + "/__namespace__.py"
    parts = Path(path).parts
    if parts and parts[0] == "pmrh":
        if len(parts) == 2:
            return ROOT_MODULE_LAYERS.get(parts[1], "unclassified")
        if len(parts) >= 3:
            return parts[1] if parts[1] in LAYERS else "unclassified"
    return None


def manifest_sources(root: Path, changed_paths=()):
    filename = root / "docs/reference/PMRS-Next_Phase1/source-inventory.json"
    if not filename.exists():
        return {}, ["source-inventory.json missing"]
    data = json.loads(filename.read_text(encoding="utf-8"))
    mapping = {m["path"]: m for m in data["modules"]}
    discrepancies = []
    for name, item in mapping.items():
        file = root / name
        if not file.is_file():
            discrepancies.append("missing:" + name)
        elif file.stat().st_size != item["bytes"] and name not in changed_paths:
            discrepancies.append("size_mismatch:" + name)
    unexpected = sorted(set(p.relative_to(root).as_posix()
                            for p in (root / "research_studio").rglob("*.py"))
                        - set(mapping) - set(changed_paths))
    discrepancies.extend("unregistered:" + name for name in unexpected)
    return mapping, discrepancies


def migrated_layer(target: str) -> str:
    # Multi-duty legacy source files cannot be classified decisively by
    # file-level AST. This is a suggested first destination only.
    matches = re.findall(r"\b(domain|ports|application|orchestration|adapters|observability|interfaces|legacy|retire|bootstrap)\b",
                         target)
    return matches[0] if matches else "unassigned"


def review_entrypoints(root: Path, external: list[dict]) -> dict:
    flagged = defaultdict(set)
    for edge in external:
        src = edge["source"]
        if src.startswith("tests/") or src.startswith("scripts/"):
            if edge["import"].split(".", 1)[0] in RISK_IMPORTS:
                flagged[src].add(edge["import"].split(".", 1)[0])
    return {"test_modules": len(list((root / "tests").rglob("*.py"))),
            "script_modules": len(list((root / "scripts").rglob("*.py"))),
            "external_capability_imports": [{"path": p, "imports": sorted(vals)}
                                            for p, vals in sorted(flagged.items())],
            "historical_runner": {
                "path": "scripts/test-runner.py",
                "status": "UNSAFE_FOR_DEFAULT_OFFLINE_EXECUTION",
                "reason": "Creates output and logs; launches child unittest discovery over legacy tests; "
                          "inherits host environment, may invoke CLI, local HTTP and rendering. "
                          "Its paid_model_calls=0 receipt is not a preventive security control.",
            }}


def run(root: Path, policy: dict) -> dict:
    paths, edges, external, dynamic, failures, digests, modules = graph_from(root)
    source_nodes = [p.relative_to(root).as_posix() for p in paths]
    namespace_nodes = sorted({value for value in modules.values()
                              if value.startswith("@namespace/")})
    nodes = sorted(set(source_nodes) | set(namespace_nodes))
    adjacency = {node: set() for node in nodes}
    for edge in edges:
        adjacency[edge["source"]].add(edge["target"])
    transitive = closure(nodes, adjacency)
    scc = components(nodes, adjacency)
    bridge = policy.get('devpr03_read_bridge', {})
    approved_paths = {
        'research_studio/store.py', 'research_studio/host_pool.py', 'research_studio/views.py',
        'research_studio/workspace.py', 'research_studio/main_session.py', 'research_studio/readonly_query.py'}
    paths_valid = bool(bridge) and set(bridge.get('changed_paths', ())) == approved_paths
    extraction = policy.get('devpr04_domain_bridge', {})
    extraction_valid = (set(extraction.get('changed_paths', ())) == set(domain_scope.SYMBOLS)
                        and extraction.get('symbols') == domain_scope.SYMBOLS)
    permitted = (approved_paths if paths_valid else set()) | (set(domain_scope.SYMBOLS) if extraction_valid else set())
    storage = policy.get('devpr05_storage_bridge', {})
    storage_valid = (set(storage.get('changed_paths', ())) == storage_scope.PATHS
                     and storage.get('symbols') == storage_scope.SYMBOLS
                     and storage.get('baseline') == storage_scope.BASE)
    if storage_valid:
        permitted |= storage_scope.PATHS
    control = policy.get('devpr06_control_bridge', {})
    control_valid = (control.get('baseline') == control_scope.BASE and
                     control.get('symbols') == control_scope.SYMBOLS and
                     set(control.get('changed_paths', ())) == control_scope.PATHS)
    if control_valid:
        permitted |= control_scope.PATHS
    fast = policy.get('devpr11_fastmath_bridge', {})
    fast_valid = (fast.get('baseline') == fastmath_scope.PARENT and
        set(fast.get('changed_paths', ())) == set(fastmath_scope.SYMBOLS) | fastmath_scope.WHOLE and
        {(r.get('source'),r.get('target')) for r in fast.get('direct_edges', ())} == fastmath_scope.EDGES)
    if fast_valid:
        permitted |= set(fastmath_scope.SYMBOLS) | fastmath_scope.WHOLE
    inventory, discrepancies = manifest_sources(root, permitted)
    violations, legacy_blocks = [], []
    bridge_edges = {(row['source'], row['target']) for row in bridge.get('direct_edges', ())
                    if all(row.get(k) for k in ('consumer', 'reason', 'owner', 'remove_by'))}
    approved_bridge_edges = {
        ('pmrh/cli.py', 'research_studio/readonly_query.py'),
        ('research_studio/readonly_query.py', 'pmrh/ports/dto/core.py'),
        ('research_studio/readonly_query.py', 'pmrh/ports/dto/enums.py'),
        ('research_studio/readonly_query.py', 'pmrh/ports/dto/__init__.py')}
    if bridge and not paths_valid:
        violations.append({'reason': 'invalid_devpr03_path_allowlist'})
    if bridge and (bridge_edges != approved_bridge_edges or
                   set(bridge.get('legacy_reachability', {})) != {'pmrh/cli.py', 'pmrh/__main__.py'}):
        violations.append({'reason': 'invalid_devpr03_bridge_allowlist'})
    extraction_edges = {(row['source'], row['target']) for row in extraction.get('direct_edges', ())
                        if all(row.get(k) for k in ('consumer', 'reason', 'owner', 'remove_by'))
                        and row.get('owner') == 'DEV-PR-04'}
    if extraction and (not extraction_valid or extraction_edges != domain_scope.EDGES):
        violations.append({'reason': 'invalid_devpr04_extraction_allowlist'})
    if extraction_valid and extraction_edges == domain_scope.EDGES:
        bridge_edges |= extraction_edges
    storage_edges = {(r['source'], r['target']) for r in storage.get('direct_edges', ())
                     if all(r.get(k) for k in ('consumer', 'reason', 'owner', 'remove_by'))
                     and r.get('owner') == 'DEV-PR-05'}
    if storage and (not storage_valid or storage_edges != storage_scope.EDGES
                    or storage.get('query_import_targets') != storage_scope.QUERY_TARGETS
                    or storage.get('legacy_reachability') != storage_scope.QUERY_LEGACY_REACH):
        violations.append({'reason': 'invalid_devpr05_storage_allowlist'})
    if storage_valid and storage_edges == storage_scope.EDGES:
        bridge_edges |= storage_edges
    control_edges = {(r['source'], r['target']) for r in control.get('direct_edges', ())
                     if all(r.get(k) for k in ('consumer', 'reason', 'owner', 'remove_by'))
                     and r.get('owner') == 'DEV-PR-06'}
    if control and (not control_valid or control_edges != control_scope.EDGES):
        violations.append({'reason': 'invalid_devpr06_control_allowlist'})
    if control_valid and control_edges == control_scope.EDGES:
        bridge_edges |= control_edges
    if fast_valid:
        try:
            fastmath_scope.verify(root)
        except (ValueError,OSError) as exc:
            violations.append({'reason':'invalid_devpr11_stage','detail':str(exc)})
        bridge_edges |= fastmath_scope.EDGES
    else:
        violations.append({'reason':'invalid_devpr11_exact_scope'})
    violation_keys = set()
    for filename in source_nodes:
        if layer(filename) == "unclassified":
            violations.append({"source": filename, "reason": "unclassified_pmrh_module",
                               "requires": "explicit approved layer or root-module mapping"})
    for edge in edges:
        source, target = edge["source"], edge["target"]
        a, b = layer(source), layer(target)
        if a == "unclassified" or b == "unclassified":
            violations.append({**edge, "reason": "unclassified_dependency_endpoint",
                               "source_layer": a, "target_layer": b})
        elif a and b and b not in ALLOWED[a]:
            # from pmrh.adapters import codex records both the package and
            # member. One source-line/target-layer violation is sufficient;
            # the complete direct graph still retains both edges.
            key = (source, edge["line"], a, b, "forbidden_new_layer_direction")
            if key not in violation_keys:
                violation_keys.add(key)
                violations.append({**edge, "reason": "forbidden_new_layer_direction",
                                   "source_layer": a, "target_layer": b})
        if source.startswith("pmrh/") and target.startswith("research_studio/") and (source, target) not in bridge_edges:
            violations.append({**edge, "reason": "new_package_may_not_depend_on_legacy"})
        if source.startswith("research_studio/") and target.startswith("pmrh/") and (source, target) not in bridge_edges:
            violations.append({**edge, "reason": "legacy_may_not_depend_on_new_package"})
        if source in inventory and target in inventory and not target.endswith("/__init__.py"):
            a = migrated_layer(inventory[source]["target"])
            b = migrated_layer(inventory[target]["target"])
            if a != b:
                owner = policy.get("legacy_owner_overrides", {}).get(source, policy["legacy_owners"].get(a, "DEV-PR-18"))
                legacy_blocks.append({**edge, "suggested_source_layer": a,
                                      "suggested_target_layer": b,
                                      "exception_id": policy["legacy_exception_id"],
                                      "owner": owner, "remove_by": owner,
                                      "classification": "PROVISIONAL_MIGRATION_BLOCKER"})
    # Do not allow a classified layer to reach a forbidden implementation
    # indirectly through an otherwise plausible module/bridge.
    direct_pairs = {(e["source"], e["target"]) for e in edges}
    # DEV03 does not suppress transitive checks. Every reachable legacy target
    # for the two CLI consumers is an exact frozen name with removal ownership.
    allowed_reach = storage_scope.QUERY_LEGACY_REACH if storage_valid else bridge.get('legacy_reachability', {})
    for source in source_nodes:
        if source.startswith('pmrh/'):
            for target in transitive[source]:
                if target.startswith('research_studio/') and target not in allowed_reach.get(source, ()):
                    violations.append({'source': source, 'target': target,
                                       'reason': 'unapproved_transitive_legacy_dependency'})
    if bridge:
        actual_query_edges = {e['target'] for e in edges if e['source'] == 'research_studio/readonly_query.py'}
        if actual_query_edges != set(storage_scope.QUERY_TARGETS if storage_valid else bridge.get('query_import_targets', ())):
            violations.append({'reason': 'query_compatibility_imports_changed'})
        if not bridge_edges <= direct_pairs:
            violations.append({'reason': 'missing_named_query_bridge_edge'})
    query_roots = ('pmrh/cli.py', 'pmrh/__main__.py', 'research_studio/readonly_query.py')
    forbidden_query = {'research_studio/native_main.py', 'research_studio/runner.py',
                       'research_studio/codex_client.py', 'research_studio/harness_runtime.py',
                       'research_studio/storage_compat.py', 'research_studio/report_catalog.py',
                       'research_studio/host_pool.py', 'research_studio/main_session.py',
                       'research_studio/scheduler.py', 'research_studio/engine.py'}
    for source in query_roots:
        for target in set(transitive.get(source, ())) & forbidden_query:
            violations.append({'source': source, 'target': target, 'reason': 'query_reaches_runtime'})
    for source in source_nodes:
        a = layer(source)
        if a not in ALLOWED:
            continue
        for target in transitive[source]:
            b = layer(target)
            if b is not None and b != "unclassified" and b not in ALLOWED[a] and (source, target) not in direct_pairs:
                violations.append({"source": source, "target": target,
                                   "reason": "forbidden_transitive_dependency",
                                   "source_layer": a, "target_layer": b})
    # Unresolved new package imports need review; never report clean merely
    # because a static target cannot be identified.
    for item in dynamic:
        if item["source"].startswith("pmrh/") or item['source'] == 'research_studio/readonly_query.py':
            violations.append({**item, "reason": "unresolved_dynamic_import",
                               "review_required": True})
    for path in paths:
        if layer(path.relative_to(root).as_posix()) != 'domain':
            continue
        try:
            tree = ast.parse(path.read_text(encoding='utf-8'))
        except (SyntaxError, UnicodeError):
            # graph_from already records malformed source as a failed check.
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {'open', 'exec', 'eval', 'compile', '__import__'}:
                violations.append({'source': path.relative_to(root).as_posix(), 'line': node.lineno,
                                   'reason': 'domain_io_or_dynamic_execution'})
    for edge in external:
        source, imported = edge["source"], edge["import"].split(".", 1)[0]
        a = layer(source)
        if source == 'research_studio/readonly_query.py' and imported not in {
                'contextlib', 'datetime', 'errno', 'os', 'pathlib', 'stat'} and edge['import'] not in {
                'pmrh.ports.dto.core.StateAxes', 'pmrh.ports.dto.core.port_error',
                'research_studio.util.PMRSError', 'research_studio.util.canonical',
                'research_studio.store.Store', 'pmrh.adapters.storage.io._Unavailable',
                'pmrh.adapters.storage.io._reason', 'pmrh.adapters.storage.io._observed_at',
                'pmrh.adapters.storage.io._ConfinedReader', 'pmrh.adapters.storage.journal.Journal'}:
            violations.append({**edge, 'reason': 'unapproved_query_capability_import'})
        if a in FORBIDDEN_IMPORTS and imported in FORBIDDEN_IMPORTS[a]:
            violations.append({**edge, "reason": "prohibited_capability_import",
                               "source_layer": a})
    named_couplings = []
    for named in policy.get("named_blockers", []):
        matches = [edge for edge in edges if edge["source"] == named["source"]
                   and edge["target"] == named["target"]]
        cross = sum(item["source"] == named["source"] and item["target"] == named["target"]
                    for item in legacy_blocks)
        named_couplings.append({**named,
                                "status": "MATCHED_DIRECT_EDGE" if matches else "MISSING_DIRECT_EDGE",
                                "direct_occurrences": len(matches),
                                "cross_layer_occurrences": cross,
                                "classification": ("CROSS_LAYER_AND_NAMED" if cross
                                                   else "NAMED_COUPLING_OUTSIDE_PROVISIONAL_CROSS_LAYER")})
        relocated = (storage_valid and named['source'] == 'research_studio/store.py'
                     and named['target'] == 'research_studio/native_main.py'
                     and ('research_studio/storage_compat.py', named['target']) in direct_pairs)
        if relocated and not matches:
            named_couplings[-1].update(status='RELOCATED_TO_TRUSTED_WRITER_ASSEMBLY',
                                      current_source='research_studio/storage_compat.py', owner='DEV-PR-05')
        if not matches and not relocated:
            violations.append({"reason": "missing_named_legacy_coupling",
                               "source": named["source"], "target": named["target"]})
    if policy.get("legacy_baseline_commit") != "e4de0210f9985224e030ac4cfd2f7e2904005b37":
        violations.append({"reason": "legacy_baseline_mismatch"})
    if any(key not in policy.get("legacy_owners", {}) for key in set(
           migrated_layer(m["target"]) for m in inventory.values())):
        violations.append({"reason": "missing_legacy_ownership_mapping"})
    if discrepancies:
        violations.append({"reason": "legacy_inventory_mismatch", "details": discrepancies})
    report = {
        "schema": "pmrh.ast-import-baseline/1",
        "source_root": ".",
        "source_manifest_sha256": hashlib.sha256(json.dumps(digests, sort_keys=True).encode()).hexdigest(),
        "source_sha256": digests,
        "counts": {"python_files": len(paths), "namespace_package_nodes": len(namespace_nodes),
                   "local_import_occurrences": len(edges),
                   "direct_unique_edges": sum(map(len, adjacency.values())),
                   "transitive_unique_edges": sum(map(len, transitive.values())),
                   "cyclic_components": sum(len(c) > 1 for c in scc),
                   "legacy_migration_blockers": len(legacy_blocks),
                   "named_legacy_couplings": len(named_couplings),
                   "unresolved_new_layer_imports": sum(x["source"].startswith("pmrh/") for x in dynamic),
                   "architecture_violations": len(violations),
                   "parse_failures": len(failures),
                   "nonliteral_imports": len(dynamic)},
        "direct_imports": edges,
        "namespace_packages": {name: target for name, target in sorted(modules.items())
                               if target.startswith("@namespace/")},
        "direct_graph": {k: sorted(v) for k, v in adjacency.items()},
        "transitive_graph": transitive,
        "strongly_connected_components": scc,
        "external_imports": external,
        "dynamic_unresolved": dynamic,
        "syntax_errors": failures,
        "architecture_violations": violations,
        "legacy_migration_blockers": legacy_blocks,
        "named_architectural_couplings": named_couplings,
        "legacy_policy": policy,
        "legacy_inventory_discrepancies": discrepancies,
        "authorized_legacy_read_paths": sorted(approved_paths) if paths_valid else [],
        "test_entrypoint_review": review_entrypoints(root, external),
    }
    return report


def markdown(report: dict) -> str:
    c = report["counts"]
    lines = ["# DEV-PR-01 — AST dependency and offline risk baseline", "",
             "Static file parsing only. No product import, model, research session, or network.",
             "Legacy target placement is provisional because many files combine duties.", "",
             "## Counts", "",
             "| Measure | Observed |", "|---|---:|"]
    lines.extend(f"| {name} | {value} |" for name, value in c.items())
    lines.extend(["", "## Largest cycles (SCC)", ""])
    for comp in (x for x in report["strongly_connected_components"] if len(x) > 1):
        lines.append("- " + " → ".join(comp))
        if len(lines) > 36:
            break
    lines.extend(["", "## New-layer violations", ""])
    for v in report["architecture_violations"][:40]:
        lines.append("- " + json.dumps(v, ensure_ascii=False, sort_keys=True))
    if not report["architecture_violations"]:
        lines.append("None in this source revision.")
    lines.extend(["", "## Provisional legacy cross-layer edges", "",
                  "Each entry is retained in the JSON artifact with owner/removal PR, "
                  "as a frozen legacy exception. This does not validate the design."])
    for v in report["legacy_migration_blockers"][:50]:
        lines.append("- " + v["source"] + " → " + v["target"] + " ("
                     + v["suggested_source_layer"] + " → " + v["suggested_target_layer"]
                     + "; owner " + v["owner"] + ")")
    lines.extend(["", "## Named architectural couplings", "",
                  "Named same-layer couplings are tracked separately; provisional cross-layer edges are not exhaustive."])
    for named in report["named_architectural_couplings"]:
        lines.append("- " + named["source"] + " → " + named["target"] +
                     ": " + named["status"] + "; direct=" + str(named["direct_occurrences"])
                     + "; cross-layer=" + str(named["cross_layer_occurrences"])
                     + "; owner=" + named["owner"])
    lines.extend(["", "## Unresolved dynamic imports", ""])
    for issue in report["dynamic_unresolved"][:40]:
        lines.append("- " + json.dumps(issue, sort_keys=True))
    if not report["dynamic_unresolved"]:
        lines.append("None detected within supported static patterns; not proof of complete runtime import closure.")
    lines.extend(["", "## Legacy test entrypoint risk", "",
                  report["test_entrypoint_review"]["historical_runner"]["reason"],
                  "", "## Limitations", "",
                  "- AST detects literal imports, not all runtime dynamic imports, plugin hooks, native code or side effects.",
                  "- Transitive graph is static reachability, not runtime load-order proof.",
                  "- Legacy exemptions retain the original baseline; exact DEV03 read-section exceptions are separately checked by CI.",
                  "- This report certifies neither OS isolation nor execution safety of historical tests.",
                  ""])
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument("--policy", type=Path, default=Path("config/architecture-exceptions.json"))
    p.add_argument("--json", type=Path, required=True)
    p.add_argument("--markdown", type=Path, required=True)
    p.add_argument("--check", action="store_true", help="fail on syntax, boundary and legacy mismatches")
    args = p.parse_args(argv)
    root = args.root.resolve()
    policy_file = args.policy if args.policy.is_absolute() else root / args.policy
    policy = json.loads(policy_file.read_text(encoding="utf-8"))
    report = run(root, policy)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown.write_text(markdown(report), encoding="utf-8")
    summary = {"counts": report["counts"],
               "baseline_sha256": report["source_manifest_sha256"],
               "violations": report["architecture_violations"][:10],
               "largest_scc": [c for c in report["strongly_connected_components"] if len(c) > 1][:4]}
    print("PMRH_AST_SUMMARY=" + json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    bad = report["syntax_errors"] or (args.check and report["architecture_violations"])
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
