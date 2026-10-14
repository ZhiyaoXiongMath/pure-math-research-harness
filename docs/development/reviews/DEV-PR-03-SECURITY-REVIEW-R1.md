**Recommendation: REQUEST_CHANGES.** One MAJOR state-preservation defect and one MINOR malformed-input defect remain. This is an independent security review recommendation, not MAIN acceptance or GitHub approval.

| Review identity | Value |
|---|---|
| PR | https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/6 |
| HEAD | `32bfced663e50cd69f418b21ed9af5f2faef0502` |
| Tree | `8f6f6686576c8e45c92ff9c7de37df950b49b6a6` |
| Base | `507ea4baca2782ab0da13ab949bc4424fc707694` |
| Model / effort | `gpt-6-astra` / `ultra`, controller-verified |

The first shell operation polled the configuration gate and proceeded only after `VERIFIED`. The second shell operation made exactly one authorized canary append attempt. It failed with **errno 30 (`EROFS`)**. Before, after, and final SHA-256 were all:

`c5bd6996390c495edc01710a47044ced30e2561b5fef7251d37e45c31bd96d22`

No source or evidence files were modified. No delegation, network/app access, research-project access, credential access, remote approval, or merge occurred.

**REV03-SEC-01 — MAJOR: unmappable requests lose their original admission state**

Locations: `research_studio/readonly_query.py:179`, `research_studio/views.py:151`; relevant mapping at `research_studio/readonly_query.py:147`.

The request projection includes `execution_state` but omits `acceptance_state`. `_state_axes()` returns `None` whenever any legacy axis lacks an exact enum mapping. In particular, `SETTLED` is absent from `ExecutionState`, so every normally settled request loses its per-request admission outcome in the new status response.

This affects ordinary stored states: `research_studio/execution.py:364` records `SETTLED` together with `ACCEPTED`, `REJECTED_STALE`, `REJECTED_CONTRACT`, or `EXACT_DUPLICATE`.

Concrete reproduction for a Controller-owned synthetic fixture:

1. Publish two requests with `execution_state="SETTLED"`, one `REJECTED_CONTRACT` and one `EXACT_DUPLICATE`.
2. Query the instance.
3. Both request rows have `state_axes=null`, without their original admission states. The aggregate accepted count cannot recover those distinctions.

This contradicts the explicit requirement to preserve raw states when typed mapping is unavailable. It loses admission provenance in the user-facing query; stored evidence and retry state remain unchanged.

**Requested correction:** retain each request’s original `acceptance_state` independently of `state_axes`, preserving absence explicitly. Keep unsupported typed mappings unavailable. Add regressions covering the ordinary settled dispositions and `NOT_SUBMITTED`.

The current regression at `tests/devpr03/test_queries.py:304` removes `acceptance_state` before testing the fallback, so it cannot detect this loss. **Established by source inspection; end-to-end reproduction NOT_EXECUTED in this read-only review.**

**REV03-SEC-02 — MINOR: malformed pool Unicode can break the entire JSON command**

Locations: `research_studio/host_pool.py:152`, `research_studio/host_pool.py:170`, `research_studio/readonly_query.py:196`, `pmrh/cli.py:36`.

Pool text validation checks type and length but permits lone Unicode surrogates. The project projection receives canonical UTF-8 validation; the subsequently attached pool projection does not.

A minimal synthetic ledger illustrating the gap is:

```json
{"cursor":0,"slots":{},"demands":{"\ud800":{"demand":1}},"projects":{}}
```

The current pool validation accepts this demand key, and `_view()` carries it into the response. `json.dumps(..., ensure_ascii=False)` accepts the string, but writing it to UTF-8 stdout with `strict` or `surrogateescape` error handling raises `UnicodeEncodeError`. A malformed independent pool can therefore prevent a readable project from producing its structured status.

**Requested correction:** validate pool output text/UTF-8 inside its error boundary before marking it available. Return an unavailable pool with null counts while preserving the project result. Add a regression that exercises UTF-8 output, since `StringIO` alone will not expose this failure.

**Established by source inspection and an independently executed standard-library encoding check. Product-level reproduction NOT_EXECUTED.** Impact is bounded command availability; no write or authorization bypass was demonstrated.

The remaining reviewed security boundaries were supported within the stated scope:

- Directory traversal uses relative directory descriptors and `O_NOFOLLOW`; file reads reject nonregular and multiply linked files. Descriptors close through the inspected success and exception paths.
- The supplied final tests exercise swaps before and after directory opening. The original legacy counterexample remains **one PASS / one FAIL at the base**, not a current successful probe or a repaired universal legacy primitive.
- The new status path avoids report-file traversal, reconciliation, process inspection, native synchronization, and registered-project traversal.
- MAIN receives the selected snapshot. Digest/checkpoint validation and existing replay remain in Store; no duplicate replay implementation was introduced.
- Pool observation retains UNKNOWN reservations and stale rows. The reconciliation body and other writer sections remain unchanged.
- Runtime/backend observation remains `UNOBSERVED`; no inspected query path resumes PAUSED, retries UNKNOWN, or grants scientific qualification.
- CI exceptions name six legacy paths and four direct compatibility edges. Existing transitive checks remain active, with negative tests for additional consumers, imports, and writer-section changes.

**Independent evidence verification performed here**

All **349 manifest entries** matched both initially and at completion. All **292 tracked files** matched HEAD by blob and mode. I independently reconstructed the Git tree and commit hashes, compared the supplied GitHub blob/mode inventory, and verified that `input/diff.patch` exactly matches the local base-to-head diff.

All five supplied ZIPs matched their supplied GitHub artifact digests, passed CRC checks, and matched their extracted files. All four source archives contained the same 292 files and modes as the frozen source.

Key packet identities:

| Evidence | SHA-256 |
|---|---|
| `manifest.json` | `c549a319a9bb5e272e60f50745980d8297a651f821735744a3c20761dcb5d538` |
| `input/diff.patch` | `f319eee811d4fc2e49a72fad942750a1f76eab73a449c81dd241bb89250bd932` |
| Each supplied `source.tar.gz` | `252910a722d52e84a452fb2abea834579d3808f372be8376be6480f84508824d` |
| `input/original-probe.py` | `3076858d1a480b8f72f325f35d7a66a416695b7fa4cb7241f400f67720cef17e` |

I independently compared raw test identities against AST inventories, including individual outcomes, duplicates, missing records, terminal results, receipt hashes, and recorded source fingerprints. Counts alone were not used.

| Supplied execution evidence | Job | Artifact | Verified result |
|---|---:|---:|---|
| [DEV03 run 38499509835](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38499509835), Python 3.11.17 | 115642861601 | 11864549625 | 33/33 |
| Same run, Python 3.13.16 | 115642861768 | 11865002331 | 33/33 |
| [DEV02 run 38499509825](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38499509825), Python 3.11.17 | 115642861830 | 11865176963 | 119/119 |
| Same run, Python 3.13.16 | 115642861595 | 11865087164 | 119/119 |
| [DEV01 run 38499510010](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38499510010), Python 3.12.3 | 115642862693 | 11865466409 | 48/48 |
| [Phase 0 run 38499509857](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38499509857) | 115642861692 | None | Six named tests passed in raw job log |

My own read-only architecture scan matched all five supplied graphs: 183 Python files, 1,228 direct edges, 7,447 transitive edges, no parse failures or architecture violations. The legacy scope check confirmed the fixed historical baseline, exact changed-path allowance, unchanged non-query sections, and unchanged reconciliation body.

**These GitHub observations were supplied offline. I performed no live network verification.** The supplied PR record is open and unmerged. The supplied `main` is `507ea4b…`, whereas `PROJECT-STATE.md` records the earlier `e1cb2dd…` snapshot. Current explicit authorization and `input/store-read-exception.json` govern this review.

Phase 0’s log identifies temporary merge commit `35f5d83a1833868200c007014b932320d4346fec`. Its commit/tree object was not supplied, so that job is not claimed as independently authenticated exact-tree execution. This is a bounded evidence limitation; DEV03 and DEV02 source archives authenticate the critical changed source directly.

Accepted DEV02 evidence remains applicable to unchanged `pmrh/ports` and `tests/devpr02`, which I verified unchanged from accepted HEAD `bdc698873999d3fc1773e76588339276ddc581ca`. **REV02-HELPER-01 remains INCONCLUSIVE / NOT_EXECUTED**, under its previously accepted nonblocking limitation. Neither those helpers nor `controller-ci-verification.json` served as the sole integrity authority here.

Local product suites, fixture-producing probes, real models/providers/native execution, browser/PDF services, hostile-native isolation, scientific qualification, and the complete future acceptance matrix remain **NOT_EXECUTED**. CI guards are Python preventive controls, not OS isolation. Supported query invocation requires bytecode writes disabled; OS-maintained atime is excluded from footprint guarantees. Model-call counts remain unmeasured, not measured zero.

The execution limitations are bounded for this source-and-receipt review. **REV03-SEC-01 blocks approval of this frozen HEAD; REV03-SEC-02 is a bounded MINOR.** No broader Store, Runner, schema, or legacy-audit expansion is requested.