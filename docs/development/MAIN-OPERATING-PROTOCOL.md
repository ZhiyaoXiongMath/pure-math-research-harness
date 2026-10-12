# PMRH — Development MAIN operating protocol

**Scope:** Software development management, independent review, acceptance and handoff. **Development MAIN is not the per-instance TRH/FDH Research MAIN** and gains no scientific authority, project access, budget or permission to invoke models.

## 1. Roles, appointments and scope

**Default: one independently appointed Development MAIN per planned DEV-PR work-package cycle.** A separately authorized documentation-only package such as GOV-01 follows the same guardrails. Development MAIN freezes the work boundary and `main` baseline, coordinates interfaces/assignments, commissions truly independent review, manages remediation and re-review, makes a separately documented MAIN acceptance decision when empowered, coordinates authorized merger, and checks actual post-merge `main` and handoff.

**Development Chat** implements and tests the explicitly authorized package, keeps one scoped branch and a reviewable **Open** PR with exact commits and CI evidence. It **must not** accept its own work, independently review itself, merge, perform unapproved tasks or expand into the next DEV-PR.

**Independent Review Chat** independently reads frozen, actual source code and GitHub PR diff, artifacts, CI/negative test receipts, and relevant invariants. It documents findings and issues `APPROVE_FOR_MAIN_ACCEPTANCE`, `REQUEST_CHANGES` or `INCONCLUSIVE` for a named SHA. Its recommendation is **not** a Development MAIN acceptance or a GitHub merger.

**Research MAIN** controls mathematical decision-making within exactly one TRH/FDH research instance, under independent scientific authorization/evidence semantics. Development managers/reviewers are never additional Research MAINs.

## 2. Distinct status and evidence

| Status | Meaning | Required distinction |
|---|---|---|
| `PLANNED` | Roadmap contract and dependency only | No execution permission |
| `AUTHORIZED` | The user explicitly approved this exact new work package and constraints | Cannot be inherited from PROJECT-STATE/handoff |
| `IMPLEMENTED` | Named source changes committed | Does not prove tested |
| `TESTED` | Defined test claims with source SHA, commands, environment, raw logs/CI URLs | Failures and exclusions preserved; not proof of math |
| `REVIEWED` | Independent examination of a frozen head and evidence, findings and verdict | Review recommendation ≠ MAIN acceptance |
| `MAIN ACCEPTED` | Development MAIN separately approved the scoped, reviewed delivery | Not the same as GitHub merged; preserve human decision provenance |
| `GITHUB MERGED` | GitHub PR merged into base, with actual SHA and parents | Merge ≠ independent review or authorization |
| `HANDOFF COMPLETE` | New main checked and evidence/risk/next-cycle transfer recorded | Outgoing MAIN stops new PR initiatives |

`BLOCKED`, `REQUEST_CHANGES`, `INCONCLUSIVE` and `NOT_EXECUTED` do not mean PASS. A changed code head requires targeted **re-review**; historical failed CI cannot be erased by later success. Usual gate order: user-authorized scope → implemented → tested → independent reviewed → MAIN accepted → separately permitted GitHub merge → verified handoff. The system records each gate without collapsing states.

## 3. Launching a new Development MAIN

1. Read [AGENTS](../../AGENTS.md), [CONTRIBUTING](../../CONTRIBUTING.md), [PROJECT-STATE](PROJECT-STATE.md), [ROADMAP](ROADMAP.md), [ACCEPTANCE-BASELINE](ACCEPTANCE-BASELINE.md), all effective ADRs under [architecture](../architecture/ADR-0001-naming.md) (including [ADR-0002](../architecture/ADR-0002-constraints.md)) and the most recently completed Handoff relevant to the current task (first concrete example: [DEV-PR-01](handoffs/DEV-PR-01.md)); read additional earlier handoffs when their contracts are still dependencies.
2. Query **live GitHub** for `refs/heads/main` and SHA, actual open/merged PR base/head, commits/parents, review submissions and discussion, workflow-run source SHA, job conclusions and attached artifacts. Reconcile against the versioned snapshot. **Report conflicting facts** explicitly, with both versions; for actual commit/PR/CI, original GitHub records prevail. `PROJECT-STATE` is neither a live API nor human authorization.
3. Obtain the **user's explicit, separate authorization** for the next DEV-PR before branch creation, code changes, tests beyond its scope or PR submission. The roadmap position and a previous MAIN's handoff **do not grant** approval. Ensure dependencies and architectural ADRs are respected.
4. Freeze the base SHA, owned files/interfaces and DTO contracts, accepted architectural exceptions, test and independent-review gates, forbidden execution, rollover policy, rollback and the Development MAIN responsible for resolving cross-package conflict.

