---
name: pmrh-trh
description: "Pursue a fixed PMRH mathematical target: prove the specified proposition, seek its counterexample, or continue an explicitly authorized TRH instance. Use for 固定命题、继续证明、寻找反例. Use pmrh-summary for progress writing alone and pmrh-fdh when the task is to choose or change the conjecture itself."
---

# PMRH targeted research

**Input:** the exact original target with hypotheses and conventions, source references, and either a new-task request or the existing authorized instance, snapshot, budget and continuation scope.
**Output:** an explicitly scoped argument, counterexample, partial result or OPEN gap, with evidence and the actual execution status. Preparation is not a completed research round.

1. Read the [current state](../../../docs/development/PROJECT-STATE.md) and relevant [shared core contract](../../../docs/development/FOUR-SKILL-CORE.md) sections. Read only the target and evidence needed for the next bounded action.
2. For an existing instance, read status before any continuation. Resolve the exact target and its needed premises through `research_studio.knowledge_access.get` and `dependencies`, using the host's authorized store/context. Preserve original hypotheses, target identity, PAUSED/UNKNOWN, prior failures and cumulative budgets.
3. Scientific strategy and P0–P14 selection belong to that instance's Research MAIN. A skill selection does not appoint a second MAIN or authorize resuming a paused instance, paid inference or canonical writes. Current production research execution is not connected by this step-2 delivery; report that gap and stop before dispatch rather than invoking a legacy runner.
4. When a later supported, explicitly authorized bounded round is available, pass the fixed target and exact references to the existing MAIN/control path, persist through the shared services, and report only its actual result. Weaker conclusions remain partial results.
5. Stop at the requested bounded result or concrete capability/authorization gap. Formal original-target completion retains `TARGET_DUAL` and P9/P12 independence; a summary, saved record or successful software test supplies no mathematical qualification.
