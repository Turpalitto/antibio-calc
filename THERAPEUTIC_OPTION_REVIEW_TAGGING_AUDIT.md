# THERAPEUTIC_OPTION_REVIEW_TAGGING_AUDIT.md
## Why All 652 TherapeuticOption Tasks Have Empty safety_axes and Flat Priority
## P5.6 RC-027 Phase 7 · 2026-07-15 · Investigation only — no fix applied here

## Confirmed, measured (full population, not a sample)
```
TherapeuticOption pending tasks: 652/652
issue_type distribution:  {'THERAPEUTIC_OPTION_VALIDATION': 652}   (uniform, no differentiation)
safety_axes distribution: {}                                        (empty for all 652)
priority band distribution: {'MEDIUM': 652}                        (flat, uniform score=40)
```

## Root cause, traced to the exact producer line
`clinical_engine/review_workbench/queue_builder.py`, the `TherapeuticOption` ingestion loop:
```python
for option in migration.therapeutic_options:
    ...
    builder.add(
        target_type=TargetType.THERAPEUTIC_OPTION, target_id=option.option_id, ...,
        issue_type="THERAPEUTIC_OPTION_VALIDATION", severity=Severity.MEDIUM,
        safety_axes=[], reasons=["missing_metadata"],
    )
```
**`safety_axes=[]` and `reasons=["missing_metadata"]` are hardcoded literals** — every
`TherapeuticOption` is unconditionally tagged the same way, regardless of its actual clinical
content. Contrast with the `ClinicalRegimen` loop immediately above it, which calls
`_regimen_axes(regimen)` to compute REAL axes per regimen (pediatric/pregnancy/renal detection
logic exists and runs for `ClinicalRegimen` — see `queue_builder.py:73-91`). **No equivalent
`_option_axes(option)` function was ever written for `TherapeuticOption`.**

## Which of the mandate's candidate causes is confirmed
| Candidate cause | Confirmed? | Evidence |
|---|:---:|---|
| Source model lacks fields | **No** | `TherapeuticOption` (`clinical_engine/regimen/therapeutic_option.py`) has `indication`, `diagnosis`-adjacent context via `origin_regimen_id`, and free text in `indication`/`therapeutic_class`/`source_quote` — the same kind of text `_regimen_axes()` scans for `ClinicalRegimen`. The data needed to compute real axes is present on the object. |
| Migration dropped fields | **No** | `class_level_migration.py`'s `_to_option()` (P5.5) correctly carries `indication`, `therapeutic_class`, `source_quote`, `contraindications` from the origin `ClinicalRegimen` reject candidate — nothing is dropped between assembly and the `TherapeuticOption` object itself. |
| **Queue builder ignores fields** | **YES — confirmed root cause** | The `TherapeuticOption` ingestion call passes literal `safety_axes=[]` — it never reads `option.indication`/`option.therapeutic_class`/`option.source_quote` at all, unlike the parallel `ClinicalRegimen` path three lines above it in the same file, which does exactly this analysis via `_regimen_axes()`. |
| Indication text contains unstructured signals | Partially relevant, not the root cause | True that the signal (pediatric/pregnancy/renal keywords) lives in free text, same as for `ClinicalRegimen` — but `ClinicalRegimen` already has working keyword-based axis detection (`_regimen_axes`) proving this is solvable with the existing text; it was simply never extended to `TherapeuticOption`. |
| Current model cannot represent safety axes | **No** | `ClinicalReviewTask.safety_axes` is a generic `tuple[str, ...]` field on the TASK, not the target object — it is target-type-agnostic. Nothing about `TherapeuticOption`'s shape prevents populating it; the ingestion code simply never tries. |

## Precise conclusion
**This is a queue-builder omission, not a modeling or migration defect.** A function structurally
identical to `_regimen_axes(regimen)` was never written for `TherapeuticOption`, so every one of
its 652 tasks is ingested with the same placeholder tag regardless of whether its `indication`
mentions "детям", "беременность", "почечная недостаточность", etc.

## Root Cause Register entry
Registered as **RC-028** (new, separate from RC-027 — this is a queue-builder tagging gap, not a
packet-provenance mapping bug; per the Phase 7 instruction, **not fixed here**):
> `TherapeuticOption` ingestion in `queue_builder.py` hardcodes `safety_axes=[]`/
> `reasons=["missing_metadata"]` for all 652 tasks instead of computing real axes from the object's
> own `indication`/`therapeutic_class`/`source_quote` text, unlike the parallel, working
> `ClinicalRegimen` path (`_regimen_axes()`) three lines above it in the same function. All 652
> TherapeuticOption tasks carry a flat, uninformative priority (MEDIUM/40) and no safety tagging.

## Why not fixed in this task
Per the Phase 7 instruction ("Do not fix it unless it is a direct part of RC-027") and per this
project's Root Cause Program discipline (classify first, rank, fix in a separate, deliberate pass —
not opportunistically mid-task): this is registered, not patched. `PHYSICIAN_PILOT_V1`'s
`DERIVED_REVIEW_SIGNAL` keyword fallback (Phase 6) already compensates for pilot-selection purposes
without needing this fix first — the pilot batch can proceed once RC-027 (packet provenance) is
resolved. RC-028's fix (writing a real `_option_axes()` analogous to `_regimen_axes()`) would
directly improve queue-wide prioritization for all 652 `TherapeuticOption` tasks and should be
ranked in the Root Cause Register's next benefit/effort pass.
