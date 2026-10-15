# DEV-PR-04 independent review — public archival rendering

This is a path-normalized rendering, **not a byte-exact copy**, of the original independent CLI report. Original UTF-8 SHA-256: `623c6fc8b5192e6addce7667a3d2639d1674da8ab5b4d1d805d3218471f0c949`. Only absolute local link destinations are transformed: source links point to the reviewed GitHub head; private evidence links become relative evidence identifiers. Report prose, verdict and historical CI condition are otherwise preserved. Private identifiers are provenance labels, not public download links. The byte-exact original and raw receipts remain in the Controller’s local evidence archive.

The subsequent [original MAIN decision](../records/DEV-PR-04-MAIN-ACCEPTANCE-ORIGINAL.json) records fulfillment of the exact-head CI condition. The later [Handoff](../handoffs/DEV-PR-04.md) records actual merger. Neither changes this historical review.

---

**APPROVE_FOR_MAIN_ACCEPTANCE — 0 BLOCKER, 0 MAJOR, 0 MINOR new findings.**

This recommendation covers the bounded DEV-PR-04 extraction at the identities below. Publication acceptance remains conditional on successful Python 3.11/3.13 CI for the same submitted head. This is an independent review recommendation, not `MAIN ACCEPTED`, merge authorization, or authorization for another work package.

| Identity | Independently verified value |
|---|---|
| HEAD | `acf7cd6e6b3c093459564487a44dbeb56845cc79` |
| Tree | `d7c5604b9752f984806125ceebc8414e0599d222` |
| Parent/base | `f724c06b54b157abe580cdf046f4fc08bb01c144` |
| Base tree | `578fd501442d9155ce1103b971c43cfaf57242ea` |

I verified these through local Git, matched all **319 frozen file hashes**, and replayed every supplied diff hunk against the independent baseline in memory: all **34 changed paths** reproduced the reviewed files. `git diff --check` passed, the checkout was clean, and the final source hashes remained unchanged.

The observed runtime configuration (`private-evidence:input/reviewer-actual-config.json`) identifies this review turn as `01a13e9e-cedf-7620-a950-215430b494fa`, running **gpt-6-astra/xhigh**, with `approval_policy=never`, restricted networking, and managed profile `devpr04-independent-review`. Source, baseline and input are read-only; scratch is the only writable task directory. Configuration SHA-256: `76031fdef343810e6bab123dabc13a2cdf92947e9130c87dea0754eff59e965f`.

The first poll invocation failed because `python` was unavailable; retrying with `/usr/bin/python3` observed `VERIFIED` before review proceeded. All required canaries passed:

| Canary | Observation |
|---|---|
| Scratch write/read | Allowed |
| Source README append-open | Denied, `EROFS` |
| Input canary append-open | Denied, `EROFS` |
| Controller-attested original work README | Hidden, `ENOENT` |
| TCP socket/connect attempt | Denied, `EPERM` |

Canary evidence (`private-evidence:scratch/isolation-evidence.json`) is preserved. I used no delegation, source edits, GitHub operations, MCP/apps/plugins, product model calls, or real research access.

I read AGENTS, CONTRIBUTING, all three relevant ADRs, MAIN protocol, PROJECT-STATE, DEV03 Handoff, ROADMAP, acceptance baseline, approved preparation, effective strategy/addendum v0.1.0, and the [DEV04 contract](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/blob/acf7cd6e6b3c093459564487a44dbeb56845cc79/docs/development/DEV-PR-04-CONTRACT.md). The historical candidate/authorization labels conflict with the current authorized scope and supplied PR8 acceptance/merge facts; I treated those labels as historical, as explicitly instructed. I did not independently query live GitHub.

The implementation is appropriately narrow:

