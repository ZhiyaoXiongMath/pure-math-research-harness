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

A real full checkout scan at head `9a9247ca4a1e6f6f185c43addfc879c9e3a1b7e1`, [Actions 38228336273](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38228336273), found **141 Python files, 4 explicit implicit-namespace graph nodes, 1,475 import occurrences between local modules, 981 deduplicated direct arrows, 6,154 transitive reachability arrows, one nontrivial cyclic strongly connected component**, and 442 provisional legacy cross-layer import occurrences; zero AST parse failures and zero new-layer prohibited imports. New synthetic counterexamples verify that `import pmrh.adapters` and `from pmrh import adapters` are rejected from `pmrh.domain` even without `adapters/__init__.py`. A legitimate `application → ports → domain` implicit-package chain remains permitted. The scanner creates a dedicated `@namespace/pmrh/adapters` virtual dependency node, never a fictional source file. Counts may change at later HEADs; the final HEAD CI artifact is authoritative.

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

To persist reports, the trusted CI/operator must pre-provision a fresh artifact root **directly under the OS temporary directory**. No arbitrary output paths are accepted. Example (on a POSIX workstation with a separate /tmp):

```sh
ARTIFACT_ROOT="$(mktemp -d /tmp/pmrh-devpr01-artifacts-XXXXXXXX)"
mkdir -p "$ARTIFACT_ROOT/offline"
PMRH_TEST_ARTIFACT_ROOT="$ARTIFACT_ROOT" \
  python3 -B scripts/offline_test.py --suite devpr01 --out "$ARTIFACT_ROOT/offline"
# Read the receipts from "$ARTIFACT_ROOT/offline" and remove the directory.
```

Without `--out`, the tool reports an inline receipt without persisting it. If `--out` is specified but no root is configured, the root is not a fresh dedicated temp child, or the destination is not an existing strict descendant, the launcher rejects it **before temporary scratch allocation, subprocess creation, or any output write**. It rejects HOME/source tree overlaps, `..` traversal, a non-allowed project directory, symlinked directory components, and existing (including symlink) output files. Accepted writes use opened directory file descriptors plus `O_CREAT|O_EXCL|O_NOFOLLOW` to prevent overwriting or following a receipt-file symlink. An isolated root supplied by a trusted CI/operator is a precondition, *not* an OS access-control mechanism: someone controlling process environment, code, or native execution can bypass Python policy.

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


## F. MAIN review fixes A/B/C (2026-10-12)

