# PMRH current development state

Observed: **2026-10-30 20:12 Asia/Shanghai**. This page describes the four-skill delivery; it does not claim to inventory all preserved local development.

- Actual main: [`2844fe8ca58e627d8e6e7b21d497259082ef60d0`](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/commit/2844fe8ca58e627d8e6e7b21d497259082ef60d0).
- [PR #16](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/16) merged at **2026-10-30 18:39:03 Asia/Shanghai**. Its accepted HEAD was `ba9124145cffde7b061faf195f34f9372ba8898c`; local Git readback confirms the actual merge and candidate share tree `6c834e84710383f8cba27820bee4dafeb3aea622`.
- Current development branch: `feat/four-skill-entrypoints`, based on that actual merge. The step-2 PR is for review; no permission to merge it or release follows.

## Available now

Public Python CLI: read-only project status via the [README](../../README.md). DEV01–06 and DEV11 are merged; DEV11 acceptance remains limited to its frozen synthetic scope. In this development branch, Codex can discover and explicitly select four repository-local entrypoints: `pmrh-kb`, `pmrh-summary`, `pmrh-trh`, `pmrh-fdh`.

## Current delivery

| Item | Actual result / limit |
| --- | --- |
| Step 2 | Four standard `.agents/skills/*/SKILL.md` files with distinct triggers, inputs/outputs, existing service calls and permission boundaries. |
| Shared implementation | One existing Python core, Journal and evidence; no Router Skill, new database, extra KB Agent or duplicate runtime. Root AGENTS and both README languages document the native selection. |
| Discovery | Actual Codex `skills/list` returned all four enabled skills with repository scope and exact paths, from both the repository root and its `pmrh/` subdirectory. Only initialize/initialized/skills/list were sent; no model turn was started. |
| Trigger check | Same-session semantic check of 10 requests: four primary outcomes, summary-of-TRH, explicit selection and an unrelated request are distinguished. This is not an extra-model routing benchmark. |
| Call smoke | Four offline unittest methods cover all four status entry uses, shared search/get/dependencies/history, forbidden exact refs, PAUSED/UNKNOWN, unchanged historical SURVEY, missing projects and unsupported CLI commands. The new tests are included in existing Phase0 CI. |
| Reused evidence | DEV11's original [run 39978666796](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/39978666796) and scoped acceptance: 108 = 93 core + 15 storage; product bytes unchanged by step 2. This remains original PR CI, not a new merge-SHA run. |
| Checks not claimed | No separate PR16 merge-SHA CI was dispatched or certified here; no new full-product audit or old heavy-suite rerun. Native discovery and direct service smoke do not establish complete research-loop operation. |

## Permissions and inheritance

Use the [shared core contract](FOUR-SKILL-CORE.md) and only the selected Skill plus needed evidence. Summary is the user-facing Survey entry; old SURVEY kinds, events, schemas and S0–S7 remain unchanged and readable. TRH/FDH strategy stays with each Research MAIN. No instance, evidence or control mutation, paid research, production activation, budget increase or paused-instance continuation is authorized merely by skill selection.

Preserve original target/D0, precise assumptions/references, six native scientific records, evidence qualification, independent scientific review, single logical MAIN, budgets and PAUSED/UNKNOWN. Formal TRH completion retains TARGET_DUAL/P9/P12; FDH retains D4. A saved result, summary or passing engineering test is not proof.

## One next task

After review/integration of step 2, implement guide 03's first **Knowledge Base + Summary** chain: selected material → supported authorized persistence → exact retrieval → cited summary, including a duplicate-input case and a concrete failure case. Reuse the existing services; stop when that first chain works. No step-3 implementation or TRH/FDH research dispatch began in this delivery.

## History

The former long status is preserved in [Git history at the merged baseline](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/blob/2844fe8ca58e627d8e6e7b21d497259082ef60d0/docs/development/PROJECT-STATE.md). Its October 22 archive-pending labels and the [DEV11 delivery](DEV-PR-11-DELIVERY.md)'s source31 heading are dated snapshots; the later source25 addendum records completed DEV06 formal handoff and PR16 contains source43's final success and retained timeout failures. [DEVELOPMENT-LEDGER.json](DEVELOPMENT-LEDGER.json) remains dated evidence. Existing private control records and paused out-of-scope work were not modified.
