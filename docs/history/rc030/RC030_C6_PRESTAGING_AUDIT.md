# RC-030 C6 — Prestaging Audit (Phase 25)

All scans run for real against the exact allowlist in `RC030_C6_EXACT_ALLOWLIST.md`.

## Secret / API key / token scan
**Result: 0 matches.**

## Personal-path / absolute-path scan
Pattern `C:\<dir>\`. **Result: 0 matches** in any committed file. (The `C:\clinrec_downloader` environmental-constraint discussion in `RC030_C6_BASELINE.md`/`RC030_C6_ARCHITECTURE_AUDIT.md` refers to it as a *path name string*, not an embedded personal path with a username — same treatment as the C3/C5 precedent of preserving factual governance content.)

## Username scan (`TURPAL`)
**Result: 0 matches.**

## Raw-clinical-data scan
Checked `RC030_C6_OWNER_REVIEW_QUEUE.json` and `RC030_C6_V2_V3_COMPARISON.json` field-by-field: queue items contain only `regimen_id`, `regimen_version`, `classification`, and governance-status flags — no `source_quote`, no `antibiotic`, no `dose`, no offsets. Comparison file contains only aggregate counts. **Result: clean.**

## Source-quote density scan
**0 source quotes** in any committed file — the full per-record results (including source offsets and quote-derived spans) live only in the excluded `generated/rc030_range_rebuild_v3/rederivation_manifest.json`.

## SQLite / PDF / model / cache scan
**Result: 0 matches** — no binary committed; the code and docs reference `assembled_regimens.sqlite` by *name* only (necessary content for describing what the engine reads), never a binary file itself.

## Large-file scan
Largest committed file: `dose_verification_sandbox/span_attribution.py` at 17,709 bytes. All files are small text.

## Generated-artifact scan
Confirmed `generated/rc030_range_rebuild_v3/rederivation_manifest.json` (123 KB) and its local duplicate comparison JSON are **not** in the allowlist and were not staged.

## Network-code scan
Pattern `fetch(|XMLHttpRequest|WebSocket|socket\.|requests\.`. **Result: 0 matches in `span_attribution.py`.** One match in the test file — a **documented false positive**: the test's own I/O-marker list (`("sqlite3.connect", "open(", "requests.", "socket.", "clinical_engine")`) contains these strings as scan targets for `test_module_has_no_io_or_network_or_clinical_engine_imports`, not as executed calls.

## DB-write scan
Pattern `sqlite3\.connect|INSERT INTO|UPDATE .* SET|DELETE FROM` against `span_attribution.py`. **Result: 0 matches** — the module performs no database I/O of any kind (read or write); all 179-record processing was done via a one-off, non-committed script that opened `assembled_regimens.sqlite` read-only.

## Clinical Engine import scan
**Result: 0 matches in `span_attribution.py`.** One match in the test file — same documented false positive as the network-code scan (the literal string `"clinical_engine"` appears only inside the test's own marker-list tuple).

## Calculation-activation scan
Checked for any write to `calculation_eligibility`/`approved_by`/any DB `UPDATE`. **Result: 0 matches** — every output record explicitly sets `calculation_eligibility: BLOCKED`, `clinically_approved: false`, `authoritative_migration_allowed: false` as static values, never computed to be otherwise.

## Threshold-modification scan
`TYPES_MEETING_PRECISION_THRESHOLD` does not appear anywhere in `span_attribution.py`. **Result: 0 matches**, and regression-tested (`test_threshold_untouched_by_import_or_use`).

## Approval-state scan
**Result: 0 matches** — no code path sets `approved_by` or any approval field.

## Event-store leakage scan
No AI event fields (`review_origin`, `ai_proposed_verdict`, etc.) and no owner-event fields (`event_id`, `reviewer_id`, `canonical_verdict`) appear in any C6 file — this turn produces classification results, not review events.

## Summary

Two false positives fully explained (both are the test file's own scan-pattern string literals, not executed network/DB/Clinical-Engine code). No secrets, no personal paths, no raw clinical data, no SQLite/PDF, no generated artifact, no network code, no DB write, no calculation/threshold/approval mutation. Allowlist is clear to stage.
