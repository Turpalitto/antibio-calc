# RC-030 / C7 Owner Review — Launch Guide

Read this before reviewing. Nothing here approves any dosing regimen for clinical use. Every verdict you record stays local to your browser until you export it and hand it back for governed processing — it never auto-submits anywhere, ever.

## 1. Build the batches (already done, rebuild only if you change source data)

```
uv run python generated/rc030_c7/build_master_registry.py
uv run python generated/rc030_c7/build_batches.py
uv run python generated/rc030_c7/build_c5_datasets.py
```

## 2. Start a local static server

From the repository root:

```
python -m http.server 8977 --directory generated/rc030_c7_owner_review
```

(Windows PowerShell equivalent is identical — `python` resolves the same way.)

## 3. Open a batch interface

In your browser, go to:

```
http://localhost:8977/c7_batch_01_exact.html
```

Batch files (in priority order — do batch_01 through batch_03 first):

- `c7_batch_01_exact.html`, `c7_batch_02_exact.html`, `c7_batch_03_exact.html` — 12+12+12 exact-link confirmations
- `c7_batch_04_engine_disagreement.html` — 11 engine/independent-audit disagreements
- `c7_batch_05_unit_basis.html` through `c7_batch_08_unit_basis.html` — 43 dose-basis-ambiguous records (12/12/12/7)
- `c7_batch_09_table_review.html` — 8 table-derived records
- `c7_batch_10_single_candidate.html`, `c7_batch_11_single_candidate.html` — 15 general single-candidates (12/3)

## 4. Configure your local PDF root

First use of "Open source PDF page" will ask you to set your local PDF folder (the directory containing the RC-030 source PDFs — e.g. `C:\clinrec_downloader`). This is stored only in your browser's `localStorage`, never written into any file in this repository.

## 5. Review records

Read the source quote and context. Select the verdict that matches what the source actually says — not what you'd clinically expect. A note is required for every verdict (explain the source-based reason, not a general clinical opinion). The parser's guess and any AI proposal stay hidden until after you submit.

Keyboard shortcuts: `←`/`→` = previous/next record, `Ctrl+Enter` = record verdict.

## 6. Export JSON after each batch

Click "Export events as JSON". The file downloads as `rc030_owner_review_c5_<mode>_export.json`. **Do this after finishing each batch, not just at the end** — your browser's local storage could be cleared by browser settings changes, and an export is your only durable copy until it's processed.

## 7. Preserve original exports

Save every exported file outside this repository (e.g. a personal backup folder). Keep the original bytes untouched — never edit an export file by hand.

## 8. Do not manually edit export JSON

If you made a mistake, go back into the interface and record a **new** verdict for that record (it becomes a superseding event, the old one is preserved, not overwritten) — then export again. Never hand-edit a downloaded JSON file.

## 9. Validate your export

Before handing an export back for processing, you (or the assistant, with your export file explicitly provided) can validate it:

```
uv run python -c "
import json
from dose_verification_sandbox.owner_fidelity_events import validate_events
events = json.load(open('YOUR_EXPORT_FILE.json'))
known = json.load(open('generated/rc030_c7/review_tasks_ready.json'))['tasks']
known_fmt = [{'regimen_id': t['regimen_id'], 'regimen_version': t['regimen_version'],
              'evidence_hash': t['unit_id'], 'pdf_hash': t['PDF_hash']} for t in known]
print(validate_events(events, known_fmt))
"
```

## 10. Submit for governed processing

Once you've exported and validated a batch, hand the export file to the assistant for Stage B processing (Part IX onward) — intake, consolidation, and precision measurement. **The assistant will never generate these events on your behalf; only your own deliberate action in the interface produces a genuine `OWNER_LOCAL` event.**

---

## Backup policy (Phase 21)

Before beginning genuine review: if you have any prior localStorage owner events from earlier testing, export them first and save outside the repository. Retain read-only originals. Never overwrite an earlier export — use a new file per batch/session. Corrections during review always create superseding events (append-only); they never require you to re-export and discard a previous file.

## Export filename convention (Phase 20)

Suggested: `rc030_c7_<batch_id>_owner_events_<UTC-date>.json` (e.g. `rc030_c7_batch_01_exact_owner_events_2026-07-19.json`). Your browser may append its own timestamp to the downloaded filename — that's fine; only the event *content* must stay stable (aside from legitimate event timestamps/IDs generated at submission time).

## Safety reminders

- Nothing you do in the interface changes `calculation_eligibility`, writes to any real database, or connects to any network.
- No verdict is ever pre-selected for you.
- The parser's and any AI's proposal are hidden until **after** you submit your own independent verdict.
- This is source-fidelity review only — "does the parser correctly report what the PDF says" — not a clinical-appropriateness judgment.
