# Program-control amendment — 2026-10-21

[PROGRAM-CONTROL](PROGRAM-CONTROL.md) records **HUMAN-PROGRAM-GRANT-20261021**, effective immediately from the explicit human decision. Governance review/merge records the grant rather than activating it. This amendment reconciles §§1–3, 5–8 below and ROADMAP's repeated-startup-grant wording only for GOV-02, DEV06 closeout, DEV07–14 and DEV18 integrated acceptance/release-candidate preparation. The original text remains intact. A ledger or handoff grants nothing independently.

**Global control persists; package stewardship is bounded.** Global control may appoint and coordinate in-scope successors after verified dependencies/handoff and a package freeze without asking the human to repeat startup authorization. Each package still has its own Controller (Development MAIN), Developer and independent Reviewer. The outgoing Controller stops at handoff and cannot self-appoint successor work. Global control arbitrates architectural conflicts. Product implementation remains sequential unless an explicit parallel plan records file/interface ownership, exact bases, dependency/merge order, one arbiter and independent gates before coding.

**Freeze before implementation:** smallest useful deliverable and direct consumers; interfaces and owned files; exact baseline and dependencies; approved specification/ADR versions and exceptions; non-goals and forbidden execution; inherited acceptance IDs with positive/rejection cases; test/evidence/review/rollback plan; role ownership and handoff conditions. Reuse unaffected verified receipts within their exact scope; target re-review to changed assumptions, dependencies, interfaces and evidence. Stop repeated audit loops once scoped gates and substantive findings close, retaining documented nonblocking limitations.

**Actual role and isolation gates:** global gpt-6-astra/xhigh; package Controller gpt-6-astra/high; Developer and fresh independent Reviewer gpt-6-astra/xhigh. Before substantive source work verify actual runtime, thread, turn, model, effort, approval policy and effective ACL/network records. Developer writes are scoped; Reviewer source and packet are read-only with scratch-only writes. Task network is blocked. Test parent and child source/input write denial, outside-access denial, allowed scratch writes and network denial. Controller verifies the probe receipt and frozen packet in a second gate matching the actual turn. Prompt-only restrictions or a successful launch are insufficient. A mismatch or CLI/security rejection stops the task with the exact error preserved; no silent fallback, model change or security weakening. Record Controller host privileges separately; do not present them as task sandboxing. Keep actual private IDs, paths and logs outside public documents.

**Evidence acquisition:** global control/package Controller obtains fresh GitHub main/PR/head/merge/review/CI facts at package intake and after authorized merge, then freezes source evidence for isolated task roles. Network-blocked Developers/Reviewers use that packet and explicitly disclose no live fetch. Reconcile stale snapshots against primary facts without inferring human consent from GitHub.

**Distinct gates remain:** program grant in scope → appointment/freeze/dependencies → implementation and matching scoped tests → independent final-head recommendation → separate Controller MAIN decision → separate human merge decision → verified actual main/handoff. A changed head requires scoped re-review and an explicitly head-bound decision. Older product acceptance cannot silently attach to a later CI repair. Reviewer recommendation, native GitHub Review, MAIN ACCEPTED, GITHUB MERGED and HANDOFF COMPLETE remain distinct. No self-acceptance, force push or auto-merge. Do not write a document's own future SHA or external acceptance into its frozen content.

Current assignments are disjoint: GOV-02 owns six documentation paths on frozen main; DEV06 closeout records read-only final-head evidence; DEV07 global read-only interface/consumer preflight owns no product edits. The later DEV06 Controller supplement records ACCEPTED_SCOPED_PREMERGE / READY_FOR_USER_MERGE_DECISION; DEV07 implementation still awaits human DEV06 merge, verified handoff and its own package appointment/freeze, with that scoped acceptance remaining valid. See [snapshot](PROJECT-STATE.md) and [ledger](DEVELOPMENT-LEDGER.json) for unresolved evidence.

New/revised scope outside the grant, each PR merge, formal tag/Release, DEV15 experiment execution, DEV16 adoption/implementation and DEV17 tool development/actual migration need separate human decisions. The latter optional dispositions remain PENDING_HUMAN_DECISION, not invented adoption/rejection. No real research/projects, paid product-model calls, production activation, recovery or budget increase is granted. Development management is neither Research MAIN nor product-model authority; all ADR-0002 invariants and the unchanged 58+46 definitions survive.

## Historical content — original bytes retained below

The following text preserves its dated decisions and observations. Read current authorization and status through the amendment above; no missing historical evidence is repaired by this annotation.

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

## 8. Research MAIN specification intake and minimum-complexity governance (candidate addendum)

The *scientific* behavior of a per-instance Research MAIN belongs to the separate [Research MAIN product specification](../architecture/RESEARCH-MAIN-STRATEGY.md) and [04/11/12 acceptance map](ACCEPTANCE-ADDENDUM-04-11-12.md), **not** inside the Development MAIN management method. A document-only PR first requires independent review, separately recorded Development MAIN acceptance, and user-authorized merge; until then this added material is not effective.

For an authorized successor work package, preflight the available GitHub/tools/CI capabilities before promising a commit or validation, reconcile the effective text against live main and the current ADR, and freeze the smallest valuable **MVP**, its direct consumers, inherited acceptance IDs, positive/rejection examples, non-goals and bounded evidence plan. Reuse already verified unaffected software receipts and mathematically qualified support in their exact scope; do targeted re-review for changed assumptions, dependencies, proof directions, exposure or interfaces instead of automatically re-auditing unrelated material. Document genuinely nonblocking MINOR findings without concealing them; once scope-relevant gates and substantive findings close, stop repeated audit loops. None of these efficiency rules relaxes authorization, PAUSED/UNKNOWN, budget, scientific independence or raw-evidence preservation.

An approved *specification* does not authorize DEV-PR-04/11/12 implementation, a new Agent, Lean mandate, backend/runtime mutation or real-model scientific evaluation. A new explicit user grant is still required for each work package.

