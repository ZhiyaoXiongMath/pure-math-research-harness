# KB and Summary MVP

`pmrh.application.kb_summary.KnowledgeSummary` is the single shared adapter used by
`pmrh-kb` and `pmrh-summary`. It starts no model, KB Agent or review agent.

## Current support

The installed persistence assembly is **synthetic-only**. An authenticated real
host adapter supplying current project/principal permissions, the installed
storage permit capability and a genuinely sealed native extraction request is
not available. The adapter rejects non-synthetic projects; neither skill may
manufacture those bindings. This is a completed **synthetic engineering loop**,
not a production-user MVP or a real model/research acceptance.

Inputs are nonempty UTF-8 `.txt`, `.md` and `.tex` originals, up to 1 MiB.
TeX is read as source; includes/macros are not executed. PDF/OCR and translation
are outside this MVP. Output is one Markdown document with English headings and
the admitted record bodies. The persisted result must fit the existing evidence
DTO bound (1 MiB); split larger tasks by actual requested scope.

## Shared calls

The trusted host injects the existing same-root `Store`, `UnitOfWork`, permit
issuer, version-expectation builder, current per-reference access check and the
existing `changes`/`knowledge_access` service modules into
`KnowledgeSummary`. These are local capabilities, never JSON supplied by an
input document. The teaching fixture is the only assembly shipped in this PR.

1. KB can call `register(raw, material_id=..., name=..., origin=...)`, followed
   by `read(source_ref, ranges=[(start, end), ...])`. Ranges are half-open UTF-8
   byte offsets. Registration preserves bytes and import names/origins; it does
   not assert reading. `read` returns the actual text and exact locators.
2. Either skill calls `prepare(raw, material_id=..., name=..., origin=...,
   request=..., ranges=...)`. Summary does not need a prior KB invocation.
   `REUSED` returns the original result reference; `NEEDS_CAPTURE` returns an
   immutable plan, selected text, changed line ranges and exact reusable records.
3. When extraction is necessary, the host supplies ONE existing frozen native
   task and seals its original response through its supported capture path.
   Its immutable input packet binds `kb_summary_plan_ref` to the exact plan
   reference, and contains the requested passages; a task for another question
   cannot be relabeled as this Summary task.
   The adapter itself never allocates or sends a model request. Use native KCS
   objects and `SOURCE_PROVENANCE`/`USED_SOURCE` links with exact SourceUse
   locators. Native source delivery, live guards and admission still apply.
4. Call `complete(plan_ref, original_request_id)`. Only Context, Statement,
   Argument, Example and SourceEvidence are accepted by this extraction adapter;
   it cannot create an Assessment. Native objects remain authoritative. Markdown
   is a deterministic presentation of the same admitted bodies and locators,
   so no second writing call is required. Use `export(result_ref)` to obtain the
   Markdown for the user's chosen output file.
5. End this request. Do not launch TRH/FDH or claim independent proof.

Source versions use exact content identities. A rename adds an import name but
reuses the source and result. New bytes preserve the old version, compare exact
lines and retain unchanged objects only when their native dependencies also
remain reusable. Affected objects are listed for recheck; no proof support is
globally withdrawn. Historical outputs stay pinned to their original sources.
When a new version changes only bytes outside the explicitly selected passages,
the existing output is returned with its old pinned version and the new material
registration; no extraction call is needed.
Current permissions, source status and relevant support state are checked again
before reuse/export. No hidden source body or index is returned through a cached
Summary.

## Storage and uncertainty

Original registration uses existing original-input admission; mathematics uses
existing native capture admission; plans/import names/output manifests are
observation evidence committed by the existing UoW into the SAME Journal/HEAD.
No second database or mathematical record format is created. These are separate
transactions, not a claim of cross-service atomicity.

After a native-write interruption, inspect the original request/capture and call
`complete` on that same request only. After `SUMMARY_COMMIT_UNCERTAIN`, use the
reported `kb-summary:...` operation ID with `recover` to inspect its durable
receipt. Reopen and inspect the saved result before any continuation. A missing
receipt or missing capture does not authorize new inference or an automatic
resubmission. The adapter starts no retry. Current control-profile activation
and production storage remain unsupported; the existing protections are intact.

Historical `SURVEY`, `pmrs.survey/1`, instances and events continue through their
unchanged readers. This adapter does not drive S0–S7 or formal report completion.

## Teaching example

From the repository root, with Python 3.11+ and no extra dependencies:

```sh
python3 -B -m tests.skills.test_kb_summary --example ../kb-summary-example
python3 -B -m unittest tests.skills.test_kb_summary -v
```

Use a new output directory each time. The example writes both versions of the
geometric-sum material, `summary-v1.md`, `summary-v2.md`, a small synthetic receipt
and a synthetic project. First delivery preserves integer `N >= 1`, real `q != 1`,
the sum from `k=0` to `N-1`, the subtraction proof and numerical example. Repeating
returns `REUSED`; version 2 adds two native objects for the `q=1` branch and reuses
five. The test also covers renamed input, changed conditions and dependent
objects, forbidden material/cached receipts, missing UNKNOWN capture, selected
ranges and interruptions after durable native/output HEAD. ALL outputs and host
captures in this example are fixed synthetic fixtures, not actual model calls.
