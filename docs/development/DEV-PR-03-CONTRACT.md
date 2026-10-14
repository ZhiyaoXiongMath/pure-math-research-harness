# DEV-PR-03 — Confined read-only status

User-authorized on 2026-10-14, including the bounded Store read-plumbing
exception. Development base: `507ea4baca2782ab0da13ab949bc4424fc707694`.
This is an implementation contract, not independent review, MAIN acceptance or
a post-merge handoff. Exact source/test receipts and the Open PR identify the
tested revision. The immutable 58+46 baseline and historical reports remain
unchanged; only the portions described below are exercised here.

## Command and meaning

```sh
python3 -B -m pmrh status ./existing-project --instance INSTANCE --json
python3 -B -m pmrh status ./existing-project --instance INSTANCE --json --as-of COMMIT
```

Use Python 3.11+ on POSIX/Linux. Disable interpreter bytecode writes with `-B`
or `PYTHONDONTWRITEBYTECODE=1` for an installed `pmrh` entrypoint. PROJECT is a
native project directory, not Workspace. No configuration or authenticated
backend is needed. Exit 0 means the project snapshot was readable; pool
availability is reported independently. Exit 1 means unavailable project data;
exit 2 means invalid CLI arguments. Help/version and unsupported commands do not
import the query compatibility slice.

`pmrh.status/1` reports the original committed control, request and scientific
scope fields. Each project projection, including MAIN, uses the same selected
journal commit. `--as-of` accepts only an existing full journal SHA-256, not a
Git SHA. Missing, denied, damaged, unsafe or oversized inputs produce safe
reason codes; query errors do not expose raw exceptions or automatically retry.
No missing directory, lock, configuration, index or ledger is created.

Global pool source identity consists of the digest of the observed ledger bytes
and a digest identifying its configured path, with an independent UTC observation
time. It is not atomic with the project journal. Missing or invalid pool data
has null counts and an unavailable reason. Existing zero is reported only after
reading a valid empty ledger. Recorded stale owners and UNKNOWN reservations
remain visible; owner/process liveness is UNOBSERVED and no registered project
root is traversed. Slot output excludes registered filesystem roots.
Pool projection keys and values must serialize as valid UTF-8 before it becomes
available. Invalid Unicode yields `INVALID_POOL_DATA` with null pool counts;
the healthy project projection remains available and ledger bytes stay untouched.

Backend/runtime, authentication and configuration are explicitly unobserved;
status does not inspect or refresh them. Stored usage remains stored usage, not
newly measured calls. Query model-call metering is NOT_INSTRUMENTED/null. Report
state comes from the journal; artifact verification remains UNOBSERVED. The
command neither advances PAUSED nor clears/retries UNKNOWN, and never grants
mathematical qualification.

The existing `StateAxes` DTO is emitted for requests whose legacy control,
execution and admission values have exact enum mappings. Its science axis is
UNOBSERVED with no invented scope reference. Otherwise the original values
remain and `state_axes` is null with an explicit reason. Safe `ErrorEnvelope`
values are real error consumers. No EvidenceRepository/EventRepository adapter,
fake ExactRef, visibility policy, event cursor or new public Port is introduced.
Every request row preserves raw `acceptance_state` independently of that mapping.
An absent field is null with `acceptance_state_unavailable_reason=NOT_RECORDED`;
a present raw value has no unavailable reason. `SETTLED` remains unmapped and
does not imply process termination or scientific qualification.

## Implementation and compatibility

- `research_studio/readonly_query.py` is the single compatibility slice. Its
  private filesystem context opens every directory component relative to a
  no-follow descriptor, pins the selected directory object, reads regular
  single-link files only, and closes every descriptor. Symlinks, traversal,
  special files and hardlinks are refused. It has no write/repair interface.
- The context has a 128 MiB aggregate project-read budget and 4096 read attempts;
  marker and HEAD limits are 64 KiB and 16 KiB. Existing per-file JSON/blob
  limits also apply. Pool reads allow one file of at most 4 MiB, with at most
  4096 entries in each ledger collection. Exceeding limits is unavailable,
  never an empty successful result. Descriptor pinning tolerates ordinary HEAD
  replacement; detected in-place file changes fail closed.
- Existing Store construction/read methods accept this directly consumed
  context and cache its marker/HEAD. The original digest, checkpoint binding,
  identity checks and delta replay remain authoritative. No second Store or
  copied replay implementation exists. Default Store callers continue to read
  the latest HEAD; writers, reducers, schema, index and util are unchanged.
