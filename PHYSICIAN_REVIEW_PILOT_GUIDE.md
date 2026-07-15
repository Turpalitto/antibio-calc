# PHYSICIAN_REVIEW_PILOT_GUIDE.md
## Instructions for Reviewer A and Reviewer B — Pilot Batch
## P5.6 RC-027 Phase 9 · 2026-07-15

## Purpose of this pilot
30 packets (20 `ClinicalRegimen`, 10 `TherapeuticOption`), selected by `PHYSICIAN_PILOT_V1`
(`PHYSICIAN_PILOT_POLICY.md`) to prioritize pediatric, pregnancy, renal, and severe-allergy cases
first. This is the FIRST real clinical decision made in ANTIBIO's Review Workbench —
`approved_objects = 0` today; your decisions are what change that number, one task at a time, never
automatically.

## What you MAY do
- Read the packet (`pilot_review_batch_v2/<task_id>.json`), verify the `normalized_object` against
  `original_source_wording` and the cited PDF/page.
- Record ONE verdict per review round using the fixed vocabulary (§Decision vocabulary below).
- Add a governed note/comment explaining your reasoning.
- Mark a task `NEEDS_INFO` or `ABSTAIN` when appropriate (§below).

## What you may NOT do
- You may **not** edit the underlying `ClinicalRegimen`/`TherapeuticOption` medical content directly
  — the workbench never exposes a "fix the dose" action; a factual correction requires a NEW,
  provenance-backed version through the assembly pipeline, not a reviewer edit.
- You may **not** self-second-review your own first review (Reviewer A and Reviewer B must be two
  different people, verdicts formed independently and blind to each other's — per
  `REVIEW_WORKFLOW_RFC.md`).
- You may **not** approve a task whose packet shows `review_blocked: true` or
  `source_wording_status: "MISSING"` — there is nothing to verify against, so it cannot be approved
  (mark `NEEDS_INFO` instead). All 30 v2 pilot packets currently show `review_blocked: false`, so
  this should not arise in this specific pilot, but the rule stands for any future batch.
- You may **not** treat a `DERIVED_REVIEW_SIGNAL` tag (visible in the manifest, e.g. "flagged
  pediatric via keyword match") as a clinical fact — it explains why the task was shown to you
  first, not a verified clinical property. Form your own judgment from the packet content.

## Decision vocabulary (exact, do not improvise)
`ACCEPT` · `ACCEPT_WITH_NOTE` · `REJECT_FIDELITY` · `REJECT_CLINICAL` · `NEEDS_INFO` · `ABSTAIN`
(identical to `CLINICAL_VALIDATION_FRAMEWORK.md` §2.3 — the same vocabulary governs this pilot).

### Fidelity rejection vs. clinical rejection — the distinction that matters most
- **`REJECT_FIDELITY`** — the normalized object does **not accurately represent** the source text.
  Example: the packet says "500 mg every 8 hours" but the cited `original_source_wording` actually
  says "500 mg every 12 hours." This is an extraction/normalization error, not a medical judgment.
- **`REJECT_CLINICAL`** — the normalized object **faithfully** represents the source, but the
  source itself, as extracted, is clinically unsafe or wrong as surfaced (e.g., missing a
  necessary caveat, wrong population match). This may indicate a genuine guideline-interpretation
  problem — escalate via comments, do not silently accept or silently reject without explanation.

### NEEDS_INFO
Use when you cannot form a verdict because something is missing or ambiguous in the packet itself
(e.g., the cited page doesn't seem to contain the claimed passage, or `field_level_provenance` is
too sparse to verify a specific field). This routes the task back toward the data/extraction side,
not toward more review — more reviewing cannot fix a data gap.

### ABSTAIN
Use when the case is outside your specialty. Do not guess at clinical judgment beyond your
competence — the Medical QA Lead reassigns abstained tasks to a matching specialist.

## Disagreement handling & adjudication
Reviewer A and Reviewer B review independently, blind to each other's verdict. If your verdicts
disagree (e.g., one `ACCEPT`, one `REJECT_CLINICAL`), the task routes to an Adjudicator — a third,
senior clinician, never A or B themselves. The Adjudicator's ruling is final for that task; there is
no further escalation tier. Document your reasoning clearly enough that an adjudicator (who was not
part of your discussion) can understand your position from the record alone.

## Expected review time
Not measured yet for this specific pilot (no prior physician-review sessions exist to benchmark
against in this project). Do not rush a first-pass estimate — record your own actual time per task
during this pilot; that measurement becomes the baseline for future batches, not an assumption made
here.

## Data privacy
These are guideline-derived clinical *regimens* and *therapeutic options* — general treatment
recommendations, not patient records. No patient-identifying data is present in any packet. Standard
handling of clinical-reference material applies; no additional PHI/PII precautions are needed for
this specific data type, but do not paste packet contents into external, non-approved tools.

## How to verify the PDF/page
Every packet's `source_references` includes `pdf` (filename) and `page`. Locate the source PDF in
the corpus directory, open the cited page, and compare its text against `original_source_wording`.
For table-derived facts, `field_level_provenance` may include `table_row`/`table_col` — use these to
locate the specific cell, not just the page.

## How to report a source mismatch
If the cited PDF/page does not contain the wording shown in `original_source_wording`, or the
wording is present but attributed to the wrong drug/regimen, this is exactly the scenario
`REJECT_FIDELITY` exists for — record it with that verdict and describe the specific discrepancy in
your comments (what the packet claims vs. what the source actually says). This is also useful signal
for RC-025 (a related, previously-registered finding about `source_quote`/`drug_original`
misalignment in a small number of records).

## Prohibition on approval without source verification
**No task may be marked `ACCEPT` or `ACCEPT_WITH_NOTE` without you having actually read the cited
source page and confirmed the wording matches.** A packet with plausible-looking normalized content
is not sufficient grounds for approval on its own — the entire point of this workbench is that every
approval is traceable to, and verified against, a specific source passage.

## Who reviews this guide
Reviewer A, Reviewer B, and the Medical QA Lead assigning the pilot. This document does not
pre-fill or suggest any medical decision for any of the 30 pilot tasks — it is process guidance
only.
