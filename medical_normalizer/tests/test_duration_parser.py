"""Tests for duration_parser.py."""

from medical_normalizer.duration_parser import DurationParser
from medical_normalizer.models import NormalizedRegimen


class TestDurationParser:
    def test_10_days(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "10 дней"})
        assert reg.duration_days_min == 10.0
        assert reg.duration_days_max == 10.0
        assert reg.duration_days_recommended == 10.0

    def test_7_days(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "7 дней"})
        assert reg.duration_days_min == 7.0

    def test_14_days(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "14 суток"})
        assert reg.duration_days_min == 14.0

    def test_5_days(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "5 дней"})
        assert reg.duration_days_min == 5.0

    def test_10_14_range(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "10-14 дней"})
        assert reg.duration_days_min == 10.0
        assert reg.duration_days_max == 14.0

    def test_7_10_range(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "7–10 дней"})
        assert reg.duration_days_min == 7.0
        assert reg.duration_days_max == 10.0

    def test_weeks(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "2 недели"})
        assert reg.duration_days_min == 14.0

    def test_1_week(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "1 неделя"})
        assert reg.duration_days_min == 7.0

    def test_english_days(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "10 days"})
        assert reg.duration_days_min == 10.0

    def test_english_range(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "10-14 days"})
        assert reg.duration_days_min == 10.0
        assert reg.duration_days_max == 14.0

    def test_empty(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": ""})
        assert reg.duration_days_min is None

    def test_none(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": None})
        assert reg.duration_days_min is None

    def test_no_key(self):
        reg = DurationParser.parse(NormalizedRegimen(), {})
        assert reg.duration_days_min is None

    def test_prolonged_no_value(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "длительно"})
        assert reg.duration_days_min is None

    def test_3_days(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "3 дня"})
        assert reg.duration_days_min == 3.0

    def test_month(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "1 месяц"})
        assert reg.duration_days_min == 30.0

    def test_14_day(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "14 day"})
        assert reg.duration_days_min == 14.0

    def test_unicode_dash(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "5–7 дней"})
        assert reg.duration_days_min == 5.0
        assert reg.duration_days_max == 7.0

    def test_gibberish(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "по показаниям"})
        assert reg.duration_days_min is None

    # ── Single-dose markers (real failing data, high count) ──────

    def test_odnokratno(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "однократно"})
        assert reg.duration_days_min == 1.0
        assert reg.duration_days_max == 1.0

    def test_odnokratnaya_doza(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "однократная доза"})
        assert reg.duration_days_min == 1.0

    def test_odna_doza(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "одна доза"})
        assert reg.duration_days_min == 1.0

    def test_odna_predoperacionnaya_doza(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "одна предоперационная доза"})
        assert reg.duration_days_min == 1.0

    def test_razovaya_doza(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "разовая доза"})
        assert reg.duration_days_min == 1.0

    def test_predoperacionno_razovaya(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "предоперационно; разовая доза"})
        assert reg.duration_days_min == 1.0

    def test_v_bolshinstve_sluchaev_odna_doza(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "в большинстве случаев одна предоперационная доза"})
        assert reg.duration_days_min == 1.0

    # ── Hours → days (real failing data) ─────────────────────────

    def test_ne_bolee_72_chasov(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "не более 72 часов после закрытия раны"})
        assert reg.duration_days_max == 3.0

    def test_ne_bolee_24_chasov(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "не более 24 часов"})
        assert reg.duration_days_max == 1.0

    def test_v_techenie_24_chasov(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "в течение 24 часов"})
        assert reg.duration_days_min == 1.0

    def test_72_chasa(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "72 часа после травмы"})
        assert reg.duration_days_min == 3.0

    def test_24_chasa_alone(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "24 часа"})
        assert reg.duration_days_min == 1.0

    # ── Weeks bounds (real failing data) ─────────────────────────

    def test_ne_menee_2_nedel(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "не менее 2-х недель"})
        assert reg.duration_days_min == 14.0

    def test_do_2_nedel(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "до 2-х недель"})
        assert reg.duration_days_max == 14.0

    # ── Years (real failing data) ────────────────────────────────

    def test_2_3_let(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "2 - 3 лет"})
        assert reg.duration_days_min == 730.0
        assert reg.duration_days_max == 1095.0

    # ── Explicit skip (None) ─────────────────────────────────────

    def test_ne_ukazano(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "не указано"})
        assert reg.duration_days_min is None

    def test_ne_ukazana(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "не указана"})
        assert reg.duration_days_min is None

    def test_na_ves_period(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "на весь период агранулоцитоза"})
        assert reg.duration_days_min is None

    def test_do_okonchaniya(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "до окончания родов"})
        assert reg.duration_days_min is None


