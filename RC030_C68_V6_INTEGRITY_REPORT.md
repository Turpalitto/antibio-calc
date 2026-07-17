# RC-030 / C6.8 Part VII — V4/V5 Audit and V6 Rebuild

## V4/V5 audit result

Verified directly: V5 (`generated/rc030_range_rebuild_v5/assembled_regimens_range_v5.sqlite`, built in C6.7 from the 53 independently-Pass-A-retained records) contains **17 rows whose exact-link status the C6.8 basis repair now shows is invalid** — `5727, 5928, 6042, 6073, 6303, 6305, 6990, 7042, 7043, 7497, 7498, 7519, 7520, 7629, 7630, 7644, 7645` — each a genuine `COMPATIBLE_BASIS_UNSPECIFIED` case the pre-C6.8 engine could not detect. Neither 5688 nor 6052 (the two source-quote-defect records fixed in Part IV) had ever held a populated range value in V4/V5 — they were always `SAFE_SINGLE_CANDIDATE`, never exact-link, so their fix doesn't retroactively add anything to V4/V5's range fields.

**V5 is marked `SUPERSEDED_EXPERIMENTAL_ARTIFACT`.** Not deleted — kept on disk as a record of the pre-basis-repair experimental state, per the owner's instruction not to delete non-temporary artifacts.

## V6 rebuild

Built from **the final 36-record intersection** (Part VI: records that survive *both* C6.7's independent blinded Pass A audit *and* C6.8's deterministic basis repair) — `generated/rc030_range_rebuild_v6/assembled_regimens_range_v6.sqlite`, sha256 `7e2c4d8057ba848e3cd4557860d4ea7eb9d353e98d56565fd84e28544575001d`.

| Check | Result |
|---|---|
| Total rows | 2675 (unchanged) |
| `dose_min` populated | 36 |
| `dose_is_range = 1` | 36 |
| `approved_by` non-empty | 0 |
| Unrelated (non-range) field changes vs. V5 | **0**, independently diffed across all core + evidence columns |
| Populated-row set == final retained-intersection set | **True** (exact match, verified programmatically) |
| 5688 / 6052 present in populated set | **False / False** (correctly absent — never exact-link candidates) |

Rows cleared going from V5 to V6 (17): each stamped `range_provenance += ' | C6.8_EXCLUDED_BASIS_REPAIR'`. Rows retained (36): stamped `range_provenance += ' | C6.8_RETAINED_AFTER_BASIS_REPAIR'`. No other field touched.

**V6 remains experimental, non-authoritative, calculation-blocked, not approved** — same as V4/V5, gitignored (`*.sqlite`), never wired into `assembled_regimens.sqlite` or the Clinical Engine.
