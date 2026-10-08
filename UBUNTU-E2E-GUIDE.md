# Ubuntu 26.04 installation and acceptance — PMRS 4.1.0

Use an independent empty workspace and a new installation prefix. Do not point this acceptance run at an existing research workspace. See [actual results](TEST-REPORT-4.1.0.md); the following is a repeatable procedure, not an assertion that a click already occurred.

## Installation

1. Verify the Release SHA256SUMS.txt and archive BUILD-INFO.json. Open pmrs4-graphical-installer_4.1.0_all.deb with Ubuntu's graphical package installer. This distinct package and its versioned menu entry can coexist with earlier installations.
2. Open “Install Pure Math Research Studio 4.1.0” from Applications, choose a new personal directory, and install the bundled wheel. Launch “Pure Math Research Studio 4.1.0”. Use the independent acceptance workspace; the normal 4.x default path retains its `4.0` directory name.
3. In Settings, inspect official client status and select/cancel the native Tectonic chooser. Record real native clicks separately. Command-line installation and package verification cannot stand in for native GUI observation.

For controlled offline installation, use the release's scripts/install-local.py with --prefix, --bin-dir, --venv and a private --desktop-dir. Verify every installed runtime file and wheel RECORD against the package, launch the installed desktop process with an explicit test --workspace, and use the real browser.

## Browser and execution cases

- Create SURVEY with Knowledge only and zero model calls; inspect scope, retrieval records, source versions, actual reading coverage, selected knowledge and independent readiness. Confirm no implicit manuscript, then separately request each supported output type with only that profile generated. Exercise scoped invalidation and paused handoff.
- Switch English/Simplified Chinese while preserving draft inputs, stage/tab selection, expanded bodies and scrolling; restart on another port and check persisted preference. Research bodies and reports remain English.
- Create TRW and TFDW projects with separately preserved originals; authorize only synthetic tasks with finite budgets. Inspect frozen settings and multiple policy overrides.
- Verify all workflow stages/paths, selected instance activity, unknown structure previews, node details and synchronized navigation.
- Observe new task cards and changed capture controls through polling; preserve expanded mathematical bodies. Inspect this project's native history and exact event details.
- Pause, close/reopen, inspect and admit an original capture exactly once. Reconcile UNKNOWN without resending. Verify budget exhaustion and read-only endpoints do not dispatch.
- Lose a completed operation response, restart the real desktop service while its old port is occupied, establish a session at the new origin and recover the original receipt. New explicit operation IDs must remain legitimate.
- Export a generated native project, inspect its archive, check and restore it as a new paused project with identical original bytes and no automatic task resume. Reject a deliberately unsupported minimal archive without conversion or source mutation. There is no upgrade or old-format import UI/CLI/API.
- Inspect report failures and successful synthetic reports, independent research decisions, login/session, missing CSRF, foreign origin and exact-operation replay.

## Rendering and delivery

Use scripts/verify-pdf.py from the verified extracted release, with the installed Python and its package directory with a trusted Tectonic binary, offline resources, Poppler, Bubblewrap, libseccomp, public CA bundle and fonts. Record real compiler output and inspect every rendered page. Model-supplied content and review remain controlled simulation; rendering is not proof. Report missing dependencies as unverified rather than bypassing isolation or silently installing system packages.

Run the exact 4.1 native suite and browser evidence gate. Build twice with the same SOURCE_DATE_EPOCH; compare source ZIP, release ZIP, wheel, Debian package and audit bytes. Inspect all archive members and the final file tree and newly introduced Git history for retired source/data, secrets and private outputs. The release must bind the same final commit, tag and package hashes.