- **One scientific implementation, compatible consumers.** I compared all **129 extracted symbols** against their baseline ASTs, normalizing import relocation and the documented stage aliases. All matched. The complete concatenated stage implementation, including Survey’s construction loop, also matched. My guarded runtime probe confirmed all 129 aliases reference the same objects and checked **79 function signatures**, including shared `PMRSError` identity.
- **Actual domain purity.** The extracted modules import only domain modules and the standard library. Standalone domain import loaded no legacy, ports or application modules. Original-byte lookup remains an explicitly supplied `blob_get(hash)` capability; domain code does not select a filesystem path, Store or live snapshot. The existing local knowledge/assurance dependency remains contained within domain.
- **Minimal complexity.** The change introduces no service container, second repository, database, backend, migration, strategy loop or fast-math object system. Legacy prompt/schema assembly and application control remain with their existing consumers.

I inspected the moved scientific implementations and their consumer bindings, not merely the tests. The preservation evidence supports these bounded conclusions:

| Responsibility | Review conclusion |
|---|---|
| Six records, provenance and identity | Closed fields, canonical encoding, KR/IB identity, exact source/quote bytes, locator ranges and staging semantics are preserved. |
| Conditions and composition | Typed assumption bindings, conditional limitations, explicit witness/quantifier evidence, AND/OR and lifting obligations remain intact. |
| Qualification and independence | Candidate/admission/formulation status does not substitute for proof qualification. Authentic execution binding, author exclusion, distinct slots, exposure checks and coverage integration remain in the actual evaluation path. |
| Cycles and invalidation | Cyclic support is rejected. Withdrawal follows selected dependencies, does not substitute another proof, and does not establish negation; independent applicable support remains reusable. |
| Original goal and D0 | Completion remains tied to the original target, dual review and applicable integration. D0 retains its required original-source bindings. |
| Workflow and human control | Stage declarations/digests and dynamic responsibilities are preserved. P13/P14, stop handling, formal D5 and separate paused TRH adoption remain application-controlled. |

