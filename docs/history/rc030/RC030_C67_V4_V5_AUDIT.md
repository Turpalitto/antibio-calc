# RC-030 / C6.7 Part IX — V4 Re-Audit and V5 Rebuild

## V4 re-audit (independent, this pass)

`generated/rc030_range_rebuild_v4/assembled_regimens_range_v4.sqlite`, verified directly (not taken on faith from prior reports):

| Check | Result |
|---|---|
| Row count | 2675 — matches authoritative `assembled_regimens.sqlite` exactly |
| Core clinical fields (diagnosis, antibiotic, dose, unit, route, frequency, duration, age_group, pregnancy, renal_adjustment, therapy_line, icd_mkb, status, review_status, approved_by, approved_at, validation_verdict) | **0 mismatches** across all 2675 rows vs. authoritative DB |
| `dose_min` populated | 74 rows — exactly the SAFE_EXACT_LINK count |
| `dose_is_range = 1` | 74 rows |
| `range_provenance` populated | 117 rows — the full 74+43 candidate pool (43 get metadata-only annotation, no dose_min/max, consistent with single-candidate non-migration status) |
| `approved_by` non-empty | 0 |

**V4 integrity confirmed independently.** No unrelated changes, no approval, no eligibility activation.

## V5 rebuild

Per Part V's disposition, only **53 of the 74 SAFE_EXACT_LINK records survive independent audit as `EXACT_LINK_RETAINED`**. `generated/rc030_range_rebuild_v5/assembled_regimens_range_v5.sqlite` was built by copying V4 and clearing the range fields (`dose_min`, `dose_max`, `dose_is_range`, `dose_range_raw`, `dose_source_start`, `dose_source_end`, `dose_range_confidence`) for the 21 non-retained rows, appending an explicit `C6.7_EXCLUDED_AFTER_AUDIT` marker to their `range_provenance`, and appending `C6.7_RETAINED_AFTER_AUDIT` to the 53 retained rows' provenance. **No other field was touched.**

| Metric | V4 | V5 |
|---|---|---|
| Total rows | 2675 | 2675 |
| `dose_min` populated | 74 | 53 |
| `dose_is_range = 1` | 74 | 53 |
| `approved_by` non-empty | 0 | 0 |
| Unrelated (non-range) field changes vs. V4 | — | **0** (independently diffed across all core + evidence columns) |

V5 sha256: `8750dba85e2449b1b09a86433fd6eff11fcfb8213cda518b5447c30c1f898f02`

**Rows removed and exact reason** (21 rows, `dose_min`/etc. cleared): matches Part V's disposition exactly —
- 13 `EXACT_LINK_DOWNGRADED_AMBIGUOUS` (independent Pass A rated single-plausible, not clean; 6 of these cross-validated by the separate unit-basis audit)
- 5 `EXACT_LINK_DOWNGRADED_TABLE_REQUIRED` (independent Pass A identified as flattened table rows the engine's own table flag missed)
- 2 `EXACT_LINK_REJECTED_WRONG_ANCHOR` (independent Pass A found a genuine competing-range or maximum-clause misread)
- 1 `EXACT_LINK_ENGINE_REVIEW_REQUIRED` (6085 — low-severity unit-annotation gap; excluded from V5 out of caution even though Pass A agreed at 0.9 confidence, since the admission standard requires unit match without qualification)

**Required checks:** unrelated changes = 0 ✅. `eligible` remains 0 (V5 is an experimental, non-authoritative copy; no code path reads it into `assembled_regimens.sqlite` or the Clinical Engine) ✅. `approved` remains 0 ✅. Neither V4 nor the authoritative `assembled_regimens.sqlite` was overwritten. **V5 was created** (not the `V5_NOT_CREATED_NO_RETAINED_ROWS` case) since 53 retained rows exist.
