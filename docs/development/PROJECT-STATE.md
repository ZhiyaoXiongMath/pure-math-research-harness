# Latest reconciliation — GOV-02 frozen snapshot (2026-10-21)

**Observed main:** `4239f15ad1233cc89cd6556cec284951b5fc2e3e`, from global control's refreshed primary GitHub metadata at **2026-10-21 13:30:58 UTC**. This is the **GitHub metadata cutoff**, not the time of the later Controller decision. The original packet remains preserved. A separate decision supplement was verified at **2026-10-21T13:39:53.644980+00:00** and changes only DEV06's final-head Controller disposition. This isolated Developer used both frozen inputs and made no live GitHub query. This is a dated evidence index, not a live mirror, authorization token or mathematical authority. All older snapshots below, including headings saying “latest,” candidate labels and NOT_AUTHORIZED/archive-pending statements, describe their dated checkpoints.

[PROGRAM-CONTROL](PROGRAM-CONTROL.md) records **HUMAN-PROGRAM-GRANT-20261021**, effective immediately from the explicit human decision; GOV-02 review/merge records it rather than activating it. It covers GOV-02, DEV06 closeout, DEV07–14 bounded development and DEV18 integrated acceptance/release-candidate preparation. [DEVELOPMENT-LEDGER.json](DEVELOPMENT-LEDGER.json) separates authorization, implementation, tests, review, acceptance, merge and handoff for all 18 planning packages. Optional DEV15–17 decisions and formal release remain PENDING_HUMAN_DECISION. Global control persists across package handoffs; dependencies, appointments/freezes and human merge decisions remain mandatory.

## Current facts and historical limitations

