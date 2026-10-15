# Research MAIN acceptance addendum — future DEV-PR-04 / 11 / 12

**Version:** 0.1.0 (2026-10-15)  
**Status:** CANDIDATE DOCUMENTATION ONLY, pending independent review / Development MAIN acceptance / user merge. All newly described behavior tests and actual research evaluation **NOT_EXECUTED**.  
**Product specification:** [Research MAIN strategy](../architecture/RESEARCH-MAIN-STRATEGY.md); **original source:** `Main-Agent-Design-Requirements.zh-CN.md` v0.1 (2026-10-14, SHA-256 `8af8130f673f0abf1b6a47f6bd4fce986e0162f583da422481dce14183ec6cc9`). **Inherited authority:** [58+46 acceptance baseline](ACCEPTANCE-BASELINE.md), [fixed Roadmap](ROADMAP.md), [implementation plan §15](../reference/PMRS-Next_Phase1/02-Implementation-Plan.zh-CN.md) and ADR-0002.

The prefix `RMAIN-REQ` is **product design**, not a new scientific qualification state or software acceptance `R01–R03`. `RMAIN-MR01–10` names local **scenario indices**, not replacement baseline IDs or current PASS receipts. Reuse existing evidence, avoid any duplicate proof-checking pipeline.

## Requirement-level traceability

| Original user clause | Candidate specification | Existing cases (reused) | Future lead |
|---|---|---|---|
| R01 | RMAIN-REQ-01 | K07/K08, GUIDE:K01, GUIDE:P01 | DEV12 / DEV04 preservation |
| R02 | RMAIN-REQ-02 | K01/K04/K06, GUIDE:K01–K04, GUIDE:K15–K16 | DEV11 |
| R03 | RMAIN-REQ-03 | K01/K03/K04, GUIDE:K02–K05, GUIDE:K08 | DEV11 |
| R04 | RMAIN-REQ-04 | K01/K03, GUIDE:K04, GUIDE:K06–K08, GUIDE:K11 | DEV11/DEV04 |
| R05 | RMAIN-REQ-05 | K04/K07, GUIDE:K02, GUIDE:P01 | DEV12 |
| R06 | RMAIN-REQ-06 | K05/K07, GUIDE:K12, GUIDE:P01 | DEV12 |
| R07 | RMAIN-REQ-07 | K04/K07/O05, GUIDE:P11 | DEV12 |
| R08 | RMAIN-REQ-08 | K05/K07/S04, GUIDE:K12, GUIDE:C15–C16 | DEV12/DEV11 |
| R09 | RMAIN-REQ-09 | K02/K04/O02/O05, GUIDE:K09/K13 | DEV04/11/12 |
| R10 | RMAIN-REQ-10 | K02/K03/S03/S04, GUIDE:K09/K11, GUIDE:C13–C15 | DEV11/12 |
| R11 | RMAIN-REQ-11 | C05–C07/O05, GUIDE:P02–P06 | DEV04/13 |
| R12 | RMAIN-REQ-12 | K06–K08/R01/R02/O02, GUIDE:K15–K16, GUIDE:P08 | DEV11/12/13 |

The 58 new cases and 46 inherited GUIDE cases remain unchanged and retain their actual not-yet-executed status. The mapping identifies **where to implement/validate later**, not a new PR dependency or automatic permission.

## Scenario-level acceptance map: each has a valid continuation and a rejection

