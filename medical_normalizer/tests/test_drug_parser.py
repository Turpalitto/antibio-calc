"""Tests for drug_parser.py — DrugParser, DoseParser."""

from medical_normalizer.drug_parser import DrugParser, DoseNormalizer
from medical_normalizer.models import NormalizedRegimen


class TestDrugParser:
    def test_single_drug(self):
        raw = {"antibiotic": "Цефтриаксон", "dose": "1,0", "unit": "г"}
        reg = DrugParser.parse(NormalizedRegimen(), raw)
        assert reg.drug_original == "Цефтриаксон"
        assert reg.drug_normalized == "Цефтриаксон"
        assert reg.drug_components == []

    def test_brand_normalized(self):
        raw = {"antibiotic": "Сумамед", "dose": "500", "unit": "мг"}
        reg = DrugParser.parse(NormalizedRegimen(), raw)
        assert reg.drug_normalized == "Азитромицин"

    def test_combination_amoxiclav(self):
        raw = {"antibiotic": "Амоксициллин+клавулановая кислота", "dose": "875/125", "unit": "мг"}
        reg = DrugParser.parse(NormalizedRegimen(), raw)
        assert reg.drug_normalized == "Амоксициллин + клавулановая кислота"
        assert len(reg.drug_components) >= 2
        assert reg.drug_components[0].name == "Амоксициллин"
        assert reg.drug_components[1].name == "Клавулановая кислота"

    def test_combination_with_markers(self):
        raw = {"antibiotic": "#Амоксициллин+клавулановая кислота**", "dose": "500/50", "unit": "мг"}
        reg = DrugParser.parse(NormalizedRegimen(), raw)
        assert reg.drug_normalized == "Амоксициллин + клавулановая кислота"
        assert len(reg.drug_components) >= 2

    def test_component_dose_parsing(self):
        components = DrugParser._parse_components("Амоксициллин+клавулановая кислота", "875/125", "мг")
        assert len(components) == 2
        assert components[0].dose_value == 875.0
        assert components[1].dose_value == 125.0
        assert components[0].dose_unit == "mg"

    def test_component_doses_none(self):
        raw = {"antibiotic": "Амоксициллин+клавулановая кислота", "dose": "875/125", "unit": "мг"}
        doses = DrugParser._parse_component_doses("875/125")
        assert doses == [875.0, 125.0]

    def test_component_doses_slash(self):
        doses = DrugParser._parse_component_doses("500/50")
        assert doses == [500.0, 50.0]

    def test_component_doses_no_match(self):
        assert DrugParser._parse_component_doses("500") is None

    def test_component_doses_empty(self):
        assert DrugParser._parse_component_doses("") is None
        assert DrugParser._parse_component_doses(None) is None

    def test_no_antibiotic_field(self):
        raw = {"dose": "500", "unit": "мг"}
        reg = DrugParser.parse(NormalizedRegimen(), raw)
        assert reg.drug_original == ""
        assert reg.drug_normalized == ""

    def test_empty_antibiotic(self):
        raw = {"antibiotic": "", "dose": "500", "unit": "мг"}
        reg = DrugParser.parse(NormalizedRegimen(), raw)
        assert reg.drug_normalized == ""

    def test_marker_clean(self):
        raw = {"antibiotic": "Цефтриаксон**", "dose": "1,0", "unit": "г"}
        reg = DrugParser.parse(NormalizedRegimen(), raw)
        assert reg.drug_original == "Цефтриаксон**"
        assert reg.drug_normalized == "Цефтриаксон"

    def test_hash_clean(self):
        raw = {"antibiotic": "#Цефтриаксон**", "dose": "1,0", "unit": "г"}
        reg = DrugParser.parse(NormalizedRegimen(), raw)
        assert reg.drug_normalized == "Цефтриаксон"


