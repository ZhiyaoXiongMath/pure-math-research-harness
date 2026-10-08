# PMRS 4.2.0 validation and evidence provenance

## Version 4.2.0: retained development evidence

Version 4.2.0 includes the completed workflow/resource repairs and new project assistant described in the [implementation notes](IMPLEMENTATION-NOTES-4.2.0.md). The following executions occurred during development before the product version changed. Their original commits, source hashes, observed results and limitations remain intact. They support only the corresponding unchanged behavior after recorded comparison; they are not relabelled as a newly executed 4.2.0 full suite. Published v4.1.0 retains its original commit/tag/Release/assets and has a separate historical section below.

| Development evidence | Observed result and exact scope |
|---|---|
| Workflow/resource stage | 49 tests passed on its recorded source, followed by a 25-test affected selection after the concrete correction-dependency fix; overlapping test IDs are not summed. The stage was preserved at commit `be077b52cf9ea1c9ba8bec6b9ece7cc018a733cb`. |
| Project-assistant final finite selection | 32 tests passed in 134.161 seconds with the source unchanged, including native assistant transport, exact report revision, actual HTTP multi-turn delivery, model policy and directly affected workflow/report/queue regressions. Tested source-content SHA-256 `248ea2ea73e675cc2544d8be7b786b26a62b99f388af77309f6a5e77edc5c715`; implementation preserved at commit `d3f34efdd3594b3d947ff0c588ab29a1ccd9976f`. |
| Actual local Web and report checks | Project/task/report assistant entry points and English/Chinese Guide were opened. A paused synthetic project retained its exhausted research budget; two assistant requests and six report-revision requests produced real revision-1 lecture/minimal PDFs and native controlled semantic/page-review receipts, retaining revision 0. |
| Finite context/resource evidence | Selected-input references, original-request recovery and the measured phase estimates are detailed in the implementation notes. A 109,748-byte old manuscript and three effective user messages used one reference per material; the new author packet was 12,471 bytes, without original text inline in the snapshot. No arbitrary workload memory bound is claimed. |
| Repository/documentation cleanup at `5820bb118860e789d09a63c7d00d85fe529fb7e9` | Removed four old release documents and updated current release prose. Two normal builds produced identical artifacts; source and installer document collections, manifests/hashes and local links passed. Runtime, UI and test bytes at that commit matched the accepted implementation. |
| Subsequent README integration | Reorganized both READMEs around actual entry points, tutorials and workflow examples while retaining the published/candidate distinction. Corrected six Guide messages for control names and the CLI allowance distinction: `start` requires an explicit limit; `plan-work` defaults to 8. Six inline Mermaid diagrams rendered, affected Guide text opened in both languages, the existing focused Guide DOM test passed, and 81 local file/anchor links passed against source and installer document sets. Earlier workflow/model/resource tests are reused for unchanged implementation; these display checks are not a new full functional-suite run or release qualification. |

The matching source ZIP contains `tests/test_assistant_kernel.py`, `tests/test_assistant_reports.py` and `tests/test_assistant_surface.py`; installer ZIPs deliberately contain product resources and user documentation rather than test sources. Detailed local execution logs, dependency comparisons, browser captures and artifact receipts are retained separately. Their prior source identities remain intact; documentation changes do not relabel earlier runs as a fresh full-source suite. No paid-model research, real research project operation, unrelated installation repeat or full historical-suite rerun was performed. Synthetic responses demonstrate software behavior, not scientific truth or live model availability.

The 4.2.0 build has its own `BUILD-INFO.json`, source/release manifests, artifact audit and `SHA256SUMS.txt` binding its actual commit/tree and bytes. Earlier reproducibility and package checks do not supply new artifact hashes. Ordinary operation and current limits are self-contained in the [README](README.md), [scope](ACCEPTANCE-SCOPE-4.2.0.md) and [architecture](ARCHITECTURE-4.2.0.md).

## Version 4.2.0 release verification boundary

Release-specific checks cover the changed product version, menu/installer identities, packaged documentation and resources, exact source and package manifests, and deterministic builds. Fourteen affected localization, packaging and Debian unit checks passed; the English and Simplified Chinese 4.2.0 title, footer and in-app Guide were opened in a separate empty, read-only workspace. The six README Mermaid definitions retain the previously rendered bytes. Functional evidence is reused only where the final dependency comparison supports it; affected version/display behavior is checked separately. Final clean-commit builds, installed-wheel version smoke and remote publication readbacks have separate release receipts; the shipped BUILD-INFO, manifests, artifact audit and checksums identify their actual inputs and artifacts. This document does not claim a repeated native desktop installation or a full historical-suite run.