| Original / candidate case and clauses | Allowed / positive behavior | Must reject or keep unqualified | Existing coverage | Owner, future evidence |
|---|---|---|---|---|
| MR01 / RMAIN-MR01 · 04–06 | From H and target G, propose a partial forward/backward mechanism chain with a bounded probe on the missing arrow | Treat necessary/backward arrow as proved sufficient or grant checked to dashed link | K01/K04/K07, GUIDE:K05/K08/P01 | DEV11/12; versioned map + decision packet |
| MR02 / RMAIN-MR02 · 03/05 | Transfer a donor mechanism, explicitly note a donor-only prerequisite and keep target OPEN pending applicability work | Give target checked merely from donor theorem | K04, GUIDE:K02/K05 | DEV11/12; donor/target map + obligation |
| MR03 / RMAIN-MR03 · 09/10 | On local failed A⇢B, retain unaffected A and original G, and consider repaired B, A⇢C⇢G, or reasoned wait | Conclude not-G or kill all OR routes from one failure | K02/K04, GUIDE:K09/K13 | DEV04/11/12; exact witness + map delta |
| MR04 / RMAIN-MR04 · 09/11 | Distinguish method failure, “no counterexample found,” and scope-qualified original counterexample | Use incomplete effort as proof/refutation | O02/O05, GUIDE:K13/P11 | DEV04/12; hypothesis and independent review |
| MR05 / RMAIN-MR05 · 01/08 | Actual MAIN packet conveys target/D0, current map/guidance/increments; Worker triad binds to input identity | Claim file existence proves delivery; backdate new input; pollute independent review with prior verdict | K05/K07/S03/S04, GUIDE:C10/C15/C16 | DEV12; assembled packet + captured output |
| MR06 / RMAIN-MR06 · 08/09/12 | Honest no-progress/empty fast delta, bounded stop and retry only with material change | Fabricate progress or reissue identical attempt merely renamed | K05/O02, GUIDE:K12/P01 | DEV12; attempt/retry trace |
| MR07 / RMAIN-MR07 · 02/10/12 | Restore failed/new routes, unconsumed increments and evidence beyond body prefix; report search coverage | Hide source/index limits or forget failure causes | K02/K06/Q04, GUIDE:K15/K16 | DEV11 with 05/09; recovery/retrieval receipt |
| MR08 / RMAIN-MR08 · 11 | FDH under D0 records a revised candidate after a scoped original counterexample; relation unknown stays unknown; formal D5 remains human choice | Silent Goal replacement, auto-adopt candidate, “unknown” becomes non-implication | C05/C06/O05, GUIDE:P03–P06 | DEV04/13; fixed D0 + choice/control trace |
| MR09 / RMAIN-MR09 · 02/12 | A qualified human reader identifies goal, assumptions, interfaces, supported/open lines and next probe | Fluent prose or a ReaderProfile grants mathematical qualification | K08/R01, GUIDE:K01/K14/P08 | DEV11/13; human comprehension/math review |
| MR10 / RMAIN-MR10 · 05/09/12 | Under **separate authorization** compare old/new strategy using same problem, materials, model, tools and budget, evaluating decision quality and failure reuse | Count nodes/tasks or synthetic PASS as evidence of improved open-problem success | K05/K07/R01, GUIDE:P01/P11 | DEV18 / separate experiment; matched evaluation |

**Evidence tier per scenario:** (1) synthetic semantic/fixed-trace test checks sound status handling and legitimate continuation; (2) actual frozen input assembly and fake Runner capture checks delivery to the invocation boundary, **not comprehension**; (3) exact mathematical/reader review and real-model behavior evaluation require appropriate independent mathematicians and (for MR10) separate human authorization. MR09 cannot pass purely by model score. Neither MR09 nor MR10 is a mandatory paid DEV04 start gate.

## Three small reusable, paired traces

**T1 — Successful connection / unchanged-review reuse.** Given independently supported H⇒A and A⇒G under the *same context and witnesses*, the qualified composite may be recognized only after necessary join/global obligations are checked. Other OR branches need not be completed, and unchanged local review may be reused. Rejection: H⇒A and G⇒A do not prove G; a displayed path or adjacent checked nodes is insufficient.

**T2 — Local failure / structure repair.** Original goal H⇒G remains open, H⇒A has support, and A⇢B⇢G is a candidate. A worker gives an H/A witness failing B but does not provide not-G. Preserve `slow_layer_result`, `fast_layer_delta` identifying the affected arrow, and `attempt_account`; MAIN may test A⇢C⇢G, repair B, seek an actual G counterexample or wait with reasons. Do **not** infer not-G, checked bypass, or invalidate unrelated qualified support.

