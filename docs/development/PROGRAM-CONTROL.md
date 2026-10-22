# PMRH program control — 2026-10-21

This public contract records the existing explicit human long-term development grant. It serves global control, package Controllers, Developers, independent Reviewers and the human deciding merges, optional adoption and releases. It changes development governance and state indexing only; product behavior, scientific authority and acceptance definitions do not change.

## Grant and authority

- Public grant: **HUMAN-PROGRAM-GRANT-20261021**, dated **2026-10-21**.
- Exact source SHA-256: `a2e8e60b1f85736a66960827772f68ed03f380dbf3400f5e7df6eb4179704611`.
- Effective **immediately from the explicit human decision**. GOV-02 review/merge records the grant; it does not activate or enlarge it. The private original remains private. The identifier/digest is provenance, not a bearer token or substitute for authenticated authority.
- Granted: **GOV-02 governance/state; DEV06 closeout; DEV07–14 bounded development; DEV18 integrated acceptance and release-candidate preparation**.
- Reserved human decisions: **each PR merge; formal tag/Release; DEV15 experiment execution; DEV16 backend adoption and implementation; DEV17 migration-tool development and actual migration**. Read-only proposals may be prepared. Adoption dispositions must explicitly record `adopt`, `do-not-adopt` or `defer` when decided; currently DEV15–17 are **PENDING_HUMAN_DECISION**.
- Excluded: real scientific research or project access, paid product-model calls, old-project recovery, production activation and budget increases. New or revised scope outside the grant needs a human decision.

Within the granted scope, this dated amendment reconciles repeated per-package human-startup wording in [AGENTS](../../AGENTS.md), [CONTRIBUTING](../../CONTRIBUTING.md), [MAIN protocol](MAIN-OPERATING-PROTOCOL.md), [ROADMAP](ROADMAP.md), earlier handoffs and ADR authorization wording. The explicit human grant supplies authorization; neither roadmap position nor an archive does so. The original dependency graph, scientific constraints and reserved decisions are unchanged. GOV-02 itself remains a Developer-authored package pending independent final-head review, separate Controller disposition and human merge; no own final SHA, PR or handoff is predicted.

## Persistent global control and bounded package roles

| Role | Required actual model/effort | Responsibility and boundary |
|---|---|---|
| Global control | gpt-6-astra / xhigh | Remains appointed across package handoffs; coordinates in-scope successors after dependencies and verified handoff/freeze, maintains program evidence, and arbitrates architecture conflicts. No repeated human startup request within the grant. |
| Package Controller / Development MAIN | gpt-6-astra / high | Separately appointed per package; freezes scope, coordinates evidence/review/remediation, issues a separate scoped MAIN decision, verifies authorized merge and handoff. Cannot self-appoint successor work. |
| Developer | gpt-6-astra / xhigh | Implements only the assigned delta and authorized checks; supplies exact evidence and limitations. Cannot self-review, accept or merge. For GOV-02, authors scratch documents only. |
| Independent Reviewer | gpt-6-astra / xhigh | Fresh independent context and read-only frozen source/packet; inspects the final committed delta and evidence, records findings and recommendation for that head. Cannot implement or accept its own reviewed delivery. |
| Human | Human authority | Decides reserved merges, optional execution/adoption/migration, formal release and changes outside the grant. |

Required configuration is not evidence that any historical or unappointed future role used it. Record actual appointments and verification privately; publish only the applicable policy and evidence conclusions. Development management never appoints a second scientific Research MAIN or grants product-model authority.

## Actual runtime and confinement gates

Before substantive source work, verify the fresh runtime's actual thread/turn, model, effort, approval policy, permission profile and filesystem/network records. Gate on observed records, not requested settings or prompt claims. Disclose global/Controller host privileges, including network/publication capabilities where present; do not imply those hosts share task confinement.

Developers receive only authorized input and scoped writable output. A Reviewer receives read-only source and evidence with scratch-only writes, independent context and no Developer mutation capability. Block task network. Use parent **and child** probes for source/input write denial without changing their bytes, outside-scope access denial, permitted scratch write/read/delete and network denial. A successful task launch or a Python-only guard is not proof of OS isolation. After probe PASS, Controller independently verifies the receipt and freezes the input packet; a second VERIFIED gate must match the actual turn before reading substantive source or authoring. Keep the exact gate/probe evidence private and hash-bound.