**A — artifact path / fail-before-write.** The former code only rejected exact HOME and one parent, allowing HOME subdirectories, other host project locations and symlink destinations. The repaired output policy requires \`PMRH_TEST_ARTIFACT_ROOT\`, a dedicated pre-existing system-temp directory with an exact test-artifact naming prefix, and pre-existing descendant \`--out\`. It validates before creating scratch, running a test or writing a receipt; opened directory descriptors and exclusive no-follow final-file opens narrow symlink/overwrite races. The CI now provisions this root via \`mktemp -d /tmp/pmrh-devpr01-artifacts-XXXXXXXX\` and copies its signed-off results to GitHub artifact staging after the guarded child has exited. Negative tests reject absent/mislocated allowed root, HOME descendant, arbitrary project path, \`..\` traversal, ancestor symlinks, root symlink and receipt symlink, and check scratch/subprocess launch counters are zero for denied destinations. This is a cooperative trusted-operator/CI boundary, not protection against a local adversary controlling environment or syscalls.

**B — AST implicit packages.** The original catalog only registered \`__init__.py\` and concrete \`.py\` files, so importing \`pmrh.adapters\` when \`pmrh/adapters\` lacked an initializer could be misclassified as external. The scanner now records implicit directories as explicit namespace nodes, includes them in reachability/SCC graphs, checks them through layer direction rules, and deduplicates the two syntactic references generated by \`from pmrh.adapters import codex\` on one source line. New synthetic cases cover \`import pmrh.adapters\`, \`from pmrh import adapters\`, literal dynamic namespace import and a legal \`from pmrh import ports\` example. No product code is imported.

**C — measured usage versus static checks.** Prior receipt incorrectly wrote \`research_model_calls=0\` upon any successful unittest run. Now \`research_model_calls\` is a structured object with \`count: null\`, \`measurement: NOT_INSTRUMENTED\`, \`observed_provider_events: NOT_MEASURED\`, \`zero_calls_verified: false\`, and separate fields for synthetic-only entrypoint scope and Python-level socket/process guards. This is **not a measured zero** and does not purport to certify external OS/network telemetry. The negative test checks that the receipt cannot regain its former conditional zero claim.

**Failure and retest receipts.** [First review-fix CI #38228197536](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38228197536) passed frozen legacy and AST scanning, but **FAILED** guarded unittest import: \`unittest.mock\` indirectly imported \`ssl\` after the socket guard was installed. The synthetic tests now use simple in-process sentinels without that late standard-library import. At source head \`9a9247ca4a1e6f6f185c43addfc879c9e3a1b7e1\`, [review-fix CI #38228336273](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38228336273) completed **SUCCESS, 26/26 tests**; corresponding [Phase 0 #38228336317](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38228336317) completed **SUCCESS, 6/6 tests**. After final documentation changes, verify both again at the actual PR head and use those later run receipts for formal handoff.

**Remaining limitations.** A caller who can change the trusted environment or run arbitrary native system calls can circumvent this Python-level boundary. Real project locations must never be configured as the allowed artifact root; OS-level sandbox/mount/network enforcement is still \`NOT_EXECUTED\`. The static scanner cannot identify arbitrary runtime-created packages or computed imports. There is no provider-side token/request telemetry in this test runner, so model-call counts remain unmeasured. The old research/native tests and formal projects remain entirely out of scope.

## G. Third remediation — Independent review REQUEST_CHANGES disposition (2026-10-12)

**This section supersedes older counts and PASS references for the current developer branch.** The previous independent review froze HEAD `419a180fdf4b114691e8e44c8bf955e10a410970` and requested changes for 4 MAJOR (`SEC-01`, `AST-01`, `AST-02`, `CI-01`) and 2 MINOR (`TEST-01`, `AST-03`). See the [six-finding remediation ledger](DEV-PR-01-INDEPENDENT-REVIEW-FINDINGS.md) for every original counterexample, file/function/line, root cause, test name, preliminary/final run, and residual risk.

All six have a developer implementation and synthetic regression tests; **neither MINOR was deferred**. New files are `scripts/verify_devpr01_artifacts.py`, `tests/devpr01/test_review_regressions.py`, `tests/devpr01/test_review_closure.py` and the findings ledger. Existing AST analysis, explicit `config/architecture-exceptions.json` and `tests/devpr01/test_static_and_offline.py` are retained.

**Before/after evidence:** reviewer-frozen historical bug is supported by the exact reviewer report; additionally developer run [#38233107438](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38233107438) yielded **30 tests with three expected new failures** before the code fixes (SEC-01, AST-01, AST-02). Expanded CI [#38234040946](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38234040946) yielded **48 tests with one test-assertion failure** caused by matching YAML comment text; this assertion was narrowed to executable copy statements, not omitted. Developer checkpoint [#38234174793](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38234174793) passed **48/48** with the required-four-file gate and artifact [#11739228793](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38234174793/artifacts/11739228793). [Phase 0 #38234174852](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38234174852) passed **6/6**. The final documentation commit requires a new final-HEAD Actions pair, to be linked in PR #2.

**Architecture semantics:** The AST scanner now reports 4 namespace virtual nodes plus approved package-root modules, rejects unknown `pmrh` root modules, handles known `importlib` aliases and marked-unresolved targets, checks forbidden transitive dependencies, and separately enumerates **442 provisional cross-layer legacy entries plus four named architectural couplings**. A named same-layer coupling (e.g. `store → native_main`) is not incorrectly treated as part of the 442. Both are provisional migration evidence, not a claim that all original source imports violate the target layering.

**Execution/capture semantics:** An offline child timeout or spawn error now results in an `ERROR` receipt with partial-output indicators and unmeasured test/model quantities. CI checks AST JSON + Markdown and offline receipt + raw unittest log as a mandatory four-file set; hash/count/head/status mismatches fail the job, and any copying failure remains nonzero. Successful GitHub Actions transport does not establish an OS sandbox or actual provider-side zero-model-use proof.

**No expansion of scope:** `research_studio/`, its mathematical semantics/SCI records, real user project files, MAIN/Goal, budgets and native runners remain unchanged and unexecuted. Python guard still cannot constrain preexisting hardlink aliases, inherited FDs, native system calls or all runtime import/reflection. Provider telemetry remains `NOT_MEASURED`, and historical/browser/Ubuntu26.04 product gates remain `NOT_EXECUTED`. Follow-up authority remains only with the Independent Review Chat and PMRH Development — MAIN; developer status is `READY_FOR_INDEPENDENT_RE_REVIEW`, never self-declared ACCEPTED.
