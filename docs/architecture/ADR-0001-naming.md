# ADR-0001 — Adopt `pmrh` as the new Python package and CLI

**Decision scope:** Phase 0 bootstrap identity. **Decision:** approved by the user's explicit Phase 0 authorization (2026-10-12); software acceptance pending independent review.

- Product: **Pure Math Research Harness** (PMRH).
- Python import package: `pmrh`.
- Distribution (`[project].name`): `pure-math-research-harness`.
- Console script: `pmrh`.
- Initial packaging metadata version: `0.0.0`, explicitly a *bootstrap identifier*, not a claim that the full research product has shipped.
- The existing `research_studio` import package, scientific schemas, historical version `4.2.2`, and three old CLI entrypoints remain legacy/compatibility code. They are **not** rebranded or automatically redirected into the new inert CLI.

**Correction to earlier planning:** the target layout shown as `pmrs/` in §2.1 of `02-Implementation-Plan.zh-CN.md` was a provisional package name. It is superseded **only as a new source-root/package name** by `pmrh/` and not by a wholesale rename of the original `research_studio/` tree. Names embedded in existing research evidence, historical schema identities, and archived docs are left unchanged.

**Consequences:** the Phase 0 CLI is intentionally limited to help/version and explicit rejection of all other commands. Full ports, DTOs, queries, runtime behavior and compatibility testing remain separate authorized DEV-PR work.

## Post-Phase 0 status annotation (2026-10-12)

The opening “acceptance pending” is original, **decision-time historical metadata**, not a live PR status. Phase 0 was later [accepted by Development MAIN](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/1#issuecomment-6120454287) and [merged as PR #1](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/1) at `977e866d64bba5cf7b5549f17a3d4b5599a4c20a`. This annotation does **not change the approved naming decision or any scientific invariant**. Consult [PROJECT-STATE](../development/PROJECT-STATE.md) and live GitHub.
