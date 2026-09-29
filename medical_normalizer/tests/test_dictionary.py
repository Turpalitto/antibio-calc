"""Tests for dictionary.py — drug/route/unit normalization."""

from medical_normalizer.dictionary import (
    ROUTE_SYNONYMS as ROUTE_SYNONYMS_LOOKUP,
)
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

    def test_convert_ml_refuses(self):
        # L4: ml is a VOLUME. Returning it as-is conflated volume with mass
        # and could silently compare a 10 ml ampoule against a 10 mg limit.
        import pytest

        with pytest.raises(ValueError):
            UnitNormalizer.convert_to_mg(10.0, "мл")

    def test_convert_iu_refuses(self):
        import pytest

        with pytest.raises(ValueError):
            UnitNormalizer.convert_to_mg(500000.0, "ед")

    def test_convert_thousand_iu_refuses(self):
        import pytest

        with pytest.raises(ValueError):
            UnitNormalizer.convert_to_mg(2.0, "тыс ед")

    def test_convert_mg_per_kg_refuses(self):
        import pytest

        with pytest.raises(ValueError):
            UnitNormalizer.convert_to_mg(15.0, "мг/кг")

    def test_convert_unknown_unit_refuses(self):
        import pytest

        with pytest.raises(ValueError):
            UnitNormalizer.convert_to_mg(1.0, "блар")

    def test_is_mass_unit(self):
        assert UnitNormalizer.is_mass_unit("мг") is True
        assert UnitNormalizer.is_mass_unit("г") is True
        assert UnitNormalizer.is_mass_unit("мл") is False
        assert UnitNormalizer.is_mass_unit("ед") is False
        assert UnitNormalizer.is_mass_unit("мг/кг") is False

    def test_unmapped_unit_is_returned_cleaned_lowercase(self):
        # L5: the ORIGINAL casing used to survive a miss, so an unmapped
        # "МГ/М2" reached the validator as "МГ/М2" and could never match the
        # lowercase controlled vocabulary -> spurious DOSE_UNIT_UNKNOWN.
        assert UnitNormalizer.normalize("МГ/М2") == "мг/м2"

    def test_unmapped_unit_trailing_period_stripped(self):
        # L5: cleaned value (lowercased, trailing period removed), not the raw
        assert UnitNormalizer.normalize("МЛГ.") == "млг"

    def test_mapped_unit_uppercase_still_maps(self):
        # L5 must not regress the normal path
        assert UnitNormalizer.normalize("МГ/КГ") == "mg/kg"
        assert UnitNormalizer.normalize("МГ.") == "mg"

    def test_slash_route_sequence(self):
        # M16: "в/в/в/м" was unreachable because the compound splitter only
        # split on "," / " или ", leaving the "/" -> "|" dictionary entry dead.
        result = RouteNormalizer.normalize("в/в/в/м")
        assert result.split("|") == ["iv", "im"]

    def test_slash_route_sequence_english(self):
        result = RouteNormalizer.normalize("intravenously/intramuscularly")
        assert result.split("|") == ["iv", "im"]

    def test_slash_route_sequence_single_is_unknown(self):
        # a lone alias must go through exact lookup, never the sequence splitter
        assert RouteNormalizer.normalize("внутривенно/") == "unknown"


# ── Regression tests: L2, L3 ──────────────────────────────────────


class TestL2L3DeadCodeRemoved:
    """L2: the "case-insensitive fallback" loop had a condition identical to
    the lookup above it and could never fire. L3: _strip_paren_re was defined
    and never used."""

    def test_case_insensitive_fallback_loop_removed(self):
        assert "for alias, canonical in DRUG_SYNONYMS.items()" not in (
            __import__("inspect").getsource(DrugNormalizer.normalize)
        )

    def test_unused_paren_regex_removed(self):
        assert not hasattr(DrugNormalizer, "_strip_paren_re")

    def test_strip_marker_regex_kept(self):
        assert hasattr(DrugNormalizer, "_strip_marker_re")

    def test_direct_lookup_still_works(self):
        assert DrugNormalizer.normalize("Амоксициллин") == "Амоксициллин"

    def test_lowercase_lookup_still_works(self):
        assert DrugNormalizer.normalize("амоксициллин") == "Амоксициллин"

    def test_miss_returns_cleaned_value(self):
        assert DrugNormalizer.normalize("#Новый препарат**") == "Новый препарат"

    def test_no_o_n_fallback_performance(self):
        # The old loop was O(len(DRUG_SYNONYMS)) per miss; a miss is now a
        # single dict lookup.
        import time

        from medical_normalizer.dictionary import DRUG_SYNONYMS

        raw = "Совершенно Неизвестный Препарат"
        start = time.perf_counter()
        for _ in range(2000):
            DrugNormalizer.normalize(raw)
        elapsed = time.perf_counter() - start
        assert elapsed < 0.5
        assert len(DRUG_SYNONYMS) > 50


class TestRouteNormalizerDataDriven:
    def test_route_aliases_exclude_separator_entries(self):
        from medical_normalizer.dictionary import RouteNormalizer

        for alias in RouteNormalizer._route_aliases:
            assert "|" not in str(ROUTE_SYNONYMS_LOOKUP.get(alias, ""))

    def test_separator_entries_not_tokenized(self):
        from medical_normalizer.dictionary import ROUTE_SYNONYMS, RouteNormalizer

        for sep in ("или", ",", "/"):
            assert sep not in RouteNormalizer._route_aliases
        assert ROUTE_SYNONYMS["/"] == "|"
