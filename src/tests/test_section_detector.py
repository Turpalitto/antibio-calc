from pathlib import Path
from unittest.mock import patch

import pytest

from section_detector import detect_sections


def test_detect_sections_finds_treatment_section(sample_pdf_text):
    pages = [sample_pdf_text]
    with patch("section_detector.extract_text_per_page", return_value=pages):
        result = detect_sections(Path("fake.pdf"), clinrec_id=2199)

    assert result["clinrec_id"] == 2199
    assert result["total_pages"] == 1
    assert 0 in result["relevant_pages"]
    assert len(result["sections_found"]) > 0
    assert any("лечение" in s["section"].lower() or "антибактериальная" in s["section"].lower()
               for s in result["sections_found"])
    assert len(result["relevant_text"]) > 0


def test_detect_sections_no_treatment_section(sample_pdf_text_no_abx):
    pages = [sample_pdf_text_no_abx]
    with patch("section_detector.extract_text_per_page", return_value=pages):
        result = detect_sections(Path("fake.pdf"), clinrec_id=2199)

    assert result["total_pages"] == 1
    assert "лечение" in str(result["sections_found"]).lower()


def test_detect_sections_multiple_pages():
    pages = [
        "РАЗДЕЛ 1. ВВЕДЕНИЕ\n\nОбщие сведения о заболевании.",
        "РАЗДЕЛ 3. ЛЕЧЕНИЕ\n\nАмоксициллин 500 мг 3 раза в день 7 дней.",
        "РАЗДЕЛ 4. РЕАБИЛИТАЦИЯ\n\nВосстановительное лечение.",
    ]
    with patch("section_detector.extract_text_per_page", return_value=pages):
        result = detect_sections(Path("fake.pdf"), clinrec_id=1)

    assert result["total_pages"] == 3
    assert 1 in result["relevant_pages"]
    assert 0 not in result["relevant_pages"]
    assert 2 not in result["relevant_pages"]
    assert "лечение" in result["relevant_text"].lower()


def test_detect_sections_empty_pdf():
    with patch("section_detector.extract_text_per_page", return_value=[]):
        result = detect_sections(Path("fake.pdf"), clinrec_id=1)

    assert result["total_pages"] == 0
    assert result["relevant_pages"] == []
    assert result["relevant_text"] == ""


def test_detect_sections_dosing_pages():
    pages = [
        "РАЗДЕЛ 3. ЛЕЧЕНИЕ\n\nОписание лечения.",
        "Таблица дозировок:\nАмоксициллин 500 мг 3 раза в день\nЦефтриаксон 1 г внутривенно",
    ]
    with patch("section_detector.extract_text_per_page", return_value=pages):
        result = detect_sections(Path("fake.pdf"), clinrec_id=1)

    assert 1 in result["dosing_pages"]
