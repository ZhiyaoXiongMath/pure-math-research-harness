# PMRS 4.1.0 validation

Candidate validation is in progress. This file does not yet certify a release. Final executed results, source hashes, installed-browser observations, actual rendering and artifact bindings will be recorded before publication. No paid research calls or existing research workspaces are used.

The target is Ubuntu 26.04. Controlled tasks and synthetic teaching materials validate software behavior only. They are not actual mathematical research, literature coverage or independent scientific review. Packaging integrity and successful compilation are recorded separately from research qualification.

## Native desktop evidence

A traceable earlier user observation confirmed installation at the default location, application-menu launch to an empty workspace, and opening/cancelling the Tectonic file picker. It was recorded against the 3.4.0 candidate. The 4.0.0 report explicitly kept its own native clicks unverified. This release changes versioned menu entries and native locale text; those changed surfaces require targeted final-package confirmation. No prior observation is silently relabelled as a 4.1.0 full acceptance.

## Reproduction

```bash
python3 -B scripts/test-runner.py --out ../validation/suite.json
python3 -B scripts/validate-groups.py --out ../validation/required --browser-evidence ../validation/browser-evidence.json
SOURCE_DATE_EPOCH=315532800 python3 -B scripts/build-release.py --out ../artifacts-a
SOURCE_DATE_EPOCH=315532800 python3 -B scripts/build-release.py --out ../artifacts-b
```

Use actual observation records from the final candidate. The [acceptance scope](ACCEPTANCE-SCOPE-4.1.0.md) defines current requirements and evidence limits; the [Ubuntu guide](UBUNTU-E2E-GUIDE.md) describes the steps. Missing native observations remain unverified and cannot be replaced by CLI installation or a simulated dialog.
