# PMRS 4.1.0 architecture

The application exposes one native mathematical research runtime through shared Engine and Workspace services. The browser and CLI share service semantics for TRW, TFDW and SURVEY; neither is an independent research authority.

## Knowledge and evidence

Strict mathematical records retain Context, Statement, Argument, Example, SourceEvidence and Assessment responsibilities. Exact revisions, immutable source/body locators, scoped support, independent assessments and withdrawal remain distinct. Saving a statement or citing a publication does not qualify a proof.

SURVEY stores versioned scope, retrieval, reading, coverage, readiness and output-plan metadata alongside native knowledge. Sources, extracted text and mathematical records are separate artifacts. A PDF's original hash is its actual byte hash, not an extracted-text hash. Metadata or abstract access never becomes a full-text reading claim. Readiness binds the selected revisions, dependency closure, evidence and proof commitment; unrelated knowledge changes do not invalidate the selection.

## Execution and retrieval

Each workflow instance owns its target or scope, state, authorization and budget. Stage/role/purpose policies freeze settings before dispatch and refuse unsupported capabilities. TRW/TFDW research and report policies are retained. Survey planning, reading, organization and coverage use registered xhigh roles; substantive reconstruction and independent mathematical checking use max roles. Report and visual roles retain the existing report policies. Product task settings are independent of the development agent's settings.

Controlled literature access separates model planning from host retrieval. The host executes bounded queries and downloads, retains provider records, actual URLs and versioned materials, and records explicit failures and access limits. Reading and synthesis consume frozen inputs. Retrieval does not globally enable network or filesystem permissions in mathematical tasks. External text remains source content rather than executable instructions.

Captured results retain original request identity. UNKNOWN is not automatically resent or refunded. Pause prevents new dispatch while retaining in-flight work and captures. Reentry requires changed inputs, a specific issue or explicitly bounded retry grounds.

## Services and persistence

The native journal uses content-addressed blobs, sparse deltas and reference checkpoints. SQL remains a disposable projection. Product and storage version identifiers are separate. Native backup validates the journal and blobs into a new paused destination; unsupported shapes fail explicitly. Earlier-version migration readers, compatibility adapters and archived research examples remain outside the product.

Preparation counts actual local blob sizes and bounded metadata before large reads. Input, serialized-byte, model-token and temporary-space budgets remain distinct. Task files and offline renderer resources use bounded streaming copies with independent files, never writable links to authoritative blobs. Project-local process-identity leases account for up to two preparations, 256 MiB of estimated preparation memory each (512 MiB aggregate), 512 MiB temporary space each (1 GiB aggregate), and 512 MiB free disk headroom. These are application preparation budgets, not operating-system memory restrictions or a guarantee against every possible OOM.

Only reconstructable caches are reclaimed. Native checkpoints retain at most four files within 128 MiB, with a 48 MiB state-serialization limit; a missing old checkpoint is replayed from immutable deltas. Settled, sealed task input copies may be removed while original packets, captures and receipts remain. Active and UNKNOWN work is protected. Read-only caches have bounded capacity and exact revision/stat keys; actual admission and delivery still verify integrity. ENOSPC and interrupted atomic publication preserve the prior valid state or a complete published state, never a successful half-file.

Each desktop workspace has a loopback service, session/origin/CSRF protection, stable workspace identity and durable operation receipts. A retry recovers the original operation; a deliberate new operation receives a new key. Workspace receipts recover completed work after service restart and port changes without resending a model request. The 4.x workspace/configuration path retains its `4.0` name while application installations and menu entries use the full product version.

## Reports and interface

TRW/TFDW retain paired lecture/minimal reports. Survey Knowledge only has no manuscript requirement; an explicit Survey writing plan requests only its selected minimal, thematic or lecture profile. Writing consumes frozen knowledge and cannot grant new mathematical support. New mathematical claims return to knowledge and readiness work. Semantic review, actual compilation and every-page review bind the actual report revision; failed attempts and prior revisions remain visible.

The interface uses stable translation keys with English fallback and a host-persisted `ui_locale`. Translation changes display only, retaining English research/report constraints, exact identifiers and frozen contracts. Polling refreshes tasks, actions, retrieval and reports while preserving the reading body. Three workflow diagrams show the selected instance and main paths by default, with every registered legal path available on demand and explicit structure previews for unloaded workflows.

See [scope](ACCEPTANCE-SCOPE-4.1.0.md), [validation](TEST-REPORT-4.1.0.md) and the [bilingual usage guide](README.md).

## Bounded task preparation

Native input preparation counts local immutable file sizes and unique hashes before reading bodies. Unique material plus scoped record/source metadata is limited to 32 MiB, with an 8 MiB metadata sublimit; packet and complete request serialization are each bounded at 64 MiB. These storage limits supplement the independently frozen model token capacity and output reserve. An oversized complete input is rejected before model dispatch; it is never silently truncated. Explicit coverage parts retain their declared original hashes and checked boundaries within the supported input budget.

Report files use immutable hash references in the packet and are materialized one file at a time with 256 KiB copy chunks and hash verification. The copy fallback creates independent files, never writable hard links to authoritative blobs. Visual tasks receive the relevant manuscript, actual pages and neighboring-page context with a small identity manifest; they do not duplicate the literature corpus. Author and semantic roles retain their complete necessary evidence.

Preparation reservations use a process-identified, OS-locked ledger under the project’s excluded `.runtime` directory. At most two preparations, or the lower existing project concurrency, may hold reservations. The estimated preparation memory allowance is 256 MiB per slot and 512 MiB total; this is accounting, not a host memory limit or a guarantee about arbitrary workloads. Temporary disk reservations allow 512 MiB per slot and 1 GiB total, with 512 MiB of free-space margin; task execution reserves 256 MiB and checks its working-directory size. Resource shortages preserve the original request and require waiting, a narrower explicit scope or more free space.

Only a settled task with a verified original capture seal may discard its named, reconstructible input copies. Captures, responses, commands, logs, scientific records, original sources and report evidence remain. Prepared, in-flight and UNKNOWN requests retain their work materials. Cache cleanup failure cannot undo settlement or authorize another model call.
