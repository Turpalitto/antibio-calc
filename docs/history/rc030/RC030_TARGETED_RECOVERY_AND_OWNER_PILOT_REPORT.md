# RC-030 Targeted Source Recovery and Owner Fidelity Validation Pilot

Executed 2026-07-16 on top of HEAD `394818675b0ed199e03cae1d89e38a488f5102ce`. Nothing in this turn is staged or committed.

## 1. Tools installed

All six tools (PyMuPDF, MinerU, Docling, DocLayout-YOLO, Table Transformer, RapidTable) import successfully with cached model weights (`RC030_SIX_TOOL_AVAILABILITY_AUDIT.md`, prior turn).

## 2. Tools actually executed

**All six, for real, this turn** (`RC030_SIX_TOOL_REAL_EXECUTION_AUDIT.md`) — corrects the prior turn's conservative assumption that this would need a dedicated compute session. A single CPU-only page took ≤25 s end-to-end per tool (MinerU's local API cold-start included). A batch of 12 pages processed via DocLayout-YOLO, Table Transformer, RapidTable, Docling (all model-load-once, loop-over-pages) and MinerU (single batch directory submission) completed in well under 10 minutes total.

## 3. Pages processed

13 total: 1 smoke page (regimen 5574, known-good reference) + 12 target pages selected via mechanical stratified criteria (`RC030_TARGET_PAGE_MANIFEST.json`) — pediatric weight-based dosing, "в сутки" markers, ambiguous mg/kg, multi-alternative ("или"), multi-numeric, sub-daily frequency, and max-dose candidates.

