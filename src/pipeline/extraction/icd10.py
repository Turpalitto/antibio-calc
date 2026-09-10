"""Single source of truth for МКБ-10 / ICD-10 token handling.

Before this module existed, ``normalize_mkb`` was copy-pasted verbatim into
three extraction modules (``dosa_to_db_mapper``, ``dosa_source_contract``,
``extension_sources``) and none of them split comma-joined code lists. That is
how ``db/diseases/extended_dosa.json`` ended up with 16 nozologies carrying
``mkb10: ["C83.5, C91.0, C95.0"]`` — one array element holding five codes.
Downstream ICD-10 joins (source contracts, extension triage, the calculator ⇄
guideline crosswalk) silently missed every code but the first.

All three modules now delegate here. ``normalize_mkb`` stays deliberately
permissive: it splits and normalises but never discards a token, so no source
wording is lost (ARCHITECTURAL_INVARIANTS.md INV-09). Use ``is_valid_mkb`` to
filter when a strict code is required.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

__all__ = ["ICD10_PATTERN", "expand_mkb_range", "is_valid_mkb", "mkb_prefix", "normalize_mkb"]

_SPLIT_RE = re.compile(r"[,;]+")
ICD10_PATTERN = re.compile(r"^[A-Z]\d{2}(?:\.\d{1,3})?$")
# "B20-24", "B20–B24", "B20 - 24" — МКБ-10 block range notation.
_RANGE_RE = re.compile(r"^([A-Z])(\d{2})\s*[-–—]\s*(?:([A-Z])\s*)?(\d{2})$")


def expand_mkb_range(token: str) -> list[str]:
    """Expand МКБ-10 block-range notation into individual 3-character codes.

    ``"B20-24"`` -> ``["B20", "B21", "B22", "B23", "B24"]``. Ranges that cross a
    letter (``"A99-B01"``) or run backwards are returned unchanged so the caller
    can flag them instead of silently inventing codes.
    """
    match = _RANGE_RE.match(token.strip().upper())
    if not match:
        return [token]
    start_letter, start, end_letter, end = match.groups()
    if end_letter is not None and end_letter != start_letter:
        return [token]
    low, high = int(start), int(end)
    if high < low:
        return [token]
    return [f"{start_letter}{n:02d}" for n in range(low, high + 1)]


def normalize_mkb(value: Any) -> list[str]:
    """Normalise МКБ-10 input into a de-duplicated, order-preserving code list.

    Accepts ``None``, a single string, a list of strings, or a list that mixes
    both. Two source defects are repaired here:

    * comma/semicolon separated strings are split (``"C83.5, C91.0"``);
    * block ranges are expanded (``"B20-24"``).

    Everything else is preserved verbatim (upper-cased, trimmed) so no source
    wording is lost.
    """
    if value is None:
        return []
    tokens: Iterable[str] = value if isinstance(value, (list, tuple, set)) else [value]
    out: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token is None:
            continue
        for part in _SPLIT_RE.split(str(token)):
            for code in expand_mkb_range(part):
                code = code.strip().upper()
                if code and code not in seen:
                    seen.add(code)
                    out.append(code)
    return out


def is_valid_mkb(code: Any) -> bool:
    """True for a well-formed ICD-10 code (``A00``, ``A00.0``, ``A00.00``)."""
    return bool(ICD10_PATTERN.match(str(code or "").strip().upper()))


def mkb_prefix(code: Any) -> str:
    """Return the 3-character ICD-10 block prefix (``A01.2`` -> ``A01``)."""
    return str(code or "").replace(".", "").strip().upper()[:3]