Neither the development batches above nor the historical 198-test record below are summed into a new total. Likewise, the historical 46-path browser registry and 37 observed paths retain their original source and observation channels. No full historical suite, N03 stress test or all-path browser campaign is implied by this version's release preparation. A missing observation remains missing; artifact integrity is not mathematical qualification or live-model validation.

## Published v4.1.0 baseline record

All remaining results and historical installation candidate numbers in this document describe the published baseline. They preserve their actual provenance and partial observation boundaries.

**198 distinct mapped native tests passed through explicit, dependency-checked evidence reuse. The finite resource matrix and both current-version human native checks passed. Actual interface observations cover 37 of 46 registered paths across CUA and human channels; the strict all-path gate remains incomplete.**

PMRS 4.1.0 adds an independent Survey workflow, English and Simplified Chinese interface resources, selected English survey editions, and bounded preparation of immutable research inputs. TRW and TFDW retain their native contracts. The product version changes to 4.1.0; existing storage and contract versions do not change merely because the product version changes.

## Validation scope and provenance

Validation ran on Ubuntu 26.04.1 LTS, Linux 7.0.0-38, x86-64, Python 3.14.4. Tests use native project records, task preparation, capture, admission and reporting with explicitly synthetic responses. No paid model calls were made for this validation. Synthetic readiness is not mathematical certification, and generating or inspecting a report does not establish a proof or complete a real literature review.

Evidence records distinguish three identities:

* **Full source identity:** the coverage registry includes runtime, scripts, tests and selected release files. A changed file changes that identity. A source-changed aggregate suite cannot be relabelled as a successful final-source run.
* **Runtime dependency identity:** an earlier result is reusable only for its actual executed test and unchanged relevant dependencies, with a recorded byte comparison. The installed candidate has 65 package files. Candidate 2 changes only `research_studio/static/workbench.js` from candidate 1; all 49 Python package files are unchanged.
* **External acquisition identity:** public-provider receipts record their actual time, request outcome, original bytes and extracted derivative hashes. They are transport evidence; they do not inherit a final source qualification or establish mathematical relevance.

The latest installed candidate was built from commit `db5b934efa652b201bed88b96c4c343ab1a7a018`. Candidate 3 adds only a browser label translation to the candidate-2 runtime; all 49 Python package files remain unchanged. The validated source manifest is `8c79af439a96f9cc79fa20c0d0a1c823dbb12cd56e82e0d6fcac069a79b669cd`. The final seal changes only `TEST-REPORT-4.1.0.md`. Final packaging commit/tree and archive source-content identity are recorded in the shipped `BUILD-INFO.json`; per-file and artifact hashes are recorded in the manifests and `SHA256SUMS.txt`. This report does not embed its own future commit or artifact hash. Root release prose is excluded from the tested source manifest; the final package manifests additionally bind that prose.

## Core and coverage results

| Run | Observed result | Interpretation |
|---|---|---|
| Final fast selection | 197 tests: 195 PASS, 1 FAIL, 1 ERROR, no skips | The error names an obsolete 21-stage method; the inventory failure identifies the omitted WEB07 and eight resource milestone entries. This aggregate remains unsuccessful. |
| Coverage repair selection | 17 tests: 17 PASS, no failures, errors or skips | The registry now resolves the 29-stage method and includes the added milestone cases. Packaging and model-policy checks passed. No runtime code changed for this repair. |
| Original heavy-suite attempt | INCOMPLETE: status 143; no measurement/final manifest | The termination cause is not established. No result from that unfinished N03 is counted. Its original log and incomplete status remain preserved. |
| Separate final-source N03 | 1 test: PASS, no failures, errors or skips | The unchanged original 10,000-record / 1,000-control test completed in its own persistent process, with the final source unchanged throughout. |
| Final UI correction selection | 4 tests: 4 PASS, no failures, errors or skips | Current-source wrappers cover the corrected labels and project/instance switching, including the nested frontend and locale assertions. |
| Final deduplicated mapped core result | **198 distinct current test IDs: 198 PASS; core_complete=true** | Exactly 186 fast, eight repair, three UI and one N03 result are selected. Ten supplemental passing tests are not added to that mapped count. Failed or incomplete aggregate runs are not relabelled as successful. |

