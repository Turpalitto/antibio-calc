"""Tests for population_parser.py — AgeParser, PregnancyParser, GFRParser."""

from medical_normalizer.population_parser import AgeParser, PregnancyParser, GFRParser
from medical_normalizer.models import NormalizedRegimen


class TestAgeParser:
    def test_adult(self):
        reg = AgeParser.parse(NormalizedRegimen(), {"age_group": "взрослые"})
        assert reg.adult is True
        assert reg.child is False

    def test_child(self):
        reg = AgeParser.parse(NormalizedRegimen(), {"age_group": "дети"})
        assert reg.adult is False
        assert reg.child is True

    def test_newborn(self):
        reg = AgeParser.parse(NormalizedRegimen(), {"age_group": "новорожденные"})
        assert reg.adult is False
        assert reg.child is True

    def test_premature(self):
        reg = AgeParser.parse(NormalizedRegimen(), {"age_group": "недоношенные"})
        assert reg.adult is False
        assert reg.child is True

    def test_elderly(self):
        reg = AgeParser.parse(NormalizedRegimen(), {"age_group": "пожилые"})
        assert reg.adult is True
        assert reg.child is False

    def test_empty(self):
        reg = AgeParser.parse(NormalizedRegimen(), {"age_group": ""})
        assert reg.adult is True
        assert reg.child is False

    def test_none(self):
        reg = AgeParser.parse(NormalizedRegimen(), {"age_group": None})
        assert reg.adult is True
        assert reg.child is False

    def test_no_key(self):
        reg = AgeParser.parse(NormalizedRegimen(), {})
        assert reg.adult is True
        assert reg.child is False

    def test_english_adult(self):
        reg = AgeParser.parse(NormalizedRegimen(), {"age_group": "adult"})
        assert reg.adult is True
        assert reg.child is False

    def test_english_child(self):
        reg = AgeParser.parse(NormalizedRegimen(), {"age_group": "children"})
        assert reg.adult is False
        assert reg.child is True

    def test_newborn_overrides_child(self):
        reg = AgeParser.parse(NormalizedRegimen(), {"age_group": "новорожденные и дети"})
        assert reg.child is True
        assert reg.adult is False

    def test_english_newborn(self):
        reg = AgeParser.parse(NormalizedRegimen(), {"age_group": "neonatal"})
        assert reg.child is True

    def test_gibberish_defaults_adult(self):
        reg = AgeParser.parse(NormalizedRegimen(), {"age_group": "непонятный текст"})
        assert reg.adult is True
        assert reg.child is False

    def test_pediatric(self):
        reg = AgeParser.parse(NormalizedRegimen(), {"age_group": "педиатрические пациенты"})
        assert reg.child is True
        assert reg.adult is False

    def test_infant(self):
        reg = AgeParser.parse(NormalizedRegimen(), {"age_group": "младенцы"})
        assert reg.child is True


class TestPregnancyParser:
    def test_pregnancy_true_from_field(self):
        reg = PregnancyParser.parse(NormalizedRegimen(), {"pregnancy": True})
        assert reg.pregnancy is True

    def test_pregnancy_false_from_field(self):
        reg = PregnancyParser.parse(NormalizedRegimen(), {"pregnancy": False})
        assert reg.pregnancy is False

    def test_pregnancy_from_age_group(self):
        reg = PregnancyParser.parse(
            NormalizedRegimen(), {"age_group": "беременные женщины"}
        )
        assert reg.pregnancy is True

    def test_pregnancy_contraindication_is_false(self):
        # M13: the "не рекоменд" branch was unreachable dead code (the
        # preceding `if` already matched "беремен"), so a CONTRAINDICATION
        # was recorded as APPLICABILITY. pregnancy=False means "explicitly
        # not for pregnancy".
        reg = PregnancyParser.parse(
            NormalizedRegimen(),
            {"source_quote": "не рекомендуется при беременности"},
        )
        assert reg.pregnancy is False

    def test_pregnancy_prohibited_is_false(self):
        reg = PregnancyParser.parse(
            NormalizedRegimen(),
            {"source_quote": "противопоказано при беременности"},
        )
        assert reg.pregnancy is False

    def test_pregnancy_not_recommended_application_is_false(self):
        reg = PregnancyParser.parse(
            NormalizedRegimen(),
            {"source_quote": "при беременности применение не рекомендовано"},
        )
        assert reg.pregnancy is False

    def test_pregnancy_applicable_is_true(self):
        reg = PregnancyParser.parse(
            NormalizedRegimen(),
            {"source_quote": "разрешено при беременности"},
        )
        assert reg.pregnancy is True

    def test_population_stated_true_for_adults(self):
        reg = AgeParser.parse(NormalizedRegimen(), {"age_group": "взрослые"})
        assert reg.population_stated is True

    def test_population_stated_false_without_evidence(self):
        reg = AgeParser.parse(NormalizedRegimen(), {"age_group": "непонятный текст"})
        assert reg.adult is True
        assert reg.population_stated is False

    def test_no_pregnancy_info(self):
        reg = PregnancyParser.parse(NormalizedRegimen(), {"age_group": "взрослые"})
        assert reg.pregnancy is None

    def test_empty(self):
        reg = PregnancyParser.parse(NormalizedRegimen(), {})
        assert reg.pregnancy is None

    def test_english_pregnancy(self):
        reg = PregnancyParser.parse(
            NormalizedRegimen(), {"source_quote": "pregnancy category B"}
        )
        assert reg.pregnancy is True

    def test_lactation_in_quote(self):
        reg = PregnancyParser.parse(
            NormalizedRegimen(),
            {"source_quote": "противопоказано при лактации"},
        )
        assert reg.pregnancy is True or reg.pregnancy is None

    def test_gestational(self):
        reg = PregnancyParser.parse(
            NormalizedRegimen(), {"age_group": "гестационный период"}
        )
        assert reg.pregnancy is True


