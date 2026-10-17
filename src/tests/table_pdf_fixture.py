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


# ---------------------------------------------------------------------------
# Audit 2026-10-14 (E-2): a synthetic three-page "guideline" so that the
# extraction router has one end-to-end path that runs on every machine —
# including CI without MinerU/docling and without the owner's corpus.
# Page 1: narrative Cyrillic text (good page). Page 2: a ruled dosing table.
# Page 3: an image-only rendering of page 1 (no text layer), i.e. a scanned
# page that forces the per-page fallback decision. The content is invented
# for the test and is NOT clinical guidance.
# ---------------------------------------------------------------------------

GUIDELINE_FIXTURE_TITLE = "Синтетическая клиническая рекомендация (тестовый документ)"

GUIDELINE_FIXTURE_PARAGRAPHS = (
    "Настоящий документ создан автоматически для проверки конвейера извлечения "
    "и не содержит клинических рекомендаций.",
    "Раздел 3. Лечение. Антибактериальная терапия назначается при подтверждённой "
    "бактериальной этиологии заболевания.",
    "Рекомендуется амоксициллин внутрь 500 мг 3 раза в сутки в течение 7 дней "
    "(уровень убедительности рекомендаций A, уровень достоверности доказательств 1).",
    "Детям рекомендуется амоксициллин 45 мг/кг/сут внутрь в 2 приёма, "
    "продолжительность курса 7-10 дней.",
    "При непереносимости пенициллинов рекомендуется азитромицин 500 мг внутрь "
    "1 раз в сутки в течение 3 дней.",
)

GUIDELINE_FIXTURE_TABLE_ROWS = [
    ["Препарат", "Доза", "Путь введения"],
    ["Амоксициллин (АТХ: J01CA04)", "500 мг 3 раза в сутки", "внутрь"],
    ["Амоксициллин (АТХ: J01CA04)", "45 мг/кг/сут в 2 приёма", "внутрь"],
    ["Цефтриаксон (АТХ: J01DD04)", "1 г 1 раз в сутки", "в/в"],
    ["Азитромицин (АТХ: J01FA10)", "500 мг 1 раз в сутки", "внутрь"],
]


def build_guideline_pdf(path: Path, fontfile: str) -> Path:
    """Write the three-page synthetic guideline PDF described above."""
    table_path = path.with_name(path.stem + "_table.pdf")
    build_table_pdf(table_path, GUIDELINE_FIXTURE_TABLE_ROWS, fontfile)
    doc = fitz.open()
    try:
        # page 1 — narrative text
        page = doc.new_page()
        page.insert_text(fitz.Point(50, 60), GUIDELINE_FIXTURE_TITLE,
                         fontsize=12, fontname="F0", fontfile=fontfile)
        y = 100.0
        for paragraph in GUIDELINE_FIXTURE_PARAGRAPHS:
            rect = fitz.Rect(50, y, 545, y + 90)
            page.insert_textbox(rect, paragraph, fontsize=10,
                                fontname="F0", fontfile=fontfile)
            y += 70.0
        # page 2 — the ruled dosing table
        table_doc = fitz.open(str(table_path))
        try:
            doc.insert_pdf(table_doc)
        finally:
            table_doc.close()
        # page 3 — image-only copy of page 1 (a "scan": no extractable text)
        png = doc[0].get_pixmap(dpi=72).tobytes("png")  # PNG keeps the file small
        scan = doc.new_page()
        scan.insert_image(scan.rect, stream=png)
        doc.save(str(path), deflate=True, garbage=3)
    finally:
        doc.close()
    table_path.unlink(missing_ok=True)
    return path