If GitHub records are inaccessible or contradictory, declare `BLOCKED` or `INCONCLUSIVE` for the affected decision; never guess the source SHA or reinterpret a successful merge as evidence of a review.

## 4. Scoped development, independent review and remediation

The Development Chat records real base/head SHA, modified paths, tests and raw receipts, pass/fail boundaries, CI links, model/network/process use (with `NOT_MEASURED` rather than invented zero), preserved constraints, excluded checks and rollback. It may open a PR, never push directly to `main` or enable auto-merge.

An Independent Review Chat separately examines the code at the final head, checks the architecture and negative/positive tests, reviews actual Actions jobs and reviewer exposure, records every `BLOCKER/MAJOR/MINOR` finding with reproducible evidence, and gives an explicit verdict. The Development MAIN returns changes to the **same PR** where feasible; developer fixes do not self-close review. Review of an older head is not silently reused after significant fixes.

Only the Development MAIN can issue a formal `MAIN ACCEPTED` management decision after assessing the independent review, unresolved limitations and scope. It must reference frozen head and supporting evidence. A green workflow or `APPROVE_FOR_MAIN_ACCEPTANCE` verdict by itself is insufficient. Actual merge needs applicable explicit authority; developers may never self-merge. **Every development PR stays Open during independent review and until applicable MAIN acceptance and distinct merge authorization; a Development Chat may never self-merge or enable auto-merge.**

## 5. GitHub merge verification and Handoff

After an authorized merger, freshly query PR merge metadata, merge commit and its parents, `main` ref, changed paths, final source tree and CI trigger (PR head, temporary merge ref, or merged `main`). **Do not claim a merge commit has its own CI pass when only the PR head ran.** Preserve failed run and independent review sources.

Produce or update `docs/development/handoffs/<WORK-PACKAGE>.md` with accepted scope, exact developer head and merge SHA, CI URLs/artifacts and review findings, accepted risks, future `NOT_EXECUTED` items, architectural API inheritance and next-cycle **authorization status**. Update [PROJECT-STATE](PROJECT-STATE.md) as a separate versioned evidence snapshot rather than attempting to write a document's own final commit SHA. Transfer management to the next appointed MAIN; **the outgoing MAIN does not initiate or advance new PRs after handoff completion**, absent a new appointment.

## 6. Parallel package exception

Sequential Development MAIN stewardship is the default. Any concurrent development must be authorized and specified *before coding*: (i) which owner controls each file and cross-package interface/contract, (ii) exact frozen base branch/SHA and permissible update/rebase policy, (iii) dependency and merge order, (iv) one **named architectural conflict coordinator** with arbitration authority, (v) independent review and tests for each PR. Without these five decisions, **parallelism is not permitted**. Parallel software management never creates a second scientific Research MAIN.

## 7. Source precedence and historical states

New explicit human instructions and formal decisions govern authorization and scope; original repository code, Git commits, GitHub PR/CI are factual evidence; approved ADRs govern architecture. Snapshot conflicts are logged, not silently “repaired.” Historical Phase 0 and DEV-PR-01 documents contain point-in-time statements; preserve them while referring to [PROJECT-STATE](PROJECT-STATE.md) for the versioned index and to GitHub for today's real state. The 58+46 future product acceptance entries remain `NOT_EXECUTED` until separately demonstrated and accepted.
