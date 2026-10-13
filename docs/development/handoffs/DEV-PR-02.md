# DEV-PR-02 — Post-merge Development MAIN handoff

**Handoff source baseline:** `main@e1cb2dd76d9b5f8651750d6bd89d0b44819b6515` (verified GitHub 2026-10-13).  
**Package:** DEV-PR-02 — Ports, versioned immutable DTOs, capability negotiation, explicit error contracts and Fake contract tests.  
**Code state:** `IMPLEMENTED / TESTED / REVIEWED / MAIN ACCEPTED / GITHUB MERGED`.  
**Archival status:** this handoff requires its own documentation PR review/authorized merge. Do not infer `HANDOFF COMPLETE` or a new work-package grant from the existence of this document.

## 1. Exact provenance and accepted boundary

| Item | GitHub identity |
|---|---|
| Software PR | [#4](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/4) — merged 2026-10-13T10:06:46Z by user |
| Original base `main` | `efd2be4e93ca8f1ee9f6a03fa53df6a1f008c8fb` |
| Accepted development HEAD | `bdc698873999d3fc1773e76588339276ddc581ca` |
| Accepted/merged Git tree | `9dc07cf45cb02ba31e047f266380be85717a64f2` |
| Merge commit | `e1cb2dd76d9b5f8651750d6bd89d0b44819b6515` |
| Merge parents | original base, then accepted development HEAD |
| Final PR change set | 36 added paths, 4 development commits; R2 fix changed eleven paths |
| Frozen legacy tree | `research_studio/`: `f49a0b4e51d9a9602f82d7dc9fdf33a3e563b7da` |

The product PR did not modify the original `research_studio` code, historical scientific evidence schemas, MAIN/Goal, budget or CLI default behavior. Git tree identity shows the source reviewed in R3 is the source merged into `main`. It does not constitute full runtime testing.

## 2. Independent review and formal acceptance

- [Original full independent R3 report](../reviews/DEV-PR-02-INDEPENDENT-RE-REVIEW-R3.md), archived **byte-exactly** from user Library: 36,830 UTF-8 bytes, SHA-256 `272d4bab9bf5a62e003ed7cc1ca349f21716db1ae9c509db06097969caf82e88`. Frozen at `bdc698873999d3fc1773e76588339276ddc581ca`; verdict `APPROVE_FOR_MAIN_ACCEPTANCE`. Report's pre-merge PR-state descriptions are preserved as historical text and must not be edited.
- [Separate Development MAIN acceptance archive](../DEV-PR-02-MAIN-ACCEPTANCE.md) records `MAIN ACCEPTED` for precisely the R3 source and scoped contract deliverable; it is not a native submitted GitHub PR Review.
- Four initial MAJOR findings `REV02-WIRE-01`, `REV02-EVENT-01`, `REV02-UNKNOWN-01`, `REV02-CI-01`: all independently CLOSED. Documentation correction `REV02-DOC-01`: CLOSED.
- **`REV02-HELPER-01` is a non-blocking accepted MINOR, not independently closed.** New handoff helpers' source was absent from R3 evidence; no independent normal/`-O` tests ran. They must not be sole integrity gates. The original developer/local deliverer must provide implementation/support files if the tools become needed; verify these specific helpers then, without reopening all DEV-PR-02.
- The Chat independent R3 report is distinct from GitHub-native Review submission. Do not invent the latter.

## 3. Exact CI, artifact, and NOT_EXECUTED boundary

| Check | Run/job | Result |
|---|---|---|
| Python 3.11 DEV02 | [38367753519 / 115196874290](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38367753519/job/115196874290) | 119/119 PASS |
| Python 3.13 DEV02 | [38367753519 / 115196874368](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38367753519/job/115196874368) | 119/119 PASS |
| DEV01 regression | [38367753326](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38367753326) | 48/48 PASS |
| Phase 0 regression | [38367753356](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38367753356) | 6/6 PASS |

Original matching artifact IDs/digests: `11797304019` / `e9146b5835fcb70047ca991df80fb45f271c571d8b7cbbbbecb3b402e2642479`; `11796649547` / `8ec21e5afcfb582d3cfc1820a2563e71d81f42efa6093587f3612087894bb9d8`; `11796719438` / `350d1182c0993426e3099e43d326b31d64139c825f2ab19fe4c38e74720d33b5`. Phase 0 produced no ZIP. Actual merge SHA has **no separately confirmed post-merge CI**; do not relabel PR-head runs.

DEV-PR-02 passed bounded synthetic/offline contracts only. No real Store/Code​​x/Provider adapters, product research jobs, model accounting, authorization/fencing, crash-recovery, OS sandbox, original full product suite, migration or entire 58+46 future acceptance matrix have been validated: `NOT_EXECUTED`. Developer/test receipt `count=null, NOT_MEASURED` does not assert actual zero model calls.

## 4. Stable contract consumers and explicit deferrals

- **DEV-PR-03:** inherit `pmrh.ports` read-only `EvidenceRepository` / `EventRepository`, `ReadBoundary`, `EventCursor/GAP`, `ExecutionObservation`, `StateAxes`, and typed errors when needed for pure queries. Historical `host_pool.status()` has side effects; establish strictly read-only `read_status` versus separately authorized `reconcile_pool`. Favor the smallest working query slice; do **not** implement/store-loop, Runner or broad UI migration. The dependencies are DEV-PR-01 plus interface alignment with merged DEV-PR-02. **DEV-PR-03 NOT AUTHORIZED to start.**
- **DEV-PR-04:** inherit immutable/versioned DTO boundary and science-vs-execution separation; extract only designated pure scientific rules while preserving exact support, scope and review semantics. Requires its own explicit authorization.
- **DEV-PR-05:** implement actual journal/blob repository + UnitOfWork semantics; a Fake in-memory transaction is not durable or atomic across ledgers.
- **DEV-PR-06:** implement authenticated policy, owner fencing, human grant/budget and outbox/inbox; `OperationPermit` DTO alone is never authority.
- **DEV-PR-07:** implement actual Codex Runner/Provider mapping, capability receipt and original input/capture/UNKNOWN semantics; managed turn != one provider inference.

Original user authorization and ADR-0002 remain binding; an implementation detail or a Fake test must not confer scientific checked status or resume PAUSED research. New work packages require separate grant. Rollbacks must be separately reviewed software reverts, never erasure of scientific journal or research status.

## 5. Transfer to project-wide MAIN: management direction and proposed mathematics acceptance

On 2026-10-13 the user stated an enduring **management direction**: meet essential safety/scientific acceptance with the *lowest reasonable complexity, least duplicate work and maintenance cost*. Incoming project MAIN should prioritize near-term headless Codex-first synthetic MVP, justify new abstractions by immediate consumers, reuse existing code/evidence, stop after scoped gates pass, accept explicitly dispositioned nonblocking MINORs, target changed/dependent surfaces in review, verify actual Website/local Codex/CI capabilities before development, and escalate substantial overruns. **This direction does not relax scientific support, permission, independent review, PAUSED/UNKNOWN, or existing approved ADR/ROADMAP dependencies.**

Separate Library discussion `PMRH Development/PMRH_AI_Math_Conversation_Record_2026-10-13.md` §§4–6 proposed targeted acceptance clarifications, retained as **`PROPOSED / NOT AUTHORIZED FOR IMPLEMENTATION`**:

| Future package | Proposed clarification; never retroactive DEV-PR-02 gate | Existing case mapping |
|---|---|---|
| DEV-PR-04 | Exact scientific support, reviewer scope, cyclic dependencies and invalidation; unaffected qualified evidence remains reusable | K03, O05, prior domain regressions |
| DEV-PR-11 | Precise conditions, quantifiers, parameter-dependence, AND/OR and common witnesses; revoked support != proof of falsehood | K01–K04, applicable GUIDE:K |
| DEV-PR-12 | MAIN concrete research gaps, actual input delivery, worker slow/fast/attempt linkage, valid no-progress/empty-delta outcomes; dependency-scoped re-review | K05, K07, S03/S04 and applicable GUIDE |

Pair useful negative tests with legitimate-positive continuation. Do not add mandatory Lean, extra reviewer/summarizer agents, fixed research chains or live paid model experiments. **No new acceptance addendum has been approved, merged or authorized for implementation.** User confirmation is required before submitting a *single small future governance documentation PR* to version these clarifications. The automatic prompt-generator inheritance mechanism is `NOT VERIFIED`; successor MAIN must explicitly read then-applicable approved sources and never elevate this proposal to authority.

## 6. Rollover gate

Before DEV-PR-03, newly appointed Development MAIN must fetch current GitHub `main`, active ADRs, ROADMAP, PROJECT-STATE, operating protocol and handoff; confirm archive doc PR status and no concurrent modifications; freeze source/interface ownership and minimal test plan; ask user for **separate explicit DEV-PR-03 authorization**.

No product changes, concurrent DEV-PR-03 work or unapproved acceptance additions occur as part of this documentation handoff. Completion of this docs PR plus live merge check is needed before declaring `HANDOFF COMPLETE`.
