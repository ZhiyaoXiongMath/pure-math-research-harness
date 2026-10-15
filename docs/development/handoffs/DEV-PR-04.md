# DEV-PR-04 — Post-merge Development MAIN handoff

**Software baseline:** `main@1a85ba643d77420ffb7303665a9f9d31a1cca14c`, checked against Controller-supplied GitHub records on 2026-10-15.

**Software state:** IMPLEMENTED / TESTED / REVIEWED / MAIN ACCEPTED / GITHUB MERGED, for the bounded domain extraction.

**Archive state:** pending independent review of the final archive commit, separate MAIN disposition, user merge and post-merge readback. Keep the archival PR **Open** for the user; **HANDOFF COMPLETE is not declared**. This snapshot predicts neither its own SHA nor its archival PR number. Later archive review/acceptance belongs in the archive PR body.

## Provenance and authority

| Identity | Verified value |
|---|---|
| Software PR | [PR #9](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/9), merged by `ZhiyaoXiongMath` at `2026-10-15T08:50:43Z` |
| Original base / first merge parent | `f724c06b54b157abe580cdf046f4fc08bb01c144` |
| Accepted head / second merge parent | `acf7cd6e6b3c093459564487a44dbeb56845cc79` |
| Actual merge / observed main | `1a85ba643d77420ffb7303665a9f9d31a1cca14c` |
| Accepted and merged tree | `d7c5604b9752f984806125ceebc8414e0599d222` |

The Controller fetched fresh PR/main/merge/review/run records; its post-merge receipt is dated `2026-10-15T08:59:40.016478+00:00`. The archive Developer independently examined those supplied records, checked local Git identities, and matched all 319 tracked file bytes/modes to the merge tree. The accepted head has that same tree. **The archive Developer did not fetch live GitHub.** The supplied merge-SHA run query returned zero: **no separate merge-SHA CI observed**, not a PR CI failure. The submitted GitHub Review list is empty; the independent review below is a separate CLI/Chat audit.

- [Original software MAIN acceptance](../records/DEV-PR-04-MAIN-ACCEPTANCE-ORIGINAL.json) is byte-exact against the supplied decision, issued at `2026-10-15T08:30:34.642650+00:00`. Its historical `merge: NOT_AUTHORIZED_NOT_PERFORMED` remains unchanged; the later user merge is a distinct event.
- [Independent software review](../reviews/DEV-PR-04-INDEPENDENT-REVIEW.md) is an explicitly **path-normalized rendering, not byte-exact**. The original report SHA-256 is `623c6fc8b5192e6addce7667a3d2639d1674da8ab5b4d1d805d3218471f0c949`, checked against the supplied original. Private raw reports/logs remain with the Controller; the rendering identifies their provenance without publishing host paths.
- [PR #8 formal approval](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/8#issuecomment-6185982722) and its merge at the DEV04 base made [Research MAIN strategy v0.1.0](../../architecture/RESEARCH-MAIN-STRATEGY.md) and the [acceptance addendum](../ACCEPTANCE-ADDENDUM-04-11-12.md) effective specifications. Their candidate labels describe the earlier checkpoint. The user then separately authorized DEV04 implementation, offline tests, independent review and Open PR submission, as recorded in PR #9's scope; the user now separately authorizes this archive. Neither the former authorization hold nor the specification merge granted implementation permission.

## Accepted scope and inherited interfaces

The [DEV04 contract](../DEV-PR-04-CONTRACT.md) and PR #9's 34-path inventory define the delivery: seven rule modules plus initializer in `pmrh/domain`, explicit legacy aliases, exact architecture/scope allowances, a frozen-oracle runner and CI. ADR-0001/0002 and [ADR-034 locator semantics](../../decisions/ADR-034-local-body-locators.md) remain binding. The contract's pre-review/CI-pending labels are historical; the later receipts above establish only the scoped acceptance stated here.

| Domain ownership | Preserved API boundary |
|---|---|
| `primitives`, `contracts`, `knowledge` | Canonical bytes, shared `PMRSError`, closed scientific fields, KR/IB identities, six record kinds, exact locators/source bindings and argument validation; legacy filesystem and schema/authoring assembly stay outside domain. |
| `relations`, `assurance` | Selected support dependencies, cycles, withdrawal, exact qualification, independent slots and coverage; legacy consumers alias the same implementations. |
| `stages`, `protocols` | TRH P0–P14 / FDH D0–D5 / Survey declarations, StageSpec identity, assignment/exit rules, D0 validation and completion evidence; prompt assembly and application control stay legacy. |

Signatures, return forms, error codes and exception identity are preserved. Domain imports are standard library plus domain; `blob_get(hash)` is an explicitly supplied immutable-snapshot byte lookup, not permission to select a Store, path or live snapshot. No new public Port, backend, persistence adapter or service authority is introduced. `changes.validator_identity` intentionally includes all eight domain Python files in FORMAT's implementation fingerprint. Scientific KR/IB/StageSpec bytes/digests remain unchanged; old FORMAT evidence cannot certify a changed live implementation. Historical replay retains its recorded identity.

RMAIN-REQ-01/11 preserve original target/D0 and human choice; 03/04 preserve conditions, direction, witnesses, AND/OR and cycles; 09 preserves failure scope; 10 preserves independent qualification and scoped withdrawal; 12 preserves identities/history and minimal extraction. The contract maps bounded A01/A02, K01–K03, O02/O05, S03/S04, C04/C06/C07 and relevant GUIDE:K/C/P fragments. These are preservation receipts, not full cross-package acceptance.

Context, Statement, Argument, Example, SourceEvidence and Assessment remain the six immutable native scientific records. Candidate, admission, formal mathematical qualification and final completion stay distinct. Failure of a method/intermediate claim does not refute the original target; withdrawal affects selected dependent qualification and does not prove negation. Applicable independent support remains reusable. One logical Research MAIN, independent proof review, exact assumptions/provenance, original D0, P13 before P14, formal D5 human choice, separate paused TRH adoption, budgets, PAUSED, UNKNOWN and no automatic UNKNOWN retry remain intact. No new mathematical result or scientific checked status is claimed.

DEV11 first-class fast objects and DEV12 strategy/Worker-triad closed loop are **not implemented**. MR03/MR04/MR08 coverage is limited to existing domain fragments. The original 58+46 definitions are untouched and **not globally PASS**; full acceptance remains NOT_EXECUTED.

## Validation and CI provenance

The Controller reran the exact accepted head under Python **3.14.4**: 34 baseline fixtures, 34 facade fixtures, 10 boundary tests, 55 equal baseline/facade/domain trace entries, and DEV01/02/03/Phase0 counts 48/119/36/6 all passed. Commands recorded in the contract/PR and private receipts include:

```text
python3 -B scripts/check_legacy_scope.py
python3 -B scripts/architecture_deps.py --check --json <scratch>/dependency-graph.json --markdown <scratch>/architecture-audit.md
python3 -B scripts/offline_domain.py --out <artifact-root>/offline --oracle <frozen-base>
python3 -B scripts/offline_test.py --out <artifact-root>/devpr01
python3 -B scripts/offline_contracts.py --out <artifact-root>/devpr02
python3 -B scripts/offline_queries.py --out <artifact-root>/devpr03
python3 -B -m unittest discover -s tests/phase0 -p 'test_*.py' -v
```

These are historical executions, **not rerun by this archive Developer**. Exact launcher environments, raw logs, source/fixture hashes and child commands remain in private receipts. Test subprocesses used bwrap with read-only source, a separate network namespace, cleared environment, synthetic HOME/TMP, disabled bytecode and no mounted credentials. The guarded DEV04 runner's Phase0 fragments are distinct from the Controller's full six-test Phase0 execution.

All **five PR workflows / eight jobs succeeded**. The workflows allow `pull_request` and manual `workflow_dispatch`; these receipts concern PR validation, not a post-merge push run:

| Workflow / run | Tested checkout and result |
|---|---|
| [DEV04 38705408611](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38705408611) | Explicit accepted head; Python 3.11/3.13, each 34 baseline + 34 facade + 10 boundaries, 55 equal traces. |
| [DEV02 38705408437](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38705408437) | Explicit accepted head; 119 tests on each of 3.11/3.13. |
| [DEV03 38705408361](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38705408361) | Explicit accepted head; 36 tests on each of 3.11/3.13. |
| [DEV01 38705408388](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38705408388) | Temporary PR test merge; 48 tests. |
| [Phase0 38705408373](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38705408373) | Temporary PR test merge; 6 tests. |

DEV01/Phase0 checked `8c569475f561e9bd769870ebcc2c1d681d7330e6`, whose tree equals the accepted tree; this is **not** the actual merge `1a85ba6…`. The Controller verified both DEV04 artifact ZIP digests against the API, 319 archived source files, raw log hashes/test identities and trace counts:

| Artifact | ZIP SHA-256 |
|---|---|
| [11958800221 — Python 3.11.17](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38705408611/artifacts/11958800221) | `533394646fab1a0ac3174f94c0991ca7b0bc892517c197a374e2cfece43f705e` |
| [11958535780 — Python 3.13.16](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38705408611/artifacts/11958535780) | `b9f20ec6da085cb55d202cf11f9764c5113d80a03b5a32ba76180a3134874ba5` |

The original review conditioned publication acceptance on same-head 3.11/3.13 CI. The later MAIN decision records that condition **FULFILLED**. Earlier local receipts saying CI NOT_EXECUTED remain valid historical records.

## Independent findings, isolation and limits

The separate software Reviewer returned **APPROVE_FOR_MAIN_ACCEPTANCE**, with **0 new BLOCKER / MAJOR / MINOR**. It independently verified 319 source hashes, replayed 34 changed paths, compared 129 extraction ASTs/aliases and 79 signatures, checked the 166-file baseline oracle, and ran architecture/scope plus guarded purity/FORMAT probes. Eight simulated domain-file changes rejected stale live FORMAT evidence while preserving historical replay. It verified Controller suite evidence; it **did not rerun whole suites or fetch live CI**.

Actual backend records verified Developer and Controller `gpt-6-astra/high`, Reviewer `gpt-6-astra/xhigh`. Developer access was confined to its checkout/scratch with networking disabled; Reviewer source/input were read-only and scratch writable, with deny canaries. Controller management was **danger-full-access**; only its recorded test subprocesses had bwrap isolation. Development/review inference is management work; model/API usage is **NOT_MEASURED**, not zero. Static architecture rules and Python guards do not certify arbitrary hostile-native isolation.

The initial 37-test selection retained three failures on both baseline and facades:

| Historical test | Preserved failure and bounded replacement |
|---|---|
| `test_final_workflows.Workflows.test_n11_single_registry` | Expects 29 stages, actual 31; explicit stage/digest/dynamic-duty checks cover extraction. |
| `test_final_workflows.Workflows.test_unknown_and_capture_block_new_sample` | Stale scheduler fixture selects no work; bounded control checks do not establish full scheduler behavior. |
| `test_consumer_input_plans.ConsumerInputPlans.test_exact_excerpt_delivers_slice_not_full_backing_and_reports_unread_scope` | Store creation hits unchanged hardlink guard; pure excerpt checks do not establish Store publication. |

The final 34-fixture selection and pure bounded replacements do not relabel those failures or alter original tests/guards. Five EOF-only newline fixes were resolved before the accepted head; earlier raw receipts remain unchanged. Inherited **REV02-HELPER-01 remains accepted nonblocking, INCONCLUSIVE / NOT_EXECUTED**; unverified helpers must never be sole integrity/merge authority. The prior PR #5 historical document-review gap remains NOT_RETRIEVED.

**NOT_EXECUTED:** full legacy suite, full runtime/scheduler/timers and Store publication, native builds/runner/provider integration, browser/PDF, scientific migrations, real research/mathematical validation, full strategic scenarios and full 58+46 acceptance. Import/facade compatibility and narrow static allowances retain the limitations documented in the contract and review.

## Archive boundary, completion and rollback

This separately appointed documentation Developer edits only this handoff and [PROJECT-STATE](../PROJECT-STATE.md). Its actual Astra/high, approval-never, managed filesystem and network-disabled configuration passed the required scratch/input/outside/TCP probes. Local work uses read-only Git/source inspection and documentation validation; writes are limited to the two assigned documents and synthetic scratch receipts. No product execution, commit, GitHub operation or delegation is part of this assignment. The Controller owns evidence files and publication; an Independent Reviewer reviews the final archive commit. Software review does not review this archive in advance.

Keep the archival PR Open without auto-merge. Separate archive review/MAIN disposition, user merge and fresh main/merge-parent/tree/evidence-link readback are still required before declaring HANDOFF COMPLETE. Do not infer archive acceptance from this document's existence.

**DEV-PR-05 and every successor are NOT_AUTHORIZED / NOT_STARTED by this cycle.** No successor startup prompt, task dispatch, new MAIN/Goal, budget or research grant is issued. The roadmap remains a dependency plan only.

Before archive merge, corrections remain scoped documentation changes; abandonment requires preserving receipts and applicable user authority. After merge, rollback uses a separately authorized, reviewed revert PR. Software rollback must retain validator-fingerprint compatibility checks. Never rewrite original history or scientific journals/blobs, clear UNKNOWN, resume PAUSED or operate research projects as rollback.
