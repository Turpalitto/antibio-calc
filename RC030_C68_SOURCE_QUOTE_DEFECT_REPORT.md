# RC-030 / C6.8 Phase 6-7 — Source Quote Defect Investigation (5688, 6052)

## Outcome

**QUOTE_FOUND_NORMALIZED_MATCH.** Both records were misclassified `PDF_QUOTE_NOT_FOUND` in C6.7. The real cause was a quote-matching defect in `dose_verification_sandbox.pdf_evidence.normalize_whitespace()`, not a wrong page, wrong PDF, stale quote, or genuinely unsupported record. **Both records' source evidence is real and correctly cited.**

## Investigation

Both 5688 and 6052 cite `Острый гепатит В (ГВ) у взрослых.pdf`, page 42, with an identical `source_quote` (same guideline paragraph, two different regimen rows extracted from it) and matching `field_provenance` (`source_document`/`source_location: page 42`/`source_store: normalized_regimens`, consistent for both records).

C6.7 concluded the quote was "not present anywhere in this 75-page PDF" based on a whole-document substring search for the anchor phrase `"бета-лактамные антибактериальные препараты"`. That search was correct as far as it went — the anchor genuinely does not appear as a contiguous substring — but the conclusion ("not in the document") was wrong.

**Root cause, confirmed by direct inspection of the real PDF page text (`doc[41].get_text()`, physical page 42):**

```
'...другие бета-\nлактамные антибактериальные препараты...'
```

PyMuPDF's raw text extraction splits the compound word "бета-лактамные" ("beta-lactam[s]") across a line wrap: the hyphen that is genuinely part of the word sits at the end of a physical line, followed by a `\n`, then "лактамные" continues on the next line. The existing `normalize_whitespace()` (`_WS_RUN_RE.sub(" ", text)`) collapses that `\n` to a space, producing `"бета- лактамные"` (hyphen **and** a spurious space) — which never matches the stored quote's `"бета-лактамные"` (hyphen, no space). Both the full-quote search and the anchor-substring search failed for the same underlying reason.

**Fix:** added a dehyphenation pass to `normalize_whitespace()` — a hyphen immediately followed by a line break, with a letter on each side, is rejoined as a bare hyphen (the line-wrap artifact is removed; the real hyphen the word needs is preserved). Verified against the actual raw text (`'бета-\nлактамные'`), confirmed narrow (only fires on `letter-\nletter`, never touches the en-dash (`–`) used for numeric ranges like `"250 – 500"`, which is a different Unicode character and is not immediately followed by a line break in this corpus).

## Verification

- `find_quote_in_page_text()` for both 5688 and 6052 now returns a valid offset (1789) instead of -1.
- Re-ran the full 117-record page/quote audit with the fix: **117/117 `PDF_EVIDENCE_VALID`** (was 115/117 in C6.7).
- Existing `tests/dose_verification_sandbox/test_pdf_evidence.py` (10 tests) still pass unchanged — the fix is additive, not a behavior change for already-working cases.

## Disposition change from C6.7

- **5688, 6052**: `SINGLE_SOURCE_BLOCKED` → **no longer source-blocked**. Both remain `SAFE_SINGLE_CANDIDATE` in the frozen C6.7 classification (this fix does not change classification, only evidence validity) and should be re-dispositioned under C6.8's Part VI single-candidate re-audit using their now-confirmed-valid source evidence, not held back as unreviewable.

## Scope note

This was a real, narrow, well-understood defect (one specific PDF's one specific hyphenated word, generalized to a correctly-scoped regex). No other record in the 117-candidate pool was affected by this specific bug (117/117 were already `PDF_EVIDENCE_VALID` for the other 115; only these 2 shared the one PDF with the line-wrapped hyphen). Broader hyphenation defects in other PDFs are possible but unobserved in this corpus — flagged as a general quote-matching hardening area (Phase 7), not fully swept across the entire 2675-row corpus in this pass.