class TestGFRParser:
    def test_renal_field_true(self):
        reg = GFRParser.parse(NormalizedRegimen(), {"renal_adjustment": True})
        assert reg.renal_adjustment is True

    def test_renal_field_false(self):
        reg = GFRParser.parse(NormalizedRegimen(), {"renal_adjustment": False})
        assert reg.renal_adjustment is False

    def test_hemodialysis_in_quote(self):
        reg = GFRParser.parse(
            NormalizedRegimen(),
            {"source_quote": "пациентам на гемодиализе требуется коррекция дозы"},
        )
        assert reg.renal_adjustment is True

    def test_peritoneal_dialysis(self):
        reg = GFRParser.parse(
            NormalizedRegimen(),
            {"source_quote": "при перитонеальном диализе"},
        )
        assert reg.renal_adjustment is True

    def test_renal_impairment_text(self):
        reg = GFRParser.parse(
            NormalizedRegimen(),
            {"source_quote": "при почечной недостаточности снизить дозу"},
        )
        assert reg.renal_adjustment is True

    def test_creatinine_clearance(self):
        reg = GFRParser.parse(
            NormalizedRegimen(),
            {"source_quote": "при клиренсе креатинина менее 30"},
        )
        assert reg.renal_adjustment is True

    def test_no_renal_info(self):
        reg = GFRParser.parse(NormalizedRegimen(), {"source_quote": "стандартная доза"})
        assert reg.renal_adjustment is False

    def test_empty(self):
        reg = GFRParser.parse(NormalizedRegimen(), {})
        assert reg.renal_adjustment is False

    def test_english_gfr(self):
        reg = GFRParser.parse(
            NormalizedRegimen(), {"source_quote": "adjust dose for GFR < 30"}
        )
        assert reg.renal_adjustment is True

    def test_english_hemodialysis(self):
        reg = GFRParser.parse(
            NormalizedRegimen(), {"source_quote": "hemodialysis patients"}
        )
        assert reg.renal_adjustment is True

    def test_english_creatinine(self):
        reg = GFRParser.parse(
            NormalizedRegimen(), {"source_quote": "CrCl below 50"}
        )
        assert reg.renal_adjustment is True


# ── Regression tests: H2 ───────────────────────────────────────────


class TestH2NonStringInputs:
    """Every population sub-parser used to raise AttributeError on
    int / list / dict inputs; now it records a MISSING_FIELD_INPUT
    ParserError and continues."""

    def test_int_age_group_does_not_raise(self):
        reg = AgeParser.parse(NormalizedRegimen(), {"age_group": 5})
        assert reg.adult is True
        assert reg.child is False

    def test_int_age_group_is_recorded(self):
        reg = AgeParser.parse(NormalizedRegimen(), {"age_group": 5})
        assert any(w.startswith("MISSING_FIELD_INPUT:age_group") for w in reg.warnings)

    def test_list_age_group_does_not_raise(self):
        reg = AgeParser.parse(NormalizedRegimen(), {"age_group": ["взрослые"]})
        assert reg.adult is True

    def test_int_source_quote_does_not_raise(self):
        reg = AgeParser.parse(NormalizedRegimen(), {"source_quote": 42})
        assert reg.adult is True

    def test_int_pregnancy_field_does_not_raise(self):
        reg = PregnancyParser.parse(NormalizedRegimen(), {"pregnancy": 1})
        assert reg.pregnancy is None

    def test_int_pregnancy_is_recorded(self):
        reg = PregnancyParser.parse(NormalizedRegimen(), {"pregnancy": 1})
        assert any(w.startswith("MISSING_FIELD_INPUT:pregnancy") for w in reg.warnings)

    def test_list_pregnancy_text_does_not_raise(self):
        reg = PregnancyParser.parse(NormalizedRegimen(), {"source_quote": ["беременные"]})
        assert reg.pregnancy is None

    def test_int_renal_field_does_not_raise(self):
        reg = GFRParser.parse(NormalizedRegimen(), {"renal_adjustment": 1})
        assert reg.renal_adjustment is False

    def test_int_renal_is_recorded(self):
        reg = GFRParser.parse(NormalizedRegimen(), {"renal_adjustment": 1})
        assert any(w.startswith("MISSING_FIELD_INPUT:renal_adjustment") for w in reg.warnings)

    def test_dict_renal_text_does_not_raise(self):
        reg = GFRParser.parse(NormalizedRegimen(), {"source_quote": {"text": "почечная"}})
        assert reg.renal_adjustment is False

    def test_all_three_markers_reach_normalizer(self):
        from medical_normalizer.models import MISSING_FIELD_INPUT
        from medical_normalizer.normalizer import MedicalNormalizer

        r = MedicalNormalizer.normalize({
            "antibiotic": "Цефтриаксон", "dose": "1,0", "unit": "г",
            "route": "в/в", "frequency": "1 раз в день",
            "age_group": 5, "pregnancy": 1, "renal_adjustment": 1,
        })
        assert MISSING_FIELD_INPUT in {e.error_type for e in r.errors}
        # the pipeline still ran every sub-parser
        assert "population.age" in r.parser_execution_order
        assert "population.pregnancy" in r.parser_execution_order
        assert "population.gfr" in r.parser_execution_order
