# DEV-PR-05 — shared disk storage and bounded observation ports

Frozen interface contract **r1**, before implementation branch creation. Baseline:
`2c65af1a407c159d6768867bf25c03566c4657c1`, tree
`2b141b07ea297aa37d6ffb2d85b21e8b6c07bd5c`. The current human development grant
and subsequent explicit approval, “批准上述受限扩展”, authorize this package.
Earlier pending/unauthorized statements describe historical cycles. The independent
contract recommendation was `APPROVE_FOR_FORMAT_DECISION`, not implementation
review or acceptance. Controller owns commits, publication and acceptance.

## Persistence and compatibility

One journal/blob/record publisher, writer lock, HEAD, checkpoint and disposable
SQLite projection serve the legacy Store facade and real disk ports. Preserve
Store's public and consumed private APIs, errors, canonical identities, original
capture validation, report-first and post-END behavior. Domain and v1 Port/DTO
files, original scientific schemas and evidence bytes remain unchanged.

Legacy-only projects continue writing `pmrs.commit/4.2.2`. Trusted internal setup
may opt explicitly created synthetic fixtures into sticky `pmrh.commit/1`.
Every subsequent entry, including checkpoints and legacy-facade writes, uses
that discriminator. Old readers/writers reject extended HEAD, even when selecting
an earlier snapshot. No migration, transparent old-reader support or downgrade.
Rollback preserves evidence and requires a compatible reader.

The extension has exactly two closed `pmrh.storage-event/1` events:

- `PMRH_PORT_SCOPE_BOUND`, with `policy_sha256`, references canonical
  `pmrh.storage-visibility/1`: `schema`, `scope`, `profile`, `read_rule`,
  `classification`. Values are `SYNTHETIC_TEST_ONLY`,
  `EXPLICIT_SCOPE_REGISTRATION`, `SYNTHETIC_TEST_ONLY`. One binding per instance.
- `PMRH_PORT_BATCH_COMMITTED`, with `manifest_sha256`, references canonical
  `pmrh.storage-batch/1`: `schema`, complete `staging_receipt`, `operation_id`,
  `idempotency_key`, ordered `evidence_refs`, ordered `observation_refs`.
  Observation blobs retain unchanged staged v1 EventEnvelope wire bytes.

No new native state collection or sidecar authority. Hash original evidence and
envelopes, then manifest, then journal; derive committed DTOs afterward to avoid
circular identities. Commit ExactRef uses `journal:<project>`, `sha256:<digest>`
and the actual journal byte digest. Policy refs use `visibility:<instance>`.
The stream is `ports-observations/1:` plus the canonical digest of project,
instance and policy-ref wire representation. Raw registrations use `raw-evidence:`
or explicitly synthetic `synthetic:` object IDs. KR/IB suffixes are never treated
as file hashes. Exact refs convey identity, not authority.

## Ports, authorization and recovery

Preserve EvidenceRepository, EventRepository and UnitOfWork signatures. Reads
require trusted out-of-band context, the exact published policy binding and a
verified boundary at/after binding in captured HEAD ancestry. Wire data never
selects paths or code. Reachability includes only explicit same-scope committed
registrations, policies and original envelopes. Future, orphan and cross-scope
objects are not readable merely because their bytes exist.

Evidence reads verify full bytes before slicing: integer offset >= 0 and at most
extent, max_bytes 1..1 MiB. Keep 1 MiB writes, 8 MiB aggregate wire, 4096 tuple,
128 MiB/4096-file scan budgets; retain legacy Store's separate 256 MiB blob limit.
Event pages use scope-specific sequence and aggregate counts, staged order,
original observation/occurrence times, and journal-derived publication time.
Validate all fields in verify_event. Wrong anchors reject; only verified exact
missing intervals produce GAP. Unindexable corruption never becomes EMPTY/GAP.

Only DIAGNOSTIC/EVIDENCE_RECORDED OBSERVATION batches are supported. Reject
supplied publication metadata, dispatch/MAIN/backend authority and HUMAN claims.
Published provenance stays SYNTHETIC/SYNTHETIC_TEST_ONLY. A marker or persisted
policy is never sufficient authorization. No production policy installer ships.

Begin/stage are local, bounded and invisible. Under the shared writer lock,
commit validates current trusted permit against transaction, staging digest,
operation, scope and expectation; reconstructs persistent duplicates; then
enforces physical HEAD CAS for a new publication. Project-wide idempotency binds
the full original expectation and ordered batch. A retry may use a new handle
and current permit, but returns the original receipt/boundary. Changed content,
scope, operation or expectation conflicts. Revoked authority denies even a retry.
Rollback cannot delete published facts. Uncertain HEAD outcomes require original
operation recovery, never model resampling.

