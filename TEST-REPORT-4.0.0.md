# PMRS 4.0.0 validation

Executed on Ubuntu 26.04.1 LTS, x86_64, Python 3.14.4. All work used independent installations, generated mathematical examples and controlled task execution. No paid research calls or existing research workspaces were used. No 3.4.0 acceptance result is counted as a 4.0.0 PASS.

## Results and limits

| Evidence | Actual result |
| --- | --- |
| Current native tests | 201 distinct tests passed; no failed, errored, skipped or unexpected-success native test |
| JavaScript tests inside the frontend wrapper | 36 passed; these are nested evidence, not 36 additional native tests |
| Installed-browser paths | 37 of 39 observed; 2 native desktop paths remain unverified |
| Retained acceptance assertions | 111 PASS, 3 SKIP, 0 FAIL out of 114 |
| Retained baseline behaviors | 108 PASS out of 108 |
| Acceptance cases | 84 complete PASS and 2 partial out of 86 |
| Required-core gate | Complete |
| Automated installed-browser gate | Complete |
| Strict complete gate including native desktop clicks | Incomplete; not reported as PASS |

The three skipped assertion mappings are N40.a1, N40.a2 and WEB01.a1. They refer to two native actions: installing and launching through the native desktop menus, and opening/cancelling the Tectonic file chooser. The current computer-control surface cannot perform native desktop clicks. CLI installation, menu-file inspection and browser interaction do not substitute for those observations. The old version's human checks remain historical only. Follow the [Ubuntu instructions](UBUNTU-E2E-GUIDE.md) to finish these two checks with the final package.

## Exact execution lineage

The tested code, tests, coverage mappings and resources have manifest SHA-256 `1fd77d8a2152f40f15443b4097c2cf61aea6ff249f15611d69495773fd8d0507`. The manifest intentionally excludes root release prose, which records results afterwards; final source-package binding additionally covers all root documentation.

A final-source run executed 200 tests in 130.018 seconds with unchanged source. The remaining N03 pressure test completed in the earlier in-progress 4.0.0 run. During that run, actual browser inspection identified and prompted a correction to native history filtering. Its aggregate source-change status is retained as failed qualification, not rewritten as a clean-suite PASS. Only the successful N03 result is reused: its 32-file test and transitive native dependency set is byte-identical to the final tree, and its execution does not use the changed history view. The private combination check verifies the original logs, plans, child results, dependency hashes, the isolated history-function change and the exact final 201-test set. All other tests were run again on the final source. This is an explicit two-run qualification, not a claim that one unchanged-source run executed all 201 tests.

The native-history correction has current regression and browser evidence: selecting an adopted TRW instance includes its own adoption and visit records without inheriting the source TFDW's stage visits; later adoption does not rewrite earlier frozen history.

## Targeted observations

- TRW P0–P14 and TFDW D0–D5 retain all stages and legal paths. Current-instance activity, main paths, selected-node details, all-path and dual-workflow views, navigation clearing and task refresh were exercised. Model/reasoning overrides affect future requests while existing requests remain frozen.
- Capture inspection is read-only; explicit continuation admits the original capture once. UNKNOWN stays attached to the original request and requires explicit reconciliation. Budget controls and report failure duties remain visible without unauthorized dispatch.
- Current native backup export, checking and paused restore preserve original bytes, request/capture identity and native history. A minimal unsupported archive is rejected clearly without a converter or source mutation.
- A completed operation's response was deliberately lost. The real installed desktop service was stopped, its old port occupied and the service restarted on another port. The new browser session recovered the original result and acknowledged the same receipt: one project, one original receipt and zero requests at recovery. A subsequent deliberate creation produced a distinct project normally.
- Real installed-browser requests exercised login/session, missing CSRF, cross-origin refusal and exact-operation replay. Repeated operation identity returned the same result with one source and one material commit. Local read-only ledger checks corroborate the observations.
- Synthetic report generation used actual isolated rendering and rendered PDF/PNG output. Semantic/visual gates, report-first failure and retained reports/open duties were exercised with simulated model responses. A rendered report is not a mathematical proof.
- The installed candidate's 54 runtime/resource files were matched exactly to the final tested source. All browser captures and failed attempts remain outside the product in the private evidence set; failed or transient observations are not counted as successful evidence.

## Storage measurement

N03 actually created 10,000 synthetic native records and 10,000 body blobs, then executed 1,000 control commits. The body count remained 10,000. Measured journal size was 1,012,931 bytes; the control delta was 663,673 bytes. Total elapsed time was 2,724.118 seconds, including validated fixture initialization and the final audit; process maximum resident memory was 605,872 KiB. This is an observed functional stress case on this host, not a throughput guarantee.

## Release and scope boundary

The [scope record](ACCEPTANCE-SCOPE-4.0.0.md) explicitly retires old upgrade/read/compatibility paths and their exclusive cases. Seven old cases, one separately mapped assertion and 23 old behavior mappings are retired with reasons rather than counted as passing. Applicable native archive, recovery, source-integrity, scientific, workflow and security tests remain required and use generated fixtures.

Before publication, the delivery procedure separately verifies the fresh parentless Git history; both complete build byte sets; source ZIP versus the committed file tree; release/wheel/Debian members and hashes; installed runtime versus the browser-tested runtime; and the final commit/tag/Release asset binding. BUILD-INFO.json, FINAL-ARTIFACT-AUDIT.json and SHA256SUMS.txt accompany the release. These artifact checks do not manufacture browser or native-GUI PASS results.

Not covered: the two native desktop clicks above, other operating systems/architectures, live paid-model research, migration or upgrade of old projects, and the scientific truth of generated examples. Browser engine version was not exposed by the browser-control API and is not invented. The release is authorized with the stated native-click limitation; the strict complete gate remains incomplete until actual current-version observations are supplied.