On runtime/ACL/probe mismatch or CLI/security rejection, stop the affected task and preserve the exact error. Do not silently fall back, weaken permissions, change model/effort or rerun under broader privileges. Arrange an authorized corrected environment before a fresh verified attempt. These are evidence requirements, not a grant of OS privileges.

Global control or the package Controller acquires fresh primary GitHub evidence at intake and after authorized merge; isolated Developers/Reviewers consume the frozen packet and disclose its cutoff. They do not bypass blocked network to satisfy older live-fetch language. Public records use supplied public URLs and repository-relative evidence links, without private conversation text, actual runtime IDs, host paths, personal packets or logs.

## Package freeze and dependency discipline

Before implementation, record the smallest useful deliverable, its direct consumers, owned files and interfaces, exact source baseline, mandatory dependencies, approved specification/ADR versions, non-goals, inherited acceptance IDs and positive/rejection examples, tests and evidence, independent review, rollback, role ownership and handoff criteria. Use [ROADMAP](ROADMAP.md) for structural edges and [ledger](DEVELOPMENT-LEDGER.json) for the dated status axes. Authorization alone does not satisfy dependencies or appoint roles.

Read [PROJECT-STATE](PROJECT-STATE.md), the relevant latest handoff and earlier inherited contracts, [ADR-0001](../architecture/ADR-0001-naming.md), [ADR-0002](../architecture/ADR-0002-constraints.md), applicable [ADR-034](../decisions/ADR-034-local-body-locators.md), [acceptance baseline](ACCEPTANCE-BASELINE.md) and [acceptance mapping](ACCEPTANCE-ADDENDUM-04-11-12.md). Research MAIN strategy/mapping v0.1.0 were approved under [PR8's formal decision](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/8#issuecomment-6185982722) and merged at `f724c06b54b157abe580cdf046f4fc08bb01c144`; their old candidate labels are historical. For DEV11/12/13 freeze applicable RMAIN-REQ clauses, inherited K/O/S/GUIDE cases, software responsibility and non-goals. The old Library proposals are not adopted wholesale; the original 58+46 definitions remain unchanged.

Default product work is sequential. Current disjoint assignments are:

| Assignment | Owned work | Gate |
|---|---|---|
| GOV-02 | AGENTS.md, CONTRIBUTING.md, MAIN-OPERATING-PROTOCOL.md, PROJECT-STATE.md, PROGRAM-CONTROL.md and DEVELOPMENT-LEDGER.json; the last four under docs/development | Documentation on frozen main `4239f15ad1233cc89cd6556cec284951b5fc2e3e`; Controller copies allowed authored bytes only after checks. |
| DEV06 closeout | Read-only final-head disposition/evidence, retained privately | Separate Controller decision **ACCEPTED_SCOPED_PREMERGE / READY_FOR_USER_MERGE_DECISION** at PR13 head `0a552d93fb2518fdc03697f21e560ec1db312999`; human merge remains pending and HANDOFF COMPLETE is not declared. |
| DEV07 preflight | Global read-only interface/consumer preparation, retained privately | No product start or package appointment. DEV06 scoped final-head acceptance is recorded; implementation still awaits human DEV06 merge, verified handoff and DEV07 appointment/freeze, with that acceptance remaining valid. |

The GitHub metadata cutoff remains **2026-10-21 13:30:58 UTC**. A later decision supplement, verified at **2026-10-21T13:39:53.644980+00:00**, records **DEV06-CLOSEOUT-20261021**, dated **2026-10-21T13:36:35.874566+00:00**, source SHA-256 `5f3447a007d233d92b2940557ac4958fd4257d624665faf0696f7b4bd0463cd4`. The new actual gpt-6-astra/high package Controller issued scoped final-head acceptance for the approved local/offline synthetic DEV06 plus the separately tested and independently reviewed four-file CI repair, at the head above and base `4239f15ad1233cc89cd6556cec284951b5fc2e3e`. Global control verified the runtime and all 26 referenced evidence digests; the package Controller verified the source decision digest. This is Controller-attested provenance from a **private original**, not a claim that the decision is public PR13 content. H0 acceptance, repair recommendation and bounded repair delivery decision remain distinct; no product tests or independent review were rerun. Changed head/base/owned interface/authority, a new finding, superseding failed CI or evidence mismatch invalidates this readiness. See [PROJECT-STATE](PROJECT-STATE.md) and the [ledger](DEVELOPMENT-LEDGER.json).

GOV-02 and DEV06 source paths are disjoint; recheck actual main at every authorized merge rather than assuming either merge order. Future parallel coding requires recorded file/interface ownership, frozen bases and update policy, dependency/merge order, global control as the architecture arbiter and independent gates for each package before coding. No concurrent product work is implied here.

## Evidence, acceptance and handoff

Keep authorization, implementation, tests, independent review, MAIN acceptance, GitHub merge and handoff as separate axes. Each actual delivery records exact base/head, changed paths and behavior, commands/subprocess/network/write scope, environments and raw outcomes, exact public CI links, unexecuted checks, risks/security and rollback. No green workflow, valid JSON or review recommendation substitutes for a separate Controller decision bound to the final head. A private independent review is not a native GitHub Review.

Preserve failed/incomplete runs and accepted limitations. Reuse unaffected audited evidence only with its original provenance and scope; fresh metadata readback is not a new full artifact audit. Changed heads need targeted independent re-review and explicitly bounded acceptance. In particular, H0 product acceptance and later CI-repair delivery decisions cannot be silently combined into final-head product acceptance. Do not relabel PR test-merge CI as actual merge-SHA CI.

After independent review and a separate MAIN decision, the human decides merge. Never force push, auto-merge or self-approve. Verify real main, actual merge/parents/tree, source/CI provenance and preserved evidence, then record handoff. The outgoing package Controller stops new-package initiatives; persistent global control coordinates any in-scope successor. A merged archive alone does not prove a historical HANDOFF COMPLETE declaration. Record later GOV-02 final-head review, decision and merge externally after this snapshot is frozen; do not create circular claims within it.

DEV18 preparation does not authorize a formal release. DEV18 retains ROADMAP's dependency on DEV14, explicit disposition of DEV17 and DEV16 only if adopted. Do not invent a do-not-adopt decision to clear a gate. Stop scope-relevant review loops when required gates and material issues close; retain nonblocking limitations instead of discarding evidence or repeating unrelated work.

## Scientific invariants and rollback

Preserve TRH P0–P14 and FDH D0–D5, immutable original target/D0 and exactly one logical Research MAIN per instance. Keep Context, Statement, Argument, Example, SourceEvidence and Assessment immutable, with precise provenance, assumptions, proof support, independent mathematical review, qualifications and dependency-scoped invalidation. Fast Knowledge Modules, Transitions, Research Maps, Frontier/Probe, ReaderProfile and RefinementBinding require detailed slow evidence; no summary, model output, JSON, software test or governance decision proves a theorem.

Preserve authenticated human grants, budgets, PAUSED, UNKNOWN, exact raw invocation/capture evidence and conservative crash recovery. Never blindly retry UNKNOWN. Separate domain policy, application control, engine, AgentRunner and ModelProvider. Observer/advisor proposals cannot become MAIN control, canonical scientific evidence or HUMAN guidance without authenticated approval. Keep UI/evidence/report duties until safe functional equivalents are demonstrated. Full 58+46 aggregate, real backend/production/research/migration remain NOT_EXECUTED in this snapshot; management inference is NOT_MEASURED.

Before merge, retain receipts and abandon/revise only within authorization. After merge, use a separately reviewed and human-authorized revert PR. Never rewrite original Git history or roll back by deleting journals/blobs, downgrading scientific formats, clearing UNKNOWN, resuming PAUSED, altering budgets or touching live projects. Reverting documentation does not revoke the human grant; a new human decision controls that authority.