The combination verifies original log/source-map hashes, the exact current registry selection and unchanged relevant dependencies, including all 88 Python files. Affected frontend wrappers use the final complete source identity. The private combination receipt binds artifact SHA-256 `e9af13885b7f719da29b082b838d5383f41c93436e16c92bc6bea5e2b36ea14a`. This is an explicit combination of actual executions, not a claim that one uninterrupted suite passed.

N03 retained exactly 10,000 original body blobs after 1,000 control commits. Measured journal entries totaled 1,012,931 bytes and control deltas 663,673 bytes; the measured fixture took 2,919.478 seconds, with process maximum RSS 607,540 KiB. Its final record/body equality and store audit passed. This Store-scale check is separate from bounded task-input preparation and is not a throughput or unlimited-size guarantee.

Targeted native regressions cover Survey scope and independent readiness, explicit activity budgets, stale knowledge/output plans, exact report selection through concurrent plan changes, abandoned reports, exact selected roots, capture recovery, report author/semantic/visual isolation, localization preferences and packaging assets. Synthetic captures exercise the actual contracts and admission path; they are not real model output.

## Finite resource validation

Preparation admits at most **32 MiB of unique material and scoped metadata together**, with an 8 MiB metadata sublimit. A serialized packet or complete frozen request is limited to 64 MiB. Streaming uses 256 KiB chunks. These byte limits supplement the existing token and output-reserve checks.

Preparations use at most `min(2, project.max_workers)` slots. Reservations account for estimated memory of 256 MiB per slot / 512 MiB total, temporary disk of 512 MiB per slot / 1 GiB total, and a 512 MiB free-disk margin. These are admission/accounting bounds, not an OS memory limit or a claim of safety at arbitrary scale. The existing renderer cache allowance is preserved. Project and shared-host research concurrency policies are unchanged.

Disposable checkpoint retention is **four recognized checkpoint files / 128 MiB**, with the latest publication protected and missing historical projections replayable from the immutable journal. The checkpoint state serialization limit is **48 MiB**, checked before publication; it is not a new limit on original research material. Survey scope/readiness metadata caching and report-catalog metadata caching each have a **4 MiB serialized-size accounting limit** (32 and 64 entries respectively), not a guarantee that Python resident memory equals that byte count. The renderer inventories its trusted offline TeX cache before copying and admits at most **256 MiB / 8,192 files**; temporary reservation includes that cache plus 256 MiB of working space. These are the implemented limits read from `store.py`, `survey.py`, `report_catalog.py` and `render.py`.

The following measurements keep the source-object count fixed at four: the 347-byte teaching source and three synthetic sources dividing the remaining bytes. Each measured phase runs in a fresh interpreter. No network or paid model call occurs in this matrix.

| Raw sources (MiB) | Phase | Result | Sampled process-tree peak / child RSS high-water (MiB) | Original bytes read (MiB) | Logical / allocated disk growth (MiB) | Seconds |
|---:|---|---|---:|---:|---:|---:|
| 8 | Freeze | SUCCESS | 26.05 / 25.79 | 0 | 0.04 / 0.04 | 0.018 |
| 8 | Input preparation | SUCCESS | 30.47 / 33.10 | 8 | 0 / 0 | 0.014 |
| 8 | Streaming materialization | SUCCESS | 28.17 / 28.11 | 8 | 8 / 8.02 | 0.037 |
| 32 | Freeze | NOT REACHED: input scope over budget | 24.80 / 24.60 | 0 | 0 / 0 | 0.000 |
| 32 | Input preparation | CONTEXT_LIMIT | 24.87 / 24.61 | 0 | 0 / 0 | 0.001 |
| 32 | Streaming helper only | SUCCESS | 27.48 / 27.48 | 32 | 32 / 32.02 | 0.059 |
| 128 | Freeze | NOT REACHED: input scope over budget | 23.02 / 24.53 | 0 | 0 / 0 | 0.000 |
| 128 | Input preparation | CONTEXT_LIMIT | 24.80 / 24.55 | 0 | 0 / 0 | 0.000 |
| 128 | Streaming helper only | SUCCESS | 27.46 / 27.39 | 128 | 128 / 128.02 | 0.158 |

The 32 MiB raw case exceeds the total limit once metadata is included. Both larger input cases reject before any original-material body read. Their successful copying uses an explicitly synthetic frozen manifest to test the native helper separately; neither becomes an accepted model task. Copies have independent inodes, verified frozen hashes and no write bits. Authoritative sources are not hardlinked into writable task directories.

