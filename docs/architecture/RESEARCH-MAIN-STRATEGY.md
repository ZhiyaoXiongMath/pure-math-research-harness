# Research MAIN strategy — TRH / FDH

**Version:** 0.1.0 (2026-10-15)  
**Status:** CANDIDATE, NOT YET EFFECTIVE — pending independent documentation review, Development MAIN acceptance and user-authorized merge. Not a grant to implement DEV-PR-04/11/12, run research or alter a project.  
**Applies to:** the **single logical Research MAIN** of each TRH/FDH instance, not the software Development MAIN or the Survey writing controller.  
**Primary user source:** `Main-Agent-Design-Requirements.zh-CN.md` (v0.1, 2026-10-14), SHA-256 `8af8130f673f0abf1b6a47f6bd4fce986e0162f583da422481dce14183ec6cc9`. The user's design-philosophy and safe-rollout summaries explain intent. The private meeting transcript remains outside GitHub.  
**Authority and compatibility:** This is a behavior-level *refinement* of [ADR-0002](ADR-0002-constraints.md), the [original PMRS-Next development guide](../reference/PMRS-Next_Phase1/00-Reference-Development-Guide.zh-CN.md), [original implementation plan](../reference/PMRS-Next_Phase1/02-Implementation-Plan.zh-CN.md), and [TRH MAIN 4.2.2 method](../TRH-MAIN-METHOD-4.2.2.md). It neither changes the original TRH Goal/FDH D0 nor creates mathematical qualification authority. [Acceptance/work-package mapping](../development/ACCEPTANCE-ADDENDUM-04-11-12.md).

The requirements below are **RMAIN-REQ-01–12**, one-to-one with the user draft **R01–R12**. They avoid collision with the existing software acceptance R01–R03. Their implementation remains subject to future scoped authorization.

## Scientific control and two-layer loop

Research MAIN, not a technical scheduler, determines the research direction; the host validates control, authorization, budget, identities, scientific admissibility and recovery. Mathematical phases are responsibilities, **not a fixed P1→P14 / D1→D5 pipeline**. The **fast layer** contains precise reusable mechanisms, candidate routes and the most consequential unknown arrows; the **slow layer** contains precise mathematical statements, assumptions, arguments, counterexamples, sources and independent reviews. They refer to the same mathematical reality at different granularity; fast objects cannot approve themselves.

On a relevant event: preserve original target/D0 → read one versioned map and new/invalidated evidence → propose or revise an explicit mechanism chain → choose a discriminating unknown → authorize a bounded Worker task or wait → receive precise slow evidence and suggested fast revision → apply scoped review/admission and dependency updates → make a reasoned next decision. A pretty graph, a completed process, JSON validity or consensus is never a proof.

## RMAIN-REQ-01 — Small useful initial skeleton (source R01)

MAIN's decision input must include the immutable TRH target or FDH D0 with permitted adjustment axes, exact assumptions, valid human guidance, callable related knowledge, current versioned map, accepted and invalidated increments, active tasks, permissions and budget. Check background knowledge that matters to the first decision, then expand research as gaps appear; do not require exhaustive literature coverage in advance. Declare human reader prerequisites through a `ReaderProfile`; changing explanation depth cannot change mathematical support.

## RMAIN-REQ-02 — Identifiable, versioned and callable knowledge (source R02)

The following are **semantic requirements**, not mandatory new databases, types or DTOs in DEV04:

| Fast object | Minimum mathematical content |
|---|---|
| `KnowledgeModule` | Obstacle solved, precise input hypotheses, output, core mechanism, limits, use in this project, provenance, qualification and open conditions |
| `Transition` | Start/end and actual mathematical direction, common background, connection mechanism, missing interface, test, support and status |
| `ResearchMap` | Original target, candidate routes, AND/OR obligations, common objects/parameters, gaps and revision reasons |
| `Frontier/Probe` | Decisive unknown, bounded investigation, possible outcomes and how each affects route choice |
| `RefinementBinding` | Exact upper-layer claim/arrow and lower-layer evidence, context, version, scope, open condition, review and invalidation dependency |
| `ReaderProfile` | Declared general/project-specific reading prerequisites and expansion depth, **never** proof qualification |

