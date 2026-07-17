# RC-030 / C6.7 Part IV-V — Blinded Pass A / Pass B Double-Pass Report

## Method

**Pass A (blind):** `generated/rc030_c67/pass_a_input.json` (117 records, frozen, sha256 `a6c9a1d9bd4ea03969d6e1eb7d9629c8b0a994d0408bbe148c9a1e866fdc2393`) carries only: regimen_id/version, expected_antibiotic, structured_dose/unit/route/age_group/frequency/duration, diagnosis, source_pdf/page/quote. No prior classification, span offset, score, or engine output was included — verified by direct key-diff against the forbidden-field set before freezing.

Three independent reviewer passes (no shared state, no access to `candidate_117_manifest.json` or any engine output) each covered a disjoint slice (30 / 44 / 43 records, sorted by regimen_id) and returned one of: `INDEPENDENT_EXACT_LINK`, `INDEPENDENT_TABLE_LINK`, `INDEPENDENT_SINGLE_PLAUSIBLE`, `INDEPENDENT_AMBIGUOUS`, `INDEPENDENT_WRONG_ANCHOR`, `INDEPENDENT_NOT_A_RANGE`, `INDEPENDENT_SOURCE_BLOCKED`, with a rationale and confidence per record. Merged output: `generated/rc030_c67/pass_a_output.json` — **117/117 covered, 0 missing, 0 duplicate.**

**Pass B (reveal):** engine classification (`frozen_classification` from `candidate_117_manifest.json`) was compared against the Pass A verdict per record. `generated/rc030_c67/double_pass_results.json`.

## Pass A verdict distribution (117 records)

| Verdict | Count |
|---|---|
| INDEPENDENT_EXACT_LINK | 71 |
| INDEPENDENT_SINGLE_PLAUSIBLE | 26 |
| INDEPENDENT_TABLE_LINK | 13 |
| INDEPENDENT_NOT_A_RANGE | 4 |
| INDEPENDENT_AMBIGUOUS | 2 |
| INDEPENDENT_WRONG_ANCHOR | 1 |
| INDEPENDENT_SOURCE_BLOCKED | 0 |

## Pass A vs. engine comparison (117 records)

| Comparison | Count |
|---|---|
| EXACT_AGREEMENT | 54 |
| DIRECTIONAL_AGREEMENT | 30 |
| TABLE_REQUIRED | 13 |
| ENGINE_OVERCONFIDENT | 13 |
| WRONG_ENGINE_LINK | 7 |
| ENGINE_UNDERCONFIDENT | 0 |
| PASS_A_UNCERTAIN | 0 |
| SOURCE_CONFLICT | 0 |

No case required forcing agreement; every disagreement is dispositioned below rather than overridden.

## 74 SAFE_EXACT_LINK — comparison breakdown

| Comparison | Count |
|---|---|
| EXACT_AGREEMENT | 54 |
| ENGINE_OVERCONFIDENT | 13 |
| TABLE_REQUIRED | 5 |
| WRONG_ENGINE_LINK | 2 |

### WRONG_ENGINE_LINK detail (2 records — real disagreements, investigated)

- **regimen_id 5678** (Цефтриаксон): source quote contains three competing numeric expressions for the same drug — a range "20-80 мг/кг/сут", a specific recommended scalar "75 мг/кг/сут", and a second, higher range "50-100 мг/кг/сут" attributed to foreign literature. The engine picked one range as the unique link; the independent reviewer found no clear single winner among three plausible candidates. **Genuine ambiguity the engine under-detected.**
- **regimen_id 6133** (Клиндамицин): quote reads "при тяжелом течении – до 1,2-4,8 г/сут" — the "до" (up to) framing plus competing scalar/pediatric-range mentions elsewhere in the same quote make this read as a maximum-dose qualifier rather than a clean therapeutic range. **Genuine wrong-anchor risk the engine did not flag.**

