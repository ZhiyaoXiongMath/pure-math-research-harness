# Four skills, one shared core

These are repository-local instruction entrypoints, not four runtimes. The current supported surface and missing capabilities are in [PROJECT-STATE](PROJECT-STATE.md).

## Native discovery and selection

Open Codex **inside this repository**. It discovers `.agents/skills/<name>/SKILL.md` from the working directory up to the repository root. Explicitly invoke `$pmrh-kb`, `$pmrh-summary`, `$pmrh-trh` or `$pmrh-fdh`; otherwise Codex selects by description. Default to one primary skill for the user's requested outcome. Do not add a Router Skill, custom classifier, mandatory skill chain or extra KB Agent. If a newly created skill is absent, refresh/restart Codex. A Python package installation alone does not install these repository skills.

| Requested outcome | Primary skill |
| --- | --- |
| Import/update sources, organize versions, retrieve stored references | `pmrh-kb` |
| Write a synthesis of selected material or current research | `pmrh-summary` |
| Pursue the original fixed proposition or its counterexample | `pmrh-trh` |
| Construct/compare formulations within immutable D0 and allowed axes | `pmrh-fdh` |

Select by the requested action: summarizing TRH progress is Summary; finding a counterexample to its fixed target is TRH; changing candidate hypotheses within D0 is FDH. Honor an explicit skill choice within that skill's capability and authorization boundaries; it does not grant new permissions. Read only the selected `SKILL.md`, this contract's relevant sections, short current state and exact evidence needed now.

## Calls to existing services

All four use the same project root, authoritative Journal, HEAD, writer exclusion and evidence. No skill owns a second database, service copy, lock, Python dependency set or research authority.

| Need | Existing entry | Availability / input and output |
| --- | --- | --- |
| Inspect an existing instance | `python3 -B -m pmrh status PROJECT --instance INSTANCE --json [--as-of COMMIT]` | Public read-only CLI; returns existing snapshot facts or explicit unavailability. Exit 0 = readable, 1 = unavailable, 2 = invalid/unsupported command. Never creates a missing project. |
| Search/read exact knowledge | `research_studio.knowledge_access.search(store, query, ...)` / `get(store, ref, ...)` | Existing Python service, not a new CLI. Use only a host-supplied authorized store/task context and scope; retain returned snapshot, locators, coverage, limits and continuation metadata. |
| Expand support/version links | `knowledge_access.dependencies(store, ref, ...)` / `history(store, ref, ...)` | Same context and exact refs; returns bounded relations/version views, not proof or authority. |
| Stage/commit a supported change | `pmrh.application.unit_of_work.UnitOfWork` with existing storage/policy/permit assembly | Existing constrained development service, not a general user KB importer. Step 3 adds the narrow synthetic [KB/Summary adapter](KB-SUMMARY.md); authenticated production host assembly remains unavailable. Never build trusted policy from project data or write journal files directly. |
| Prepare/capture/apply fast changes or recover a receipt | `pmrh.application.fastmath.FastMathService` | Use only its existing trusted same-root storage/Control assembly, registered identity, exact source/capture refs, current grant/epoch/version and budget. Frozen synthetic DEV11 acceptance is not production enablement. Recover original receipt/state before acting on an unknown result; never blindly resend UNKNOWN. |
| Interpret scientific records / protocols | `pmrh/domain/knowledge.py`, `assurance.py`, `relations.py`, `protocols.py`, `stages.py` | Shared six native record types, qualification and TRH/FDH rules. These modules are not an execution authorization. |

For example, KB searches with `knowledge_access.search`, Summary reads selected bodies with `get`, TRH expands exact premises with `dependencies`, and FDH reads candidate versions with `history`. Consumers may use any of these shared operations directly; they do not invoke another skill to perform ordinary I/O. If the required context or supported adapter is missing, report the precise gap; do not fabricate an API or strip a guard. Supplied documents can still be summarized directly without a project write.

The two material skills share `pmrh.application.kb_summary.KnowledgeSummary` for registration, selected reading, incremental preparation, original-capture admission and deterministic Markdown export. It uses the existing native Store and UnitOfWork on one Journal, retains synthetic protections, and makes no model call. See [supported use and recovery](KB-SUMMARY.md).

## Permissions and scientific boundaries

- Bind an existing-project request to its authorized root, instance, snapshot and requested operation. A read request authorizes no project, evidence or control mutation. Creating a requested output file is distinct from canonical scientific acceptance.
- Preserve original bytes/versions, exact refs and assumptions, provenance, native evidence, scoped invalidation, single Research MAIN, budgets and PAUSED/UNKNOWN. Do not forge producer identity, raw output, capture, human approval or a grant to satisfy a service contract.
- Formal scientific claims retain their existing independence and qualification gates, including TRH TARGET_DUAL/P9/P12 and FDH D4. Engineering tests, a summary and successful persistence do not establish proof.
- TRH/FDH strategy stays with the respective Research MAIN. No automatic paid research, continuation, budget increase, production activation, adoption or FDH-to-TRH launch follows from choosing a skill. Step 2 supplies no production execution adapter.
- Summary replaces the user-facing Survey name only. Historical `SURVEY` instances, identifiers, schema/event names, snapshots and S0–S7 remain readable without rewriting or resuming them. No other legacy migration/support expansion is implied.

## Development and verification

Use one work session, changed-scope checks and valid existing evidence. Default extra audit agents: zero. Add a single targeted independent check only for a concrete unresolved permission, qualification, identity, transaction or recovery risk; preserve scientific independence separately. No full audit, background scheduler or repeated historical tests for an instruction-only change.

Native discovery follows [official skill documentation](https://learn.chatgpt.com/docs/build-skills). Read-only `skills/list` through the [official app-server API](https://learn.chatgpt.com/docs/app-server) can verify names, enabled state, paths and discovery errors without starting a model turn. This is distinct from a model-driven routing benchmark or actual research execution.