class TestDoseParser:
    def test_simple_integer(self):
        raw = {"dose": "500", "unit": "мг"}
        reg = DoseNormalizer.parse(NormalizedRegimen(), raw)
        assert reg.dose_value == 500.0
        assert reg.dose_unit == "mg"

    def test_comma_decimal(self):
        raw = {"dose": "0,5", "unit": "г"}
        reg = DoseNormalizer.parse(NormalizedRegimen(), raw)
        assert reg.dose_value == 0.5
        assert reg.dose_unit == "g"

    def test_dose_gram(self):
        raw = {"dose": "1,0", "unit": "г"}
        reg = DoseNormalizer.parse(NormalizedRegimen(), raw)
        assert reg.dose_value == 1.0
        assert reg.dose_unit == "g"

    def test_dose_range(self):
        raw = {"dose": "1,0-2,0", "unit": "г"}
        reg = DoseNormalizer.parse(NormalizedRegimen(), raw)
        assert reg.dose_value == 1.0
        assert reg.dose_unit == "g"

    # RC-030 repair Phase 9: the range regex's group(2) upper bound, previously
    # matched and then silently discarded, is now preserved additively.
    def test_dose_range_preserves_upper_bound(self):
        raw = {"dose": "20-50", "unit": "мг/кг"}
        reg = DoseNormalizer.parse(NormalizedRegimen(), raw)
        assert reg.dose_value == 20.0  # legacy scalar unchanged — byte-identical to prior behavior
        assert reg.dose_min == 20.0
        assert reg.dose_max == 50.0
        assert reg.dose_is_range is True

    def test_dose_scalar_backward_compatible(self):
        raw = {"dose": "500", "unit": "мг"}
        reg = DoseNormalizer.parse(NormalizedRegimen(), raw)
        assert reg.dose_value == 500.0
        assert reg.dose_min == 500.0 and reg.dose_max == 500.0
        assert reg.dose_is_range is False
        # to_dict() unchanged — no new keys leak into authoritative serialization
        assert "dose_min" not in reg.to_dict()
        assert "dose_min" in reg.to_dict_with_range()

    def test_no_dose(self):
        raw = {"dose": "", "unit": "мг"}
        reg = DoseNormalizer.parse(NormalizedRegimen(), raw)
        assert reg.dose_value is None

    def test_no_dose_and_no_unit(self):
        raw = {"dose": "", "unit": ""}
        reg = DoseNormalizer.parse(NormalizedRegimen(), raw)
        assert reg.dose_value is None
        assert reg.dose_unit is None

    def test_unit_iu(self):
        raw = {"dose": "500000", "unit": "ед"}
        reg = DoseNormalizer.parse(NormalizedRegimen(), raw)
        assert reg.dose_value == 500000.0
        assert reg.dose_unit == "IU"

    def test_unit_ml(self):
        raw = {"dose": "10", "unit": "мл"}
        reg = DoseNormalizer.parse(NormalizedRegimen(), raw)
        assert reg.dose_value == 10.0
        assert reg.dose_unit == "ml"

    def test_mg_kg(self):
        raw = {"dose": "15", "unit": "мг/кг"}
        reg = DoseNormalizer.parse(NormalizedRegimen(), raw)
        assert reg.dose_value == 15.0
        # The unit "мг/кг" is not in the dictionary, so it's preserved as-is
        assert reg.dose_unit == "mg/kg" or reg.dose_unit is None

    def test_compound_dose_875_125(self):
        # Compound dose should parse first value
        raw = {"dose": "875/125", "unit": "мг"}
        reg = DoseNormalizer.parse(NormalizedRegimen(), raw)
        # The slash makes it not a simple number
        assert reg.dose_value is not None

    def test_empty_regimen(self):
        raw = {}
        reg = DoseNormalizer.parse(NormalizedRegimen(), raw)
        assert reg.dose_value is None
        assert reg.dose_unit is None

    def test_dose_whitespace(self):
        raw = {"dose": "  500  ", "unit": "  мг  "}
        reg = DoseNormalizer.parse(NormalizedRegimen(), raw)
        assert reg.dose_value == 500.0
        assert reg.dose_unit == "mg"

    # ── Type guards: non-string dose/unit (real production errors) ──

    def test_dose_int(self):
        raw = {"dose": 250, "unit": "мг"}
        reg = DoseNormalizer.parse(NormalizedRegimen(), raw)
        assert reg.dose_value == 250.0
        assert reg.dose_unit == "mg"

    def test_dose_int_large(self):
        raw = {"dose": 1200, "unit": "мг"}
        reg = DoseNormalizer.parse(NormalizedRegimen(), raw)
        assert reg.dose_value == 1200.0

    def test_dose_float(self):
        raw = {"dose": 1.5, "unit": "МЕ"}
        reg = DoseNormalizer.parse(NormalizedRegimen(), raw)
        assert reg.dose_value == 1.5

    def test_dose_float_2_4(self):
        raw = {"dose": 2.4, "unit": "МЕ"}
        reg = DoseNormalizer.parse(NormalizedRegimen(), raw)
        assert reg.dose_value == 2.4

    def test_dose_zero_int(self):
        raw = {"dose": 0, "unit": "мг"}
        reg = DoseNormalizer.parse(NormalizedRegimen(), raw)
        assert reg.dose_value is None

    def test_unit_int(self):
        raw = {"dose": "500", "unit": 5}
        reg = DoseNormalizer.parse(NormalizedRegimen(), raw)
        assert reg.dose_value == 500.0

    def test_drug_parser_with_int_dose(self):
        raw = {"antibiotic": "Азитромицин", "dose": 250, "unit": "мг"}
        reg = DrugParser.parse(NormalizedRegimen(), raw)
        assert reg.drug_normalized == "Азитромицин"
        assert reg.drug_components == []

    def test_drug_parser_combination_with_int_dose(self):
        raw = {"antibiotic": "Амоксициллин+клавулановая кислота", "dose": 875, "unit": "мг"}
        reg = DrugParser.parse(NormalizedRegimen(), raw)
        assert reg.drug_normalized == "Амоксициллин + клавулановая кислота"
        assert len(reg.drug_components) >= 2

    def test_drug_parser_with_float_dose(self):
        raw = {"antibiotic": "Бензатина бензилпенициллин", "dose": 1.5, "unit": "МЕ"}
        reg = DrugParser.parse(NormalizedRegimen(), raw)
        assert reg.drug_original == "Бензатина бензилпенициллин"


