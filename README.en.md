# Pure Math Research Studio 4.0.0

[简体中文](README.md)

PMRS is a local mathematical research workspace. Targeted Research Workflow (TRW) develops and reviews an exact statement. Theorem Formulation Discovery Workflow (TFDW) starts from phenomena, immutable background and an explicit exploration scope to produce and compare candidates. They share knowledge and original materials while retaining distinct tasks, authorizations, budgets and state.

4.0.0 is an independent distribution of the current native product. It contains no earlier source trees, project upgraders, migration readers, compatibility adapters or real research project samples. The new repository starts from a reviewed file snapshot with fresh history. See the [test report](TEST-REPORT-4.0.0.md) for actual acceptance; checks that have not run are not counted as passed.

## Install and open

The target is Ubuntu 26.04 with Python 3.11+. Download `pmrs4-graphical-installer_4.0.0_all.deb` from the matching Release and verify `SHA256SUMS.txt`. Open it with Ubuntu's graphical package installer, complete system authorization, and launch “Install Pure Math Research Studio 4.0.0” from Applications. Select a new personal installation directory and install. The bundled wheel creates an isolated environment offline. Missing Python venv and Zenity system packages come from Ubuntu repositories.

Launch “Pure Math Research Studio 4.0.0” from Applications. Version 4.0 has separate package and menu identities, personal installation, configuration and default workspace; it does not automatically adopt existing research. Its workspace is `$XDG_DATA_HOME/pure-math-research-studio/4.0/workspace` (under the user's `.local/share` when XDG is unset), and settings are in `$XDG_CONFIG_HOME/pure-math-research-studio/4.0` (default `.config`). Application files and research data are separate.

If a `.desktop` file opens as text, use the `.deb` and application-menu route. Ordinary use does not require editing launchers. Existing installation directories and same-version menu entries are never overwritten; an existing same-version menu entry causes an explicit rejection. Closing the browser leaves background research running. Reopen through the application menu to reconnect; pause research before using the page's background-service exit button.

Web Settings can select an existing Codex CLI, Tectonic compiler, offline resources and public CA file, or explicitly install the listed official components. Authentication belongs to the official client; never paste passwords or tokens into projects. Missing PDF components do not prevent ordinary reading or work that does not require PDFs. Dependency detection is not an actual render test.

## Features and use

1. Create a TRW with an exact problem and assumptions, or a TFDW with separately preserved phenomenon, immutable background and exploration scope. Original UTF-8 materials are supported. Creating a paused project makes no model call.
2. Starting a round requires an explicit purpose, call limit and concurrency. Inspect model and reasoning policies by stage, role and purpose. Policy changes affect future tasks only; updating or resetting one scope preserves other overrides and frozen task settings. Unsupported capabilities fail explicitly without fallback.
3. Create multiple named workflow instances in one project. Complete TRW P0–P14 and TFDW D0–D5 maps emphasize the selected workflow and main path. A node opens duties, policies, tasks and outputs; branches and returns appear on demand, with a dual overview and all-paths option. Activity is not a proof-completion percentage. A graph without its corresponding selected instance is an unknown-state structural preview.
4. Knowledge, original materials, open duties, research history, and task/configuration views expose this native project's bodies and journal. History comes from its own immutable commits and events. Background polling updates new tasks, states and available actions while retaining the current reading snapshot and expanded sections. Changing project or instance clears inapplicable stage details and filters.
5. Pause retains in-flight requests and captured results. Admitting a captured result reads its existing response without resending. Abandoning UNKNOWN retains consumption; confirming that a request was not sent requires selecting an actual transport-evidence original bound to that request. A note alone is not evidence.
6. If an operation response is lost, query its original result. Unacknowledged receipts persist in the workspace and can be found after a restart or port change. Completed results are recovered directly; PENDING is never resent automatically, and failure requires inspection and explicit acknowledgement. A deliberate new operation uses a new key, allowing the same input to be used again.
7. Candidate comparison and adoption bind the exact candidate and scope and create a new paused workflow without granting proof authority. Lecture and minimal reports track semantic and actual-page review independently. Report failure does not automatically block otherwise authorized research decisions.
8. Export Backup saves this project's native archive. Restore Native Backup first checks it and then creates a separate project. Restore retains native knowledge, materials, journal and captures while pausing workflows; it never automatically resumes old tasks. Inputs outside the current native contract are explicitly rejected without conversion or modification of originals.

A zero-model input/output example: create a TRW named `Arithmetic example` with `For every integer $n$, $n + 0 = n$.`. The expected result is a paused instance retaining the original sentence as material and target, with zero calls. Saving it does not establish proof. Home-page demonstrations create isolated synthetic projects and are not real research results.

## Scope and limits

This version retains the current native storage structure and safe native backup/restore. Internal format identifiers are independent of the product version; keeping a format identifier is not a promise of backward compatibility. There are no old-format import, upgrade or conversion commands, historical source trees, concrete research originals or continuation packages. See the [4.0 acceptance scope](ACCEPTANCE-SCOPE-4.0.0.md) for retired requirements and retained coverage.

Original material, a successful save, task completion and report output do not establish mathematical proof. Support and qualification bind exact objects, revisions and checked scope. This release does not provide formal verification. Costs and effective configuration or usage absent from client responses remain unknown. Paid research requires explicit authorization; development acceptance uses controlled simulation.

## Advanced maintenance and development

Ordinary operation is available through the web UI. The advanced CLI shares its service layer:

```bash
python3 -m research_studio --help
python3 -m research_studio project init --problem examples/problem.zh-CN.md --out ../new-project
python3 -m research_studio status ../new-project
python3 -m research_studio audit ../new-project
python3 -m research_studio project restore BACKUP.zip --out ../restored-project
```

From a verified, extracted release ZIP, offline prefix installation: `python3 scripts/install-local.py --prefix NEW_PREFIX --bin-dir NEW_BIN --venv`. Choose new directories; add `--desktop-dir` for application-menu registration. Maintenance acceptance uses a separate private menu directory instead of overwriting an existing same-version entry. Keep tests and builds outside the source tree:

```bash
python3 -B scripts/test-runner.py --out ../validation/suite.json
python3 -B scripts/validate-groups.py --out ../validation/required --browser-evidence ../validation/browser-evidence.json
SOURCE_DATE_EPOCH=315532800 python3 -B scripts/build-release.py --out ../artifacts
```

Acceptance requires actual executions of this version, not an earlier release's PASS. Builds produce a source ZIP, installable release ZIP, wheel, graphical `.deb`, artifact inventory and checksums. Building alone establishes packaging integrity, not product acceptance.

More: [architecture](ARCHITECTURE-4.0.0.md), [changes](CHANGELOG-4.0.0.md), [Ubuntu installation and acceptance](UBUNTU-E2E-GUIDE.md), [license](LICENSE).
