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

    def test_pregnancy_from_quote(self):
        reg = PregnancyParser.parse(
            NormalizedRegimen(),
            {"source_quote": "не рекомендуется при беременности"},
        )
        assert reg.pregnancy is True

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
