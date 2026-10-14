# Pure Math Research Harness (PMRH)

**Current development: a read-only status MVP; not a released research runtime.** PMRH preserves the Pure Math Research Studio 4.2.2-preview history and compatibility code. The new command reads existing native project facts without starting research, reconciling resources, refreshing authentication or rebuilding indexes. Help/version remain inert; control commands remain unsupported. [简体中文](README.zh-CN.md)

From this checkout, use Python 3.11+ on POSIX/Linux with bytecode writes disabled; no native binary, model credentials or additional Python dependencies are needed for status:

```sh
python3 -B -m pmrh status ./existing-project --instance INSTANCE --json
```

For an installed entrypoint, use `PYTHONDONTWRITEBYTECODE=1 pmrh status ./existing-project --instance INSTANCE --json`. `PROJECT` is the native project directory containing `project.json` and `HEAD`, not a workspace directory. Optional `--as-of COMMIT` selects an existing full journal SHA-256. Exit codes are 0 for readable project status, 1 for unavailable project data and 2 for invalid arguments. For example, querying an absent `./missing-project` returns JSON containing `"available": false, "unavailable_reason": "NOT_FOUND"` and leaves it absent.

Project projections share one commit. The global pool has an independent observation time and byte digest; missing pool counts are null. Runtime/authentication/configuration are unobserved, and report files are not verified by this command. PAUSED, UNKNOWN and exact scientific scope are preserved. See the [DEV03 contract and limits](docs/development/DEV-PR-03-CONTRACT.md).

Development controls: [AGENTS.md](AGENTS.md) · [CONTRIBUTING.md](CONTRIBUTING.md) · [Phase 0 provenance](docs/development/PHASE0-PROVENANCE.md) · [18 planned work packages](docs/development/ROADMAP.md) · [reference audit documents](docs/reference/PMRS-Next_Phase1/README.md).

The following text is the original historical **PMRS 4.2.2-preview README** retained for provenance. Its legacy runtime claims are not PMRH acceptance claims.

---

# Pure Math Research Studio 4.2.2 preview

[简体中文](README.zh-CN.md) · [Architecture](ARCHITECTURE-4.2.2.md) · [Changes](CHANGELOG-4.2.2.md) · [Validation limits](TEST-REPORT-4.2.2.md)

PMRS is a local workspace for researchers working on pure mathematics. It preserves original sources, candidate statements, Arguments, independent assessments, planning decisions, communications and observed model usage in an auditable project. Model output is candidate research until the required scientific qualifications apply.

This branch contains the **candidate22 code preview**, with publication cleanup and updated documentation. Candidate22 was built, installed in isolation and used in the single real HSC eigenvalue TRH experiment through software repairs. That experiment remains **OPEN** and was subsequently **paused at the user's request**, including its native Goal. This is **not complete feature acceptance**. FDH, SURVEY and behavior not naturally covered by that experiment are not claimed to have passed runtime acceptance. Private materials, mathematical outputs, raw sessions, authentication and local logs are not distributed here. This code push creates no tag or GitHub Release.

## What is implemented

| Product | Input | Control and result |
| --- | --- | --- |
| **TRH — Targeted Research Harness** | Exact original target, hypotheses, conventions and source materials | Its own `gpt-6-astra` Ultra MAIN dynamically chooses P0–P13 work and P14 decisions; preserves evidence and an explicitly qualified or OPEN result |
| **FDH — Formulation Discovery Harness** | D0 phenomenon, immutable background and permitted exploration axes | A separate Astra Ultra MAIN dynamically selects D1–D4; formal D5 hands evidenced candidates and comparisons to the researcher |
| **SURVEY — Survey Workflow** | Topic, selected sources and output request | Host-controlled sequential source review and reporting, without a MAIN Goal |

Each TRH/FDH instance has a separate persistent native Codex thread and Goal, bound to the original target or D0 scope, acceptance conditions and authorization. Complete dynamic-method instructions enter MAIN's actual input, including after recovery or context compression. MAIN controls stages, routes, concurrent work, returns, communication and delivery. The host admits resources, executes validated decisions and records evidence. MAIN failure does not activate an old host-planned scientific workflow.

The implementation includes:

- MAIN-selected stage CLI tasks, directed communication, dependencies and explicit waits. Each dispatch and each instance allow at most **8 stage tasks**; all projects share **20 stage slots**. SURVEY is serial and occupies the global pool.
- MAIN and Codex native internal delegation are outside those stage slots. PMRS adds no internal count, concurrency, depth, model or token quota. Authorized PMRS top-level calls remain finite and cumulative; a continuation or software repair does not reset them. Unknown usage stays unknown; parent/child counters with unspecified overlap are not summed.
- Original source versions, native Arguments, exact scope and P9/P12/D4 independence. Separate internal agents and accepted output schemas do not themselves confer independent mathematical qualification.
- A workbench exposing actual MAIN/stage inputs, materials, raw outputs, repairs, admission results, mathematical bodies, messages, errors and usage, with expansion and original downloads.
- Event-driven guidance and result handling in one MAIN flow. Configurable defaults are a lightweight 30-minute control check and a full strategic audit after about four hours of effective instance research. Normal waiting does not cause another paid analysis. Whole-instance pauses and pure external waits freeze the research clock; concurrent agent hours are not added together. MAIN-authored checkpoints are immutable and separate from disposable replay caches.
- Readable P13 reports before P14. Formal manuscripts/PDFs are generated only on explicit request or selected output settings, not after every stage. English and Simplified Chinese interfaces are available.

