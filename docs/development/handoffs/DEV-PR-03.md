# DEV-PR-03 — Post-merge Development MAIN handoff

**Software baseline:** `main@bd5c957798355296248e2c9fbc1ebdf63a1861eb`, independently verified 2026-10-14.  
**Software state:** IMPLEMENTED / TESTED / REVIEWED / MAIN ACCEPTED / GITHUB MERGED.  
**Archive state:** documentation review, user merge and post-merge readback are still required. **HANDOFF COMPLETE is not yet declared by this versioned snapshot.** This document does not predict its own final commit/merge SHA.

## Provenance and evidence

- [Software PR #6](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/6), merged by the user at 2026-10-14T13:15:58Z.
- Original base: `507ea4baca2782ab0da13ab949bc4424fc707694`.
- Accepted HEAD: `c4ea8bc93b2018f30f04a5c5df7d1a8b1a653525`; parent/R1 head `32bfced663e50cd69f418b21ed9af5f2faef0502`.
- Actual merge: `bd5c957798355296248e2c9fbc1ebdf63a1861eb`, with parents original base, then accepted HEAD.
- Accepted and merged tree: `7a079828c351af4dce6f645da6e5d53a44c75010`; all 292 checkout blobs/modes matched GitHub. No separate merge-SHA CI run was found.
- [Formal MAIN acceptance](../DEV-PR-03-MAIN-ACCEPTANCE.md), [byte-exact original decision](../records/DEV-PR-03-MAIN-ACCEPTANCE-ORIGINAL.txt), [machine-readable identities/test inventory](../DEV-PR-03-EVIDENCE.json).
- Original [General R1](../reviews/DEV-PR-03-GENERAL-REVIEW-R1.md) / [Security R1](../reviews/DEV-PR-03-SECURITY-REVIEW-R1.md): REQUEST_CHANGES. [General R2](../reviews/DEV-PR-03-GENERAL-REVIEW-R2.md) / [Security R2](../reviews/DEV-PR-03-SECURITY-REVIEW-R2.md): APPROVE at accepted HEAD. All four reports are byte-exact; historical pre-merge statements remain historical.

One directed remediation round (limit two) closed raw-admission preservation and malformed pool Unicode findings. No new DEV03 blocker/major/minor remains. Reviewer approval, MAIN acceptance, user merge and archive completion are distinct. The independent CLI reviews are not GitHub-native review submissions.

## Accepted behavior and inherited interfaces

The smallest usable status path is `python3 -B -m pmrh status PROJECT --instance INSTANCE --json [--as-of JOURNAL_COMMIT]`; see [contract](../DEV-PR-03-CONTRACT.md). Project snapshot reads and global pool observation do not create/repair persistent data, reconcile reservations, inspect processes, refresh authorization or start research. Missing/unobserved values remain explicit. PAUSED, UNKNOWN, raw admission outcomes and scientific scope retain their meaning.

`host_pool.read_status` is observation; `reconcile_pool` retains the original writer body; the old `status` alias is mutating. Existing Store verification/replay consumes the private descriptor reader only in the new query. Default Store readers still follow latest HEAD. MAIN and communication projections receive the fixed snapshot. This does not certify all old workspace/report/runner paths as confined queries.

`pmrh.ports.StateAxes` and typed errors are reused only where concrete semantics match. Unmappable legacy states stay raw with null typed mapping. No fabricated ExactRef, new public Port, repository adapter or second Store was introduced. The read-plumbing exception is not blanket permission for future Store/writer changes. Exact legacy-path and dependency exceptions have direct consumers, ownership and negative tests; original baselines remain unchanged.

## Validation and preserved limits

Accepted-head CI: DEV03 [38502114213](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38502114213), 36 tests on each of Python 3.11/3.13; DEV02 [38502114198](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38502114198), 119 each; DEV01 [38502114175](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38502114175), 48; Phase 0 [38502114254](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38502114254), six. See acceptance/index for job/artifact IDs, digests, raw test identities and temporary-merge distinction.

Q01/Q02/Q03 and relevant GUIDE:C03 are evidenced only within defined synthetic DEV03 coverage; Q04 snapshot/paging/concurrency and Q05 backend-unobserved portions are bounded. Nine Controller strict-UTF-8 CLI checks supplement CI. Reviewers verified supplied raw evidence but did not execute product suites in their read-only environments. Historical failed probes/AST checks/R1 findings and startup timeouts are preserved, not relabelled.

POSIX/Linux and bytecode-disabled invocation are required. OS atime is excluded, pool/project are not atomic, and bounded-read excess returns unavailable. Tests do not prove hostile-native isolation. Real models/providers/native research, paid usage measurement, browser/PDF, full historical product suite, scientific migrations and complete 58+46 future cases remain NOT_EXECUTED. Model counts remain null/unmeasured. No software result grants mathematical checked status.

REV02-HELPER-01 remains the inherited accepted nonblocking MINOR, INCONCLUSIVE / NOT_EXECUTED; do not make its unverified helpers a sole integrity authority. PR #5 historical document-review text remains NOT_RETRIEVED; the separate DEV03 baseline preflight does not retroactively fill that gap.

## User's new Research MAIN requirements — mandatory startup hold

On 2026-10-14 the user instructed: **“我将提出新的 TRH/FDH Research MAIN 设计要求，DEV04 开发尚未授权，启动前需要评估这些要求的影响。”**

The new requirements have not yet been supplied here. Do not invent their content, implement them, or treat this note as an approved ADR/acceptance change. Before any DEV04 development startup, the next appointed MAIN must obtain the requirements and assess their effect on the proposed domain extraction, existing TRH/FDH responsibilities, one logical Research MAIN per instance, scientific evidence/review semantics, ownership, interfaces, dependencies and acceptance plan. Preserve approved constraints pending explicit decisions; report conflicts instead of weakening them. Any normative addendum and development scope need their own explicit user authorization.

**DEV04 development is NOT AUTHORIZED and has NOT STARTED. DEV04 through DEV18 remain unstarted by this Controller.** The eventual successor prompt is for recovery, requirements intake and impact assessment before seeking development authority; it cannot dispatch implementation. Previous proposed DEV04/11/12 mathematics clarifications remain PROPOSED / NOT AUTHORIZED, not automatically accepted by this handoff.

## Completion, rollover and rollback

1. Independently review this documentation-only PR against frozen source and original evidence; record a separate MAIN documentation disposition.
2. Keep it Open, without auto-merge, for the user to decide and execute merge.
3. After the user merge, freshly verify actual PR/main/merge parents, documentation tree, byte-exact raw reports/decision and archive links. Distinguish any documentation CI from software/post-merge runtime testing.
4. Only after successful readback may the outgoing MAIN declare HANDOFF COMPLETE and deliver the next MAIN startup prompt containing the requirement hold above. Do not start DEV04 or a successor chat automatically.

A new MAIN must read current AGENTS, CONTRIBUTING, all effective ADRs, protocol, roadmap, acceptance baseline, state and this handoff, then independently reconcile live GitHub facts. This versioned snapshot is not authorization or a live status service. Keep the user's minimum-complexity/MVP direction and reuse evidence for unchanged identities; preserve research and access safety.

Documentation corrections use scoped normal commits; after merge, software rollback requires a separately reviewed revert PR. Never rewrite preserved refs or scientific evidence, clear UNKNOWN, resume PAUSED or operate real research projects during handoff.
