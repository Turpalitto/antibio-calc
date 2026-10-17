# RC-030 C6.5 — Structural Root-Cause Analysis, Unit-Normalization Fix, and V4 Experimental Artifact

## Headline finding: a real, high-impact engine defect

While clustering the 223 `WRONG_RANGE_ANCHOR` records' rejection reasons for root-cause analysis, the diagnostic reason list itself was found to be **unreliable** — see "Diagnostic bug #1" below — and fixing it revealed a second, much more consequential defect: **82% of `WRONG_RANGE_ANCHOR` rejections (182/223) were actually unit-mismatch rejections, not genuine structural ambiguity.**

Root cause: `assembled_regimens.sqlite` stores the structured dose unit in **Latin script** (`mg`, `g`, `mg/kg`), while the source-text range regex only matches **Cyrillic-script** units (`мг`, `г`, `мг/кг`) as they appear in the guideline PDFs. The engine's `_base_unit()` comparison did simple `.lower()` string equality with no script canonicalization — `"mg" == "мг"` is `False` in Python (different Unicode code points) even though they mean the same thing. Every single-drug, structurally-clean, correctly-scalar-matched candidate was therefore being rejected purely on this superficial mismatch.

## Fix

`_base_unit()` now runs the leading unit token (before any `/`) through `medical_normalizer.dictionary.UnitNormalizer.normalize()` — the same **already-governed** dictionary the production parser (`DoseNormalizer`) uses for exactly this purpose (`'мг' → 'mg'`, `'г' → 'g'`, `'мл' → 'ml'`). No new dictionary was created; this reuses existing, already-trusted infrastructure. One line changed in `_base_unit()`, plus the import.

## Diagnostic bug #1 (found first, fixed first)

A separate, purely diagnostic bug was found while investigating: `c.get("boundary") or "phase_conflict" or "unit_mismatch"` always evaluates to the literal string `"phase_conflict"` (Python `or`-chaining returns the first truthy operand, and `"phase_conflict"` is always truthy — the `"unit_mismatch"` branch was unreachable dead code). This never affected the actual classification decisions (those use `comp["boundary"]`/`comp.get("phase_conflict")` directly), only the informational `rejection_reasons` list — but it was actively misleading this exact root-cause analysis until fixed. Both fixes are covered by regression tests.

## Verification (before trusting the unit fix)

- **All 37 existing unit tests pass**, including the adversarial wrong-drug (`test_wrong_drug_first_range_is_never_safe`) and multi-phase (`test_full_365_replay_never_produces_wrong_safe_classification_for_known_adversarial_cases`) regressions.
- **The three known adversarial real records from C6's architecture audit were re-checked directly**: regimen 5584 (multi-phase surgical dosing) → still `WRONG_RANGE_ANCHOR`; regimen 5622 (Vancomycin/Clindamycin wrong-drug-after-"или") → still `WRONG_RANGE_ANCHOR`; regimen 5624 (malformed multi-drug combination) → now more precisely `AMBIGUOUS_MULTIPLE_DRUGS` (was `WRONG_RANGE_ANCHOR`). **All three remain correctly non-SAFE.**
- **5 `SAFE_EXACT_LINK` results were manually inspected against their real `source_quote` text** (regimens 5659, 5671, 5683, 5678, 5727) — every one is a genuine, clean, single-drug, scalar-matched range (e.g. regimen 5671: structured `Амоксициллин 500 mg`, quote `"Амоксициллин ... 500 - 1000 мг 3 раза в сутки"` — an exact, correct, unambiguous link).

## Real 365-record replay result after the unit-normalization fix

| Classification | Before fix | After fix |
|---|---|---|
| `SAFE_EXACT_LINK` | 0 | **74** |
| `SAFE_TABLE_LINK` | 0 | 0 (no PDF table-bbox recovery attempted this turn) |
| `SAFE_SINGLE_CANDIDATE` | 0 | **43** |
| `WRONG_RANGE_ANCHOR` | 223 | 60 |
| `AMBIGUOUS_MULTIPLE_DRUGS` | 3 | 50 |
| `AMBIGUOUS_ALTERNATIVE_BOUNDARY` | 48 | 40 |
| `AMBIGUOUS_MULTIPLE_RANGES` | 0 | 7 |
| `AMBIGUOUS_TABLE_CONTEXT` | 23 | 23 |
| `AMBIGUOUS_LOADING_MAINTENANCE` | 2 | 2 |
| `DICTIONARY_GAP` | 40 | 40 |
| `NOT_A_DOSE_RANGE` | 26 | 26 |
| **Total** | 365 | 365 |

