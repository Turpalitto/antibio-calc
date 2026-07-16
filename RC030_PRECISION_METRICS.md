# RC030_PRECISION_METRICS.md

Status: RC-030 Evidence Validation, Phase 5. Precision computed from the Phase 4 manual sample
(`dose_verification_sandbox/data/phase4_validation_sample.json`), independently re-read against
`source_quote` — the parser's own output was **not** used as the answer key.

## Achieved sample size vs. requested

The spec requested ≥50/50/50/50/30/30/30/30/30/30 (380 total, stratified). **This was not achieved.**
Given the time available for this pass, 135 rows were drawn and read (15 per stratum × 9 strata:
`WEIGHT_PER_DAY`/`WEIGHT_PER_DOSE`/`FIXED_PER_DAY`/`FIXED_PER_DOSE` clean strata, a high-risk stratum,
a max-dose-extraction stratum, `AMBIGUOUS`, `UNPARSED`, and multi-alternative/combination-drug rows).
This is stated plainly, not minimized: **the sample is too small to statistically support the
requested 99%-precision claim at any reasonable confidence level**, regardless of how clean the
results look — see the Wilson intervals below.

## Results by stratum (manual re-read verdicts, independent of parser output)

| Stratum | n | correct | point precision | Wilson 95% CI |
|---|---:|---:|---:|---|
| WEIGHT_PER_DAY (clean) | 15 | 14 | 93.3% | (70.2%, 98.8%) |
| WEIGHT_PER_DOSE (clean) | 15 | 15 | 100% | (79.6%, 100%) |
| FIXED_PER_DAY (clean) | 15 | 15 | 100% | (79.6%, 100%) |
| FIXED_PER_DOSE (clean) | 15 | 15 | 100% | (79.6%, 100%) |
| High-risk (flagged by Phase 3 audit) | 14 | 13 | 92.9% | (68.5%, 98.7%) |
| Max-dose extraction | 7 | 7 | 100% | (64.6%, 100%) |

**Not one stratum's Wilson lower bound reaches the spec's required 99% precision threshold** — even
the four perfect 15/15 strata only support a lower bound of ~79.6%. This is a direct, unavoidable
consequence of sample size: achieving a 99% lower-bound CI on a claimed-perfect stratum requires on
the order of several hundred samples, not 15. No amount of additional confidence in the *point*
estimate substitutes for statistical power the sample doesn't have.

## What the manual re-read actually found

**One dangerous bug**, found and fixed during this review (see `RC030_VALIDATION_BASELINE.md` for the
pre-fix module hash): regimen 7951 was classified `WEIGHT_PER_DAY`/`RESOLVED_BY_FREQUENCY_ONE` despite
its dose token ("10") not appearing anywhere in its `source_quote` at all. Root cause: the
frequency=1 algebraic shortcut was applied whenever no period signal was found, without checking
whether the dose token had even been *located* in the text first. Fixed in `semantics_parser.py`
(`dose_token_located` guard); regression test added
(`test_frequency_one_shortcut_never_applies_without_locatable_dose_token`). Re-running the full
corpus after the fix moved 34 rows (1.3% of the corpus, 2.1% of previously-`PARSER_CANDIDATE` rows)
from a resolvable type to `AMBIGUOUS`.

**One evidentiary misattribution** in the high-risk stratum (regimen 6242, `CROSSES_ALTERNATIVE_BOUNDARY`):
the matched `"/сут"` fragment for a 250 mg azithromycin dose actually belongs to a *different* drug
("рофлумиласт... 250 или 500 мкг/сут") listed earlier in the same sentence, not to azithromycin's own
"1 раз в сут" clause. The final calculated number happens to be numerically unaffected (frequency=1
makes per-dose/per-day identical regardless), but the **displayed evidence is wrong** — the owner
would be shown the wrong justification for a coincidentally-correct number. This is exactly the kind
of finding the Phase 3 independent risk audit exists to catch, and it did (this row was already
flagged `CROSSES_ALTERNATIVE_BOUNDARY` before this manual check confirmed it as a real problem, not a
false alarm).

**Several coverage gaps, not correctness bugs** (fail-safe, not fail-dangerous): dose numbers written
with a thousands-separator space (`"1 000 мг"`) are not located by the current token-matching logic;
an OCR-corrupted `"стуки"` (should be `"сутки"`) does not match; `"дважды"`/`"трижды"` alone (without a
following `"раз"`) are not recognized as frequency words; `"в N приема"` (divided into N doses) is not
recognized as a per-dose signal. All of these correctly fall through to `AMBIGUOUS` rather than being
guessed — safe, but leaves real, resolvable cases unresolved. Not fixed in this pass; listed as
improvement opportunities, not defects, since the failure direction is the safe one.

## Precision threshold determination (per spec Phase 5 rule)

> "Types below threshold must remain `NEEDS_SOURCE_VALIDATION`, not calculable."

Applying this literally and conservatively: **every one of the four resolvable semantic types
(`WEIGHT_PER_DAY`, `WEIGHT_PER_DOSE`, `FIXED_PER_DAY`, `FIXED_PER_DOSE`) remains below the 99%
Wilson-lower-bound threshold**, because no stratum's sample was large enough to demonstrate it,
regardless of the (encouraging) point estimates. Per the rule, **none of them may be treated as
calculation-eligible on the strength of this validation pass.** See Phase 9 (`RC030_STATUS_MODEL`
implementation) for how this is enforced in code: every `DoseSemantics` record defaults to
`validation_status = UNVALIDATED` and `calculation_eligibility = BLOCKED`, regardless of
`semantic_type`, until a larger validation pass (or a different, statistically adequate acceptance
methodology, e.g. per-rule rather than per-type precision with pooled samples) is completed.
