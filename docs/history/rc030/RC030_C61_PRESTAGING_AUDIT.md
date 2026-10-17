# RC-030 C6.1 — Prestaging Audit (Phase 20)

All scans run for real against the exact allowlist in `RC030_C61_EXACT_ALLOWLIST.md`.

## Secret / API key / token scan
**Result: 0 matches.**

## Absolute-path / personal-path scan
Pattern `C:\<dir>\`. **Result: 0 matches.**

## Username scan (`TURPAL`)
**Result: 0 matches.**

## Source-quote density / raw-clinical-data scan
Checked `RC030_C61_OWNER_REVIEW_QUEUE.json` (all 85 items) and `RC030_C61_RANGE_REVALIDATION_SUMMARY.json` field-by-field: queue item keys are exactly `regimen_id, regimen_version, classification, old_trust, owner_review_required, clinically_approved, calculation_eligibility, authoritative_migration_allowed` — no `source_quote`, no `antibiotic`, no dose values, no offsets, no preselected verdict. **Result: clean.**

## SQLite / PDF / model / cache scan
**Result: 0 matches** — no binary committed; `.sqlite`/`.pdf` appear only as prose references to database/file *names* in the docs (necessary content), never as literal committed paths.

## Large-file scan
Largest committed file: `dose_verification_sandbox/span_attribution.py` at 18,328 bytes. All files small text.

## Generated-artifact scan
Confirmed `generated/rc030_c61/pass_a_365.json` and `generated/rc030_c61/range_revalidation_365.json` (full per-record dumps) are **not** in the allowlist and were not staged.

## Owner-event leakage scan
`RC030_C61_OWNER_REVIEW_QUEUE.json` contains no `event_id`, `reviewer_id`, `canonical_verdict`, `ui_action`, or `note` field — it is a review-input bundle (matches the mission's explicit "this is a review-input bundle, not an event store"), not an event export.

## AI-event leakage scan
No `review_origin`, `ai_proposed_verdict`, or any AI-provenance field appears in any C6.1 file.

## DB-write scan
Pattern `sqlite3\.connect|INSERT INTO|UPDATE .* SET|DELETE FROM` against `span_attribution.py`. **Result: 0 matches** — the module still performs no database I/O of any kind (unchanged from C6; only the classification-labeling logic changed).

## Network-code scan
**Result: 0 matches** in `span_attribution.py`.

## Clinical Engine import scan
**Result: 0 matches** in `span_attribution.py`.

## Calculation-activation scan
**Result: 0 matches** — every queue item and summary field explicitly sets `calculation_eligibility: BLOCKED`, `clinically_approved: false`, `authoritative_migration_allowed: false` as static values.

## Threshold-modification scan
`TYPES_MEETING_PRECISION_THRESHOLD` does not appear in `span_attribution.py`. **Result: 0 matches**, regression-tested (`test_threshold_untouched_by_import_or_use`, unchanged from C6).

## Approval-state scan
**Result: 0 matches** — no code path sets `approved_by` or any approval field.

## Summary

No secrets, no personal/absolute paths, no raw clinical data (source quotes/offsets), no SQLite/PDF, no generated artifact, no owner/AI event leakage, no network code, no DB write, no Clinical Engine reference, no calculation/threshold/approval mutation. Allowlist is clear to stage.