Relevant implementation anchors include [record validation](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/blob/acf7cd6e6b3c093459564487a44dbeb56845cc79/pmrh/domain/knowledge.py#L65), [qualification](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/blob/acf7cd6e6b3c093459564487a44dbeb56845cc79/pmrh/domain/assurance.py#L277), [authentic coverage integration](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/blob/acf7cd6e6b3c093459564487a44dbeb56845cc79/pmrh/domain/assurance.py#L176), [selected-support invalidation](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/blob/acf7cd6e6b3c093459564487a44dbeb56845cc79/pmrh/domain/relations.py#L120), and [completion evidence](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/blob/acf7cd6e6b3c093459564487a44dbeb56845cc79/pmrh/domain/protocols.py#L149).

FORMAT’s [implementation fingerprint](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/blob/acf7cd6e6b3c093459564487a44dbeb56845cc79/research_studio/changes.py#L637) now includes all eight domain Python files while retaining the existing legacy entries. My additional synthetic probe simulated a byte change in each domain file: **live verification rejected the old FORMAT evidence in all eight cases**, while historical replay remained valid and retained its recorded identity. No files were modified by these simulations. This correctly distinguishes changing implementation fingerprints from preserved scientific KR/IB/StageSpec identities.

The static allowances remain specific: named paths, symbols and 13 direct dependency edges with ownership/removal metadata. The original audit baseline is retained; DEV03 read allowances and reconciliation-body protection remain active. Existing policy rules are unchanged apart from the added DEV04 scope and explanatory wording. Negative tests exercise blanket allowances, forbidden reverse dependencies, duplicate facade implementations and unrelated mixed-module writer edits. These checks are useful static enforcement, not a claim to sandbox arbitrary hostile Python.

I independently executed the following checks:

| Execution | Result |
|---|---|
| Runtime gate/configuration and required isolation canaries | PASS |
| Local Git identity, cleanliness and diff whitespace checks | PASS |
| Frozen hashes, baseline Git-object hashes, diff replay and extraction AST comparisons | PASS |
| `python3 -B scripts/check_legacy_scope.py` | PASS |
| `python3 -B scripts/architecture_deps.py --check …` | PASS |
| Fixed guarded reviewer probe: standalone import, all aliases/signatures, FORMAT live/historical behavior | PASS |

The runtime probe used Python **3.14.4**, a clean environment, scratch HOME/XDG/TMP, disabled bytecode, and the inherited offline guard. Exact commands, environments, exit codes and log hashes are in the review-check receipt (`private-evidence:scratch/review-check-receipt.json`); the probe source (`private-evidence:scratch/reviewer_probe.py`), static comparisons (`private-evidence:scratch/static-review.json`), and final static checks (`private-evidence:scratch/final-static-checks.json`) are also preserved.

I inspected and verified these **Controller executions; I did not rerun these suites**:

| Raw evidence | Verified result |
|---|---|
| Selected historical fixtures | 34/34 baseline; 34/34 facade |
| Separate baseline/facade/domain traces | 55 entries, equal across all three |
| DEV04 boundary tests | 10/10 |
| DEV01 | 48/48 |
| DEV02 | 119/119 |
| DEV03 | 36/36 |
| Full Phase0 suite | 6/6, including the original CLI smoke method |
| Architecture and legacy-scope gates | PASS |

I checked raw log hashes, test identities/counts, terminal results, selection identities and recorded source hashes. The **166-file oracle** covers every baseline Python file under `pmrh`, `research_studio` and `tests`; every hash also matched the corresponding base Git object. Some inherited receipts report checkout metadata as `UNVERIFIED_LOCAL`/`UNVERIFIED_WORKTREE`; their recorded source hashes match the frozen checkout independently verified here.

The receipt inspection (`private-evidence:scratch/receipt-inspection.json`) records these checks. Raw evidence resides under Controller artifacts (`private-evidence:input/controller-tests/sandbox/pmrh-devpr01-artifacts-ov2v1oax`). I also inspected the Controller’s bwrap command, sandbox probe, Developer runtime/isolation records, failure/fix log and EOF correction receipt. **The Controller management runtime is `danger-full-access`; only its recorded test subprocesses had the described bwrap isolation.**

The three historical failures are **baseline issues, not extraction regressions**:

| Location and minimal reproduction | Observed failure and impact |
|---|---|
| [test_final_workflows.py:47](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/blob/acf7cd6e6b3c093459564487a44dbeb56845cc79/tests/test_final_workflows.py#L47): `Workflows.test_n11_single_registry` | Expects 29 stages; both implementations contain 31. Replacement checks the explicit stage set, shared declarations/digests and dynamic duties. |
| [test_final_workflows.py:31](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/blob/acf7cd6e6b3c093459564487a44dbeb56845cc79/tests/test_final_workflows.py#L31): `Workflows.test_unknown_and_capture_block_new_sample` | Stale fixture indexes an empty scheduler selection on both versions. Full scheduler execution remains uncovered; replacement boundary checks do not claim to repair it. |
| [test_consumer_input_plans.py:92](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/blob/acf7cd6e6b3c093459564487a44dbeb56845cc79/tests/test_consumer_input_plans.py#L92): `ConsumerInputPlans.test_exact_excerpt_delivers_slice_not_full_backing_and_reports_unread_scope` | Store creation reaches the unchanged hardlink prohibition on both versions. Replacement verifies pure excerpt delivery and rejection boundaries, not Store publication. |

Initial **37-test failures remain failures** in the retained raw evidence. Historical test definitions and the guard were not changed. I also verified that each of the five EOF corrections removed exactly one trailing newline byte; the original receipt remains untouched. These resolved formatting issues create no open finding.

Remaining limits are explicit:

- Python **3.11/3.13 CI and live GitHub publication state: NOT_EXECUTED by this reviewer**. Controller must verify successful CI on this exact submitted head before final acceptance.
- Full historical discovery, scheduler/runtime integration, Store publication, native/runner/browser/PDF operations, migrations and real research: **NOT_EXECUTED**.
- RMAIN-MR03/MR04/MR08 evidence covers existing domain fragments only. Full strategic behavior, DEV11/12 functionality, reader comprehension and mathematical validity are not established.
- The original **58+46 definitions, scientific methods and roadmap remain unchanged**; they are not collectively marked PASS.
- Model/API usage remains **NOT_MEASURED**, not measured zero. Synthetic software passes confer no mathematical qualification.
- Previously accepted historical documentation/helper limitations remain inherited; this review neither closes nor recounts them as new DEV04 findings.

No substantive extraction defect or scope violation requiring remediation was found. The authorized review is complete.