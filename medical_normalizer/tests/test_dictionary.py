"""Tests for dictionary.py — drug/route/unit normalization."""

from medical_normalizer.dictionary import (
    DrugNormalizer,
    RouteNormalizer,
    UnitNormalizer,
)


class TestDrugNormalizer:
    def test_direct_name(self):
        assert DrugNormalizer.normalize("Амоксициллин") == "Амоксициллин"

    def test_brand_to_generic(self):
        assert DrugNormalizer.normalize("Сумамед") == "Азитромицин"

    def test_brand_synonym(self):
        assert DrugNormalizer.normalize("Амоксиклав") == "Амоксициллин + клавулановая кислота"

    def test_english_generic(self):
        assert DrugNormalizer.normalize("amoxicillin") == "Амоксициллин"

    def test_english_brand(self):
        assert DrugNormalizer.normalize("Augmentin") == "Амоксициллин + клавулановая кислота"

    def test_strip_marker_suffix(self):
        assert DrugNormalizer.normalize("Амоксициллин**") == "Амоксициллин"

    def test_strip_hash_prefix(self):
        assert DrugNormalizer.normalize("#Цефтриаксон**") == "Цефтриаксон"

    def test_clean_multiple_markers(self):
        assert DrugNormalizer.normalize("#Амоксициллин+клавулановая кислота**") == "Амоксициллин + клавулановая кислота"

    def test_empty_input(self):
        assert DrugNormalizer.normalize("") == ""

    def test_none_input(self):
        assert DrugNormalizer.normalize(None) == ""

    def test_unknown_drug_preserved(self):
        assert DrugNormalizer.normalize("Новый препарат") == "Новый препарат"

    def test_known_synonym_with_marker(self):
        assert DrugNormalizer.normalize("Амоксиклав**") == "Амоксициллин + клавулановая кислота"

    def test_case_insensitive(self):
        assert DrugNormalizer.normalize("амоксициллин") == "Амоксициллин"


class TestRouteNormalizer:
    def test_oral(self):
        assert RouteNormalizer.normalize("внутрь") == "oral"

    def test_per_os(self):
        assert RouteNormalizer.normalize("per os") == "oral"

    def test_iv(self):
        assert RouteNormalizer.normalize("в/в") == "iv"

    def test_iv_full(self):
        assert RouteNormalizer.normalize("внутривенно") == "iv"

    def test_im(self):
        assert RouteNormalizer.normalize("в/м") == "im"

    def test_im_full(self):
        assert RouteNormalizer.normalize("внутримышечно") == "im"

    def test_topical(self):
        assert RouteNormalizer.normalize("местно") == "topical"

    def test_inhalation(self):
        assert RouteNormalizer.normalize("ингаляционно") == "inhalation"

    def test_ophthalmic(self):
        assert RouteNormalizer.normalize("глазные капли") == "ophthalmic"

    def test_compound_iv_or_im(self):
        result = RouteNormalizer.normalize("в/в или в/м")
        parts = result.split("|")
        assert "iv" in parts
        assert "im" in parts

    def test_compound_iv_im(self):
        result = RouteNormalizer.normalize("в/в, в/м")
        parts = result.split("|")
        assert "iv" in parts
        assert "im" in parts

    def test_compound_slash_not_separator(self):
        # Slash is part of abbreviation (в/в, в/м), not separator
        assert RouteNormalizer.normalize("в/в/м") == "unknown"

    def test_empty_input(self):
        assert RouteNormalizer.normalize("") == "unknown"

    def test_none_input(self):
        assert RouteNormalizer.normalize(None) == "unknown"

    def test_unknown_route(self):
        assert RouteNormalizer.normalize("чрескожно") == "unknown"

    def test_iv_english(self):
        assert RouteNormalizer.normalize("IV") == "iv"

    def test_oral_russian_short(self):
        assert RouteNormalizer.normalize("внутр") == "oral"

    def test_compound_no_duplicates(self):
        result = RouteNormalizer.normalize("в/в или внутривенно")
        assert result.count("iv") == 1


class TestUnitNormalizer:
    def test_mg(self):
        assert UnitNormalizer.normalize("мг") == "mg"

    def test_gram(self):
        assert UnitNormalizer.normalize("г") == "g"

    def test_mcg(self):
        assert UnitNormalizer.normalize("мкг") == "mcg"

    def test_ml(self):
        assert UnitNormalizer.normalize("мл") == "ml"

    def test_iu(self):
        assert UnitNormalizer.normalize("ед") == "IU"

    def test_english_mg(self):
        assert UnitNormalizer.normalize("mg") == "mg"

    def test_empty(self):
        assert UnitNormalizer.normalize("") == ""

    def test_none(self):
        assert UnitNormalizer.normalize(None) == ""

    def test_convert_g_to_mg(self):
        assert UnitNormalizer.convert_to_mg(2.0, "г") == 2000.0

    def test_convert_mg_to_mg(self):
        assert UnitNormalizer.convert_to_mg(500.0, "мг") == 500.0

    def test_convert_mcg_to_mg(self):
        assert UnitNormalizer.convert_to_mg(500.0, "мкг") == 0.5

    def test_convert_ml_no_conversion(self):
        assert UnitNormalizer.convert_to_mg(10.0, "мл") == 10.0