# ── Regression tests: C1, C2, C3, M4, M17, L1 ──────────────────────


class TestC1NonFiniteDoseRejected:
    """C1: float("NaN") passed every bound check, so a NaN dose reached
    verdict=PASS with dose=NULL and range_confidence=1.0."""

    def test_nan_string_rejected(self):
        reg = DoseNormalizer.parse(NormalizedRegimen(), {"dose": "NaN", "unit": "мг"})
        assert reg.dose_value is None
        assert reg.dose_min is None and reg.dose_max is None
        assert reg.dose_is_range is None

    def test_inf_string_rejected(self):
        reg = DoseNormalizer.parse(NormalizedRegimen(), {"dose": "inf", "unit": "мг"})
        assert reg.dose_value is None

    def test_negative_inf_string_rejected(self):
        reg = DoseNormalizer.parse(NormalizedRegimen(), {"dose": "-inf", "unit": "мг"})
        assert reg.dose_value is None

    def test_float_nan_value_rejected(self):
        reg = DoseNormalizer.parse(NormalizedRegimen(), {"dose": float("nan"), "unit": "мг"})
        assert reg.dose_value is None

    def test_nan_no_range_confidence(self):
        reg = DoseNormalizer.parse(NormalizedRegimen(), {"dose": "NaN", "unit": "мг"})
        assert reg.dose_range_confidence is None

    def test_scientific_notation_rejected(self):
        reg = DoseNormalizer.parse(NormalizedRegimen(), {"dose": "1e9", "unit": "мг"})
        assert reg.dose_value is None

    def test_nan_reaches_reject_verdict(self):
        from medical_normalizer.normalizer import MedicalNormalizer
        from medical_normalizer.validator import Verdict

        r = MedicalNormalizer.normalize({
            "antibiotic": "Цефтриаксон", "dose": "NaN", "unit": "мг",
            "route": "в/в", "frequency": "1 раз в день",
        })
        assert r.validation.verdict == Verdict.REJECT
        assert any(i.code == "REQUIRED_MISSING" and i.field == "dose"
                   for i in r.validation.errors)


