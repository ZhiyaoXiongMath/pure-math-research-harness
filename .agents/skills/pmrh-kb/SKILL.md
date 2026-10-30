---
name: pmrh-kb
description: "Maintain PMRH sources and stored knowledge: import or update materials, register versions, search exact records, or organize an existing knowledge base. Use for 导入材料、更新来源、检索知识. Use pmrh-summary for a written synthesis, pmrh-trh for a fixed theorem, and pmrh-fdh for formulation discovery."
---

# PMRH knowledge base

Use this entry independently; ordinary reads and writes call shared services directly, without a separate KB Agent.

**Input:** user-selected materials or exact references; for an existing project, its authorized root, instance and snapshot; for changes, the requested operation and write scope.
**Output:** matching references and coverage, or a source/version/change receipt when a supported authorized write actually succeeds. A prepared import is not a committed import.

1. Read the [current state](../../../docs/development/PROJECT-STATE.md) and the relevant part of the [shared core contract](../../../docs/development/FOUR-SKILL-CORE.md). Load only selected materials or changed versions.
2. For an existing project, use the common read-only status call. With a host-supplied authorized store/context, call `research_studio.knowledge_access.search`, then `get` only for the exact bodies needed. Preserve snapshot, scope, truncation and source locators.
3. For import/update, retain original bytes and version relationships. Use the existing transaction service only when its trusted assembly, authorization and supported input path are available. The general user KB import/write adapter is deferred to step 3; until then return the concrete missing capability and a proposed import, without writing the journal directly.
4. Return what was read, found, changed or left unexecuted. Stop after this request; do not start writing a report or researching a theorem unless requested.

Storage does not confer proof status. Never manufacture capture provenance, an authorization grant or a successful receipt.