# ── Regression tests: M14, H2 ──────────────────────────────────────


class TestM14YearsAndDashed:
    """M14: "2 года"/"1 год" were missed, the dash blocked "5-дневный
    курс", and a ceiling was published as a recommendation."""

    def test_two_goda(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "2 года"})
        assert reg.duration_days_min == 730.0
        assert reg.duration_days_max == 730.0

    def test_one_god(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "1 год"})
        assert reg.duration_days_min == 365.0

    def test_tri_goda(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "3 года"})
        assert reg.duration_days_min == 1095.0

    def test_five_day_course(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "5-дневный курс"})
        assert reg.duration_days_min == 5.0
        assert reg.duration_days_max == 5.0

    def test_ten_day_course(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "10-дневный курс"})
        assert reg.duration_days_min == 10.0

    def test_dashed_days(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "7-дневный"})
        assert reg.duration_days_min == 7.0

    def test_max_hours_has_no_recommendation(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "не более 72 часов"})
        assert reg.duration_days_max == 3.0
        assert reg.duration_days_recommended is None

    def test_max_weeks_has_no_recommendation(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "до 2-х недель"})
        assert reg.duration_days_max == 14.0
        assert reg.duration_days_recommended is None

    def test_single_value_still_sets_recommendation(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "10 дней"})
        assert reg.duration_days_recommended == 10.0

    def test_range_still_has_no_recommendation(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "7-10 дней"})
        assert reg.duration_days_recommended is None

    def test_min_weeks_keeps_recommendation(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": "не менее 2-х недель"})
        assert reg.duration_days_min == 14.0
        assert reg.duration_days_recommended == 14.0


class TestH2NonStringInputs:
    def test_int_duration_does_not_raise(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": 7})
        assert reg.duration_days_min is None

    def test_int_duration_is_recorded(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": 7})
        assert any(w.startswith("MISSING_FIELD_INPUT:duration") for w in reg.warnings)

    def test_list_duration_does_not_raise(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": ["7 дней"]})
        assert reg.duration_days_min is None

    def test_dict_duration_does_not_raise(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": {"days": 7}})
        assert reg.duration_days_min is None

    def test_float_duration_does_not_raise(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": 7.5})
        assert reg.duration_days_min is None

    def test_none_duration_is_not_an_error(self):
        reg = DurationParser.parse(NormalizedRegimen(), {"duration": None})
        assert reg.duration_days_min is None
        assert reg.warnings == []

    def test_absent_duration_is_not_an_error(self):
        reg = DurationParser.parse(NormalizedRegimen(), {})
        assert reg.duration_days_min is None
        assert reg.warnings == []

    def test_marker_reaches_parser_error(self):
        from medical_normalizer.models import MISSING_FIELD_INPUT
        from medical_normalizer.normalizer import MedicalNormalizer

        r = MedicalNormalizer.normalize({
            "antibiotic": "Цефтриаксон", "dose": "1,0", "unit": "г",
            "route": "в/в", "frequency": "1 раз в день", "duration": 7,
        })
        assert MISSING_FIELD_INPUT in {e.error_type for e in r.errors}
        assert "duration" in r.parser_execution_order
