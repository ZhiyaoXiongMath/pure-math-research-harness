# DEV-PR-01 — post-merge Development MAIN handoff

**Scope:** `DEV-PR-01`, static dependency graph and isolated synthetic offline test baseline.  
**Handoff baseline:** `main@5d1b34d27bfbc171b2c5041973db8e8c1406a4b1` (verified 2026-10-12).  
**Status distinction:** GitHub `MERGED` verified; the complete original final independent Chat review is now [archived unchanged](../reviews/DEV-PR-01-INDEPENDENT-RE-REVIEW.md) (SHA-256 `8d40e731b3101c122b8e58e77da62a96b0089bfc2075885e6b509c688c74c6c9`); a separate archival source for the MAIN acceptance decision remains unavailable. This handoff does not grant DEV-PR-02/03 authority.

## 1. Real GitHub PR and acceptance history

- [DEV-PR-01 PR #2](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/2): `closed / merged=true` at **2026-10-12T11:32:08Z**.
- Development base: `main@977e866d64bba5cf7b5549f17a3d4b5599a4c20a` (Phase 0 merge). Development branch: `chore/dev-pr-01-static-offline-baseline`. **Final development head: `f8f93e962100010489946f4d82e302ea187c9874`**.
- Merge SHA: **`5d1b34d27bfbc171b2c5041973db8e8c1406a4b1`**; first parent Phase 0 merge, second parent final dev head. Final dev tree and merge tree both `5681becd4810657210643d99928f5f663c9f9760`.
- The PR touched **12 files**: architecture scanner and exceptions inventory, Python-level synthetic offline guard/runner, mandatory CI artifact gate, workflow, tests and developer audit/closure documents. `research_studio/` was not changed. No product, mathematical protocol, real MAIN/Goal, budget or live project migration was implemented.
- The initial independent review froze head `419a180fdf4b114691e8e44c8bf955e10a410970` with `REQUEST_CHANGES` (4 MAJOR, 2 MINOR). Following remediation, previously supplied final independent-review metadata reports `APPROVE_FOR_MAIN_ACCEPTANCE` at `f8f93e962...`, and the former Development MAIN is reported to have issued `ACCEPTED`. The [complete final reviewer report](../reviews/DEV-PR-01-INDEPENDENT-RE-REVIEW.md) has now been copied **verbatim** from the user attachment (16,855 bytes; SHA-256 `8d40e731b3101c122b8e58e77da62a96b0089bfc2075885e6b509c688c74c6c9`); its original `open` PR status describes the actual **pre-merge** audit moment and is preserved, not retrospectively edited. The independently retrievable MAIN `ACCEPTED` artifact is still unavailable. No submitted native GitHub PR #2 Review or issue conversation comment was found at the prior verification snapshot; the report is **independent Chat review**, not a GitHub Review submission.
- `REVIEWED` recommendation, `MAIN ACCEPTED` decision and observed GitHub `MERGED` remain different, even when describing one completed cycle.

## 2. Actual CI (source SHA and bounded results)

| Real record | Tested source | CI result and evidence |
|---|---|---|
| [DEV-PR-01 Actions run #38234570618](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38234570618) | `f8f93e962100010489946f4d82e302ea187c9874` | `completed/success`, job `114761973046`; **48/48 synthetic tests**. Frozen-legacy, AST, four-file verifier and artifact upload steps all `success` |
| [Phase 0 regression run #38234570610](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38234570610) | same final development head | `completed/success`, job `114761972816`, **6/6 Phase 0 regression tests** |
| [Final artifact #11739533909](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38234570618/artifacts/11739533909) | DEV-PR-01 final run | AST JSON, architecture Markdown, unittest raw log and receipt JSON; developer-recorded ZIP SHA-256 `f779fb2ee83f27e9e57b4cb865e4d703a7f1c3ea720c2475a41c532f5ad12145` |
| [Phase 0 original run #38210420301](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38210420301) | Phase 0 head `801bcf1a48d414a3a4ffecc293ae96587d32a9a6` | `completed/success`, 6 limited smoke/static tests; historical prerequisite |

GitHub's ephemeral PR test-merge tree was checked against the same final development tree in the PR evidence. **No separate post-merge `main@5d1b34...` CI pass is asserted.** Preserved failed development checks include [run #38233107438](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38233107438) (three useful pre-fix red counterexamples) and [run #38234040946](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38234040946) (later corrected test-assertion scope).

## 3. Six independent-review findings — final dispositions

These dispositions are supported by the [archived original independent re-review](../reviews/DEV-PR-01-INDEPENDENT-RE-REVIEW.md), [developer remediation ledger](../DEV-PR-01-INDEPENDENT-REVIEW-FINDINGS.md) and final CI. This handoff summarizes the independent report; it does not replace or rewrite it.

| Finding | Severity | Final code/test change | Recorded disposition |
|---|---|---|---|
| **SEC-01** | MAJOR | Deny Python-guarded `os.link` hardlink escape while keeping original-source write denial and legal scratch tests | Implemented/tested, archived independent re-review PASS |
| **AST-01** | MAJOR | Recognize supported `importlib.import_module` function/module aliases; unresolved dynamic targets fail closed in new `pmrh` layers | Implemented/tested, archived independent re-review PASS |
| **AST-02** | MAJOR | Explicitly classify `pmrh` root modules and enforce forbidden transitive layer paths | Implemented/tested, archived independent re-review PASS |
| **CI-01** | MAJOR | Require all four CI artifacts with checked HEAD, hash, count and status; copy/upload failures cannot yield green | Implemented/tested, archived independent re-review PASS |
| **TEST-01** | MINOR | Timeout and child-start failures produce structured `ERROR` receipt/partial-output flags where possible | Implemented/tested, **not deferred**, archived independent re-review PASS |
| **AST-03** | MINOR | Report named legacy couplings independently of 442 provisional cross-layer entries, matching real direct edges | Implemented/tested, **not deferred**, archived independent re-review PASS |

Final source-static report (not a dynamic dependency certification): **144 Python files**, **4 namespace virtual nodes**, **987** unique direct edges, **6,160** transitive reachabilities, **one** large cyclic SCC, **442** provisional legacy cross-layer entries plus **4** separately named architectural couplings, **0** syntax errors and **0** known detected new-layer violations.

## 4. Accepted constraints and NOT_EXECUTED items

- Python-level guard = **defense-in-depth, not OS sandbox**. Pre-existing hardlinks, inherited descriptors, native syscalls, hostile mounts/process environments remain outside guarantee.
- Static AST checks cannot cover arbitrary dynamically computed imports, reflection or `exec`. The 442 + 4 legacy reports are migration debt, not automatically rule violations.
- Model/provider request measurement is `count=null`, `NOT_INSTRUMENTED` / `NOT_MEASURED`; **do not assert zero calls**.
- `NOT_EXECUTED`: original full legacy test-runner suite; native Codex and Research MAIN/Goal; real project isolation and migration; OS sandbox; browser/PDF; Ubuntu 26.04 integrated product gate; actual model/provider telemetry and the future **58 new + 46 inherited acceptance cases**.
- Phase 0 provenance/security acceptance was scoped to its original independently attested historical Git migration and no broader scientific/runtime guarantee.

## 5. DEV-PR-02/03 contract inherited by the next MAIN

**Candidate DEV-PR-02 — ports, immutable DTO and explicit errors:** depends on DEV-PR-01 and must retain the import direction gate, unknown-root/dynamic-import rejection, immutable `research_studio` source, named architectural debt, original scientific identity, structured failure status and separation of AgentRunner from ModelProvider. Neither a Store object nor native process/SDK/framework state should cross domain DTO boundaries. Positive and forbidden-dependency negative tests require a new work authorization.

**Candidate DEV-PR-03 — pure query and reconciliation separation:** depends on DEV-PR-01 and interface alignment with 02. Existing `host_pool.status()` may reconcile/write a resource ledger; it was **not** proven read-only in DEV-PR-01. Require no-write/missing-ledger/permissions/stale-owner adversarial checks; no reactivation of removed `PROJECT_ASSISTANT` or scientific execution.

**Both are NOT AUTHORIZED.** The successor Development MAIN must reread current [AGENTS](../../../AGENTS.md), [CONTRIBUTING](../../../CONTRIBUTING.md), [MAIN protocol](../MAIN-OPERATING-PROTOCOL.md), [PROJECT-STATE](../PROJECT-STATE.md), [ROADMAP](../ROADMAP.md), [acceptance baseline](../ACCEPTANCE-BASELINE.md), effective [ADR-0001](../../architecture/ADR-0001-naming.md) and [ADR-0002](../../architecture/ADR-0002-constraints.md), and live GitHub merged PR/source/CI. Reconcile conflicts, then obtain a new explicit user grant and decide independent review and coordination responsibilities. Any parallel work requires interface ownership, source baseline and an architectural conflict arbiter in advance. The previous MAIN ceases starting new packages after handoff.

**Rollback:** a subsequent defect in merged DEV-PR-01 requires a separate reviewed software revert PR, not a reset of original Git history, research evidence, budget or PAUSED/UNKNOWN state.
