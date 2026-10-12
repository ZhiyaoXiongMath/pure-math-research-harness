# PMRH development-agent contract (repository-wide)

**Scope.** This repository is the successor to Pure Math Research Studio, a domain-specific, evidence-constrained multi-agent pure-mathematics harness. This file directs software-development agents only. It is **not** an operating-system ACL, a sandbox, a grant to access research projects, or authority to run model inference.

## Authority and precedence

Resolve decisions by (1) current explicit user authorization and formal project decisions, (2) verified original repository facts and source evidence, (3) subsequently approved architecture decision records (ADRs), (4) the specific authorized development PR contract. When an authority conflicts with a factual invariant or a security requirement, disclose the conflict and stop the affected change; do not quietly weaken scientific semantics. Unapproved draft ADRs are not binding implementation evidence.

## Non-negotiable preservation rules

- Preserve TRH P0–P14 and FDH D0–D5 responsibilities, original target/D0 constraints, per-instance **single logical MAIN**, independent mathematics and scope-limited acceptance.
- Keep the six immutable native scientific record types (Context, Statement, Argument, Example, SourceEvidence, Assessment), precise provenance, exact assumptions, proof support, reviewer independence, scope qualifications, and invalidation semantics.
- Treat Knowledge Module, Transition, Research Map, Frontier/Probe, ReaderProfile and RefinementBinding as proposed first-class *fast-math* objects grounded by detailed *slow-math* evidence. A summary, model output, valid JSON or passing software test is **never** proof of a mathematical claim.
- Keep human authorization, budgets, PAUSED, UNKNOWN, exact raw invocation/capture evidence, conservative crash recovery, and single-MAIN ownership checks. Never automatically retry an UNKNOWN external request.
- Separate mathematical domain policy, application control, orchestration engine, AgentRunner and ModelProvider. Do not treat an SDK or framework checkpoint as scientific authority or human consent.
- Target Codex-first headless operation, with no self-built Web UI **only after** all UI-hosted duties have safe functional equivalents. Do not remove existing UI, evidence, or report services prematurely.
- Observer/advisor sessions may inspect authorized snapshots and offer proposals; they cannot control MAIN, increase budgets, write canonical scientific evidence or become HUMAN guidance without authenticated human approval.

## Current Development MAIN and evidence bootstrap

Before any new package, the Development MAIN reads [versioned PROJECT-STATE](docs/development/PROJECT-STATE.md), [MAIN-OPERATING-PROTOCOL](docs/development/MAIN-OPERATING-PROTOCOL.md), the most recently completed Handoff relevant to the current work package (first example: [DEV-PR-01](docs/development/handoffs/DEV-PR-01.md)), all effective ADRs, ROADMAP and the acceptance baseline. Fetch live GitHub `main`/PR/head/merge/reviews/CI at the start of the term. When live GitHub conflicts with the versioned state, **report the difference**; primary GitHub records determine observed commit/PR/CI, but do **not** grant human authorization.

Default one separately appointed Development MAIN per planned DEV-PR. It differs from the scientific per-instance Research MAIN. Developers implement; independent Review Chat reviews exact head and evidence; Development MAIN alone makes the scoped `MAIN ACCEPTED` decision; GitHub `MERGED` is separately verified. A new DEV-PR requires new **explicit user authorization**, never inherited from a state file or handoff. Parallel work must first assign files/contracts, frozen baselines and one architecture conflict arbiter. Post-merge reconfirm `main` and hand off before a successor MAIN acts.

## Phase 0-specific historical restrictions (not a universal development gate)

For Phase 0 only, allowed: static source reading, documentation, packaging identity, inert `pmrh --help/--version`, isolated offline tests, and a reviewable bootstrap PR. Do not execute old research entrypoints, `scripts/test-runner.py`, `doctor`, native builds, the existing self-hosted/browser workflow, paid model/API calls or access private research workspaces. Do not rewrite original Git history or modify the original repository. Never force push, auto-merge, or self-approve your own delivery.

The Phase 0 `pmrh` CLI was intentionally **inert**; the old `research_studio` Python modules and legacy console scripts remain for traceability only and have **not** been certified as inert. Source/module relocation, runtime services, observer access and model interfaces require separate authorized development PRs.

## PR and evidence protocol

Use `DEV-PR-01` through `DEV-PR-18` for **planned software work**, not actual GitHub PR numbers. `TRH-P01` is a mathematical stage; `FDH-D01` is a discovery stage; neither is a software PR. Record statuses precisely: `PLANNED`, `IMPLEMENTED`, `TESTED`, `REVIEWED`, `ACCEPTED`. Never elevate a status without a matching artifact/evidence receipt. Mark all unexecuted checks `NOT_EXECUTED` (never PASS).

Every actual PR records base/head SHA, changed paths, preserved and changed behaviors, local and GitHub tests with exact run links, work not tested, commands/subprocesses/network/write scope, risks, security and rollback. Require independent Review Chat evidence and a separate Development MAIN decision; `REVIEWED`, `MAIN ACCEPTED` and GitHub `MERGED` are distinct. After an authorized merge, verify real `main` and preserve a Handoff. Never merge on the developer's own initiative.

Reference evidence: [audit package](docs/reference/PMRS-Next_Phase1/README.md), [architecture invariants](docs/architecture/ADR-0002-constraints.md), and [development roadmap](docs/development/ROADMAP.md).
