**Recommendation: REQUEST_CHANGES — two MAJOR findings.** This is the independent DEV-PR-03 general review, not MAIN acceptance or a GitHub approval.

| Review identity | Value |
|---|---|
| PR | [#6](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/6) |
| HEAD | `32bfced663e50cd69f418b21ed9af5f2faef0502` |
| Tree | `8f6f6686576c8e45c92ff9c7de37df950b49b6a6` |
| Base | `507ea4baca2782ab0da13ab949bc4424fc707694` |
| Model / effort | `gpt-6-astra / xhigh`, controller-verified |
| Role | Independent general Reviewer; no delegation |

**Isolation and method**

The first shell operation polled the configuration gate and received `VERIFIED`. The second shell operation made exactly one authorized canary append attempt. It failed with **errno 30, `EROFS`**. Before, after, and final canary SHA-256 were identical:

`eec8fe2623e7f2173410d699c47c8eb2c9553499c9fdd4ebae33c37ca2b49b81`

No source or evidence files changed. Final Git status was clean.

I reviewed all 25 changed paths, affected runtime consumers, tests, CI changes, applicable governance/ADRs, acceptance requirements, and the explicit Store exception. Own execution comprised read-only Git, hash, archive, AST, log-identity checks, and one standard-library Unicode encoding check. **Product tests and filesystem fixture reproductions were NOT_EXECUTED locally** under this read-only profile.

GitHub observations below come from **supplied offline records**, not live network verification by this reviewer. Those records show PR #6 open and unmerged, with `main` at the stated base. `PROJECT-STATE.md` retains its older `e1cb2dd…` baseline and pre-authorization DEV03 status; current explicit user authorization governs this review.

**REV03-GEN-01 — MAJOR: raw admission state disappears when typed mapping is unavailable**

Locations: `research_studio/readonly_query.py:179`, `research_studio/readonly_query.py:181`; contributing projection at `research_studio/views.py:151`.

The query promises to preserve original legacy values when `StateAxes` cannot represent them. However, the request projection includes only `request_id`, `execution_state`, `capture_ref`, `usage`, and `fenced`. The new query adds the typed mapping but never restores raw `acceptance_state`.

For a normal settled request, `_state_axes()` returns `None` because `SETTLED` is absent from `ExecutionState`. Consequently, its admission outcome disappears. Requests settled as `REJECTED_CONTRACT` and `REJECTED_STALE` become indistinguishable in the returned request fields; aggregate acceptance counts cannot recover that information.

This is a source-proven omission, not a hypothesized future adapter problem. Existing execution code produces these states. `test_unrepresentable_legacy_states_are_not_invented` misses the defect because it removes `acceptance_state` before checking the result.

**Bounded reproduction:** publish a synthetic request with `execution_state="SETTLED"` and `acceptance_state="REJECTED_CONTRACT"`, query status, then repeat with `REJECTED_STALE`. Both return null `state_axes` without the original admission value.

**Requested correction:** preserve raw per-request `acceptance_state` independently of typed mapping, with explicit absence handling. Add regressions for settled accepted/rejected outcomes and absent admission data. Keep `SETTLED` unmapped; do not invent termination semantics.

Filesystem reproduction: **NOT_EXECUTED here**; suitable for the Controller’s existing synthetic fixture environment.

**REV03-GEN-02 — MAJOR: malformed pool Unicode escapes validation and can break JSON status output**

Locations: `research_studio/host_pool.py:152`, `research_studio/host_pool.py:170`; final-output boundary at `research_studio/readonly_query.py:186`, `research_studio/readonly_query.py:196`, and `pmrh/cli.py:36`.

Pool `valid_text()` checks only string type and length. JSON containing an escaped unpaired surrogate therefore passes validation. A slot’s `start` value, for example, can contain `"\ud800"` and still reach the returned pool projection with `available=True`.

The project projection receives a canonical UTF-8 serialization check, but the pool is appended **after** that check. The CLI then serializes with `ensure_ascii=False` and prints the result. On normal UTF-8 output, the surrogate raises an uncaught `UnicodeEncodeError`, preventing even a healthy project’s status from being returned as valid JSON.

I independently confirmed the relevant standard-library behavior: the escaped surrogate parses, satisfies the implemented text predicate, and fails UTF-8 encoding. The full CLI fixture reproduction remains **NOT_EXECUTED**, so this is source analysis plus an executed language-level check—not a claimed product test run.

**Bounded reproduction:** in an otherwise valid synthetic pool ledger, replace one slot’s `start` with the JSON escape `"\ud800"`; invoke the status CLI for a valid synthetic project using UTF-8 stdout.

**Requested correction:** validate the pool projection’s Unicode/serialization inside its error boundary, before marking it available. Return an explicit pool-unavailable reason and null counts while retaining readable project output. Add an actual CLI regression with malformed pool Unicode and a valid-Unicode positive case.

**Verified evidence**

- All **349 manifest-listed files** matched their SHA-256 values at both initial and final checks.
- Manifest SHA-256: `c549a319a9bb5e272e60f50745980d8297a651f821735744a3c20761dcb5d538`.
- `input/diff.patch` exactly matched the local base-to-head diff; SHA-256: `f319eee811d4fc2e49a72fad942750a1f76eab73a449c81dd241bb89250bd932`.
- Independently reconstructed Git tree identity matched the nominated tree. All **292 tracked files**, including executable modes, matched supplied GitHub blob records.
- All five artifact ZIP digests matched supplied GitHub artifact metadata. CRCs and extracted-member bytes matched; all four source archives matched the frozen source.
- Regenerated AST results matched every supplied graph: **183 Python files, 1,228 direct edges, 7,447 transitive edges**, with no reported architecture violations, parse failures, or inventory discrepancies.
- Historical baseline and exact six-path legacy allowance checked successfully. Non-exempt AST sections and the original reconciliation body were unchanged.

The supplied execution receipts were checked against source-derived individual test identities, not just totals:

| Suite | Run / job | Python | Successful IDs | Artifact |
|---|---|---:|---:|---:|
| DEV03 | [38499509835 / 115642861601](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38499509835/job/115642861601) | 3.11.17 | 33 | 11864549625 |
| DEV03 | [38499509835 / 115642861768](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38499509835/job/115642861768) | 3.13.16 | 33 | 11865002331 |
| DEV02 | [38499509825 / 115642861830](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38499509825/job/115642861830) | 3.11.17 | 119 | 11865176963 |
| DEV02 | [38499509825 / 115642861595](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38499509825/job/115642861595) | 3.13.16 | 119 | 11865087164 |
| DEV01 | [38499510010 / 115642862693](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38499510010/job/115642862693) | 3.12.3 | 48 | 11865466409 |
| Phase 0 | [38499509857 / 115642861692](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38499509857/job/115642861692) | Supplied job | 6 | None |

Verified ZIP SHA-256 identities:

```text
11864549625  9e9ea34ea9d3873c63aef8495893f4a09e42b7936fe32d93990a6d9d4a6f1916
11865002331  6cc01dd7f2788e589d2d7aa83bf19063f2e9d042123a48712d41db78312b20d9
11865176963  a5b540a1a1cc3e7e45180bb8a4ac868a514871e65a0e6d8a3faf39296c1887aa
11865087164  96cc0979bdf34afde9b41c59d0e4f3a7abe058b31989c6685e7aee97efa4a150
11865466409  9084f7f56b1036a37193d46f3fdc0b7a6ce24694ba136510c3991de5b0e80d12
```

DEV02/DEV03 have exact-head source archives. DEV01’s supplied AST fingerprints match the frozen Python sources. Phase 0’s raw log records temporary PR merge `35f5d83a1833868200c007014b932320d4346fec`; its merge object is unavailable in the packet checkout, so I do not independently certify that temporary commit’s entire tree. This is a bounded evidence limitation, not an additional blocking finding.

**Coverage and retained limits**

The implementation stays within the authorized Store read-plumbing exception. It reuses original digest verification, checkpoint binding, and replay; no duplicate Store, writer/reducer/schema change, or new runtime adapter was found. Relevant query consumers use pure pool observation, while the mutating compatibility alias remains explicit.

Supplied CI meaningfully covers absent/existing projects, footprints excluding OS atime, permission failures, corrupt inputs, parent swaps, concurrent HEAD publication, paging, explicit as-of reads, PAUSED/UNKNOWN preservation, independent pool observation, and workspace MAIN/communication snapshot consistency. Those successes do not cover the two findings above.

The original parent-swap failure remains preserved in `input/original-probe*`: **two tests, one failure** on the baseline primitive. It is not relabelled PASS. The new confined query has separate passing regression receipts; unchanged legacy I/O does not inherit its confinement guarantee.

Accepted DEV02 evidence is reused only for unchanged Ports/DTOs, contract tests, and runner behavior. Their relevant paths were unchanged from accepted HEAD `bdc698873999d3fc1773e76588339276ddc581ca`. **REV02-HELPER-01 remains an accepted nonblocking MINOR, INCONCLUSIVE / NOT_EXECUTED**, and was not used as a sole integrity gate.

Real research, model/provider/native execution, production recovery, browser/PDF gates, full legacy suites, migrations, hostile-process certification, and remaining future acceptance work remain **NOT_EXECUTED**. Usage remains **NOT_MEASURED / NOT_INSTRUMENTED**, not measured zero. No software result confers mathematical proof or scientific qualification.

The two MAJOR findings block approval of this frozen head. Both admit narrow fixes and targeted regression tests within DEV03; they do not require future-package implementation or a repeated full DEV02 audit.