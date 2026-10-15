# DEV-PR-04 domain extraction contract

This change extracts existing native scientific rules into `pmrh/domain` and
routes current consumers through explicit legacy aliases. It introduces no new
scientific object, backend, migration or strategy loop. Developer delivery is
subject to independent review and a separate Controller decision. It is not
`REVIEWED`, `MAIN ACCEPTED` or `MERGED`.

## Authority and frozen identities

The explicitly authorized preparation applies to base
`f724c06b54b157abe580cdf046f4fc08bb01c144`, tree
`578fd501442d9155ce1103b971c43cfaf57242ea`. The accepted PR8 strategy and addendum
v0.1.0 are effective despite their historical candidate labels. The preparation's
historical `NOT_AUTHORIZED` was superseded by explicit development authorization.
No live GitHub access was performed in this isolated developer environment.

The original audit baseline remains
`e4de0210f9985224e030ac4cfd2f7e2904005b37`, tree
`c17a592ff0a4906afa7a6423535f41c67c926128`. Its inventory, original 58+46 acceptance
definitions, historical reviews, PROJECT-STATE and handoffs are unchanged.
The new oracle manifest pins the Python sources of the separate DEV04 base;
it does not replace that original audit inventory.

## Implementation and consumer boundaries

| Domain module | Existing responsibility and compatibility consumers |
| --- | --- |
| `primitives` | Canonical bytes/hash/parser, the single `PMRSError` class and pure authored-language checks; `research_studio.util` and `.language` alias exact symbols. Filesystem utilities and search stay legacy. |
| `contracts` | Closed scientific fields, native schema constants, bounded JSON and KR/IB identities; legacy contracts retains authoring/schema assembly and `ValidatedChange`. |
| `knowledge` | Six record kinds, exact locators, source closure bindings, native argument payload validation and inference identity; legacy knowledge is an explicit alias facade. |
| `relations` | Native reference/support graph, cycles and selected dependency invalidation; legacy relations is an explicit alias facade. |
| `assurance` | Exact consumer qualification, conditions, independent slots, scope and coverage. Legacy assurance is a facade; communication aliases only `independence_status`; context aliases only pure coverage helpers and their numeric `validate_budget` dependency. |
| `stages` | Original TRH P0–P14, FDH D0–D5 and Survey declarations and activity selectors; the three legacy stage modules alias the same objects/functions. |
| `protocols` | StageSpec compilation, identity/digest, assignment/exit rules, D0 validation and completion evidence. Legacy registry keeps prompt imports/assembly; workflow_instances aliases only the two pure scientific predicates. |

All extraction aliases and direct owner/consumer edges are enumerated in
`scripts/domain_scope.py` and `config/architecture-exceptions.json`, owned by
DEV-PR-04 with an explicit removal horizon. There is no directory exception.
The legacy scope gate compares all other mixed-module AST sections with the
original baseline; pure facades may not retain or add algorithm bodies. Existing
DEV03 read exceptions and the reconcile-body check remain separate and active.

Domain dependencies are stdlib plus domain modules. There is no path, process,
network, Store, port, application or SDK import. A caller explicitly supplies
`blob_get(hash)` for bytes from its selected immutable snapshot; tests supply
memory dictionaries. The domain does not select a live snapshot or authorize
access. The static import/call gate is a review aid, not a complete adversarial
Python capability sandbox.

Transaction/admission/allocation, requests, authorization, control and reporting
remain legacy. Current consumers retain signatures, return forms, error codes
and shared exception class identity. `changes.validator_identity` alone adds
all actual domain Python files to FORMAT's implementation fingerprint. Its
existing revision label and legacy fingerprints remain. KR/IB and StageSpec
bytes/digests are unchanged. Old FORMAT attestations cannot establish that the
new implementation was checked merely because a legacy facade name matches.

## Requirement preservation and bounded acceptance map

RMAIN-REQ-01/11 preserve original target/D0 and human choice boundaries;
03/04 preserve exact conditions, direction, witnesses, AND/OR, cycles and
interfaces; 09 preserves failure scope and honest absence of progress;
10 preserves exact independent qualification and scoped withdrawal;
12 preserves identities/history and the minimum extraction design.

The table maps the preparation's thirteen paired groups. Exact inherited test
IDs are in `tests/devpr04/selection.json`; trace keys are emitted by
`domain_probe.py`; new test IDs are recorded from `test_boundaries.py`. Empty
selection arrays mean that the group is covered by the trace, boundary tests or
inherited runners described here, rather than a selected historical test.
No row redefines or fully accepts a cross-package K/O/S/GUIDE requirement.

