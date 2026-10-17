# P2-1 Conformance-validator — Analysis

**Date:** 2026-07-11 (updated during full execution)
**Status:** Analysis → RFC → Impl → Tests green → Review (original PASS WITH FIXES) → Fixes applied (A: negative MANIFEST_VALIDATION_ERROR test + doc updates) → FROZEN.
**Workflow:** Full per spec: Analysis → RFC (light, additive) → Impl → Tests → Golden (infra tests as proxy) → Review → Freeze → Docs → Audit → Handoff

## Current State (repo inspection)

- **ValidationPolicy** (clinical_engine/models.py): STRICT (PASS only), ALLOW_REVIEW (PASS+REVIEW), DEBUG (all), AUDIT (all, no filters). Used exclusively in:
  - readers/sqlite_reader.py: _VERDICTS_BY_POLICY filter in load_regimens
  - config.py: default STRICT, Profiles.*
  - stages/regimen_load.py: passed to provider
  - engine.py, tests assert counts (1/2/3 for g_cap under STRICT/ALLOW/DEBUG)
- **Bundle conformance** (P0-1 frozen):
  - clinical_engine/manifest.py: validate_manifest (required fields, types, patterns, I10-tolerant ignore unknown), load_manifest (drops unknown).
  - bundle_manifest.schema.json: frozen, enum for bundle_type etc.
  - clinical_engine/bundles/loader.py: load uses load_manifest + validate + _check_compatibility (kernel version, format handler, expiry), _verify_integrity (content_hash).
  - LoadedBundle returned; warnings collected, errors raise BundleLoadError.
- **Current usage of bundles**:
  - config.py: use_bundles flag (default False).
  - tests/test_bundle_loader.py, test_manifest.py: cover load, I10, missing required, hash format, valid manifests (regimen, safety, terminology, score_profile).
  - No general "conformance report" — either pass or hard fail.
- No dedicated conformance module or CI gate that *flags* (non-fatal list of issues) non-conforming bundles/data.
- From DEVELOPMENT_BACKLOG: P2-1 M/Crit, dep P0-1, DoD "non-conforming флагуется; CI".
- From ARCHITECTURE_V3: P12 "Open for extension, closed for modification".
- From clinical-decision-engine-v1.md §10: testing tiers include invariants, but no bundle conformance tier yet.
- src/pipeline has separate "validate" but out of scope (P2 is for clinical_engine eval).

P1-B (diagnosis) and P0 untouched per prior work. All P1 state restored pure. P2-1 is additive extension to Bundle Loader.

## Gaps identified (repo evidence only)

1. Loader/manifest either succeeds or raises — no "report issues" mode for CI (e.g. pre-merge check of new bundle).
2. I10 tolerance is good, but no way to opt-in strict-unknown-fields for production curation checks.
3. No unified ConformanceResult for manifests + potential future resource shape checks per bundle_type.
4. No integration with ValidationPolicy or curation_status enforcement beyond load.
5. Tests cover happy + basic error, missing negative conformance scenarios for CI (e.g. bad curation for prod, mismatched bundle_type, expiry in past).
6. No tool or hook for "conformance check" in eval pipeline (P2 goal).

## Analysis conclusion

Additive only, inside v3 (P12 extension).
Smallest: clinical_engine/conformance.py with:
- ConformanceIssue (code, message, severity=ERROR|WARNING, field)
- ConformanceResult (conformant: bool, issues: tuple)
- ConformanceValidator class with validate_manifest(manifest, strict_unknown=False), validate_loaded(loaded_bundle)
Reuse frozen validate_manifest + loader checks, but collect instead of only raise.
Optional integration in BundleLoader (e.g. collect warnings as issues).
Pure infra, no domain/clinical logic. The frozen Bundle Loader received an RFC-approved additive extension while preserving default behavior and compatibility.
Add tests (positive, negative, I10 strict, curation checks).
Use existing test manifests + golden-like cases in tests for "conformant bundles".
Update loader optionally (behind flag or param, default no behavior change).
Update relevant tests, config if needed (additive).
No Golden clinical routing change (this is assurance infra), but infra "conformance cases" in tests.
CI hook via test or future tool.

Laws: Optimization (improves assurance for clinical data quality), Traceability (issues traceable to field), no violation.

No arch redesign. Additive. Back compat. 

See DEVELOPMENT_BACKLOG for DoD.

**Analysis complete. Ready for RFC.**