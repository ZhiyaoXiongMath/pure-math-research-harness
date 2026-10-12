# PMRH development project state — versioned evidence snapshot

**Checked:** 2026-10-12 (GitHub Connector, UTC timestamps below).  
**Verified main baseline:** `5d1b34d27bfbc171b2c5041973db8e8c1406a4b1`.  
**Repository:** [pure-math-research-harness](https://github.com/ZhiyaoXiongMath/pure-math-research-harness).  
**Management cycle:** GOV-01, expressly authorized *governance-documentation-only* work. A GOV-01 PR number, this document's own final SHA and any GOV-01 acceptance are deliberately not presumed inside this pre-commit snapshot.

> This file is a **versioned management state and evidence index**. It is NOT a live GitHub status mirror, a human authorization token, or scientific authority. A newly appointed Development MAIN must read current GitHub refs, PRs, reviews, merge records and CI, compare them with this snapshot, and report discrepancies. For observed commit/PR/CI facts, original GitHub records prevail; for authorization and acceptance, the relevant explicit human decisions are separately required.

## 1. Phase 0 and DEV-PR-01

| Cycle | Formal decision and evidence | GitHub identity |
|---|---|---|
| Phase 0 / repository bootstrap | Development MAIN formally accepted Phase 0, including closure of GIT-04 with bounded independent operator attestation: [acceptance](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/1#issuecomment-6120454287), [post-merge check](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/1#issuecomment-6120473063) | [PR #1](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/1): base `e4de0210f9985224e030ac4cfd2f7e2904005b37`; head `801bcf1a48d414a3a4ffecc293ae96587d32a9a6`; merge `977e866d64bba5cf7b5549f17a3d4b5599a4c20a`, 2026-10-12T08:20:01Z; `MERGED` |
| DEV-PR-01 / AST dependency and synthetic offline baseline | Earlier independent review froze `419a180fdf4b114691e8e44c8bf955e10a410970` and returned `REQUEST_CHANGES` (4 MAJOR, 2 MINOR). Supplied final reviewer *metadata* identifies final verdict `APPROVE_FOR_MAIN_ACCEPTANCE` and prior Development MAIN reported `ACCEPTED`. **Original final report body and independently linkable MAIN acceptance record unavailable in the current archive; no native GitHub submitted Review found.** [Provenance gap](reviews/DEV-PR-01-INDEPENDENT-RE-REVIEW.md) | [PR #2](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/2): base `977e866d64bba5cf7b5549f17a3d4b5599a4c20a`; final head `f8f93e962100010489946f4d82e302ea187c9874`; merge `5d1b34d27bfbc171b2c5041973db8e8c1406a4b1`, 2026-10-12T11:32:08Z; `MERGED` |

The DEV-PR-01 merge has parents Phase 0 merge `977e866d...` and accepted-for-merge development head `f8f93e962...`, with source tree `5681becd4810657210643d99928f5f663c9f9760` unchanged by merger. The GitHub `MERGED` fact is **not itself evidence of a submitted `REVIEWED` or `MAIN ACCEPTED` record**. Historical developer/ADR descriptions saying “acceptance pending” reflect earlier checkpoints, not today's verified merge.

### Exact test, PR, and audit pointers

- [Phase 0 Actions 38210420301](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38210420301): `completed/success` at head `801bcf1a...`, 6 Phase 0 smoke/static tests.
- [DEV-PR-01 Actions 38234570618](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38234570618): `completed/success` at final head `f8f93e962...`, job `114761973046`, **48/48 synthetic tests**, required artifact verifier/upload steps succeeded.
- [Phase 0 regression Actions 38234570610](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38234570610): `completed/success` at the **same DEV-PR-01 head**, job `114761972816`, **6/6 regressions**.
- [Final Actions artifact 11739533909](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38234570618/artifacts/11739533909): AST JSON, architecture Markdown, raw unittest log and receipt JSON. Developer-recorded archive SHA-256: `f779fb2ee83f27e9e57b4cb865e4d703a7f1c3ea720c2475a41c532f5ad12145`. This is **not** the independent reviewer report.
- [Six findings and developer remediation](DEV-PR-01-INDEPENDENT-REVIEW-FINDINGS.md), [source/architecture/test baseline](DEV-PR-01-BASELINE.md), [handoff](handoffs/DEV-PR-01.md), [Phase 0 provenance](PHASE0-PROVENANCE.md).

## 2. Current governance and future package status

The [ROADMAP](ROADMAP.md) freezes 18 planned IDs and their dependency graph, not real-time progress. Phase 0 was `ACCEPTED / MERGED` with a durable GitHub comment trail. DEV-PR-01 is `IMPLEMENTED / TESTED / MERGED` with final-review recommendation and MAIN acceptance **reported in preceding management materials but not archivally reproducible here**; the `MERGED` claim is independently confirmed. GOV-01 is **USER-AUTHORIZED FOR DOCS ONLY**, not self-reviewed, accepted or merged.

`DEV-PR-02` through `DEV-PR-18` remain planning packages without a GOV-01 grant for implementation, test execution, review or merger. **DEV-PR-02 and DEV-PR-03 are NOT authorized to start.** No parallel work is implicitly authorized.

## 3. Effective ADR and acceptance contracts

- [ADR-0001 — package naming](../architecture/ADR-0001-naming.md): Python package/CLI `pmrh`, distribution `pure-math-research-harness`, original `research_studio` source maintained.
- [ADR-0002 — mathematical and architectural invariants](../architecture/ADR-0002-constraints.md): TRH/FDH original Goal/D0, one logical Research MAIN per instance, six immutable scientific evidence records, scoped independent proof review, fast/slow mathematical binding, human budgets/PAUSED/UNKNOWN, conservative recovery and clean domain/orchestrator/runner/provider boundaries. No premature removal of UI.
- [ACCEPTANCE-BASELINE](ACCEPTANCE-BASELINE.md): **58 new + 46 inherited future product tests remain `NOT_EXECUTED`**. They are not the DEV-PR-01 synthetic tests or Phase 0 regressions.
- [MAIN-OPERATING-PROTOCOL](MAIN-OPERATING-PROTOCOL.md): Development MAIN cycle, role separation, review and handoff, authorization limits.

## 4. Accepted scope limits, open evidence and NOT_EXECUTED

The DEV-PR-01 Python-level guards are **not an OS sandbox**: preexisting hardlinks, native syscalls, inherited file descriptors, host mounts and hostile interpreters remain outside guarantee. Its AST rules cover supported static patterns, not arbitrary computed imports/reflection/`exec`. The 442 provisional legacy migration edges and four separately named couplings are *not* 446 confirmed new-layer violations. Model/API usage is `NOT_MEASURED` (count `null`), **not measured zero**.

**Evidence gap:** the unchanged complete final independent re-review and durable independent pointer to the Development MAIN `ACCEPTED` decision for DEV-PR-01 are unavailable; record their absence explicitly rather than fabricate a report. [Review placeholder](reviews/DEV-PR-01-INDEPENDENT-RE-REVIEW.md). Phase 0's local migration operation/secret-scan evidence was accepted with documented operator-attestation limits, not reproduced by GOV-01.

**Unexecuted future checks:** complete legacy suite/test runner, native Codex and Research MAIN/Goal, OS sandbox and real project path-isolation tests, actual provider metering, browser/PDF, Ubuntu 26.04 product gate, scientific migration, and the 58+46 product acceptance cases.

## 5. Next candidates, dependencies, and authorization

**Candidate DEV-PR-02:** ports, immutable DTOs and explicit error contracts; depends on DEV-PR-01 import and safety baseline. **Candidate DEV-PR-03:** pure read-only queries vs reconciliation; depends on DEV-PR-01 and interface alignment with DEV-PR-02; historical `host_pool.status()` is not certified pure. See [handoff](handoffs/DEV-PR-01.md).

These are **unstarted candidates**. Before either, the next Development MAIN must independently re-check current `main`/PRs/CI, report any mismatch, read active ADRs and handoffs, resolve ownership and architectural conflicts, and obtain **new explicit user authorization**. Nothing in this state index, roadmap or prior PR transfers that authority.
