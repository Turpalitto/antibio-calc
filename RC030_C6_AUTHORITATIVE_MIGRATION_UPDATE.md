# RC-030 C6 — Authoritative Range Migration Proposal Update

Supersedes/extends `RC030_AUTHORITATIVE_RANGE_MIGRATION_PROPOSAL.md` (C3) with C6's span-linked re-derivation results.

**AUTHORITATIVE MIGRATION NOT AUTHORIZED. NOT EXECUTED. NO AUTHORITATIVE SQLITE MODIFIED IN THIS TURN.**

## V3 safe-link count

0 `SAFE_EXACT_LINK`, 0 `SAFE_TABLE_LINK` from the 179-record SUSPECT set processed this turn (see `RC030_C6_V2_V3_COMPARISON_REPORT.md`). Combined with the 186 `TRUSTWORTHY` records from the original V2 pass (C3, not re-examined this turn — those already had scalar-lower-bound agreement, a weaker but non-zero signal), the current best-available migration candidate pool for the *entire* 365-row range-candidate set remains: **0 rows verified via span-linked attribution to `SAFE_EXACT_LINK`/`SAFE_TABLE_LINK` standard.** The 186 `TRUSTWORTHY` rows have not been run through this turn's stricter engine and should not be assumed migration-ready without doing so.

## V3 ambiguous count

46 of 179 (`AMBIGUOUS_ALTERNATIVE_BOUNDARY` 23, `AMBIGUOUS_TABLE_CONTEXT` 12, `AMBIGUOUS_MULTIPLE_DRUGS` 10, `AMBIGUOUS_LOADING_MAINTENANCE` 1) — owner-review-required, not migration candidates.

## Exact changed-field allowlist (unchanged from C3 proposal)

`dose_min, dose_max, dose_is_range, dose_range_raw, dose_source_start, dose_source_end, dose_range_confidence, range_provenance` — additive columns only. `dose` (scalar) and every clinical field stay byte-identical. **Zero rows currently qualify for population under this turn's stricter standard.**

## Expected authoritative changed rows

**0**, given the current result set. Should the 186 `TRUSTWORTHY` rows later be re-verified via span-linked attribution and some subset reach `SAFE_EXACT_LINK`/`SAFE_TABLE_LINK`, that subset (bounded by 186) would become the candidate pool for a future migration turn — not this one.

## Rollback strategy (unchanged)

Snapshot authoritative DBs (sha256 recorded) before any future migration; additive columns allow `DROP COLUMN`/table-rebuild or snapshot restore.

## Pre-migration backups

Would be required before any future execution; none created or needed this turn (nothing executed).

## Provenance checks

Each `SAFE_EXACT_LINK`/`SAFE_TABLE_LINK` candidate carries `source_offset_start`/`source_offset_end`/`result_hash` for exact re-derivation verification — none currently populated with a non-null selected range, since no record reached a SAFE classification.

## Post-migration diff requirements (unchanged)

Only additive columns non-null-diff; 0 clinical-field changes; row count identical; sha256 of every clinical column unchanged.

## Owner-review requirements

Every `AMBIGUOUS_*` result requires owner adjudication via the C5 interface (or a future C6-specific queue variant) before any status change. `RC030_C6_OWNER_REVIEW_QUEUE.json` (23 items) is the current compact review queue.

## Clinical governance requirements (unchanged)

Even for a hypothetical future `SAFE_EXACT_LINK` row, `TYPES_MEETING_PRECISION_THRESHOLD` stays governed and empty; physician review is still required before any range participates in a real recommendation.

## Adapter compatibility

Unchanged from C3 — `CanonicalRegimenProviderAdapter` remains validation-only, the live Clinical Engine pipeline remains wired to the legacy `SQLiteReader`, not `assembled_regimens`.

## Schema version

`range_v2` (unchanged).

## Migration script design (updated)

1. Snapshot authoritative DBs (sha256 recorded) into a timestamped backup.
2. `ALTER TABLE ADD COLUMN` for the 8 additive fields (nullable).
3. Populate **only** from rows independently reaching `SAFE_EXACT_LINK` or `SAFE_TABLE_LINK` under the span-linked attribution engine (`dose_verification_sandbox/span_attribution.py`), never from the naive first-range heuristic.
4. Verify: only additive columns non-null-diff; 0 clinical-field changes; row count identical; sha256 of every clinical column unchanged.

## Stop conditions

- Any `SAFE_EXACT_LINK`/`SAFE_TABLE_LINK` candidate pool smaller than an owner-set minimum sample size — stop, do not migrate a handful of rows in isolation.
- Any candidate whose `result_hash` cannot be independently re-derived from the current `assembled_regimens.sqlite` content — stop.
- Any candidate overlapping a maximum-dose or loading/maintenance marker — excluded by construction, but re-verify at migration time regardless.

## Current status

**AUTHORITATIVE MIGRATION NOT AUTHORIZED.** Given 0 qualifying rows from this turn's 179-record re-derivation, there is currently nothing eligible to propose for migration. The 186 `TRUSTWORTHY` rows remain the only nominally-stronger signal in the corpus and have **not** been re-verified under this turn's stricter standard — doing so is the natural next step before any future migration proposal, not something this turn performed (scope was the 179 SUSPECT records per owner authorization).
