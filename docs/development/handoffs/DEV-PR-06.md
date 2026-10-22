# DEV-PR-06 postmerge handoff archive — candidate, 2026-10-22

**PR13 is actually merged; source/evidence verification and private technical
transfer readiness are recorded. Formal HANDOFF COMPLETE remains pending the
public archive's actual merge and readback.** This document is a local archival
candidate, not a new acceptance, merged archive or successor appointment.

## Accepted scope and source identity

The accepted scope is local offline synthetic application control under the
approved **R1-final contract**, exact human-approved **R8 visit supplement** and
bounded **R10 durable launcher repair**: current authorization, owner epoch and
control fencing, reservation/outbox/inbox, budgets and PAUSED/UNKNOWN,
conservative project/shared-pool recovery, exact visit derivation and strict
complete-history reading. The final four-file CI/guard repair changes no public
ports/DTO, persistence semantics or scientific guards.
The historical [contract candidate](../DEV-PR-06-CONTRACT-DRAFT.md) and
[implementation progress](../DEV-PR-06-IMPLEMENTATION-PROGRESS.md) retain their
dated labels and failures; this archive does not silently rewrite them.

| Identity | Verified value |
|---|---|
| Original accepted base | `4239f15ad1233cc89cd6556cec284951b5fc2e3e` |
| Original H0 product head | `261195fa78f1243326119876a94b9f32219b4b26` |
| Final reviewed CI-repair head | `0a552d93fb2518fdc03697f21e560ec1db312999` |
| Final head tree | `97f1bb72b20c5b55b7259b8ff7b596e1d43bb2f7` |
| Actual [PR13](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/13) merge | `3d5880885f1f99d05851ff9fa18d4b368106b121` |
| Actual merge parents, in order | `58817a8749d63f7c72c7452c2225f687372f6e9f`, `0a552d93fb2518fdc03697f21e560ec1db312999` |
| Actual merged tree | `ab23bb3637dc0d635f2673c75ca3dcbef5a1c86a` |

Controller verification binds all **370 paths** to the exact disjoint composition:
**37 DEV06 paths plus six separately reviewed GOV-02 documents** relative to the
original common base, with no product/test/workflow drift from the final DEV06
head. The actual merged tree includes GOV-02; it is not asserted identical to
the pre-GOV-02 DEV06 head tree. Git executable modes were separately reconciled;
permissions stripped from historical frozen copies are not Git tree modes.

Source: Controller frozen source-bound summary, packet cutoff
`2026-10-22T03:16:15.271716+00:00`, main readback `2026-10-22T03:01:13.194831+00:00`.
This Developer used no live GitHub access and did not repeat the private audit.

## Separate decisions and preserved failure history

| Stage | Decision and scope |
|---|---|
| H0 product review and acceptance | Independent **APPROVE_FOR_MAIN_ACCEPTANCE**, zero findings; original Controller **MAIN ACCEPTED** at `2026-10-18T14:48:29.944471+00:00` for H0, validation009 **116/116**, **43 requirement items**, approved offline synthetic scope only. |
| Final frozen010 repair review | Independent **APPROVE_FOR_MAIN_ACCEPTANCE**, zero findings, for the four-file delta; management subsequently verified hosted results. This is distinct from the original product review. |
| Repair delivery decision | **ACCEPTED_FOR_AUTHORIZED_CI_REMEDIATION_DELIVERY**, bounded to that repair delivery; not H0 acceptance rebound to the final head. |
| New final-head Controller decision | **ACCEPTED_SCOPED_PREMERGE**, `2026-10-21T13:36:35.874566+00:00`, binding final head, original base and head tree above. Original decision **DEV06-CLOSEOUT-20261021** remains dated premerge evidence. |
| Human merge decision | **HUMAN-MERGE-PR14-PR13-20261022**, 2026-10-22, approved PR14 then PR13 only; no archival merge authorization or gate waiver. |
| Actual postmerge disposition | **ACCEPTED_SCOPED_POSTMERGE_SOURCE_AND_EVIDENCE_FORMAL_HANDOFF_PENDING**, recorded `2026-10-22T03:14:55.763879+00:00`. Actual merge/source and scoped applicability verified; **PRIVATE_TRANSFER_READY**; formal handoff pending. |