| Group; inherited scope | Positive and negative evidence; limits |
| --- | --- |
| 01; A01/A02, six immutable records | `01.*` trace compares canonical hex, KR/IB identities, six kinds, source closure and original Unicode bytes; bad hash/quote/range/UTF-8, duplicate keys and unknown fields fail. Selected identity, local-reference, strict JSON and source-binding tests cover staging, aliases and local cycles. |
| 02; RMAIN-REQ-01/11, MR08 fragment | `02.*` and fixed-target revision/handoff fixtures preserve target and D0's three source bindings; weaker target or missing/misbound D0 fails. Exact completion requires dual scope and global integration where applicable. Candidate handoff remains a separate paused TRH. No unknown comparison is converted into a new NOT_IMPLIES relation. |
| 03; O05, GUIDE:P11 | `03.*` plus NO_RESULT, assurance and human-adoption fixtures separate candidate/formulation/admission from scoped qualification; completion is independently tested in group 02. No JSON or test result proves a mathematical claim. |
| 04; K01 existing semantics, GUIDE:K04/K06/K08 | `04.*` compares exact declared-hypothesis qualification against strengthening/unconditional use. Explicit witness bindings and qualified components pass; missing mapping/quantifier or open condition fails. Selected fixtures reject boolean compatibility, undeclared assumptions and quantifier gaps. No new quantifier compression or semantic prover. |
| 05; GUIDE:K06/K07, RMAIN-REQ-04 | `05.*` plus existing three-child fixture checks complete AND/OR paths; missing child, open lifting and incomplete alternative stay unqualified. An exploratory gap does not constitute a reduction. |
| 06; K03, GUIDE:K11 | `06.*` checks a real acyclic support graph and mutually dependent supports in both graph validation and qualification. Dynamic P8→P6 reentry is separately legal; workflow return is not a mathematical proof cycle. |
| 07; K02 domain portion, GUIDE:K09/C13, MR03 fragment | `07.*` plus selected withdrawal fixtures retain independent paths and nonintersecting consumer scope; selected dependent paths invalidate without rebinding, negation or changing statement family. A1 defects do not authorize A2 withdrawal. Propagation stays based on selected support IDs. |
| 08; O05, S03/S04 domain portions | `08.*` plus credential/coverage tests check full exact inputs, distinct executions, dual slots and integration. Author self-review, synthetic credential in a real snapshot, contaminated verdict exposure, missing slots and incomplete scope fail. Authentic coverage parts are recomputed. No complete cross-role runtime/cache isolation certification. |
| 09; O02 domain classification, GUIDE:K13, MR03/MR04 fragments | `09.*`, NO_RESULT and scoped-refutation fixtures preserve an open original target after a failed sufficient route; exact refutation requires reviewed evidence satisfying the target scope. No strategic diagnosis/retry engine; transport UNKNOWN remains covered only by inherited contract/query scope. |
| 10; GUIDE:C13, existing live guards | Selected PINNED/CURRENT/query/write-CAS tests preserve relevant revisions and allow unrelated changes. A pure exact-excerpt packet test permits delivered bytes and rejects undelivered full source/out-of-range selection. No Store publication or new FastDelta transaction. |
| 11; C04/C06/C07, GUIDE:P01–P06 affected controls | `11.*`, selected workflow/control/handoff fixtures and boundary tests cover dynamic duties, shared StageSpec digest, paused sealed worker vs MAIN/fenced capture, P13-before-P14, stop handling, ordinary vs formal D5 and late reports remaining paused. No live Engine, timer execution, native MAIN or complete DEV06/13 acceptance. |
| 12; A01/A02 | Three independent processes compare frozen baseline, current facades and standalone domain. Every traced call repeats with input-mutation checks. Boundary tests reject forbidden dependency/I/O edges, blanket allowances and unrelated writer edits; fingerprint mutation checks cover every domain file. Common socket/process/thread calls and writes are blocked by the inherited guard, with separately verified OS isolation locally. |
| 13; inherited DEV01/02/03 and Phase0 | Run unchanged fixed suites (48/119/36 tests) through their offline runners. Phase0's five static test IDs run under the existing query guard; its four exact CLI cases run as separate guarded children because nested subprocesses are forbidden. This is not blanket historical discovery or the original smoke method execution. |

MR03/MR04/MR08 coverage is confined to these existing semantic fragments.
DEV11 fast objects, DEV12 strategy/triad loop, new backends, Lean, migrations,
UI/report replacement, scheduler/pool work and real research remain outside scope.

## Reproduction and evidence

Read imports before executing selected tests. Provision an external dedicated
`pmrh-devpr01-artifacts-*` directory directly under the scratch system temp
root, with an existing child output directory; set `PMRH_TEST_ARTIFACT_ROOT`.
Set launcher HOME/XDG/TMP to synthetic scratch locations and use a sanitized
environment. Then run:

```text
python -B scripts/check_legacy_scope.py
python -B scripts/architecture_deps.py --check --json <scratch>/dependency-graph.json --markdown <scratch>/architecture-audit.md
python -B scripts/offline_domain.py --out <artifact-root>/offline --oracle <read-only-frozen-base>
python -B scripts/offline_test.py --out <artifact-root>/devpr01
python -B scripts/offline_contracts.py --out <artifact-root>/devpr02
python -B scripts/offline_queries.py --out <artifact-root>/devpr03
```

The DEV04 runner validates the frozen oracle's per-file hashes, records actual
source hashes, fixture hash, exact commands/IDs, Python/platform, outputs and
exclusions, then verifies both trees remain unchanged. Six named `.log` files
are raw output; `unittest.log` is only the run index. `receipt.json` records the
three-way comparison and each child's result. All raw local logs, isolation
probes, failure/fix history and final source manifest stay outside the repository.

The dedicated CI workflow uses pinned actions and Python 3.11/3.13, materializes
an independent fixed-base oracle and uploads raw results even on failure.
CI execution is `NOT_EXECUTED` in this developer delivery; local availability
is Python 3.14 only. No numerical provider call/cost claim is made:
`NOT_INSTRUMENTED` / `NOT_MEASURED` remains explicit in receipts.

Three historical tests failed identically on the independent baseline and new
facades: the registry assertion expects 29 stages while current declarations
contain 31; an old scheduler fixture selects no work under current MAIN rules;
and the Store excerpt test attempts hardlinks denied by the unchanged guard.
Their initial raw failures are retained. They were removed from the fixed
selection, not edited; domain registry/dynamic-duty and pure excerpt assertions
cover the affected extraction boundaries. Full scheduler execution and Store
publication remain `NOT_EXECUTED`. No behavior fix is hidden in the extraction.

Rollback restores the changed source/gate files and removes the new domain,
tests, runner, scope manifest, workflow and this contract. There is no data
migration or project-state write to reverse. Existing evidence must still be
checked against the validator fingerprint of whichever implementation runs.
