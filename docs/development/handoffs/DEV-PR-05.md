# DEV-PR-05 — Post-merge Development MAIN handoff

**Software:** IMPLEMENTED / TESTED / REVIEWED / MAIN ACCEPTED / GITHUB MERGED,
for shared disk storage and bounded observation ports only.
**Archive:** pending independent exact-head review, separate Controller disposition,
user merge and readback. Keep the archive PR **Open**, without auto-merge.
**HANDOFF COMPLETE is not declared.** This document predicts no archive SHA or PR
number; later archive review and acceptance belong in its PR body.

## Provenance and distinct decisions

| Identity / event | Verified value |
|---|---|
| Software delivery | [PR #11](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/11), 49 changed paths, two commits |
| Software base / first merge parent | `2c65af1a407c159d6768867bf25c03566c4657c1` |
| Accepted head / second merge parent | `68de9fa7db55c51ffad27e498e928ab6788cb817` |
| Actual merge / observed main | `25176107f552cbec2abe1b05c03b87a38d610f39` |
| Accepted and actual merge tree | `59f2777d9cb736eb3c445f29f7dfb6e8a92a0647` |
| User merge | `ZhiyaoXiongMath`, `2026-10-16T02:10:14Z` (10:10:14 Asia/Shanghai) |
| Controller post-merge verification | `2026-10-16T02:15:42.152590+00:00` |

The archive Developer inspected **Controller-supplied fresh GitHub records**,
not its own live observations. Local read-only Git checks independently matched
merge parents, accepted/merged trees, and all **349** baseline tracked files'
SHA-256 hashes, Git blob identities and modes. The supplied source manifest
matches those bytes. The supplied merge-SHA query is empty: **no separate
merge-SHA CI observed**, not a CI failure. Native GitHub Reviews are empty;
the independent CLI review below is a separate evidence source.

[DEV04 archive PR #10](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/10)
merged at `2026-10-15T09:58:11Z` as the software base above. This reconciles the
prior state snapshot's archive-pending observation; it does not manufacture a
missing historical decision. The user separately authorized DEV05 implementation
and its restricted persistence extension, then later merged the software.
The present grant covers only this handoff and the new PROJECT-STATE snapshot.

- [Independent final re-review](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/11#issuecomment-6193171124): **APPROVE_FOR_MAIN_ACCEPTANCE** at the accepted head; F1/P1 and F2/P2 closed, final CI condition satisfied, no unresolved substantive finding.
- [Separate Development MAIN acceptance](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/11#issuecomment-6193187147): **MAIN ACCEPTED — DEV-PR-05 only**, `2026-10-15T13:25:42.124887+00:00`.
- That immutable decision records PR11 **OPEN / unmerged**, merge NOT_AUTHORIZED_NOT_PERFORMED and post-merge handoff not started. The later user merge is a distinct event, not a rewrite of the decision or an authorization inferred from CI.

The public comments summarize provenance, not byte-exact copies of private reports.
The archive Developer verified the supplied original files against these hashes:

| Original evidence | SHA-256 |
|---|---|
| Independent final report | `ce80fa28545a6ed7e95aa8c45582951a3a98c4cd1d55193c0759cc06bc56335c` |
| Controller final CI verification | `517933909c1273ab7f9eb0cc7bf5c23e547869c00241269c7a1f1d33bfe75634` |
| Original MAIN decision | `f0b910bf20a9959e27c43aaad196070db74c8ec78277d28247652c64334e116c` |

## Accepted scope and inherited API

The [DEV05 contract](../DEV-PR-05-CONTRACT.md) defines the inherited behavior;
this archive makes no new implementation decision. [ADR-0001](../../architecture/ADR-0001-naming.md),
[ADR-0002](../../architecture/ADR-0002-constraints.md), [ADR-034](../../decisions/ADR-034-local-body-locators.md)
and the [DEV04 handoff](DEV-PR-04.md) retain their applicable constraints.

One journal/blob/record publisher, writer lock and HEAD authority serve the legacy
Store facade and disk ports. Checkpoints and SQLite are disposable projections.
Store's consumed APIs, errors, canonical identities, raw capture validation,
report-first and post-END behavior remain compatible. Domain and v1 Port/DTO
source bytes and signatures are unchanged. Core/repository reads have no legacy
runtime, Runner or Provider dependency. Application code uses ports/domain and
injected local capabilities; adapters use ports/domain. Fixed trusted legacy
assembly owns reducers and allowed collections; data cannot install callbacks,
reducers or arbitrary patches. Pure query projections and confined pool reads
retain the selected snapshot; minimal queries use journal-only unverified reports.

EvidenceRepository/EventRepository reads require trusted out-of-band scope,
the exact published policy binding and a committed-prefix boundary at/after that
binding in captured HEAD ancestry. Staged, future, orphan and cross-scope bytes
remain invisible. ExactRef identifies content, not authority; wire data selects
neither paths nor code. Evidence bytes are fully verified before bounded slices.
Original EventEnvelope bytes, staged ordering and observation/occurrence times
are retained; publication time derives from the journal. Only verified exact
missing intervals yield GAP; corrupt/unindexable history cannot become EMPTY/GAP.

UnitOfWork begin/stage are local, bounded and invisible. Under the shared lock,
current permit authority is checked **before duplicate lookup**, against transaction,
staging digest, operation, scope and expectation. Persistent project-wide
idempotency binds the complete ordered batch and original expectation. A newly
authorized retry returns the original receipt/boundary; changed content or scope
conflicts, and revoked authority rejects. New port publication uses physical HEAD
CAS. Legacy scientific admission instead revalidates relevant task/raw, selected
revisions, supports, memberships, parents, obligations and control under lock;
unrelated HEAD changes remain admissible. Sealed paused-worker admission and
paused-MAIN/new-dispatch rejection are preserved. Uncertain publication retains
the original operation for authorized recovery, never model resampling.

The explicitly approved extension is **synthetic-only**: two closed storage events
(`PMRH_PORT_SCOPE_BOUND`, `PMRH_PORT_BATCH_COMMITTED`) plus policy, batch and
original-envelope blobs. Trusted setup enables sticky `pmrh.commit/1`; every
later checkpoint and legacy-facade entry in that lineage retains it. Legacy-only
projects retain `pmrs.commit/4.2.2`. Old readers reject extended HEAD even for
older snapshot selection. There is no production activation, installer, migration,
downgrade, second authority or new native scientific record collection.
Only DIAGNOSTIC/EVIDENCE_RECORDED OBSERVATION batches are supported, with
SYNTHETIC/SYNTHETIC_TEST_ONLY provenance; publication metadata, dispatch/MAIN/backend
authority and HUMAN claims are rejected. A persisted marker grants no consent.

Direct inheritance is E01/E03/E04, storage portions of E02/E08, Q01–Q04 and
GUIDE:K10/C13/C14 in existing local scope. RMAIN-REQ-02/10/12 preserve versioned,
scoped, independent evidence and durable recovery; REQ-01/09/11 preserve original
target/D0, candidate and failure boundaries. TRH P0–P14, FDH D0–D5, six immutable
records (Context, Statement, Argument, Example, SourceEvidence, Assessment), exact
assumptions/provenance, support qualification, candidate/formal distinction,
independent review, scoped failure/dependency invalidation, one logical MAIN,
human budgets, PAUSED and UNKNOWN remain protected. No automatic UNKNOWN retry
or mathematical proof status follows. Full DEV11 fast objects and DEV12 strategy
loop are not implemented; original **58+46 definitions are unchanged, not globally PASS**.

## Review remedies and retained failure history

- **F1/P1 closed:** prospective disk preflight verifies the actual candidate's full native/extension closure before HEAD, including candidate HEAD cost, with unchanged 4,096-file/128 MiB limits. Present checkpoints are validated without skipping native replay. It covers scope binding, port batches and later legacy/checkpoint publications. Capacity refusal preserves the old readable HEAD; immutable orphan files remain invisible. DTO validity does not promise unlimited cumulative capacity. Real maximum-batch, cumulative-budget, checkpoint-disposal and authorized duplicate-recovery cases passed.
- **F2/P2 closed:** FORMAT fingerprints cover the precise 13-file verification/registration closure: ports initializer, interfaces and all 11 DTO modules. DTO/domain bytes remain unchanged. Live mutation rejects; historical verification and recorded proof bytes remain unchanged.
- **SCOPE-01:** mechanical movement of the specified language/version constants into `native_format.py`, retaining aliases, values and shared DEFAULT identity; no new policy.
- **SCOPE-02:** exactly one DEV03 concurrent-query hook targets extracted `read_projections.main_view` with its pinned snapshot; all five original assertions and concurrent publication remain unchanged. No other original test is amended by this exception.
- **SCOPE-03:** inherited artifact gates recognize only the exact Store→native_main coupling, DEV-PR-05 owner and relocation into `storage_compat.py`; require absent old and present new edges/imports, reject missing/forged/duplicate/unrelated relocations. Other artifact gates remain intact.

The contract retains S2 candidate 01 failure (17 methods, 8 error entries),
candidate 02 (29/30 pass), candidate 03 (31/32 pass), and the earlier DEV03
35-pass/1-fail obsolete-hook regression. Original Engine.prepare-dependent
fixtures failed MODEL_CONFIGURATION_UNSUPPORTED; new synthetic fixtures do not
relabel them. The Developer's nested-isolation launch failed before imports:
product tests there remain **NOT_EXECUTED**, separate from Controller executions.
First head `4613438fa847bac8e1b833e9bff0b449de0743b3` retains failed DEV01/02
artifact gates, hosted S2 NOT_EXECUTED after bwrap setup denial, the reproduced
unreadable-HEAD capacity defect and the first **REQUEST_CHANGES** review.
Later success does not erase those failures or earlier DEV04 fixture limitations.

## Reused tests, commands and CI provenance

Controller final local S2: **43 PASS**, Python **3.14.4**. Hosted S2: **43 PASS each**
on **3.11.17 / 3.13.16**, zero errors/failures/skips/expected failures.
The supplied verification and independent re-review establish **six successful PR
workflows / ten jobs**, with **eight complete source archives matching 349 files**.
This archive Developer verifies supplied records/hashes; it does not rerun tests
or claim to re-download/reconstruct those archives.

| Workflow / exact run | Checkout and scoped result |
|---|---|
| [DEV01 38740632997](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38740632997) | Explicit accepted head; 48 PASS. |
| [DEV02 38740632913](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38740632913) | Explicit accepted head; 119 PASS on each Python 3.11/3.13. |
| [DEV03 38740632915](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38740632915) | Explicit accepted head; 36 PASS each. |
| [DEV04 38740632982](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38740632982) | Explicit accepted head; 34 baseline + 34 facade + 10 boundaries, 55 equal trace keys each. |
| [DEV05 38740633013](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38740633013) | Explicit accepted head; 43 S2 methods PASS each. |
| [Phase0 38740632971](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38740632971) | Temporary PR merge; 6 PASS. |

Phase0 checked `738a1c99d28cc25949a2a8ef1804c10446fb382b`, with the same tree and
parents as the actual merge, **not actual merge-SHA CI**. That temporary object's
provenance is supplied Controller/reviewer evidence; it is unavailable in the
archive checkout's local Git objects. Run metadata's headSha alone is not checkout proof.

Historical commands include `python3 -B scripts/check_legacy_scope.py`,
`python3 -B scripts/architecture_deps.py --check --json <artifacts>/dependencies.json --markdown <artifacts>/architecture.md`,
and `python3 -B scripts/offline_storage.py --out <artifacts>/storage-s2 --oracle <frozen-baseline>`;
regressions use accepted `offline_test.py`, `offline_contracts.py`,
`offline_queries.py`, `offline_domain.py` and the six-test Phase0 suite.
S2 permits only fixed Python children for oracle/query/restart/crash/lock cases,
uses bwrap read-only source/baseline, separate tmpfs scratch, cleared environment,
no credentials and isolated networking; real link/fsync/rename publication is tested.
The ephemeral hosted-job mitigation conditionally adjusts only
`kernel.apparmor_restrict_unprivileged_userns`, records its value and restores it
in an always-run step; both final receipts show restoration. The local host and
S2 confinement remain unchanged. Original denial's precise kernel cause is not
proven; no root product execution or bare-test fallback is certified.

## Limits, archive boundary and rollback

**NOT_EXECUTED:** full legacy/native/provider/browser/PDF suites, 10,000/1,000
stress, full 58+46 product acceptance, production activation/migration, real
research and full DEV06 recovery. Bounded crash/fault checks are not universal
filesystem/power-loss certification. Fixed capacity limits deliberately refuse
publication; no journal/orphan deletion is authorized. Inherited REV02-HELPER-01
remains accepted nonblocking **INCONCLUSIVE / NOT_EXECUTED**, never sole integrity
or merge authority. Management inference usage is **NOT_MEASURED**, not zero.

Supplied runtime evidence distinguishes Controller Astra/high with disclosed
host privileges, software implementation/remediation Astra/xhigh or high, and
independent Reviewer Astra/xhigh with read-only sources, scratch writes and no
network. This separately appointed archive Developer passed its VERIFIED
**Astra/high** gate and actual probes: scratch write succeeds; base/input append-open
without writing denies; outside canary is absent; AF_INET/SOCK_STREAM creation denies.
Its writes are only these two documents and scratch receipts. Static source/hash/Git
and documentation validation use no product imports/tests, Git mutations, network,
research access or other agents. Controller owns publication and acceptance.

Only this handoff and [PROJECT-STATE](../PROJECT-STATE.md) change; the original state
bytes remain an intact historical suffix. Software acceptance does not accept
this archive. Exact-head independent archive review, separate Controller disposition,
user merge and fresh readback remain outstanding before **HANDOFF COMPLETE**.
**DEV-PR-06 through DEV-PR-18: NOT_AUTHORIZED / NOT_STARTED by this cycle.**
No successor startup prompt, new MAIN/Goal, budget or research grant is issued.
Rollback requires authorized review/revert with evidence preserved: never rewrite
history, delete journals/blobs, downgrade extended projects, clear/retry UNKNOWN
or resume PAUSED. Compatible readers and fingerprint checks remain required.
