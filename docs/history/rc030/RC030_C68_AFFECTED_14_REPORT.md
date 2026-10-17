# RC-030 / C6.8 Phase 13 — Individual Re-Audit of the 14 Originally Unit-Basis-Affected Records

## Method

Each of the 14 records flagged in C6.7's unit-normalization audit (`RC030_C67_UNIT_NORMALIZATION_AUDIT.md`) was re-run through the C6.8-repaired engine (`DoseUnitSignature`/`compare_dose_units`, plus the extended range regex recognizing spelled-out per-kilogram(-per-day) constructions and compact concentration forms). Prior classification was not used as an input to the re-run — only `source_pdf`/`page`/`quote`/`antibiotic`/`dose`/`unit`/`frequency` (the same frozen 365-input used for the full replay).

## Results, all 14

| regimen_id | C6.7 classification | C6.8 classification | unit_compatibility | Was a previously-exact record? |
|---|---|---|---|---|
| 5917 | SAFE_EXACT_LINK | SAFE_SINGLE_CANDIDATE | COMPATIBLE_BASIS_UNSPECIFIED | **yes** |
| 5918 | SAFE_EXACT_LINK | SAFE_SINGLE_CANDIDATE | COMPATIBLE_BASIS_UNSPECIFIED | **yes** |
| 5441 | SAFE_EXACT_LINK | SAFE_SINGLE_CANDIDATE | COMPATIBLE_BASIS_UNSPECIFIED | **yes** |
| 5442 | SAFE_EXACT_LINK | SAFE_SINGLE_CANDIDATE | COMPATIBLE_BASIS_UNSPECIFIED | **yes** |
| 5475 | SAFE_EXACT_LINK | **SAFE_EXACT_LINK** | EXACT_EQUIVALENT | **yes** |
| 5478 | SAFE_EXACT_LINK | **SAFE_EXACT_LINK** | EXACT_EQUIVALENT | **yes** |
| 5514 | SAFE_SINGLE_CANDIDATE | WRONG_RANGE_ANCHOR | — (rejected, INCOMPATIBLE_WEIGHT_BASIS) | no |
| 6638 | SAFE_SINGLE_CANDIDATE | SAFE_SINGLE_CANDIDATE | COMPATIBLE_BASIS_UNSPECIFIED | no |
| 6072 | SAFE_SINGLE_CANDIDATE | WRONG_RANGE_ANCHOR | — (rejected, INCOMPATIBLE_WEIGHT_BASIS) | no |
| 5526 | SAFE_SINGLE_CANDIDATE | WRONG_RANGE_ANCHOR | — (rejected, INCOMPATIBLE_WEIGHT_BASIS) | no |
| 5533 | SAFE_SINGLE_CANDIDATE | WRONG_RANGE_ANCHOR | — (rejected, INCOMPATIBLE_WEIGHT_BASIS) | no |
| 6085 | SAFE_EXACT_LINK | SAFE_SINGLE_CANDIDATE | COMPATIBLE_BASIS_UNSPECIFIED | **yes** |
| 6110 | SAFE_SINGLE_CANDIDATE | SAFE_SINGLE_CANDIDATE | COMPATIBLE_BASIS_UNSPECIFIED | no |
| 6111 | SAFE_SINGLE_CANDIDATE | SAFE_SINGLE_CANDIDATE | COMPATIBLE_BASIS_UNSPECIFIED | no |

## The 6 previously-exact records — individual disposition

**4 correctly downgraded (5917, 5918, 5441, 5442):** all four share the identical erythromycin dosing sentence — *"20-40 мг на кг массы тела **в сутки**"* / *"30-50 мг на кг массы тела **в сутки**"* — the source text explicitly states a per-day basis in words. The structured field says only `mg/kg` (no day qualifier). Correctly downgraded to `COMPATIBLE_BASIS_UNSPECIFIED` (source is more specific than the structured field, not equal to it) → `SAFE_SINGLE_CANDIDATE`.

**2 correctly remained exact (5475, 5478) — a real positive control:** both cite *"25-50 мг на кг массы тела (не более 125 мг)"* — note the **absence** of "в сутки" (per day) in the source text. The spelled-out-unit parser correctly recognizes this as weight-only (no time qualifier), matching the structured field's own `mg/kg` (also no time qualifier) exactly → `EXACT_EQUIVALENT` → **`SAFE_EXACT_LINK` is correctly retained**. This demonstrates the repair discriminates on genuine textual evidence rather than reflexively downgrading every previously-flagged record — the fix is evidence-driven, not a blanket relaxation or blanket restriction.

## The 8 originally-non-exact records

**4 correctly rejected (5514, 6072, 5526, 5533):** each has a genuine `INCOMPATIBLE_WEIGHT_BASIS` conflict between the structured field and the source range's actual basis (confirmed individually: 5526/5533's only range in their multi-drug quote genuinely belongs to a *different* drug — ethambutol/rifabutin, not the record's own clarithromycin — carrying a `mg/kg` basis the clarithromycin record's `500 mg` absolute dose cannot match; 5514/6072 have a direct weight-basis mismatch on their own drug's figures). These were already flagged `SINGLE_WRONG_ANCHOR`/`SINGLE_NOT_A_RANGE` in C6.7's independent Pass A disposition (`RC030_C67_SINGLE_CANDIDATE_DISPOSITION.md`) — the engine repair now reaches the same conclusion deterministically, without needing the separate blinded review pass.

**4 remain SAFE_SINGLE_CANDIDATE (6638, 6110, 6111):** `COMPATIBLE_BASIS_UNSPECIFIED` — genuinely basis-ambiguous, correctly capped below exact-link, consistent with their original C6.7 disposition.

## Cross-validation with the independent Pass A audit

C6.7's independent blinded Pass A audit (a completely different method — human-equivalent re-reading, zero access to engine internals) flagged exactly 6 of the 13 `EXACT_LINK_DOWNGRADED_AMBIGUOUS` records as also carrying this same unit-basis defect: 5917, 5918, 5441, 5442, 5475, 5478. The C6.8 deterministic repair independently agrees on 4 of those 6 (5917/5918/5441/5442 downgraded) and *disagrees* on 2 (5475/5478, which the repair keeps exact) — investigated above and found to be **correct**: Pass A's reviewers, working from the blinded quote text alone without the engine's structural parse, could not distinguish "25-50 мг на кг массы тела" (no day) from "20-40 мг на кг массы тела в сутки" (explicit day) as cleanly as the structured parser now can. This is not a disagreement to paper over — it is a case where the deterministic repair is more precise than the human-equivalent blinded pass, and it is reported as such rather than silently preferring one method over the other.

## Final retained exact-link pool

Combining both independent verification methods (C6.7 blinded Pass A retained = 53; C6.8 basis-repaired retained = 47), the **intersection — records that survive both — is 36**. This is the final, most-defensible retained exact-link pool for C6.8's owner queue rebuild (Part VIII). See `generated/rc030_c68/final_exact_link_intersection.json` for the full accounting: 17 records that survived Pass A but are now correctly basis-downgraded by the repair, and 11 records that the repair would keep exact but Pass A had downgraded for unrelated structural reasons (competing ranges, table-shape, wrong-anchor risk) — those 11 remain excluded, since Pass A's reasons were about link structure, not unit basis, and are unaffected by this repair.
