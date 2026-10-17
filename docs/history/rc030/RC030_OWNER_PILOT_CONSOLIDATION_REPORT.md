# RC-030 Owner Pilot Consolidation — Final Report

Executed 2026-07-16 on HEAD `394818675b0ed199e03cae1d89e38a488f5102ce`. Nothing staged, nothing committed, nothing pushed.

## 1. Verdict taxonomy selected

**Canonical = `validation_unit.HUMAN_FIDELITY_VERDICTS`** (matches the owner's specified 17-value list exactly). `dose_verification_sandbox/verdict_taxonomy.py` implements the deterministic UI-action→canonical mapping with a module-load-time completeness assertion. See `RC030_VERDICT_TAXONOMY_DECISION.md`.

**Bug found and fixed during this reconciliation**: `precision_calculator.py` (built last turn) was still bucketing verdicts by the UI-action vocabulary rather than the canonical one — a raw `SOURCE_CONFIRMS_PER_DAY` string would have silently counted as 0 correct instead of being recognized. Fixed, with a regression test (`test_precision_calculator_consumes_canonical_verdicts_not_ui_actions`) and a matching completeness assertion mirroring the taxonomy module's.

## 2. Interface migration result

`generated/rc030_recovery/RC030_OWNER_REVIEW_INTERFACE.html` rebuilt (v2): events now carry `event_id`, `event_version`, `regimen_version`, `source_packet_hash`, `pdf_hash`, `parser_version`, `interface_version`, `previous_event_id`/`supersedes_event_id`, `test_event`. Export preview panel added. Import-validation panel added (paste exported JSON, checks schema version / evidence hash / regimen version / PDF hash / required-note rules without loading it into the live session). Dry-run verified live in browser: verdict never prefilled, canonical mapping correct (`SOURCE_CONFIRMS_PER_DAY` → `CORRECT_EXPLICIT_PER_DAY`), append-only, own export validates as `VALID`, tampered PDF hash correctly `REJECTED`, stale schema version correctly `REJECTED`, zero network requests beyond the initial page load, all test data cleared afterward.

## 3. Table clipped-text result

**Implemented and successful on all 3 tested pages** (`RC030_TABLE_CLIPPED_TEXT_RECOVERY_REPORT.md`): Table Transformer bbox → PDF-point conversion → `page.get_text(clip=...)` recovered 100% correct Cyrillic text, generated from coordinates, not typed. Recovered the джозамицин pediatric row (Отит, 40-50 мг/кг/сутки) completely and correctly, and independently cross-validated the regimen-5660 range finding from a second page (Паратонзиллярный, "20-50 мг/кг массы тела").

## 4. Cyrillic corruption comparison

`RC030_CYRILLIC_TABLE_TEXT_COMPARISON.md`: **`EMBEDDED_TEXT_PREFERRED` for all 3 pages.** MinerU's batch-mode OCR of the Отит table **dropped the drug name and dose unit entirely** for the джозамицин row (not just corrupted — absent); RapidTable corrupted individual Cyrillic characters (к→κ, т→τ, etc.) on the same table. Neither OCR path outperformed embedded-text extraction on any page checked.

## 5. Exact range-loss stage

**Pinned to one line of code** (`RC030_RANGE_LOSS_STAGE_RCA.md`): `medical_normalizer/drug_parser.py:139`, `DoseNormalizer.parse()` — the regex has a second capture group for a range's upper bound, but the code only reads `match.group(1)`. Directly reproduced (`"20-50"` → `dose_value=20.0`) matching real database values for regimens 5660/5671/5683 exactly. Confirmed **Stage C (normalization)**, not Stage D (assembly is a verbatim passthrough — traced 20/20 sample rows) and not Stage A/E. Regression test added.

## 6. Range schema recommendation

`RC030_ADDITIVE_RANGE_SCHEMA_PROPOSAL.md` — additive `dose_min`/`dose_max`/`dose_is_range`/etc. fields, sandbox-owned (not touching `assembled_regimens.sqlite`), with explicit rules distinguishing ranges from alternatives, max-dose clauses, and loading/maintenance pairs. Design only, not activated.

## 7. Max-dose queue size

**20 records** (`RC030_MAX_DOSE_OWNER_QUEUE.json`, guide at `RC030_MAX_DOSE_OWNER_GUIDE.md`), covering pediatric/adult, alternatives, range-near-max risk (the specific risk flagged by §5/§6 above), and multi-numeric-anchor cases. Not reviewed. Not wired into the owner-review interface (max-dose-specific verdicts are a follow-up).

## 8. PDF coverage

**Corrected, significant finding** (`RC030_PDF_COVERAGE_GAP_REPORT.md`): prior turn's "65% coverage" was an artifact of searching only `downloads_active`. Searching the full approved storage tree (`downloads_active`, `downloads_all`, `downloads_antibiotics`, `downloads_other`, `archive_no_antibiotics`, `archive_review`, `quarantine`) finds **193/193 (100%) available, 0 hash mismatches**. Full detail: `RC030_MISSING_PDF_MANIFEST.json`.

## 9. Owner event schema

`dose_verification_sandbox/owner_fidelity_event_schema.json` (formal JSON Schema) + `dose_verification_sandbox/owner_fidelity_events.py` (deterministic Python validator, mirrors the interface's JS-side validator). 11 tests covering missing fields, stale regimen version, PDF-hash mismatch, unknown source-packet hash, unsupported schema version, missing note on confirming verdicts, and — critically — `filter_real_events()` excluding `test_event: true` **and** fail-closed-defaulting any event that's missing the `test_event` flag entirely to "test" (never silently counted as real).

## 10. Precision dry-run

Run against synthetic-only events (`test_precision_dry_run_empty_real_store_produces_no_claim`, `test_precision_dry_run_never_activates_a_semantic_type`): empty real-event store → no precision claim (`precision=None`); `TYPES_MEETING_PRECISION_THRESHOLD` untouched by any dry-run computation. No real precision has been computed or published — none can be, since real owner-verdict count is 0.

## 11. Real owner verdict count

**0.**

## 12. QA-calculable count

**0 / 2,675** (live re-derivation, this turn).

## 13. Clinically approved count

**0.**

## 14. Source DB hashes

`assembled_regimens.sqlite` = `9f505d08428cd2841983d3c8881c15e0813ada4a9056dea360a357a0f3eebcd9`; `normalized_regimens.sqlite` = `c7b67354b0723ad538a185e561ed94d09b11c019279be9c4c6412c4f1eaa4237` — unchanged.

## 15. Review DB state

`review_workbench_p56.sqlite` = `3e479ee70e59ce9aafa6ba44718dda68d867dbcc660796b81ff63d2b19ca0f29`; `review_decisions` = 0 rows; all 9,153 `review_tasks` = `PENDING`.

## 16. Tests

126/126 `dose_verification_sandbox`/RC-030 targeted tests passed (17 new this turn: 11 in `test_owner_pilot_consolidation.py`, plus 1 range-loss regression added to `test_targeted_recovery_pilot.py`, plus fixes to 5 pre-existing tests that used the pre-reconciliation vocabulary). Canonical collection unchanged at 1,456. Full canonical pytest re-confirmed **0 unexpected failures** this turn (same result as all prior turns this session).

## 17. Files created or modified

**Code** (untracked, unstaged): `dose_verification_sandbox/verdict_taxonomy.py`, `dose_verification_sandbox/owner_fidelity_events.py`, `dose_verification_sandbox/owner_fidelity_event_schema.json`, `dose_verification_sandbox/precision_calculator.py` (modified — bug fix). **Tests**: `tests/dose_verification_sandbox/test_owner_pilot_consolidation.py` (new), `test_targeted_recovery_pilot.py` (modified — vocabulary fix + new regression test). **Interface**: `generated/rc030_recovery/RC030_OWNER_REVIEW_INTERFACE.html` (regenerated v2), `owner_review_template.html`, `owner_review_data.json` (regenerated with hash fields). **Reports**: this file, `RC030_OWNER_PILOT_CONSOLIDATION_BASELINE.md`, `RC030_VERDICT_TAXONOMY_DECISION.md`, `RC030_TABLE_CLIPPED_TEXT_RECOVERY_REPORT.md`, `RC030_CYRILLIC_TABLE_TEXT_COMPARISON.md`, `RC030_RANGE_LOSS_STAGE_RCA.md`, `RC030_ADDITIVE_RANGE_SCHEMA_PROPOSAL.md`, `RC030_MAX_DOSE_OWNER_GUIDE.md`, `RC030_PDF_COVERAGE_GAP_REPORT.md`. **Data**: `RC030_MAX_DOSE_OWNER_QUEUE.json`, `RC030_MISSING_PDF_MANIFEST.json` (rewritten), `generated/rc030_recovery/clipped_table_recovery.json`.

## 18. Exact owner launch instruction

**Windows, no server required (if your browser allows local-file JavaScript):**
Double-click `C:\ANTIBIO\generated\rc030_recovery\RC030_OWNER_REVIEW_INTERFACE.html`.

**If your browser blocks `file://` JavaScript** (Chrome does by default for `fetch`, though this file has no `fetch` calls and should work; verified in this turn via a local server, not via `file://` directly):
```
cd C:\ANTIBIO\generated\rc030_recovery
python -m http.server 8000
```
then open `http://localhost:8000/RC030_OWNER_REVIEW_INTERFACE.html`.

All 60 queued records verified this turn: PDF exists (100% found across approved storage), hash matches, page index in range, evidence hash re-derives exactly. **The interface is not claimed ready based on anything unverified — every record was checked, not assumed.**

## Tests, canonical

126/126 sandbox tests passed. Full canonical pytest: **1455 passed, 1 xfailed, 0 failed** in 317s — confirmed, matches baseline exactly.
