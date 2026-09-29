"""Synthetic-PDF fixtures for the regimen-candidate extraction logic.

F-5: seven substantive extraction tests used to `pytest.skip` unless a hardcoded
`C:\\...` corpus PDF existed, so on any non-Windows checkout the ENTIRE
dose-extraction test surface was inert.  These fixtures build a ruled table PDF in
`tmp_path` so the pure extraction logic is exercised everywhere, and the corpus
tests above remain as the source-anchored end-to-end checks.
"""

from __future__ import annotations

from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz")

# A Cyrillic-capable font is required: PyMuPDF's built-in base-14 fonts render
# Cyrillic as filler glyphs, which would make the fixture meaningless.
_CYRILLIC_FONTS = (
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
    "C:/Windows/Fonts/calibri.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)


def _fontfile() -> str | None:
    return next((p for p in _CYRILLIC_FONTS if Path(p).exists()), None)


def resolve_cyrillic_font() -> str:
    """Return a Cyrillic-capable TTF path, or skip if none exists."""
    path = _fontfile()
    if path is None:
        pytest.skip("no Cyrillic-capable TTF available to build the fixture PDF")
    return path


# Registered as a session fixture in conftest.py (and usable directly).  It is
# wrapped with `.fixture` so importing it into a test module does not shadow an
# identically named parameter (F811).
cyrillic_font = pytest.fixture(scope="session")(resolve_cyrillic_font)


def build_table_pdf(path: Path, rows: list[list[str]], fontfile: str) -> Path:
    """Write a ruled table PDF; rows[0] is the header row."""
    xs = [40.0, 240.0, 400.0, 540.0]
    y0, row_height = 60.0, 28.0
    doc = fitz.open()
    try:
        page = doc.new_page()
        count = len(rows)
        for x in xs:
            page.draw_line(fitz.Point(x, y0), fitz.Point(x, y0 + count * row_height))
        for index in range(count + 1):
            page.draw_line(
                fitz.Point(xs[0], y0 + index * row_height),
                fitz.Point(xs[-1], y0 + index * row_height),
            )
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                if not value:
                    continue
                if c >= len(xs):
                    continue
                page.insert_text(
                    fitz.Point(xs[c] + 4, y0 + r * row_height + 19),
                    value, fontsize=9, fontname="F0", fontfile=fontfile,
                )
        doc.save(str(path))
    finally:
        doc.close()
    return path


def build_table_pdf_fixture(tmp_path: Path, rows: list[list[str]],
                            cyrillic_font: str, name: str = "table.pdf") -> Path:
    return build_table_pdf(tmp_path / name, rows, cyrillic_font)
