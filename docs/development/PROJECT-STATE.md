# PMRH development project state — versioned evidence snapshot

**Checked:** 2026-10-14 (fresh GitHub API and Git clone; UTC evidence timestamps).  
**Verified main baseline:** `bd5c957798355296248e2c9fbc1ebdf63a1861eb` (post-DEV03 software merge, before this archival PR).  
**Repository:** [pure-math-research-harness](https://github.com/ZhiyaoXiongMath/pure-math-research-harness).  
**Management cycle:** DEV-PR-03 post-merge documentation archive under GOV-01 guardrails. The prior `e1cb2dd...` snapshot preceded PR #5's documentation merge `507ea4b...`; PR #6 is now merged. This snapshot does not predict this archival PR's final SHA or assert its review/merge/readback is complete.

> This file is a **versioned management state and evidence index**. It is NOT a live GitHub status mirror, a human authorization token, or scientific authority. A newly appointed Development MAIN must read current GitHub refs, PRs, reviews, merge records and CI, compare them with this snapshot, and report discrepancies. For observed commit/PR/CI facts, original GitHub records prevail; for authorization and acceptance, the relevant explicit human decisions are separately required.

## 1. Phase 0 and DEV-PR-01

| Cycle | Formal decision and evidence | GitHub identity |
|---|---|---|
| Phase 0 / repository bootstrap | Development MAIN formally accepted Phase 0, including closure of GIT-04 with bounded independent operator attestation: [acceptance](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/1#issuecomment-6120454287), [post-merge check](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/1#issuecomment-6120473063) | [PR #1](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/1): base `e4de0210f9985224e030ac4cfd2f7e2904005b37`; head `801bcf1a48d414a3a4ffecc293ae96587d32a9a6`; merge `977e866d64bba5cf7b5549f17a3d4b5599a4c20a`, 2026-10-12T08:20:01Z; `MERGED` |
| DEV-PR-01 / AST dependency and synthetic offline baseline | Earlier independent review froze `419a180fdf4b114691e8e44c8bf955e10a410970` and returned `REQUEST_CHANGES` (4 MAJOR, 2 MINOR). The complete [original independent re-review](reviews/DEV-PR-01-INDEPENDENT-RE-REVIEW.md) is now archived **verbatim** (16,855 UTF-8 bytes, SHA-256 `8d40e731b3101c122b8e58e77da62a96b0089bfc2075885e6b509c688c74c6c9`); its frozen head was `f8f93e962100010489946f4d82e302ea187c9874` and reviewer verdict `APPROVE_FOR_MAIN_ACCEPTANCE`. Prior Development MAIN `ACCEPTED` is reported, but a separately retrievable MAIN acceptance record was not found; no native submitted GitHub Review was found. | [PR #2](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/2): base `977e866d64bba5cf7b5549f17a3d4b5599a4c20a`; final head `f8f93e962100010489946f4d82e302ea187c9874`; merge `5d1b34d27bfbc171b2c5041973db8e8c1406a4b1`, 2026-10-12T11:32:08Z; `MERGED` |

The DEV-PR-01 merge has parents Phase 0 merge `977e866d...` and accepted-for-merge development head `f8f93e962...`, with source tree `5681becd4810657210643d99928f5f663c9f9760` unchanged by merger. The GitHub `MERGED` fact is **not itself evidence of a native GitHub Review or a separately recorded `MAIN ACCEPTED` decision**. The archived reviewer report is an independent Chat audit, **not** a GitHub Review submission. Historical developer/ADR descriptions saying “acceptance pending” reflect earlier checkpoints, not today's verified merge.

### Exact test, PR, and audit pointers

- [Phase 0 Actions 38210420301](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38210420301): `completed/success` at head `801bcf1a...`, 6 Phase 0 smoke/static tests.
- [DEV-PR-01 Actions 38234570618](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38234570618): `completed/success` at final head `f8f93e962...`, job `114761973046`, **48/48 synthetic tests**, required artifact verifier/upload steps succeeded.
- [Phase 0 regression Actions 38234570610](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38234570610): `completed/success` at the **same DEV-PR-01 head**, job `114761972816`, **6/6 regressions**.
- [Final Actions artifact 11739533909](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38234570618/artifacts/11739533909): AST JSON, architecture Markdown, raw unittest log and receipt JSON. Developer-recorded archive SHA-256: `f779fb2ee83f27e9e57b4cb865e4d703a7f1c3ea720c2475a41c532f5ad12145`. This is **not** the independent reviewer report.
- [Original independent re-review, unmodified](reviews/DEV-PR-01-INDEPENDENT-RE-REVIEW.md) (SHA-256 `8d40e731b3101c122b8e58e77da62a96b0089bfc2075885e6b509c688c74c6c9`); [six findings and developer remediation](DEV-PR-01-INDEPENDENT-REVIEW-FINDINGS.md), [source/architecture/test baseline](DEV-PR-01-BASELINE.md), [handoff](handoffs/DEV-PR-01.md), [Phase 0 provenance](PHASE0-PROVENANCE.md).

## 1A. GOV-01 and DEV-PR-02 — independently rechecked 2026-10-13

| Cycle | Review / acceptance distinction | Observed GitHub identity |
|---|---|---|
| GOV-01 | Governance docs/archival PR completed; the earlier "Open" note was a dated historical snapshot, not its present state. No native GitHub Review or separately linkable MAIN acceptance object was verified here; do not invent one. | [PR #3](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/3) **MERGED** as `efd2be4e93ca8f1ee9f6a03fa53df6a1f008c8fb` (2026-10-12T13:17:08Z). |
| DEV-PR-02 | `IMPLEMENTED / TESTED / REVIEWED / MAIN ACCEPTED / GITHUB MERGED` for bounded ports/DTO/error contracts. [Original R3 independent report](reviews/DEV-PR-02-INDEPENDENT-RE-REVIEW-R3.md) recommends `APPROVE_FOR_MAIN_ACCEPTANCE`; its authorship is an independent Chat audit, not a native submitted GitHub Review. Separate [MAIN acceptance archive](DEV-PR-02-MAIN-ACCEPTANCE.md) documents the decision and non-blocking risk. | [PR #4](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/4) **MERGED**, base `efd2be4e...`, final head `bdc698873999d3fc1773e76588339276ddc581ca`, merge `e1cb2dd76d9b5f8651750d6bd89d0b44819b6515` (2026-10-13T10:06:46Z), identical accepted/merge tree `9dc07cf45cb02ba31e047f266380be85717a64f2`. |

DEV-PR-02 exact source CI: [Python 3.11/3.13 run 38367753519](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38367753519) (119/119 each), [DEV-PR-01 regression 38367753326](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38367753326) (48/48), [Phase 0 regression 38367753356](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38367753356) (6/6). These tested the PR head or a temporary PR merge ref of the **identical tree**. No separate post-merge `main@e1cb2dd...` CI run is claimed.

R3 closed REV02-WIRE-01 / EVENT-01 / UNKNOWN-01 / CI-01 (4 MAJOR) and DOC-01 (MINOR); REV02-HELPER-01 remains **`INCONCLUSIVE / NOT_EXECUTED`** (independent helper implementation/optimized-mode test not obtained). MAIN **accepted this nonblocking MINOR** solely with a rule that unverified external handoff helpers must never be the single authority for critical integrity/merge decisions. The original local deliverer retains the responsibility to supply their implementations if future trusted use is proposed; targeted helper re-check only, no new general code gate. See [handoff](handoffs/DEV-PR-02.md) and [formal acceptance](DEV-PR-02-MAIN-ACCEPTANCE.md).

**Archive PR limitation:** presence of these draft document links on a PR branch does not mean the documentation PR was reviewed or merged. Its completion must be separately checked live before declaring `HANDOFF COMPLETE`.

## 1B. DEV-PR-03 — software merge independently checked 2026-10-14

[PR #6](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/6) is **IMPLEMENTED / TESTED / REVIEWED / MAIN ACCEPTED / GITHUB MERGED** for the bounded read-only query MVP. User merge: 2026-10-14T13:15:58Z. Accepted HEAD `c4ea8bc93b2018f30f04a5c5df7d1a8b1a653525`; actual merge/current baseline `bd5c957798355296248e2c9fbc1ebdf63a1861eb`; parents `507ea4baca2782ab0da13ab949bc4424fc707694`, then accepted HEAD; accepted/merge tree `7a079828c351af4dce6f645da6e5d53a44c75010`.

[MAIN acceptance](DEV-PR-03-MAIN-ACCEPTANCE.md), [original decision](records/DEV-PR-03-MAIN-ACCEPTANCE-ORIGINAL.txt), [Handoff](handoffs/DEV-PR-03.md), [evidence index](DEV-PR-03-EVIDENCE.json). Independent [General R1](reviews/DEV-PR-03-GENERAL-REVIEW-R1.md) / [Security R1](reviews/DEV-PR-03-SECURITY-REVIEW-R1.md) requested changes; one of two authorized remediation rounds closed both defects; [General R2](reviews/DEV-PR-03-GENERAL-REVIEW-R2.md) / [Security R2](reviews/DEV-PR-03-SECURITY-REVIEW-R2.md) APPROVE at accepted HEAD. All raw reports are byte-exact independent CLI audits, not GitHub-native submitted reviews.

Final PR CI: DEV03 38502114213 (36 each on 3.11/3.13), DEV02 38502114198 (119 each), DEV01 38502114175 (48), Phase 0 38502114254 (6). All passed with source/test/artifact identities verified; Phase 0 temporary merge has the accepted tree. No workflow was found for the actual merge SHA. New CLI confinement does not certify all legacy I/O. Bytecode must be disabled; OS atime excluded; project/pool non-atomic; future full product/research gates remain NOT_EXECUTED. See acceptance for the precise limits.

PR #5 is merged as `507ea4b...`, but its historical independent document-review body remains NOT_RETRIEVED. DEV03's separate independent baseline preflight and MAIN dependency acceptance do not retroactively create missing historical review/HANDOFF COMPLETE evidence. Inherited HELPER-01 remains accepted nonblocking, INCONCLUSIVE / NOT_EXECUTED, never sole authority.

## 2. Current execution gate

DEV03 software is accepted and user-merged. **This separate archive still requires independent documentation review, user merge and readback before HANDOFF COMPLETE.** Neither the software merge nor existence of these documents completes the Goal.

**DEV-PR-04 through DEV-PR-18 are NOT AUTHORIZED for product implementation by this cycle.** The user will propose new TRH/FDH Research MAIN design requirements; **assess their impact before DEV04 startup**. Their contents have not been supplied or approved here. Do not begin development, create new normative requirements, or dispatch DEV04 agents from this state file. Previous DEV04/11/12 mathematics additions remain PROPOSED / NOT AUTHORIZED.

## 3. Effective ADR and acceptance contracts

- [ADR-0001 — package naming](../architecture/ADR-0001-naming.md): Python package/CLI `pmrh`, distribution `pure-math-research-harness`, original `research_studio` source maintained.
- [ADR-0002 — mathematical and architectural invariants](../architecture/ADR-0002-constraints.md): TRH/FDH original Goal/D0, one logical Research MAIN per instance, six immutable scientific evidence records, scoped independent proof review, fast/slow mathematical binding, human budgets/PAUSED/UNKNOWN, conservative recovery and clean domain/orchestrator/runner/provider boundaries. No premature removal of UI.
- [ACCEPTANCE-BASELINE](ACCEPTANCE-BASELINE.md): **58 new + 46 inherited future product tests remain `NOT_EXECUTED`**. They are not the DEV-PR-01 synthetic tests or Phase 0 regressions.
- [MAIN-OPERATING-PROTOCOL](MAIN-OPERATING-PROTOCOL.md): Development MAIN cycle, role separation, review and handoff, authorization limits.

## 4. Accepted scope limits, open evidence and NOT_EXECUTED

The DEV-PR-01 Python-level guards are **not an OS sandbox**: preexisting hardlinks, native syscalls, inherited file descriptors, host mounts and hostile interpreters remain outside guarantee. Its AST rules cover supported static patterns, not arbitrary computed imports/reflection/`exec`. The 442 provisional legacy migration edges and four separately named couplings are *not* 446 confirmed new-layer violations. Model/API usage is `NOT_MEASURED` (count `null`), **not measured zero**.

**Independent re-review archive completed:** [full original Markdown](reviews/DEV-PR-01-INDEPENDENT-RE-REVIEW.md) was supplied by the user and copied without editing; SHA-256 `8d40e731b3101c122b8e58e77da62a96b0089bfc2075885e6b509c688c74c6c9`, 16,855 bytes, reviewed DEV-PR-01 head `f8f93e962...`, verdict `APPROVE_FOR_MAIN_ACCEPTANCE`. It was authored before PR #2 merged, so its historical `open` status remains intact. **Remaining evidence boundary:** this is a Chat independent audit, not a GitHub native submitted Review; no separately linkable GitHub MAIN acceptance record has been located. Do not infer such a record from the merge. Phase 0's local migration operation/secret-scan evidence was accepted with documented operator-attestation limits, not reproduced by GOV-01.

**Unexecuted future checks:** complete legacy suite/test runner, native Codex and Research MAIN/Goal, OS sandbox and real project path-isolation tests, actual provider metering, browser/PDF, Ubuntu 26.04 product gate, scientific migration, and the 58+46 product acceptance cases.

## 5. Next candidate, requirements and authorization

**DEV-PR-04 — mathematical domain kernel extraction (NOT AUTHORIZED)** remains the roadmap candidate dependent on DEV02. The user explicitly stated on 2026-10-14 that new **TRH/FDH Research MAIN design requirements** will be proposed. The next appointed MAIN must first receive them, assess effects on domain scope, evidence/independent-review semantics, MAIN ownership, interfaces, dependencies and acceptance, and present any conflicts or necessary governance changes for explicit approval. Do not guess the requirements or quietly alter approved constraints.

Read the [DEV03 Handoff](handoffs/DEV-PR-03.md), [DEV02 Handoff](handoffs/DEV-PR-02.md), current approved ADRs and live GitHub evidence. Reuse unchanged contracts and verified evidence; justify new abstractions by immediate consumers; retain the user's minimum-complexity MVP direction without weakening scientific support, access isolation, PAUSED/UNKNOWN or independence.

An eventual successor startup prompt authorizes no implementation. DEV04 needs a fresh explicit development grant **after** assessing the user's forthcoming requirements; proposed DEV04/11/12 acceptance additions require their own approved governance process. No successor is started by this archival work.