Private originals stay outside the public repository. The following are
Controller-verified provenance digests; they are not links to public receipts:

| Private source | Date | SHA-256 |
|---|---|---|
| DEV06-CLOSEOUT-20261021 | 2026-10-21 | `5f3447a007d233d92b2940557ac4958fd4257d624665faf0696f7b4bd0463cd4` |
| HUMAN-MERGE-PR14-PR13-20261022 | 2026-10-22 | `3a79c12ea4ee665c57034d42049ff5cfe6fc4ffe0de81a97ca28a03523ff8c97` |
| DEV06 postmerge source/evidence disposition | 2026-10-22 | `9cb02d559ca16241803bf674ad11c32c45983a2d67a6ea56499cb4aff4e8b789` |

The earlier closeout verification bound 26 referenced evidence digests and actual
runtime; it did not rerun product tests or independent review. Independent private
review is not a native GitHub Review. Changed head/base, owned interface/authority,
new findings, superseding failed CI or evidence mismatch require targeted renewed
disposition. Current reuse is expressly limited to the verified composition above.

Local001–004 and local006–008 retain their **FAIL** history. Local005 remains
**INCOMPLETE**, no final receipt, cause **UNKNOWN**. H0 hosted DEV05 on both
Python versions retained **43 tests: 41 OK / 2 errors** when historical direct
source guards rejected separately approved DEV06 edits. H0 hosted DEV06 on both
versions was cancelled at the confirmed outer **15-minute** limit; archived
**RUNNING / completed=false / isolation NOT_ESTABLISHED** remains non-success.
Later success does not erase any of these observations or establish local005's cause.

## Test and CI provenance reused within scope

All seven final PR workflows / twelve jobs succeeded in the supplied receipts:

| Workflow | Public run | Jobs | Scoped recorded coverage |
|---|---|---|---|
| Phase0 | [39595721914](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/39595721914) | 1 | 6 |
| DEV01 | [39595721871](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/39595721871) | 1 | 48; Python-level guard, not S2 |
| DEV02 | [39595722065](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/39595722065) | 2 | 119 per Python version |
| DEV03 | [39595722138](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/39595722138) | 2 | 36 per Python version |
| DEV04 | [39595722202](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/39595722202) | 2 | 34+34 paired; 10 boundary; 3 traces |
| DEV05 | [39595721970](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/39595721970) | 2 | 43 per Python version; S2 |
| DEV06 | [39595721989](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/39595721989) | 2 | 119 per Python version; S2 |

Ten DEV02–06 jobs checked `0a552d93fb2518fdc03697f21e560ec1db312999`. Phase0 and DEV01's two jobs
checked temporary PR merge `2fa9fac802d83e8e72bebf0da36212cfab7677e0`, the same
source tree as that head; this is **not the actual PR13 merge**. Run metadata
alone does not establish checkout. Prior verification covered **12 checkout
logs, 11 artifact ZIP digests and 10 source archives**. Postmerge bounded reuse
verified the referenced evidence hashes and all 12 log hashes; it did not repeat
the full downloads/audit. This archival Developer did neither product execution
nor that historical audit.

Local repair evidence reports DEV05 **43/43** and DEV06-suite **119/119**;
the latter is **84 DEV06 + 35 selected DEV05**, with 35 overlapping methods.
Do not sum them as 162 unique tests or additional acceptance definitions.
Original H0's 116 is **81 + 35**. Requirement coverage remains its separately
qualified **43 items**, not an inference from method counts.

Actual merge-SHA readback found **zero runs, zero check-runs and zero legacy
statuses**, across all events with pagination verified. The empty legacy combined
label **pending** is neither tested PASS nor an observed test failure. No actual
merge-SHA CI was dispatched. Controller applied **postmerge-ci-plan/2** affected
scope reuse to unchanged product/test/workflow/interface assumptions; the original
PR-triggered provenance is retained. A universal actual-merge CI rerun is not
claimed or required by this bounded evidence plan.

