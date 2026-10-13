# DEV-PR-02 — Formal Development MAIN acceptance (archived)

**Decision:** `MAIN ACCEPTED` — **2026-10-13**, for the bounded DEV-PR-02 Ports/DTO/error-contract work package.  
**Decision provenance:** previously issued in `PMRH Development — MAIN | DEV-PR-02` after receiving the independent R3 report. This document archives that separate management decision; it is **not** a native GitHub PR Review or a claim of new post-merge testing.  
**GitHub product PR:** [#4](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/4), `GITHUB MERGED`.  
**Accepted development HEAD:** `bdc698873999d3fc1773e76588339276ddc581ca`.  
**Accepted Git tree:** `9dc07cf45cb02ba31e047f266380be85717a64f2`.  
**Observed merge commit:** `e1cb2dd76d9b5f8651750d6bd89d0b44819b6515`.  
**Independent review:** [R3 original report](reviews/DEV-PR-02-INDEPENDENT-RE-REVIEW-R3.md), verdict `APPROVE_FOR_MAIN_ACCEPTANCE`, report SHA-256 `272d4bab9bf5a62e003ed7cc1ca349f21716db1ae9c509db06097969caf82e88`.

## Scope and reasons

The accepted deliverable is **eight Port contracts, 60 versioned immutable DTOs, 19 explicit error codes, capability/usage separation, synthetic Fake contract tests and bounded offline CI**. No real Codex/Provider/Store/auth adapter was introduced or switched on; the old `research_studio/` runtime, original research identities and existing CLI behavior remain unchanged.

An initial independent review at `dd044d09acaae7ddc250e9f96cd0ba4e940bf467` returned `REQUEST_CHANGES` with four MAJOR and two MINOR findings. A targeted single-parent remediation commit `bdc698873999d3fc1773e76588339276ddc581ca` changed eleven paths. The independent R3 reviewer reviewed this exact delta, reproduced the relevant red/green counterexamples and the certified source/CI evidence, and reported:

| Finding | Independent R3 status | MAIN disposition |
|---|---|---|
| REV02-WIRE-01 | CLOSED | ACCEPTED |
| REV02-EVENT-01 | CLOSED | ACCEPTED |
| REV02-UNKNOWN-01 | CLOSED | ACCEPTED |
| REV02-CI-01 | CLOSED | ACCEPTED |
| REV02-DOC-01 | CLOSED | ACCEPTED |
| REV02-HELPER-01 | INCONCLUSIVE / independent execution NOT_EXECUTED | **Non-blocking MINOR risk explicitly accepted, not marked PASS** |

**REV02-HELPER-01 risk limits:** the two external handoff helper implementations were not included in the material available to R3; the reviewer's normal/`python -O` execution was `NOT_EXECUTED`. Developer-recorded 28/28 tests are not independent evidence. These helpers must **not** serve as a sole authoritative integrity, security or merge gate. GitHub commit/tree identities, authentic Actions artifacts and independent reviewer checks provide the accepted evidence instead. The original local deliverer/developer retains responsibility for providing the missing helper source/support files; if either helper is later promoted into a trusted workflow, undertake **only targeted helper verification**, not a full PR-02 re-audit.

## Actual execution and identity evidence

| Gate | Frozen source | Actual record |
|---|---|---|
| DEV-PR-02 Python 3.11 | `bdc698873999d3fc1773e76588339276ddc581ca` | [Run 38367753519, job 115196874290](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38367753519/job/115196874290), 119/119 PASS |
| DEV-PR-02 Python 3.13 | same | [Run 38367753519, job 115196874368](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38367753519/job/115196874368), 119/119 PASS |
| DEV-PR-01 synthetic regression | same test-source tree | [Run 38367753326](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38367753326), 48/48 PASS |
| Phase 0 smoke regression | same test-source tree | [Run 38367753356](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38367753356), 6/6 PASS |

The two inherited workflows checked out a PR test-merge commit whose tree equals `9dc07cf45cb02ba31e047f266380be85717a64f2`; that **does not** mean it is the actual merge of PR #4. The *actual* merge commit `e1cb2dd76d9b5f8651750d6bd89d0b44819b6515` has parents `efd2be4e93ca8f1ee9f6a03fa53df6a1f008c8fb` and `bdc698873999d3fc1773e76588339276ddc581ca`, and its tree equals the accepted tree. **No separate workflow run for the actual merge SHA was found**; no such run is claimed.

Key preserved GitHub artifact identities:

- [Python 3.11 artifact 11797304019](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38367753519/artifacts/11797304019): SHA-256 `e9146b5835fcb70047ca991df80fb45f271c571d8b7cbbbbecb3b402e2642479`.
- [Python 3.13 artifact 11796649547](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38367753519/artifacts/11796649547): SHA-256 `8ec21e5afcfb582d3cfc1820a2563e71d81f42efa6093587f3612087894bb9d8`.
- [DEV-PR-01 artifact 11796719438](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38367753326/artifacts/11796719438): SHA-256 `350d1182c0993426e3099e43d326b31d64139c825f2ab19fe4c38e74720d33b5`.
- Phase 0's corresponding workflow has job logs but no artifact; no fourth archive is invented.

## Limits and rollback

The contract-level A01/A03/A04/B04 portions are `IMPLEMENTED / TESTED / REVIEWED / MAIN ACCEPTED / GITHUB MERGED` for their **defined DEV-PR-02 portions only**. Production authentication, root-turn gating, atomic budgets, journal/blob crash recovery, real provider usage, OS-hostile sandboxing, full legacy product tests, genuine mathematical research, and other unmet 58+46 future cases remain `NOT_EXECUTED`. Model/API usage is `NOT_MEASURED` (`count=null`), not confirmed zero. CI synthetic guards are not an OS sandbox.

If the merged software later needs rollback, open a separately reviewed software revert PR; do not rewrite original Git history, delete scientific records or change research `MAIN/Goal/PAUSED/UNKNOWN` facts.

**Next:** [DEV-PR-02 Handoff](handoffs/DEV-PR-02.md). This acceptance did **not** authorize DEV-PR-03 or implement proposed future acceptance additions.
