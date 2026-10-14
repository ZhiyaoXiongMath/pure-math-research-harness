**Recommendation: APPROVE.** Both original general-review findings are **CLOSED** at the frozen R2 head. No new findings or scope drift were identified. This recommendation is not MAIN acceptance, GitHub approval, or merge authorization.

| Identity | Reviewed value |
|---|---|
| HEAD | `c4ea8bc93b2018f30f04a5c5df7d1a8b1a653525` |
| Tree | `7a079828c351af4dce6f645da6e5d53a44c75010` |
| Parent / R1 HEAD | `32bfced663e50cd69f418b21ed9af5f2faef0502` |
| Model / effort | `gpt-6-astra / xhigh`, controller-verified |
| Iteration | R2 review following remediation round 1; 1/2 rounds used |
| PR | [#6](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/6), open/unmerged in supplied offline observations |

**Isolation and targeted scope**

This attempt’s first shell operation received `VERIFIED` from `general/go.json`. Its second shell operation made exactly one canary append attempt, which failed with **errno 30, `EROFS`**. Before, after, and final SHA-256 matched:

`21ab77b3347c4576ca4cca52145f859ee737ee93b8fae5c314532ec1be71d204`

The earlier R2 configuration timeout remains recorded; it involved no source review or canary attempt.

I reviewed `input/MAIN-R1-DISPOSITION.txt`, the actual four-file delta, new regression methods, relevant raw CI artifacts, and Controller probe evidence. R1 review remains applicable to identity-unchanged code; I did not repeat the full DEV02 or legacy audit.

Only `readonly_query.status()` and `host_pool.read_status()` changed in runtime code. Existing test methods were unchanged; three tests and one UTF-8 output helper were added. Documentation changes describe those fixes.

**REV03-GEN-01 / MAIN-03-01 — CLOSED**

At `research_studio/readonly_query.py:181`, each request now exposes raw `acceptance_state` independently of `StateAxes`. Missing data produces null plus `acceptance_state_unavailable_reason="NOT_RECORDED"`; present values retain their original meaning. The existing mapping remains unchanged: `SETTLED` is not converted into process termination or scientific qualification.

`tests/devpr03/test_queries.py:313` checks:

- `SETTLED` with `ACCEPTED`, `REJECTED_STALE`, `REJECTED_CONTRACT`, and `EXACT_DUPLICATE`;
- ordinary `PREPARED` / `NOT_SUBMITTED`;
- absent admission data;
- multiple request identities, unchanged execution states, PAUSED, and unchanged fixture footprint.

Both Python CI executions contain the successful test identity. The six supplied Controller admission CLI outputs independently preserve the expected raw values or explicit absence. The Controller’s `NOT_SUBMITTED` case uses `SETTLED`; coverage of the ordinary `PREPARED` combination comes from the CI regression, not that Controller case.

**REV03-GEN-02 / MAIN-03-02 — CLOSED**

At `research_studio/host_pool.py:170`, the pool projection is now constructed separately and passed through canonical UTF-8 serialization **before** any counts are published. Unicode encoding failures are caught through `ValueError` and mapped to `INVALID_POOL_DATA`. The initial unavailable result retains null counts, while project output remains available.

The new tests at `tests/devpr03/test_queries.py:359` and `:388` exercise high and low unpaired surrogates in both slot values and demand keys, plus valid Unicode keys and values. They use the real CLI print path through a strict UTF-8 `TextIOWrapper`, checking valid output bytes, null unavailable counts, source digest, preserved PAUSED/UNKNOWN, and unchanged footprints.

The supplied Controller additionally ran actual CLI subprocesses with `PYTHONIOENCODING=utf-8:strict`. I checked their raw outputs and hashes: malformed field/key cases returned valid project JSON with unavailable pools; the valid-Unicode case retained its value. All nine Controller cases exited 0 with empty stderr.

The bounded reproduction evidence is sufficient to close both findings. No further execution or remediation is required for these findings.

**Source and execution evidence**

Own executed checks were read-only Git, AST, hash, archive, metadata, and raw-output checks. Product test execution below is **supplied CI or Controller evidence**, not execution by this reviewer.

- All **377 manifest-listed immutable files** matched initially and finally; Git remained clean.
- The patch exactly matched the parent-to-head diff. SHA-256: `5296d94c2bedf2ebd33af11388ca1cac9551e59ea50b6d45fc2fd32f918bf02a`.
- Manifest SHA-256: `c21c6946ed17a17eecd091ca2675dc1df521dabe434293c775b38d708e5fd20b`.
- All **292 source blobs and modes** matched supplied GitHub records; independently reconstructed tree identity matched the reviewed tree.
- Five artifact ZIPs matched supplied GitHub digests, CRCs, and extracted bytes. Four embedded source archives matched the frozen source.
- Raw successful test identities matched source inventories, including all three new regression methods. Receipt hashes, source fingerprints, and job steps were consistent.

| Suite | Run / job | Python | Successful IDs | Artifact |
|---|---|---:|---:|---:|
| DEV03 | [38502114213 / 115651255653](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38502114213/job/115651255653) | 3.11.17 | 36 | 11866406934 |
| DEV03 | [38502114213 / 115651255833](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38502114213/job/115651255833) | 3.13.16 | 36 | 11866073337 |
| DEV02 | [38502114198 / 115651255547](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38502114198/job/115651255547) | 3.11.17 | 119 | 11866247348 |
| DEV02 | [38502114198 / 115651255736](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38502114198/job/115651255736) | 3.13.16 | 119 | 11865528650 |
| DEV01 | [38502114175 / 115651255396](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38502114175/job/115651255396) | 3.12.3 | 48 | 11866411891 |
| Phase 0 | [38502114254 / 115651255735](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38502114254/job/115651255735) | Supplied job | 6 | None |

DEV03 ZIP SHA-256 identities:

```text
11866406934  8dcd1b33b9ef2cb25b9731b78049687c1b7198da07248a19f10d68833f0efd9a
11866073337  e39a17508867b97a69665377e0be3e5311ac17536e0f6cb7de1a5e0d4cb31417
```

Controller evidence is in `input/controller-probes/`. I inspected its script and sandbox command receipt, verified script SHA-256 `6fc13071c3f9427f64852229cf688841bac2aadeb3c27f118b1286cd9c276679`, and checked all nine stdout/stderr pairs against `results.json`. Footprint equality remains a supplied harness execution result; I did not recreate its fixtures.

**Phase 0 evidence gap resolved**

Using `input/prior-phase0-merge-proof.json` and `input/github/phase0-tested-merge-commit.json`, I reconstructed both commit hashes and checked their parents and trees:

- Prior temporary merge `35f5d83…` has the R1 tree.
- Current temporary merge `6378ea4…`, named in the raw Phase 0 log, has the R2 tree.

This closes the previously bounded merge-object evidence gap. These are PR test merges, not actual merges of PR #6.

**Retained limits**

All GitHub observations were supplied offline; I made no live queries. Own product tests remain **NOT_EXECUTED** under the read-only profile. No files were modified, reports written to disk, remote approvals posted, or delegation performed.

The documented invocation requires `-B` or `PYTHONDONTWRITEBYTECODE`; footprint comparisons exclude OS atime; project and pool observations are not atomic; Python guards are not OS isolation proof. Real model/native/provider execution, scientific qualification, full legacy acceptance, and future-package work remain outside this review. Model usage is unmeasured, not verified zero.

Inherited **REV02-HELPER-01 remains INCONCLUSIVE / NOT_EXECUTED**, an accepted nonblocking MINOR that was not used as sole integrity authority. Prior failed findings and probe history remain historical evidence; their closure here applies only to the frozen R2 implementation and verified coverage.