RSS combines 10 ms `/proc` process-tree sampling with the child's kernel high-water counter. Disk measures `st_size` and `st_blocks × 512` separately. Dataset sizes run sequentially and are cleaned up between cases. Test guards apply only to the harness children, not research processes. These finite measurements are not an OOM test, a disk-fill test or an unlimited-size performance guarantee.

Reuse checks additionally observed 100 explicit freeze operations sharing one knowledge manifest, 10 native small-record versions, 50 warmed progress/locale refreshes with no new project files or original-body hashing, and three output profiles sharing a knowledge snapshot. Critical admission still validates original evidence; same-size tampering with restored mtime is detected. Cache deletion cannot grant mathematical authority.

Settled input cleanup requires the original sealed response and intact capture. It removes only rebuildable named task inputs, preserving command, logs, response/capture, source and native research evidence. PREPARED, RESERVED, SENT, UNKNOWN and unsealed states remain protected. Cleanup failure does not undo settlement or resend a paid request. Transient resource failure keeps the original capture available for recovery. Store checkpoint retention and atomic-write failure tests are recorded separately from the measured matrix. Later runner failure/recovery refinements did not change the measured helper/context paths; affected recovery tests were run separately.

## Actual report rendering

The final rendering receipt records actual isolated, offline Tectonic/Poppler execution for `minimal`, `thematic` and `lecture` Survey plans. Each completed one native author, one semantic and one visual role using synthetic captures. The receipt contains 18 native tasks overall, nine report-role tasks, PDF/TeX/page hashes and all-page rendering evidence. There were zero paid model calls and zero network calls.

All three one-page PDFs were rendered to images and inspected for clipping, overlap, legible glyphs, English headings, the Inconclusive boundary and page numbers. Visual packets contained the report body and inspected page, without the full literature corpus. The deterministic body is shared across profiles: this verifies the three selected-plan routes, contract and renderer pipeline, not actual editorial differences, mathematical readiness or a real model's writing quality.

The render receipt binds its measured source before and after execution. Subsequent candidate-2 changes are confined to browser JavaScript/tests and documentation; final reuse must retain the unchanged native renderer dependency comparison. Rendering from source and verification of the installed package are separate receipts.

## Public acquisition smoke

A bounded Crossref request returned one metadata-only candidate, with response bytes retained and hashed. An arXiv search request timed out on two attempts and remains FETCH_FAILED. A separately named, known arXiv PDF was downloaded successfully (889,089 bytes) and converted with `pdftotext -layout`, with distinct original and derivative hashes. It was a transport/extraction check only; it was not asserted to be relevant to the teaching example or independently read mathematically. Crossref metadata does not stand in for full text. No model call was involved.

## Installed package and interface observations

Candidates 2 and 3 were built outside the repository, verified and prepared through the shipped release preparation script, then installed through the shipped local installer in an offline virtual environment. All 71 wheel members and 65 runtime package files matched the packaged/frozen bytes. Source/release archives contain the default English README, complete Chinese README and six bilingual workflow SVGs. The obsolete separate English redirect is absent. Wheel metadata uses the default README.

Candidate 1's two independent builds produced identical bytes for all six release files. Candidates 2 and 3 have their own build/install receipts. Final publication separately requires two byte-identical builds from the clean documentation-bound commit, source ZIP versus the complete committed tree, release/wheel/Debian member verification, and unchanged accepted runtime/native assets. Earlier reproducibility does not supply final artifact hashes. The six release files are the source ZIP, release ZIP, wheel, Debian installer, artifact audit and SHA256SUMS.

The installed service started in a new empty validation workspace. An actual restart replaced only that owned service, reused its workspace and changed its port; the persisted Chinese preference remained byte-identical. Candidate 3 was subsequently installed and restarted on another port with its then-current persisted English preference unchanged. Its focused backup confirmation was actually inspected in English and Chinese: the host-owned title reads “Current native project backup” / “当前原生项目备份”, while the 46-file count and stopped-process state are unchanged.

The supplemented candidate-3 browser evidence receipt has SHA-256 `c6c64228e636a9ecdcccef6ab5c48c1eb798261d22cb0c98c3e5a8039201a53a`. It records **37 actual observation steps covering 35 unique paths out of 46**, with **43 JPEG screenshots and 43 accessibility-tree text captures**. The supplement adds Settings, paused TRW creation, original-material upload and read-only refresh observations, and binds the existing TFDW authorization/frozen-request observations. It makes no new model calls. Earlier observations retain their actual candidate/source identities and screenshots; documented dependency-equivalence and narrow UI-diff records explain their reuse. The report does not relabel all screenshots as fresh candidate-3 executions.

