"""RC-030 C6.3 — read-only PDF evidence helpers.

Pure, read-only functions for locating a stored `source_quote` within a
PDF-extracted full-page text and computing a bounded, deterministic
context window around it. No PDF is written or modified by this module;
callers are responsible for opening PDFs (e.g. via PyMuPDF) and passing
extracted text in.

Real defect fixed during C6.2/C6.3/C6.4 development: a naive
`str.find()` locating `source_quote` inside PDF-extracted page text fails
for the large majority of records, because PDF text extraction wraps
lines differently than the whitespace in the stored `source_quote` —
the substring search silently found nothing and callers fell back to
the original narrow, un-expanded quote. `find_quote_in_page_text()`
normalizes whitespace on both sides before searching, which raised the
real-world match rate from roughly 16/365 to 104/365 in the RC-030
range-candidate corpus (see RC030_C62_C63_C64_DICTIONARY_PDF_REPLAY_REPORT.md).
"""
from __future__ import annotations

import re

_WS_RUN_RE = re.compile(r"\s+")

# C6.8: a PDF line-wrap that splits a word mid-hyphen (e.g. "бета-\nлактамные"
# from real page-42 text of "Острый гепатит В (ГВ) у взрослых.pdf") must be
# rejoined WITHOUT a space, not collapsed to "бета- лактамные" -- a spurious
# space breaks exact quote matching even though the quote genuinely is on
# that page. Root-caused during C6.8's investigation of regimens 5688/6052
# (RC030_C68_SOURCE_QUOTE_DEFECT_REPORT.md): both were classified
# PDF_QUOTE_NOT_FOUND in C6.7 for this reason, not a wrong-page/wrong-PDF
# defect. Only a hyphen immediately followed by a line break between two
# Cyrillic/Latin letters is treated as a line-wrap split -- a numeric range
# dash uses "–"/"—" (en/em dash) or is not immediately followed by a
# newline, so this never touches real dash-separated ranges.
_HYPHEN_LINEWRAP_RE = re.compile(r"(?<=[a-zA-Zа-яА-ЯёЁ])-\n(?=[a-zA-Zа-яА-ЯёЁ])")


def normalize_whitespace(text: str) -> str:
    """Rejoin hyphen line-wraps, then collapse all remaining whitespace runs
    to a single space and strip. Used only for *locating* a quote inside
    page text — never mutates stored data."""
    text = _HYPHEN_LINEWRAP_RE.sub("-", text)
    return _WS_RUN_RE.sub(" ", text).strip()


def find_quote_in_page_text(page_text: str, quote: str, anchor_length: int = 40) -> int:
    """Returns the character offset of `quote` within `page_text` (both
    whitespace-normalized for the search), or -1 if not found even via a
    shortened anchor. Falls back to matching just the first `anchor_length`
    characters of the quote if the full quote isn't found verbatim — PDF
    extraction sometimes drops or alters a trailing footnote marker
    (e.g. `**`) that the stored quote includes."""
    if not page_text or not quote:
        return -1
    norm_page = normalize_whitespace(page_text)
    norm_quote = normalize_whitespace(quote)
    idx = norm_page.find(norm_quote)
    if idx != -1:
        return idx
    anchor = norm_quote[:anchor_length]
    if not anchor:
        return -1
    return norm_page.find(anchor)


def expand_context(page_text: str, quote: str, window: int = 300) -> str:
    """Returns a bounded window of whitespace-normalized page text centered
    on `quote`'s location, or `quote` itself unchanged if it cannot be
    located in `page_text` at all. Deterministic: same inputs always
    produce the same output; no randomness, no network, no file I/O."""
    if not page_text or not quote:
        return quote
    norm_page = normalize_whitespace(page_text)
    norm_quote = normalize_whitespace(quote)
    idx = find_quote_in_page_text(page_text, quote)
    if idx == -1:
        return quote
    start = max(0, idx - window)
    end = min(len(norm_page), idx + len(norm_quote) + window)
    return norm_page[start:end]