### ENGINE_OVERCONFIDENT detail (13 records)

Independent reviewers rated these `INDEPENDENT_SINGLE_PLAUSIBLE` rather than a clean exact link — typically because other drug names or a secondary numeric expression appear elsewhere in the same quote even though the engine's structural rules found exactly one valid segment. IDs: 5842, 5847, 5917, 5918, 6074, 6075, 7051, 5441, 5442, 5475, 5478, 5546, 5547.

**Cross-validation with the unit-normalization audit** ([RC030_C67_UNIT_NORMALIZATION_AUDIT.md](RC030_C67_UNIT_NORMALIZATION_AUDIT.md)): 6 of these 13 (5917, 5918, 5441, 5442, 5475, 5478) were *independently* flagged by the byte-level unit-basis audit as having a `mg` vs `mg/kg` dose-basis conflation. Two unrelated audit methods converging on the same 6 records is a strong signal these are not clean exact links, regardless of which single defect is cited.

### TABLE_REQUIRED detail (5 records)

5683, 6579, 6580, 7258, 7895 — independent reviewers identified these as flattened/concatenated table-row fragments (drug/dose/max/route/frequency on separate lines or dashes, no connecting prose), even though the engine's `table_context` flag was never set for them (recall: 0/117 records in this pool carry the engine's own table flag — see PDF/table evidence audit). This is a **real detection gap**: the engine's table-context detection relies on `needs_review_reasons` containing "table", which these records' source data apparently didn't trigger, yet the raw quote text is table-shaped.

## 74 SAFE_EXACT_LINK — final disposition

| Disposition | Count | IDs |
|---|---|---|
| EXACT_LINK_RETAINED | 53 | (EXACT_AGREEMENT, no unit-basis flag) |
| EXACT_LINK_DOWNGRADED_AMBIGUOUS | 13 | 5842, 5847, 5917, 5918, 6074, 6075, 7051, 5441, 5442, 5475, 5478, 5546, 5547 |
| EXACT_LINK_DOWNGRADED_TABLE_REQUIRED | 5 | 5683, 6579, 6580, 7258, 7895 |
| EXACT_LINK_REJECTED_WRONG_ANCHOR | 2 | 5678, 6133 |
| EXACT_LINK_ENGINE_REVIEW_REQUIRED | 1 | 6085 (low-severity unit-annotation gap — Pass A agreed EXACT_LINK at 0.9 confidence, but structured_unit lacks the `/day` qualifier the source text carries; not wrong, but incomplete) |
| **Total** | **74** | |

Full per-record data: `generated/rc030_c67/exact_link_disposition.json`, `generated/rc030_c67/double_pass_results.json`.

**Retained exact-link pool after independent audit: 53/74 (72%).** 21 records (28%) are downgraded, rejected, or flagged for engine review — every one of them is not preserved merely to hit a target count, per the owner's explicit instruction.

## 43 SAFE_SINGLE_CANDIDATE — comparison breakdown

| Comparison | Count |
|---|---|
| DIRECTIONAL_AGREEMENT | 30 |
| TABLE_REQUIRED | 8 |
| WRONG_ENGINE_LINK | 5 |

WRONG_ENGINE_LINK detail and full 43-record disposition: see [RC030_C67_SINGLE_CANDIDATE_DISPOSITION.md](RC030_C67_SINGLE_CANDIDATE_DISPOSITION.md) (Part VI).

## Reviewer self-reported uncertainty (non-blocking, recorded for owner review priority)

Reviewers flagged 9 records across all three batches as "genuinely torn between two verdicts" even after deciding (5364, 5726, 5546/5547/5842 batch 1; 6133, 6989, 6068, 6579/6580 batch 2; 7051, 7194-family, 7548/7559 batch 3). These are good candidates for the owner's first review pass regardless of which disposition bucket they landed in — flagged in the owner queues (Part X) as `pass_a_reviewer_uncertain = true`.
