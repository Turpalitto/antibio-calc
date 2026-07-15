"""Milestone 2: JsonDiagnosisProvider — diagnosis_index.json -> DiagnosisEntry."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clinical_engine.models import EngineError, EngineErrorCode
from clinical_engine.readers.diagnosis_reader import JsonDiagnosisProvider


class TestLoadErrors:
    def test_missing_file_raises_engine_error(self, tmp_path: Path) -> None:
        with pytest.raises(EngineError) as exc_info:
            JsonDiagnosisProvider(tmp_path / "nope.json")
        assert exc_info.value.code is EngineErrorCode.DIAGNOSIS_INDEX_NOT_FOUND

    def test_non_array_json_raises_engine_error(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text('{"not": "an array"}', encoding="utf-8")
        with pytest.raises(EngineError) as exc_info:
            JsonDiagnosisProvider(bad)
        assert exc_info.value.code is EngineErrorCode.RESOURCE_PARSE_ERROR


class TestObjectForm:
    """Draft production index uses {"meta": ..., "entries": [...]}."""

    def _write(self, tmp_path: Path) -> Path:
        doc = {
            "meta": {"status": "AUTO_GENERATED_DRAFT", "guideline_set_version": "draft-auto"},
            "entries": [
                {
                    "guideline_id": "343",
                    "diagnosis_name": "брюшной тиф",
                    "icd10_codes": ["A01.0"],
                    "guideline_title": "Брюшной тиф",
                    "guideline_year": 2024,
                    "guideline_revision_date": None,
                    "source_url": "",
                }
            ],
        }
        p = tmp_path / "diagnosis_index.json"
        p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        return p

    def test_object_form_loads_entries(self, tmp_path: Path) -> None:
        provider = JsonDiagnosisProvider(self._write(tmp_path))
        matches = provider.lookup("брюшной тиф", None)
        assert len(matches) == 1
        assert matches[0].guideline_id == "343"

    def test_object_form_exposes_meta(self, tmp_path: Path) -> None:
        provider = JsonDiagnosisProvider(self._write(tmp_path))
        assert provider.meta["status"] == "AUTO_GENERATED_DRAFT"

    def test_bare_list_still_works_with_empty_meta(self, tmp_path: Path) -> None:
        p = tmp_path / "bare.json"
        p.write_text(json.dumps([{"guideline_id": "1", "diagnosis_name": "x",
                                   "icd10_codes": [], "guideline_title": "",
                                   "guideline_year": None, "guideline_revision_date": None,
                                   "source_url": ""}]), encoding="utf-8")
        provider = JsonDiagnosisProvider(p)
        assert provider.meta == {}
        assert provider.lookup("x", None)

    def test_real_draft_index_loads(self) -> None:
        # The actual generated production draft must load and be non-trivial.
        path = Path("clinical_engine/resources/diagnosis_index.json")
        if not path.exists():
            pytest.skip("draft diagnosis_index.json not generated in this checkout")
        provider = JsonDiagnosisProvider(path)
        assert provider.meta.get("status") == "AUTO_GENERATED_DRAFT"


class TestLookup:
    def test_lookup_by_diagnosis_name_case_insensitive(
        self, diagnosis_index_path: Path
    ) -> None:
        provider = JsonDiagnosisProvider(diagnosis_index_path)
        matches = provider.lookup("Vnebolnichnaya Pnevmoniya", None)
        assert len(matches) == 1
        assert matches[0].guideline_id == "g_cap_adult"
        assert matches[0].guideline_year == 2024

    def test_lookup_by_icd10(self, diagnosis_index_path: Path) -> None:
        provider = JsonDiagnosisProvider(diagnosis_index_path)
        matches = provider.lookup(None, "J18.9")
        assert len(matches) == 1
        assert matches[0].guideline_id == "g_cap_adult"

    def test_lookup_by_icd10_case_insensitive(self, diagnosis_index_path: Path) -> None:
        provider = JsonDiagnosisProvider(diagnosis_index_path)
        matches = provider.lookup(None, "n30")
        assert len(matches) == 1
        assert matches[0].guideline_id == "g_cystitis"

    def test_no_match_returns_empty_list_not_error(self, diagnosis_index_path: Path) -> None:
        provider = JsonDiagnosisProvider(diagnosis_index_path)
        assert provider.lookup("completely unknown disease", None) == []
        assert provider.lookup(None, "Z99") == []
        assert provider.lookup(None, None) == []

    def test_diagnosis_and_icd10_both_given_merges_without_duplicates(
        self, diagnosis_index_path: Path
    ) -> None:
        provider = JsonDiagnosisProvider(diagnosis_index_path)
        matches = provider.lookup("vnebolnichnaya pnevmoniya", "J18")
        guideline_ids = [m.guideline_id for m in matches]
        assert guideline_ids == ["g_cap_adult"]  # not duplicated

    def test_entry_shape(self, diagnosis_index_path: Path) -> None:
        provider = JsonDiagnosisProvider(diagnosis_index_path)
        entry = provider.lookup("ostryi sinusit", None)[0]
        assert entry.icd10_codes == ("J01",)
        assert entry.guideline_title == "Acute sinusitis"
        assert entry.guideline_revision_date is None
        assert entry.source_url == "https://cr.minzdrav.gov.ru/recomend/200"