Split by reusable decision boundaries or independently failing mathematical interfaces, not by each algebraic line. Preserve stable identities and revision history using existing evidence/event/index services where adequate.

## RMAIN-REQ-03 — Dashed arrows, conditionality and applicability (source R03)

Represent separately (i) the mathematical relation—implication, equivalence (both directions), conditional implication, applicability, analogy/heuristic or open connection—and (ii) evidence state and version/scope. A conjectured **dashed arrow** remains OPEN even if both endpoint nodes are checked. A verified conditional theorem is not proof its condition holds for this project. Retain assumptions, quantifier order, shared witnesses, parameter dependence, constants, provenance, application obligations and exact review scope. Do not infer “checked” from a source citation, diagram color or model confidence.

## RMAIN-REQ-04 — Compositional reasoning and direction (source R04)

AND-premises must all hold in a compatible context; alternative OR routes are individually sufficient candidates and do not all have to succeed. Independently checked components do not automatically compose under mismatched witnesses, parameters or assumptions. Backward reasoning identifies **candidate sufficient requirements**, not a proved reversed implication or a mere necessary condition elevated to sufficiency. The explanatory reading order is distinct from proof dependencies. Circular support must have independent noncircular justification.

## RMAIN-REQ-05 — Forward/backward construction and framework transfer (source R05)

**Direct construction:** push from initial hypotheses toward intermediate mechanisms; search backward from the target for plausible sufficient outputs; locate unresolved joins, introduce new objects/quantities as needed, and mark unproved connections explicitly.

**Framework transfer:** reconstruct how a related solved problem works (its mathematical mechanism, not keywords), map donor objects, hypotheses, inputs/outputs and witnesses to this target, and identify the lost conditions or unproved transfer arrows. Propose a specific applicability/replacement probe. A donor's checked conclusion is not automatically checked here.

Either path may create a rough but testable map. MAIN need not know the final proof first; neither exploration style nor a new route is compulsory every round.

## RMAIN-REQ-06 — Consequential Worker tasks (source R06)

For each substantive dispatch state: the affected module/transition or explicitly unmapped frontier; why testing it could change the route decision; frozen mathematical input and exact missing claim; legitimate results and their consequences; return/stop/retry condition; exact references, isolation, scope and authorization. Proof, counterexample, conditional/weaker result, method obstacle, incomplete work or **no progress** are all legitimate outcomes. Workers may select technical methods inside their bounded responsibility. Budget/time exhaustion is not mathematical refutation.

## RMAIN-REQ-07 — MAIN does mathematical strategy (source R07)

MAIN compares mechanisms and assumptions, can perform short quantifier/dimension/model sanity checks and preliminary derivation sketches, and must inspect slow proofs or original sources when a crucial hypothesis, transfer, witness, support change or controversy demands it. Long proof attacks and new deductions intended as formal scientific premises need named tasks or native candidate Arguments and scoped review. Reuse verified mature tools within their exact applicability; do not require Lean or another Agent to re-prove every known theorem. Research MAIN is **not** merely a task administrator.

## RMAIN-REQ-08 — One attempt, three coordinated deliveries (source R08)

A Worker return from the same frozen attempt contains:

| Field | Scientific content |
|---|---|
| `slow_layer_result` | Precise proposition, proof/construction/calculation, sources, extra assumptions, failure locus and unfinished scope |
| `fast_layer_delta` | Proposed before/after changes to a module, transition or map; evidence/scope and effect on the next decision |
| `attempt_account` | What was actually done/not done, failure class, remaining gap and substantive basis needed to retry |

An honest **empty** fast delta is allowed and explained, not fabricated. Missing mandatory handoff components preserve the raw mathematical capture but are marked incomplete. The delta is a proposal pending qualification/admission, **not** a direct permission to change control, run a model or claim proof. Later materials cannot be backdated into an earlier task's delivered inputs.

## RMAIN-REQ-09 — Local failure drives diagnosis and justified structure change (source R09)

