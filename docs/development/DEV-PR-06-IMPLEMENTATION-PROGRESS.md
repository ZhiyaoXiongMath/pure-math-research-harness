# DEV06 feedback R7 remediation and visit-boundary decision

Controller validation007 ran the exact R6 source fingerprint
`ae30198984d0efe3e54411d8440c4f30d5cd60f643bf5535a2490e0e7e76a450`:
107 tests, two errors, one failure, zero skips, isolation VERIFIED. This is
historical execution evidence; the changed R7 assertions are NOT_EXECUTED.

The cancellation/abandon test now uses two fresh synthetic roots, reversing the
two actions. Each first action must publish its actual event, return its original
cached result under current authority, and reject a denied-authority replay.
The second action only repeats the existing fence, so the test explicitly checks
NO_CHANGE, no operation-index entry and current authorization before that return.
Both orders preserve UNKNOWN liability, no release and no automatic retry.
No product reducer or action coverage category was changed.

Both scientific positives remain selected with every original assertion intact.
Their validation007 errors expose a native visit integration boundary, rather
than an independence guard to relax: `scheduler.commit_dispatch` normally
publishes `VISIT_OPENED` before task freezing. The approved /2 raw execution
allowlist excludes that event, and `ControlNativeBridge.prepare` only invokes
PREPARE+RESERVE. Current strategy consumers therefore have no persisted visit;
both author and reviewer have `visit_id=None`. The unchanged native task/context
checks classify the RESEARCH author's output as a sibling input to PROOF and
correctly refuse it. Different mission, stage or round cannot change that test.
An invented visit string or rewritten author provenance would not fix it.

`implementation-scratch/native-visit-boundary-r7.json` records exact source
locations/hashes and proposes a Controller decision on internally deriving and
validating the original native visit within CALL_PREPARED's existing transaction,
including reader replay checks. No such persistence change has been made. The
later /2 qualification, independent-review exposure/withdrawal and complete
communication-subaction assertions remain unexecuted. Accepted unchanged-domain
evidence remains useful only for those original domain behaviors; it does not
establish the blocked /2 integration positives.

The R7 delivery includes the exact source manifest, 134 protected-file and
approved-document hashes, static checks, narrow corrections to the R6 requirement
map and targeted test identities. The audited launcher/guard, fixed child
allowlist and finite 1800-second timeout are unchanged. No product runtime was
executed in the Developer sandbox, and no commit, independent review or
Controller acceptance is claimed.

---

# DEV06 feedback R6 candidate

This is the same Developer's candidate for Controller S2 validation. Validation006
ran the exact R4 manifest: 101 tests, 2 errors, 1 failure, no skips, 323.584 seconds,
with verified isolation. The original F1/F2/F3 probes all rejected their forged
target, budget and status. Run005 remains incomplete, cause UNKNOWN. No R5 work
is attributed to a completed Developer turn.

R6 changes fixtures and assertions, not the public DTO or product format. The
two communication-dependent cases now authorize the original finite communication
policy before native task freezing. Their previous missing communication contract
also explains the missing COMMUNICATION_APPLIED witness. The control-only rejection
fixture now preserves the original bounded error response and required metadata.
The cursor test separates exact ContractViolation/INVALID_FIELD decoding from
semantic rejection of a valid nonzero cursor naming an unobserved event.

Added targeted cases cover native pool acquire/release and scientific facade
retries, strategy/guidance cache paths, future/orphan/cross-scope authority,
missing-target and extra-mission prefixes, and the reachable source-input race
across activation using a real child barrier. Existing control tests now enter
commit_control directly for the eight subactions; existing successful recovery,
owner/revoke, cancellation, guidance and inbox commands gain denied duplicate
assertions. A synthetic scoped review case checks authentic independent capture,
qualification, paused-worker admission and equality of the native derived science
collections through the /2 facade. No central state is patched to grant authority.

The scientific activation race has two distinct cases. A previously frozen model
request is incompatible with the closed setup prefix (no missions/tasks/requests).
An original source-input proposal can reach the pre-lock choice. The unchanged
publisher rechecks the actual previous schema under the writer lock and denies
publication after activation; the new process test exercises precisely that path.
The inherited LegacyWriters.commit AST remains intact. Unchanged native assurance,
withdrawal and dependency reducers retain accepted DEV04 domain evidence; this
reuse is not represented as a new /2 withdrawal execution.

