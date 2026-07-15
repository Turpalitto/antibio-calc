# DOSE_VERIFICATION_USER_GUIDE.md

QA / RESEARCH ONLY — NOT CLINICALLY APPROVED — DO NOT USE FOR PATIENT CARE

## What this is

A local tool to check whether ANTIBIO's source-derived dose data can be safely turned into a number,
and whether the arithmetic is correct when it can. It is not a calculator you give to a patient or a
prescriber. Every screen says so.

## Running it

1. Export a fresh snapshot (read-only against `assembled_regimens.sqlite`):
   ```
   python -m dose_verification_sandbox.snapshot
   ```
   Writes `dose_verification_sandbox/data/snapshot_latest.json`.

2. Open `dose_verification_sandbox/ui/dose_verification_sandbox.html` in a browser. Two ways:
   - Directly via `file://` (some browsers restrict local file access for the file picker's
     FileReader — this generally still works since no `fetch()` is used).
   - Or serve locally for convenience: `python -m http.server 8791` from inside
     `dose_verification_sandbox/`, then open `http://127.0.0.1:8791/ui/dose_verification_sandbox.html`.
   This is a static file served locally for your own inspection — not a deployed production endpoint.

3. Click "Snapshot JSON" and pick `data/snapshot_latest.json`.

4. Select a diagnosis (MKB/ICD code), then an antibiotic. All regimen variants for that pair are
   listed — including `REJECTED` ones — nothing is hidden or merged.

5. Click a regimen row to select it. Its source dose, unit, frequency, provenance (PDF + page +
   quote), and approval state are shown.

6. Enter age and weight, click Calculate. The trace panel shows every arithmetic step. If the source
   data is ambiguous (most real regimens today — see below), you'll see `BLOCKED` with an explicit
   reason instead of a number.

7. Optionally enter your own independently-calculated expected values under "Owner comparison",
   classify the discrepancy, and click "Download defect report (JSON)" to save a
   `DoseCalculationIssue` record to your own disk.

## What "BLOCKED" means, and why you will see it a lot

`assembled_regimens.sqlite` stores dose as a number + a unit string (e.g. `dose=50, unit="mg/kg"`),
but has no column saying whether that 50 mg/kg is the *total daily* amount or the amount for *one
administration*. The sandbox will not guess. If the unit string doesn't explicitly say "per day" or
"per dose", the calculation blocks and tells you why (`AMBIGUOUS_PERIOD`). In the Phase 15 pilot, all
12 real cases sampled hit this or a similar block — this is the sandbox doing its job, not a bug.

## What "NOT_AVAILABLE" means for max_dose / rounding / formulation_conversion

The source data has no maximum-dose columns and no formulation/concentration columns at all. These
verdicts will read `NOT_AVAILABLE` on essentially every real regimen until that data is added
upstream (or a new, more complete data source is used).

## Reading the verdict panel

Eight independent checks: `source_fidelity`, `parsing`, `arithmetic`, `unit_consistency`,
`max_dose`, `rounding`, `formulation_conversion`, `clinical_approval`. `clinical_approval` will
always read `NOT_APPROVED` — this cannot be changed by anything in this tool, by design. A `PASS` on
`arithmetic` means the math is correct given the source numbers; it says nothing about whether the
source numbers themselves are clinically correct.

## What to do with a finding

Any `BLOCKED`/`FAIL`/mismatch you record is a QA finding, not a physician decision. It belongs in
`data/issues.json` (via the UI's download button, or `dose_verification_sandbox.issues.record_issue`
from Python) and, once confirmed, should be escalated to `ROOT_CAUSE_REGISTER.md` for prioritization
against the rest of the backlog.
