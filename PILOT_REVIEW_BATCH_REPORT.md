# PILOT_REVIEW_BATCH_REPORT.md
## First Physician-Review Pilot Batch — 20 ClinicalRegimen + 10 TherapeuticOption
## 2026-07-15 · STRICT MODE — nothing approved, no medical data changed

> Selected from the already-built review queue (`review_workbench_p56.sqlite`, 9,153 PENDING
> tasks, 0 approved). Generator: `generate_pilot_review_batch.py` (read-only against the queue,
> new file, does not modify `clinical_engine/review_workbench/` or any regimen/store code).
> 30 deterministic review packets exported to `pilot_review_batch/*.json` +
> `pilot_review_batch/PILOT_BATCH_MANIFEST.json`.

## 1. Priority discrepancy found and resolved explicitly (not silently)
The system's existing default `priority_score` (in `priority.py`, used to order the general 9,153-
task queue) weighs `severe_allergy`/`missing_dose`/`source_mismatch` (45) and `missing_unit`/
`clinical_conflict` (40) **above** `pediatric`/`pregnancy`/`renal` (35) — the **opposite** of the
order requested for this pilot (pediatric > pregnancy > renal > allergy > dose/unit > conflict >
mismatch). I did **not** change the shared `priority.py` weights (that would re-order the entire
9,153-task production queue, well beyond "prepare a pilot batch"). Instead, `generate_pilot_
review_batch.py` implements the requested order as an independent, explicit ranking used only for
this selection — the underlying queue and its default ordering are untouched.

## 2. Two real findings surfaced while building the batch (not hidden)

**Finding A — no task in the entire 9,153-item queue is tagged `severe_allergy`, and only 5 are
tagged `renal`** (confirmed by a full-population query, not a sample). Likely related to RC-023
(kb_p44 atomic Contraindication objects not yet linked into the regimen-assembly/queue-tagging
path). To still produce a genuine allergy/renal-representative pilot, the generator falls back to a
keyword scan (аллерг/почеч/ренал/скф) over the target's own `indication`/`diagnosis`/`therapeutic_
class`/`source_quote` text — same evidence-based method as the P5.4/P5.5 audits, not a guess.

**Finding B (RC-027, registered) — all 30/30 sampled packets came back with `original_source_
wording: [None, ...]`** from the existing `ReviewService.packet()`, even though the target's own
`source_quote` field is populated for all 30. Reproduced the root cause: `packet()` reads
`item.get("original_text"/"source_quote")` off `snapshot["provenance"]` dict entries, which don't
carry those keys — a real defect affecting **all 9,153** queued packets, not just this pilot.
**Registered as RC-027 (High)** in `ROOT_CAUSE_REGISTER.md`; `service.py` itself was **not**
modified (out of scope for "prepare the batch"). For this pilot only, the generator supplements the
exported packet with the real quote from `normalized_object.source_quote` and tags it
`_rc027_note` so reviewers know it was recovered, not fabricated. **This must be fixed in
`service.py` before the other 9,123 queued packets are worked**, or every reviewer will see blank
source wording.

## 3. Selection method
Strict owner priority order, WITH a per-tier cap (`ceil(count / tiers_present)`) so a numerous tier
(496 pediatric-tagged tasks system-wide) cannot exhaust the whole batch and hide rarer-but-still-
top-priority tiers (renal: 5 tagged system-wide, allergy: 0 tagged) — a first run without the cap
produced 20/20 pediatric-only and 10/10 untagged TherapeuticOption tasks, which would not have been
a useful pilot; the capped version is what shipped.

## 4. Batch composition (final)

**ClinicalRegimen (20):** pediatric 4 · pregnancy 4 · renal 3 · severe_allergy 4 (keyword-recovered)
· missing_dose_or_unit 4 · no-tier-match 1 (filled from queue order, no owner-tier signal found).

**TherapeuticOption (10):** pediatric 3 · pregnancy 2 · renal 1 · severe_allergy 2 (keyword-
recovered) · no-tier-match 2. **None** of the 652 TherapeuticOption tasks carry ANY safety_axis tag
system-wide (confirmed, full population) — all 10 selections here rely on the keyword fallback or,
for the 2 "no-tier-match" entries, on the existing queue order alone. This is a second angle on the
same underlying gap as Finding A.

No task in either batch reached the `unresolved_conflict` or `source_mismatch` tiers — expected,
since tiers 1-5 filled every slot before reaching tier 6/7, consistent with the owner's stated
priority order (pediatric/pregnancy/renal/allergy/dose come first).

Full per-task detail (task ID, rank, reason, system score, safety axes, issue type):
`pilot_review_batch/PILOT_BATCH_MANIFEST.json`.

## 5. Packet contents (verified present in all 30)
`task` (full `ClinicalReviewTask` incl. `task_id`/`target_type`/`target_id`/`priority`/
`lifecycle_state`), `normalized_object` (the ClinicalRegimen/TherapeuticOption itself),
`original_source_wording` (recovered per §2 Finding B), `source_references`, `field_level_
provenance`, `detected_conflicts`, `validation_failures`, `decision_options` (`ACCEPT` /
`ACCEPT_WITH_NOTE` / `REJECT_FIDELITY` / `REJECT_CLINICAL` / `NEEDS_INFO` / `ABSTAIN` — matches
`CLINICAL_VALIDATION_FRAMEWORK.md`'s verdict vocabulary exactly), `unsupported_checks` (interaction
checking correctly shown as `"NOT AVAILABLE / UNSATISFIABLE"`, never a fake PASS), `snapshot_hash`.

**One known limitation, disclosed, not silently shipped:** `prior_versions` is an empty list in
every packet — `ReviewService.packet()` does not currently populate version history at all (a
separate, pre-existing gap, not introduced here). Reviewers working these 30 tasks will not see
prior versions even where they might exist; flag for future workbench improvement.

## 6. What was NOT done (per STRICT MODE)
No task was claimed, started, decided, or transitioned. No `ClinicalRegimen`/`TherapeuticOption`
content was altered. `priority.py`'s production weights were not changed. `service.py`'s packet
defect (RC-027) was not fixed in place — only worked around for this batch's 30 exported files.
`approved_objects` remains **0** after this step, as it must — this batch prepares physicians to
review, it does not review or approve anything itself.

## 7. Next step
Hand `pilot_review_batch/` (30 packets + manifest) to Reviewer A / Reviewer B per
`REVIEW_WORKFLOW_RFC.md` — independent, blind review, no self-second-review, adjudicator on
disagreement. Fix RC-027 in `service.py` before extending review beyond this pilot batch.
