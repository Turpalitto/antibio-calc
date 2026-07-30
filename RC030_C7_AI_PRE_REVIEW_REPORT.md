# RC-030 C7 AI Pre-Review Report

Date: 2026-07-29

## Verdict

**AI PRE-REVIEW COMPLETE — NOT OWNER REVIEW, NOT CLINICAL APPROVAL**

All 113 tasks in `generated/rc030_c7/review_tasks_ready.json` received an
advisory AI source-fidelity classification. The artifact is deliberately
disjoint from the owner event format:

- `review_origin = AI_PRE_REVIEW`
- `owner_verified = false`
- `human_validated = false`
- `clinically_approved = false`
- `calculation_eligibility = BLOCKED`

It must not be used to populate `OWNER_LOCAL` events, the governed precision
threshold, physician approval, or Clinical Engine inputs.

## Scope and method

1. Re-read the exact quote, sentence/paragraph context, target drug, structured
   scalar/unit/frequency, source range, and queue category for all 113 tasks.
2. Classified the source as a daily-total range, per-administration range, or
   incorrect dose anchor using the canonical fidelity taxonomy.
3. Visually rendered and inspected the PDF pages for the cases where flattened
   text was insufficient:
   - `Перелом нижней челюсти.pdf`, pages 24-25;
   - `Кистозный фиброз (муковисцидоз).pdf`, pages 85-86;
   - `Острый ларингит.pdf`, page 16;
   - `Переломы костей голени.pdf`, page 30;
   - `Гонококковая инфекция.pdf`, page 21.
4. Generated the advisory artifact deterministically and verified exact
   113/113 coverage, uniqueness, canonical verdicts, provenance flags, and the
   unconditional calculation block.

This was a source-fidelity audit only. It did not determine whether a source
recommendation is clinically appropriate, current, licensed for the
population, or suitable for an individual patient.

## Results

| AI verdict | Count |
|---|---:|
| `CORRECT_RANGE_SINGLE` | 64 |
| `CORRECT_RANGE_DAILY` | 48 |
| `WRONG_DOSE_ANCHOR` | 1 |
| Total | 113 |

Evidence level:

| Evidence | Count |
|---|---:|
| Direct quote + context | 100 |
| Visual PDF | 3 |
| Visual table | 10 |

## Material finding

`regimen_id=5528` is `WRONG_DOSE_ANCHOR`.

The quote contains:

- ethambutol: `15-20 mg/kg once daily`;
- rifabutin: `5 mg/kg once daily`.

The candidate range `15-20 mg/kg` belongs to ethambutol, not the target
rifabutin regimen. This remains an AI finding until independently reviewed,
but it must not be silently treated as a confirmed rifabutin range.

## Visual-review findings

- `5683` and `7895`: the preceding table header explicitly says
  `Суточные дозы для детей`; ceftriaxone `50-80 mg/kg` is therefore a
  daily-total range.
- Lower-jaw-fracture table tasks: clindamycin `0.6-0.9 g` is an alternative
  prophylaxis dose; the notes column says PAP is administered once, with a
  limited postoperative exception for contaminated surgery.
- `6068`: the apparent `5001-10002 mg` is extraction flattening of superscript
  footnote markers (`500¹-1000² mg`), not a 5,001-10,002 mg dose.
- `5726`: the source distinguishes a pre-operative cefazolin 1.0 g dose from
  0.5-1.0 g intra/post-operative doses every 6-8 hours; the candidate range
  links to the repeated phase.
- `5475`: the PDF genuinely prints ceftriaxone `25-50 mg/kg` and a 125 mg
  maximum. This report confirms only source fidelity and makes no claim about
  clinical correctness of that maximum.

## Artifacts

- `RC030_C7_AI_PRE_REVIEW_EVENTS.json`
- `generated/rc030_c7/build_ai_pre_review.py`
- `tests/rc030_owner_interface/test_c7_ai_pre_review.py`

## Verification

- `python generated/rc030_c7/build_ai_pre_review.py`
  - 113 events;
  - 64 range-single;
  - 48 range-daily;
  - 1 wrong-dose-anchor.
- `python -m pytest tests/rc030_owner_interface tests/dose_verification_sandbox -q`
  - 379 passed.
- `python -m pytest medical_normalizer/tests clinical_engine/tests src/tests -q`
  - 1357 passed, 1 skipped, 1 xfailed, 1 warning.

## Governance effect

No source database was changed. No owner or physician event was created. No
precision threshold was populated. No regimen became calculation-eligible.
The Clinical Engine remains disconnected and P6 remains BLOCKED.
