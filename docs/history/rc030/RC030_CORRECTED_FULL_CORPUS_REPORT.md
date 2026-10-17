# RC030_CORRECTED_FULL_CORPUS_REPORT.md

Status: RC-030 Evidence Validation, Phase 12. Supersedes the terminology used in
`RC030_DOSE_SEMANTICS_AUDIT.md` (which described parser output as "resolved") and
`DOSE_VERIFICATION_SANDBOX_REPORT.md`/`PROJECT_STATE.md`'s earlier "61.5% resolved" framing. Numbers
below reflect the classifier and calculator **after** the three fixes made during this validation
pass (see `RC030_VALIDATION_BASELINE.md` for the pre-fix module hash; module hash has changed since).

## Corrected terminology

| Old term (imprecise) | Correct term (this report) | Meaning |
|---|---|---|
| "resolved" | `PARSER_CANDIDATE` | The classifier assigned a non-ambiguous `semantic_type` — not evidence of correctness |
| — | `validation_status` | What kind of check, if any, has actually confirmed the candidate (see below) |
| — | `calculation_eligibility` | Whether a record may be treated as safe to calculate — currently `BLOCKED` for 100% of the corpus, by design (see `RC030_PRECISION_METRICS.md`) |

## PARSER_CANDIDATE counts (full corpus, n=2,675, post-fix)

| semantic_type | count | % |
|---|---:|---:|
| MISSING | 658 | 24.6% |
| FIXED_PER_DOSE | 579 | 21.6% |
| FIXED_PER_DAY | 506 | 18.9% |
| WEIGHT_PER_DAY | 446 | 16.7% |
| AMBIGUOUS | 236 | 8.8% |
| NOT_APPLICABLE | 96 | 3.6% |
| WEIGHT_PER_DOSE | 80 | 3.0% |
| UNPARSED | 74 | 2.8% |

Changed from the pre-validation numbers (`RC030_VALIDATION_BASELINE.md`): `WEIGHT_PER_DAY` 461→446
(-15), `FIXED_PER_DAY` 525→506 (-19), `AMBIGUOUS` 202→236 (+34) — the 34-row net movement is the
`dose_token_located` fix from Phase 4 (rows where the dose number wasn't actually locatable in
`source_quote` no longer get the `RESOLVED_BY_FREQUENCY_ONE` shortcut).

**`PARSER_CANDIDATE` total: 1,611 rows (60.2% of corpus)** — down from the previously-reported 1,645
(61.5%), reflecting the correction.

## validation_status (this validation pass's independent layer, Phase 9)

| validation_status | count | meaning |
|---|---:|---|
| `RULE_VALIDATED` | 1,304 | Classifier rule fired cleanly with no risk factors from the Phase 3 independent audit |
| `UNVALIDATED` | 1,135 | Either no candidate exists (MISSING/NOT_APPLICABLE/UNPARSED = 828) or a candidate exists but was flagged high-risk by the independent audit (307) |
| `AMBIGUOUS` | 236 | Classifier itself reports no resolvable signal |

## calculation_eligibility (the number that actually matters for safety)

| calculation_eligibility | count |
|---|---:|
| `BLOCKED` | **2,675 (100%)** |
| `QA_ELIGIBLE` | 0 |
| `CLINICALLY_INELIGIBLE` | 0 |

**Every single row in the corpus is currently `BLOCKED` for calculation eligibility purposes — including
all 1,304 `RULE_VALIDATED` rows.** This is not a bug; it is the direct, intended consequence of
`RC030_PRECISION_METRICS.md`'s finding that no semantic type's precision has been demonstrated at the
required 99% Wilson-lower-bound with the sample sizes achieved in this pass
(`TYPES_MEETING_PRECISION_THRESHOLD` is empty by design in `validation_status.py`). A future,
adequately-powered validation pass (hundreds of samples per type, not 15) could populate that set and
change this number — nothing in the current codebase does so automatically.

## Additional finding not yet reflected above: sub-daily frequency

42 of the 1,611 `PARSER_CANDIDATE` rows have `frequency < 1` (representing weekly/monthly dosing, not
daily) and would independently `BLOCKED` at the arithmetic stage (`SUB_DAILY_FREQUENCY`, found and
fixed in Phase 6) even if they were otherwise eligible — already correctly reflected in
`calculation_eligibility = BLOCKED` for those rows via the parser-candidate/validation-status path,
called out here separately because it's a distinct failure mode (arithmetic-formula misapplication,
not semantic misclassification) worth tracking on its own.

## Honest summary

Before RC-030: 0 rows had any dose semantics beyond the raw, unusable `dose`/`unit` pair. After
RC-030's parser work: 1,611 rows (60.2%) have a plausible `PARSER_CANDIDATE` classification, with
three real bugs found and fixed along the way (`dose_token_located`, `SUB_DAILY_FREQUENCY`, and the
proximity-window gap-calculation bug in the risk audit itself). After this validation pass: **0 rows**
are actually safe to treat as calculation-eligible, because the precision of the classifier has not
been proven at the confidence level the task required — not because the classifier is known to be
wrong, but because the sample sizes used to check it were too small to prove it right with
statistical confidence. The gap between "looks right on every sample checked" (93–100% point
estimates across all six strata) and "proven right" (99% Wilson lower bound) is exactly the gap this
Evidence Validation pass exists to make visible rather than paper over.
