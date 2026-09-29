"""Tests for models.py -- NormalizedRegimen, ConfidenceScore, ParserResult.

Covers M2 (from_dict dropped all 8 RC-030 range fields) and M5/M18.
"""

from __future__ import annotations

import math
from dataclasses import is_dataclass

import pytest

from medical_normalizer.models import (
    MISSING_FIELD_INPUT,
    UNSET,
    ConfidenceScore,
    DrugComponent,
    NormalizedRegimen,
    ParserResult,
)


class TestDataclassBasics:
    def test_regimen_is_dataclass(self):
        assert is_dataclass(NormalizedRegimen)

    def test_component_is_dataclass(self):
        assert is_dataclass(DrugComponent)

    def test_component_truthiness(self):
        assert bool(DrugComponent(name="Амоксициллин")) is True
        assert bool(DrugComponent(name="")) is False

    def test_to_dict_has_no_range_keys(self):
        # the authoritative serializer must stay byte-identical
        d = NormalizedRegimen(dose_min=1.0, dose_max=2.0).to_dict()
        assert "dose_min" not in d and "dose_max" not in d

    def test_to_dict_with_range_has_range_keys(self):
        d = NormalizedRegimen(dose_min=1.0, dose_max=2.0).to_dict_with_range()
        assert d["dose_min"] == 1.0 and d["dose_max"] == 2.0


class TestM2FromDictRestoresRange:
    """M2: from_dict silently dropped all 8 RC-030 range fields, making
    to_dict_with_range() -> from_dict() lossy."""

    def _full_regimen(self) -> NormalizedRegimen:
        return NormalizedRegimen(
            source_id=1,
            clinrec_id=2,
            drug_original="Амоксициллин+клавулановая кислота",
            drug_normalized="Амоксициллин + клавулановая кислота",
            drug_components=[
                DrugComponent(name="Амоксициллин", dose_value=875.0, dose_unit="mg"),
                DrugComponent(name="Клавулановая кислота", dose_value=125.0, dose_unit="mg"),
            ],
            atc_code="J01CR02",
            dose_value=20.0,
            dose_unit="mg/kg",
            dose_min=20.0,
            dose_max=50.0,
            dose_is_range=True,
            dose_range_raw="20-50",
            dose_basis_raw="20-50 мг/кг",
            dose_source_start=0,
            dose_source_end=5,
            dose_range_confidence=1.0,
            dose_component_count=2,
            route="oral",
            frequency_per_day=2.0,
            frequency_is_range=True,
            duration_days_min=7.0,
            duration_days_max=10.0,
            duration_days_recommended=7.0,
            adult=True,
            child=False,
            population_stated=True,
            pregnancy=False,
            renal_adjustment=True,
            therapy_line="first",
            confidence=0.91,
            warnings=["DOSE_COMBINATION_STRENGTH"],
        )

    def test_all_eight_range_fields_survive(self):
        original = self._full_regimen()
        restored = NormalizedRegimen.from_dict(original.to_dict_with_range())
        assert restored.dose_min == 20.0
        assert restored.dose_max == 50.0
        assert restored.dose_is_range is True
        assert restored.dose_range_raw == "20-50"
        assert restored.dose_basis_raw == "20-50 мг/кг"
        assert restored.dose_source_start == 0
        assert restored.dose_source_end == 5
        assert restored.dose_range_confidence == 1.0

    def test_component_count_survives(self):
        restored = NormalizedRegimen.from_dict(
            self._full_regimen().to_dict_with_range()
        )
        assert restored.dose_component_count == 2

    def test_frequency_is_range_survives(self):
        restored = NormalizedRegimen.from_dict(
            self._full_regimen().to_dict_with_range()
        )
        assert restored.frequency_is_range is True

    def test_population_stated_survives(self):
        restored = NormalizedRegimen.from_dict(
            self._full_regimen().to_dict_with_range()
        )
        assert restored.population_stated is True

    def test_components_survive(self):
        restored = NormalizedRegimen.from_dict(
            self._full_regimen().to_dict_with_range()
        )
        assert len(restored.drug_components) == 2
        assert restored.drug_components[0].dose_value == 875.0

    def test_full_round_trip_is_lossless(self):
        original = self._full_regimen()
        d = original.to_dict_with_range()
        restored = NormalizedRegimen.from_dict(d)
        assert restored.to_dict_with_range() == d

    def test_from_plain_to_dict_still_defaults_range_to_none(self):
        restored = NormalizedRegimen.from_dict(
            NormalizedRegimen(dose_value=5.0).to_dict()
        )
        assert restored.dose_min is None
        assert restored.dose_max is None
        assert restored.dose_is_range is None
        assert restored.dose_component_count is None

    def test_from_dict_tolerates_missing_keys(self):
        r = NormalizedRegimen.from_dict({})
        assert r.dose_value is None
        assert r.route == "unknown"
        assert r.frequency_is_range is False
        assert r.population_stated is False

    def test_from_dict_coerces_flags_to_bool(self):
        r = NormalizedRegimen.from_dict(
            {"frequency_is_range": 1, "population_stated": "yes"}
        )
        assert r.frequency_is_range is True
        assert r.population_stated is True


class TestM18Sentinel:
    def test_unset_sentinel_is_falsy(self):
        assert bool(UNSET) is False
        assert "UNSET" in repr(UNSET)

    def test_default_overall_uses_fields_mean(self):
        assert ConfidenceScore(fields={"a": 1.0, "b": 0.0}).overall == 0.5

    def test_explicit_zero_wins(self):
        assert ConfidenceScore(overall=0.0, fields={"a": 1.0}).overall == 0.0

    def test_overall_was_set_flag(self):
        assert ConfidenceScore().overall_was_set is False
        assert ConfidenceScore(overall=0.0).overall_was_set is True
        assert ConfidenceScore(overall=0.5).overall_was_set is True


class TestM5ParserResultConfidence:
    def test_weighted_not_unweighted(self):
        pr = ParserResult(field_confidence={"drug": 1.0, "duration": 0.0})
        assert pr.confidence == 0.6

    def test_empty(self):
        assert ParserResult().confidence == 0.0

    def test_nan_field_is_finite(self):
        pr = ParserResult(field_confidence={"drug": math.nan, "dose": 1.0})
        assert math.isfinite(pr.confidence)


class TestMissingFieldInputConstant:
    def test_constant_value(self):
        assert MISSING_FIELD_INPUT == "MISSING_FIELD_INPUT"

    def test_used_as_warning_prefix(self):
        from medical_normalizer.frequency_parser import FrequencyParser

        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": 3})
        assert reg.warnings == [f"{MISSING_FIELD_INPUT}:frequency"]
