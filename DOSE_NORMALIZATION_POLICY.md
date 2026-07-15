# DOSE_NORMALIZATION_POLICY.md
## Rules for Automatic Regimen Field Normalization · P5.4
## Status: ADOPTED — governs P5.4 Task 4 implementation and all future normalization work

> Grounded in `RC024_DOSE_AUDIT_REPORT.md`'s finding that 71.1% of REJECTs require physician
> judgment and only 26.2% are safely auto-fixable. This policy exists to make that line permanent
> and machine-enforced, not a one-time judgment call.

## The one absolute rule
**Never generate a dose. Never guess a dose, route, frequency, or duration value that is not
literally recoverable from the regimen's own source text.** Every value a normalization step
produces MUST be traceable to specific characters in that regimen's own `source_quote` (or an
equivalent already-certified provenance field) — never inferred from population statistics, drug
class defaults, similar regimens, or "typical" values.

## What counts as "source-backed normalization" (permitted)
A transformation is source-backed if it is a **deterministic, reversible mapping** from text
literally present in the regimen's own source to a normalized representation of the SAME
information — not new information:
- **Keyword/synonym normalization:** "в/в" / "внутривенно" / "внутривенно капельно" → a canonical
  `route=intravenous` value, where the keyword is present, unambiguous (exactly one route family
  matched), and the mapping is a fixed, reviewable dictionary — not a heuristic guess.
- **Unit string canonicalization:** "мг" → "mg", "г" → "g", consistent casing/spacing — the
  numeric value is untouched, only its unit's textual representation.
- **mg/kg formatting:** ensuring a weight-based dose's unit string is uniformly `"mg/kg"` when the
  source states it as such — again, representation only, not value invention.
- **Frequency representation:** converting an already-extracted "times per day" float into a
  human-readable period label (e.g. "1 раз в 3 дня") — the underlying number is not changed,
  altered, or rounded to a different clinical meaning.

## What is FORBIDDEN, always
- Filling a null `dose` with a class-typical, drug-typical, or population-typical value.
- Picking one value from an "или"/"либо" (or) branch in the source text — an ambiguous source stays
  ambiguous; ambiguity is not resolved by the normalizer.
- Inferring `route=oral` because no other route is mentioned (absence of a stated route is NOT
  evidence of oral — it is evidence of missing information, per RC024's Category A finding of 82
  genuinely ambiguous cases).
- Treating a drug-class/alternatives statement (RC024 Category B, 675 rows) as if it were a
  single-drug dosed regimen by picking one drug and a "reasonable" dose. This is a MODELING
  question for a physician, not a normalization problem to paper over.
- Any transformation whose output cannot be traced field-by-field to the specific source characters
  that produced it (breaks the `FieldProvenance` contract from `CLINICAL_REGIMEN_MODEL.md`).

## Every normalized field carries provenance
A field touched by automatic normalization gets a `FieldProvenance` with `source_store` tagged
distinctly from the base extraction (e.g. `"normalized_regimens+text_normalization"`), so it is
always visible on audit which fields came from the original LLM extraction verbatim and which were
derived by a P5.4 normalization pass — never silently merged into looking identical to a
human-verified value.

## Ambiguity always routes to REVIEW, never REJECT-by-default or PASS-by-default
When a normalization step CANNOT resolve a field with full confidence (multiple route options,
conditional dose, class-level statement), the regimen's status is left exactly as the assembly/
validation layer already determines it (REJECT for missing hard fields, REVIEW for soft gaps) — the
normalization step does not change gate severity, only recovers values that ARE safely recoverable.

## Metrics discipline
Every normalization run reports, permanently and honestly:
- how many fields were normalized (and by which rule),
- how many candidates were EXAMINED but left unchanged because they failed the safety test
  (ambiguous, no literal match),
- the before/after gate-verdict distribution (PASS/REVIEW/REJECT), so a reduction in REJECT is
  always shown alongside the reason, never presented as a bare improved number.

## Relationship to Gate 1
This policy does not change `REGIMEN_VALIDATION_GATES.md` Gate 1's completeness requirement. It
changes what data REACHES Gate 1 by recovering values that were always present in the source and
simply not parsed — Gate 1 itself is not weakened, loosened, or given new pass conditions.
