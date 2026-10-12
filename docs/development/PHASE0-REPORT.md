# Phase 0 developer handoff (for independent MAIN review)

**Scope:** `chore/phase0-bootstrap` only. Not DEV-PR-01, not research software acceptance. **Reviewer:** PMRH Development — MAIN (pending). **Merge:** not authorized.

## Delivered implementation

- GitHub object-level read verification of imported baseline, source/main map and all annotated tag objects; see [provenance](PHASE0-PROVENANCE.md).
- Exact preserved audit bundle under `docs/reference/PMRS-Next_Phase1/`: original guide, architecture audit, implementation plan, inventory, two JSON manifests, checksum and README. The 7 original checksums refer to unchanged sibling bytes.
- `AGENTS.md`, `CONTRIBUTING.md`, architecture ADRs, scoped roadmap, acceptance baseline and PR template, with development/scientific namespaces distinguished.
- New versioned Python distribution name `pure-math-research-harness`, inert import `pmrh`, console script `pmrh` and explicit unsupported return for all other commands. Legacy `research_studio`, CLI aliases, scientific schemas, UI and runtime remain untouched.
- `.github/workflows/phase0-safe.yml`: hosted, minimal `contents: read`, offline metadata/integrity/AST/import/smoke and read-only immutable Git provenance tests. Historical manual self-hosted workflow is unchanged.

## Tests and limits

The exact command for the developer's local isolated staging check is:

```sh
python3 -B -m unittest discover -s tests/phase0 -p 'test_*.py' -v
```

CI executes the same suite using isolated temporary HOME, XDG directories and TMPDIR with no model secrets. The smoke suite checks return codes for `--help`, `--version` and unsupported commands, plus unchanged temporary HOME/XDG/TMP directory structure. It does **not** prove complete operating-system sandboxing, installed wheel behavior, absence of all possible side effects, native Codex compatibility or scientific correctness.

GitHub Actions run status and exact head SHA must be taken from the actual Actions result linked in the Phase 0 PR; no status is predicted here. Additional tests **NOT_EXECUTED**: old test-runner, doctor, native build, self-hosted browser workflow, real model/API, project migration, full future 58+46 acceptance, full AST call/graph (DEV-PR-01), formal read-only queries (DEV-PR-03), real installation matrix.

## Security/authorization trace

This branch is intended to create only GitHub Git blobs/tree/commit/ref and PR and run isolated local tests. No research projects, MAIN/Goal, budget, original evidence, model credentials or model requests were used or modified. API requests are solely GitHub Connector reads/writes; local Python subprocesses are confined to the three CLI smoke invocations, and `git` is read-only in CI. The original Git-history transport and any all-history secret scan were performed independently by local Codex, not observable in this developer session. Record its sanitized receipts in MAIN review if required.

## Rollback and subsequent work

Before merge, close the PR and leave `main`, `4.2.2-preview`, archived main and tags unchanged; remove branch only with authorization. After merge, create a revert PR without rewriting source history or touching scientific data. `DEV-PR-01` requires separate authorization after Phase 0 accepted; it must generate complete AST direct/transitive dependencies and SCCs, isolate all test-runner dependencies, strengthen import/side-effect/security gates, assess native and system dependencies, and never borrow Phase 0 smoke as product acceptance.
