# Contributing to Pure Math Research Harness

## Development status

Phase 0 creates a safe package identity and governance baseline, not a functional research CLI. The existing `research_studio` code and legacy entrypoints remain available but are **not** covered by Phase 0's no-side-effect guarantee. Never use live projects to exercise experimental code.

## Environment and checks

- Python >=3.11. The Phase 0 test suite uses only the standard library; no paid models, network probes, browsers, or native Codex binaries are required.
- From an isolated checkout, run `python3 -B -m unittest discover -s tests/phase0 -p 'test_*.py' -v` with temporary `HOME`, `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_CACHE_HOME` and `TMPDIR`, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONNOUSERSITE=1`, and `PIP_NO_INDEX=1`.
- Read-only CLI smoke: `python3 -B -m pmrh --help`, `python3 -B -m pmrh --version`. Other command names must report unsupported and return nonzero.
- Do not run `research-studio`, `pure-math-research-studio`, `pmrs-desktop`, the historical test runner, `doctor`, native builds, or model integration tests under the Phase 0 gate.
- The historical `.github/workflows/final-candidate.yml` is a manual, self-hosted Ubuntu 26.04/browser product gate and is **not** equivalent to the new Phase 0 offline CI.

## Branches and commits

`main` initially preserves the migrated 4.2.2-preview baseline; `4.2.2-preview` and `archive/pmrs-original-main` are reference branches. Do not move or rewrite the legacy history or tags. Author changes only on a scoped `chore/`, `docs/`, `feat/` or `fix/` branch approved for the corresponding development phase. Phase 0 uses `chore/phase0-bootstrap`. Keep each commit reviewable with a descriptive imperative subject and a diff limited to its declared contract. Never force push or squash imported history.

## Review and acceptance

Use the pull-request template. Distinguish `PLANNED` (design only), `IMPLEMENTED` (code present), `TESTED` (matching actual execution receipts), `REVIEWED` (independent review recorded) and `ACCEPTED` (authorized acceptance). These labels apply per item; Phase 0 smoke does not test future mathematical obligations. For every missing test, write `NOT_EXECUTED` and why. Formal mathematical checked status is separate from all five software states.

Source hierarchy and boundary conflicts are specified in [AGENTS.md](AGENTS.md). A new implementation proposal cannot bypass original target/D0, scoped evidence, human authorization, PAUSED, UNKNOWN, or independence. Follow the 18-package dependency map in [ROADMAP](docs/development/ROADMAP.md) and retain the 58 + 46 acceptance baseline unchanged.

## Rollback and data integrity

Before merging, the default rollback is closing the unmerged PR and deleting its development branch **only after authorization and preservation of receipts**. After merge, revert the software commit on a new PR. Do not reset, rewrite, delete scientific journal/blobs, purge UNKNOWN reservations or alter research projects as a form of rollback. No live project migration without separate explicit authorization.
