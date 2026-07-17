# RC-030 Autonomous AI Source-Fidelity Audit — Report

**AI-only. NOT owner-verified, NOT clinically approved, calculation BLOCKED throughout.** All 60 events carry `review_origin=AI_AUTONOMOUS_AUDIT`, `human_validated=false`, `owner_verified=false`, `calculation_eligibility=BLOCKED`.

## Method — mechanically-blinded double pass

Pass 1 ran against `generated/rc030_recovery/_ai_audit_blinded_input.json`, which was built by **stripping every parser field** (`parser_semantic_type`, rule, confidence, risk flags) and all prior-AI/owner verdicts — verified zero parser leakage before reasoning began. Pass 1 verdicts were frozen and hashed (`RC030_AI_AUDIT_PASS1.json`, sha256 `a7b7bdd68469c08c...`) BEFORE Pass 2 revealed the parser candidate and prior AI verdict. Pass 1 was not edited during Pass 2.

**Honest caveat on internal conflict:** this audit is performed by a single AI analyst, so Pass 1 and Pass 2 share one reasoning process; `internal_conflict=false` for all 60 records means only that revealing the parser did not force me to abandon a frozen source-based verdict — it is NOT independent multi-model corroboration. Do not read 0 conflicts as strong evidence of correctness.

## Calibration (regimen 6657)

Blinded Pass 1 for "цефуроксим** 50 мг/кг" (no marker) = **REMAINS_AMBIGUOUS**, matching the owner's recorded verdict. Per mission: calibration PASSED. **One calibration success does not prove the other 59 results are correct** — it only shows the fail-closed reflex fires on the known case.

## Aggregate counts

| Metric | Count |
|---|---|
| Total audited | 60 |
| HIGH_EXPLICIT | 40 |
| MEDIUM_CONTEXTUAL | 7 |
| LOW_AMBIGUOUS | 11 |
| SOURCE_BLOCKED | 2 |
| Parser AGREE (same day/dose family) | 40 |
| Parser DISAGREE (opposite family) | 6 |
| Parser AI_NONCONFIRMING (parser confirmed, AI ambiguous/table/freq-error) | 14 |
| Prior-AI agreement (SAME) | 60 |
| Internal conflict | 0 (see caveat) |

## Final AI verdict distribution

| Verdict | Count |
|---|---|
| CORRECT_FIXED_SINGLE | 18 |
| CORRECT_EXPLICIT_PER_DOSE | 14 |
| REMAINS_AMBIGUOUS | 11 |
| CORRECT_RANGE_DAILY | 7 |
| CORRECT_EXPLICIT_PER_DAY | 5 |
| CORRECT_RANGE_SINGLE | 2 |
| TABLE_CONTEXT_REQUIRED | 2 |
| WRONG_FREQUENCY_LINK | 1 |

## Clusters (summary — full detail in RC030_AUTONOMOUS_AI_DEFECT_CLUSTERS.md)

| Cluster | Records | Severity |
|---|---|---|
| freq1_shortcut_markerless_mgkg | 4 | HIGH |
| freq1_shortcut_markerless_fixed | 5 | HIGH |
| odnokratno_misclassified | 3 | MEDIUM |
| r_sut_tokenization | 2 | MEDIUM |
| dvazhdy_tokenization | 1 | MEDIUM |
| weekly_schedule_collapse | 1 | MEDIUM |
| range_not_captured | 9 | HIGH |
| table_flattened_headers_lost | 2 | MEDIUM |
| loading_maintenance_ambiguity | 1 | LOW |
| v_n_priema_alone | 1 | LOW |

## What this audit does not do

- No governed precision computed from AI labels; `TYPES_MEETING_PRECISION_THRESHOLD` untouched (empty).
- No owner/clinical/calculation state changed.
- HIGH_EXPLICIT confirmations (e.g. "каждые 12 часов", "/сут", "однократно") are the only records with direct source support, and even those remain NOT_OWNER_VERIFIED.
