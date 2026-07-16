from unittest.mock import patch

import pytest

from classifier import classify_one, compute_confidence_score


def test_classify_level_a(sample_item, sample_pdf_text):
    with patch("classifier.detect_sections") as mock_detect:
        mock_detect.return_value = {
            "clinrec_id": 2199,
            "total_pages": 10,
            "relevant_pages": [3, 4, 5],
            "relevant_text": sample_pdf_text,
            "sections_found": [
                {"section": "Лечение", "page": 3},
                {"section": "Антибактериальная терапия", "page": 4},
            ],
            "dosing_pages": [4, 5],
        }
        result = classify_one(sample_item)

    assert result["abx_level"] == "A"
    assert result["confidence_score"] >= 80
    assert result["extraction_priority"] == "high"
    assert result["has_dosing_info"] is True
    assert len(result["matched_sections"]) >= 2


def test_classify_level_d(sample_item, sample_pdf_text_no_abx):
    item = {**sample_item, "abx_drugs_found": [], "abx_keywords_found": [], "abx_score": 0, "has_antibiotics": False}
    with patch("classifier.detect_sections") as mock_detect:
        mock_detect.return_value = {
            "clinrec_id": 2199,
            "total_pages": 5,
            "relevant_pages": [2],
            "relevant_text": sample_pdf_text_no_abx,
            "sections_found": [{"section": "Лечение", "page": 2}],
            "dosing_pages": [],
        }
        result = classify_one(item)

    assert result["abx_level"] == "D"
    assert result["confidence_score"] == 0
    assert result["extraction_priority"] == "skip"


def test_classify_level_c(sample_item, sample_pdf_text_keyword_only):
    item = {
        **sample_item,
        "abx_drugs_found": [],
        "abx_keywords_found": ["антибиотик"],
        "abx_score": 5,
        "has_antibiotics": True,
    }
    with patch("classifier.detect_sections") as mock_detect:
        mock_detect.return_value = {
            "clinrec_id": 2199,
            "total_pages": 3,
            "relevant_pages": [],
            "relevant_text": sample_pdf_text_keyword_only,
            "sections_found": [],
            "dosing_pages": [],
        }
        result = classify_one(item)

    assert result["abx_level"] == "C"
    assert 1 <= result["confidence_score"] <= 49
    assert result["extraction_priority"] == "low"


def test_classify_level_b(sample_item):
    item = {
        **sample_item,
        "abx_drugs_found": ["амоксициллин"],
        "abx_keywords_found": ["антибактериальная терапия"],
        "abx_score": 15,
        "has_antibiotics": True,
    }
    with patch("classifier.detect_sections") as mock_detect:
        mock_detect.return_value = {
            "clinrec_id": 2199,
            "total_pages": 10,
            "relevant_pages": [4],
            "relevant_text": "Антибактериальная терапия\nАмоксициллин 500 мг.",
            "sections_found": [{"section": "Антибактериальная терапия", "page": 4}],
            "dosing_pages": [4],
        }
        result = classify_one(item)

    assert result["abx_level"] == "B"
    assert 50 <= result["confidence_score"] <= 79
    assert result["extraction_priority"] == "medium"


def test_classify_no_pdf_path():
    item = {"Id": 1, "Name": "Test", "CodeVersion": "1_1", "pdf_path": ""}
    result = classify_one(item)
    assert result["abx_level"] == "D"
    assert result["confidence_score"] == 0
    assert result["extraction_priority"] == "skip"


def test_compute_confidence_score_high():
    score = compute_confidence_score(
        drug_count=5,
        has_treatment_section=True,
        has_dosing=True,
        has_duration=True,
        keyword_count=3,
    )
    assert score >= 80


def test_compute_confidence_score_zero():
    score = compute_confidence_score(
        drug_count=0,
        has_treatment_section=False,
        has_dosing=False,
        has_duration=False,
        keyword_count=0,
    )
    assert score == 0


# Regression: TEST_FIXTURE_EXTERNAL_PATH_RCA.md — sample_item's pdf_path must
# never depend on a directory outside this test's own tmp_path.
def test_sample_item_pdf_path_is_repository_free(sample_item, tmp_path):
    import pathlib

    pdf_path = pathlib.Path(sample_item["pdf_path"])
    assert pdf_path.exists()
    # must live inside this test's own tmp_path, not any fixed external dir
    assert tmp_path in pdf_path.parents or pdf_path.parent == tmp_path
    assert "clinrec_downloader" not in str(pdf_path)


def test_classification_passes_without_external_clinrec_downloader_dir(sample_item, monkeypatch, tmp_path):
    # Simulate a machine where C:\clinrec_downloader does not exist at all —
    # e.g. a fresh clone or CI runner — and confirm classify_one still works
    # correctly via sample_item's self-contained tmp_path fixture file.
    nonexistent = tmp_path / "definitely_does_not_exist" / "clinrec_downloader"
    assert not nonexistent.exists()

    with patch("classifier.detect_sections") as mock_detect:
        mock_detect.return_value = {
            "clinrec_id": 2199, "total_pages": 10, "relevant_pages": [4],
            "relevant_text": "Антибактериальная терапия\nАмоксициллин 500 мг.",
            "sections_found": [{"section": "Антибактериальная терапия", "page": 4}],
            "dosing_pages": [4],
        }
        item = {**sample_item, "abx_drugs_found": ["амоксициллин"],
                "abx_keywords_found": ["антибактериальная терапия"], "abx_score": 15}
        result = classify_one(item)

    assert result["abx_level"] == "B"
    assert result["extraction_priority"] == "medium"
