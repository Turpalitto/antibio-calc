# RC-030 C6.2/C6.3/C6.4 — Dictionary Reconciliation, PDF Discovery, and Enhanced-Evidence Replay

**Superseding update (see `RC030_C65_STRUCTURAL_ANALYSIS_AND_V4_REPORT.md`):** the "0 new SAFE classifications" finding stated below was accurate for the context-expansion experiment described in this document, run *before* a separate, much higher-impact defect was found and fixed during the immediately-following C6.5 root-cause analysis (a Latin-vs-Cyrillic unit-script mismatch in `_base_unit()`, unrelated to context expansion or dictionary coverage). After that fix, the real 365-record replay produces 117 SAFE classifications (74 `SAFE_EXACT_LINK` + 43 `SAFE_SINGLE_CANDIDATE`). This document's findings about quote-truncation causing most `DICTIONARY_GAP` labels remain accurate and are preserved as-is below, per the "do not alter historical meaning" documentation discipline — read alongside C6.5 for the complete, current picture.

These three tracks are reported together because this turn's central finding — the PDF corpus is real and available — reshaped all three at once: most "dictionary gaps" turned out to be a symptom of truncated `source_quote` text losing the drug name (present a few dozen characters away on the real PDF page, in a table header or a preceding clause), not genuine dictionary coverage gaps.

## C6.3 — PDF corpus discovery (real, executed)

See `RC030_MULTIWORKSTREAM_BASELINE.md` for the corrected environmental finding. Direct results for all 365 range-candidate records:

| Metric | Count |
|---|---|
| Total referenced PDFs (365 records) | 365 |
| `PDF_FOUND_HASH_MATCH` (found + SHA-256 matches `CORPUS_MANIFEST.json`) | **365 (100%)** |
| `PDF_FOUND_HASH_MISMATCH` | 0 |
| `PDF_MISSING` | 0 |
| Page-text extraction succeeded (PyMuPDF) | 363 |
| Page-text extraction failed (bad page index) | 2 |

Search roots used (explicit allowlist, read-only): `downloads_active`, `downloads_antibiotics`, `downloads_other`, `archive_no_antibiotics`, `archive_review`, `quarantine` under `C:\clinrec_downloader`. Every referenced PDF was found in at least one root (most in multiple, i.e. redundantly stored across `downloads_active`/`downloads_antibiotics`/`downloads_other` — not a conflict, just duplicated storage). No PDF was modified; no PDF was copied into git.

## C6.2 — Dictionary-gap audit (40 records)

Direct inspection of all 40 `DICTIONARY_GAP` records' expected antibiotic names: **Цефтриаксон** (8), **тинидазол/Тинидазол** (4), **Ко-тримоксазол/ко-тримоксазол** (8, including an `(JO1EE)` ATC-coded form), **Цефотаксим** (2), **Секнидазол** (2), **нетилмицин/Нетилмицин** (4), **Джозамицин** (1), **Амоксициллин + клавулановая кислота** (1), **колистиметат натрия** (1), **даптомицин** (1), plus remaining singles.

**Key finding: most of these drug names are ALREADY in `medical_normalizer.dictionary.DRUG_SYNONYMS`** (spot-checked: `цефтриаксон` → `True`, `ко-тримоксазол` → `True`, `цефотаксим` → `True`). The dictionary was not the actual blocker for these — the real cause, confirmed by direct PDF page inspection (regimen 5660, Цефтриаксон): **the stored `source_quote` field frequently starts mid-sentence, after the drug name**, e.g. quote = `"новорожденным до 2 нед – 20–50 мг/кг/сут"` (newborns up to 2 weeks – 20-50 mg/kg/day) while the actual PDF page reads `"...цефтриаксон** – по 1–2 г в сутки внутримышечно или внутривенно детям старше 12 лет ..., новорожденным до 2 нед – 20–50 мг/кг/сут, детям от 3 нед до 12 лет – 20–80 мг/кг/сут..."` — a single age-stratified sentence about one drug, where only the age-group-specific dosing clause for *this* particular assembled regimen was captured as `source_quote`, dropping the sentence-initial drug name entirely.

**No unsafe dictionary additions were made.** Per the required standard (Phase 3), a dictionary addition must be based on an explicit, unambiguous source token — since the actual cause here is quote truncation (an extraction-pipeline issue upstream of both the dictionary and the attribution engine), adding dictionary entries would not have fixed anything; the drug names were already governed.

## C6.4 — Enhanced-evidence replay using real PDF page context

