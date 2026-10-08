# Actual installed-browser evidence — PMRS 4.2.0

The runner accepts `--browser-evidence /absolute/private-validation/browser.json`. This is an input for actual observations already performed through CUA in the installed candidate. It does not drive a browser and cannot convert HTTP/unit tests into browser observations. Never label an unperformed step PASS. A historical screenshot or source hash remains historical. An unchanged behavior may be reused only through a separately recorded dependency comparison; that comparison is not a newly performed browser action. Private specification-checker counts do not replace actual observations.

Freeze the code, tests, mappings and resources before browser acceptance. `source_sha256` is SHA-256 of `coverage_registry.encoded(coverage_registry.source_manifest(root))`. Every installed `research_studio/**` file must match that source. Files referenced by the evidence must be below its private directory, with exact sizes and hashes; absolute references, parent traversal and symbolic links are rejected. Root release documentation can later record outcomes without changing the tested source manifest. Final package binding separately verifies all runtime files, metadata and commit identity.

## Record shape

Use schema `pmrs.browser-evidence/1`, mode `CUA_INSTALLED_BROWSER`, and fields `source_sha256`, `environment`, `installed_assets` and `actual_test_results`. Environment reports actual OS, Python, installed runtime and browser identity; if the browser API does not expose a version, say so rather than inventing it.

Each installed asset maps its source-relative name to a private relative `path`, SHA-256 and byte count. Each actual test row has `outcome`, `executed_paths`, `steps` and `artifacts`. A step includes its registered path, the action actually performed, what was observed and hash-bound artifact references. Test IDs and required paths are defined by `tests/coverage/required.json`. Missing or failed observations are never turned into PASS through test counts or a previous release's receipt.

## Native desktop boundary

WEB01 separates browser-observable paths from `native_manual_paths`: `desktop-install-launch` and `path-picker`. Without actual current-version native GUI observations, retain SKIP for that manual scope and list the actions as unverified. A command-line installation, generated menu entry or CUA browser launch is not a native desktop click. Earlier human observations retain their original version and method. Reuse for byte-identical, unaffected behavior must be explicit; changed menu labels or native surfaces are not silently counted as newly observed 4.2.0 clicks.

The strict complete gate preserves missing manual checks. The separately named required-core gate reports current native results and automated installed observations independently, with `core_complete`, `automated_installed_complete` and `native_click_unverified`. Release authorization does not convert a missing observation into PASS or relabel a partial strict gate. The actual 4.2.0 evidence and any reused observation must retain their separately recorded scopes.

## Current backup case and removed requirements

WEB05 uses current native backup/restore only: `native-backup`, `select-native-archive`, `check-native-backup`, `restore-new-paused-project`, and `inspect-restored-records-and-capture`. Use generated mathematical examples and preserve original bytes, capture identity, paused restore behavior and no automatic dispatch. Unsupported format refusal is a current safety property. Old upgrade/reader/continuation and real-project migration cases remain retired; the self-contained [current scope](../../ACCEPTANCE-SCOPE-4.2.0.md) retains the applicable native checks.

The old private specification evidence input is removed. Current documentation, resource inventory, mappings and build consistency are checked by the current test suite. All original observations and failed attempts remain in private validation storage outside the product. Source, browser and package records must identify their actual build and execution. The historical v4.1.0 46-path registry and its partial observations remain historical; finite 4.2.0 checks are not a repeat of that entire campaign. No validation record authorizes paid research.

Survey and localization observations additionally identify the selected instance, S-stage, locale, source/knowledge revisions and actual operations. Capture English and Chinese SURVEY, all-workflow overview, and both existing workflows in both locales. Synthetic activity outputs are marked as software test evidence; actual provider fetches and page rendering retain their own receipts.
