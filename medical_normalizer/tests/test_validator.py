"""Tests for validator.py -- Validator, ValidationIssue, ValidationReport, Verdict."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, is_dataclass

import pytest

from medical_normalizer.models import DrugComponent, NormalizedRegimen
from medical_normalizer.validator import (
    Severity,
    ValidationIssue,
    ValidationReport,
    Validator,
    ValidatorConfig,
    Verdict,
)


# -- Helpers ---------------------------------------------------------


def _perfect_regimen() -> NormalizedRegimen:
    return NormalizedRegimen(
        drug_normalized="Цефтриаксон",
        dose_value=1.0,
        dose_unit="g",
        route="iv",
        frequency_per_day=1.0,
        duration_days_min=7.0,
        duration_days_max=10.0,
        adult=True,
        child=False,
        pregnancy=True,
        renal_adjustment=True,
        therapy_line="first",
        atc_code="J01DD04",
    )


def _empty_regimen() -> NormalizedRegimen:
    return NormalizedRegimen()


def _bare_regimen() -> NormalizedRegimen:
    return NormalizedRegimen(adult=False, child=False)


# -- ValidatorConfig -------------------------------------------------


class TestValidatorConfig:
    def test_required_fields(self):
        assert ValidatorConfig().required_fields == ("drug", "dose", "route", "frequency")

    def test_valid_routes(self):
        rv = ValidatorConfig().valid_routes
        for r in ("oral", "iv", "im", "topical", "ophthalmic", "inhalation", "otic"):
            assert r in rv

    def test_valid_therapy_lines(self):
        assert ValidatorConfig().valid_therapy_lines == ("first", "alternative", "reserve", "unknown")

    def test_valid_units(self):
        u = ValidatorConfig().valid_units
        for x in ("g", "mg", "mcg", "ml", "mg/kg", "mg/kg/day", "IU", "thousand_IU"):
            assert x in u

    def test_numeric_bounds(self):
        c = ValidatorConfig()
        assert c.dose_min == 0.0 and c.dose_max > 0
        assert c.frequency_min == 0.0 and c.frequency_max == 24.0
        assert c.duration_min == 0.0 and c.duration_max == 365.0

    def test_atc_pattern(self):
        import re
        p = ValidatorConfig().atc_pattern
        assert re.match(p, "J01DD04")
        assert re.match(p, "A07AA01")
        assert not re.match(p, "j01dd04")
        assert not re.match(p, "J01DD")
        assert not re.match(p, "J01DD044")

    def test_frozen(self):
        c = ValidatorConfig()
        with pytest.raises(FrozenInstanceError):
            c.dose_max = 99  # type: ignore[misc]


# -- Severity / Verdict enums ----------------------------------------


class TestSeverity:
    def test_values(self):
        assert Severity.WARNING.value == "warning"
        assert Severity.REVIEW.value == "review"
        assert Severity.ERROR.value == "error"

    def test_is_str(self):
        assert isinstance(Severity.ERROR, str)


class TestVerdict:
    def test_values(self):
        assert Verdict.PASS.value == "PASS"
        assert Verdict.REVIEW.value == "REVIEW"
        assert Verdict.REJECT.value == "REJECT"

    def test_is_str(self):
        assert isinstance(Verdict.PASS, str)


# -- ValidationIssue -------------------------------------------------


class TestValidationIssue:
    def test_is_dataclass(self):
        assert is_dataclass(ValidationIssue)

    def test_defaults(self):
        i = ValidationIssue("CODE", Severity.ERROR, "msg", "drug")
        assert i.suggested_fix is None

    def test_to_dict(self):
        i = ValidationIssue("CODE", Severity.ERROR, "msg", "drug", "fix")
        d = i.to_dict()
        assert d == {
            "code": "CODE",
            "severity": "error",
            "message": "msg",
            "field": "drug",
            "suggested_fix": "fix",
        }


# -- ValidationReport ------------------------------------------------


class TestValidationReport:
    def test_is_dataclass(self):
        assert is_dataclass(ValidationReport)

    def test_defaults(self):
        r = ValidationReport(verdict=Verdict.PASS)
        assert r.issues == [] and r.metadata == {}

    def test_passed_true(self):
        assert ValidationReport(verdict=Verdict.PASS).passed is True

    def test_passed_false(self):
        assert ValidationReport(verdict=Verdict.REVIEW).passed is False
        assert ValidationReport(verdict=Verdict.REJECT).passed is False

    def test_errors_filter(self):
        e = ValidationIssue("E", Severity.ERROR, "m", "drug")
        w = ValidationIssue("W", Severity.WARNING, "m", "drug")
        r = ValidationReport(verdict=Verdict.REJECT, issues=[e, w])
        assert r.errors == [e] and r.warnings == [w]

    def test_reviews_filter(self):
        rv = ValidationIssue("R", Severity.REVIEW, "m", "drug")
        e = ValidationIssue("E", Severity.ERROR, "m", "drug")
        r = ValidationReport(verdict=Verdict.REJECT, issues=[rv, e])
        assert r.reviews == [rv] and r.errors == [e]

    def test_warnings_filter(self):
        w = ValidationIssue("W", Severity.WARNING, "m", "drug")
        r = ValidationReport(verdict=Verdict.PASS, issues=[w])
        assert r.warnings == [w]

    def test_issue_count(self):
        a = ValidationIssue("A", Severity.WARNING, "m", "drug")
        b = ValidationIssue("B", Severity.ERROR, "m", "dose")
        r = ValidationReport(verdict=Verdict.REJECT, issues=[a, b])
        assert r.issue_count == 2

    def test_to_dict(self):
        i = ValidationIssue("E", Severity.ERROR, "msg", "drug", "fix")
        r = ValidationReport(verdict=Verdict.REJECT, issues=[i], metadata={"x": 1})
        d = r.to_dict()
        assert d["verdict"] == "REJECT"
        assert d["issues"][0]["code"] == "E"
        assert d["metadata"] == {"x": 1}

    def test_empty_report(self):
        r = ValidationReport(verdict=Verdict.PASS)
        assert r.errors == [] and r.reviews == [] and r.warnings == []
        assert r.issue_count == 0


# -- check_required_fields -------------------------------------------


class TestCheckRequiredFields:
    def test_perfect_no_issues(self):
        assert Validator.check_required_fields(_perfect_regimen()) == []

    def test_missing_drug(self):
        r = NormalizedRegimen(dose_value=1.0, route="iv", frequency_per_day=1.0)
        iss = Validator.check_required_fields(r)
        assert len(iss) == 1
        assert iss[0].code == "REQUIRED_MISSING"
        assert iss[0].severity == Severity.ERROR
        assert iss[0].field == "drug"

    def test_missing_dose(self):
        r = NormalizedRegimen(drug_normalized="Цефтриаксон", route="iv", frequency_per_day=1.0)
        iss = Validator.check_required_fields(r)
        assert len(iss) == 1 and iss[0].field == "dose"

    def test_missing_route(self):
        r = NormalizedRegimen(drug_normalized="Цефтриаксон", dose_value=1.0, frequency_per_day=1.0)
        r.route = "unknown"
        iss = Validator.check_required_fields(r)
        assert len(iss) == 1 and iss[0].field == "route"

    def test_missing_frequency(self):
        r = NormalizedRegimen(drug_normalized="Цефтриаксон", dose_value=1.0, route="iv")
        iss = Validator.check_required_fields(r)
        assert len(iss) == 1 and iss[0].field == "frequency"

    def test_all_required_missing(self):
        iss = Validator.check_required_fields(_bare_regimen())
        codes = {i.field for i in iss}
        assert codes == {"drug", "dose", "route", "frequency"}
        assert all(i.severity == Severity.ERROR for i in iss)

    def test_empty_string_drug(self):
        r = NormalizedRegimen(drug_normalized="", dose_value=1.0, route="iv", frequency_per_day=1.0)
        iss = Validator.check_required_fields(r)
        assert len(iss) == 1 and iss[0].field == "drug"

    def test_suggested_fix_drug_with_original(self):
        r = NormalizedRegimen(drug_original="Цефтриаксон", dose_value=1.0, route="iv", frequency_per_day=1.0)
        iss = Validator.check_required_fields(r)
        assert iss[0].suggested_fix is not None
        assert "Цефтриаксон" in iss[0].suggested_fix

    def test_suggested_fix_route(self):
        r = NormalizedRegimen(drug_normalized="X", dose_value=1.0, frequency_per_day=1.0)
        r.route = "unknown"
        iss = Validator.check_required_fields(r)
        assert iss[0].suggested_fix is not None

    def test_suggested_fix_frequency(self):
        r = NormalizedRegimen(drug_normalized="X", dose_value=1.0, route="iv")
        iss = Validator.check_required_fields(r)
        assert iss[0].suggested_fix is not None

    def test_unknown_required_field_not_missing(self):
        # _is_missing returns False for unknown field names -> no issue
        r = NormalizedRegimen(drug_normalized="X", dose_value=1.0, route="iv", frequency_per_day=1.0)
        original = Validator.config
        try:
            Validator.config = ValidatorConfig(required_fields=("bogus",))
            iss = Validator.check_required_fields(r)
            assert iss == []
        finally:
            Validator.config = original


# -- check_drug_exists -----------------------------------------------


class TestCheckDrugExists:
    def test_known_drug_no_issue(self):
        assert Validator.check_drug_exists(_perfect_regimen()) == []

    def test_unknown_drug_review(self):
        r = NormalizedRegimen(drug_normalized="Неизвестный антибиотик")
        iss = Validator.check_drug_exists(r)
        assert len(iss) == 1
        assert iss[0].code == "DRUG_UNKNOWN"
        assert iss[0].severity == Severity.REVIEW

    def test_empty_drug_no_issue(self):
        assert Validator.check_drug_exists(_empty_regimen()) == []

    def test_case_insensitive_known(self):
        r = NormalizedRegimen(drug_normalized="цефтриаксон")
        assert Validator.check_drug_exists(r) == []

    def test_combination_known(self):
        r = NormalizedRegimen(drug_normalized="Амоксициллин + клавулановая кислота")
        assert Validator.check_drug_exists(r) == []


# -- check_dose_positive ---------------------------------------------


class TestCheckDosePositive:
    def test_valid_dose_no_issue(self):
        assert Validator.check_dose_positive(_perfect_regimen()) == []

    def test_none_dose_no_issue(self):
        assert Validator.check_dose_positive(_empty_regimen()) == []

    def test_zero_dose_error(self):
        r = NormalizedRegimen(dose_value=0.0)
        iss = Validator.check_dose_positive(r)
        assert len(iss) == 1 and iss[0].code == "DOSE_NOT_POSITIVE"
        assert iss[0].severity == Severity.ERROR

    def test_negative_dose_error(self):
        r = NormalizedRegimen(dose_value=-5.0)
        iss = Validator.check_dose_positive(r)
        assert len(iss) == 1 and iss[0].code == "DOSE_NOT_POSITIVE"

    def test_huge_dose_error(self):
        r = NormalizedRegimen(dose_value=2_000_000.0)
        iss = Validator.check_dose_positive(r)
        assert len(iss) == 1 and iss[0].code == "DOSE_OUT_OF_RANGE"

    def test_unknown_unit_review(self):
        r = NormalizedRegimen(dose_value=500.0, dose_unit="blarg")
        iss = Validator.check_dose_positive(r)
        assert len(iss) == 1 and iss[0].code == "DOSE_UNIT_UNKNOWN"
        assert iss[0].severity == Severity.REVIEW

    def test_known_unit_no_issue(self):
        r = NormalizedRegimen(dose_value=500.0, dose_unit="mg")
        assert Validator.check_dose_positive(r) == []

    def test_no_unit_no_issue(self):
        r = NormalizedRegimen(dose_value=500.0, dose_unit=None)
        assert Validator.check_dose_positive(r) == []

    def test_empty_unit_no_issue(self):
        r = NormalizedRegimen(dose_value=500.0, dose_unit="")
        assert Validator.check_dose_positive(r) == []


# -- check_frequency_valid -------------------------------------------


class TestCheckFrequencyValid:
    def test_valid_no_issue(self):
        assert Validator.check_frequency_valid(_perfect_regimen()) == []

    def test_none_no_issue(self):
        assert Validator.check_frequency_valid(_empty_regimen()) == []

    def test_zero_error(self):
        r = NormalizedRegimen(frequency_per_day=0.0)
        iss = Validator.check_frequency_valid(r)
        assert len(iss) == 1 and iss[0].code == "FREQUENCY_NOT_POSITIVE"

    def test_negative_error(self):
        r = NormalizedRegimen(frequency_per_day=-1.0)
        iss = Validator.check_frequency_valid(r)
        assert len(iss) == 1 and iss[0].code == "FREQUENCY_NOT_POSITIVE"

    def test_above_max_error(self):
        r = NormalizedRegimen(frequency_per_day=25.0)
        iss = Validator.check_frequency_valid(r)
        assert len(iss) == 1 and iss[0].code == "FREQUENCY_OUT_OF_RANGE"

    def test_max_boundary_ok(self):
        r = NormalizedRegimen(frequency_per_day=24.0)
        assert Validator.check_frequency_valid(r) == []

    def test_small_positive_ok(self):
        r = NormalizedRegimen(frequency_per_day=0.5)
        assert Validator.check_frequency_valid(r) == []


# -- check_duration_valid --------------------------------------------


class TestCheckDurationValid:
    def test_valid_no_issue(self):
        assert Validator.check_duration_valid(_perfect_regimen()) == []

    def test_none_no_issue(self):
        assert Validator.check_duration_valid(_empty_regimen()) == []

    def test_negative_min_error(self):
        r = NormalizedRegimen(duration_days_min=-1.0)
        iss = Validator.check_duration_valid(r)
        assert any(i.code == "DURATION_NEGATIVE" for i in iss)

    def test_negative_max_error(self):
        r = NormalizedRegimen(duration_days_max=-1.0)
        iss = Validator.check_duration_valid(r)
        assert any(i.code == "DURATION_NEGATIVE" for i in iss)

    def test_negative_recommended_error(self):
        r = NormalizedRegimen(duration_days_recommended=-1.0)
        iss = Validator.check_duration_valid(r)
        assert any(i.code == "DURATION_NEGATIVE" for i in iss)

    def test_above_max_error(self):
        r = NormalizedRegimen(duration_days_min=400.0)
        iss = Validator.check_duration_valid(r)
        assert any(i.code == "DURATION_OUT_OF_RANGE" for i in iss)

    def test_max_boundary_ok(self):
        r = NormalizedRegimen(duration_days_min=365.0)
        assert Validator.check_duration_valid(r) == []

    def test_min_gt_max_error(self):
        r = NormalizedRegimen(duration_days_min=10.0, duration_days_max=5.0)
        iss = Validator.check_duration_valid(r)
        assert any(i.code == "DURATION_MIN_GT_MAX" for i in iss)

    def test_min_eq_max_ok(self):
        r = NormalizedRegimen(duration_days_min=7.0, duration_days_max=7.0)
        assert Validator.check_duration_valid(r) == []

    def test_only_min_ok(self):
        r = NormalizedRegimen(duration_days_min=7.0)
        assert Validator.check_duration_valid(r) == []

    def test_only_max_ok(self):
        r = NormalizedRegimen(duration_days_max=10.0)
        assert Validator.check_duration_valid(r) == []

    def test_multiple_issues_collected(self):
        r = NormalizedRegimen(
            duration_days_min=-1.0,
            duration_days_max=400.0,
            duration_days_recommended=-5.0,
        )
        iss = Validator.check_duration_valid(r)
        assert len(iss) >= 3


# -- check_route_valid -----------------------------------------------


class TestCheckRouteValid:
    def test_valid_iv(self):
        assert Validator.check_route_valid(NormalizedRegimen(route="iv")) == []

    def test_valid_oral(self):
        assert Validator.check_route_valid(NormalizedRegimen(route="oral")) == []

    def test_valid_im(self):
        assert Validator.check_route_valid(NormalizedRegimen(route="im")) == []

    def test_valid_topical(self):
        assert Validator.check_route_valid(NormalizedRegimen(route="topical")) == []

    def test_valid_ophthalmic(self):
        assert Validator.check_route_valid(NormalizedRegimen(route="ophthalmic")) == []

    def test_valid_inhalation(self):
        assert Validator.check_route_valid(NormalizedRegimen(route="inhalation")) == []

    def test_valid_otic(self):
        assert Validator.check_route_valid(NormalizedRegimen(route="otic")) == []

    def test_compound_route_ok(self):
        r = NormalizedRegimen(route="iv|im")
        assert Validator.check_route_valid(r) == []

    def test_unknown_route_review(self):
        r = NormalizedRegimen(route="unknown")
        iss = Validator.check_route_valid(r)
        assert len(iss) == 1 and iss[0].code == "ROUTE_UNKNOWN"
        assert iss[0].severity == Severity.REVIEW

    def test_invalid_route_error(self):
        r = NormalizedRegimen(route="bogus")
        iss = Validator.check_route_valid(r)
        assert len(iss) == 1 and iss[0].code == "ROUTE_INVALID"
        assert iss[0].severity == Severity.ERROR

    def test_empty_route_no_issue(self):
        r = NormalizedRegimen(route="")
        assert Validator.check_route_valid(r) == []

    def test_compound_with_invalid_part_error(self):
        r = NormalizedRegimen(route="iv|bogus")
        iss = Validator.check_route_valid(r)
        assert len(iss) == 1 and iss[0].code == "ROUTE_INVALID"


# -- check_component_consistency -------------------------------------


class TestCheckComponentConsistency:
    def test_single_drug_no_components_no_issue(self):
        r = NormalizedRegimen(drug_normalized="Цефтриаксон")
        assert Validator.check_component_consistency(r) == []

    def test_combination_with_components_no_issue(self):
        r = NormalizedRegimen(drug_normalized="Амоксициллин + клавулановая кислота")
        r.drug_components = [
            DrugComponent(name="Амоксициллин", dose_value=875.0, dose_unit="mg"),
            DrugComponent(name="Клавулановая кислота", dose_value=125.0, dose_unit="mg"),
        ]
        assert Validator.check_component_consistency(r) == []

    def test_combination_without_components_review(self):
        r = NormalizedRegimen(drug_normalized="Амоксициллин + клавулановая кислота")
        iss = Validator.check_component_consistency(r)
        assert len(iss) == 1 and iss[0].code == "COMBINATION_MISSING_COMPONENTS"
        assert iss[0].severity == Severity.REVIEW

    def test_components_without_combination_review(self):
        r = NormalizedRegimen(drug_normalized="Цефтриаксон")
        r.drug_components = [DrugComponent(name="Цефтриаксон", dose_value=1.0)]
        iss = Validator.check_component_consistency(r)
        assert len(iss) == 1 and iss[0].code == "COMPONENTS_WITHOUT_COMBINATION"
        assert iss[0].severity == Severity.REVIEW

    def test_component_empty_name_error(self):
        r = NormalizedRegimen(drug_normalized="Амоксициллин + клавулановая кислота")
        r.drug_components = [
            DrugComponent(name="Амоксициллин"),
            DrugComponent(name=""),
        ]
        iss = Validator.check_component_consistency(r)
        assert any(i.code == "COMPONENT_NAME_MISSING" for i in iss)
        assert i_severity(iss, "COMPONENT_NAME_MISSING") == Severity.ERROR

    def test_empty_drug_no_components_no_issue(self):
        r = NormalizedRegimen()
        assert Validator.check_component_consistency(r) == []


def i_severity(issues, code):
    for i in issues:
        if i.code == code:
            return i.severity
    return None


# -- check_atc_format ------------------------------------------------


class TestCheckAtcFormat:
    def test_valid_atc_no_issue(self):
        r = NormalizedRegimen(atc_code="J01DD04")
        assert Validator.check_atc_format(r) == []

    def test_none_atc_no_issue(self):
        assert Validator.check_atc_format(_empty_regimen()) == []

    def test_empty_atc_no_issue(self):
        r = NormalizedRegimen(atc_code="")
        assert Validator.check_atc_format(r) == []

    def test_lowercase_atc_warning(self):
        r = NormalizedRegimen(atc_code="j01dd04")
        iss = Validator.check_atc_format(r)
        assert len(iss) == 1 and iss[0].code == "ATC_FORMAT_INVALID"
        assert iss[0].severity == Severity.WARNING

    def test_too_short_warning(self):
        r = NormalizedRegimen(atc_code="J01DD")
        iss = Validator.check_atc_format(r)
        assert len(iss) == 1 and iss[0].code == "ATC_FORMAT_INVALID"

    def test_too_long_warning(self):
        r = NormalizedRegimen(atc_code="J01DD044")
        iss = Validator.check_atc_format(r)
        assert len(iss) == 1 and iss[0].code == "ATC_FORMAT_INVALID"

    def test_wrong_shape_warning(self):
        r = NormalizedRegimen(atc_code="ABCDE12345")
        iss = Validator.check_atc_format(r)
        assert len(iss) == 1 and iss[0].code == "ATC_FORMAT_INVALID"

    def test_another_valid(self):
        r = NormalizedRegimen(atc_code="A07AA01")
        assert Validator.check_atc_format(r) == []


# -- check_pregnancy_consistency -------------------------------------


class TestCheckPregnancyConsistency:
    def test_none_no_issue(self):
        assert Validator.check_pregnancy_consistency(_empty_regimen()) == []

    def test_true_with_adult_no_issue(self):
        r = NormalizedRegimen(pregnancy=True, adult=True)
        assert Validator.check_pregnancy_consistency(r) == []

    def test_true_with_child_no_issue(self):
        r = NormalizedRegimen(pregnancy=True, child=True, adult=False)
        assert Validator.check_pregnancy_consistency(r) == []

    def test_true_without_population_review(self):
        r = NormalizedRegimen(pregnancy=True, adult=False, child=False)
        iss = Validator.check_pregnancy_consistency(r)
        assert len(iss) == 1 and iss[0].code == "PREGNANCY_WITHOUT_POPULATION"
        assert iss[0].severity == Severity.REVIEW
        assert iss[0].suggested_fix is not None

    def test_false_no_issue(self):
        r = NormalizedRegimen(pregnancy=False, adult=False, child=False)
        assert Validator.check_pregnancy_consistency(r) == []


# -- check_renal_adjustment_consistency ------------------------------


class TestCheckRenalAdjustmentConsistency:
    def test_false_no_issue(self):
        assert Validator.check_renal_adjustment_consistency(_empty_regimen()) == []

    def test_true_with_adult_no_issue(self):
        r = NormalizedRegimen(renal_adjustment=True, adult=True)
        assert Validator.check_renal_adjustment_consistency(r) == []

    def test_true_with_child_no_issue(self):
        r = NormalizedRegimen(renal_adjustment=True, child=True, adult=False)
        assert Validator.check_renal_adjustment_consistency(r) == []

    def test_true_without_population_review(self):
        r = NormalizedRegimen(renal_adjustment=True, adult=False, child=False)
        iss = Validator.check_renal_adjustment_consistency(r)
        assert len(iss) == 1 and iss[0].code == "RENAL_WITHOUT_POPULATION"
        assert iss[0].severity == Severity.REVIEW
        assert iss[0].suggested_fix is not None


# -- validate (full) -------------------------------------------------


class TestValidate:
    def test_returns_validation_report(self):
        assert isinstance(Validator.validate(_perfect_regimen()), ValidationReport)

    def test_perfect_passes(self):
        r = Validator.validate(_perfect_regimen())
        assert r.verdict == Verdict.PASS
        assert r.passed is True

    def test_perfect_no_errors(self):
        assert Validator.validate(_perfect_regimen()).errors == []

    def test_perfect_no_reviews(self):
        assert Validator.validate(_perfect_regimen()).reviews == []

    def test_bare_regimen_rejected(self):
        r = Validator.validate(_bare_regimen())
        assert r.verdict == Verdict.REJECT
        assert len(r.errors) >= 4

    def test_empty_regimen_rejected(self):
        # empty regimen has adult=True default; still missing drug/dose/route/freq
        r = Validator.validate(_empty_regimen())
        assert r.verdict == Verdict.REJECT

    def test_missing_drug_rejected(self):
        r = NormalizedRegimen(
            dose_value=1.0, route="iv", frequency_per_day=1.0,
            duration_days_min=7.0, adult=True,
        )
        rep = Validator.validate(r)
        assert rep.verdict == Verdict.REJECT
        assert any(i.code == "REQUIRED_MISSING" and i.field == "drug" for i in rep.errors)

    def test_unknown_drug_review_verdict(self):
        r = NormalizedRegimen(
            drug_normalized="Неизвестный антибиотик",
            dose_value=1.0, route="iv", frequency_per_day=1.0,
        )
        rep = Validator.validate(r)
        assert rep.verdict == Verdict.REVIEW
        assert len(rep.reviews) >= 1
        assert rep.errors == []

    def test_unknown_route_error_rejected(self):
        r = NormalizedRegimen(
            drug_normalized="Цефтриаксон",
            dose_value=1.0, route="bogus", frequency_per_day=1.0,
        )
        rep = Validator.validate(r)
        assert rep.verdict == Verdict.REJECT

    def test_negative_dose_rejected(self):
        r = NormalizedRegimen(
            drug_normalized="Цефтриаксон",
            dose_value=-1.0, route="iv", frequency_per_day=1.0,
        )
        rep = Validator.validate(r)
        assert rep.verdict == Verdict.REJECT
        assert any(i.code == "DOSE_NOT_POSITIVE" for i in rep.errors)

    def test_additive_multiple_errors(self):
        r = NormalizedRegimen(
            drug_normalized="",
            dose_value=-1.0, route="bogus", frequency_per_day=0.0,
        )
        rep = Validator.validate(r)
        assert rep.verdict == Verdict.REJECT
        assert len(rep.errors) >= 4

    def test_atc_warning_does_not_block_pass(self):
        # atc warning + otherwise perfect -> still PASS (warnings don't block)
        r = _perfect_regimen()
        r.atc_code = "bad"
        rep = Validator.validate(r)
        assert rep.warnings
        assert rep.verdict == Verdict.PASS

    def test_atc_warning_with_review_is_review(self):
        r = _perfect_regimen()
        r.atc_code = "bad"
        r.drug_normalized = "Неизвестный"
        rep = Validator.validate(r)
        assert rep.verdict == Verdict.REVIEW

    def test_review_with_warning_still_review(self):
        r = NormalizedRegimen(
            drug_normalized="Неизвестный",
            dose_value=1.0, route="iv", frequency_per_day=1.0,
        )
        r.atc_code = "bad"
        rep = Validator.validate(r)
        assert rep.verdict == Verdict.REVIEW
        assert rep.reviews and rep.warnings

    def test_error_overrides_review(self):
        # unknown drug (review) + missing dose (error) -> REJECT
        r = NormalizedRegimen(drug_normalized="Неизвестный", route="iv", frequency_per_day=1.0)
        rep = Validator.validate(r)
        assert rep.verdict == Verdict.REJECT
        assert rep.errors and rep.reviews


# -- validate_field --------------------------------------------------


class TestValidateField:
    def test_drug_field_issues(self):
        r = NormalizedRegimen(drug_normalized="", dose_value=1.0, route="iv", frequency_per_day=1.0)
        iss = Validator.validate_field("drug", r)
        assert all(i.field == "drug" for i in iss)
        assert any(i.code == "REQUIRED_MISSING" for i in iss)

    def test_dose_field_issues(self):
        r = NormalizedRegimen(drug_normalized="Цефтриаксон", dose_value=-1.0, route="iv", frequency_per_day=1.0)
        iss = Validator.validate_field("dose", r)
        assert all(i.field == "dose" for i in iss)
        assert any(i.code == "DOSE_NOT_POSITIVE" for i in iss)

    def test_route_field_issues(self):
        r = NormalizedRegimen(drug_normalized="X", dose_value=1.0, route="bogus", frequency_per_day=1.0)
        iss = Validator.validate_field("route", r)
        assert all(i.field == "route" for i in iss)

    def test_frequency_field_issues(self):
        r = NormalizedRegimen(drug_normalized="X", dose_value=1.0, route="iv", frequency_per_day=0.0)
        iss = Validator.validate_field("frequency", r)
        assert all(i.field == "frequency" for i in iss)

    def test_atc_field_issues(self):
        r = NormalizedRegimen(drug_normalized="X", dose_value=1.0, route="iv", frequency_per_day=1.0)
        r.atc_code = "bad"
        iss = Validator.validate_field("atc_code", r)
        assert all(i.field == "atc_code" for i in iss)

    def test_empty_when_field_clean(self):
        r = _perfect_regimen()
        assert Validator.validate_field("drug", r) == []

    def test_no_cross_field_leak(self):
        # dose error should NOT appear in route field results
        r = NormalizedRegimen(drug_normalized="X", dose_value=-1.0, route="iv", frequency_per_day=1.0)
        iss = Validator.validate_field("route", r)
        assert iss == []


# -- is_valid --------------------------------------------------------


class TestIsValid:
    def test_perfect_true(self):
        assert Validator.is_valid(_perfect_regimen()) is True

    def test_bare_false(self):
        assert Validator.is_valid(_bare_regimen()) is False

    def test_review_false(self):
        r = NormalizedRegimen(
            drug_normalized="Неизвестный",
            dose_value=1.0, route="iv", frequency_per_day=1.0,
        )
        assert Validator.is_valid(r) is False

    def test_warning_only_true(self):
        r = _perfect_regimen()
        r.atc_code = "bad"
        assert Validator.is_valid(r) is True


# -- verdict derivation ----------------------------------------------


class TestVerdictDerivation:
    def test_no_issues_pass(self):
        assert Validator._derive_verdict([]) == Verdict.PASS

    def test_warning_only_pass(self):
        w = ValidationIssue("W", Severity.WARNING, "m", "atc_code")
        assert Validator._derive_verdict([w]) == Verdict.PASS

    def test_review_only_review(self):
        rv = ValidationIssue("R", Severity.REVIEW, "m", "drug")
        assert Validator._derive_verdict([rv]) == Verdict.REVIEW

    def test_error_only_reject(self):
        e = ValidationIssue("E", Severity.ERROR, "m", "drug")
        assert Validator._derive_verdict([e]) == Verdict.REJECT

    def test_error_and_review_reject(self):
        e = ValidationIssue("E", Severity.ERROR, "m", "drug")
        rv = ValidationIssue("R", Severity.REVIEW, "m", "drug")
        assert Validator._derive_verdict([e, rv]) == Verdict.REJECT

    def test_error_and_warning_reject(self):
        e = ValidationIssue("E", Severity.ERROR, "m", "drug")
        w = ValidationIssue("W", Severity.WARNING, "m", "atc_code")
        assert Validator._derive_verdict([e, w]) == Verdict.REJECT

    def test_review_and_warning_review(self):
        rv = ValidationIssue("R", Severity.REVIEW, "m", "drug")
        w = ValidationIssue("W", Severity.WARNING, "m", "atc_code")
        assert Validator._derive_verdict([rv, w]) == Verdict.REVIEW

    def test_all_three_reject(self):
        e = ValidationIssue("E", Severity.ERROR, "m", "drug")
        rv = ValidationIssue("R", Severity.REVIEW, "m", "drug")
        w = ValidationIssue("W", Severity.WARNING, "m", "atc_code")
        assert Validator._derive_verdict([e, rv, w]) == Verdict.REJECT


# -- metadata --------------------------------------------------------


class TestMetadata:
    def test_perfect_metadata(self):
        m = Validator.validate(_perfect_regimen()).metadata
        assert m["verdict"] == "PASS"
        assert m["issue_count"] == 0
        assert m["error_count"] == 0
        assert m["review_count"] == 0
        assert m["warning_count"] == 0
        assert m["checks_run"] == 10
        assert m["drug_normalized"] == "Цефтриаксон"
        assert m["has_components"] is False

    def test_bare_metadata(self):
        m = Validator.validate(_bare_regimen()).metadata
        assert m["verdict"] == "REJECT"
        assert m["error_count"] >= 4
        assert m["issue_count"] == m["error_count"] + m["review_count"] + m["warning_count"]

    def test_combination_has_components_flag(self):
        r = NormalizedRegimen(
            drug_normalized="Амоксициллин + клавулановая кислота",
            dose_value=875.0, dose_unit="mg", route="oral", frequency_per_day=2.0,
        )
        r.drug_components = [DrugComponent(name="Амоксициллин"), DrugComponent(name="Клавулановая кислота")]
        m = Validator.validate(r).metadata
        assert m["has_components"] is True

    def test_review_metadata(self):
        r = NormalizedRegimen(
            drug_normalized="Неизвестный",
            dose_value=1.0, route="iv", frequency_per_day=1.0,
        )
        m = Validator.validate(r).metadata
        assert m["verdict"] == "REVIEW"
        assert m["review_count"] >= 1
        assert m["error_count"] == 0


# -- immutability / purity -------------------------------------------


class TestImmutability:
    def test_regimen_not_modified(self):
        r = _perfect_regimen()
        before = r.to_dict()
        Validator.validate(r)
        assert r.to_dict() == before

    def test_confidence_not_overwritten(self):
        r = _perfect_regimen()
        r.confidence = 0.777
        Validator.validate(r)
        assert r.confidence == 0.777

    def test_warnings_not_touched(self):
        r = _perfect_regimen()
        Validator.validate(r)
        assert r.warnings == []

    def test_drug_components_not_modified(self):
        r = NormalizedRegimen(drug_normalized="Амоксициллин + клавулановая кислота")
        r.drug_components = [DrugComponent(name="Амоксициллин", dose_value=875.0)]
        before = [c.__dict__.copy() for c in r.drug_components]
        Validator.validate(r)
        assert [c.__dict__ for c in r.drug_components] == before

    def test_validate_does_not_mutate_issues_input(self):
        issues = [
            ValidationIssue("E", Severity.ERROR, "m", "drug"),
            ValidationIssue("R", Severity.REVIEW, "m", "drug"),
        ]
        Validator._derive_verdict(issues)
        assert len(issues) == 2


# -- config-driven (no magic constants) ------------------------------


class TestConfigDriven:
    def test_custom_required_fields(self):
        original = Validator.config
        try:
            Validator.config = ValidatorConfig(required_fields=("drug",))
            # only drug required now
            r = NormalizedRegimen(route="unknown")
            iss = Validator.check_required_fields(r)
            assert all(i.field == "drug" for i in iss)
        finally:
            Validator.config = original

    def test_custom_dose_bounds(self):
        original = Validator.config
        try:
            Validator.config = ValidatorConfig(dose_max=10.0)
            r = NormalizedRegimen(dose_value=100.0)
            iss = Validator.check_dose_positive(r)
            assert any(i.code == "DOSE_OUT_OF_RANGE" for i in iss)
        finally:
            Validator.config = original

    def test_custom_frequency_max(self):
        original = Validator.config
        try:
            Validator.config = ValidatorConfig(frequency_max=6.0)
            r = NormalizedRegimen(frequency_per_day=8.0)
            iss = Validator.check_frequency_valid(r)
            assert any(i.code == "FREQUENCY_OUT_OF_RANGE" for i in iss)
        finally:
            Validator.config = original

    def test_custom_valid_routes(self):
        original = Validator.config
        try:
            Validator.config = ValidatorConfig(valid_routes=("oral",))
            r = NormalizedRegimen(route="iv")
            iss = Validator.check_route_valid(r)
            assert any(i.code == "ROUTE_INVALID" for i in iss)
        finally:
            Validator.config = original

    def test_custom_atc_pattern(self):
        original = Validator.config
        try:
            Validator.config = ValidatorConfig(atc_pattern=r"^\d+$")
            r = NormalizedRegimen(atc_code="12345")
            assert Validator.check_atc_format(r) == []
            r2 = NormalizedRegimen(atc_code="J01DD04")
            assert len(Validator.check_atc_format(r2)) == 1
        finally:
            Validator.config = original


# -- edge cases ------------------------------------------------------


class TestEdgeCases:
    def test_cyrillic_drug_known(self):
        r = NormalizedRegimen(drug_normalized="Цефтриаксон")
        assert Validator.check_drug_exists(r) == []

    def test_cyrillic_drug_unknown(self):
        r = NormalizedRegimen(drug_normalized="Рандомный препарат")
        assert len(Validator.check_drug_exists(r)) == 1

    def test_dose_just_above_zero(self):
        r = NormalizedRegimen(dose_value=0.001)
        assert Validator.check_dose_positive(r) == []

    def test_frequency_just_above_zero(self):
        r = NormalizedRegimen(frequency_per_day=0.001)
        assert Validator.check_frequency_valid(r) == []

    def test_duration_zero_ok(self):
        r = NormalizedRegimen(duration_days_min=0.0)
        assert Validator.check_duration_valid(r) == []

    def test_route_with_spaces_not_in_vocab(self):
        r = NormalizedRegimen(route="внутривенно")
        iss = Validator.check_route_valid(r)
        # raw cyrillic not normalized -> invalid
        assert iss and iss[0].code == "ROUTE_INVALID"

    def test_combination_normalized_but_no_plus_in_normalized(self):
        # edge: drug_normalized has no +, components present -> review
        r = NormalizedRegimen(drug_normalized="Амоксициллин")
        r.drug_components = [DrugComponent(name="Амоксициллин")]
        iss = Validator.check_component_consistency(r)
        assert any(i.code == "COMPONENTS_WITHOUT_COMBINATION" for i in iss)

    def test_validate_idempotent(self):
        r = _perfect_regimen()
        a = Validator.validate(r)
        b = Validator.validate(r)
        assert a.verdict == b.verdict
        assert len(a.issues) == len(b.issues)

    def test_report_to_dict_round_trip(self):
        rep = Validator.validate(_perfect_regimen())
        d = rep.to_dict()
        assert d["verdict"] == rep.verdict.value
        assert len(d["issues"]) == len(rep.issues)

    def test_perfect_regimen_has_no_issues_at_all(self):
        rep = Validator.validate(_perfect_regimen())
        assert rep.issues == []

    def test_bare_regimen_all_errors(self):
        rep = Validator.validate(_bare_regimen())
        assert all(i.severity == Severity.ERROR for i in rep.errors)

    def test_validate_does_not_short_circuit(self):
        # multiple errors should all be collected
        r = NormalizedRegimen(
            drug_normalized="",
            dose_value=-1.0,
            route="bogus",
            frequency_per_day=0.0,
        )
        rep = Validator.validate(r)
        codes = {i.code for i in rep.errors}
        assert "REQUIRED_MISSING" in codes
        assert "DOSE_NOT_POSITIVE" in codes
        assert "ROUTE_INVALID" in codes
        assert "FREQUENCY_NOT_POSITIVE" in codes

    def test_check_registry_count(self):
        assert len(Validator._checks()) == 10