**Real gap found during selection**: of the initial 26 candidate pages, only **12 (46%)** had a locally-available source PDF — 14 referenced PDFs are not present in `C:\clinrec_downloader\downloads_active\` (68 of 193 distinct PDFs referenced by the whole corpus are missing locally, 65% coverage). This is reported as-is; it constrains what can be verified against source right now, independent of anything about RC-030's own code.

## 4. Successful outputs

All 12 pages: PyMuPDF (raw text, exact), DocLayout-YOLO (region detection), Table Transformer (table detection, threshold 0.7), Docling (Markdown), MinerU (Markdown + structured JSON) all produced real, inspectable artifacts under `generated/rc030_recovery/` (gitignored-by-convention, not staged). RapidTable ran only on the 6 pages Table Transformer flagged as containing a table (methodologically correct — running structure recognition on a whole non-table page produces false "tables", as the smoke test on the regimen-5574 prose page demonstrated).

## 5. Failed outputs

None. Zero `INSTALLED_BUT_FAILED`/`MODEL_MISSING`/`DEPENDENCY_CONFLICT`/`UNAVAILABLE` across all 6 tools × 12 pages.

## 6. Table recovery results

6 of 12 pages contain a real table, confirmed by **independent agreement between DocLayout-YOLO and Table Transformer** on 3 of them (`Лепра [болезнь Гансена].pdf` p.32, `Отит средний острый.pdf` p.23, `Паратонзиллярный абсцесс.pdf` p.22), plus 3 more Table-Transformer-only detections at high confidence (0.73–0.92).

**Critical finding**: on `Отит средний острый.pdf` p.23, the table contains real dosing data (Table 4, "Суточные дозы и режим введения антибиотиков при ОСО") including a джозамицин pediatric row ("40-50 мг/кг/сутки 2-3 приема"). **MinerU and RapidTable's OCR-based table-cell extraction systematically corrupts Cyrillic characters** inside table cells (е.g. "50-60¹ /κ/yT" instead of "50-60 мг/кг/сут" — Cyrillic к/т/г/в confused with Latin/Greek look-alikes κ/τ/г/B), even though **PyMuPDF's plain-text extraction of the exact same page is perfect and complete**, because the source PDF has a real embedded text layer, not a scanned image. **Actionable conclusion**: table recovery for this corpus should use layout detection (bounding boxes) + PyMuPDF text extraction *clipped to those boxes*, not OCR — OCR is the wrong tool for a born-digital PDF and introduces errors that don't exist in the source.

## 7. Direct-text recovery results

PyMuPDF text, Docling Markdown, and MinerU Markdown all agree exactly on prose (non-table) content, matching the previously-verified regimen-5574 evidence packet byte-for-byte in substance. Confirms plain-text extraction is already fully reliable for this corpus.

## 8. Range-expression RCA

**Cause C, conclusively established with code + data evidence** (`RC030_RANGE_EXPRESSION_RCA.md`): `parser.py`'s `parse_dose_expression()` receives a single scalar `dose` value and sets `numeric_min = numeric_max = dose` unconditionally — `is_range` can never be `True`, not because the parser fails to recognize ranges in text, but because ranges are collapsed to a single number **before assembly**. 348/2,675 rows (13%) have a genuine numeric range in `source_quote` (e.g. "20–50 мг/кг/сут") but `dose` always holds only the lower bound. Corroborated by schema: `normalized_regimens` has `duration_min`/`duration_max` but no `dose_min`/`dose_max`. Regression test added (`test_range_collapse_reproducible_on_known_regimen`).

## 9. Owner pilot queue

**60 records prepared** (`RC030_OWNER_PILOT_QUEUE.json`), quota exactly met: 15 WEIGHT_PER_DAY, 15 WEIGHT_PER_DOSE, 10 FIXED_PER_DAY, 10 FIXED_PER_DOSE, 5 AMBIGUOUS controls, 5 table/source-recovery cases (drawn from the 3 confirmed-table pages above). All 60 have a locally-available source PDF and short, single-antibiotic source quotes for a fast first pass.

## 10. Owner-review interface status

**Built and dry-run verified** (`generated/rc030_recovery/RC030_OWNER_REVIEW_INTERFACE.html`, guide at `RC030_OWNER_PILOT_GUIDE.md`). Static, offline, no server, no network submission — verdicts append-only to browser `localStorage`, exportable as JSON. Verified live in a browser this turn: verdict field never prefilled (parser's answer is never shown as a default), append-only confirmed (2 submits on the same record → 2 preserved entries), empty-note validation correctly blocks confirming verdicts, only network request observed was the page's own initial load (zero submission traffic). All test verdicts were synthetic and cleared from storage after verification — **no real owner verdicts exist.**

**Known gap**: the interface's verdict taxonomy (`SOURCE_CONFIRMS_PER_DAY`, ...) is this turn's Phase 6 vocabulary; the previously-defined `DoseSemanticEvidenceUnit.human_fidelity_verdict` (prior turn, Phase 8/9) uses a *different* vocabulary (`CORRECT_EXPLICIT_PER_DAY`, ...). These two taxonomies are **not reconciled** — a real inconsistency, documented rather than silently resolved, since resolving it correctly requires a judgment call about which vocabulary is authoritative that should be an explicit owner decision, not something decided implicitly by picking one in code.

## 11. Max-dose queue

**Not built this turn.** 104 max-dose candidates were identified mechanically in the prior turn's baseline; Phase 10's evidence-packet generation for a ~20-case first queue was not attempted — deprioritized in favor of the range RCA and owner interface, which had more direct value this turn. Open for a follow-up pass.

## 12. Formulation limitation

Unchanged from `RC030_FORMULATION_AVAILABILITY_REPORT.md` (prior turn): 0 SOURCE_BACKED, 0 DICTIONARY_BACKED, 40 AMBIGUOUS, 2,635 ABSENT. Conversion remains disabled. No new work this turn.

## 13. Active QA-calculable count

**0.** Live re-derivation across all 2,675 rows via `classify_regimen` → `assess_risk` → `validate`: zero rows have `calculation_eligibility != BLOCKED`.

## 14. Clinically approved count

**0.** `review_decisions` = 0 rows; all 9,153 `review_tasks` = `PENDING`.

## 15. Source DB hashes

`assembled_regimens.sqlite` = `9f505d08428cd2841983d3c8881c15e0813ada4a9056dea360a357a0f3eebcd9`; `normalized_regimens.sqlite` = `c7b67354b0723ad538a185e561ed94d09b11c019279be9c4c6412c4f1eaa4237` — both unchanged, re-verified read-only.

## 16. Review DB state

Unchanged: 0 decisions, 9,153/9,153 tasks `PENDING`.

## 17. Remaining blockers

- No real owner fidelity verdicts recorded yet (interface is ready and verified; nobody has used it for real records).
- 65% PDF coverage locally — some target-page categories (e.g. `source_corrupted_or_short`, `explicit_na_priem`) had almost no locally-available examples in the original 26-page candidate set.
- Verdict-taxonomy mismatch between this turn's owner interface and the prior turn's `DoseSemanticEvidenceUnit` (see §10) needs an explicit owner decision on which vocabulary is authoritative before any real verdict gets recorded into a permanent schema.
- Max-dose evidence-packet queue (Phase 10) not built this turn.
- Precision calculator (`dose_verification_sandbox/precision_calculator.py`) is implemented and unit-tested against synthetic data only — has never run against a real verdict.

## 18. Exact owner action required

1. Open `generated/rc030_recovery/RC030_OWNER_REVIEW_INTERFACE.html` and review some or all of the 60 queued records against their source PDFs.
2. Decide which fidelity-verdict taxonomy is authoritative (this turn's `SOURCE_CONFIRMS_*` set, or the prior turn's `CORRECT_EXPLICIT_*` set) so a future turn can reconcile the two without guessing.
3. Decide whether to invest in the layout-detection-plus-PyMuPDF-clipping table-recovery approach (§6) as a follow-up, since it would fix real Cyrillic-corruption in table cells that OCR-based recovery currently introduces.

## Tests

`tests/dose_verification_sandbox/test_targeted_recovery_pilot.py` (9 new tests): evidence-unit fail-closed defaults, rejection of non-`BLOCKED` eligibility, Wilson-interval reference value, precision-denominator correctness (ambiguous excluded), minimum-sample-size flagging, precision calculator never touching `TYPES_MEETING_PRECISION_THRESHOLD`, and the range-collapse regression. Full RC-030/sandbox suite: **107/107 passed**. Canonical collection unchanged at 1,456. Full canonical pytest: **1455 passed, 1 xfailed, 0 failed** — confirmed, matches baseline exactly.
