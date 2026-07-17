# RC-030 / C6.7 Part VII — PDF and Table Evidence Audit (117 candidates)

## Method

Real, byte-level verification against the actual PDF corpus at `C:\clinrec_downloader` (confirmed a genuine, distinct directory from `C:\ANTIBIO` — different inode/device; contains 477 files under `downloads_active` alone plus `downloads_all`, `downloads_antibiotics`, `downloads_other`, `archive_review`, `archive_no_antibiotics`, `quarantine`). No PDF bytes were modified; no PDF was copied into the repo.

Scripts (not yet committed — outputs only, in `generated/rc030_c67/`, excluded from git):
- `pdf_hash_reverify.json` — re-hashes each unique source PDF referenced by the 117 candidates and compares to `CORPUS_MANIFEST.json`'s recorded sha256.
- `pdf_page_quote_audit.json` — for each of the 117 records, opens `source_pdf` at `source_page` with PyMuPDF, extracts real page text, and searches (via the already-committed, already-tested `dose_verification_sandbox.pdf_evidence.find_quote_in_page_text`) for `source_quote` inside it.

## PDF hash re-verification

117 candidate records reference **39 unique PDF files**. All 39 were located in the corpus and re-hashed from actual file bytes:

**39/39 `PDF_EVIDENCE_VALID` — 0 `PDF_HASH_MISMATCH`, 0 `PDF_PAGE_MISSING`.**

No record is removed from the pool on hash grounds.

## Page + quote verification

For all 117 records: page exists in the PDF, page text extracts non-empty, and `source_quote` (whitespace-normalized) was searched for inside the extracted page text.

- **115/117 `PDF_EVIDENCE_VALID`** — quote found verbatim (whitespace-normalized) on the cited page.
- **2/117 `PDF_QUOTE_NOT_FOUND`** — regimen_id `5688` (v1) and `6052` (v1), both citing `Острый гепатит В (ГВ) у взрослых.pdf`, page 42.

### Finding: quote/source mismatch, not just a page offset error

Investigated further (whole-document search, not just the cited page): the anchor phrase from both records' `source_quote` ("бета-лактамные антибактериальные препараты") does **not appear anywhere in this 75-page PDF at all**. Page 42 of the actual document is about GI-symptom management (lactulose, domperidone, activated charcoal, pancreatin) for hepatitis B patients — unrelated content. The quoted sentence (antibacterial coverage with cefazolin/ceftriaxone + metronidazole, worded like peritonitis/intra-abdominal-infection coverage) is not from this document.

This is a genuine source-attribution defect in the two records' `source_pdf`/`source_quote` fields upstream of this audit (most likely a mis-join during original corpus assembly to the wrong guideline), **not a PDF-extraction or whitespace-normalization artifact** — the text genuinely isn't in the cited file.

**Disposition:** both `5688` and `6052` are classified `PDF_QUOTE_NOT_FOUND` and removed from the exact-link-eligible evidence pool. Both were already `SAFE_SINGLE_CANDIDATE` (not `SAFE_EXACT_LINK`), so this does not change the 74-count exact-link pool, but it does directly inform their Part VI disposition (`SINGLE_SOURCE_BLOCKED`, not any confirmation-track bucket) — see [RC030_C67_SINGLE_CANDIDATE_DISPOSITION.md](RC030_C67_SINGLE_CANDIDATE_DISPOSITION.md).

## Table evidence

**0/117 candidates carry the table-context flag.** The engine (`span_attribution.attribute()`) always routes table-flagged records to `AMBIGUOUS_TABLE_CONTEXT`, which is excluded from the SAFE classifications by construction — so no record in the 74+43 pool is table-derived. Phase 10's table-layout-model requirement (DocLayout-YOLO / Table Transformer / MinerU / Docling / RapidTable comparison) therefore has **no applicable records in this pool** and was not run. This should be re-checked if the 43 single-candidate or rejected/downgraded pools are ever re-mined for promotion — table-context records are a distinct, larger population (23/365 in the full replay) not covered by this audit pass.

## Multi-column / evidence-density signal

31/117 records (26%) have `competing_ranges_count > 0` in the manifest — i.e. more than one numeric-range-shaped span existed in the source quote, and exactly one survived the engine's structural filters. This is not itself a defect (it's the expected shape of "safe because deterministically disambiguated," not "safe because trivial"), but it flags these 31 as higher-value targets for the Part IV/V independent Pass A comparison and the Phase 7 manual sample.

## Classification summary

| Status | Count |
|---|---|
| PDF_EVIDENCE_VALID (hash + page + quote all clean) | 115 |
| PDF_QUOTE_NOT_FOUND | 2 (regimen 5688, 6052) |
| PDF_HASH_MISMATCH | 0 |
| PDF_PAGE_MISSING | 0 |
| PDF_TEXT_MISSING | 0 |
| PDF_CORRUPTED | 0 |
| PDF_TABLE_REQUIRED | 0 (no table-flagged records in this pool) |
| PDF_MULTICOLUMN_RISK | not separately assessed this pass (no automated column-layout detector run; `block_count` recorded per page in `pdf_page_quote_audit.json` as a coarse proxy only) |

**Local blocker, not a program-wide stop** (per owner's explicit blocker taxonomy: a per-record PDF issue marks that record BLOCKED and the rest of the program continues): records `5688` and `6052` are marked `PDF_QUOTE_NOT_FOUND` / evidence-blocked and excluded from any confirming disposition.