All changed runtime assertions remain **NOT_EXECUTED** pending Controller S2.
Static architecture, exact scope, syntax/AST and protected-hash checks are recorded
with the exact source manifest, commands, prior raw-result hashes, assertion-level
coverage map and limits in `implementation-scratch/feedback-r6-delivery.json`.
All 35 selected inherited checks remain selected; no original test is modified or
skipped. The Developer has not retried namespace creation or imported product code
outside S2. Independent review and Controller acceptance remain outstanding.

---

# DEV06 feedback R4 implementation snapshot

This is the continuing Developer's implementation handoff for Controller S2 execution, not an independent review or acceptance. The approved R1-final contract and public DTOs are unchanged. All R4 runtime checks are **NOT_EXECUTED** in the Developer sandbox; the preserved nested namespace denial has not been retried.

CTRL-F3 is acknowledged: validation005 accepted a rehashed PAUSE with ACTIVE instance status. The reader now checks exact native instance, run-control, mission, retry-grant, scope-version and control-event effects. Configuration and extension preserve wait states; original scientific D5/P14 transitions retain their native behavior and are tied to original captured MAIN disposition. Earlier CTRL-F2 budget checks remain. Paired reader forgeries cover TRH/FDH/SURVEY status, mission and round changes, along with lawful continuation, RESUME, END and budget/configuration operations.

The launcher now streams and fsyncs stdout/stderr, persists RUNNING before spawn, and writes completion/failure/timeout/interruption receipts with hashes and test identities. PASS requires the complete no-skip result and isolation markers. The finite ceiling is 1800 seconds: run004 took 61.848 seconds, and new pool/closure/replay cases add substantial work. Catchable interruption drains output and kills the existing child; SIGKILL/power loss leaves the durable non-success RUNNING receipt and available partial logs. Source/oracle mounts, temporary HOME, environment clearing, namespace isolation and fixed child-program restriction are retained. Two additional fixed synthetic child modes test launcher failure accounting and the native duplicate activation race. There is no fallback outside S2.

Validation005 is **INCOMPLETE_NO_VERIFIED_TEST_RESULT**, cause UNKNOWN. Only its command was recovered. Validation004's 85 tests had zero errors and one fixture failure. R3 changed that fixture to separately authorized distinct work; it still requires execution. The exact CTRL-F2 probe rejected on validation005, while CTRL-F3 still failed there. These are historical results, not proof for this candidate.

Additional R4 tests exercise direct receipt/usage cursor preservation, reader receipt/cursor/liability forgeries, an actual child crash after conflict HEAD before pool inspection, a native duplicate blocked across activation, all nine communication subactions through current authorization before native duplicate return, and lawful P4 evidence/P9 independent task preparation with exact dynamic input, exposure and withdrawal guards. Live strategy duplicate routing now reaches current authorization without incorrectly treating its old accepted plan as a new proposal at the latest strategy revision. The protected original LegacyWriters.commit/create/initial_state ASTs remain unchanged.

The exact artifact inventory, commands, hashes, test IDs, section-8 matrix, inherited-result limits and remaining coverage work are in `implementation-scratch/feedback-r4-delivery.json` outside the source tree. Controller should freeze these bytes and run the same bounded launcher against the protected DEV05 oracle, returning all failures to this same Developer thread. Tests added since run004 have not yet produced verified full-suite results; their names/counts are not acceptance evidence. Future real backend, production, migration and the original 58+46 aggregate remain NOT_EXECUTED. No local commit is made before runtime feedback.

---

# DEV06 implementation: feedback round 3

Current handoff: prepared for Controller S2 execution; full section 8 remains
incomplete. Controller validation004 ran 85 tests with no errors, one failure
and no skips. It verified the earlier DTO/AST fixes, reader target/D0/SURVEY
regressions and actual ADOPTED positive/negative tests on that frozen snapshot.
Its opposite contradiction/reuse test stopped at the lawful EXISTING_REQUEST
guard before reuse. That fixture now authorizes a distinct new mission and
scope question; it retains the original spent liability and native retry rules.

CTRL-F2 is acknowledged: a correctly hashed PAUSE journal delta could raise a
grant. The reader now checks native control subaction write sets and exact
grant, project-budget and worker-limit effects. PAUSE/P14/human-decision branches
cannot amend grants; new authorization, extension and future configuration
have separate constrained effects. New forged-reader negatives use multiple
limits, unlimited/worker fields and project budgets, with lawful authorization,
extension and future-configuration positives.

