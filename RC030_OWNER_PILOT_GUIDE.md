# RC-030 Owner Fidelity Pilot — Guide

## What this is

A 60-record pilot queue (`RC030_OWNER_PILOT_QUEUE.json`) and an offline review interface (`generated/rc030_recovery/RC030_OWNER_REVIEW_INTERFACE.html`) for the repository owner to check whether the RC-030 parser's reading of a dose expression matches the actual PDF wording. This is **source-fidelity review**, not physician approval — see the banner in the interface itself.

## How to open it

The file is static HTML with the 60 records' data embedded directly (no server, no network calls, no build step). Two ways to open it:
1. Double-click `generated\rc030_recovery\RC030_OWNER_REVIEW_INTERFACE.html` in Explorer (opens via `file://` in your default browser), or
2. `python -m http.server` from `generated/rc030_recovery/` and open `http://localhost:<port>/RC030_OWNER_REVIEW_INTERFACE.html` if your browser restricts `file://` JavaScript.

## Queue composition (60 records, all with a locally-available source PDF)

- 15 apparent `WEIGHT_PER_DAY`
- 15 apparent `WEIGHT_PER_DOSE`
- 10 `FIXED_PER_DAY`
- 10 `FIXED_PER_DOSE`
- 5 `AMBIGUOUS` controls (parser already says "I don't know" — check whether that's the right call)
- 5 table/source-recovery cases (drawn from the pages already processed in the Phase 1–3 multi-engine pilot — `Отит средний острый.pdf` p.23, `Паратонзиллярный абсцесс.pdf` p.22, `Лепра [болезнь Гансена].pdf` p.32 — genuine tables were confirmed present there)

Selection favored short, single-antibiotic source quotes (no "или" alternatives, ≤2 bolded drug names) so the first pass is fast — harder multi-alternative/table cases are intentionally deferred past this first 60.

## How to review a record

1. Read the **source quote** — this is verbatim `source_quote` from the database, not anything reconstructed.
2. Compare it against the **normalized** fields (what the pipeline extracted) and the **semantics** panel (what the RC-030 parser concluded, and why — see `Rule fragment`).
3. Pick the verdict that matches what the *source text* actually says, not what you'd expect clinically. If the source doesn't clearly state per-day vs. per-dose, that's `REMAINS_AMBIGUOUS`, not a guess.
4. Any `SOURCE_CONFIRMS_*`/`TABLE_HEADER_CONFIRMS_*` verdict requires a short note — quote or paraphrase the exact phrase that supports it.
5. Click "Record verdict" and move to the next record. Verdicts are append-only in this browser tab's local storage (key `rc030_owner_fidelity_dryrun_v1`) — nothing is sent anywhere.

## What happens to your verdicts

Nothing, automatically. Use "Export all verdicts as JSON" when you're done with a batch to get a file a human (or a future turn of this pilot) can read and turn into precision numbers (`RC030_PRECISION_CALCULATOR` — see `RC030_TARGETED_RECOVERY_AND_OWNER_PILOT_REPORT.md` Phase 9 for the deterministic calculation method, not yet run against real verdicts since none exist yet).

## What this cannot do

- Cannot approve anything clinically.
- Cannot change `calculation_eligibility` for any regimen.
- Cannot write to `review_workbench_p56.sqlite` or `assembled_regimens.sqlite`.
- Is not wired to the Clinical Engine in any way.

Verified in this turn's dry run (`RC030_TARGETED_RECOVERY_AND_OWNER_PILOT_REPORT.md`): verdict field starts empty every time, submission is append-only, empty-note validation blocks confirming verdicts without a source-backed note, and the only network request the page makes is its own initial load — no submission traffic of any kind.