Since the drug name is frequently present on the real PDF page just outside the stored `source_quote`'s boundaries, this turn built a **bounded, deterministic context-expansion** step: locate the (whitespace-normalized) `source_quote` within the (whitespace-normalized) full extracted page text, then take a fixed ±300-character window around it (snapping was attempted at paragraph breaks; not always available). This is a genuine, bounded evidence improvement — not full page-layout/table reconstruction (Part V, not attempted this turn).

**A real bug was found and fixed during this analysis**: an initial naive `str.find()` (without whitespace normalization) failed to locate ~88 of 104 quotes within their page text at all (PDF text has different line-wrapping than the stored quote), silently falling back to the original narrow quote with zero effective expansion. Normalizing whitespace on both sides before the substring search fixed this (verified: quote-location success rate improved from 16/365 effective expansions to 104/365).

### Before/after classification distribution (all 365, same engine, wider context)

| Classification | Before (C6.1, narrow quote) | After (this turn, expanded context) |
|---|---|---|
| `WRONG_RANGE_ANCHOR` | 223 | 216 |
| `AMBIGUOUS_ALTERNATIVE_BOUNDARY` | 48 | 111 |
| `DICTIONARY_GAP` | 40 | **6** |
| `AMBIGUOUS_TABLE_CONTEXT` | 23 | 0 (reclassified into other buckets by the expansion; no table-bbox recovery was attempted so this doesn't mean "resolved," see below) |
| `NOT_A_DOSE_RANGE` | 26 | 25 |
| `AMBIGUOUS_MULTIPLE_DRUGS` | 3 | 0 |
| `AMBIGUOUS_MULTIPLE_RANGES` | 0 | 3 |
| `AMBIGUOUS_LOADING_MAINTENANCE` | 2 | 4 |
| **SAFE_* (any)** | **0** | **0** |

**Zero new SAFE classifications**, despite 104/365 records changing classification. This is an honest, important result: broader real-PDF context resolves the *dictionary-gap* symptom (34 of 40 records reclassify away from `DICTIONARY_GAP` once the drug name is visible) but mostly reveals *more* structural complexity — additional "или" alternative boundaries and competing ranges that the truncated quote had hidden — rather than confirming a single safe link. The regimen-5660 example (above) illustrates why: the real sentence has *three* age-stratified dose clauses for one drug, and the engine correctly refuses to guess which one belongs to this specific structured regimen without also matching the regimen's own `age_group` field against age markers in the text — a capability the current engine does not have (see "Recommended next step" below).

## Recommended next step (not implemented this turn — a genuine, well-evidenced lead)

**Age-group-aware disambiguation**: extend `span_attribution.py` to detect age-group markers (e.g. "новорожденным", "детям от X до Y лет", "детям старше N лет") as spans, and match them against each assembled regimen's own structured `age_group` field as an *additional* positive-evidence signal (similar to the existing `unit_match`/`scalar_match` checks) when multiple age-stratified ranges exist in one sentence for one drug. This was identified as the single most promising concrete lead from this turn's real evidence (regimen 5660 and likely several of the 111 `AMBIGUOUS_ALTERNATIVE_BOUNDARY` records fit this exact pattern). Deferred rather than rushed, because: (a) it requires new span-detection code, (b) it requires careful boundary-rule design to avoid a wrong link (attaching the wrong age group's range), and (c) it needs full regression testing across all 365 records before being trusted — none of which fits safely within this turn's remaining scope.

## What was NOT attempted this turn (explicit deferrals, not silent gaps)

- **Six-tool table-layout bbox/row/column reconstruction** (Part V, DocLayout-YOLO/Table Transformer/MinerU/Docling/RapidTable) — the PDF corpus is now confirmed available, so this is no longer blocked by data availability, but running the full ML stack across the table-context records is a substantial undertaking not attempted this turn. Documented as future work with a clear, unblocked path.
- **Mixed-script/OCR confusable-character normalization** (Phase 4) — not needed this turn, since the actual dictionary-gap cause (quote truncation) was different from what that phase anticipated.
- **Combination-drug separator handling** (Phase 5) — not specifically audited this turn; the 3 `AMBIGUOUS_MULTIPLE_DRUGS`/3 `AMBIGUOUS_MULTIPLE_RANGES` records after expansion would be the starting point for this.

## Safety confirmation

No dictionary file was modified. No PDF was modified or committed. No authoritative database was touched. Zero new SAFE classifications means no new migration candidates exist as a result of this analysis. All context-expansion processing was read-only against the real PDF corpus and the existing `assembled_regimens.sqlite`.
