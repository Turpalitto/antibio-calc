# PILOT_REVIEW_BATCH_V2_REPORT.md
## Pilot Batch v2 — Production `ReviewService.packet()` + PHYSICIAN_PILOT_V1
## 2026-07-15 · STRICT MODE — nothing approved, no medical data changed

## v1 vs v2 comparison

| Aspect | v1 (`pilot_review_batch/`) | v2 (`pilot_review_batch_v2/`) |
|---|---|---|
| Source wording | Recovered via a **pilot-script-only patch** (`_rc027_note`), bypassing the broken `packet()` | Resolved by the **fixed canonical `packet()`** (`resolve_source_wording`, `service.py`) — no script-level patch of any kind |
| Provenance path | Ad hoc, duplicated ranking logic in `generate_pilot_review_batch.py` | Named, versioned policy module (`clinical_engine/review_workbench/pilot_policy.py`, `PHYSICIAN_PILOT_V1`) — reusable, not duplicated |
| Signal origin labelling | Not distinguished (STORED vs keyword-derived conflated) | Explicit `STORED` / `DERIVED_REVIEW_SIGNAL` / `NONE` on every selection |
| `review_blocked` field | Did not exist | Present on every packet; **0/30 blocked** |
| `source_wording_status` field | Did not exist | Present on every packet; **30/30 `AVAILABLE`** |
| Batch composition | pediatric 4 / pregnancy 4 / renal 3 / severe_allergy 4 / missing_dose_or_unit 4 / no-match 1 (ClinicalRegimen); pediatric 3 / pregnancy 2 / renal 1 / severe_allergy 2 / no-match 2 (TherapeuticOption) | **Identical** (deterministic — same policy, same data) |
| Task IDs selected | 30 tasks | **24/30 identical to v1; 6 differ** (checked empirically, not assumed — see below) |

**Correction (checked, not assumed):** an earlier draft of this report claimed v1 and v2 select
"the exact same 30 tasks." That claim was **verified false** by diffing the two manifests directly:
24 of 30 task IDs match; 6 differ (all within the tier-1/tier-2 ranks, where multiple candidate
tasks tie on `(tier, match-count, priority_score)` and the tie-break falls to `task_id` string
comparison). v1's script and v2's `pilot_policy.py` compute an equivalent but not byte-identical
tie-break tuple, so a *different* task within the same tied group can win the tier cap in each
version. **Neither selection is wrong** — both are valid, deterministic, tier-correct picks — but
they are not identical, and the report is corrected to say so rather than repeat an unverified claim.

## Full-field verification (Phase 4/8 requirement — not "100% because a fallback string exists")
All 30 v2 packets contain every required field (`task`, `normalized_object`,
`original_source_wording`, `source_wording_status`, `review_blocked`, `source_references`,
`field_level_provenance`, `prior_versions`, `detected_conflicts`, `validation_failures`,
`decision_options`, `unsupported_checks`, `snapshot_hash`) — 0 missing-field incidents across 30
files. `decision_options` matches `CLINICAL_VALIDATION_FRAMEWORK.md`'s verdict vocabulary exactly
(`ACCEPT`/`ACCEPT_WITH_NOTE`/`REJECT_FIDELITY`/`REJECT_CLINICAL`/`NEEDS_INFO`/`ABSTAIN`).
`unsupported_checks.drug_interactions` correctly shows `"NOT AVAILABLE / UNSATISFIABLE"` on all 30 —
never a fake PASS. Text-match spot-checks (§RC027_ROOT_CAUSE_REPORT.md manual verification) already
confirmed the resolved wording is byte-identical to the target's real `source_quote`, not a
placeholder.

## Known, disclosed limitation (unchanged from v1, not hidden)
`prior_versions` remains an empty list in every packet — `ReviewService.packet()` does not populate
version history yet (a separate, pre-existing gap; not RC-027, not fixed here). Reviewers will not
see prior versions in this pilot even where they might exist.

## Signal origin breakdown (new in v2 — the honest labelling Phase 6 required)
**ClinicalRegimen (20):** 9 STORED, 10 DERIVED_REVIEW_SIGNAL, 1 NONE (no tier match, filled by
queue order). **TherapeuticOption (10):** 0 STORED, 8 DERIVED_REVIEW_SIGNAL, 2 NONE — consistent
with RC-028 (no TherapeuticOption task carries any stored safety tag at all; every non-trivial match
here came from the keyword fallback, not from queue-builder tagging).
