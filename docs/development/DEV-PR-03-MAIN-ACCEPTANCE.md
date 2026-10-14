# DEV-PR-03 — Formal Development MAIN acceptance archive

**Decision:** `MAIN ACCEPTED`, issued 2026-10-14T02:59:30.462866Z before user merge.  
**Accepted HEAD:** `c4ea8bc93b2018f30f04a5c5df7d1a8b1a653525`.  
**Accepted tree:** `7a079828c351af4dce6f645da6e5d53a44c75010`.  
**Software PR:** [#6](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/6), now `GITHUB MERGED`.  
**Observed merge/main:** `bd5c957798355296248e2c9fbc1ebdf63a1861eb`.

This file archives the separate Development MAIN decision. It does not replace independent review, confer mathematical authority, or declare this documentation PR reviewed/merged. The [original decision record](records/DEV-PR-03-MAIN-ACCEPTANCE-ORIGINAL.txt) is preserved **byte-exactly**. Its historical `WAITING_FOR_USER_MERGE` describes the pre-merge checkpoint. Local evidence paths in that record and `input/...` references in raw reports identify retained audit packets; they are not promised repository files. [Evidence index](DEV-PR-03-EVIDENCE.json) records identities and durable test inventories.

## Scope and authority

The user authorized DEV03, necessary bounded CI/test changes, independent review, up to two directed remediation rounds, MAIN acceptance, and a separate archive PR after software merge. A later explicit exception permitted **existing Store construction/read plumbing only**. Writers, reducers, schema/index, future Store implementation, real Runner/Provider, UI replacement and subsequent packages remained excluded. Both software and documentation merge decisions/execution belong to the user.

The accepted MVP is the [confined status query](DEV-PR-03-CONTRACT.md): `python3 -B -m pmrh status PROJECT --instance INSTANCE --json [--as-of JOURNAL_COMMIT]`. It reads an existing, pinned project snapshot; missing project/config/pool data does not create persistent state. `read_status` observes the global pool separately from `reconcile_pool`; the legacy `status` alias remains explicitly mutating. MAIN and communication consume the selected snapshot. The private descriptor reader directly feeds existing Store verification/replay, with no duplicate storage engine. `StateAxes` and typed errors have actual consumers; unmappable raw state remains explicit.

The MAIN inspected the affected source and judged the defined Q01/Q02/Q03/ GUIDE:C03 and partial Q04/Q05 MVP evidence sufficient, after independently verifying GitHub source/CI/test identities, both independent reviews and nine isolated actual CLI checks. Full future product acceptance is not claimed.

## Independent review and remediation

| Evidence | Frozen HEAD | Recommendation |
|---|---|---|
| [General R1](reviews/DEV-PR-03-GENERAL-REVIEW-R1.md), Astra/xhigh | `32bfced663e50cd69f418b21ed9af5f2faef0502` | REQUEST_CHANGES: 2 MAJOR |
| [Security R1](reviews/DEV-PR-03-SECURITY-REVIEW-R1.md), Astra/ultra | same | REQUEST_CHANGES: 1 MAJOR, 1 MINOR |
| [General R2](reviews/DEV-PR-03-GENERAL-REVIEW-R2.md), Astra/xhigh | accepted HEAD | APPROVE; both findings CLOSED |
| [Security R2](reviews/DEV-PR-03-SECURITY-REVIEW-R2.md), Astra/ultra | accepted HEAD | APPROVE; both findings CLOSED |

One of two permitted remediation rounds was used. The normal commit from R1 to accepted HEAD changes four files (117 insertions, three deletions); unchanged R1 scope/evidence is reused. No second remediation or expanded work was required.

| MAIN finding | Original review IDs | Final disposition |
|---|---|---|
| MAIN-03-01: lost admission state when typed mapping unavailable | GEN-01 / SEC-01 | CLOSED: raw per-request `acceptance_state` retained; absent value explicitly NOT_RECORDED; no fabricated SETTLED mapping |
| MAIN-03-02: malformed pool Unicode breaks project JSON | GEN-02 / SEC-02 | CLOSED: canonical UTF-8 validation before pool availability/count publication; invalid keys/values yield unavailable/null counts, retaining project JSON |

The reviewers' original severity difference is preserved. MAIN required both defects fixed for MVP correctness/availability. There are no remaining DEV03 BLOCKER/MAJOR or newly deferred MINOR findings.

Reviewers used independent CLI contexts, frozen copies and verified read-only/restricted-network profiles; no Developer full conversation or write credentials. Every actual turn was checked before the gate opened. Authorized canary writes failed with EROFS(30), hashes unchanged; all 377 R2 immutable packet files remained unchanged. Own reviewer execution was source/object/hash/archive/AST/log verification; product tests were supplied CI/Controller execution, **NOT_EXECUTED by reviewers**. The initial configuration-gate timeouts are retained as NOT_EXECUTED attempts, not passed reviews. These are independent CLI reports, **not GitHub-native Review submissions**.

## CI and merged source identity

| Check | Run / job | Result / artifact |
|---|---|---|
| DEV03 Python 3.11 | [38502114213 / 115651255653](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38502114213/job/115651255653) | 36 unique tests; 11866406934 |
| DEV03 Python 3.13 | [38502114213 / 115651255833](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38502114213/job/115651255833) | 36 unique tests; 11866073337 |
| DEV02 Python 3.11 | [38502114198 / 115651255547](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38502114198/job/115651255547) | 119 unique tests; 11866247348 |
| DEV02 Python 3.13 | [38502114198 / 115651255736](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38502114198/job/115651255736) | 119 unique tests; 11865528650 |
| DEV01 | [38502114175 / 115651255396](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38502114175/job/115651255396) | 48 unique tests; 11866411891 |
| Phase 0 | [38502114254 / 115651255735](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38502114254/job/115651255735) | 6 tests; no ZIP |

All completed/success. Original ZIP digests/CRCs, raw test IDs/outcomes/hashes and source archives were independently verified, including all 292 source blobs/modes. Phase 0 tested temporary merge `6378ea468987aff13a6e939d4441869dce49a7c4`, whose parents and tree were verified; it is not the actual merge. R1's earlier temporary-merge evidence gap was subsequently resolved without editing its report.

User `ZhiyaoXiongMath` merged PR #6 at **2026-10-14T13:15:58Z (21:15:58 Asia/Shanghai)**. Fresh GitHub observations at 13:44:11Z confirmed main/merge `bd5c957...`, parents in order `507ea4baca2782ab0da13ab949bc4424fc707694` and the accepted HEAD, and the exact accepted tree. The fresh checkout's 292 blobs/modes also match the remote tree. **Zero workflow runs were found for the actual merge SHA**; previous PR evidence is not relabelled post-merge main CI.

## Explicit retained risks and limits

- POSIX/Linux, Python 3.11+, `-B`/`PYTHONDONTWRITEBYTECODE` required; OS-maintained atime excluded. Project/pool observations are not atomic. Read limits fail unavailable rather than repairing state.
- Confined-query tests do not certify all legacy I/O, hostile native code, privileged mounts or modified interpreters. Python test guards are not OS isolation proof.
- Real research, models/providers/native execution, metered calls, browser/PDF, full legacy suite, migrations and complete 58+46 future acceptance remain NOT_EXECUTED. Counts are NOT_INSTRUMENTED/null, not measured zero. PAUSED/UNKNOWN and mathematical qualifications are not upgraded.
- Inherited REV02-HELPER-01 remains accepted nonblocking MINOR, INCONCLUSIVE / NOT_EXECUTED; it is never a sole integrity gate. The original deliverer must provide source before any future trusted use; target that helper only.
- Historical PR #5 document-review body remains NOT_RETRIEVED. DEV03 used a separately verified independent baseline preflight and MAIN dependency decision; no historical review or HANDOFF COMPLETE is invented.
- Original failed probes, CI/AST checks, R1 defects and startup failures remain historical failures. New evidence closes defects only at the accepted HEAD. Material source/base drift needs targeted reassessment.

After merge, rollback is a separately reviewed software revert PR; never rewrite Git/scientific journal history, delete evidence or clear UNKNOWN. [Handoff](handoffs/DEV-PR-03.md) records the documentation completion gate and the user's new Research MAIN requirement hold.
