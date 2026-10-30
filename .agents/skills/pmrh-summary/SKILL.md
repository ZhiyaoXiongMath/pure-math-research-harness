---
name: pmrh-summary
description: Write a source-grounded PMRH summary of specified papers, chapters, knowledge objects, or research progress, including requests phrased as Survey or 综述、总结论文、整理研究进展. Use for a readable synthesis; use pmrh-kb for database maintenance, pmrh-trh to pursue a fixed theorem, or pmrh-fdh to discover formulations.
---

# PMRH Summary

Summary is the user-facing writing entry, including requests formerly called Survey. It runs independently of the other three skills.

**Input:** selected materials, exact knowledge references or an authorized project snapshot, plus audience, language and requested output.
**Output:** a readable synthesis with precise sources, actual coverage and explicit gaps; no research-completion decision.

1. Read the [current state](../../../docs/development/PROJECT-STATE.md) and relevant [shared core contract](../../../docs/development/FOUR-SKILL-CORE.md) sections. Expand only evidence needed for this writing task.
2. Read supplied text directly within its authorized scope. For stored material, use `research_studio.knowledge_access.get` with the supplied store/context and exact reference, searching only when necessary. Do not require the user to run `pmrh-kb` or an extra KB Agent first.
3. When persistence is supported and authorized, call the SAME `pmrh.application.kb_summary.KnowledgeSummary.prepare` directly, including material bytes, identity, actual origin, request and selected ranges. `REUSED` returns the saved result without a model call. Otherwise the host supplies one frozen native extraction task and its original capture; `complete(plan_ref, request_id)` admits native objects and derives cited Markdown from their bodies, and `export` returns the saved output. Read the short [adapter guide](../../../docs/development/KB-SUMMARY.md) as needed. Current persistence is synthetic-only; report absent authenticated production assembly before real project writes. Do not construct fake host/capture/permission objects.
4. Write the requested definitions, main results, mechanisms, proof outline and limitations as appropriate. Preserve all hypotheses and quantifiers needed by the claims; distinguish a source's claim from verified proof and missing text from read text. On uncertainty inspect the original request/operation receipt; do not start another call.
5. Read historical `SURVEY` instances through the unchanged status/snapshot services. Keep their kinds, event names, identifiers, schemas and S0–S7 records unchanged. This naming transition authorizes no migration or execution of legacy workflows.
6. Deliver the requested text or authorized output file and stop. Storage and extraction confer no independent mathematical qualification. Do not finalize a TRH target, trigger FDH D5, or resume research just because a summary was requested.
