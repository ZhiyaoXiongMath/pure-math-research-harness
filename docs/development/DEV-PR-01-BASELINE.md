# DEV-PR-01 — Static dependency baseline and synthetic offline tests

Status: IMPLEMENTED; TESTED only for the precise linked CI receipts. Independent PMRH Development — MAIN acceptance remains pending. This is software testing, not research authorization.

## Fixed development baseline

- Target: ZhiyaoXiongMath/pure-math-research-harness.
- Phase 0 PR #1 merged 2026-10-12T08:20:01Z.
- DEV-PR-01 base main: 977e866d64bba5cf7b5549f17a3d4b5599a4c20a.
- Original 4.2.2 legacy source commit: e4de0210f9985224e030ac4cfd2f7e2904005b37, unchanged in research_studio/ as checked by Git diff.
- Developer branch: chore/dev-pr-01-static-offline-baseline. Final head is always the actual PR metadata SHA, not a temporary PR test-merge SHA.

## A. Full source AST dependency graph

Run: python3 -B scripts/architecture_deps.py --check --json /tmp/dependencies.json --markdown /tmp/dependencies.md

The script enumerates all checkout Python source files except generated environments, parses each file with ast.parse, and **never imports product or test modules**. Its JSON records per-file SHA-256, import occurrences, deduplicated direct dependency graph, transitive closure, strongly connected components (Tarjan), external imports, literal dynamic imports, unresolved dynamic imports, syntax errors, provisional legacy migration blockers, architecture violations, and static test-entrypoint review.

An actual full checkout CI scan at source head bf2b26509994416d6df515a5acadb6b6c2a71b19, [Actions 38225117032](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38225117032), found 141 Python files, 1,473 import occurrences between local modules, 980 deduplicated direct arrows, 6,153 transitive reachability arrows, one nontrivial cyclic strongly connected component, and 442 provisional cross-layer legacy import occurrences; zero AST parse failures and zero new-layer prohibited imports. Counts may change after source edits; use the latest attached CI artifact as the authoritative report.

The large SCC covers multiple research_studio modules including store, execution, scheduler, runner, native_main, strategy and changes. The destination mapping from the fixed source inventory is a migration hypothesis, particularly when one legacy file contains multiple responsibilities. It is not a claim that all candidate cross-layer arrows are currently forbidden by a new implemented layout.

## B. Enforced import directions and explicit legacy exception debt

- New pmrh/domain is self-contained. Ports can import ports/domain; application can import application/ports/domain.
- Orchestration and adapters implement ports, but cannot directly import each other or application. Bootstrap is the composition root.
- Domain and ports cannot statically import subprocess, sockets, HTTP clients, concrete SQLite storage, provider SDKs, Codex and agent frameworks.
- New pmrh may not import research_studio; legacy may not import pmrh. Both are forbidden by default.
- config/architecture-exceptions.json registers the only existing legacy island, its immutable commit/tree, named legacy blockers and per-module/target removal owners. CI rejects source changes to the original research_studio tree against the fixed base.
- Every provisional legacy cross-layer edge is emitted in the JSON report with exact source/target/line, planned destination layers and responsible DEV-PR. It is not silently ignored or treated as an approved final design. Revising the frozen exception requires its own reviewed change.
- The synthetic negative cases deliberately violate layer direction and source inventory sizes to verify rejection.

## C. Strictly allowlisted synthetic offline test process

Run: python3 -B scripts/offline_test.py --suite devpr01 --out /tmp/pmrh-offline-receipts

Only the synthetic tests/devpr01 suite is allowed. The historical scripts/test-runner.py, arbitrary test modules, native test names and research commands cannot be selected. A fresh child Python interpreter receives temporary HOME/XDG/TMP, a scrubbed environment (no inherited model/API credentials or proxy settings), disabled Python bytecode/user site/pip index, and a sitecustomize guard. Common socket/process, source-write, HOME/private read/write and outside-fixture filesystem attempts are rejected. Tests intentionally attempt forbidden operations; they also verify allowed synthetic scratch writes.

**This is Python-level defense in depth, not a kernel or OS sandbox.** It does not reliably confine hostile native code, inherited descriptors, every path API, another external process, or direct OS syscalls. Untrusted legacy suites need a separately verified OS sandbox such as an isolated VM or Linux namespace/seccomp/landlock before their results can imply stronger security.

The historical scripts/test-runner.py was statically reviewed, not executed: it creates output/log folders, constructs a child unittest discovery process, inherits the host environment, and can load browser evidence. The paid_model_calls zero field is only a retrospective receipt. Existing tests/test_codex_mcp_transport.py can start installed Codex CLI and loopback HTTP. Legacy/native/browser/PDF suites are not certified safe by this PR and were not added to the guarded default.

## D. CI receipts and exclusions

The new pull-request GitHub Actions job uses hosted Ubuntu, read-only repository permissions, a complete checkout with no retained credentials, immutable legacy diff, complete AST audit and adversarial synthetic tests. Raw dependency-graph.json, architecture-audit.md, unittest.log and receipt.json are uploaded as run artifacts, including failures. The independent Phase 0 workflow still checks its six existing smoke tests.

GitHub checkout/action distribution necessarily uses GitHub infrastructure networking. Only the guarded synthetic Python process rejects ordinary Python networking: runner-wide network isolation is **not** asserted.

NOT_EXECUTED: old full test suite, self-hosted Ubuntu 26.04 installed/browser gate, native Codex and MAIN/Goal, paid model/API/provider calls, live research projects, real project path confinement on arbitrary host machines, system dependency/BOM lock, PDF build, 58 new and 46 inherited future acceptance tests, and mathematical proof checking. Neither any formal research project nor original research data was accessed or changed by this PR.

## E. Revert and PR-02/PR-03 inheritance

Unmerged rollback: close PR, leave main and legacy refs/tags untouched. Delete branch only with authorization. Post-merge rollback: separate software revert PR; never touch scientific journal, blobs, PAUSED/UNKNOWN reservations or stored evidence.

DEV-PR-02 must build ports/DTOs within these import rules, without passing Store, native process handles, framework states or provider-specific response objects through DTOs. Add explicit tests for each approved cross-layer exception rather than weakening the scanner.

DEV-PR-03 may inherit this safe synthetic entrypoint, but must separately prove read-only queries versus reconciliation using no-write, missing-ledger, permissions and stale-owner negative cases. The old host_pool.status() is not certified pure/read-only here.

Only an independent PMRH Development — MAIN review of the exact final source SHA, raw CI logs, artifacts and known limits can mark this work ACCEPTED.
