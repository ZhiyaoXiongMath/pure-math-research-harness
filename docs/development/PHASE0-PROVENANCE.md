# Phase 0 — read-only Git provenance verification

**Checked:** 2026-10-12, using independently connected GitHub Git refs, Git commits, Git trees, annotated tags and compare endpoints. **Scope:** observable Git object identity; not a reconstruction of local Codex's terminal transcript or private pre-migration scan.

- Source: `ZhiyaoXiongMath/Pure-Math-Research-Studio` (`private`); original `4.2.2-preview` is `e4de0210f9985224e030ac4cfd2f7e2904005b37`.
- Target: `ZhiyaoXiongMath/pure-math-research-harness` (`private`), default `main` initially at the same commit.
- The fixed commit has tree `c17a592ff0a4906afa7a6423535f41c67c926128`, parent `bc2225d1baca3e6b01693622967d7eeb26e5d82d`. The target Git compare reports one commit ahead of that parent, no divergent commit.

| Source ref | Exact source object SHA | Target ref | Target object confirmed? |
|---|---|---|---|
| `refs/heads/4.2.2-preview` | `e4de0210f9985224e030ac4cfd2f7e2904005b37` | `refs/heads/4.2.2-preview` and initial `refs/heads/main` | yes |
| `refs/heads/main` | `bc2225d1baca3e6b01693622967d7eeb26e5d82d` | `refs/heads/archive/pmrs-original-main` | yes |
| `refs/tags/v4.0.0` | `3c176c678af33825ed40b963134ada0b3d942eec` | same | yes |
| `refs/tags/v4.1.0` | `35cee188672bb1dd0199d02d3fe1f170a9e806d7` | same | yes |
| `refs/tags/v4.2.0` | `08dc6d711c16cf3d119bcd29e4336fba081b7877` | same | yes |

Annotated tag targets also match between source and target: `v4.0.0` → `21cb551f4ef6fa3a4efd91587bc5ef3b56c0c938`; `v4.1.0` → `ab450484aa53d01c0e18a7237410e20cdf114736`; `v4.2.0` → `bc2225d1baca3e6b01693622967d7eeb26e5d82d`.

**Full reachable history argument:** identical reachable head commit IDs recursively bind their parent commits and tree/blobs; identical annotated tag object IDs bind their target commits. GitHub resolved the fixed commit/tree, original main and all six refs without truncation (tree 229 entries, 206 blobs). This supports Git-object-identity preservation of all history reachable from those refs; an independently downloaded `git rev-list --objects --all` diff was **NOT_EXECUTED** in this Chat because authenticated Git transport remains unavailable. The original transfer process, absence of `--force` or `filter-repo`, and pre-migration scan commands cannot be reconstructed from GitHub refs alone. Ask the local Codex operator for sanitized receipts; do not label that procedural check PASS merely from matching objects.

**Licenses:** preserve root Apache-2.0 `LICENSE`, `research_studio/native/LICENSE`, `docs/native-goal-APACHE-LICENSE`, `docs/NATIVE-RUNTIME.md`, and MathJax 3.2.2 source/license manifest in `research_studio/static/vendor/`. No original source/notice file is deleted in Phase 0. GitHub platform Issues, PR comments, Actions and releases are outside Git object history.

**Privacy:** Phase 0 developer did not access private scientific projects or scan local research directories; GitHub's final tree filename inspection does not replace an all-history sensitive-object scan. No credential content is transcribed here. Migration receipts from the local Codex workstation were not supplied to this Chat. If later receipts identify a leaked credential or private research material, stop publication/merging and seek explicit remediation approval; never rewrite history unilaterally.
