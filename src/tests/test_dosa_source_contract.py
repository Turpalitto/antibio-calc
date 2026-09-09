from __future__ import annotations

import json

from src.pipeline.extraction.dosa_source_contract import (
    MATCH_BY_CR_ID,
    MATCH_BY_MKB,
    MATCH_BY_NAME,
    NO_MATCH,
    build_dosa_index,
    build_source_contract,
    match_disease_to_dosa,
    normalize_mkb,
)

KB = [
    {"code_version": "654_2", "guideline_name": "Внебольничная пневмония у взрослых",
     "clinrec_id": 654, "pdf_file": "a.pdf", "pdf_sha256": "s1",
     "publication_date": "2024", "extraction_model": "m",
     "regimens": [
         {"antibiotic": "ц", "dose": "0,5", "unit": "г", "frequency": "3 раза",
          "route": "внутрь", "duration": None, "age_group": "взрослые",
          "page_number": 5, "section_name": "3.1", "source_quote": "q1", "mkb": "J18"},
     ]},
    {"code_version": "179_2", "guideline_name": "Острый аппендицит и перитонит у детей",
     "clinrec_id": 179, "pdf_file": "b.pdf", "pdf_sha256": "s2",
     "regimens": [
         {"antibiotic": "а", "dose": "100", "unit": "мг", "frequency": "2",
          "route": "в/в", "duration": "7", "age_group": "дети",
          "page_number": 9, "section_name": "1.2", "source_quote": "q2", "mkb": "K35.8"},
     ]},
    {"code_version": "566_1", "guideline_name": "Болезнь Лайма у взрослых",
     "clinrec_id": 566, "pdf_file": "c.pdf", "pdf_sha256": "s3",
     "regimens": [
         {"antibiotic": "т", "dose": "200", "unit": "мг", "frequency": "2",
          "route": "внутрь", "duration": "14", "age_group": "взрослые",
          "page_number": 12, "section_name": "2.1", "source_quote": "q3", "mkb": "A69.20"},
     ]},
]


def _db():
    return {"recommendations": [
        {"id": "cap_adult", "name": "Внебольничная пневмония у взрослых",
         "cr_id": "654_2", "cr_year": 2024, "mkb10": ["J18"], "calculation_blocked": True},
        {"id": "intraabdominal_infection", "name": "Интраабдоминальная инфекция (осложнённый аппендицит, перитонит)",
         "cr_id": "—", "cr_year": None, "mkb10": ["K35.8"], "calculation_blocked": True},
        {"id": "lyme_disease", "name": "Болезнь Лайма (боррелиоз)",
         "cr_id": "—", "cr_year": None, "mkb10": ["A69.20"], "calculation_blocked": True},
        {"id": "prostatitis", "name": "Простатит (острый и хронический бактериальный)",
         "cr_id": "—", "cr_year": None, "mkb10": ["N41.0"], "calculation_blocked": True},
    ]}


def test_normalize_mkb_string_and_list():
    assert normalize_mkb("J18") == ["J18"]
    assert normalize_mkb(["J18", None, " K35.8 "]) == ["J18", "K35.8"]
    assert normalize_mkb(None) == []


def test_match_by_exact_cr_id():
    index = build_dosa_index(KB)
    result = match_disease_to_dosa({"cr_id": "654_2", "mkb10": ["J18"], "name": "x"}, index)
    assert result["basis"] == MATCH_BY_CR_ID
    assert result["guideline"]["code_version"] == "654_2"


def test_match_by_mkb_overlap_for_dash_cr():
    index = build_dosa_index(KB)
    result = match_disease_to_dosa({"cr_id": "—", "mkb10": ["K35.8"], "name": "x"}, index)
    assert result["basis"] == MATCH_BY_MKB
    assert result["guideline"]["code_version"] == "179_2"


def test_match_by_name_keyword():
    index = build_dosa_index(KB)
    result = match_disease_to_dosa({"cr_id": "—", "mkb10": ["A69.20"], "name": "Болезнь Лайма (боррелиоз)"}, index)
    assert result["basis"] == MATCH_BY_MKB


def test_no_match_when_nothing_hits():
    index = build_dosa_index(KB)
    result = match_disease_to_dosa({"cr_id": "—", "mkb10": ["N41.0"], "name": "Простатит"}, index)
    assert result["basis"] == NO_MATCH
    assert result["guideline"] is None


def test_build_source_contract_counts_and_never_unblocks(tmp_path):
    dbp = tmp_path / "db.json"
    kbp = tmp_path / "kb.json"
    dbp.write_text(json.dumps(_db()), encoding="utf-8")
    kbp.write_text(json.dumps(KB), encoding="utf-8")
    report = build_source_contract(dbp, kbp)
    assert report["artifact_type"] == "DOSA_SOURCE_LAYER_CONTRACTS"
    assert report["disease_count"] == 4
    assert report["matched_count"] == 3
    assert report["match_breakdown"] == {
        "exact_cr_id": 1, "mkb_overlap": 2, "name_keyword": 0, "no_match": 1,
    }
    by_id = {row["disease_id"]: row for row in report["rows"]}
    assert by_id["cap_adult"]["calculation_blocked"] is True
    assert by_id["cap_adult"]["evidence_count"] == 1
    assert by_id["cap_adult"]["evidence"][0]["source_quote"] == "q1"
    assert by_id["cap_adult"]["guideline"]["pdf_sha256"] == "s1"
    assert by_id["prostatitis"]["match_basis"] == NO_MATCH
    assert by_id["prostatitis"]["guideline"] is None
