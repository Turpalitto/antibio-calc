# RC-030 Authoritative Range Migration — Proposal (NOT executed)

Design only. No authoritative SQLite artifact is mutated in this task.

## Scope
- Target: `normalized_regimens.sqlite` and `assembled_regimens.sqlite`.
- Schema version: `range_v2` — additive columns `dose_min, dose_max, dose_is_range, dose_range_raw, dose_source_start, dose_source_end, dose_range_confidence, range_provenance`.
- Expected changed rows: ~186 (trustworthy, scalar==lower-bound) of 365 range-candidates; the 179 SUSPECT rows must first be re-derived with span-linked anchoring (not the naive first-range heuristic) before inclusion.
- Changed-field allowlist: the 8 additive columns only. `dose` (scalar) and every clinical field stay byte-identical.

## Migration script design
1. Snapshot authoritative DBs (sha256 recorded) into a timestamped backup.
2. `ALTER TABLE ADD COLUMN` for the 8 additive fields (nullable).
3. Populate from a span-linked re-derivation (anchor range to the dose token, reusing the sandbox `range_collapsed_upstream` logic), NOT the naive manifest.
4. Verify: only additive columns non-null-diff; 0 clinical-field changes; row count identical; sha256 of every clinical column unchanged.

## Rollback
- Restore from the pre-migration snapshot (columns are additive, so `DROP COLUMN`/table-rebuild or snapshot restore both work).

## Gates
- Owner approval required (authoritative DB write).
- Canonical assembly rebuild + adapter review (assembled consumers).
- Clinical Engine impact review: even with dose_max present, no row becomes calculation-eligible — `TYPES_MEETING_PRECISION_THRESHOLD` stays governed and empty.
- Physician review still required before any range participates in a real recommendation.

**This migration is not part of commits C1/C2/C3 and is not executed here.**