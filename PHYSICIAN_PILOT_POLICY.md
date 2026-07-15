# PHYSICIAN_PILOT_POLICY.md
## PHYSICIAN_PILOT_V1 — Named Pilot Selection Policy · P5.6 RC-027 Phase 6

> Formalizes the owner-requested pilot priority order as an explicit, named, versioned policy,
> implemented in `clinical_engine/review_workbench/pilot_policy.py`. **Does not replace or modify
> `priority.py`'s production priority model**, which continues to order the general 9,153-task
> queue unchanged.

## Policy identity
`POLICY_NAME = "PHYSICIAN_PILOT_V1"`, `POLICY_VERSION = 1`. Any future change to tier order,
quotas, or keyword patterns must increment the version and be documented as `PHYSICIAN_PILOT_V2`,
never silently edited in place.

## Tier order (owner's exact specification)
1. pediatric
2. pregnancy
3. renal impairment
4. severe allergy
5. missing dose or unit
6. unresolved conflict
7. source mismatch

## Quotas — the deterministic anti-monopoly rule
`cap = ceil(batch_size / tiers_present)`. Fill each tier up to `cap`, in tier order; if a tier has
fewer candidates than `cap`, the remainder rolls to the next tiers in order (never left unfilled if
alternatives exist). This is why a first, uncapped run (20 pediatric-only ClinicalRegimen, 10
untagged TherapeuticOption) was rejected and replaced with the capped selection actually shipped in
`pilot_review_batch/` — see `PILOT_REVIEW_BATCH_REPORT.md` §3-4 for the measured before/after.

## Signal origin — STORED vs DERIVED_REVIEW_SIGNAL (never conflated)
Every tier match is tagged with exactly one origin:
- **`STORED`** — the task's own `safety_axes`/`issue_type`, written by `queue_builder.py` at
  ingestion time from real, structured data (kb_p44 provenance, dose-audit records, etc.).
- **`DERIVED_REVIEW_SIGNAL`** — found ONLY by a keyword regex over the target's own free text
  (`indication`/`diagnosis`/`therapeutic_class`/`source_quote`/etc.), used exclusively because the
  stored tags are absent for that category (see `THERAPEUTIC_OPTION_REVIEW_TAGGING_AUDIT.md` — 0/652
  TherapeuticOption tasks and most ClinicalRegimen severe-allergy/renal cases carry no stored tag at
  all today).

**Hard rule:** a `DERIVED_REVIEW_SIGNAL` match is a *pilot-selection convenience* — it decides which
tasks a physician sees first. It is **never** written back into `safety_axes`, `issue_type`, or any
clinical field, and never treated as equivalent to a physician's own judgment. The physician review
packet still shows the raw target content; the reviewer forms their own clinical opinion regardless
of why the task was selected for the pilot.

## Limitations (stated plainly)
- Keyword patterns are simple regex over Russian medical terms; they can miss synonyms or produce
  a false positive on an unrelated mention of the same word in a different clinical context. They
  are a selection aid, not a clinical claim.
- The quota-capped selection guarantees *representation* across tiers, not statistical
  proportionality to the true population size of each risk category.
- `renal` and `severe_allergy` STORED tags are extremely rare or absent system-wide (5 and 0 of
  9,153 tasks respectively) — see `THERAPEUTIC_OPTION_REVIEW_TAGGING_AUDIT.md` for the root cause
  investigation. `PHYSICIAN_PILOT_V1`'s keyword fallback compensates for pilot-selection purposes
  only; it does not fix the underlying tagging gap.
