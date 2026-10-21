# Current contribution amendment — 2026-10-21

[PROGRAM-CONTROL](docs/development/PROGRAM-CONTROL.md) records the immediately effective **HUMAN-PROGRAM-GRANT-20261021**. It replaces repeated package startup permission only for GOV-02, DEV06 closeout, DEV07–14 and DEV18 integrated acceptance/release-candidate preparation. Its effect comes from the human grant, not this documentation PR. The per-package-grant wording in the historical text and [ROADMAP](docs/development/ROADMAP.md) is reconciled within that scope; dependencies and reserved human decisions remain binding.

Read [PROJECT-STATE](docs/development/PROJECT-STATE.md), the [ledger](docs/development/DEVELOPMENT-LEDGER.json), [MAIN protocol](docs/development/MAIN-OPERATING-PROTOCOL.md), effective ADRs, acceptance baseline/addendum and relevant handoffs. Global control persists across handoffs; a package Controller completes only its appointed package. Global control may coordinate a successor after dependencies and handoff are verified and its smallest useful deliverable, consumers, baseline, interfaces/files, non-goals, acceptance IDs, tests/review/rollback and roles are frozen. Default product work is sequential. DEV07's current global read-only preflight is not implementation or package appointment.

Use actual gpt-6-astra/xhigh global control, gpt-6-astra/high Controller and gpt-6-astra/xhigh Developer and independent Reviewer. Verify runtime identity and effective permissions before source work; use scoped Developer writes, fresh read-only review inputs, blocked task network and parent/child filesystem/network probes. Disclose Controller host privileges. Stop and retain exact errors on mismatch or rejection; never silently change model or confinement. Public records summarize the gates without exposing private runtime identifiers or logs.

A Developer supplies a bounded delta and exact evidence; the independent Reviewer examines the final committed head; the package Controller separately decides MAIN acceptance. The human decides each merge. Then verify actual main, parents/tree and CI checkout provenance before handoff. This isolated GOV-02 Developer produces scratch documents only: Controller owns inspection, copying and publication. GOV-02 has no self-review, self-acceptance or predicted final SHA/PR/merge.

DEV15 experiments, DEV16 adoption/implementation, DEV17 migration tooling/actual migration and formal tag/Release remain **PENDING_HUMAN_DECISION**. Read-only proposals may inform those decisions. No development grant authorizes real research/project access, paid product-model calls, production, recovery or extra budget. Preserve scientific authority and raw evidence, original target/D0, single Research MAIN, PAUSED/UNKNOWN and no blind retry. Run only package-authorized checks; this documentation package uses static validation and does not rerun product suites or mark 58+46 PASS. Management inference is NOT_MEASURED.

## Historical content — original bytes retained below

The following text preserves its dated decisions and observations. Read current authorization and status through the amendment above; no missing historical evidence is repaired by this annotation.

# Contributing to Pure Math Research Harness

## Development status

Phase 0 creates a safe package identity and governance baseline, not a functional research CLI. The existing `research_studio` code and legacy entrypoints remain available but are **not** covered by Phase 0's no-side-effect guarantee. Never use live projects to exercise experimental code.

## Environment and checks

- Python >=3.11. The Phase 0 test suite uses only the standard library; no paid models, network probes, browsers, or native Codex binaries are required.
- From an isolated checkout, run `python3 -B -m unittest discover -s tests/phase0 -p 'test_*.py' -v` with temporary `HOME`, `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_CACHE_HOME` and `TMPDIR`, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONNOUSERSITE=1`, and `PIP_NO_INDEX=1`.
- Inert CLI smoke: `python3 -B -m pmrh --help`, `python3 -B -m pmrh --version`. DEV03 adds only `status PROJECT --instance INSTANCE --json [--as-of COMMIT]`; other command names remain unsupported. Use synthetic fixtures and the [DEV03 contract](docs/development/DEV-PR-03-CONTRACT.md) for its separate guarded suite.
- Do not run `research-studio`, `pure-math-research-studio`, `pmrs-desktop`, the historical test runner, `doctor`, native builds, or model integration tests under the Phase 0 gate.
- The historical `.github/workflows/final-candidate.yml` is a manual, self-hosted Ubuntu 26.04/browser product gate and is **not** equivalent to the new Phase 0 offline CI.

## Branches and commits

`main` initially preserves the migrated 4.2.2-preview baseline; `4.2.2-preview` and `archive/pmrs-original-main` are reference branches. Do not move or rewrite the legacy history or tags. Author changes only on a scoped `chore/`, `docs/`, `feat/` or `fix/` branch approved for the corresponding development phase. Phase 0 uses `chore/phase0-bootstrap`. Keep each commit reviewable with a descriptive imperative subject and a diff limited to its declared contract. Never force push or squash imported history.

## Review and acceptance

Use the pull-request template. Distinguish `PLANNED` (design only), `IMPLEMENTED` (code present), `TESTED` (matching actual execution receipts), `REVIEWED` (independent review recorded) and `ACCEPTED` (authorized acceptance). These labels apply per item; Phase 0 smoke does not test future mathematical obligations. For every missing test, write `NOT_EXECUTED` and why. Formal mathematical checked status is separate from all five software states.

Source hierarchy and boundary conflicts are specified in [AGENTS.md](AGENTS.md). A new implementation proposal cannot bypass original target/D0, scoped evidence, human authorization, PAUSED, UNKNOWN, or independence. Follow the 18-package dependency map in [ROADMAP](docs/development/ROADMAP.md) and retain the 58 + 46 acceptance baseline unchanged.

## Management cycles, independent review and post-merge handoff

The frozen [ROADMAP](docs/development/ROADMAP.md) tracks 18 planning packages and dependencies, **not live status or permission**. [PROJECT-STATE](docs/development/PROJECT-STATE.md) is the versioned management evidence index; [MAIN-OPERATING-PROTOCOL](docs/development/MAIN-OPERATING-PROTOCOL.md) governs roles, explicit user authorization, remediation, formal acceptance and post-merge transfer. Before starting, each new Development MAIN reads current rules, all active ADRs and the most recently completed Handoff relevant to the current work package (first example: [DEV-PR-01](docs/development/handoffs/DEV-PR-01.md)), then fetches **real** GitHub `main`/PR/review/CI and reports state conflicts. Original GitHub records control actual SHA/PR/CI facts; they cannot substitute for human consent.

Default one separately staffed Development MAIN for each planned DEV-PR cycle. Development Chat makes only the scoped branch, commits, tests and Open PR; Independent Review Chat audits exact source/evidence and records findings and a recommendation; Development MAIN separately decides `MAIN ACCEPTED`. `REVIEWED`, `MAIN ACCEPTED` and `GITHUB MERGED` are **not synonyms**. A developer must not self-approve, enlarge work or merge. After an authorized merge, verify `main`, merge parents and CI provenance before Handoff; the outgoing MAIN does not start the successor PR.

A next work package always requires **new explicit user authorization**, not PROJECT-STATE inheritance. Concurrent packages require prior agreement on file/contract ownership, frozen base SHA, dependency order and named architectural conflict coordinator. Scientific Research MAINs are separate from software governance MAINs.

## Rollback and data integrity

Before merging, the default rollback is closing the unmerged PR and deleting its development branch **only after authorization and preservation of receipts**. After merge, revert the software commit on a new PR. Do not reset, rewrite, delete scientific journal/blobs, purge UNKNOWN reservations or alter research projects as a form of rollback. No live project migration without separate explicit authorization.
