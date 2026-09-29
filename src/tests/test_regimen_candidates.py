from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from src.pipeline.extraction.regimen_candidates import (
    CandidateRowGroup,
    GuidelineCandidateSpec,
    _frequency_interval_is_exact,
    _frequency_values,
    candidate_spec_from_mapping,
    extract_regimen_candidates,
    load_candidate_spec,
    persist_candidate_artifact,
    write_candidate_artifact,
)


@pytest.mark.parametrize(("wording", "expected"), [
    ("500 мг каждые 12 ч", (2, 2)),
    ("2 г каждые 6-8 ч", (3, 4)),
    ("1 г каждые 24 часа", (1, 1)),
    ("1 г каждые 8 ч", (3, 3)),
    # F-6: every pre-existing case was an exact divisor of 24, so the `24 // hours`
    # floor-rounding bug (M-2) was untestable by construction.  These are not.
    ("1 г каждые 7 ч", (3, 4)),
    ("1 г каждые 5 ч", (4, 5)),
    ("1 г каждые 9 ч", (2, 3)),
    ("1 г каждые 11 ч", (2, 3)),
    ("1 г каждые 13 ч", (1, 2)),
])
def test_frequency_values_supports_hour_abbreviation_and_range(wording, expected):
    assert _frequency_values(wording) == expected


@pytest.mark.parametrize(("wording", "exact"), [
    ("500 мг каждые 12 ч", True),
    ("1 г каждые 8 ч", True),
    ("1 г каждые 24 часа", True),
    ("2 г каждые 6-8 ч", True),          # a genuine 6..8 range is still exact per end
    ("1 г каждые 7 ч", False),           # M-2: no whole number of doses per day
    ("1 г каждые 5 ч", False),
    ("1 г каждые 9 ч", False),
    ("3 раза в день", True),             # not an hour interval at all
    ("1 раз в сутки", True),
])
def test_frequency_interval_is_exact(wording, exact):
    assert _frequency_interval_is_exact(wording) is exact


def test_m2_non_divisor_interval_is_flagged_not_silently_floored():
    """M-2: 'каждые 7 ч' must never be reported as exactly 3/day."""
    assert _frequency_values("1 г каждые 7 ч") == (3, 4)
    assert _frequency_interval_is_exact("1 г каждые 7 ч") is False


def _aom_spec() -> GuidelineCandidateSpec:
    return GuidelineCandidateSpec(
        guideline_id="314_3",
        guideline_title="Отит средний острый",
        approval_year=2024,
        source_url="https://cr.minzdrav.gov.ru/view-cr/314_3",
        diagnosis="Острый средний отит у детей",
        icd10=("H65.0", "H65.1", "H66.0"),
        table_pages=(21, 22, 23),
        duration="7-10 days",
        duration_page=25,
        duration_wording="Рекомендована стандартная длительность курса антибиотикотерапии (7-10 дней).",
    )


def test_current_aom_pdf_yields_source_linked_safe_candidates():
    pdf = Path(r"C:\ANTIBIO\tmp\pdfs\aom\official_314.pdf")
    if not pdf.is_file():
        pytest.skip("current official CR 314_3 snapshot not available")
    candidates = extract_regimen_candidates(pdf, _aom_spec())
    assert len(candidates) == 8
    amoxicillin = next(item for item in candidates if item["atc"] == "J01CA04")
    assert amoxicillin["dose"] == {
        "value_min": 50.0, "value_max": 60.0, "unit": "mg/kg/day",
        "basis": "MG_KG_PER_DAY", "route": "oral",
        "frequency_min_per_day": 2, "frequency_max_per_day": 3,
        "duration": "7-10 days", "maximum_dose": "NOT_STATED_IN_TABLE_ROW",
    }
    assert "50-601" not in amoxicillin["source"]["wording"]
    assert amoxicillin["guideline"]["pdf_sha256"] == "sha256:6022928b4138f2a2ab9319c34e2a3b2c13bb53f2d08add5eb3fa83eed296665d"
    blocked = {reason for item in candidates for reason in item["blocking_reasons"]}
    assert {"MULTIPLE_DOSE_STRATA", "ROUTE_NOT_EXACT"}.issubset(blocked)


