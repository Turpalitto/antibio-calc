"""Tests for confidence.py -- ConfidenceCalculator, ConfidenceConfig, ConfidenceResult."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, is_dataclass

import pytest

from medical_normalizer.confidence import (
    ConfidenceCalculator,
    ConfidenceConfig,
    ConfidenceResult,
)
from medical_normalizer.models import ConfidenceScore, NormalizedRegimen, ParserResult


# -- Helpers ---------------------------------------------------------


def _perfect_regimen() -> NormalizedRegimen:
    return NormalizedRegimen(
        drug_normalized="Цефтриаксон",
        dose_value=1.0,
        dose_unit="g",
        route="внутривенно",
        frequency_per_day=1.0,
        duration_days_min=7.0,
        duration_days_max=10.0,
        adult=True,
        child=False,
        population_stated=True,
        pregnancy=True,
        renal_adjustment=True,
        therapy_line="first",
        atc_code="J01DD04",
    )


def _perfect_no_optionals() -> NormalizedRegimen:
    return NormalizedRegimen(
        drug_normalized="Цефтриаксон",
        dose_value=1.0,
        route="внутривенно",
        frequency_per_day=1.0,
        duration_days_min=7.0,
        adult=True,
        population_stated=True,
        therapy_line="first",
        atc_code=None,
        pregnancy=None,
        renal_adjustment=False,
    )


def _empty_regimen() -> NormalizedRegimen:
    return NormalizedRegimen()


def _bare_regimen() -> NormalizedRegimen:
    return NormalizedRegimen(adult=False, child=False)


# -- ConfidenceConfig ------------------------------------------------


class TestConfidenceConfig:
    def test_default_weights(self):
        cfg = ConfidenceConfig()
        assert cfg.weight_required == 3
        assert cfg.weight_important == 2
        assert cfg.weight_optional == 1

    def test_default_tiers(self):
        cfg = ConfidenceConfig()
        assert cfg.exact_match == 0.99
        assert cfg.inferred == 0.90
        assert cfg.inferred_partial == 0.85
        assert cfg.inferred_low == 0.80
        assert cfg.uncertain == 0.60
        assert cfg.not_found == 0.0

    def test_required_fields(self):
        assert ConfidenceConfig().required_fields == ("drug", "dose", "route", "frequency")

    def test_important_fields(self):
        assert ConfidenceConfig().important_fields == ("duration", "population", "therapy_line")

    def test_optional_fields_match_spec(self):
        assert ConfidenceConfig().optional_fields == ("atc_code", "pregnancy", "renal_adjustment")

    def test_all_fields_count(self):
        assert len(ConfidenceConfig().all_fields) == 10

    def test_all_fields_contains_all(self):
        cfg = ConfidenceConfig()
        for f in ("drug", "dose", "route", "frequency", "duration",
                  "population", "therapy_line", "atc_code",
                  "pregnancy", "renal_adjustment"):
            assert f in cfg.all_fields

    def test_weights_dict(self):
        w = ConfidenceConfig().weights
        assert w["drug"] == 3 and w["dose"] == 3 and w["route"] == 3 and w["frequency"] == 3
        assert w["duration"] == 2 and w["population"] == 2 and w["therapy_line"] == 2
        assert w["atc_code"] == 1 and w["pregnancy"] == 1 and w["renal_adjustment"] == 1

    def test_weights_total(self):
        assert sum(ConfidenceConfig().weights.values()) == 21

    def test_frozen(self):
        cfg = ConfidenceConfig()
        with pytest.raises(FrozenInstanceError):
            cfg.weight_required = 99  # type: ignore[misc]

    def test_custom_weights(self):
        cfg = ConfidenceConfig(weight_required=5, weight_important=3, weight_optional=1)
        assert cfg.weights["drug"] == 5
        assert cfg.weights["duration"] == 3
        assert cfg.weights["atc_code"] == 1

    def test_custom_fields(self):
        cfg = ConfidenceConfig(required_fields=("drug",))
        assert cfg.all_fields == ("drug",) + cfg.important_fields + cfg.optional_fields


# -- ConfidenceResult ------------------------------------------------


class TestConfidenceResult:
    def test_is_dataclass(self):
        assert is_dataclass(ConfidenceResult)

    def test_defaults(self):
        r = ConfidenceResult(0.5, {}, None)
        assert r.calculation_metadata == {}

    def test_with_metadata(self):
        r = ConfidenceResult(0.5, {"drug": 0.9}, 0.8, {"x": 1})
        assert r.overall_confidence == 0.5
        assert r.field_confidence == {"drug": 0.9}
        assert r.parser_confidence == 0.8
        assert r.calculation_metadata == {"x": 1}


# -- calculate_field: per-field inference ----------------------------


class TestCalculateFieldDrug:
    def test_known_drug(self):
        assert ConfidenceCalculator.calculate_field("drug", _perfect_regimen()) == 0.99

    def test_missing_drug(self):
        assert ConfidenceCalculator.calculate_field("drug", _empty_regimen()) == 0.0

    def test_unknown_drug_uncertain(self):
        r = NormalizedRegimen(drug_normalized="Неизвестный антибиотик")
        assert ConfidenceCalculator.calculate_field("drug", r) == 0.60

    def test_empty_string_drug(self):
        r = NormalizedRegimen(drug_normalized="")
        assert ConfidenceCalculator.calculate_field("drug", r) == 0.0


class TestCalculateFieldDose:
    def test_present(self):
        assert ConfidenceCalculator.calculate_field("dose", NormalizedRegimen(dose_value=500.0)) == 0.90

    def test_missing(self):
        assert ConfidenceCalculator.calculate_field("dose", _empty_regimen()) == 0.0

    def test_zero(self):
        assert ConfidenceCalculator.calculate_field("dose", NormalizedRegimen(dose_value=0.0)) == 0.0

    def test_negative(self):
        assert ConfidenceCalculator.calculate_field("dose", NormalizedRegimen(dose_value=-5.0)) == 0.0

    def test_none(self):
        assert ConfidenceCalculator.calculate_field("dose", NormalizedRegimen(dose_value=None)) == 0.0


class TestCalculateFieldRoute:
    def test_present(self):
        assert ConfidenceCalculator.calculate_field("route", NormalizedRegimen(route="внутрь")) == 0.90

    def test_unknown(self):
        assert ConfidenceCalculator.calculate_field("route", _empty_regimen()) == 0.0

    def test_explicit_unknown_string(self):
        assert ConfidenceCalculator.calculate_field("route", NormalizedRegimen(route="unknown")) == 0.0

    def test_empty_string(self):
        assert ConfidenceCalculator.calculate_field("route", NormalizedRegimen(route="")) == 0.0


class TestCalculateFieldFrequency:
    def test_present(self):
        assert ConfidenceCalculator.calculate_field("frequency", NormalizedRegimen(frequency_per_day=2.0)) == 0.90

    def test_missing(self):
        assert ConfidenceCalculator.calculate_field("frequency", _empty_regimen()) == 0.0

    def test_zero(self):
        assert ConfidenceCalculator.calculate_field("frequency", NormalizedRegimen(frequency_per_day=0.0)) == 0.0

    def test_negative(self):
        assert ConfidenceCalculator.calculate_field("frequency", NormalizedRegimen(frequency_per_day=-1.0)) == 0.0


class TestCalculateFieldDuration:
    def test_present(self):
        r = NormalizedRegimen(duration_days_min=7.0)
        assert ConfidenceCalculator.calculate_field("duration", r) == 0.85

    def test_missing(self):
        assert ConfidenceCalculator.calculate_field("duration", _empty_regimen()) == 0.0

    def test_only_max_present_not_counted(self):
        r = NormalizedRegimen(duration_days_min=None, duration_days_max=10.0)
        assert ConfidenceCalculator.calculate_field("duration", r) == 0.0


class TestCalculateFieldPopulation:
    # M6: `adult` defaults to True for backward compatibility, so `adult or
    # child` was always True and a regimen with ZERO population evidence
    # scored 0.90. population_stated is what distinguishes "evidence" from
    # "default".
    def test_adult_default_alone_is_not_evidence(self):
        # adult=True is only the default -> no evidence -> not_found
        assert ConfidenceCalculator.calculate_field("population", NormalizedRegimen()) == 0.0

    def test_adult_with_population_stated(self):
        r = NormalizedRegimen(adult=True, population_stated=True)
        assert ConfidenceCalculator.calculate_field("population", r) == 0.90

    def test_child(self):
        # child defaults to False, so child=True IS explicit evidence
        r = NormalizedRegimen(adult=False, child=True)
        assert ConfidenceCalculator.calculate_field("population", r) == 0.90

    def test_both(self):
        r = NormalizedRegimen(adult=True, child=True, population_stated=True)
        assert ConfidenceCalculator.calculate_field("population", r) == 0.90

    def test_neither(self):
        r = NormalizedRegimen(adult=False, child=False)
        assert ConfidenceCalculator.calculate_field("population", r) == 0.0

    def test_age_parser_sets_population_stated(self):
        from medical_normalizer.population_parser import AgeParser

        r = AgeParser.parse(NormalizedRegimen(), {"age_group": "взрослые"})
        assert r.population_stated is True
        assert ConfidenceCalculator.calculate_field("population", r) == 0.90

    def test_no_age_text_leaves_population_unstated(self):
        from medical_normalizer.population_parser import AgeParser

        r = AgeParser.parse(NormalizedRegimen(), {})
        assert r.adult is True          # default preserved
        assert r.population_stated is False
        assert ConfidenceCalculator.calculate_field("population", r) == 0.0


class TestCalculateFieldTherapyLine:
    def test_present(self):
        assert ConfidenceCalculator.calculate_field("therapy_line", NormalizedRegimen(therapy_line="first")) == 0.99

    def test_unknown(self):
        assert ConfidenceCalculator.calculate_field("therapy_line", _empty_regimen()) == 0.0

    def test_empty(self):
        assert ConfidenceCalculator.calculate_field("therapy_line", NormalizedRegimen(therapy_line="")) == 0.0


class TestCalculateFieldAtcCode:
    def test_present(self):
        r = NormalizedRegimen(atc_code="J01DD04")
        assert ConfidenceCalculator.calculate_field("atc_code", r) == 0.99

    def test_missing(self):
        assert ConfidenceCalculator.calculate_field("atc_code", _empty_regimen()) == 0.0

    def test_empty_string(self):
        assert ConfidenceCalculator.calculate_field("atc_code", NormalizedRegimen(atc_code="")) == 0.0


class TestCalculateFieldPregnancy:
    def test_true(self):
        assert ConfidenceCalculator.calculate_field("pregnancy", NormalizedRegimen(pregnancy=True)) == 0.80

    def test_false(self):
        assert ConfidenceCalculator.calculate_field("pregnancy", NormalizedRegimen(pregnancy=False)) == 0.80

    def test_none(self):
        assert ConfidenceCalculator.calculate_field("pregnancy", _empty_regimen()) == 0.0


class TestCalculateFieldRenal:
    def test_true(self):
        r = NormalizedRegimen(renal_adjustment=True)
        assert ConfidenceCalculator.calculate_field("renal_adjustment", r) == 0.80

    def test_false(self):
        r = NormalizedRegimen(renal_adjustment=False)
        assert ConfidenceCalculator.calculate_field("renal_adjustment", r) == 0.0


class TestCalculateFieldUnknown:
    def test_unknown_field_returns_not_found(self):
        assert ConfidenceCalculator.calculate_field("nope", _empty_regimen()) == 0.0

    def test_unknown_field_with_parser(self):
        pr = ParserResult(field_confidence={"nope": 0.5})
        assert ConfidenceCalculator.calculate_field("nope", _empty_regimen(), pr) == 0.5


# -- calculate_field: parser / score overrides -----------------------


class TestCalculateFieldOverrides:
    def test_parser_result_overrides_inference(self):
        pr = ParserResult(field_confidence={"drug": 0.75})
        assert ConfidenceCalculator.calculate_field("drug", _perfect_regimen(), pr) == 0.75

    def test_confidence_score_overrides_inference(self):
        cs = ConfidenceScore(fields={"drug": 0.65})
        assert ConfidenceCalculator.calculate_field("drug", _perfect_regimen(), None, cs) == 0.65

    def test_parser_result_wins_over_confidence_score(self):
        pr = ParserResult(field_confidence={"drug": 0.75})
        cs = ConfidenceScore(fields={"drug": 0.65})
        assert ConfidenceCalculator.calculate_field("drug", _perfect_regimen(), pr, cs) == 0.75

    def test_parser_high_value_clamped(self):
        pr = ParserResult(field_confidence={"drug": 1.5})
        assert ConfidenceCalculator.calculate_field("drug", _empty_regimen(), pr) == 1.0

    def test_parser_negative_clamped(self):
        pr = ParserResult(field_confidence={"drug": -0.5})
        assert ConfidenceCalculator.calculate_field("drug", _empty_regimen(), pr) == 0.0

    def test_parser_zero_kept(self):
        pr = ParserResult(field_confidence={"drug": 0.0})
        assert ConfidenceCalculator.calculate_field("drug", _perfect_regimen(), pr) == 0.0

    def test_parser_one_kept(self):
        pr = ParserResult(field_confidence={"drug": 1.0})
        assert ConfidenceCalculator.calculate_field("drug", _empty_regimen(), pr) == 1.0


# -- calculate_overall -----------------------------------------------


class TestCalculateOverall:
    def test_empty_dict(self):
        assert ConfidenceCalculator.calculate_overall({}) == 0.0

    def test_single_required_full(self):
        assert ConfidenceCalculator.calculate_overall({"drug": 1.0}) == 1.0

    def test_single_required_zero(self):
        assert ConfidenceCalculator.calculate_overall({"drug": 0.0}) == 0.0

    def test_optional_zero_excluded(self):
        assert ConfidenceCalculator.calculate_overall({"atc_code": 0.0}) == 0.0

    def test_optional_nonzero_included(self):
        assert ConfidenceCalculator.calculate_overall({"atc_code": 0.5}) == 0.5

    def test_weighted_two_required(self):
        assert ConfidenceCalculator.calculate_overall({"drug": 0.5, "dose": 1.0}) == 0.75

    def test_weighted_required_vs_important(self):
        assert ConfidenceCalculator.calculate_overall({"drug": 1.0, "duration": 0.0}) == 0.6

    def test_weighted_required_vs_optional(self):
        assert ConfidenceCalculator.calculate_overall({"drug": 1.0, "atc_code": 1.0}) == 1.0

    def test_unknown_field_ignored(self):
        assert ConfidenceCalculator.calculate_overall({"unknown": 1.0}) == 0.0

    def test_clamped_above_one(self):
        assert ConfidenceCalculator.calculate_overall({"drug": 2.0}) == 1.0

    def test_clamped_below_zero(self):
        assert ConfidenceCalculator.calculate_overall({"drug": -1.0}) == 0.0

    def test_rounded_to_four_digits(self):
        # (1.0*3 + 1.0*3 + 0.11111*1) / 7 = 6.11111/7 = 0.8730157... -> 0.8730
        val = ConfidenceCalculator.calculate_overall({"drug": 1.0, "dose": 1.0, "atc_code": 0.11111})
        assert val == 0.8730

    def test_all_optional_zero(self):
        d = {"atc_code": 0.0, "pregnancy": 0.0, "renal_adjustment": 0.0}
        assert ConfidenceCalculator.calculate_overall(d) == 0.0

    def test_all_optional_full(self):
        d = {"atc_code": 1.0, "pregnancy": 1.0, "renal_adjustment": 1.0}
        assert ConfidenceCalculator.calculate_overall(d) == 1.0

    def test_mixed_optional_zero_and_nonzero(self):
        d = {"atc_code": 1.0, "pregnancy": 0.0, "renal_adjustment": 0.0}
        assert ConfidenceCalculator.calculate_overall(d) == 1.0

    def test_all_required_full(self):
        d = {"drug": 1.0, "dose": 1.0, "route": 1.0, "frequency": 1.0}
        assert ConfidenceCalculator.calculate_overall(d) == 1.0

    def test_all_required_zero(self):
        d = {"drug": 0.0, "dose": 0.0, "route": 0.0, "frequency": 0.0}
        assert ConfidenceCalculator.calculate_overall(d) == 0.0


# -- calculate_parser_score ------------------------------------------


class TestCalculateParserScore:
    def test_none_none(self):
        assert ConfidenceCalculator.calculate_parser_score(None, None) is None

    def test_parser_empty(self):
        assert ConfidenceCalculator.calculate_parser_score(ParserResult(), None) is None

    def test_parser_with_fields(self):
        pr = ParserResult(field_confidence={"drug": 0.8, "dose": 0.9})
        assert ConfidenceCalculator.calculate_parser_score(pr, None) == 0.85

    def test_confidence_score_overall(self):
        cs = ConfidenceScore(overall=0.75, fields={})
        assert ConfidenceCalculator.calculate_parser_score(None, cs) == 0.75

    def test_confidence_score_fields_auto_overall(self):
        cs = ConfidenceScore(fields={"drug": 0.8, "dose": 0.9})
        assert ConfidenceCalculator.calculate_parser_score(None, cs) == 0.85

    def test_confidence_score_priority_over_parser(self):
        pr = ParserResult(field_confidence={"drug": 0.8, "dose": 0.9})
        cs = ConfidenceScore(overall=0.42, fields={})
        assert ConfidenceCalculator.calculate_parser_score(pr, cs) == 0.42

    def test_confidence_score_explicit_zero_overall_is_respected(self):
        # M18: an explicitly passed overall=0.0 is a real parser verdict and
        # must not be indistinguishable from "not supplied".
        pr = ParserResult(field_confidence={"drug": 0.8, "dose": 0.9})
        cs = ConfidenceScore(overall=0.0, fields={})
        assert cs.overall_was_set is True
        assert ConfidenceCalculator.calculate_parser_score(pr, cs) == 0.0

    def test_confidence_score_only_empty_fields_falls_back(self):
        # No fields and no explicit overall -> nothing to report
        cs = ConfidenceScore()
        assert cs.overall_was_set is False
        assert ConfidenceCalculator.calculate_parser_score(None, cs) is None

    def test_parser_single_field(self):
        pr = ParserResult(field_confidence={"drug": 0.6})
        assert ConfidenceCalculator.calculate_parser_score(pr, None) == 0.6

    def test_score_clamped_above_one(self):
        cs = ConfidenceScore(overall=1.5, fields={})
        assert ConfidenceCalculator.calculate_parser_score(None, cs) == 1.0

    def test_score_clamped_below_zero(self):
        cs = ConfidenceScore(overall=-0.3, fields={})
        assert ConfidenceCalculator.calculate_parser_score(None, cs) == 0.0

    def test_score_rounded(self):
        cs = ConfidenceScore(overall=0.123456, fields={})
        assert ConfidenceCalculator.calculate_parser_score(None, cs) == 0.1235


# -- calculate (full) ------------------------------------------------


class TestCalculate:
    def test_returns_confidence_result(self):
        res = ConfidenceCalculator.calculate(_perfect_regimen())
        assert isinstance(res, ConfidenceResult)

    def test_perfect_regimen_overall(self):
        # all 10 fields present at their best inference tier
        res = ConfidenceCalculator.calculate(_perfect_regimen())
        # 19.14 / 21 = 0.9114
        assert res.overall_confidence == 0.9114

    def test_perfect_no_optionals_overall(self):
        # optionals missing -> excluded; 16.55 / 18 = 0.9194
        res = ConfidenceCalculator.calculate(_perfect_no_optionals())
        assert res.overall_confidence == 0.9194

    def test_missing_optional_does_not_reduce_to_zero(self):
        res = ConfidenceCalculator.calculate(_perfect_no_optionals())
        assert res.overall_confidence > 0.9

    def test_empty_regimen_overall(self):
        # M6: with the always-true `adult or child` branch an EMPTY regimen
        # scored 0.10 purely from the adult=True default. With no stated
        # population there is no evidence at all -> 0.0.
        res = ConfidenceCalculator.calculate(_empty_regimen())
        assert res.overall_confidence == 0.0

    def test_bare_regimen_overall_zero(self):
        res = ConfidenceCalculator.calculate(_bare_regimen())
        assert res.overall_confidence == 0.0

    def test_all_fields_missing_zero(self):
        res = ConfidenceCalculator.calculate(_bare_regimen())
        assert res.overall_confidence == 0.0

    def test_one_required_field_missing(self):
        # drug missing, rest perfect, optionals missing
        r = NormalizedRegimen(
            drug_normalized="",
            dose_value=1.0,
            route="внутривенно",
            frequency_per_day=1.0,
            duration_days_min=7.0,
            adult=True,
            population_stated=True,
            therapy_line="first",
        )
        res = ConfidenceCalculator.calculate(r)
        # 13.58 / 18 = 0.7544
        assert res.overall_confidence == 0.7544

    def test_field_confidence_has_all_fields(self):
        res = ConfidenceCalculator.calculate(_perfect_regimen())
        assert set(res.field_confidence.keys()) == set(ConfidenceConfig().all_fields)

    def test_field_confidence_perfect_values(self):
        res = ConfidenceCalculator.calculate(_perfect_regimen())
        fc = res.field_confidence
        assert fc["drug"] == 0.99
        assert fc["dose"] == 0.90
        assert fc["route"] == 0.90
        assert fc["frequency"] == 0.90
        assert fc["duration"] == 0.85
        assert fc["population"] == 0.90
        assert fc["therapy_line"] == 0.99
        assert fc["atc_code"] == 0.99
        assert fc["pregnancy"] == 0.80
        assert fc["renal_adjustment"] == 0.80

    def test_parser_confidence_none_without_parser(self):
        res = ConfidenceCalculator.calculate(_perfect_regimen())
        assert res.parser_confidence is None

    def test_parser_confidence_from_parser_result(self):
        pr = ParserResult(field_confidence={"drug": 0.8, "dose": 0.9})
        res = ConfidenceCalculator.calculate(_perfect_regimen(), pr)
        assert res.parser_confidence == 0.85

    def test_parser_confidence_from_confidence_score(self):
        cs = ConfidenceScore(overall=0.55, fields={})
        res = ConfidenceCalculator.calculate(_perfect_regimen(), None, cs)
        assert res.parser_confidence == 0.55

    def test_parser_field_confidence_used_over_inference(self):
        pr = ParserResult(field_confidence={"drug": 0.5})
        res = ConfidenceCalculator.calculate(_perfect_regimen(), pr)
        assert res.field_confidence["drug"] == 0.5

    def test_overall_in_range(self):
        res = ConfidenceCalculator.calculate(_perfect_regimen())
        assert 0.0 <= res.overall_confidence <= 1.0

    def test_overall_boundary_zero(self):
        res = ConfidenceCalculator.calculate(_bare_regimen())
        assert res.overall_confidence == 0.0

    def test_overall_boundary_one_via_parser(self):
        pr = ParserResult(field_confidence={f: 1.0 for f in ConfidenceConfig().all_fields})
        res = ConfidenceCalculator.calculate(_bare_regimen(), pr)
        assert res.overall_confidence == 1.0

    def test_dose_only_overall(self):
        # M6: adult=True without population evidence no longer contributes.
        r = NormalizedRegimen(dose_value=500.0, adult=True)
        res = ConfidenceCalculator.calculate(r)
        # 2.70 / 18 = 0.15 (required fields with 0.0 still carry weight)
        assert res.overall_confidence == 0.15

    def test_drug_only_known_overall(self):
        r = NormalizedRegimen(drug_normalized="Цефтриаксон", adult=True)
        res = ConfidenceCalculator.calculate(r)
        # 2.97 / 18 = 0.165
        assert res.overall_confidence == 0.165


# -- calculation_metadata --------------------------------------------


class TestCalculationMetadata:
    def test_perfect_all_included(self):
        res = ConfidenceCalculator.calculate(_perfect_regimen())
        m = res.calculation_metadata
        assert m["included_count"] == 10
        assert m["excluded_count"] == 0
        assert m["excluded_fields"] == []
        assert m["total_weight"] == 21
        assert m["field_count"] == 10

    def test_missing_optionals_excluded(self):
        res = ConfidenceCalculator.calculate(_perfect_no_optionals())
        m = res.calculation_metadata
        assert m["included_count"] == 7
        assert set(m["excluded_fields"]) == {"atc_code", "pregnancy", "renal_adjustment"}
        assert m["total_weight"] == 18

    def test_empty_regimen_excludes_optionals(self):
        res = ConfidenceCalculator.calculate(_empty_regimen())
        m = res.calculation_metadata
        assert set(m["excluded_fields"]) == {"atc_code", "pregnancy", "renal_adjustment"}
        assert m["included_count"] == 7

    def test_weights_in_metadata(self):
        res = ConfidenceCalculator.calculate(_perfect_regimen())
        assert res.calculation_metadata["weights"] == ConfidenceConfig().weights

    def test_included_fields_present(self):
        res = ConfidenceCalculator.calculate(_perfect_no_optionals())
        inc = res.calculation_metadata["included_fields"]
        assert "drug" in inc and "atc_code" not in inc


# -- immutability / purity -------------------------------------------


class TestImmutability:
    def test_regimen_not_modified(self):
        r = _perfect_regimen()
        before = r.to_dict()
        ConfidenceCalculator.calculate(r)
        assert r.to_dict() == before

    def test_regimen_confidence_field_not_overwritten(self):
        r = _perfect_regimen()
        r.confidence = 0.123
        ConfidenceCalculator.calculate(r)
        assert r.confidence == 0.123

    def test_calculate_does_not_touch_warnings(self):
        r = _perfect_regimen()
        ConfidenceCalculator.calculate(r)
        assert r.warnings == []


# -- config-driven (no magic constants) ------------------------------


class TestConfigDriven:
    def test_all_inferred_values_come_from_config(self):
        cfg = ConfidenceCalculator.config
        res = ConfidenceCalculator.calculate(_perfect_regimen())
        fc = res.field_confidence
        assert fc["drug"] == cfg.exact_match
        assert fc["dose"] == cfg.inferred
        assert fc["route"] == cfg.inferred
        assert fc["frequency"] == cfg.inferred
        assert fc["duration"] == cfg.inferred_partial
        assert fc["population"] == cfg.inferred
        assert fc["therapy_line"] == cfg.exact_match
        assert fc["atc_code"] == cfg.exact_match
        assert fc["pregnancy"] == cfg.inferred_low
        assert fc["renal_adjustment"] == cfg.inferred_low

    def test_missing_values_are_not_found(self):
        cfg = ConfidenceCalculator.config
        res = ConfidenceCalculator.calculate(_bare_regimen())
        fc = res.field_confidence
        for f in cfg.required_fields:
            assert fc[f] == cfg.not_found
        for f in cfg.important_fields:
            assert fc[f] == cfg.not_found
        for f in cfg.optional_fields:
            assert fc[f] == cfg.not_found

    def test_custom_config_changes_overall(self):
        original = ConfidenceCalculator.config
        try:
            ConfidenceCalculator.config = ConfidenceConfig(
                weight_required=10, weight_important=1, weight_optional=0,
            )
            res = ConfidenceCalculator.calculate(_perfect_no_optionals())
            # required fields weight 10 each; important weight 1 each
            # included: 4 required + 3 important (optionals missing/excluded)
            # drug 0.99*10 + dose 0.90*10 + route 0.90*10 + freq 0.90*10
            # + duration 0.85*1 + population 0.90*1 + therapy 0.99*1
            num = 9.9 + 9.0 + 9.0 + 9.0 + 0.85 + 0.90 + 0.99
            den = 40 + 3
            assert res.overall_confidence == round(num / den, 4)
        finally:
            ConfidenceCalculator.config = original

    def test_custom_config_changes_field_set(self):
        original = ConfidenceCalculator.config
        try:
            ConfidenceCalculator.config = ConfidenceConfig(required_fields=("drug",))
            res = ConfidenceCalculator.calculate(NormalizedRegimen(drug_normalized="Цефтриаксон"))
            assert "drug" in res.field_confidence
            assert res.calculation_metadata["weights"]["drug"] == 3
        finally:
            ConfidenceCalculator.config = original


# -- calculate_field_confidence --------------------------------------


class TestCalculateFieldConfidence:
    def test_returns_all_fields(self):
        fc = ConfidenceCalculator.calculate_field_confidence(_perfect_regimen())
        assert set(fc.keys()) == set(ConfidenceConfig().all_fields)

    def test_with_parser_overrides(self):
        pr = ParserResult(field_confidence={"drug": 0.5, "dose": 0.5})
        fc = ConfidenceCalculator.calculate_field_confidence(_perfect_regimen(), pr)
        assert fc["drug"] == 0.5
        assert fc["dose"] == 0.5
        # non-overridden fields still inferred
        assert fc["route"] == 0.90

    def test_with_confidence_score(self):
        cs = ConfidenceScore(fields={"drug": 0.4})
        fc = ConfidenceCalculator.calculate_field_confidence(_perfect_regimen(), None, cs)
        assert fc["drug"] == 0.4
        assert fc["dose"] == 0.90

    def test_parser_wins_over_score(self):
        pr = ParserResult(field_confidence={"drug": 0.5})
        cs = ConfidenceScore(fields={"drug": 0.4})
        fc = ConfidenceCalculator.calculate_field_confidence(_perfect_regimen(), pr, cs)
        assert fc["drug"] == 0.5


# -- edge cases / boundaries -----------------------------------------


class TestEdgeCases:
    def test_cyrillic_route_normalized(self):
        r = NormalizedRegimen(route="внутримышечно")
        assert ConfidenceCalculator.calculate_field("route", r) == 0.90

    def test_negative_duration_not_counted(self):
        r = NormalizedRegimen(duration_days_min=-1.0)
        # min present but negative -> inference checks `is not None` only
        assert ConfidenceCalculator.calculate_field("duration", r) == 0.85

    def test_zero_frequency_not_counted(self):
        r = NormalizedRegimen(frequency_per_day=0.0)
        assert ConfidenceCalculator.calculate_field("frequency", r) == 0.0

    def test_empty_parser_result_field_confidence(self):
        pr = ParserResult(field_confidence={})
        assert ConfidenceCalculator.calculate_parser_score(pr, None) is None

    def test_parser_override_for_optional_field(self):
        pr = ParserResult(field_confidence={"atc_code": 0.0})
        r = NormalizedRegimen(atc_code="J01DD04")
        # parser 0.0 wins over inference; optional 0 -> excluded
        assert ConfidenceCalculator.calculate_field("atc_code", r, pr) == 0.0

    def test_calculate_overall_with_extra_unknown_keys(self):
        d = {"drug": 1.0, "bogus": 0.0}
        assert ConfidenceCalculator.calculate_overall(d) == 1.0

    def test_repeated_calculate_idempotent(self):
        r = _perfect_regimen()
        a = ConfidenceCalculator.calculate(r)
        b = ConfidenceCalculator.calculate(r)
        assert a.overall_confidence == b.overall_confidence
        assert a.field_confidence == b.field_confidence


# ── Regression tests: M1, M5, M18, H7 ─────────────────────────────


class TestM1NonFiniteClamp:
    """M1: _clamp let NaN through (nan < 0 and nan > 1 are both False), so a
    NaN poisoned calculate_overall and was written to overall_confidence."""

    def test_clamp_nan_returns_zero(self):
        assert ConfidenceCalculator._clamp(float("nan")) == 0.0

    def test_clamp_infinity_returns_zero(self):
        assert ConfidenceCalculator._clamp(float("inf")) == 0.0
        assert ConfidenceCalculator._clamp(float("-inf")) == 0.0

    def test_clamp_none_returns_zero(self):
        assert ConfidenceCalculator._clamp(None) == 0.0  # type: ignore[arg-type]

    def test_clamp_string_returns_zero(self):
        assert ConfidenceCalculator._clamp("x") == 0.0  # type: ignore[arg-type]

    def test_clamp_bounds_still_work(self):
        assert ConfidenceCalculator._clamp(1.5) == 1.0
        assert ConfidenceCalculator._clamp(-0.5) == 0.0
        assert ConfidenceCalculator._clamp(0.42) == 0.42

    def test_calculate_overall_nan_is_zero(self):
        assert ConfidenceCalculator.calculate_overall({"drug": float("nan")}) == 0.0

    def test_calculate_overall_mixed_nan_is_finite(self):
        # the bad field is clamped to 0.0 in isolation; the other two still
        # contribute (1*3 + 0*3 + 1*3) / 9
        val = ConfidenceCalculator.calculate_overall(
            {"drug": 1.0, "dose": float("nan"), "route": 1.0}
        )
        assert 0.0 <= val <= 1.0
        assert val == round(6.0 / 9.0, 4)

    def test_calculate_field_nan_is_zero(self):
        pr = ParserResult(field_confidence={"drug": float("nan")})
        assert ConfidenceCalculator.calculate_field(
            "drug", _empty_regimen(), pr
        ) == 0.0

    def test_overall_never_nan_end_to_end(self):
        pr = ParserResult(field_confidence={f: float("nan") for f in ("drug", "dose")})
        res = ConfidenceCalculator.calculate(_bare_regimen(), pr)
        assert res.overall_confidence == res.overall_confidence  # not NaN
        assert 0.0 <= res.overall_confidence <= 1.0

    def test_overall_written_to_db_is_finite(self):
        import math as _math

        from medical_normalizer.db import NormalizerDB
        from medical_normalizer.normalizer import MedicalNormalizer

        db = NormalizerDB.connect(":memory:")
        try:
            db.save(MedicalNormalizer.normalize({
                "antibiotic": "Цефтриаксон", "dose": "1,0", "unit": "г",
                "route": "в/в", "frequency": "1 раз в день",
            }), "g1", "r1")
            rec = db.load("g1", "r1")
            assert rec is not None
            assert _math.isfinite(rec.overall_confidence)
        finally:
            db.close()


class TestM5ParserResultUsesWeightedConfidence:
    """M5: ParserResult.confidence was an UNWEIGHTED mean while
    ConfidenceCalculator.calculate_overall is WEIGHTED — the two disagreed
    for the same data."""

    def test_required_outweighs_important(self):
        # unweighted mean would be 0.5; weighted is 1.0*3 / (3+2) = 0.6
        pr = ParserResult(field_confidence={"drug": 1.0, "duration": 0.0})
        assert pr.confidence == 0.6

    def test_agrees_with_calculator(self):
        fields = {"drug": 0.8, "dose": 0.6, "duration": 0.4, "atc_code": 0.0}
        pr = ParserResult(field_confidence=dict(fields))
        assert pr.confidence == ConfidenceCalculator.calculate_overall(fields)

    def test_equal_weights_agree(self):
        fields = {"drug": 0.8, "dose": 0.9}
        pr = ParserResult(field_confidence=dict(fields))
        assert pr.confidence == 0.85

    def test_empty_is_zero(self):
        assert ParserResult().confidence == 0.0

    def test_optional_zero_excluded(self):
        pr = ParserResult(field_confidence={"drug": 1.0, "atc_code": 0.0})
        assert pr.confidence == 1.0

    def test_unknown_field_ignored(self):
        pr = ParserResult(field_confidence={"nope": 1.0})
        assert pr.confidence == 0.0

    def test_nan_field_not_poisoning(self):
        pr = ParserResult(field_confidence={"drug": float("nan"), "dose": 1.0})
        assert pr.confidence == 0.5


class TestM18ConfidenceScoreSentinel:
    """M18: an explicitly passed overall=0.0 was indistinguishable from the
    default and was overwritten by the fields mean."""

    def test_explicit_zero_is_preserved(self):
        cs = ConfidenceScore(overall=0.0, fields={"drug": 0.9})
        assert cs.overall == 0.0
        assert cs.overall_was_set is True

    def test_default_is_overwritten_by_mean(self):
        cs = ConfidenceScore(fields={"drug": 0.9})
        assert cs.overall == 0.9
        assert cs.overall_was_set is False

    def test_explicit_value_beats_fields_mean(self):
        cs = ConfidenceScore(overall=0.42, fields={"drug": 0.9})
        assert cs.overall == 0.42

    def test_no_fields_default_is_zero(self):
        cs = ConfidenceScore()
        assert cs.overall == 0.0
        assert cs.overall_was_set is False

    def test_explicit_none_becomes_zero_and_counts_as_set(self):
        cs = ConfidenceScore(overall=None)
        assert cs.overall == 0.0
        assert cs.overall_was_set is True

    def test_explicit_zero_drives_parser_score(self):
        cs = ConfidenceScore(overall=0.0, fields={})
        assert ConfidenceCalculator.calculate_parser_score(None, cs) == 0.0

    def test_unset_score_falls_back_to_parser(self):
        pr = ParserResult(field_confidence={"drug": 0.8, "dose": 0.9})
        cs = ConfidenceScore()
        assert ConfidenceCalculator.calculate_parser_score(pr, cs) == 0.85