| Evidence/outcome | Correct interpretation |
|---|---|
| Independently qualified counterexample meeting original hypotheses and violating original conclusion | May refute the **original** scoped TRH target |
| Counterexample to a stronger intermediate lemma, reduction or one conditional link | Revise *that* claim/route, re-evaluate original target; not automatically not-G |
| Failure of one particular method | Locate the missing mechanism; repair, add a condition, use another module, change route or reasonably stop |
| Weaker/conditional result | Keep its actual strength and an open promotion condition |
| No proof, no counterexample, unfinished mathematics | Unknown; no truth/falsity inference |
| Missing source, software/transport error or UNKNOWN | Material/execution issue; not mathematical failure |

MAIN may preserve the same promising route, search for a true original-target counterexample, insert intermediate objects, reconstruct a different framework, or wait. Record exact affected arrow, context, cause and **what would make a retry meaningfully different**. A failure of A⇢B in A⇢B⇢G is not automatically a refutation of G.

## RMAIN-REQ-10 — Scope, revision and independent review (source R10)

Accepted deltas record module/arrow revisions, the changed or unchanged strategic decision, why, and the next discriminating probe/wait. Withdrawn proof support makes only the dependent **qualification closure** open; it does not establish negation. Reuse unchanged, still-valid mathematical reviews, and re-review only materially affected assumptions, quantifiers, implication direction, interface or global stitching. Independent proof/counterexample review receives necessary allowed original evidence but is protected from contaminating prior verdicts and derived summaries; no blanket re-review for a display edit.

Even a visually complete path cannot deliver the target until critical arrows, joint assumptions, open duties and the required global checks are properly supported. Software tests, model votes and schema validity cannot grant mathematical checked status.

## RMAIN-REQ-11 — TRH versus FDH goals (source R11)

**TRH:** original proposition/assumptions remain fixed. Weaker results or changed proof frameworks are not proof of that target. Only an applicable and reviewed counterexample satisfying **all** original assumptions can refute it. Preserve existing P0–P14 obligations, P9/P12 independence and **P13 before P14**; continuing a round never secretly replaces the Goal.

**FDH:** with immutable D0 and only its authorized adjustment axes, compare candidate formulations, logical relationships, hypothesis cost and positive/negative/unknown evidence. “Unknown relation” is **not** “no implication”. Ordinary D5 synthesis is not formal D5 handoff: formal selection pauses for human choice. Adoption of an exact candidate by the user creates a **separate paused TRH**, which still needs its own startup permission. Never mutate the FDH Goal into the adopted TRH target.

## RMAIN-REQ-12 — Durable recovery, readable knowledge and minimal machinery (source R12)

Persist routes, supported/open arrows, failure reasons, changed prerequisites, why choices changed or stayed, and exact versions. Resume from original target/D0, last qualified map, outstanding increments, active attempts and failure memory; do not retry unchanged work by renaming it.

Readable overview: **original target → main callable modules → candidate routes → supported/conditional/open arrows → real recent change → next decisive test/reason → exact expandable slow evidence**. Reports and lecture-style details consume a **specific accepted knowledge snapshot**, disclose stale/unconsumed changes and do not independently create unsupported results. Necessary source research should first update the KB, then inform report generation. Reader ease does not alter proof status.

Use minimum sufficient complexity and existing evidence, events, indexes and reporting; new abstractions require identifiable immediate consumers. No mandatory Lean, graph database, embeddings, new Agent or recurrent polling; no fixed route-switch threshold or automatic whole-library re-review. When actual scoped acceptance and material issues are closed, **stop unnecessary repeated audits**.

## Explicitly undecided items

FDH candidate scoring (“meaningful/elegant”), new D0 adjustment axes, numerical route-switch thresholds, the cost/benefit of local Lean Transition checks, and a real open-problem evaluation benchmark have **not** been decided. Do not create new hard gates or arbitrary values for them. New paid model evaluation needs explicit separate authorization.

The [acceptance addendum](../development/ACCEPTANCE-ADDENDUM-04-11-12.md) maps original R01–R12 and MR01–MR10 to current K/O/S/GUIDE and future DEV04/11/12/13 responsibilities; its synthetic traces are behavior examples, not actual theorem or research-success evidence. This document may become an approved *future-development requirement* after proper review and user merge, **never** retroactive proof of implementation or a new research grant.
