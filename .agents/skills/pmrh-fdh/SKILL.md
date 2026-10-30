---
name: pmrh-fdh
description: Discover and compare PMRH conjecture formulations within a fixed D0 phenomenon and allowed adjustment axes. Use for 表述发现、构造猜想、比较候选命题、调整量词或假设. Use pmrh-trh to prove an already fixed target and pmrh-summary to summarize existing candidates without further discovery.
---

# PMRH formulation discovery

**Input:** the original D0 phenomenon, immutable background, allowed adjustment axes and sources; for continuation, the authorized instance, snapshot and remaining budget.
**Output:** versioned candidate formulations, distinguishing evidence and reasons for changes, or a precise OPEN gap. Candidate adoption and a new TRH are separate decisions.

1. Read the [current state](../../../docs/development/PROJECT-STATE.md) and relevant [shared core contract](../../../docs/development/FOUR-SKILL-CORE.md) sections. Load D0 and only the candidate/evidence slice needed now.
2. Read existing status before continuation. Use `research_studio.knowledge_access.get`, `history` and, when needed, `dependencies` through the same authorized store/context. Keep original D0, allowed axes, candidate identities and unsuccessful attempts intact.
3. Scientific strategy and D0–D5 selection belong to this FDH instance's Research MAIN. Step 2 does not connect production research execution; stop at that capability gap before dispatch. Do not start a legacy runner or another MAIN to bypass it.
4. In a later supported, explicitly authorized bounded round, compare candidates with exact assumptions, quantifiers, examples and support through the existing MAIN/control and persistence path. Keep incomparability, conditional support and OPEN results visible.
5. Return the requested candidate comparison and stop. Ordinary writing does not trigger formal D5. Neither adoption nor a handoff may rewrite the FDH identity or automatically launch a TRH. Preserve D4 independence and the existing formal evidence gates.