## Inherited interfaces, scientific boundaries and risks

Consumers inherit accepted local control and **visit-aware storage /2** semantics:
authorization and owner epoch/control fencing, reservations and outbox/inbox,
budget liability, PAUSED/UNKNOWN, and conservative project/shared-pool recovery.
Current authority remains necessary; cached receipts or hashes do not supply it.
The four-file repair supplies no new API or persistence behavior.

Old **visitless /2** history is intentionally rejected, including old as-of and
pool paths requiring full ancestry checks. There is no weak reader, automatic
migration, format downgrade or liability-clearing path. Trusted synthetic
registry/root/producer assembly remains an assumption. Project and shared pool
are two conservative ledgers, not a distributed atomic transaction;
UNKNOWN/HELD/tombstones or unreadable registered roots can block progress.
Do not clear liabilities or blindly retry UNKNOWN.

Preserve immutable original target/D0, TRH P0–P14, FDH D0–D5 and one logical
Research MAIN; Context, Statement, Argument, Example, SourceEvidence and
Assessment retain provenance, exact assumptions, proof support, independent
review, qualification and dependency-scoped invalidation. Software tests, hashes,
valid JSON and SDK checkpoints are neither human consent nor mathematical proof.

AST comparisons outside allowed sections do not reject all formatting/comment
changes. Frozen boundary artifacts and validators must remain paired; changed
source, pins or ownership require targeted review. Genuine007 old-fixture direct
paired execution covers HEAD/as-of/pool only; cached/send/ingest/science/recovery/
acquire/release/prove-unsent were not individually paired on that fixture.
Other static and constructed-case evidence keeps its own scope. There is no
universal filesystem, power-loss or SIGKILL guarantee.

Full original **58+46 aggregate**, full legacy/native/provider/browser/PDF/doctor,
real backend transport and unselected stress matrices remain **NOT_EXECUTED**.
Real research/project access, paid product-model calls, production activation,
scientific migration, old-project recovery and budget increases are outside scope.
Management inference is **NOT_MEASURED**, not measured zero. Inherited
REV02-HELPER-01 stays accepted nonblocking **INCONCLUSIVE / NOT_EXECUTED** and
cannot be sole integrity or merge authority.

## Formal handoff gate, next cycle and rollback

Existing DEV06 premerge plan step 6 and merge-readiness step 6 require this public
archive to receive independent exact-head review, separate Controller acceptance,
root publication, separate human merge approval, actual merge into main and file
readback **before formal HANDOFF COMPLETE**. Root reverified this original gate;
**no human waiver exists**. Verified original merges and private transfer readiness
do not close it. This candidate embeds no future archive SHA/PR or acceptance.

[PROGRAM-CONTROL](../PROGRAM-CONTROL.md)'s existing grant covers bounded successor
work, subject to dependencies, appointed roles and a recorded package freeze.
DEV07 read-only preparation is completed; implementation has not started and
awaits the formal DEV06 archive/handoff gate plus its own appointment/input/scope
freeze. DEV11 is in bounded implementation; final independent review, overall
Controller acceptance, public merge and handoff remain absent, and final integration
follows existing ordering. DEV08/13 have read-only preparation only; other future
packages are unimplemented. Global control freezes successor baselines, consumers,
interfaces and affected acceptance IDs; unchanged evidence may be reused within
scope, while changed assumptions require targeted checks and review. Research
MAIN strategy/mapping v0.1.0 remains the approved specification; DEV11/12/13 must
name applicable RMAIN-REQ and K/O/S/GUIDE cases at their package freezes.

This Developer authors only four scratch documents and performs static checks;
it does not accept, review, publish or start a successor. Formal tag/Release and
DEV15–17 reserved execution/adoption/migration decisions still need the human.
Rollback after merge needs a separately reviewed, human-authorized revert that
preserves journal/blob evidence, compatible readers and UNKNOWN liabilities.
Never rewrite history, downgrade /2, delete evidence, resume PAUSED, expand budgets
or access live projects as an archival rollback.