**117 of 365 (32%) now reach a SAFE classification** (74 `SAFE_EXACT_LINK` + 43 `SAFE_SINGLE_CANDIDATE`). `AMBIGUOUS_MULTIPLE_DRUGS` rising from 3 to 50 is expected and correct: previously these candidates were rejected on the (bugged) unit check before the multi-drug-ambiguity logic ever got a chance to evaluate them specifically; now they correctly reach that more precise diagnosis instead of the generic `WRONG_RANGE_ANCHOR` catch-all.

**Every `SAFE_EXACT_LINK`/`SAFE_TABLE_LINK`/`SAFE_SINGLE_CANDIDATE` result still carries `clinically_approved=false`, `calculation_eligibility=BLOCKED`, `authoritative_migration_allowed=false`** — per the mission's explicit requirement, "even SAFE_EXACT_LINK and SAFE_TABLE_LINK remain migration-prohibited in this task." `SAFE_SINGLE_CANDIDATE` remains additionally review-required and is never treated as equivalent to `SAFE_EXACT_LINK`.

## V4 experimental artifact (Phase 20-21)

Since real `SAFE_EXACT_LINK` results now exist, `generated/rc030_range_rebuild_v4/assembled_regimens_range_v4.sqlite` was built: a byte-copy of `assembled_regimens.sqlite` with 8 additive columns (`dose_min, dose_max, dose_is_range, dose_range_raw, dose_source_start, dose_source_end, dose_range_confidence, range_provenance`), populated **only** for the 74 `SAFE_EXACT_LINK` rows (`dose_min`/`dose_max`/`dose_is_range`/`range_provenance`); the 43 `SAFE_SINGLE_CANDIDATE` rows get `range_provenance` metadata only (no `dose_min`/`dose_max` — per the mission's explicit rule that this classification remains review-required, not migration-safe).

**Integrity check (real, executed):**
- Row count: 2675 before, 2675 after — unchanged.
- All 10 core clinical fields (`antibiotic, dose, unit, frequency, duration_recommended, route, diagnosis, status, approved_by, source_quote`) compared row-by-row between the original and V4 copy: **0 mismatches**.
- Rows with `dose_min` populated: 74 (matches `SAFE_EXACT_LINK` count exactly).
- **The authoritative `assembled_regimens.sqlite` SHA-256 hash was re-verified identical before and after building V4** (`9f505d08...` unchanged) — V4 is a separate file under `generated/`, never in-place modification.

V4 is excluded from git (per the same generated-clinical-artifact policy as V2/V3) — it is a local, regenerable experimental file.

## Wrong-anchor and ambiguity root-cause clusters (post-fix, 60 `WRONG_RANGE_ANCHOR` + 50 `AMBIGUOUS_MULTIPLE_DRUGS` + 40 `AMBIGUOUS_ALTERNATIVE_BOUNDARY` + 7 `AMBIGUOUS_MULTIPLE_RANGES`)

Real rejection-reason breakdown for the remaining 60 `WRONG_RANGE_ANCHOR` records (now diagnostically accurate): `SENTENCE_BOUNDARY` and `SEMICOLON` boundaries, `INTERVENING_DRUG` (a different antibiotic mentioned between the candidate drug and the range), and a residual `unit_mismatch`/`no_valid_segment` tail for compound units not covered by `UnitNormalizer` (e.g. `мг/кг/сутки` vs `мг/кг/день` variants not in the 33-entry `UNIT_NORMALIZATION` table) — a smaller, second-order dictionary-coverage gap, distinct from the drug-name gap addressed in C6.2.

## Loading/maintenance search across the full 2675-row corpus (Phase 18)

Beyond the 2 range-candidate records already flagged, a corpus-wide regex search for loading/maintenance phase markers (`нагрузочн|первая доза|стартов|поддерживающ|последующ`) found **80 of 2675 rows** (3%) contain this vocabulary — most are scalar (non-range) doses with an explicit phase marker, outside this program's 365-record range-candidate scope, but noted as a broader pattern relevant to future dose-semantics work in `dose_verification_sandbox/semantics_parser.py` (already handles some of this per C1's phase markers).

## Not-a-dose-range review (26 records, Phase 19)

Not individually re-audited this turn beyond the exclusion-reason categories already computed by the engine (age/duration/interval/maximum/non-increasing) — no false-positive regex pattern was found requiring a new regression test; the detector's unit whitelist continues to correctly exclude these upstream.
