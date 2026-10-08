# Pure Math Research Studio 4.0.0

[简体中文](README.md) · [Download](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/releases/tag/v4.0.0) · [Validation record](TEST-REPORT-4.0.0.md)

**Keep the mathematical question, the research process and the evidence for each check in one local workspace.** PMRS is for people who want to use models for mathematical research while retaining exact source material and traceable records. Work on a fixed statement through derivation, counterexample search and independent review, or start from observations and compare formulations until you can select a statement worth proving.

Outputs include statements and arguments, examples and counterexamples, source references, review coverage, open questions and research reports. Tasks, call authorizations and original responses stay in the local project so you can pause, inspect and continue the work.

**Start here:** [choose a workflow](#choose-a-workflow) → [install and open](#install-and-open) → [run-a-round instructions](#run-a-round-of-research) → [two worked usage examples](#two-worked-usage-examples).

## Choose a workflow

| What do you have? | Choose | Main outputs | What do you decide next? |
| --- | --- | --- | --- |
| A statement with precise objects, assumptions, quantifiers and a conclusion | **TRW · Targeted Research Workflow** | Derivation or refutation, exact gaps, independent checks, progress and reports | Continue, pause, end, or explore alternative formulations |
| Observations, examples or a family of conjectures whose formulation needs work | **TFDW · Theorem Formulation Discovery Workflow** | Evidence, exact candidates, comparisons and unchecked scope | Keep exploring, retain candidates, or adopt one for a TRW |

A **project** holds shared knowledge and materials. A **workflow instance** binds a research target or discovery scope. A **research round** records the current intent, authorization and call limit. One project can contain several named instances that share materials and keep separate state. Adopting a candidate creates a new paused instance and preserves the original workflow.

### TRW: investigate an exact statement

![TRW: frame, investigate, independently review and integrate, present progress, and record the researcher's decision](examples/readme/trw.en.svg)

The groups show how different kinds of work relate. **P0–P14 are available research activities, not a sequence that every round must execute.** Work is selected from concrete questions, dependencies and remaining authorization. In the current web UI, starting a TRW initially assigns derivation work at P4. Clicking a stage opens its details; it does not force that stage to execute.

| Stage | Work and results to inspect |
| --- | --- |
| P0 · Target and authorization | Fix the statement, existing knowledge entry points and bounded authorization. |
| P1 · Context and notation | Clarify objects, definitions, assumptions, quantifiers and notation. |
| P2 · Relations and routes | Distinguish necessary, sufficient and equivalent conditions and possible routes. |
| P3 · Work selection | Select concrete, justified work with a limited scope. |
| P4 · Derivation and construction | Attempt derivations, constructions, counterexamples and failed approaches; save what was actually obtained. |
| P5 · Target gap | Compare existing results with the original target and identify what is still missing. |
| P6 · Problem reduction | Organize AND/OR subproblems while retaining the work needed to lift local results to the original target. |
| P7 · Obligation analysis | Apply a source, derive directly, or compare both routes and then synthesize, as needed. |
| P8 · Repair and falsification | Repair a specific gap and search for targeted counterexamples. |
| P9 · Independent checks | Review proofs and counterexamples independently, recording checked and unchecked scope. |
| P10 · Integration | Combine local results under common context and same-witness requirements. |
| P11 · Change accounting | Compare with the starting point: additions, reuse, support changes and open work. |
| P12 · Assembled-argument review | Independently review the assembled argument; parts may remain open. |
| P13 · Progress and reports | Present current progress; prepare formal reports when explicitly requested. |
| P14 · Researcher decision | Record your choice to continue, pause, end or hand off. |

For example, P4 results may go directly to P9 for review; a gap found at P9 may return to P8 for repair; P12 may request integration again. P0–P12 also allow early delivery to P13, preserving unresolved questions. Reentry needs a concrete question, inputs and bounded retry authorization.

A candidate proof or refutation of the original fixed target requires the corresponding independent dual review. Local results are checked against an explicitly required scope; passing a local check does not establish the whole statement.

### TFDW: turn observations into a researchable statement

![TFDW: frame observations, collect evidence, formulate and probe candidates, review independently, and hand off by human choice](examples/readme/tfdw.en.svg)

TFDW separates three inputs: **what you observed, what background must stay fixed, and what you permit the research to vary.** This preserves the question's boundaries when candidates are compared. Starting a TFDW in the current web UI initially assigns evidence-learning work at D1.

| Stage | Work and results to inspect |
| --- | --- |
| D0 · Phenomenon and scope | Fix the observations, immutable background and allowed exploration scope. |
| D1 · Evidence and failures | Organize positive and negative examples, failure mechanisms and unknown coverage. |
| D2 · Candidate formulations | Construct exact candidates along explicit axes of variation and identify comparisons to investigate. |
| D3 · Discriminating research | Use distinguishing examples, local derivations and mechanism analysis to evaluate candidates. |
| D4 · Independent review | Examine formulations, evidence selection, logical comparisons and interpretive limits. |
| D5 · Candidate selection | Present the candidate frontier, record your choice and prepare reports when requested. |

D4 can return to D2 for reformulation or to D3 for further investigation. D0–D4 may also present existing candidates and unknowns early at D5. There may be no candidate when evidence is insufficient, and a comparison may remain unknown.

In “候选比较与交接” (candidate comparison and handoff), read the complete candidate, click “采用为新的定题研究” (adopt for a new TRW), then confirm “采用并创建暂停的 TRW”. **Adoption means selecting an exact research target.** The new TRW needs a separate start and its own proof and review work. You can also create a paused TFDW from a TRW target while preserving the original statement.

### Read the application diagrams

- The default view emphasizes the selected instance's workflow and main path. Switch to the other structure or open “双图总览” (both workflows).
- Select a node to inspect duties, model policies, tasks and outputs. Related branches, returns and early-delivery paths appear on demand; “显示全部路径” retains every legal path.
- An iteration marker indicates authorized reentry. The activity area shows running or waiting P/D stages, including several active stages during parallel work. Stage numbers are not completion percentages.
- Without a loaded instance for that workflow, the graph is a structural preview with unknown state. It cannot tell you whether the stage has been visited.

## Install and open

The target is **Ubuntu 26.04**, with **Python 3.11+**.

1. Download `pmrs4-graphical-installer_4.0.0_all.deb` from the [v4.0.0 Release](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/releases/tag/v4.0.0) and verify the accompanying `SHA256SUMS.txt`.
2. Open the `.deb` with Ubuntu's graphical package installer. After system authorization, launch “Install Pure Math Research Studio 4.0.0” from Applications and select a new personal installation location. The bundled wheel creates an isolated environment offline; missing Python venv and Zenity packages come from Ubuntu repositories.
3. Launch “Pure Math Research Studio 4.0.0”. In “设置与登录” (settings and login), select existing Codex CLI, Tectonic, offline-resource or public-CA paths, or explicitly install the listed official components. Authentication belongs to the official client.

If a `.desktop` file opens as text, use the `.deb` and application-menu route above. Existing installation directories and same-version menu entries are never overwritten. Without PDF components you can still read knowledge or perform work that does not need PDFs; report dependencies are checked separately before PDF generation. See [installation help](INSTALL-HELP.html).

Version 4.0 uses separate installation, menu, configuration and default-workspace paths and does not automatically adopt existing research. The default workspace is `$XDG_DATA_HOME/pure-math-research-studio/4.0/workspace`; settings use `$XDG_CONFIG_HOME/pure-math-research-studio/4.0`. Without XDG overrides, these use the user's `.local/share` and `.config`. Application files and research data are separate.

## Run a round of research

1. **Create a paused project.** In “新建项目” (new project), select TRW and enter the full statement, or select TFDW and fill in its three discovery inputs. UTF-8 problem files and supplementary materials are supported. Creation makes no model call. An incomplete TFDW may explicitly be saved as a draft; complete it before starting.
2. **Set intent and budget.** In “开始本轮研究” (start this research round), enter a specific purpose, maximum call count and maximum concurrent tasks. The UI defaults are 12 calls and concurrency 2; adjust them as needed. Submitting authorizes and starts the necessary work. A call limit does not guarantee completion of the research and reports.
3. **Check model policies.** Policies distinguish stage, role and purpose. To override one, first click “加入或更新此作用域” (add/update this scope), then submit. Future-policy edits affect new tasks only. Updating or resetting one scope preserves other overrides and existing frozen requests. Unsupported capabilities fail explicitly without fallback.
4. **Inspect progress and gaps.** Use “当前知识” (current knowledge) for bodies and support scope, “开放问题” (open questions) for missing work, and “任务与配置” (tasks and configuration) for actual execution state. New tasks and actions update automatically. Knowledge bodies retain the reading snapshot; refresh them when you choose after an update notice.
5. **Request reports or decide what follows.** Click “制作研究报告” (prepare research reports) to request formal reports. They have lecture and minimal versions, with separate semantic and actual-page checks. Reports are explicitly requested and share the round's call limit. Only selecting the report-first option makes report completion a prerequisite for continuing, ending or adopting a candidate.

To learn the interface without real model calls, open “使用指引” (usage guide) and select “运行命题示例” or “运行候选与交接示例”. These create independent deterministic simulations whose output carries test-isolation markers. Simulated output is not a real research result.

## Two worked usage examples

These are teaching inputs you can paste into the forms. The mathematical results below are references for inspection, not records of a real model run or guarantees of the exact output. Creating a project makes no model call; clicking “开始本轮研究” starts work through the selected executor under your authorization.

### Example 1: use TRW to study the sum of the first n odd numbers

**Situation:** you already have a precise statement and want an inspectable proof with explicit review coverage.

Create a **TRW** project named `Odd-number sum`, name its first instance `Induction proof`, and paste this into the full-problem field:

```text
Prove that for every positive integer n,
1 + 3 + 5 + ... + (2n - 1) = n^2.
State the positive-integer domain and summation convention explicitly.
Give a complete proof; finitely many examples do not prove the general statement.
```

After creation, expect a paused TRW instance, the original problem retained and no model requests. Open the start-round form and enter this intent:

```text
Try mathematical induction first. Check the base case n = 1 and the step
from n to n + 1. Preserve the quantifiers and positive-integer domain.
Explain the proof's coverage and any remaining gaps.
```

Confirm the call limit and concurrency, then start. Inspect the result in this order:

| Where to look | What to check |
| --- | --- |
| Current knowledge | Does the argument include the base case and the step from adding $2n+1$ to $n^2$ to obtain $(n+1)^2$? |
| Tasks and configuration | Which derivation and independent-review tasks actually ran? What settings were frozen on their requests? |
| Open questions | Is any required review or scope still incomplete? Task completion is not a substitute for these checks. |
| Research reports | When you want a deliverable, request a report explicitly and inspect both versions and their review states. |

**Reference result:** the base case is $1=1^2$. If the first $n$ terms sum to $n^2$, adding the next term $2n+1$ gives $(n+1)^2$. The records should let you trace the argument and independent-review scope. If the budget runs out or a check is incomplete, retain that open status.

### Example 2: use TFDW to discover when a consecutive-integer sum is divisible by its length

**Situation:** you have observed a pattern and need to determine the right statement and its essential conditions.

Create a **TFDW** project named `Consecutive integers`, with instance name `Find divisibility conditions`. Fill the three inputs separately.

**Phenomenon:**

```text
1+2+3=6 is divisible by 3; 1+2+3+4=10 is not divisible by 4;
1+2+3+4+5=15 is divisible by 5.
If the starting integer and number of terms vary, when is the sum of
consecutive integers divisible by the number of terms?
```

**Immutable background and constraints:**

```text
The starting value a is any integer; the number of terms n is a positive integer.
Study S(a,n)=a+(a+1)+...+(a+n-1). Divisibility means integer divisibility.
```

**Allowed exploration directions and scope:**

```text
Vary a and n, and compare odd and even n.
Find a necessary and sufficient condition on n, and check whether it holds
for every integer a. Preserve consecutive integers and integer divisibility;
do not replace them with arbitrary real numbers or a different sum.
```

After creation, check that all three originals were retained and the instance is paused. For a research round, use an intent such as: “Construct positive and negative examples, compare odd and even lengths, propose exact candidates and record unchecked scope.”

Read “候选比较与交接” (candidate comparison and handoff): inspect the full quantifiers and assumptions, then the examples, counterevidence and unknown comparisons. A **reference candidate to check against** is: for every integer $a$ and positive integer $n$, $n$ divides $S(a,n)$ if and only if $n$ is odd. The calculation to inspect is

$$
S(a,n)=na+\frac{n(n-1)}{2},\qquad \frac{S(a,n)}n=a+\frac{n-1}{2}.
$$

Once a candidate is available, hand it off as follows:

1. Read and select that exact candidate. A few examples alone do not prove its general statement.
2. Click “采用为新的定题研究”, review the full statement, then confirm “采用并创建暂停的 TRW”.
3. Switch to the new TRW in the workflow selector. It shares project materials with the preserved TFDW. It starts paused, makes no automatic call and gains no proof qualification from adoption.
4. Set a separate purpose and budget for the new TRW and explicitly start the proof work. Use research history to trace candidate formation and adoption later.

## Read, pause and save

| Need | Entry point and behavior |
| --- | --- |
| Inspect originals and evidence | Original Materials retains original files. Current Knowledge shows full text, formulas, versions and actual support scope. |
| See what changed | Round Changes distinguishes additions, reuse, support changes and withdrawals. Research History retains this project's immutable commits and events. |
| Pause or continue | Pause stops new dispatch and retains in-flight requests. Continue Existing Research uses existing authorization and balance. Ending the round makes the instance `ENDED`; further research requires explicitly creating a new instance. |
| Admit a captured result | Admit Captured Result reads the original response without resending. |
| Handle UNKNOWN | Resolve the original request rather than automatically resending. Abandoning the wait retains uncertainty and consumption. Confirming not-sent requires binding actual transport-evidence originals; a note alone is not evidence. |
| Recover a missing operation response | Query or recover the original operation. Workspace receipts survive service restart and port changes. Completed results are recovered directly; PENDING is not automatically resent. A deliberate new operation gets a new key. |
| Back up or restore | Export Backup writes a native archive. “恢复备份” (restore backup) opens the native-backup dialog, checks the archive and creates a new paused project without automatically resuming task execution. |

Closing the browser does not stop background research. Reopen the same workspace from Applications. To exit the service, pause research, wait for in-flight work to finish and use the exit button at the bottom of the page. Keep passwords and tokens out of project materials.

## Scope and validation

4.0.0 is an independent distribution of the current native product, with fresh repository history created from a reviewed snapshot. It retains current native storage and backup/restore. It contains no earlier source trees, upgraders, migration readers, compatibility adapters, real research project samples or continuation packages. Inputs outside the current native contract are rejected without silent conversion or modification of originals. Internal storage-format identifiers are independent of the product version.

Original material, a successful save, task completion and report output do not establish mathematical proof. Support and qualification bind exact objects, revisions and checked scope. This release does not provide formal verification. Effective configuration, usage and actual costs absent from client responses remain unknown.

The [4.0.0 validation record](TEST-REPORT-4.0.0.md) distinguishes executed checks from unverified scope. Native desktop installation/menu launch and opening/cancelling the Tectonic chooser still await human validation. This documentation update does not run paid research or count tutorial reference results as acceptance evidence. See the [acceptance scope](ACCEPTANCE-SCOPE-4.0.0.md) for retired requirements.

## Advanced maintenance and development

Ordinary operation is available through the web UI. The advanced CLI shares its service layer. From the source directory:

```bash
python3 -m research_studio --help
python3 -m research_studio project init --problem examples/problem.zh-CN.md --out ../new-project
python3 -m research_studio status ../new-project
python3 -m research_studio audit ../new-project
python3 -m research_studio project restore BACKUP.zip --out ../restored-project
```

From a verified, extracted release ZIP, install offline into a new prefix with `python3 scripts/install-local.py --prefix NEW_PREFIX --bin-dir NEW_BIN --venv`. Add `--desktop-dir` for application-menu registration. Maintenance acceptance uses a separate private menu directory instead of overwriting existing entries. Keep test and build outputs outside the source tree:

```bash
python3 -B scripts/test-runner.py --out ../validation/suite.json
python3 -B scripts/validate-groups.py --out ../validation/required --browser-evidence ../validation/browser-evidence.json
SOURCE_DATE_EPOCH=315532800 python3 -B scripts/build-release.py --out ../artifacts
```

Builds produce a source ZIP, installable release ZIP, wheel, graphical `.deb`, artifact inventory and checksums. A successful build establishes packaging integrity only; acceptance requires actual execution records, not a previous version's PASS.

More: [architecture](ARCHITECTURE-4.0.0.md) · [changes](CHANGELOG-4.0.0.md) · [Ubuntu installation and acceptance](UBUNTU-E2E-GUIDE.md) · [license](LICENSE).
