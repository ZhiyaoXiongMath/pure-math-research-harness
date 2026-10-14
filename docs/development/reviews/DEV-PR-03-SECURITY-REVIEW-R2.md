**Recommendation: APPROVE** for the targeted DEV03 R2 security follow-up. Both original findings are **CLOSED**. No new findings or scope drift were identified. This recommendation is not MAIN acceptance or GitHub approval.

| Review identity | Value |
|---|---|
| HEAD | `c4ea8bc93b2018f30f04a5c5df7d1a8b1a653525` |
| Tree | `7a079828c351af4dce6f645da6e5d53a44c75010` |
| Parent reviewed in R1 | `32bfced663e50cd69f418b21ed9af5f2faef0502` |
| Model / effort | `gpt-6-astra` / `ultra`, controller-verified |
| Iteration | R2, following directed remediation round 1 of 2 |

**Isolation and method**

This turn’s first shell operation obtained `VERIFIED` from the new configuration gate. The second operation made exactly one authorized canary append attempt; it failed with **errno 30 (`EROFS`)**. Before, after, and final SHA-256 all matched:

`ee90a077e3066362814a39ce76bfa1549fc7948f0271f080e1cadeb2d466a3b8`

The earlier configuration-blocked attempt remains `NOT_EXECUTED`; it supplied no review results.

I reviewed `input/MAIN-R1-DISPOSITION.txt`, the actual patch, affected runtime boundaries, new tests, and raw execution evidence. Git confirms exactly four changed paths:

- `research_studio/readonly_query.py`
- `research_studio/host_pool.py`
- `tests/devpr03/test_queries.py`
- `docs/development/DEV-PR-03-CONTRACT.md`

Identity-unchanged R1 evidence is reused for confinement, Store replay, PAUSED/UNKNOWN preservation, reconciliation, architecture exceptions, and inherited contracts. No full DEV02 or legacy re-audit was performed.

**REV03-SEC-01 — CLOSED**  
R1 severity: MAJOR; maps to MAIN-03-01.

At `research_studio/readonly_query.py:181`, each request now retains its original `acceptance_state` independently of typed mapping. Missing data produces null plus `acceptance_state_unavailable_reason="NOT_RECORDED"`. Unsupported mappings remain null; `SETTLED` is not reinterpreted as termination or scientific qualification.

The new regression verifies per-request attribution across `ACCEPTED`, `REJECTED_STALE`, `REJECTED_CONTRACT`, `EXACT_DUPLICATE`, `NOT_SUBMITTED`, and absence, while preserving execution state and fixture footprint.

The supplied Controller CLI outputs independently show the raw dispositions and explicit absence marker. Its `NOT_SUBMITTED` probe uses `SETTLED`; the ordinary **`PREPARED` / `NOT_SUBMITTED`** pairing is covered by the new CI regression. This distinction does not leave the finding open.

**REV03-SEC-02 — CLOSED**  
R1 severity: MINOR; MAIN-03-02 required closure for MVP availability.

At `research_studio/host_pool.py:170`, the pool projection is constructed and canonical UTF-8 validation completes **before** counts or availability are published. Unicode failures become `INVALID_POOL_DATA`; the initial null counts remain intact.

The new tests exercise high and low lone surrogates in a field value and demand key through the actual CLI print path using strict UTF-8 encoding. They verify readable project JSON, unavailable pool/null counts, preserved source digest, PAUSED/UNKNOWN, and unchanged fixture footprint. Valid Unicode keys and values have a positive regression.

The Controller’s actual CLI subprocess outputs likewise show safe rejection for malformed field/key cases and successful valid-Unicode output. No traceback or loss of the readable project response remains in those supplied executions.

**Source and execution evidence**

My own executed checks were read-only hash, Git-object, archive, AST-inventory, and raw-result comparisons—not product-test executions.