New tests also exercise real shared typed pools through registered synthetic
roots and worker duties created by the running MAIN strategy bridge; current
action permissions before historical duplicate lookup; a still-live old process
during owner takeover; post-HEAD replacement directory-fsync uncertainty; actual
captured D5/P14 waits followed by timer/guidance; and 8 MiB, node, 4096-file and
128 MiB closure bounds. D5/P14 admission revealed a missing legitimate control
version transition: the reader now allows that increment only with the matching
new APPLIED strategy disposition in the scientific transaction.

These additions are authored, not runtime-validated by the Developer. The
reviewed launcher discovers 60 DEV06 methods plus the same 35 inherited methods.
All new runtime results are NOT_EXECUTED pending Controller S2. Exact evidence
and remaining work are in `implementation-scratch/feedback-r3-delivery.json`.
Architecture, scope and static checks pass; no protected definitions changed.

Remaining work includes the full native-subaction/bridge duplicate and activation
race matrix, reader receipt/page effect-equivalence negatives, scientific
independence/invalidation adversarial coverage, exact lineage negatives and
remaining conflict/recovery crash combinations. Authored bounds and pool cases
must reach their assertions in S2 before they count as coverage. No aggregate,
independent review, MAIN acceptance, production or backend qualification is claimed.

## Previous remediation (round 2)

Status: partial implementation, prepared for Controller S2 execution. This is
neither an independent review nor an acceptance receipt. The approved contract
and example remain unchanged. Frozen base: `4239f15ad1233cc89cd6556cec284951b5fc2e3e`.

Controller validation003 ran 80 tests with 9 errors, 1 failure and no skips.
The failures and earlier validation001/002 results remain in the Controller's
immutable feedback packets. Those results describe their frozen snapshots.

This round fixes the incompatible `port_error` argument in both the fixture and
the product's local unsent proof. Both now use the existing public `evidence`
parameter. It moves misplaced READY/RESERVED assertions to the pause/send test.
The inherited AST failure was caused by adding a gate to `LegacyWriters.commit`;
that original body is restored exactly. The approved `Store.commit` facade now
routes `/2` captures through the same control admission gate. No protected test
was modified or removed from the launcher.

The immutable instance-field checks already present after validation002 are
retained. New reader regressions forge correctly hashed journal entries and HEAD
for TRH target/identity, all three FDH D0 source bindings and discovery brief,
and SURVEY scope. They exercise activation, pause and owner takeover, reopen the
reader, test old as-of rejection and retain legitimate control positives. The
paired unauthorized activation-budget regression is also included.

ADOPTED now explicitly requires an APPLIED strategy record and the exact
direction's reply reference, in addition to the current MAIN receiver and
direction-answer checks. A positive test uses the original scientific admission
path to create this evidence; negative cases cover another direction, another
receiver and an unaccepted proposal. Another test covers SENT, terminal release,
slot reuse, then contradictory NOT_SENT, complementing the opposite order.

Architecture, exact legacy scope, syntax and original initializer/admission AST
checks pass locally. Runtime tests for these changes are NOT_EXECUTED by the
Developer: nested namespace creation remains unavailable. The reviewed launcher
must run in the Controller's outer S2 environment. It now discovers 50 DEV06
test methods and retains the 35 affected inherited tests. Discovery and static
checks do not establish behavioral success.

Remaining work includes complete per-action replay/effect-equivalence negatives;
every native bridge's duplicate authorization and activation-race checks; real
multi-project 8/20 fairness and cursor coverage; full scientific independence,
invalidation and target/D0 adversarial admission; pending D5/P14 behavior; full
closure/lineage limits; and remaining owner/HEAD-fsync crash combinations. The
58+46 aggregate, future backends and production are NOT_EXECUTED. No scope is
declared complete merely from inherited tests or test counts.

Exact source inventory, protected hashes, intended test IDs, section-8 coverage
gaps, commands and feedback acknowledgment are in the Developer scratch receipt
`feedback-r2-delivery.json`. No local candidate commit has been made pending
runtime feedback. Rollback is removal of this uncommitted scoped implementation
against the frozen base; synthetic `/2` roots must be discarded or retained for
forensics, never downgraded or migrated into old readers.