class TestC2RussianCommaDisambiguation:
    """C2: every comma was replaced with a dot, so "1,000" became 1.0 mg —
    a 1000x underdose."""

    def test_decimal_comma_one_digit(self):
        assert DoseNormalizer.parse_number("1,5") == 1.5

    def test_decimal_comma_two_digits(self):
        assert DoseNormalizer.parse_number("0,25") == 0.25

    def test_thousands_comma_three_digits(self):
        assert DoseNormalizer.parse_number("1,000") == 1000.0

    def test_thousands_comma_five_digit_group(self):
        assert DoseNormalizer.parse_number("12,345") == 12345.0

    def test_thousands_then_decimal(self):
        assert DoseNormalizer.parse_number("1,000,5") == 1000.5

    def test_space_thousands_still_works(self):
        assert DoseNormalizer.parse_number("1 000") == 1000.0

    def test_space_thousands_then_decimal(self):
        assert DoseNormalizer.parse_number("1 000,5") == 1000.5

    def test_ambiguous_four_digit_group_refused(self):
        # fail closed: "1,0000" is neither a 3-digit group nor 1-2 decimals
        assert DoseNormalizer.parse_number("1,0000") is None

    def test_thousands_via_parser(self):
        reg = DoseNormalizer.parse(NormalizedRegimen(), {"dose": "1,000", "unit": "мг"})
        assert reg.dose_value == 1000.0
        assert reg.dose_min == 1000.0 and reg.dose_max == 1000.0

    def test_thousands_then_decimal_via_parser(self):
        reg = DoseNormalizer.parse(NormalizedRegimen(), {"dose": "1,000,5", "unit": "мг"})
        assert reg.dose_value == 1000.5

    def test_thousands_range_via_parser(self):
        reg = DoseNormalizer.parse(NormalizedRegimen(), {"dose": "1,000-2,000", "unit": "мг"})
        assert reg.dose_value == 1000.0
        assert reg.dose_max == 2000.0
        assert reg.dose_is_range is True

    def test_decimal_unchanged(self):
        reg = DoseNormalizer.parse(NormalizedRegimen(), {"dose": "0,5", "unit": "г"})
        assert reg.dose_value == 0.5


class TestC3CombinationStrength:
    """C3: "875/125" collapsed to a single 875 mg dose with
    dose_range_confidence=1.0, because _dose_re had no "/" alternative."""

    def test_two_components_summed(self):
        reg = DoseNormalizer.parse(NormalizedRegimen(), {"dose": "875/125", "unit": "мг"})
        assert reg.dose_value == 1000.0
        assert reg.dose_component_count == 2
        assert reg.dose_is_range is False
        assert reg.dose_min == 1000.0 and reg.dose_max == 1000.0

    def test_combination_does_not_claim_full_range_confidence(self):
        reg = DoseNormalizer.parse(NormalizedRegimen(), {"dose": "875/125", "unit": "мг"})
        assert reg.dose_range_confidence < 1.0
        assert reg.dose_range_confidence == DoseNormalizer.COMBINATION_CONFIDENCE

    def test_combination_raw_preserved(self):
        reg = DoseNormalizer.parse(NormalizedRegimen(), {"dose": "875/125", "unit": "мг"})
        assert reg.dose_range_raw == "875/125"

    def test_combination_records_warning(self):
        reg = DoseNormalizer.parse(NormalizedRegimen(), {"dose": "875/125", "unit": "мг"})
        assert "DOSE_COMBINATION_STRENGTH" in reg.warnings

    def test_three_components_summed(self):
        reg = DoseNormalizer.parse(NormalizedRegimen(), {"dose": "1/2/3", "unit": "мг"})
        assert reg.dose_value == 6.0
        assert reg.dose_component_count == 3

    def test_scalar_has_no_component_count(self):
        reg = DoseNormalizer.parse(NormalizedRegimen(), {"dose": "500", "unit": "мг"})
        assert reg.dose_component_count is None
        assert reg.dose_range_confidence == 1.0

    def test_div_sign_supported(self):
        reg = DoseNormalizer.parse(NormalizedRegimen(), {"dose": "500÷50", "unit": "мг"})
        assert reg.dose_value == 550.0

    def test_component_and_scalar_parsers_agree(self):
        components = DrugParser._parse_component_doses("875/125")
        reg = DoseNormalizer.parse(NormalizedRegimen(), {"dose": "875/125", "unit": "мг"})
        assert components == [875.0, 125.0]
        assert reg.dose_value == sum(components)

    def test_three_component_doses_not_lost(self):
        assert DrugParser._parse_component_doses("1/2/3") == [1.0, 2.0, 3.0]


