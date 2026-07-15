"""Milestone 2: DrugReferenceReader — drugs_reference JSON -> DrugInfo."""

from __future__ import annotations

from pathlib import Path

import pytest

from clinical_engine.models import EngineError, EngineErrorCode, PregnancyCategory
from clinical_engine.readers.drug_reference_reader import DrugReferenceReader


class TestLoadErrors:
    def test_missing_file_raises_engine_error(self, tmp_path: Path) -> None:
        with pytest.raises(EngineError) as exc_info:
            DrugReferenceReader(tmp_path / "nope.json")
        assert exc_info.value.code is EngineErrorCode.DRUG_REFERENCE_NOT_FOUND

    def test_malformed_json_raises_engine_error(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(EngineError) as exc_info:
            DrugReferenceReader(bad)
        assert exc_info.value.code is EngineErrorCode.RESOURCE_PARSE_ERROR


class TestGetDrugInfo:
    def test_known_drug(self, drug_reference_path: Path) -> None:
        reader = DrugReferenceReader(drug_reference_path)
        info = reader.get_drug_info("amoxicillin")
        assert info is not None
        assert info.inn == "Амоксициллин"
        assert info.drug_class == "Полусинтетические пенициллины широкого спектра"
        assert info.pregnancy_category is PregnancyCategory.ALLOWED

    def test_unknown_drug_returns_none(self, drug_reference_path: Path) -> None:
        reader = DrugReferenceReader(drug_reference_path)
        assert reader.get_drug_info("does_not_exist") is None

    def test_underscore_keys_are_skipped(self, drug_reference_path: Path) -> None:
        reader = DrugReferenceReader(drug_reference_path)
        assert reader.get_drug_info("_note") is None

    def test_forms_mapped(self, drug_reference_path: Path) -> None:
        reader = DrugReferenceReader(drug_reference_path)
        info = reader.get_drug_info("amoxicillin")
        assert info.forms[0].form_type == "tablet"
        assert info.forms[0].concentration == "500 мг"
        assert info.forms[1].concentration_mg_per_ml == 50

    def test_dilution_mapped_known_fields_only(self, drug_reference_path: Path) -> None:
        reader = DrugReferenceReader(drug_reference_path)
        info = reader.get_drug_info("levofloxacin")
        route = info.dilution["iv_infusion"]
        assert route.infusion_time_min == 60
        assert route.cautions == "Не смешивать с гепарином."
        assert route.steps[0] == "Развести в 100 мл 0.9% NaCl."
        # "child_solvent_warning" is not a DilutionRoute field -- dropped, not crashed on.
        assert not hasattr(route, "child_solvent_warning")

    def test_missing_contraindications_and_pediatric_dosing_are_none(
        self, drug_reference_path: Path
    ) -> None:
        reader = DrugReferenceReader(drug_reference_path)
        info = reader.get_drug_info("amoxicillin")
        assert info.contraindications is None
        assert info.pediatric_dosing is None


class TestPregnancyClassification:
    """See DECISIONS.md 2026-07-10 for the classification rule."""

    def test_prohibited_unconditional(self, drug_reference_path: Path) -> None:
        reader = DrugReferenceReader(drug_reference_path)
        assert reader.get_pregnancy_category("doxycycline") is PregnancyCategory.PROHIBITED

    def test_trimester_conditional_is_caution_not_prohibited_or_allowed(
        self, drug_reference_path: Path
    ) -> None:
        reader = DrugReferenceReader(drug_reference_path)
        # raw text: "Противопоказан в I и III триместрах" -- conditional, not absolute
        assert reader.get_pregnancy_category("levofloxacin") is PregnancyCategory.CAUTION

    def test_caution_with_parenthetical(self, drug_reference_path: Path) -> None:
        reader = DrugReferenceReader(drug_reference_path)
        assert reader.get_pregnancy_category("gentamicin") is PregnancyCategory.CAUTION

    def test_allowed_unconditional(self, drug_reference_path: Path) -> None:
        reader = DrugReferenceReader(drug_reference_path)
        assert reader.get_pregnancy_category("amoxicillin") is PregnancyCategory.ALLOWED

    def test_missing_pregnancy_category_is_unknown(self, drug_reference_path: Path) -> None:
        reader = DrugReferenceReader(drug_reference_path)
        assert reader.get_pregnancy_category("unmapped_drug") is PregnancyCategory.UNKNOWN

    def test_get_pregnancy_category_unknown_drug_ref_returns_none(
        self, drug_reference_path: Path
    ) -> None:
        reader = DrugReferenceReader(drug_reference_path)
        assert reader.get_pregnancy_category("does_not_exist") is None


class TestResolveDrugRef:
    def test_resolve_by_inn_case_insensitive(self, drug_reference_path: Path) -> None:
        reader = DrugReferenceReader(drug_reference_path)
        assert reader.resolve_drug_ref("Амоксициллин") == "amoxicillin"
        assert reader.resolve_drug_ref("амоксициллин") == "amoxicillin"

    def test_resolve_by_key_itself(self, drug_reference_path: Path) -> None:
        reader = DrugReferenceReader(drug_reference_path)
        assert reader.resolve_drug_ref("amoxicillin") == "amoxicillin"

    def test_resolve_unknown_returns_none(self, drug_reference_path: Path) -> None:
        reader = DrugReferenceReader(drug_reference_path)
        assert reader.resolve_drug_ref("совершенно неизвестный препарат") is None


class TestConvenienceAccessors:
    def test_get_interactions(self, drug_reference_path: Path) -> None:
        reader = DrugReferenceReader(drug_reference_path)
        assert "аллопуринолом" in reader.get_interactions("amoxicillin")
        assert reader.get_interactions("does_not_exist") is None

    def test_get_renal_adjustment(self, drug_reference_path: Path) -> None:
        reader = DrugReferenceReader(drug_reference_path)
        assert reader.get_renal_adjustment("amoxicillin") == "КК<30: удлинить интервал"
        assert reader.get_renal_adjustment("gentamicin") is not None
        assert reader.get_renal_adjustment("does_not_exist") is None
