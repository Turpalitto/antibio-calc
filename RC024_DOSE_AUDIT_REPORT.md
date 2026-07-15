# RC024_DOSE_AUDIT_REPORT.md
## Full Audit of 1,132 REJECT ClinicalRegimens · P5.4 · 2026-07-15
## Status: AUDIT COMPLETE — computed against the full REJECT population, not a sample

> All 1,132 REJECT regimens fail exclusively at **Gate 1 (Completeness)**
> (`P5.3_IMPLEMENTATION_REPORT.md` — confirmed: `REJECT by gate: {'G1_completeness': 1132}`).
> Breakdown: 378 route-only missing · 557 dose+route missing · 197 dose-only missing → 754 total
> dose-missing, 378 route-only-missing (of the non-dose-missing REJECTs). This document classifies
> WHY, computed by regex/signal analysis over the real `source_quote`, `field_confidence`, and
> `drug_original` columns for the complete set — not extrapolated from a sample.

## Method
For each REJECT regimen's underlying `normalized_regimens` row:
- **Dose-missing (754)** classified by: presence of a numeric+unit pattern in `source_quote`
  (`\d+\s*(мг|г|ЕД|мл|мкг)`), presence of "или/либо" (or) branching, whether `drug_original` reads
  as a drug class/alternatives list (length, class-term keywords), and `field_confidence.dose`
  (consistently `0.0` across this set — confirming the normalizer genuinely found no dose signal,
  not that it found one and failed to parse it).
- **Route-only-missing (378)** classified by: presence of route keyword(s)
  (внутривенно/перорально/внутрь/в/в/в/м/местно/etc.) literally in `source_quote`, and whether
  multiple distinct route options are offered ("или").

## Category definitions & results

### Dose-missing (754 rows)