Legacy scientific admission retains under-lock revalidation of the same original
task/raw and relevant selected revisions, supports, query memberships, write
parents, obligations and control. Unrelated HEAD updates remain admissible.
Preserve sealed paused-worker admission and paused-MAIN/new-dispatch rejection.

## Extraction and preservation

Core/repository reads import no legacy runtime, Runner or Provider. Application
depends on ports/domain and injected local capabilities; adapters depend on
ports/domain. Static trusted compatibility assembly owns legacy reducers and
their exact allowed collections. Data cannot install reducers or generic patches.

Extract only frozen pure desired/view, budget, MAIN-session, scope/status,
strategy and audit projections into application/read_projections; confined pool
status and its pure helpers into adapters/storage/pool_read. Legacy aliases or
wrappers preserve behavior and verified reports. Minimal query uses journal-only
unverified reports and has no static or runtime native/runner/provider reachability.
Keep architecture audit baseline `e4de0210f9985224e030ac4cfd2f7e2904005b37`,
DEV03/04 guards and general layer rules; only exact owned edges/symbols change.
FORMAT fingerprints include moved implementation; historical identities stay
recorded unchanged.

Direct inheritance: E01/E03/E04; storage portions of E02/E08; Q01–Q04;
GUIDE:K10/C13/C14 in their existing local scope. RMAIN-REQ-02/10/12 require
versioned, scoped, independent evidence and durable recovery; REQ-01/09/11
preserve original target/D0, candidate and failure boundaries. Preserve TRH
P0–P14, FDH D0–D5, six immutable records, single logical MAIN, budgets, PAUSED,
UNKNOWN, independent mathematics and no automatic UNKNOWN retries. Original
58+46 definitions remain unchanged and are not globally passed.

Non-goals: DEV06 production policy/epoch/global-pool/outbox, DEV07 execution,
DEV09 full event CLI, DEV11/12 fast objects/strategy, migration, real research,
model calls, UI removal, new scheduler/controller behavior or dependency framework.

## Validation and status

These are the historical statuses at the contract freeze, before execution.
Subsequent Controller receipts and the scoped test amendment are recorded below.

All product tests and CI: **NOT_EXECUTED** until matching receipts exist.
Implementation review, MAIN acceptance and merge: **NOT_PERFORMED**.

Bounded real-disk D05-01..10 tests cover frozen native bytes and private consumers;
stage/rollback; evidence/event reachability and forgery; persistent duplicates and
changed expectations; five publication fault points, process crash/reopen and
lock competition; physical CAS and scientific relevance/paused boundaries;
sticky format/old-reader rejection; checkpoint/projection/disk failures; pure
query output/import closure; validator fingerprint changes. Use real link/fsync/
rename publication. Preserve original failed fixtures without relabelling them.

Run through `scripts/offline_storage.py` only: failclosed bwrap, readonly source
and baseline, separate tmpfs scratch, cleared environment/no credentials,
isolated network, listed Python children only. Record source/scratch/outside,
cross-filesystem and internal hardlink, and network probes before product imports.
Nested isolation failure means product tests remain NOT_EXECUTED; Controller
executes the safe runner. Existing SEC-01/offline_guard is unchanged. Required
DEV01/02/03/04/Phase0 regressions and exact-head Python 3.11/3.13 CI remain separate
receipts. No full legacy/stress/native/browser/research runs. Management inference
usage is NOT_MEASURED. Independent review and Controller disposition follow.

Controller mechanical disposition **DEV05-SCOPE-01** permits moving only
`language.DEFAULT/policy` and `version.SCHEMA_VERSION/COMMIT_SCHEMA` into
`adapters/storage/native_format.py`, with explicit original aliases, unchanged
values/behavior and shared DEFAULT identity. This closes the pure snapshot
validator dependency; it authorizes no additional format or policy change.

## Initial Developer delivery and reproducible commands

Code and bounded tests are present in the working diff; the Developer makes no
commit, independent-review or acceptance claim. Local static syntax, exact legacy
scope and architecture checks passed; the architecture graph has no violations.
The final source and execution receipts must be rebound by Controller to its
immutable code head. The initial S2 launch failed before product imports because
this role's sandbox denied nested namespace creation. Product tests, regressions
and Python 3.11/3.13 CI therefore remain **NOT_EXECUTED by Developer**.

The common implementation is `adapters/storage/{io,native_format,journal,format,
repositories}.py`; `application/unit_of_work.py` coordinates an injected local
capability and current policy. Trusted legacy reducers live in
`research_studio/storage_compat.py`. Query projections and pool observations have
separate pure/read-only modules. No DTO, scientific policy, version value,
original test or SEC-01 file is changed.

Controller commands, with fresh external artifact directories and the frozen
baseline matching `tests/devpr05/oracle-manifest.json`:

```text
python3 -B scripts/check_legacy_scope.py
python3 -B scripts/architecture_deps.py --check --json <artifacts>/dependencies.json --markdown <artifacts>/architecture.md
python3 -B scripts/offline_storage.py --out <artifacts>/storage-s2 --oracle <frozen-DEV05-baseline>
```

The new workflow repeats S2 on exact PR head with Python 3.11/3.13, archives the
source and uploads logs even on failure. The runner records the complete source
and frozen-oracle inventories, actual command/interpreter, mount/network/hardlink
probes and raw results. It masks Git metadata and permits only its fixed Python
child helper modes for oracle/query, restart, crash and lock checks. Existing
DEV01/02/03/04/Phase0 workflows remain required regressions; use their accepted
guarded entrypoints and declared scratch. Their results are separate from S2.
The existing SEC-01 hardlink prohibition remains unchanged.

The new tests retain six selected original publisher/resource definitions and
add real disk cases for the D05-01..10 responsibilities above. Original baseline
failures in the three Engine.prepare-dependent Store/resource methods remain
historical failures: their fixture capability evidence was rejected as
MODEL_CONFIGURATION_UNSUPPORTED. New MAIN capture fixtures explicitly declare
synthetic capabilities; they do not claim installed backend capability or run a
model. No old failed fixture is renamed or edited into a pass.

Resource limits are deliberate: full extension scans are bounded and may fail
UNOBSERVED rather than return partial facts. Checkpoints and SQLite remain
rebuildable projections; corrupt existing checkpoints reject. Process-exit and
injected fsync failures test bounded recovery properties only. They do not
certify every filesystem's power-loss behavior or durability of newly created
parent-directory entries. Uncertain publication retains the original operation
for fresh authorization and receipt lookup; rollback refuses an uncertain
transaction and cannot delete its evidence.

The inherited DEV03/04 inventories and original audit baseline remain intact.
DEV05 adds exact symbol/import allowances and a smaller enforced query closure.
The original Store→native reducer coupling is explicitly relocated to the
trusted legacy writer assembly; it is absent from core/repository/query reads.
The general application/interfaces→adapters prohibition is unchanged; only the
two existing CLI composition roots are classified as bootstrap.

## Round-two amendment and execution history

Controller disposition **DEV05-SCOPE-02** authorizes only
`QueryTests.test_Q04_head_publication_during_query_keeps_main_on_selected_commit`
in `tests/devpr03/test_queries.py` to patch the extracted
`pmrh.application.read_projections.main_view` with its already-pinned snapshot.
The concurrent native publication and every assertion remain unchanged. The
scope guard verifies the frozen baseline hash, exact replacement, and unchanged
bytes and AST outside this method; all other existing tests remain byte-identical.
This exception supersedes only r1's existing-test restriction for that method.
Original 58+46 definitions, SEC-01 and accepted offline runners are unchanged.
No DTO, format or scientific-policy amendment is authorized.

Controller executed three immutable S2 candidates with verified isolation:

| Receipt | Executed result |
| --- | --- |
| S2 candidate 01 | FAIL: 17 methods, 8 error entries; includes child-spawn rejection and MAIN fixture failure. |
| S2 candidate 02 | FAIL: 29 of 30 methods passed; MAIN fixture error remained. |
| S2 candidate 03 | FAIL: 31 of 32 methods passed, no skips; MAIN synthetic `next_action` enum error remained. |
| Regression candidate 01 | DEV01: 48 PASS; DEV02: 119 PASS; DEV03: 35 PASS / 1 FAIL at the obsolete hook above; DEV04: PASS, including 34 baseline/34 facade selections, 10 boundary tests and differential traces. |

These logs remain failures for their recorded source manifests; they do not
certify the revised working diff. Candidate 03 passed crash/reopen, lock/CAS,
native-byte equivalence, old-reader rejection, query closure and FORMAT checks.
The Developer's initial nested S2 attempt remains NOT_EXECUTED, separately from
these executed Controller runs. Exact-head CI and independent review remain pending.

Round two corrects only the new synthetic MAIN response before capture and adds
active-admission/paused-rejection pairing. It fixes the test hook above, replaces
the writer star import with explicit imports, and makes S2 reject empty discovery,
skips and altered spawn environments, including PYTHONPATH/PYTHONHOME injection.
The existing facade read hook, Python runtime-prefix bind and permitted child
tests remain in place. Legacy checkpoints still avoid old delta replay; ancestry
headers remain verified for sticky-format integrity without a mutable cache.
Static syntax, exact scope and architecture checks pass. Revised product tests
are NOT_EXECUTED by Developer in round two; Controller must rerun S2 and the
accepted regressions on the complete frozen candidate before review/publication.

## SCOPE-03: CI artifact compatibility