class TestM4MalformedRanges:
    """M4: the reversed-range branch never set dose_range_raw."""

    def test_reversed_range_keeps_raw(self):
        reg = DoseNormalizer.parse(NormalizedRegimen(), {"dose": "2,0-1,0", "unit": "мг"})
        assert reg.dose_range_raw == "2,0-1,0"

    def test_reversed_range_is_not_a_range(self):
        reg = DoseNormalizer.parse(NormalizedRegimen(), {"dose": "2,0-1,0", "unit": "мг"})
        assert reg.dose_is_range is False
        assert reg.dose_value == 2.0
        assert reg.dose_max == 2.0

    def test_reversed_range_low_confidence(self):
        reg = DoseNormalizer.parse(NormalizedRegimen(), {"dose": "2,0-1,0", "unit": "мг"})
        assert reg.dose_range_confidence == 0.5

    def test_reversed_range_reaches_reject(self):
        # dose_min > dose_max is now an ERROR (DOSE_RANGE_INVERTED)
        from medical_normalizer.models import NormalizedRegimen as R
        from medical_normalizer.validator import Severity, Validator

        r = R(dose_value=2.0, dose_min=2.0, dose_max=1.0)
        codes = {i.code for i in Validator.check_dose_positive(r)}
        assert "DOSE_RANGE_INVERTED" in codes

    def test_every_branch_sets_range_raw(self):
        for raw, expect_raw in (
            ("500", True), ("20-50", True), ("2,0-1,0", True), ("1,0", True),
        ):
            reg = DoseNormalizer.parse(NormalizedRegimen(), {"dose": raw, "unit": "мг"})
            if expect_raw:
                assert reg.dose_range_raw == raw, raw


class TestM17SlashCombinations:
    """M17: "/" separated combinations were not recognised at all."""

    def test_slash_drug_split_into_components(self):
        raw = {"antibiotic": "амоксициллин/клавулановая кислота",
               "dose": "875/125", "unit": "мг"}
        reg = DrugParser.parse(NormalizedRegimen(), raw)
        assert len(reg.drug_components) == 2

    def test_slash_components_get_doses(self):
        reg = DrugParser.parse(
            NormalizedRegimen(),
            {"antibiotic": "амоксициллин/клавулановая кислота",
             "dose": "875/125", "unit": "мг"},
        )
        assert reg.drug_components[0].dose_value == 875.0
        assert reg.drug_components[1].dose_value == 125.0

    def test_plus_still_works(self):
        reg = DrugParser.parse(
            NormalizedRegimen(),
            {"antibiotic": "Амоксициллин+клавулановая кислота",
             "dose": "875/125", "unit": "мг"},
        )
        assert len(reg.drug_components) == 2

    def test_three_way_slash_combination(self):
        reg = DrugParser.parse(
            NormalizedRegimen(),
            {"antibiotic": "a/b/c", "dose": "1/2/3", "unit": "мг"},
        )
        assert len(reg.drug_components) == 3
        assert [c.dose_value for c in reg.drug_components] == [1.0, 2.0, 3.0]


class TestL1AtcLookup:
    """L1: DRUG_ATC was loaded and never used, so the atc_code docstring was
    a dead claim."""

    def test_atc_stays_none_when_unmapped(self):
        reg = DrugParser.parse(NormalizedRegimen(), {"antibiotic": "Цефтриаксон"})
        assert reg.atc_code is None

    def test_atc_populated_from_dictionary(self, monkeypatch):
        import medical_normalizer.drug_parser as dp

        monkeypatch.setitem(dp.DRUG_ATC, "цефтриаксон", "J01DD04")
        reg = DrugParser.parse(NormalizedRegimen(), {"antibiotic": "Цефтриаксон"})
        assert reg.atc_code == "J01DD04"

    def test_atc_lookup_case_insensitive(self, monkeypatch):
        import medical_normalizer.drug_parser as dp

        monkeypatch.setitem(dp.DRUG_ATC, "амоксициллин", "J01CA04")
        reg = DrugParser.parse(NormalizedRegimen(), {"antibiotic": "Амоксициллин"})
        assert reg.atc_code == "J01CA04"

    def test_atc_none_for_empty_drug(self):
        assert DrugParser._lookup_atc("") is None
