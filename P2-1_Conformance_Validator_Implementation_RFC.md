# P2-1 Conformance Validator Implementation RFC (lightweight)

**Date:** 2026-07-11
**Status:** Draft → Accepted → Implemented → PASS WITH REQUIRED FIXES resolved (negative test + doc phrasing) → FROZEN.
**Type:** Eval & Assurance (infra). Dep on P0-1 BundleManifest.
**Principle:** Additive, open for extension (Arch v3 P12). The frozen Bundle Loader received an RFC-approved additive extension while preserving default behavior and compatibility. Provides flag/report for non-conforming bundles/data for CI. Improves assurance without affecting clinical paths.

**From P2-1 Analysis (repo):**
- Current: manifest validate + loader either pass or hard error. No "flag issues" mode.
- ValidationPolicy exists for regimens only.
- Need: conformance result (issues list) usable in CI, strict opt-in for unknown fields/curation.
- DoD per backlog: non-conforming flagged; CI.

Laws: Optimization Rule (assurance improves clinical data quality/safety gate), no clinical behavior change here.

## 1. Problem

Bundles (post P0-1/P0-3) have schema + loader validation, but:
- No way to *collect* issues non-fatally for CI gate on new/updated bundles.
- I10 tolerant by design, but production curation may want strict-unknown check.
- No unified report for manifest + basic checks (curation_status, expiry, bundle_type validity in context).
- Loader raises on bad; tests cover basic but no CI-oriented conformance harness.

Result: hard to catch non-conforming bundles early in eval pipeline (P2 goal).

## 2. Solution (additive only)

Add `clinical_engine/conformance.py`:
- `ConformanceIssue(code, message, severity="ERROR"|"WARNING", field=None)`
- `ConformanceResult(conformant: bool, issues: tuple[ConformanceIssue, ...], bundle_id=None)`
- `ConformanceValidator` (or functions):
  - `validate_manifest(raw_or_typed, *, strict_unknown=False) -> ConformanceResult`
  - `validate_loaded_bundle(loaded: LoadedBundle, ...) -> ConformanceResult`
- Reuses frozen `validate_manifest`, loader compat/integrity checks.
- Collects instead of (only) raise.
- Strict mode: treat unknown fields as ERROR (opt-in, default False for compat).
- Checks: curation_status for "production" intent, expiry, format registered, hash format, etc.
- Pure infra. No domain knowledge, no clinical logic, no reader/stage change.

Integration (additive):
- BundleLoader.load gains optional `check_conformance: bool = False` (default False, no behavior change).
- If True and issues with ERROR, raise or attach to LoadedBundle.warnings + result (backward compat).
- Or separate `validate_conformance` entry.

Tests:
- Extend test_bundle_loader.py or new test_conformance.py: conformant cases (existing manifests), negative (missing required, bad hash, unknown field in strict, expired, bad curation).
- Negative + edge: empty, malformed, I10 unknown tolerated by default.
- Legacy: default paths unchanged (use_bundles=False or loader default no check).
- Determinism: pure, same input same result.
- Invariants preserved.

No change to frozen manifest.py, schema, loader core behavior, ValidationPolicy (separate concern for regimens), models.

## 3. Acceptance Criteria (must pass before Freeze)

- ConformanceResult used in tests to assert issues.
- Existing bundle loads unchanged when check off.
- New tests pass (positive/negative/compat).
- `python -m pytest ... clinical_engine/tests -q` green (relevant).
- Loader optional conformance does not alter public API for default use.
- Traceable issues (code + field).
- The frozen Bundle Loader received an RFC-approved additive extension while preserving default behavior and compatibility.
- Doc in analysis + this RFC + handoff.
- Additive only.

## 4. Non-goals (out of scope for this RFC)

- Full resource schema validation per bundle_type (future P2).
- Integration with src/pipeline validate.
- CI yaml changes (later).
- Clinical Golden changes (this is infra assurance).
- Strict by default (would break I10 expectation).

## 5. Implementation plan (additive)

1. clinical_engine/conformance.py (new, pure)
2. Update bundles/loader.py : optional param + use validator (minimal)
3. tests: add conformance tests, keep legacy green.
4. Update test_manifest.py or loader tests for coverage.
5. Run tests real.
6. If needed, small update to bundles/__init__.py exports.
7. RFC accepted → impl → review (self as independent) → freeze if PASS.

## 6. Risks & Mitigation

- Over-strict: mitigated by default tolerant, opt-in strict.
- Scope creep: stay infra only, no clinical.
- Frozen: enforced by review + grep in impl.

References: P2-1_Conformance_Validator_Analysis.md, DEVELOPMENT_BACKLOG.md, bundles/loader.py, manifest.py, clinical-decision-engine-v1.md §10, ARCHITECTURE_V3 P12.

**Ready for implementation.**