- `host_pool.read_status()` is pure observation. `reconcile_pool()` has the
  original locked reconciliation body. `status()` remains an explicitly
  MUTATING compatibility alias for existing scheduling/writer flows. The new
  query and workspace progress use `read_status`. Retired assistant diagnostic
  code and legacy writer/control callers are not newly certified pure queries.
- `main_session.view(..., snapshot=...)` consumes the supplied snapshot.
  Workspace progress passes the same snapshot into MAIN and its existing
  communication projection; it never constructs Workspace for the new CLI.
  Existing workspace/report/runner services are not given the new confined-I/O
  guarantee merely because their pool read is corrected.

The descriptor reader protects selected-path traversal; it is not a defense
against arbitrary native code, privileged mount changes or hostile interpreter
modification. OS-maintained access time is not a program write and is excluded
from footprint comparisons. The new CLI's supported invocation disables Python
bytecode writes. No filesystem migration is performed.

## Architecture and CI

The original legacy commit `e4de0210f9985224e030ac4cfd2f7e2904005b37` and tree
`c17a592ff0a4906afa7a6423535f41c67c926128` remain fixed. CI permits exactly
host_pool.py, main_session.py, store.py, views.py, workspace.py and the new
readonly_query.py under research_studio. `check_legacy_scope.py` rejects any
other changed legacy path and changes outside the named read functions, and
compares the original reconciliation body. No original baseline is refreshed.

`architecture-exceptions.json` names the CLI-to-query edge and the three DTO
module edges with consumer/reason/removal ownership. It enumerates the exact
63 reachable legacy modules for each of the two CLI files. This is file-level
reachability through inherited mixed-duty modules, not permission to invoke
their writer/runtime functions. No other new source inherits those exemptions.
Existing layer/transitive checks remain; extra query imports, dynamic imports,
new consumers and whole-directory exceptions have negative tests. Repository
source bytes outside the allowed legacy files stay frozen.

The inherited Python guard allows no-follow read-only directory descriptors for
ancestors of its approved roots, solely to support confined traversal. Listing
those descriptors and reading files outside approved roots remain forbidden.
The DEV03 child additionally blocks thread launch. Standard-library ssl type
definitions are preloaded before socket replacement for the bounded workspace
read-method test; no server or browser starts. These are preventive Python
checks, not an OS sandbox.

DEV03 CI runs the actual new suite on Python 3.11 and 3.13 at the exact PR head.
It preserves source archives, original-baseline/AST results, individual raw
test records and receipts, including failures. The runner checks every test
identity against a static source inventory, rejects skips/duplicate/missing
records, checks source hashes before/after and propagates child failure.
Inherited DEV01, DEV02 and Phase 0 workflows continue to run. Only the obsolete
Phase 0 unsupported-status assertion and precise CI compatibility gates change.

## Evidence coverage and limits

The synthetic tests under `tests/devpr03/` directly exercise:

| Planned case | Defined DEV03 evidence |
|---|---|
| Q01 | Absent project/pool/configuration remain absent; existing project reads without pool/configuration |
| Q02 | Content, structure, permissions, mtime/ctime and link-count footprints; readonly and denied permissions; malformed/oversized files; explicit reconciliation preserves UNKNOWN |
| Q03 / GUIDE:C03 | Actual CLI/query and legacy read projections; PAUSED/UNKNOWN/scientific scope preserved; prohibited process/network/thread/native/reconciliation paths fail the positive query test |
| Q04 portion | MAIN and multi-page scientific body reads share a commit during deterministic concurrent HEAD publication; `--as-of` and independent pool observation |
| Path regression | Original parent-swap failure reproduced separately; final actual query rejects a swap before directory open and reads the originally pinned inode after open |
| Compatibility | Original default Store reads advance to new HEAD; pool reconciliation body and stale/UNKNOWN behavior; workspace MAIN/communication share the passed snapshot |

The original failed parent-swap probe and first failed AST check are retained
in external developer evidence. Tests use synthetic native-format fixtures and
original encoders/validators; no fixture conveys mathematical checked status.
The report is not a new entry in the immutable acceptance baseline.

NOT_EXECUTED: real research/model/provider/native work, paid usage measurement,
browser/PDF product gates, the full historical runner, OS-hostile sandbox
certification, scientific migrations, DEV09 event streaming and complete Q04/Q05
product acceptance. No claim covers those future packages.

Rollback before merge leaves this Open branch and receipts for the authorized
decision. After a user merge, rollback requires a separate software revert PR.
Never roll back scientific journal/blobs, PAUSED/UNKNOWN state or Git history.