| Item | Frozen evidence and limits |
|---|---|
| DEV01–05 software | Merged as the older baseline records report. DEV01's separately retrievable MAIN acceptance remains unavailable despite its archived independent review and merge. No retroactive acceptance record is created. |
| Historical archives | [PR12](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/12) is merged at observed main above (archive head `7adeb4e6b5e8c3662c0f67e406828a725a01fde0`), reconciling the older DEV05 archive-pending snapshot. Prior PR7/10 merges remain recorded below. Archive merge alone establishes neither missing historical review/acceptance nor HANDOFF COMPLETE. PR5's historical independent document review is **NOT_RETRIEVED**. |
| Approved specification | Research MAIN strategy and 04/11/12 mapping v0.1.0 are effective specifications via [PR8 approval](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/8#issuecomment-6185982722), merged `f724c06b54b157abe580cdf046f4fc08bb01c144`. Historical candidate labels persist unchanged; specification approval itself never granted implementation. |
| DEV06 current delivery | [PR13](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/13) is **OPEN / unmerged**, head `0a552d93fb2518fdc03697f21e560ec1db312999`, base equal to observed main. At the metadata cutoff, seven workflows / twelve jobs are green; exact runs follow. The later supplement reports no merge and does not refresh CI metadata. There is no actual merge SHA or merge-SHA CI for this unmerged PR. |
| DEV06 original product decision | H0 `261195fa78f1243326119876a94b9f32219b4b26`: original Controller MAIN ACCEPTED only for the approved local/offline synthetic scope, validation009 **116/116** and **43 requirement items**. The PR13 public body indexes review/acceptance/evidence; original private sources remain private. |
| DEV06 later repair | Final head changes four CI/guard files with product bytes unchanged. Independent recommendation **APPROVE_FOR_MAIN_ACCEPTANCE** (zero findings) and separate **ACCEPTED_FOR_AUTHORIZED_CI_REMEDIATION_DELIVERY** decision are bounded repair evidence, not the original product acceptance rebound to final head. Private independent review is distinct from native GitHub Review; delivery reported no native reviews. |
| DEV06 closeout — later decision supplement | A separate new actual **gpt-6-astra/high** package Controller issued **ACCEPTED_SCOPED_PREMERGE / READY_FOR_USER_MERGE_DECISION** at **2026-10-21T13:36:35.874566+00:00**, for head `0a552d93fb2518fdc03697f21e560ec1db312999`, base `4239f15ad1233cc89cd6556cec284951b5fc2e3e` and tree `97f1bb72b20c5b55b7259b8ff7b596e1d43bb2f7`. Scope: approved local/offline synthetic DEV06 plus the separately tested and independently reviewed four-file CI repair. Human merge remains pending; **DEV06 HANDOFF COMPLETE is not declared.** |
| DEV07–14 / DEV18 | AUTHORIZED_UNDER_PROGRAM_GRANT within the stated scope, but product packages remain NOT_STARTED / NOT_APPOINTED until appointed and frozen with dependencies verified. DEV07 global read-only preflight is preparation only; DEV06 scoped final-head acceptance is now recorded; implementation still awaits human DEV06 merge, verified handoff and package appointment/freeze, with that acceptance remaining valid. DEV18 formal release needs a separate decision. |
| GOV-02 | Six-path documentation package only. Developer authors scratch outputs; independent final-commit review, separate Controller acceptance, PR/merge and post-merge handoff are not recorded here. No own future SHA or completion claim is embedded. |

**New decision provenance:** `DEV06-CLOSEOUT-20261021`, dated `2026-10-21T13:36:35.874566+00:00`, source SHA-256 `5f3447a007d233d92b2940557ac4958fd4257d624665faf0696f7b4bd0463cd4`. The original decision is **PRIVATE**, retained outside the public repository; this public ID/date/digest is Controller-attested provenance, not a public PR13 decision link. Global control verified all **26 evidence digests**, the report and actual runtime; the package Controller verified the source decision digest. No product tests or independent review were rerun. This new decision is separate from H0 product acceptance, the repair recommendation and bounded repair delivery decision; none is retroactively rebound. Readiness is invalidated by changed head/base/owned interface/authority, a new finding, superseding failed CI or evidence mismatch.

## DEV06 CI provenance — reused scoped evidence

| Exact public run | Workflow | Jobs | Metadata at 13:30:58 UTC |
|---|---|---|---|
| [39595721914](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/39595721914) | PMRH Phase 0 safe offline checks | 1 | completed / success |
| [39595721871](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/39595721871) | PMRH DEV-PR-01 AST and synthetic offline guard | 1 | completed / success |
| [39595722065](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/39595722065) | PMRH DEV-PR-02 versioned contracts | 2 | completed / success |
| [39595722202](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/39595722202) | PMRH DEV-PR-04 pure domain extraction | 2 | completed / success |
| [39595722138](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/39595722138) | PMRH DEV-PR-03 confined read-only queries | 2 | completed / success |
| [39595721970](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/39595721970) | PMRH DEV-PR-05 bounded disk storage | 2 | completed / success |
| [39595721989](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/39595721989) | PMRH DEV-PR-06 synthetic control admission | 2 | completed / success |

DEV02–06 checkout the exact PR head `0a552d93fb2518fdc03697f21e560ec1db312999`. Phase0/DEV01 use temporary PR merge `2fa9fac802d83e8e72bebf0da36212cfab7677e0`, with the same tree; it is **not an actual merge**. Run metadata alone is not checkout proof. The original delivery audited **12 checkout logs, 11 artifact ZIPs and 10 source archives**. Global control refreshed current metadata and reused that prior audit; neither this refresh nor this documentation authoring is a new full artifact audit.

Supplied local full-suite evidence reports DEV05 **43/43** and DEV06 **119/119**, with **35 overlapping methods**; do not add these as independent coverage or equate them to H0 validation009's 116/116. Original local001–008 failures/incomplete history remains; **local005 cause is UNKNOWN**. Later success does not repair historical provenance. Inherited REV02-HELPER-01 stays accepted nonblocking **INCONCLUSIVE / NOT_EXECUTED**, never sole integrity or merge authority.

## Unchanged boundaries and next gates

Preserve original target/D0, TRH/FDH responsibilities, six immutable scientific records, exact source/proof qualification and independent review, dependency-scoped invalidation, one logical Research MAIN, budgets, PAUSED/UNKNOWN, no blind retry and raw invocation/capture evidence. Development management supplies no scientific/model authority. Original **58+46 definitions are unchanged**: full product aggregate, real backend transport, production, research and migration remain **NOT_EXECUTED**. Management inference is **NOT_MEASURED**, not measured zero. No product tests were rerun by this documentation Developer.

GOV-02's next gate is Controller inspection/copy followed by fresh independent review of the committed full delta and frozen inputs, separate MAIN disposition and human merge. DEV06 now awaits the human merge decision, then actual main/CI-provenance readback and verified handoff under its separately recorded scoped final-head acceptance; neither package can claim the other's acceptance. Recheck real main on each authorized merge, record CI source provenance and verify handoff before successors. Public evidence uses existing repository records and supplied public links; private packets, runtime IDs, paths and logs remain private. Revert only through reviewed, authorized software/documentation change; never rewrite evidence or clear PAUSED/UNKNOWN.

## Historical content — original bytes retained below

The following text preserves its dated decisions and observations. Read current authorization and status through the amendment above; no missing historical evidence is repaired by this annotation.

# PMRH development project state — latest versioned snapshot

## Latest snapshot — DEV05 software merged; archive pending (2026-10-16)

**Observed main:** `25176107f552cbec2abe1b05c03b87a38d610f39`.
**Tree:** `59f2777d9cb736eb3c445f29f7dfb6e8a92a0647`.
**DEV05 software:** IMPLEMENTED / TESTED / REVIEWED / MAIN ACCEPTED / GITHUB MERGED.
This snapshot records supplied evidence, not live status, human consent or mathematical authority.

Controller post-merge verification is dated `2026-10-16T02:15:42.152590+00:00`.
The archive Developer independently compared local Git parents/trees and all 349
baseline tracked file hashes/blob identities/modes with the supplied manifest and
fresh Controller GitHub records. **It made no live GitHub queries.**
The original state below is preserved byte-for-byte as a historical suffix.

| Event / status | Evidence and reconciliation |
|---|---|
| DEV04 archive merged | [PR #10](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/10), `2026-10-15T09:58:11Z`, merge `2c65af1a407c159d6768867bf25c03566c4657c1`. The older DEV04 archive-pending snapshot is historical. |
| DEV05 separate grant | The user separately authorized implementation/offline tests/review/Open PR and the restricted synthetic persistence extension in the [contract](DEV-PR-05-CONTRACT.md). Earlier NOT_AUTHORIZED text remains true of its original cycle; it does not prohibit this later authorized work. |
| Independent software review | [CLI re-review](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/11#issuecomment-6193171124), APPROVE_FOR_MAIN_ACCEPTANCE at `68de9fa7db55c51ffad27e498e928ab6788cb817`; F1/P1, F2/P2 closed and final CI satisfied. Native GitHub Reviews are separately empty. |
| Separate software MAIN decision | [Acceptance](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/11#issuecomment-6193187147), `2026-10-15T13:25:42.124887+00:00`. Its immutable OPEN/unmerged/no-merge-authorization state is preserved; later user merge is distinct. |
| User software merge | [PR #11](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/11), merged by `ZhiyaoXiongMath` at `2026-10-16T02:10:14Z` (10:10:14 Asia/Shanghai). Actual merge is observed main above; parents are `2c65af1a407c159d6768867bf25c03566c4657c1` and accepted head `68de9fa7db55c51ffad27e498e928ab6788cb817`; merge and accepted trees are identical. |
| Archive only, pending | [DEV05 Handoff](handoffs/DEV-PR-05.md) records scope/API, exact CI links, hashes, failures, limits and rollback. Keep archive PR **Open** pending independent exact-head review, separate Controller disposition, user merge and readback. No archive SHA/PR number is predicted; later review/acceptance belongs in its PR body. **HANDOFF COMPLETE is not declared.** |

Six PR workflows / ten jobs passed: DEV01 48; DEV02 119 each; DEV03 36 each;
DEV04 34 baseline + 34 facade + 10 boundaries and 55 equal trace keys each;
DEV05 43 S2 methods each; Phase0 6. Hosted S2 uses Python 3.11.17/3.13.16;
final local S2 is 43 PASS on 3.14.4. Controller/reviewer evidence binds eight
complete source archives to 349 files; this archive reuses those receipts.
DEV02–05 explicitly checked accepted head. DEV01/Phase0 used temporary merge
`738a1c99d28cc25949a2a8ef1804c10446fb382b`, same tree/parents, **not actual merge**.
ARCHIVE-CI-01: DEV01's original checkout log identifies this temporary merge;
`PMRH_SOURCE_SHA=68de9fa7db55c51ffad27e498e928ab6788cb817` is its logical receipt
label, not actual checkout. Original receipts, software results and tree equality
remain unchanged; the [handoff](handoffs/DEV-PR-05.md) records this provenance correction.
Fresh merge-runs is empty: **no separate merge-SHA CI observed**, not CI failure.
No product suites were rerun by this archive Developer.

Inherited storage has one journal/lock/HEAD authority, pure core/repository dependencies,
unchanged domain/v1 DTOs, fixed trusted legacy reducers and pure/confined queries.
Scope-bound committed-prefix reads exclude staged data; authority precedes duplicate
lookup under lock; persistent full-batch idempotency, port CAS, legacy relevant-dependency
revalidation, original envelopes and exact GAP semantics remain. No arbitrary callbacks
or HUMAN claims. Synthetic-only two-event/policy/batch/envelope extension uses sticky
`pmrh.commit/1`; legacy-only stays `pmrs.commit/4.2.2`; old readers reject extended HEAD.
No production activation/migration. F1 capacity preflight preserves old readable HEAD
under unchanged limits, leaving invisible orphans; F2 covers 13 FORMAT dependency files.
SCOPE-01/02/03 are the exact contract exceptions; original failure history is retained.

Original target/D0, six records, qualification, candidate/formal distinction, independent
review, failure scope/dependency invalidation, single MAIN, budgets and PAUSED/UNKNOWN
remain protected. No full DEV11/12 objects/strategy loop or mathematical proof claim.
Original 58+46 definitions are unchanged and not globally PASS. Full legacy/native/provider/
browser/PDF, 10,000/1,000 stress, production migration, real research and DEV06 recovery
remain NOT_EXECUTED; no universal power-loss certification. Management inference is
NOT_MEASURED. REV02-HELPER-01 remains nonblocking INCONCLUSIVE / NOT_EXECUTED,
never sole authority. Rollback requires authorized review/revert, preserving journals,
compatible format readers and UNKNOWN; no deletion, downgrade or automatic retry.

**DEV-PR-06 through DEV-PR-18: NOT_AUTHORIZED / NOT_STARTED by this cycle.**
Controller retains Git/publication/acceptance; the Developer does not self-accept.
No successor startup prompt, dispatch, new MAIN/Goal, budget or research is authorized.

## Historical content — entire original state retained below

All following headings and restrictions describe their dated checkpoints, including
old “latest”, archive-pending and successor-authorization labels. The snapshot above
reconciles subsequent events without rewriting any historical decision or granting new work.

# PMRH development project state — versioned evidence snapshot

## Latest authoritative snapshot — DEV04 software merged; archive pending (2026-10-15)

**Current observed software main:** `1a85ba643d77420ffb7303665a9f9d31a1cca14c`; tree `d7c5604b9752f984806125ceebc8414e0599d222`. **DEV04 software: IMPLEMENTED / TESTED / REVIEWED / MAIN ACCEPTED / GITHUB MERGED.** This new snapshot supersedes the current-status interpretation of the older DEV04 NOT_AUTHORIZED and PR8 CANDIDATE statements below; their text is retained as historical evidence.

The Controller fetched fresh GitHub records and recorded post-merge verification at `2026-10-15T08:59:40.016478+00:00`. The separately appointed archive Developer independently examined those records and local Git, verified all 319 tracked file bytes/modes, merge parents and equality with the accepted software tree. It performed **no live GitHub fetch**. This remains a dated evidence index, not a live service or human authorization token.

| Decision / event | Current evidence and scope |
|---|---|
| Research MAIN specification approved | [PR #8 formal approval](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/8#issuecomment-6185982722), then merge `f724c06b54b157abe580cdf046f4fc08bb01c144`. [Strategy v0.1.0](../architecture/RESEARCH-MAIN-STRATEGY.md) and [addendum v0.1.0](ACCEPTANCE-ADDENDUM-04-11-12.md) are effective specifications despite historical candidate labels. Their approval did not authorize implementation. |
| Separate DEV04 implementation grant | The user subsequently explicitly authorized implementation according to the preparation report, offline tests, independent review and Open PR submission, without automatic merge or successor work; [PR #9 scope](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/9) records this grant. This superseded the earlier hold; the hold itself granted nothing. |
| DEV04 software MAIN acceptance | [Byte-exact original decision](records/DEV-PR-04-MAIN-ACCEPTANCE-ORIGINAL.json), `2026-10-15T08:30:34.642650+00:00`, accepted head `acf7cd6e6b3c093459564487a44dbeb56845cc79`. [Independent review rendering](reviews/DEV-PR-04-INDEPENDENT-REVIEW.md): APPROVE_FOR_MAIN_ACCEPTANCE, zero new blocker/major/minor findings; same-head CI condition subsequently fulfilled. The rendering is path-normalized, **not byte-exact**; original SHA-256 `623c6fc8b5192e6addce7667a3d2639d1674da8ab5b4d1d805d3218471f0c949`. |
| User software merge | [PR #9](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/9), merged by `ZhiyaoXiongMath` at `2026-10-15T08:50:43Z` as current main above. Parents: `f724c06b54b157abe580cdf046f4fc08bb01c144`, then accepted head. The original decision's `merge: NOT_AUTHORIZED_NOT_PERFORMED` is preserved as historical, not rewritten by this later event. |
| Separate archive grant and pending gates | The user now authorizes DEV04 handoff/state archival work only. [DEV04 Handoff](handoffs/DEV-PR-04.md) records scope, APIs, commands, CI/artifacts, failures, limits, isolation and rollback. The archive remains pending final-commit independent review, separate MAIN disposition, user merge and readback; keep its PR **Open**. **HANDOFF COMPLETE is not declared.** Later acceptance is recorded externally in the archive PR body; this snapshot predicts no archive head or PR number. |

Five PR workflows / eight jobs succeeded: [DEV04 38705408611](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38705408611) (34 baseline + 34 facade + 10 boundaries, 55 equal traces on each of Python 3.11/3.13), [DEV02 38705408437](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38705408437) (119 each), [DEV03 38705408361](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38705408361) (36 each), [DEV01 38705408388](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38705408388) (48), [Phase0 38705408373](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38705408373) (6). DEV02/03/04 explicitly checked the accepted head. DEV01/Phase0 checked temporary PR test merge `8c569475f561e9bd769870ebcc2c1d681d7330e6`, with the same tree, **not the actual merge**. The merge-SHA query returned zero runs: **no separate merge-SHA CI observed**, not failed PR CI. Controller artifact verification and exact-head Python 3.14.4 bwrap tests are indexed in the handoff; this archive Developer did not rerun product suites.

Accepted scope is existing domain-rule extraction with compatible aliases and an intentional FORMAT implementation-fingerprint update. Original target/D0, six records, exact qualification, independent review, candidate/formal distinction, scoped failure and dependency invalidation remain preserved; no new mathematical results. DEV11 fast objects and DEV12 strategy closed loop are not implemented. The 58+46 definitions remain untouched and are not globally PASS. Initial three fixture/guard failures and five resolved EOF fixes retain their original evidence. REV02-HELPER-01 remains accepted nonblocking, INCONCLUSIVE / NOT_EXECUTED. Full runtime/native/provider/browser/PDF/migration/research and full product acceptance remain NOT_EXECUTED; model usage is NOT_MEASURED, not zero.

**DEV-PR-05 through DEV-PR-18: NOT_AUTHORIZED / NOT_STARTED by this cycle.** No successor startup prompt or dispatch is issued. Controller publication, independent archive review, MAIN disposition and user merge remain separate responsibilities; this Developer does not self-accept or merge.

## Historical snapshots — original text retained below

The following dated sections preserve earlier observations and authorization limits. Their headings such as “Current execution gate” and “Next candidate” apply to those earlier checkpoints; the latest snapshot above supplies the current DEV04 state. This annotation does not fabricate missing historical review or handoff evidence.

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

## 6. Research MAIN documentation candidate and post-archive readback — 2026-10-15

New live GitHub readback confirmed [DEV03 software PR #6](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/6) merged as `bd5c957798355296248e2c9fbc1ebdf63a1861eb`, and [DEV03 archive PR #7](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/7) merged at 2026-10-15T03:13:33Z as `4b8111dcc74863d8e9d0a1898c373d4cbebb4fcb`. Archive head `98a4a3c4cff2967150d94967dcd94f749d8451ef` and PR #7 merge have identical Git tree `00192c889c5ae242b2109e7a0d4ceb204dfd82a7`; merge parents are software merge and archive head. This observation supplements rather than overwrites the historically correct pre-merge Handoff; no claim that its separate historical HANDOFF COMPLETE declaration occurred.

The separately authorized **documentation-only** branch [docs/research-main-strategy-2026-10-15](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/tree/docs/research-main-strategy-2026-10-15) proposes [Research MAIN strategy v0.1.0](../architecture/RESEARCH-MAIN-STRATEGY.md) and [04/11/12 acceptance addendum](ACCEPTANCE-ADDENDUM-04-11-12.md). The actual PR number, frozen head, CI and independent verdict are determined by GitHub/PR evidence, **not predicted inside this versioned document**. Current proposed status: **DOCUMENT CANDIDATE / NOT EFFECTIVE / NOT REVIEWED / NOT IMPLEMENTED**; awaiting independent review, Development MAIN acceptance and user-authorized merge. The user's R01–R12/MR01–MR10 are recorded as future design behavior and scenario mappings, not live mathematical facts or newly executed product tests.

Future ownership: DEV04 preserves original Goal/D0 and scientific domain/qualification semantics during extraction; DEV11 implements the first-class fast layer and precise slow bindings; DEV12 implements genuine MAIN decision inputs, Worker triad and evidence-sensitive replanning; DEV13 consumes qualified snapshots for reporting. Old 2026-10-13 Library proposals were PROPOSED/NOT AUTHORIZED and are not adopted wholesale. **DEV-PR-04–18 software implementation is NOT AUTHORIZED by this documentation cycle**; all 58+46 future product acceptance cases remain at their existing execution status and have not been bulk marked PASS. No scientific project, MAIN/Goal, budget, provider call or scientific evidence is touched. A successor MAIN must recheck the effective version and seek distinct software authorization.

