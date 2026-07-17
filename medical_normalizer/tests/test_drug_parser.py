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