def test_candidate_artifact_enters_versioned_kb_as_queued_review(tmp_path):
    artifact = tmp_path / "314.json"
    artifact.write_text(json.dumps({
        "artifact_type": "EXTRACTED_REGIMEN_CANDIDATES", "guideline_id": "314",
        "candidates": [{
            "candidate_id": "erc-1", "calculation_ready": True, "blocking_reasons": [],
            "dose": {"value_min": 50, "value_max": 60},
            "source": {"pdf_path": "source.pdf", "page": 21, "table_row": 3,
                       "wording": "Амоксициллин 50-60 мг/кг/сут",
                       "cells": [{"col": 2, "bbox": [1, 2, 3, 4], "confidence": 0.97}]},
        }],
    }, ensure_ascii=False), encoding="utf-8")
    db = tmp_path / "kb.sqlite"
    stats = persist_candidate_artifact(artifact, db)
    assert stats == {"added": 1, "reviews": 1, "conflicts": 0, "superseded": 0}
    connection = sqlite3.connect(db)
    row = connection.execute(
        "SELECT type,status,validation_status,review_status FROM objects"
    ).fetchone()
    connection.close()
    assert row == ("RegimenCandidate", "draft", "pending", "queued")


def test_candidate_spec_loader_preserves_revision_and_expected_hash(tmp_path):
    path = tmp_path / "314.json"
    payload = {
        "guideline_id": "314",
        "guideline_title": "Отит средний острый",
        "approval_year": 2024,
        "source_url": "https://cr.minzdrav.gov.ru/recomend/314",
        "diagnosis": "Острый средний отит у детей",
        "icd10": ["H65.0", "H65.1", "H66.0"],
        "table_pages": [21, 22, 23],
        "duration": "7-10 days",
        "duration_page": 25,
        "duration_wording": "7-10 дней",
        "rubricator_revision": "314",
        "expected_pdf_sha256": "sha256:" + "a" * 64,
        "row_groups": [{
            "page": 19, "row_start": 7, "row_end": 11,
            "drug_col": 0, "dose_col": 2, "duration_col": 4,
            "therapy_line": "first", "blocking_reasons": ["FOOTNOTE_PENDING"],
            "population_constraints": {"age_years_max_exclusive": 12},
        }],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    spec = load_candidate_spec(path)
    assert spec == candidate_spec_from_mapping(payload)
    assert spec.rubricator_revision == "314"
    assert spec.expected_pdf_sha256 == "sha256:" + "a" * 64
    assert spec.row_groups[0].row_start == 7
    assert spec.row_groups[0].duration_col == 4
    assert spec.row_groups[0].blocking_reasons == ("FOOTNOTE_PENDING",)
    assert spec.row_groups[0].population_constraints == {"age_years_max_exclusive": 12}


def test_current_tonsillopharyngitis_pdf_uses_declared_row_groups_and_row_duration():
    matches = list(Path(r"C:\clinrec_downloader\downloads_active").glob(
        "*тонзиллит*фарингит*.pdf"
    ))
    if not matches:
        pytest.skip("current CR 306_3 snapshot not available")
    spec = load_candidate_spec(
        Path("clinical_sources/regimen_candidate_specs/306_3.json")
    )
    candidates = extract_regimen_candidates(matches[0], spec)
    assert len(candidates) == 18
    assert sum(item["calculation_ready"] for item in candidates) == 8
    amoxicillin = next(
        item for item in candidates
        if item["atc"] == "J01CA04" and item["dose"]["route"] == "oral"
    )
    assert amoxicillin["dose"]["value_min"] == 50
    assert amoxicillin["dose"]["frequency_min_per_day"] == 2
    assert amoxicillin["dose"]["frequency_max_per_day"] == 3
    assert amoxicillin["dose"]["duration"] == "10 дней"
    cefixime = next(item for item in candidates if item["atc"] == "J01DD08")
    assert cefixime["dose"]["frequency_min_per_day"] == 1
    assert cefixime["dose"]["frequency_max_per_day"] == 2
    azithromycin = next(item for item in candidates if item["atc"] == "J01FA10")
    assert "DURATION_FOOTNOTE_REVIEW_REQUIRED" in azithromycin["blocking_reasons"]
    cefditoren = next(item for item in candidates if item["atc"] == "J01DD16")
    assert cefditoren["dose"]["basis"] == "FIXED_PER_DOSE"
    assert cefditoren["population_constraints"]["age_years_min_inclusive"] == 12
    parenteral = [item for item in candidates if item["dose"]["route"] != "oral"]
    assert all("DURATION_NOT_EXTRACTED" in item["blocking_reasons"] for item in parenteral)


def test_current_adult_pyelo_pdf_extracts_fixed_and_weight_based_doses():
    pdf = Path(r"C:\clinrec_downloader\downloads_active\Острый пиелонефрит.pdf")
    if not pdf.is_file():
        pytest.skip("current CR 9_3 snapshot not available")
    spec = load_candidate_spec(Path("clinical_sources/regimen_candidate_specs/9_3.json"))
    candidates = extract_regimen_candidates(pdf, spec)
    assert len(candidates) == 21
    cefixime = next(item for item in candidates if item["atc"] == "J01DD08")
    assert cefixime["dose"]["basis"] == "FIXED_PER_DOSE"
    assert cefixime["dose"]["value_min"] == 400
    assert cefixime["dose"]["frequency_min_per_day"] == 1
    assert cefixime["dose"]["duration"] == "10"
    gentamicin = next(item for item in candidates if item["atc"] == "J01GB03")
    assert gentamicin["dose"]["basis"] == "MG_KG_PER_DOSE"
    assert gentamicin["dose"]["value_min"] == 3
    assert gentamicin["dose"]["value_max"] == 5
    severe_ceftriaxone = next(
        item for item in candidates
        if item["atc"] == "J01DD04" and item["therapy_line"] == "severe_susceptible"
    )
    assert severe_ceftriaxone["dose"]["frequency_min_per_day"] == 2
    assert severe_ceftriaxone["dose"]["duration"] == "14"
    assert "ROUTE_NOT_EXACT" in severe_ceftriaxone["blocking_reasons"]


def test_current_pregnancy_uti_pdf_preserves_route_interval_and_missing_duration():
    pdf = Path(r"C:\clinrec_downloader\downloads_active\Инфекция мочевых путей при беременности.pdf")
    if not pdf.is_file():
        pytest.skip("current CR 719_2 snapshot not available")
    spec = load_candidate_spec(Path("clinical_sources/regimen_candidate_specs/719_2.json"))
    candidates = extract_regimen_candidates(pdf, spec)
    assert len(candidates) == 19
    oral_cefixime = next(item for item in candidates if item["atc"] == "J01DD08")
    assert oral_cefixime["dose"]["route"] == "oral"
    assert oral_cefixime["dose"]["value_min"] == 400
    assert oral_cefixime["dose"]["frequency_min_per_day"] == 1
    assert oral_cefixime["dose"]["duration"] == "7 – 10"
    iv_ceftriaxone = next(
        item for item in candidates
        if item["atc"] == "J01DD04" and item["therapy_line"] == "pyelonephritis_empiric"
    )
    assert iv_ceftriaxone["dose"]["route"] == "intravenous"
    assert iv_ceftriaxone["dose"]["frequency_min_per_day"] == 1
    assert "DURATION_NOT_EXTRACTED" in iv_ceftriaxone["blocking_reasons"]


def test_current_child_uti_pdf_keeps_dose_age_strata_explicit_and_fail_closed():
    pdf = Path(r"C:\clinrec_downloader\downloads_active\Инфекция мочевых путей.pdf")
    if not pdf.is_file():
        pytest.skip("current CR 281_3 snapshot not available")
    spec = load_candidate_spec(Path("clinical_sources/regimen_candidate_specs/281_3.json"))
    candidates = extract_regimen_candidates(pdf, spec)
    assert len(candidates) == 8
    amox_clav = next(item for item in candidates if item["atc"] == "J01CR02")
    assert amox_clav["dose"]["value_min"] == 45
    assert amox_clav["dose"]["value_max"] == 60
    assert amox_clav["dose"]["frequency_min_per_day"] == 2
    assert amox_clav["dose"]["frequency_max_per_day"] == 3
    assert amox_clav["population_constraints"] == {"age_years_max_exclusive": 12}
    assert not amox_clav["calculation_ready"]
    nitrofurantoin = next(item for item in candidates if item["atc"] == "J01XE01")
    assert nitrofurantoin["dose"]["duration"] == "5-7 days"
    assert nitrofurantoin["population_constraints"] == {
        "age_years_min_inclusive": 6,
        "age_years_max_inclusive": 12,
    }
    fosfomycin = next(item for item in candidates if item["atc"] == "J01XX01")
    assert fosfomycin["dose"]["value_min"] == 3000
    assert fosfomycin["dose"]["frequency_min_per_day"] == 1
    assert fosfomycin["dose"]["duration"] == "1 day"
    assert fosfomycin["population_constraints"] == {"age_years_min_exclusive": 12}
    assert fosfomycin["calculation_ready"]


def test_current_adult_cap_pdf_extracts_reference_table_but_keeps_it_unbound():
    pdf = Path(r"C:\clinrec_downloader\downloads_active\Внебольничная пневмония у взрослых.pdf")
    if not pdf.is_file():
        pytest.skip("current CR 654_2 snapshot not available")
    spec = load_candidate_spec(Path("clinical_sources/regimen_candidate_specs/654_2.json"))
    candidates = extract_regimen_candidates(pdf, spec)
    assert len(candidates) == 32
    assert not any(item["calculation_ready"] for item in candidates)
    amoxicillin = next(item for item in candidates if item["atc"] == "J01CA04")
    assert amoxicillin["dose"]["value_min"] == 500
    assert amoxicillin["dose"]["value_max"] == 1000
    assert amoxicillin["dose"]["frequency_min_per_day"] == 3
    ceftriaxone = next(
        item for item in candidates
        if item["drug"] == "Цефтриаксон" and item["atc"] == "J01DD04"
    )
    assert ceftriaxone["dose"]["frequency_min_per_day"] == 1
    assert ceftriaxone["dose"]["frequency_max_per_day"] == 2
    assert "DOSE_TABLE_NOT_LINKED_TO_TREATMENT_SCENARIO" in ceftriaxone["blocking_reasons"]


def test_current_child_cap_pdf_preserves_age_strata_and_hour_intervals():
    pdf = Path(r"C:\clinrec_downloader\downloads_active\Пневмония (внебольничная).pdf")
    if not pdf.is_file():
        pytest.skip("current CR 714_2 snapshot not available")
    spec = load_candidate_spec(Path("clinical_sources/regimen_candidate_specs/714_2.json"))
    candidates = extract_regimen_candidates(pdf, spec)
    assert len(candidates) == 19
    assert not any(item["calculation_ready"] for item in candidates)
    azithromycin = next(item for item in candidates if item["atc"] == "J01FA10")
    assert azithromycin["dose"]["value_min"] == 10
    assert azithromycin["dose"]["frequency_min_per_day"] == 1
    assert azithromycin["dose"]["duration"] == "3 days"
    linezolid = next(item for item in candidates if item["atc"] == "J01XX08")
    assert linezolid["dose"]["frequency_min_per_day"] == 3
    ceftriaxone = next(item for item in candidates if item["atc"] == "J01DD04")
    assert ceftriaxone["dose"]["frequency_min_per_day"] == 1
    assert ceftriaxone["population_constraints"] == {"age_years_max_exclusive": 12}


def test_candidate_spec_missing_required_field_fails_closed():
    with pytest.raises(ValueError, match="guideline_title"):
        candidate_spec_from_mapping({"guideline_id": "314"})


def test_candidate_artifact_rejects_unexpected_pdf_hash(tmp_path):
    pdf = tmp_path / "not-the-approved-snapshot.pdf"
    pdf.write_bytes(b"%PDF-not-the-approved-snapshot")
    spec = GuidelineCandidateSpec(
        **{**_aom_spec().__dict__, "expected_pdf_sha256": "sha256:" + "0" * 64}
    )
    with pytest.raises(ValueError, match="source PDF hash mismatch"):
        write_candidate_artifact(tmp_path / "artifact.json", pdf_path=pdf, spec=spec)


# ---------------------------------------------------------------------------
# F-5 -- the dose-extraction test surface must not depend on a Windows-only corpus.
# These tests build a ruled table PDF in tmp_path and exercise the same pure
# extraction logic the corpus tests above cover against real guidelines.
# ---------------------------------------------------------------------------

def _spec(rows_spec, *, guideline_id="999_1", duration="NOT_STATED_IN_ROW"):
    return GuidelineCandidateSpec(
        guideline_id=guideline_id,
        guideline_title="Синтетическая таблица",
        approval_year=2024,
        source_url="https://example.test/cr",
        diagnosis="Тестовая инфекция",
        icd10=("J18.9",),
        table_pages=(1,),
        duration=duration,
        duration_page=1,
        duration_wording="Длительность указана в строке таблицы.",
        row_groups=rows_spec,
    )


def _extract(tmp_path, cyrillic_font, rows, row_group, *, name="table.pdf"):
    from src.tests.table_pdf_fixture import build_table_pdf

    pdf = build_table_pdf(tmp_path / name, rows, cyrillic_font)
    return extract_regimen_candidates(pdf, _spec(row_group))


def _normalize_chars(items):
    """Undo PDF glyph substitutions the synthetic font introduces.

    The renderer emits U+00A0 for spaces and U+00AD for hyphens; both are real
    characters that occur in genuine guidelines, so the fixture normalises them
    rather than making the parsers untestable.
    """
    import json
    blob = json.dumps(items, ensure_ascii=False)
    blob = blob.replace("\\u00a0", " ").replace("\\u00ad", "-")
    return json.loads(blob)


def test_f5_weight_per_day_dose_is_extracted(tmp_path, cyrillic_font):
    rows = [
        ["Препарат", "Доза (дети)", "Длительность"],
        ["Амоксициллин (АТХ: J01CA04)", "50-60 мг/кг/сут в 2-3 приема", "7-10 дней"],
    ]
    group = (CandidateRowGroup(
        page=1, table_index=0, row_start=1, row_end=1, drug_col=0, dose_col=1,
        duration_col=2, therapy_line="first", atc="J01CA04", drug="Амоксициллин",
    ),)
    candidates = _normalize_chars(_extract(tmp_path, cyrillic_font, rows, group))
    assert len(candidates) == 1
    dose = candidates[0]["dose"]
    assert dose["basis"] == "MG_KG_PER_DAY"
    assert dose["unit"] == "mg/kg/day"
    assert (dose["value_min"], dose["value_max"]) == (50.0, 60.0)
    assert (dose["frequency_min_per_day"], dose["frequency_max_per_day"]) == (2, 3)
    assert dose["duration"] == "7-10 дней"
    assert candidates[0]["atc"] == "J01CA04"


def test_f5_weight_per_dose_dose_is_distinguished(tmp_path, cyrillic_font):
    rows = [
        ["Препарат", "Доза (дети)", "Длительность"],
        ["Амоксициллин (АТХ: J01CA04)", "3-5 мг/кг в 1 введение", "10 дней"],
    ]
    group = (CandidateRowGroup(
        page=1, table_index=0, row_start=1, row_end=1, drug_col=0, dose_col=1,
        duration_col=2, therapy_line="first", atc="J01CA04", drug="Амоксициллин",
    ),)
    candidates = _normalize_chars(_extract(tmp_path, cyrillic_font, rows, group))
    assert len(candidates) == 1
    assert candidates[0]["dose"]["basis"] == "MG_KG_PER_DOSE"
    assert candidates[0]["dose"]["unit"] == "mg/kg/dose"
    assert candidates[0]["dose"]["frequency_min_per_day"] == 1


def test_f5_fixed_dose_in_grams_is_converted_to_milligrams(tmp_path, cyrillic_font):
    rows = [
        ["Препарат", "Доза (дети)", "Длительность"],
        ["Амоксициллин (АТХ: J01CA04)", "0,5 г 3 раза в сутки", "7 дней"],
    ]
    group = (CandidateRowGroup(
        page=1, table_index=0, row_start=1, row_end=1, drug_col=0, dose_col=1,
        duration_col=2, therapy_line="first", atc="J01CA04", drug="Амоксициллин",
    ),)
    candidates = _normalize_chars(_extract(tmp_path, cyrillic_font, rows, group))
    assert len(candidates) == 1
    dose = candidates[0]["dose"]
    assert dose["basis"] == "FIXED_PER_DOSE"
    assert dose["value_min"] == 500.0
    assert dose["frequency_min_per_day"] == 3


def test_f5_row_without_a_dose_is_skipped(tmp_path, cyrillic_font):
    rows = [
        ["Препарат", "Доза (дети)", "Длительность"],
        ["Амоксициллин (АТХ: J01CA04)", "по клинической ситуации", "7 дней"],
    ]
    group = (CandidateRowGroup(
        page=1, table_index=0, row_start=1, row_end=1, drug_col=0, dose_col=1,
        duration_col=2, therapy_line="first", atc="J01CA04", drug="Амоксициллин",
    ),)
    assert _extract(tmp_path, cyrillic_font, rows, group) == []


def test_c7_unresolved_route_fails_closed_instead_of_defaulting_to_oral(tmp_path, cyrillic_font):
    """C-7: the fallback branch used to set route='oral' with NO blocking reason."""
    rows = [
        ["Препарат", "Доза (дети)", "Длительность"],
        ["Амоксициллин (АТХ: J01CA04)", "50 мг/кг/сут в 2 приема", "7 дней"],
    ]
    group = (CandidateRowGroup(
        page=1, table_index=0, row_start=1, row_end=1, drug_col=0, dose_col=1,
        duration_col=2, therapy_line="first", atc="J01CA04", drug="Амоксициллин",
    ),)
    candidates = _extract(tmp_path, cyrillic_font, rows, group)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["dose"]["route"] == "unknown"
    assert "ROUTE_NOT_EXTRACTED" in candidate["blocking_reasons"]
    assert candidate["calculation_ready"] is False, \
        "an unresolved route must never be calculation-ready"


def test_c7_oral_route_still_resolves(tmp_path, cyrillic_font):
    rows = [
        ["Препарат", "Доза (дети)", "Длительность"],
        ["Амоксициллин (АТХ: J01CA04), внутрь", "50 мг/кг/сут в 2 приема", "7 дней"],
    ]
    group = (CandidateRowGroup(
        page=1, table_index=0, row_start=1, row_end=1, drug_col=0, dose_col=1,
        duration_col=2, therapy_line="first", atc="J01CA04", drug="Амоксициллин",
    ),)
    candidates = _extract(tmp_path, cyrillic_font, rows, group)
    assert len(candidates) == 1
    assert candidates[0]["dose"]["route"] == "oral"
    assert "ROUTE_NOT_EXTRACTED" not in candidates[0]["blocking_reasons"]


def test_c7_iv_route_resolves_and_ambiguous_routes_block(tmp_path, cyrillic_font):
    iv_rows = [
        ["Препарат", "Доза (дети)", "Длительность"],
        ["Цефтриаксон (АТХ: J01DD04) в/в", "50 мг/кг/сут в 1 введение", "10 дней"],
    ]
    group = (CandidateRowGroup(
        page=1, table_index=0, row_start=1, row_end=1, drug_col=0, dose_col=1,
        duration_col=2, therapy_line="first", atc="J01DD04", drug="Цефтриаксон",
    ),)
    candidates = _normalize_chars(_extract(tmp_path, cyrillic_font, iv_rows, group, name="iv.pdf"))
    assert candidates[0]["dose"]["route"] == "intravenous"

    ambiguous = [
        ["Препарат", "Доза (дети)", "Длительность"],
        ["Цефтриаксон (АТХ: J01DD04) в/в или внутрь", "50 мг/кг/сут в 1 введение", "10 дней"],
    ]
    candidates = _normalize_chars(
        _extract(tmp_path, cyrillic_font, ambiguous, group, name="amb.pdf")
    )
    assert candidates[0]["dose"]["route"] == "multiple_routes"
    assert "ROUTE_NOT_EXACT" in candidates[0]["blocking_reasons"]
    assert candidates[0]["calculation_ready"] is False


def test_m2_non_divisor_interval_blocks_the_candidate(tmp_path, cyrillic_font):
    """M-2 end to end: 'каждые 7 ч' must not become a ready 3/day regimen."""
    rows = [
        ["Препарат", "Доза (дети)", "Длительность"],
        ["Амоксициллин (АТХ: J01CA04)", "50 мг/кг/сут каждые 7 ч", "7 дней"],
    ]
    group = (CandidateRowGroup(
        page=1, table_index=0, row_start=1, row_end=1, drug_col=0, dose_col=1,
        duration_col=2, therapy_line="first", atc="J01CA04", drug="Амоксициллин",
    ),)
    candidates = _normalize_chars(_extract(tmp_path, cyrillic_font, rows, group))
    assert len(candidates) == 1
    dose = candidates[0]["dose"]
    assert (dose["frequency_min_per_day"], dose["frequency_max_per_day"]) == (3, 4)
    assert "FREQUENCY_INTERVAL_NOT_DIVISIBLE" in candidates[0]["blocking_reasons"]
    assert candidates[0]["calculation_ready"] is False


def test_l31_footnote_marker_does_not_corrupt_the_dose(tmp_path, cyrillic_font):
    """L-31: '1x10^9' style superscripts must not swallow the dose into a footnote."""
    rows = [
        ["Препарат", "Доза (дети)", "Длительность"],
        ["Амоксициллин (АТХ: J01CA04)", "50 мг/кг/сут¹ в 2 приема", "7 дней"],
    ]
    group = (CandidateRowGroup(
        page=1, table_index=0, row_start=1, row_end=1, drug_col=0, dose_col=1,
        duration_col=2, therapy_line="first", atc="J01CA04", drug="Амоксициллин",
    ),)
    candidates = _normalize_chars(_extract(tmp_path, cyrillic_font, rows, group))
    assert len(candidates) == 1
    assert candidates[0]["dose"]["value_min"] == 50.0
    assert "501" not in candidates[0]["source"]["wording"]


def test_missing_row_group_fails_closed(tmp_path, cyrillic_font):
    """A hash-pinned row span that is not in the PDF must raise, not silently pass."""
    from src.tests.table_pdf_fixture import build_table_pdf

    rows = [["Препарат", "Доза (дети)", "Длительность"],
            ["Амоксициллин (АТХ: J01CA04)", "50 мг/кг/сут в 2 приема", "7 дней"]]
    pdf = build_table_pdf(tmp_path / "t.pdf", rows, cyrillic_font)
    group = (CandidateRowGroup(
        page=1, table_index=0, row_start=99, row_end=99, drug_col=0, dose_col=1,
        duration_col=2, therapy_line="first", atc="J01CA04", drug="Амоксициллин",
    ),)
    with pytest.raises(ValueError, match="source row group missing"):
        extract_regimen_candidates(pdf, _spec(group))
