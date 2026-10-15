# Future acceptance baseline — no implied PASS

The original audit bundle is copied byte-for-byte to [`docs/reference/PMRS-Next_Phase1/`](../reference/PMRS-Next_Phase1/). It freezes:

- **58 new software cases** (A01–A04, Q01–Q05, E01–E08, C01–C08, B01–B06, O01–O06, S01–S06, K01–K08, R01–R03, M01–M04): [implementation plan §15.2](../reference/PMRS-Next_Phase1/02-Implementation-Plan.zh-CN.md#152-最低软件验收矩阵).
- **46 inherited guide cases** (`GUIDE:K01`–`GUIDE:K16`, `GUIDE:C01`–`GUIDE:C16`, `GUIDE:P01`–`GUIDE:P14`): [implementation plan §15.3](../reference/PMRS-Next_Phase1/02-Implementation-Plan.zh-CN.md#153-既有指南-46-项验收的继承映射).

Both tables, including every scenario, expected rejection and assigned future PR, are copied unchanged. **Their execution status remains `NOT_EXECUTED`**, even if Phase 0 smoke tests pass. No software test can grant mathematical checked status, proof validity, a live MAIN grant or an observer write permission.

For each future case, append a reviewable receipt keyed by `(acceptance_id, source_commit, test_environment, test_invocation, raw_result, reviewer)` under a separately authorized implementation PR. Mark `TESTED` only for the exact covered claim; keep known limits. Independent MAIN must explicitly issue `ACCEPTED` only after review. Do not overwrite the baseline or retroactively convert the 2026-10-11 static audit into a product-test report.

## Research MAIN candidate addendum — indexed, not executed (2026-10-15)

The [Research MAIN candidate strategy](../architecture/RESEARCH-MAIN-STRATEGY.md) uses `RMAIN-REQ-01`–`12` for the user's original design R01–R12, to avoid collision with the baseline's **software R01–R03**. The [04/11/12 acceptance addendum](ACCEPTANCE-ADDENDUM-04-11-12.md) uses `RMAIN-MR01`–`10` solely as local indices for the original MR01–MR10 behavior scenarios and maps them to existing K/O/S/GUIDE/R cases, future package responsibilities and valid/invalid traces. It distinguishes (i) offline synthetic semantics, (ii) actual packet assembly/fake-runner delivery, and (iii) independently reviewed mathematical quality or separately authorized real-model evaluation.

The documents are **candidates** until independent review, separate Development MAIN acceptance and user-authorized merge. They create no new mathematical checked source, software PASS, new mandatory model/Lean/Agent/graph-database gate, or silent permission to implement DEV04/11/12. **Neither the exact 58+46 baseline cases nor their currently NOT_EXECUTED future status is altered.** Future authorized work should reuse valid scoped receipts, include legitimate-positive counterparts to rejection tests and limit review to affected assumptions/dependencies rather than repeat unrelated audits.

