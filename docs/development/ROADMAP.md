# PMRH development work packages — PLANNED, not GitHub Pull Requests

`DEV-PR-01` through `DEV-PR-18` are **planning IDs** from §13 of the 2026-10-11 [implementation plan](../reference/PMRS-Next_Phase1/02-Implementation-Plan.zh-CN.md). They are not GitHub issue numbers, actual PRs, assigned tasks or permissions to start work. `TRH-P01` is a targeted mathematical-research phase; `FDH-D01` is a discovery phase; neither is a software PR. The Phase 0 GitHub PR has its own ordinary GitHub number and is not `DEV-PR-01`.

| Work package | Description | Mandatory predecessors | Status |
|---|---|---|---|
| DEV-PR-01 | Safe AST baseline and isolated test entrypoint | Phase 0 independently accepted; separate authorization | PLANNED |
| DEV-PR-02 | Ports, DTO and explicit error contracts | 01 | PLANNED |
| DEV-PR-03 | Read-only queries separated from reconciliation | 01; align interfaces with 02 | PLANNED |
| DEV-PR-04 | Mathematical domain kernel extraction | 02 | PLANNED |
| DEV-PR-05 | Journal/blob Store and UnitOfWork adapters | 04 | PLANNED |
| DEV-PR-06 | Control, MAIN epoch, admission and outbox | 02, 05 | PLANNED |
| DEV-PR-07 | Codex AgentRunner / ModelProvider boundary | 02, 06 | PLANNED |
| DEV-PR-08 | Headless Supervisor and event wakeup | 07 | PLANNED |
| DEV-PR-09 | CLI event reading and safe diagnostics | 03, 06, 08 | PLANNED |
| DEV-PR-10 | Observer/Advisor with controlled guidance | 09 | PLANNED |
| DEV-PR-11 | Fast-math objects and RefinementBinding | 04, 05 | PLANNED |
| DEV-PR-12 | MAIN/worker slow+fast delivery contract | 07, 10, 11 | PLANNED |
| DEV-PR-13 | Reports and TRH/FDH delivery service | 05, 09, 12 | PLANNED |
| DEV-PR-14 | Remove self-built Web UI after equivalence | 08, 10, 13 and equivalence gate | PLANNED |
| DEV-PR-15 | Optional orchestration/runner offline evaluation | 07; separate experiment authorization | PLANNED |
| DEV-PR-16 | Conditional accepted backend adapter | 15 formal adoption decision; separate authorization | PLANNED |
| DEV-PR-17 | Authorized copy-only scientific data migration | 05, 06, 11; separate migration authorization | PLANNED |
| DEV-PR-18 | Integrated headless product and release | 14; explicit disposition of 17; 16 only if adopted | PLANNED |

Dependencies are structural, not scheduling permission. In particular 15–16 do not block 03/11/14. When no new backend is adopted, formally mark 16 as **not adopted** rather than creating a fake implementation. This document freezes the original §13 dependency graph; tests, individual file scopes and detailed rollback for each package remain authoritative in the copied implementation plan.

## Execution and acceptance gates

- **PLANNED:** only an approved specification exists. Does not mean code, PR, tests or permission to run.
- **IMPLEMENTED:** code/documentation was committed to a named SHA; does not mean tests passed.
- **TESTED:** specify exact head SHA, command, environment, output and supported claim.
- **REVIEWED:** recorded independent review, including open blocking concerns.
- **ACCEPTED:** explicit authority accepted the work; do not equate with a PR merge automatically.
- **NOT_EXECUTED:** test/verification missing or blocked; never present as PASS.

Phase gates: Phase 0 provenance/governance/bootstrap (current); DEV-PR-01 baseline/isolated runner; DEV-PR-02/03 interfaces and read-only query; DEV-PR-04..13 substantive domain and runtime; DEV-PR-14 UI retirement after functional equivalence; DEV-PR-15/16 optional adoption; DEV-PR-17 separately authorized copy migration; DEV-PR-18 product validation and release. Every gate needs a separate explicit user authorization. Do not start real research or touch project data in any development check.

**Rollback:** unmerged changes can be abandoned without rewriting `main`; merged software changes use a new revert PR. Preserve original heads and annotated tags. NEVER roll back scientific evidence or live MAIN/Goal via Git manipulation.
