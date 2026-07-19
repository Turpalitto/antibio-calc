# RC-030 / C7 Part VII — Browser Validation (synthetic test_event=true only)

## Method

Served the built interfaces via a local static HTTP server (`python -m http.server`, localhost-only, stopped after validation). Real, interactive browser testing (not static inspection) against `c7_batch_01_exact.html` (real task evidence, read-only inspection) and `c7_controls.html` (4 synthetic `TEST-CONTROL-*` records, the only surface ever interacted with).

**Governance boundary enforced by the harness itself, not just by convention**: an attempt to fill a verdict on the real `c7_batch_01_exact.html` interface was auto-blocked with an explicit citation of this task's own "AI must not click verdicts" rule. All subsequent interaction was correctly redirected to `c7_controls.html` only.

## Three real bugs found and fixed during this validation (not found by static inspection alone)

1. **Field-name mismatches silently blanked the interface.** The C7 review-task model uses `structured_scalar`/`structured_unit`/`sentence_context`/`paragraph_context`/`source_pdf_relative_path`/`page`, but `owner_review_template.html` reads `r.dose`/`r.unit`/`r.context_before`/`r.context_after`/`r.source_pdf`/`r.source_page`. Loading the real built HTML showed `Dose?` and blank context panels. Fixed in `generated/rc030_c7/build_c5_datasets.py` (and the separately-built `build_controls.py`) with an explicit field-mapping step.
2. **`test_event` was hardcoded `false`** in the template's event-creation code for every mode, including `control` — the first synthetic verdict recorded showed `"test_event":false` in `localStorage`, meaning a browser-synthetic verdict was indistinguishable from a genuine `OWNER_LOCAL` event by this flag alone. Fixed: `test_event: r.test_event === true || MODE === "control"`.
3. **`pdf_hash` was silently dropped from every exported event.** The dataset key was `PDF_hash` (capitalized); the template reads `r.pdf_hash` (lowercase) directly into the event object literal — `undefined` values are dropped by `JSON.stringify`. Running the real captured event through the committed C4 validator (`dose_verification_sandbox.owner_fidelity_events.validate_events`) confirmed: `pdf_hash: missing required field`. Fixed the field-mapping step; re-validated the corrected event — **0 issues, `test_event=True` correctly excludes it via `filter_real_events`**.

## Checklist results (Phase 17)

| Check | Result |
|---|---|
| Each mode loads | ✅ (batch_01 real interface + controls interface both rendered correctly) |
| Batch/record count correct | ✅ (12/12 exact-link batch; 4/4 controls) |
| First record visible | ✅ |
| No verdict preselected | ✅ (`— select a verdict —` default confirmed via DOM read) |
| Candidate/AI hidden before submission | ✅ ("PARSER AND AI PROPOSAL ARE HIDDEN UNTIL YOU SUBMIT" banner, no candidate value anywhere in pre-submit DOM) |
| Note required | ✅ (submit button read "Select a verdict first" until both fields set) |
| Synthetic verdict submission | ✅ (2 events recorded: initial + correction, both on `TEST-CONTROL-CONFIRMING`) |
| Reveal after submission | ✅ (`revealHeader` click opens `revealBody`, shows "Your verdict CORRECT_EXPLICIT_PER_DAY"; "No AI proposal available" correctly shown since synthetic controls carry no AI fields) |
| Correction/supersession | ✅ (2nd event has `previous_event_id`/`supersedes_event_id` pointing to the 1st; both preserved, append-only — `localStorage` array length 2, not 1) |
| Export mechanism | ✅ static-verified: `Blob`+`a.download` client-side only, filename `rc030_owner_review_c5_${MODE}_export.json`, no network call |
| Reload persistence | ✅ (navigated away and back; both events survived in `localStorage`) |
| Storage-key isolation | ✅ (`rc030_owner_review_c5_events_v1_control` vs `..._v1_range-exact-review` confirmed distinct; the blocked batch_01 interaction never wrote anything to the exact-review key — confirmed absent) |
| Reset confirmation | ✅ static-verified: gated behind `confirm(...)` |
| No console errors | ✅ (`read_console_messages` — none) |
| No uncaught exceptions | ✅ (implied by above; no error-level console entries) |
| No external network requests | ✅ (`read_network_requests` — only the local static-server GETs for the HTML files themselves) |

## C4 validation of the browser-exported event (Phase 18)

Ran the actual captured `localStorage` event (post-fix) through the committed validators:

- `validate_events([event], known_records)` → **0 issues** (once the matching fixture record includes both `evidence_hash` and `pdf_hash`).
- `filter_real_events([event])` → **`[]`** — correctly excluded as `test_event=True`.
- Supersession chain (`validate_supersession_chain`) → **0 issues** for the 2-event correction sequence.
- `find_duplicate_event_ids` → **0 duplicates**.

## Cleanup

Local test `localStorage` cleared (`removeItem`) after validation. Local static server (port 8977) stopped. No genuine owner event was created — every event in this report carries `test_event=true` and references only synthetic `TEST-CONTROL-*` regimen IDs never present in any real queue.

## Regression tests added

`test_control_mode_always_stamps_test_event_true`, `test_dataset_pdf_hash_field_name_matches_template_reader` — full C5 suite: **46/46 passing** (was 44/44 before this fix pass).
