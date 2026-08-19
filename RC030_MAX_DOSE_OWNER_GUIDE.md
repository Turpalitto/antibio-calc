# RC-030 Max-Dose Owner Queue — Guide

20 mechanically-selected max-dose candidates (`RC030_MAX_DOSE_OWNER_QUEUE.json`), all with a locally-available source PDF (35/104 mechanical max-dose candidates have a local PDF; the 20 shortest/cleanest source quotes were chosen for a fast first pass, same rationale as the 60-record owner pilot queue).

## What "max-dose candidate" means here

`dose_verification_sandbox.semantics_parser.extract_max_dose_signal()` found a phrase near the dose that looks like a maximum-dose clause (e.g. "не более...", "максимум...", "max..."). This is **purely mechanical pattern matching** — it has not been validated, and per `RC030_FAIL_CLOSED_IMPLEMENTATION_AUDIT.md` no max-dose value can affect any calculation regardless (`calculator.py`'s `apply_max_dose()` is never called automatically; `trace.max_dose_reason` defaults to `MAX_DOSE_NOT_AVAILABLE`).

## What the owner needs to check per record

For each of the 20 records, verify against the source PDF:
1. **Exact maximum phrase** — does `max_dose_signal` actually point at a real maximum-dose statement, or is it a false-positive match (e.g. matching "не более 10 дней" — a duration limit, not a dose limit)?
2. **Numeric value and unit** — does the extracted number/unit match what the PDF actually says?
3. **Daily vs. single** — does the phrase clearly say "maximum *daily*" or "maximum *single (per-administration)*" dose? Ambiguous phrasing should be flagged, not guessed.
4. **Same antibiotic, same age group, same alternative** — in a multi-drug or multi-alternative source quote, does the maximum genuinely belong to *this* regimen's antibiotic/age-group, or could it belong to a different alternative in the same sentence?
5. **Range-upper-bound confusion** — is this genuinely a maximum-dose clause, or is it actually the upper bound of a dose range (see `RC030_RANGE_LOSS_STAGE_RCA.md`) that `extract_max_dose_signal` mismatched as a "maximum"? 4 of the 20 queued records are tagged `range_near_max` specifically to surface this risk.

## No usability without confirmation

No max-dose value becomes usable for anything — QA calculation or otherwise — without an explicit owner source-fidelity confirmation, and even then, `calculation_eligibility` for the regimen as a whole is governed entirely by `TYPES_MEETING_PRECISION_THRESHOLD` (currently empty), never by max-dose confirmation alone.

This queue is prepared for review; it has not been reviewed. Loading it into the owner-review interface (extending it to cover max-dose-specific verdicts) is a follow-up not implemented this turn.