**T3 — Donor transfer blocked / valid donor reuse.** A known theorem on a donor object requires condition T, not established for target H. Record the donor and exact object/assumption mapping, test the applicability interface H⇢T and keep target open. Reuse the donor in its valid original scope. Do **not** copy its checked verdict to the new target or silently drop T.

Each trace records frozen original inputs and versions, accepted vs merely proposed status, actual delivered packet, map revision, lawful wait/continue and decision reason. Traces can be implemented incrementally in later authorized packages. They prove software handling only; they are **not** actual mathematical achievements.

## Work-package responsibility, non-goals and dependency preservation

| Package | Future minimum responsibility | Explicit exclusion |
|---|---|---|
| **DEV-PR-04** | Extract and preserve existing domain semantics: goal/D0 identity, candidate versus qualified, exact failure scope, AND/OR, withdrawal versus negation and independent proof review; pair overblocking negatives with legitimate reuse positives | Not a ResearchMap database, planning algorithm, Lean, new scientific-review authority or DEV11/12 implementation |
| **DEV-PR-11** | First-class fast objects, precise conditionality/quantifiers/shared witnesses, RefinementBinding, versions, scoped invalidation and actual authorized retrieval beyond prefixes/legacy research_routes | Not graph reachability as mathematical proof; no second authority or unneeded database |
| **DEV-PR-12** | Actual MAIN prompt/packet assembly and strategic choices; consequential Worker question, linked slow+fast+attempt returns, honest empty delta, local-failure replan and reviewer context isolation | Not mere documentation, fixed-stage script, mandatory route churn or extra summary Agent |
| **DEV-PR-13** | Exact accepted-KB snapshot as source for readable P13/report/FDH synthesis; expose conditional/open connections, stale increments and P13→P14/formal D5 controls | Not a new proof or Survey-only compulsory writing template |
| DEV-PR-05/06 | Exact persistence/CAS, grants, epoch, qualified admission, PAUSED/UNKNOWN, no blind retry | A proposed fast delta cannot independently authorize new research |
| DEV-PR-07/08 | Preserve method/input versions, runner capture and event-driven wakeups | Orchestrator/timer cannot choose science or replace frozen model |
| DEV-PR-09/10 | Query/recovery/observer safe context and isolation | Observer cannot become Research MAIN or scientific checker |
| DEV-PR-18 | Scoped product integration and optional independently approved behavioral evaluation | No claims about solving open problems from synthetic tests |

Keep **all** original mandatory Roadmap edges unchanged: 04→05; 02/05→06; 02/06→07; 04/05→11; 07/10/11→12; 05/09/12→13. None of these packages is authorized by this PR.

### Relationship to the earlier Library proposals and audit economy

The 2026-10-13 personal Library DEV04/11/12 suggestions were `PROPOSED / NOT AUTHORIZED`. The paired examples here adopt only **in-scope user-confirmed Research MAIN behavior**, with traceability to current K/O/S/GUIDE; they do **not** ratify the old proposal collection, a new independent review layer, a novel proof gate or a backend. Keep legitimate positive cases alongside refusals. Valid source scope and independent review may be reused; recheck only materially affected assumptions, quantifiers, witnesses, dependencies or global joins. A documented nonblocking MINOR does not automatically trigger a total re-audit. Stop when the authorized scope's checks and substantive findings are resolved.

**This documentation PR's acceptance only:** six-file diff; RMAIN-REQ-01–12 / RMAIN-MR01–10 coverage; correct references and privacy; unchanged 58+46/ADR/Roadmap; actual GitHub head/CI and independent document review. No runtime model calls, research evaluations, software release or paid usage allowed. Merge requires Development MAIN's scoped acceptance and distinct user authorization; before merge the user may close the PR, after merge use a reviewed revert rather than rewriting scientific evidence/history.
