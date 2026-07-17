# RC-030 AI-Assisted Source Fidelity Pre-Review — Report

This is an **AI pre-review**, not owner validation, not physician approval. All 60 events are marked `review_origin=AI_PRE_REVIEW`, `owner_verified=false`, `clinically_approved=false`, `calculation_eligibility=BLOCKED`. Nothing in this turn enters the real owner event store (`rc030_owner_fidelity_dryrun_v1` in the interface's localStorage), touches any database, or affects `TYPES_MEETING_PRECISION_THRESHOLD`.

## Methodology note (honesty about the double-pass)

The mission specified a literal two-pass process (Pass 1 blind to the parser candidate, Pass 2 comparing against it). All 60 records' data (including the parser's `parser_semantic_type`) were loaded together in one dataset before review began, so a **literal** blinded first pass was not mechanically enforced. What was actually done: for every record, the source quote and context were read and a verdict was determined by applying the fail-closed rules (explicit "/сут"/"/сутки" marker → per day; explicit "каждые N часов"/"N раз(а) в день/сутки"/"однократно"/"разовая доза" → per dose or single; no marker or competing/insufficient context → ambiguous or table-context-required) **before** consulting the parser field in each individual reasoning step, and the parser field was then compared afterward, per record. This is a weaker guarantee than a mechanically enforced blind pass, and is disclosed here rather than overclaimed. No case surfaced where the independent reading felt genuinely torn between two source-supported answers, so `AI_INTERNAL_CONFLICT` = 0 — but that absence should be read in light of this methodological caveat, not as a stronger guarantee than it is.

## Calibration check (regimen 6657)

Independent AI read of "цефуроксим\*\* 50 мг/кг" (no marker): **`REMAINS_AMBIGUOUS`** — matches the owner's actual recorded verdict for this record exactly. The AI did **not** propose a confirming verdict here. Per the mission's stop-condition, the pre-review process is **not** classified as unreliable.

## Aggregate counts

| Metric | Count |
|---|---|
| Total reviewed | 60 |
| HIGH_EXPLICIT confidence | 40 |
| MEDIUM_CONTEXTUAL confidence | 7 |
| LOW_AMBIGUOUS confidence | 11 |
| SOURCE_BLOCKED confidence | 2 |
| Parser agreement (AGREE) | 36 |
| Parser disagreement (DISAGREE) | 16 |
| Partial agreement (direction right, range not captured — known limitation) | 8 |
| AI internal conflict | 0 |
| Owner-required count (categories B+C+D+F) | 23 |

## Proposed verdict distribution

| Proposed canonical verdict | Count |
|---|---|
| CORRECT_FIXED_SINGLE | 18 |
| CORRECT_EXPLICIT_PER_DOSE | 14 |
| REMAINS_AMBIGUOUS | 11 |
| CORRECT_RANGE_DAILY | 7 |
| CORRECT_EXPLICIT_PER_DAY | 5 |
| CORRECT_RANGE_SINGLE | 2 |
| TABLE_CONTEXT_REQUIRED | 2 |
| WRONG_FREQUENCY_LINK | 1 |

## Proposed parser-error categories (16 disagreements)

1. **Marker-less prophylaxis pattern (9 records)**: `6657, 6659, 6658, 6651, 6652, 6655, 6654, 5961` + one more (`6653`) — all on the "Повреждение связок коленного сустава.pdf" surgical-prophylaxis dose list (or the structurally identical `5961` cesarean-prophylaxis table row). Source states only a bare number (mg or mg/kg) with zero per-day/per-dose marker; parser used the frequency=1 algebraic-identity shortcut to assign `WEIGHT_PER_DAY`/`FIXED_PER_DAY`. This is a single **root pattern**, not 9 independent findings — the whole page's dosing table appears to lack explicit per-administration wording throughout.
2. **"однократно" (single/one-time) mismatched to a "PER_DAY" type (3 records)**: `5450, 5895, 5913` — parser assigns `FIXED_PER_DAY` to a regimen the source explicitly states is one-time-only. Numerically the value doesn't change, but the type label is a real mismatch worth a schema/taxonomy conversation (is "FIXED_SINGLE" meant to cover "one dose ever," or only "one dose per administration within a recurring regimen"?).
3. **Abbreviated "р/сут" not recognized as a per-dose marker (2 records)**: `6976, 7025` — "500 мг 2 р/сут" (2 times per day, abbreviated) was parsed as `FIXED_PER_DAY`, while the spelled-out equivalent "2 раза в сутки" elsewhere in the same corpus (e.g. `5897`, `5905`) is correctly parsed as `FIXED_PER_DOSE`. This looks like a genuine, fixable regex gap in the parser's frequency-marker pattern.
4. **"дважды" (twice, single word) not recognized (1 record)**: `7354` — "100 мг внутрь дважды в день" was parsed as `AMBIGUOUS` even though "дважды в день" is an unambiguous per-dose marker; likely the same class of regex gap as #3 (parser recognizes "N раз(а)" forms but not "дважды").
5. **Sub-weekly frequency not captured (1 record)**: `5374` — "10 мг/кг/сут 1 раз в день – 3 раза в неделю" (azithromycin, intermittent 3x/week dosing) has an explicit per-day dose marker, but the stored `frequency` field (1.0) doesn't represent the "3 раза в неделю" periodicity — a data-fidelity gap distinct from the semantic-type question.

## Table/multi-anchor cases requiring owner attention (5 records)

`5534` (multi-alternative-drug quote, verify anchor), `5683`/`7895` (flattened table row, headers lost), `5670` (two valid dosing alternatives for the same patient group), `6074` (age-group qualifier "≥40kg" not separately captured in the `child` flag).

## What this analysis explicitly does not do

- **No governed precision was computed from AI labels.** `dose_verification_sandbox.precision_calculator.compute_precision()` was not invoked with any AI-proposed verdict as input.
- **`TYPES_MEETING_PRECISION_THRESHOLD` was not touched** — confirmed empty before and after this turn.
- Confidence class alone is not a substitute for owner review; per the mission, `MEDIUM_CONTEXTUAL` results (7 records) are explicitly not to be treated as validated, and all `LOW_AMBIGUOUS`/`SOURCE_BLOCKED` results remain unresolved by design.

See `RC030_AI_PRE_REVIEW_DISAGREEMENTS.md` for full per-record disagreement detail and `RC030_AI_OWNER_CONTROL_SAMPLE.json` for the reduced-workload owner queue.