Controller authorizes `verify_devpr01_artifacts.py` and
`verify_devpr02_artifacts.py` to recognize only the existing named coupling
`research_studio/store.py` → `research_studio/native_main.py`, owned by DEV-PR-05,
as relocated to `research_studio/storage_compat.py`. The shared static verifier
requires that exact tuple, owner, current source and relocation status, zero
original direct occurrences, an absent old edge, and the actual new edge in both
the direct graph and import occurrences. Forged, duplicated, missing or unrelated
relocations reject. All other receipt, source, raw-log and test-identity gates
remain unchanged. The original audit baseline and original scientific tests,
domain/ports, SEC-01 and old offline runners are unchanged.

First CI at PR11 head `4613438fa847bac8e1b833e9bff0b449de0743b3` remains failed:
DEV01/02 test suites passed, but their old artifact gates rejected the relocation.
DEV05 Python 3.11/3.13 S2 was NOT_EXECUTED: bwrap failed before product imports
with `loopback: Failed RTM_NEWADDR: Operation not permitted`. The recorded command
retained `--unshare-all`, readonly source/oracle, tmpfs scratch and cleared env.
The supplied logs do not establish which kernel security mechanism denied it.

The DEV05 workflow conditionally clears only
`kernel.apparmor_restrict_unprivileged_userns` on its ephemeral GitHub-hosted Linux
job, where Ubuntu's AppArmor restriction can block this namespace setup. It logs
the original value and adjustment and restores the value in an always-run step.
It does not disable AppArmor globally, change this development host, alter S2
mounts/network namespace/probes, run product tests as root or provide a bare-test
fallback. This is a targeted mitigation, pending actual hosted-runner validation;
remaining setup failures stay fail-closed. Original failed CI evidence is retained.

## Review correction: publication read budget

Independent review of head `4613438fa847bac8e1b833e9bff0b449de0743b3`
found that one valid evidence-only batch of 4096 references (1,354,816 wire
bytes) published a HEAD whose closure exceeded the ordinary confined reader's
file budget. Controller reproduced this in verified S2: HEAD advanced, commit,
reopen and retry returned UNOBSERVED, and legacy reopen raised QUERY_READ_LIMIT.
This is an executed failure of that head; it remains part of the evidence.

The shared publisher now verifies each candidate `pmrh.commit/1` snapshot and
full extension closure from its immutable on-disk files before replacing HEAD.
It uses the ordinary confined reader's unchanged limits, charges the future
HEAD read, replays all native deltas and validates present checkpoints without
using them to skip replay. Publication safety therefore does not depend on a
particular disposable checkpoint remaining available. This applies to scope
activation, UoW batches and every later legacy publication on an extended
project, including checkpoints. Legacy-only publication is unchanged.

A file or byte limit rejects before HEAD with native `RESOURCE_LIMIT`; the
frozen v1 Port error vocabulary continues to map this to UNOBSERVED with
read-only recovery and no automatic retry. The previous readable boundary and
all immutable facts remain; unpublished candidate files are orphans. A valid
individual DTO does not promise unlimited cumulative project capacity. No
read limit, DTO, persisted schema, authorization or scientific admission rule
has changed, and no public arbitrary-head read or durable index was added.

Four new real-disk regression methods cover the maximum valid batch, cumulative
normal batches under reduced real file/byte budgets, later legacy/checkpoint
rejection, and successful publication plus durable duplicate recovery after
all checkpoints are discarded. Existing process-exit crash/reopen, lock/CAS and
publication-fault tests exercise the same publisher. The revised product suite
is NOT_EXECUTED by Developer because nested S2 is unavailable; Controller must
run the complete frozen candidate in S2. Prior executed results above are
historical and are not replaced by this status.

## Review correction: FORMAT dependency fingerprints

Finding F2 identified omitted DTO verification dependencies in the live FORMAT
implementation identity. `validator_identity` now also hashes the ports
initializer, interfaces and all 11 DTO source modules: package initialization,
wire registry/decoding/serialization/budgets, core identities, enums, events,
storage, authorization/control, capability, execution, orchestration and specs.
The interfaces import path registers this complete DTO set; no DTO or Port
source bytes, schema, validation behavior or persisted format change.

The existing end-to-end FORMAT test now mutates each of these 13 source
fingerprints independently: live verification must reject, historical
verification must succeed, and recorded evidence must remain unchanged. It also
pairs historical acceptance of the prior module-map shape with live rejection.
Recorded identities are not rewritten and the validator revision is unchanged.

Controller candidate 06 passed all 43 methods in verified S2, including F1's
publication-budget regressions. That result belongs to its recorded source
manifest; F1 is unchanged here. F2's extended test is NOT_EXECUTED by Developer
and awaits Controller S2. Required exact-head CI and independent re-review
remain pending; earlier failed CI and review evidence are retained.