| Category | Definition | Count | % | Auto-fixable? | Physician needed? |
|---|---|---:|---:|:---:|:---:|
| **B — dose intentionally absent** | `source_quote` is a drug-class/alternatives statement with NO numeric dose anywhere (e.g. "макролиды", "цефалоспорины 2-го/3-го поколения", "другие бета-лактамные препараты") — the guideline is naming a drug OPTION or CLASS, not prescribing a quantified regimen | **675 (89.5%)** | No — there is no dose to extract; this is not an extraction gap | **Yes** — a physician must decide whether this is (a) a valid class-level recommendation that should be modeled differently (not as a single-drug dosed regimen), or (b) excluded from the regimen corpus entirely |
| **C — conditional dosing** | `source_quote` contains a numeric dose AND an "или"/"либо" branch (multiple dose options depending on an unstated condition, e.g. two drugs each with a different dose in one sentence) | **48 (6.4%)** | No — picking one value would be guessing | **Yes** — physician selects/splits into distinct regimens |
| **A — extraction failure** | `source_quote` contains a clear numeric+unit dose pattern, but the field is null — the value was present in text and the extractor missed it | **31 (4.1%)** | **Partially** — re-extraction (not in-place fabrication) could recover these; requires re-running the LLM/normalizer extraction on these specific rows, which is a `normalized_regimens` change and out of P5.4 scope (rule 5: do not modify normalized_regimens) | Flagged for a future targeted re-extraction pass; not touched here |
| D — pediatric/adult split | (checked, not separately triggered in this set beyond what's captured in B/C — population-specific dose splits present in the corpus are already handled correctly upstream when a numeric value exists) | 0 distinct | — | — | — |
| F — other | Empty quote or unclassifiable | 0 | — | — | — |

**Dominant finding: 89.5% of dose-missing REJECTs are not a data quality defect at all — they are
guidelines correctly describing a drug class or an alternatives list without a single quantified
dose.** The REJECT verdict is *clinically correct* for these as single-drug dosed regimens: forcing
a dose onto a class-level statement would be fabrication, exactly what `DOSE_NORMALIZATION_POLICY.md`
prohibits. This is a **regimen-modeling scope question**, not a defect to silently fix.

### Route-only-missing (378 rows — dose already present and correct)

> **Correction (post-implementation):** the count below was recomputed against the actual, safety-
> reviewed `recover_route_from_quote()` implementation (`field_normalization.py`), not the
> exploratory regex used during initial audit. The initial audit regex included bare single-character
> matches (`в`, `м\b`) which are near-ubiquitous prepositions in Russian medical text and produced a
> **false Category-E count of 296 (78.3%)**. The real, strict, ambiguity-checked implementation
> (word-stem patterns only: `внутривенн\w*`, `в/в\b`, etc., never a bare preposition) recovers far
> fewer — this is reported honestly below, not left at the inflated exploratory figure.

| Category | Definition | Count (corrected) | % | Auto-fixable? | Physician needed? |
|---|---|---:|---:|:---:|:---:|
| **E — route present in text, not parsed** | `source_quote` literally contains an unambiguous, specific route keyword (word-stem match, no bare prepositions), single option | **13 (3.4%)** | **Yes — safe, source-backed** | No |
| **C — conditional/ambiguous route** | `source_quote` offers 2+ distinct specific route options | **21 (5.6%)** | No — picking one would be guessing | Yes, if a specific route is clinically required |
| (recomputed) no specific route keyword recoverable at all | route genuinely not stated in this snippet (info elsewhere in the guideline, or truly implicit) | **344 (91.0%)** | No | Yes — needs the fuller guideline context or physician judgment |

**Real, implemented, safe fix: 13 regimens (1.1% of all 1,132 REJECTs) get `route` correctly derived
from unambiguous text in their own `source_quote`.** The remaining 91% of route-missing cases do not
contain a specific, unambiguous route keyword in the stored `source_quote` snippet — recovering them
would require either a wider text window (out of P5.4 scope, an extraction-layer change) or
physician input. This is a smaller improvement than the exploratory pass suggested, and is reported
at its true, implemented size — not the inflated exploratory estimate.

## Summary table (corrected to match the actual implemented, safety-reviewed logic)

| Category | Count | Share of 1,132 | Auto-fixable (safe) | Requires physician |
|---|---:|---:|:---:|:---:|
| B — dose intentionally absent (class/alternatives) | 675 | 59.6% | No | Yes |
| E — route present in text, unparsed (implemented) | 13 | 1.1% | **Yes** | No |
| C — conditional ambiguous (dose or route) | 69 | 6.1% | No | Yes |
| A — genuine dose extraction failure | 31 | 2.7% | Partial (needs re-extraction, out of scope) | Deferred |
| Route not recoverable from stored quote snippet | 344 | 30.4% | No (needs wider context or physician) | Yes/deferred |

**Total safely auto-fixable and IMPLEMENTED within P5.4 scope: 13 / 1,132 (1.1%).**
**Total requiring physician judgment: ~775 / 1,132 (~68%) — correctly REJECTed, not hidden.**
**Total deferred (extraction-layer, out of scope): 31 dose + 344 route-context ≈ 375 / 1,132 (~33%).**

## Conclusion feeding into DOSE_NORMALIZATION_POLICY.md
The audit does NOT support broadly loosening Gate 1. The overwhelming majority of REJECTs (89.5% of
dose-missing, 59.6% of the total) are guidelines that are structurally not single-drug dosed
regimens — publishing them as if they were would be the fabrication the whole P5.x governance stack
exists to prevent. The real, safe, measurable improvement — route recovery from literal, unambiguous
in-quote text — is genuinely small (13 regimens, 1.1%) once implemented under a properly strict,
ambiguity-checked matcher; an earlier exploratory estimate (296) was inflated by an overly permissive
regex and is corrected here rather than left standing. **A small, honest improvement is worth more
than a large, wrong one** — the whole point of measuring before claiming.
