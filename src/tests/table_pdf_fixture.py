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


_BASE_FONTSIZE = 9.0
_MIN_FONTSIZE = 5.0
_CELL_PADDING = 4.0


def _fit_fontsize(font: "fitz.Font", value: str, cell_width: float) -> float:
    """Largest font size (<= 9 pt) at which ``value`` stays inside its cell.

    Audit 2026-10-14 (A-2): with DejaVu/Liberation metrics a 9 pt cell such as
    "Цефтриаксон (АТХ: J01DD04) в/в или внутрь" is ~210 pt wide and overflowed
    the 200 pt drug column, so the extractor read "или внутрь" as part of the
    DOSE cell and the route test failed on every Linux CI runner while passing
    on macOS/Windows fonts. Glyph overflow is a fixture artefact, not extractor
    behaviour, so the text is shrunk to fit instead of widening the columns.
    """
    available = cell_width - 2 * _CELL_PADDING
    width = font.text_length(value, fontsize=_BASE_FONTSIZE)
    if width <= available:
        return _BASE_FONTSIZE
    return max(_MIN_FONTSIZE, _BASE_FONTSIZE * available / width)


def build_table_pdf(path: Path, rows: list[list[str]], fontfile: str) -> Path:
    """Write a ruled table PDF; rows[0] is the header row."""
    xs = [40.0, 240.0, 400.0, 540.0]
    y0, row_height = 60.0, 28.0
    font = fitz.Font(fontfile=fontfile)
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
                cell_width = xs[c + 1] - xs[c] if c + 1 < len(xs) else 100.0
                page.insert_text(
                    fitz.Point(xs[c] + _CELL_PADDING, y0 + r * row_height + 19),
                    value, fontsize=_fit_fontsize(font, value, cell_width),
                    fontname="F0", fontfile=fontfile,
                )
        doc.save(str(path))
    finally:
        doc.close()
    return path


def build_table_pdf_fixture(tmp_path: Path, rows: list[list[str]],
                            cyrillic_font: str, name: str = "table.pdf") -> Path:
    return build_table_pdf(tmp_path / name, rows, cyrillic_font)