## Requirements and installation

The native runtime currently targets **Linux x86_64**, with **Python 3.11+** and a browser. Stage tasks need an authenticated official Codex CLI and access to the configured model modes. PDF output additionally needs the configured TeX/compiler resources. Graphical installation uses Python Tk. PMRS checks capabilities and does not silently downgrade MAIN.

This is a **source-only branch**. The two compiled native executables are intentionally not stored in Git. A plain Python install is not sufficient to run MAIN. The [native runtime guide](docs/NATIVE-RUNTIME.md) explains the pinned source, admission patch, licenses, exact companion provenance and known build limitation.

From a new checkout:

```sh
git clone --branch 4.2.2-preview https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio.git pmrs-preview
cd pmrs-preview
```

Prepare the required native pair before packaging. Either supply a previously verified pair and its matching manifest as described in the native guide, or build the patched app-server using an existing, independently obtained official companion:

```sh
# Set this to your own absolute path to the exact verified official companion.
# Its required SHA-256 is recorded in docs/native-code-mode-source.json.
export PMRS_CODE_MODE_HOST="$PWD/../native-tools/codex-code-mode-host"
sh scripts/build-native-main.sh "$PWD/../pmrs-native-build" "$PMRS_CODE_MODE_HOST"
```

The native build needs a C/C++ toolchain, pkg-config, OpenSSL development headers, curl, tar, patch, network access and enough local build storage. The script installs an isolated Rust toolchain. The matching-source companion build was blocked by an unavailable upstream V8 archive; do not assume an arbitrary Codex companion is compatible. This source push did not repeat that native build or run a new model probe.

Once the verified native pair is present, build locally and install into **new** directories:

```sh
python3 -B scripts/build-release.py --out ../pmrs-packages
python3 -B scripts/prepare-release.py \
  ../pmrs-packages/Pure-Math-Research-Studio-4.2.2-release.zip \
  --out ../pmrs-unpacked --desktop-dir ../pmrs-applications
python3 -B ../pmrs-unpacked/Pure-Math-Research-Studio-4.2.2/scripts/install-local.py \
  --venv --prefix ../pmrs-install --bin-dir ../pmrs-bin \
  --desktop-dir ../pmrs-applications
../pmrs-bin/pmrs-desktop --workspace ../pmrs-workspace
```

`build-release.py` creates local artifacts; it does not publish a GitHub Release. `prepare-release.py` checks the package manifest and safe executable modes. The installer refuses existing prefixes and launchers. Use the generated SHA-256 manifests to verify transferred artifacts. Keep workspaces and credentials outside the checkout. 4.2.2 does not migrate old project formats; use each older project with its original version.

## Use and control

1. Open **Settings & sign-in**, select the official Codex CLI, and inspect authentication, model capabilities and optional report dependencies. Do not commit authentication files or session URLs.
2. Create a project, choose TRH, FDH or SURVEY, enter the complete target/scope and add original source files. Selecting or viewing saved work does not start research.
3. Use **Start research round** with concrete intent, selected sources and an explicit finite top-level call allowance. Stage roles follow the configured stage/role/purpose matrix; research choices belong to MAIN.
4. Inspect **Actual task inputs and outputs**, route/candidate decisions, effective guidance, audits, messages and reports. Distinguish requested PMRS state from the observed native Goal state and synchronization errors.
5. For TRH, **Automatic continuation** is the default: P14 can continue the same Goal within the original scope and allowance. **Wait for a human decision at every P14** and **Stop at the next P14** hand control back at that node. Canceling a flag, viewing a paused project or switching mode alone does not resume it. An explicit continue preserves the selected P14 mode.
6. For FDH, formal D5 pauses for continued discovery, an exact user-selected candidate, continued pause or ending. A TRH handoff creates a separate paused instance with its own MAIN/Goal; starting it needs authorization. An ordinary candidate summary does not pause discovery.

**Pause now** stops new dispatches. Already sent work and usage remain recorded; closing a browser does not pause the backend. Goal success is not inferred from a stage finishing, a pause, user ending or budget exhaustion. New targets and additional budget require user decisions.

## Input/output example

This is an **illustrative workflow**, not a newly executed acceptance scenario. The repository's [teaching source](examples/readme/finite-geometric-sums.teaching.md) is explicitly labeled as teaching material.

- **Input:** create a TRH project with target “For a positive integer n and real q, establish the finite geometric-sum formula, treating q = 1 separately.” Attach the teaching source and choose an explicit finite allowance in the start form.
- **Expected product output:** an immutable source entry; actual MAIN and any selected stage task inputs/outputs; candidate statement/Argument and review records; a P13 report showing exact scope, evidence and unresolved gaps. No success verdict is promised by this example, and the teaching text is not independent review.
- **Inspection:** expand a task and download its original output; compare its admission state and scientific support with the report. A failed or OPEN result remains visible.

The existing examples, fixtures and normal test sources are retained. They do not constitute candidate22 runtime acceptance. No synthetic scenario, stress run, new research call, FDH/SURVEY paid run or test matrix was executed for this code push. See [validation limits](TEST-REPORT-4.2.2.md) and [acceptance scope](ACCEPTANCE-SCOPE-4.2.2.md).

## License

PMRS is distributed under [Apache-2.0](LICENSE). Bundled source resources retain their licenses, including MathJax and the native client patch's upstream attribution. The native binaries and private experiment evidence are not included in this branch.