Representative English/Chinese observations include a paused zero-call Survey, draft/selection preservation across locale change, readable selected Survey evidence, all three workflow graphs and 29 stages, a single thematic output plan, existing TRW/TFDW views, exact-candidate handoff to a paused TRW, report/open-duty separation, capture recovery and UNKNOWN views, native-format backup inspection and restoration to a new paused project. This is the agreed representative coverage, not the Cartesian product of every workflow, state, locale and browser.

| Browser group | Candidate-3 evidence result | Remaining observation scope |
|---|---|---|
| WEB02, WEB04, WEB05, WEB07 | PASS | All registered paths for these groups have recorded observations. |
| WEB01 | Browser scope complete; CUA row remains SKIP | Its six browser paths are observed. Desktop install/launch and the native path picker are covered separately by direct human report, not CUA. |
| WEB03 | Partial / SKIP | Closing the browser and reopening the workspace. Native original-capture admission, pause and UNKNOWN behavior are recorded separately. |
| WEB06 | Partial / SKIP | Future model-policy configuration, exhausted-budget rejection, cross-origin/CSRF/authentication rejection, idempotent POST replay and frozen-task preservation. Exact-instance switching and read-only refresh without dispatch were observed. |

The CUA channel retains **11 unobserved registered paths: two native desktop paths and nine browser paths**. It remains 35/46; its native SKIPs are not converted to CUA successes. The separate human acceptance below supplies the two native paths, giving **37 distinct observed paths across both channels and nine unobserved browser paths**. These are the two WEB03 paths and seven WEB06 paths listed above. The accepted representative scope leaves them explicitly unobserved. Automated native/API checks do not silently replace missing interface observations. **The strict all-path gate remains incomplete (`strict_complete=false`).**

The human user confirmed installing the specified candidate-3 4.1.0 Debian package and opening the application successfully. They also confirmed that the Tectonic chooser opens and cancels normally and that English/Chinese PMRS prompts are correct. These are **PASS by direct human report** for `desktop-install-launch` and `path-picker`, separately recorded at 2026-10-08 04:56:07 UTC. No native screenshot or CUA action is fabricated. The private acceptance receipt has SHA-256 `0eacabc6a3914e90f0b7ea27fca0cac00583ad6000fe9012175fddecf7bddd8a` and binds the candidate commit, Debian-package hash and runtime-package hash.

Reuse for the final documentation-only build requires a recorded comparison proving that only `TEST-REPORT-4.1.0.md` changed and that native launch/install scripts and all runtime assets remain byte-identical. This comparison is an enforced final artifact check. No repeat installation or human question is needed when it succeeds. The older 3.4 installer/menu/Tectonic-chooser record remains historical lineage and is not relabelled as 4.1 evidence.

## Published-baseline release binding and reproduction

For the published baseline, the release procedure enforced the documentation-only change boundary against the human-accepted installation candidate, verified all 65 runtime files and native installer/launcher resources, and checked both deterministic artifact sets. It verified the pushed main commit, annotated v4.1.0 tag, formal Release and six uploaded asset hashes while preserving v4.0.0. Those identities belong to the baseline. A later local candidate has its own build metadata and targeted acceptance; the historic 65-file comparison is not a current runtime equivalence claim. Artifact integrity does not manufacture a missing browser observation or scientific qualification.

```bash
python3 -B scripts/validate-groups.py --required-core --out ../validation/core
python3 -B scripts/validate-groups.py --out ../validation/strict --browser-evidence ../validation/browser-evidence.json
SOURCE_DATE_EPOCH=315532800 python3 -B scripts/build-release.py --out ../artifacts-a
SOURCE_DATE_EPOCH=315532800 python3 -B scripts/build-release.py --out ../artifacts-b
```

The strict command requires actual observations for every registered path and is expected to remain incomplete with the representative evidence described above. Its requirements and CI workflow were not weakened to obtain a PASS. The [published v4.1.0 scope](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/v4.1.0/ACCEPTANCE-SCOPE-4.1.0.md) preserves that release's applicable behavior and observation boundaries; the [current scope](ACCEPTANCE-SCOPE-4.2.0.md) is separate. Other platforms, paid-model research, scientific truth and old-project migration were not validated.