- All **377 manifest entries** matched initially and finally.
- All **292 tracked files** matched the frozen source by blob and mode.
- Independently reconstructed commit and tree hashes match the review identity.
- `input/diff-from-r1.patch` exactly matches the Git parent-to-head diff.
- All five CI ZIPs match their supplied GitHub digests and extracted bytes, with valid CRCs.
- All four source archives match the complete frozen file/mode inventory.
- Individual test identities, outcomes, terminal results, receipt hashes, and recorded source fingerprints match; no missing or duplicate test records were found.

| Supplied CI | Job | Artifact | Verified result |
|---|---:|---:|---|
| [DEV03 run 38502114213](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38502114213), Python 3.11.17 | 115651255653 | 11866406934 | 36/36 |
| Same run, Python 3.13.16 | 115651255833 | 11866073337 | 36/36 |
| [DEV02 run 38502114198](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38502114198), Python 3.11.17 | 115651255547 | 11866247348 | 119/119 |
| Same run, Python 3.13.16 | 115651255736 | 11865528650 | 119/119 |
| [DEV01 run 38502114175](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38502114175) | 115651255396 | 11866411891 | 48/48 |
| [Phase 0 run 38502114254](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38502114254) | 115651255735 | None | Six named tests passed |

All three new `test_R1_*` methods appear with successful individual records on both DEV03 Python versions.

I inspected `input/controller-probes/probe.py`, its sandbox command receipt, results, and all nine stdout/stderr pairs. Their hashes agree; all nine results record exit 0, valid JSON, empty stderr, and unchanged fixture footprints. These are **Controller execution evidence**, not my own measured executions. The script launches the CLI with the frozen source as its working directory and explicit `PYTHONPATH`, with strict UTF-8 output and bytecode disabled.

Key evidence identities:

| File | SHA-256 |
|---|---|
| `manifest.json` | `c21c6946ed17a17eecd091ca2675dc1df521dabe434293c775b38d708e5fd20b` |
| `input/diff-from-r1.patch` | `5296d94c2bedf2ebd33af11388ca1cac9551e59ea50b6d45fc2fd32f918bf02a` |
| Each supplied `source.tar.gz` | `6a326ab133640f9e54012e6f1479ec68afd62ae53457c2f62c0f54c3fc4c9e99` |
| `input/controller-probes/probe.py` | `6fc13071c3f9427f64852229cf688841bac2aadeb3c27f118b1286cd9c276679` |
| `input/controller-probes/results.json` | `6a0deb7be9fd0d0dd1b2cad408f8a7c520b8f00cf2051844b15a572c37aa194a` |

**Offline provenance and retained limits**

All GitHub observations were supplied offline; **no live queries were performed**. The supplied PR record remains open, unmerged, with no auto-merge.

`input/prior-phase0-merge-proof.json` closes R1’s bounded tree-evidence gap: temporary merge `35f5d83…` has the R1 tree and expected parents. The current Phase 0 log identifies temporary merge `6378ea468987aff13a6e939d4441869dce49a7c4`; its supplied commit object has the current reviewed tree and expected base/head parents. Neither temporary merge establishes a merge into `main`.

Local product suites and fixture-producing probes remain **NOT_EXECUTED by this reviewer**. Real research/model/provider/native execution, scientific qualification, hostile-native isolation, and the full future acceptance matrix remain outside this review. Supported invocation still requires `-B` or `PYTHONDONTWRITEBYTECODE`; OS atime is excluded; project and pool observations are not atomic; Python guards are not OS-isolation proof. Model usage is not measured zero.

**REV02-HELPER-01 remains INCONCLUSIVE / NOT_EXECUTED**, under its previously accepted nonblocking limitation, and was not used as a sole integrity authority. R1 failures remain historical failures; this report closes their defects only for the named new HEAD.

These limitations are bounded and do not block this targeted approval. No source/evidence writes, delegation, network/app access, credential access, research-project access, remote approval, or merge occurred.