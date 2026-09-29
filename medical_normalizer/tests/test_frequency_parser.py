"""Tests for frequency_parser.py."""

from medical_normalizer.frequency_parser import FrequencyParser
from medical_normalizer.models import NormalizedRegimen


class TestFrequencyParser:
    def test_two_times_day(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "2 раза в день"})
        assert reg.frequency_per_day == 2.0

    def test_three_times_day(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "3 раза в день"})
        assert reg.frequency_per_day == 3.0

    def test_once_day(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "1 раз в день"})
        assert reg.frequency_per_day == 1.0

    def test_every_8_hours(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "каждые 8 часов"})
        assert reg.frequency_per_day == 3.0

    def test_every_12_hours(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "каждые 12 часов"})
        assert reg.frequency_per_day == 2.0

    def test_every_6_hours(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "каждые 6 часов"})
        assert reg.frequency_per_day == 4.0

    def test_every_4_hours(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "каждые 4 часа"})
        assert reg.frequency_per_day == 6.0

    def test_every_24_hours(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "каждые 24 часа"})
        assert reg.frequency_per_day == 1.0

    def test_twice_daily(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "2 раза в сутки"})
        assert reg.frequency_per_day == 2.0

    def test_every_other_day(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "через день"})
        assert reg.frequency_per_day == 0.5

    def test_continuous(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "непрерывно"})
        assert reg.frequency_per_day == 24.0

    def test_empty(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": ""})
        assert reg.frequency_per_day is None

    def test_none(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": None})
        assert reg.frequency_per_day is None

    def test_no_key(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {})
        assert reg.frequency_per_day is None

    def test_q8h(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "q8h"})
        assert reg.frequency_per_day == 3.0

    def test_bid(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "bid"})
        assert reg.frequency_per_day == 2.0

    def test_tid(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "tid"})
        assert reg.frequency_per_day == 3.0

    def test_qd(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "qd"})
        assert reg.frequency_per_day == 1.0

    def test_russian_every_8h(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "каждые 8 ч"})
        assert reg.frequency_per_day == 3.0

    def test_three_times_sutki(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "3 раза в сутки"})
        assert reg.frequency_per_day == 3.0

    def test_four_times_day(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "4 раза в день"})
        assert reg.frequency_per_day == 4.0

    def test_dayly(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "ежедневно"})
        assert reg.frequency_per_day == 1.0

    def test_gibberish(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "по схеме"})
        assert reg.frequency_per_day is None

    def test_once(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "однократно"})
        assert reg.frequency_per_day == 1.0

    # ── Word-number frequencies (real failing data) ──────────────

    def test_word_odin_raz_v_sutki(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "один раз в сутки"})
        assert reg.frequency_per_day == 1.0

    def test_word_odin_raz_v_den(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "один раз в день"})
        assert reg.frequency_per_day == 1.0

    def test_word_odin_raz_v_nedelyu(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "1 раз в неделю"})
        assert reg.frequency_per_day == 1.0 / 7.0

    def test_word_odin_raz_v_mesyac(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "1 раз в месяц"})
        assert reg.frequency_per_day == 1.0 / 30.0

    def test_word_dva_raza_v_den(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "два раза в день"})
        assert reg.frequency_per_day == 2.0

    def test_word_dvazhdy_v_den(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "дважды в день"})
        assert reg.frequency_per_day == 2.0

    def test_word_trizhdy_v_nedelyu(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "трижды в неделю"})
        assert reg.frequency_per_day == 3.0 / 7.0

    def test_word_trizhdy_v_den(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "трижды в день"})
        assert reg.frequency_per_day == 3.0

    # ── Slash abbreviated forms (real failing data) ──────────────

    def test_2_raza_slash_sut(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "2 раза/сут"})
        assert reg.frequency_per_day == 2.0

    def test_2_r_slash_sut(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "2 р/сут"})
        assert reg.frequency_per_day == 2.0

    def test_1_raz_slash_sut(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "1 раз/сут"})
        assert reg.frequency_per_day == 1.0

    def test_2_r_slash_sutki(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "2 р/сутки"})
        assert reg.frequency_per_day == 2.0

    def test_2r_no_space_v_sut(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "2р в сут"})
        assert reg.frequency_per_day == 2.0

    def test_range_endash_r_slash_sut(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "2–3 р/сут"})
        assert reg.frequency_per_day == 2.0

    # ── "в/на/за N приема/введения" (doses) ───────────────────────

    def test_v_2_priema(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "в 2 приема"})
        assert reg.frequency_per_day == 2.0

    def test_v_2_3_priema(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "в 2-3 приема"})
        assert reg.frequency_per_day == 2.0

    def test_v_tri_priema(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "в три приема"})
        assert reg.frequency_per_day == 3.0

    def test_na_2_priema(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "на 2 приема"})
        assert reg.frequency_per_day == 2.0

    def test_v_1_2_priema(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "в 1-2 приема"})
        assert reg.frequency_per_day == 1.0

    def test_za_2_vvedeniya(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "за 2 введения"})
        assert reg.frequency_per_day == 2.0

    def test_za_2_4_vvedeniya(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "за 2-4 введения"})
        assert reg.frequency_per_day == 2.0

    def test_v_2_vvedeniya(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "в 2 введения"})
        assert reg.frequency_per_day == 2.0

    def test_v_sutki_v_2_priema(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "в сутки в 2 приема"})
        assert reg.frequency_per_day == 2.0

    def test_za_3_vvedeniya_v_sutki(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "за 3 введения в сутки"})
        assert reg.frequency_per_day == 3.0

    def test_sutochnaya_doza_razdelennaya_na_2_priema(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "суточная доза разделенная на 2 приема"})
        assert reg.frequency_per_day == 2.0

    def test_razdelennyh_na_4_priema(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "разделенных на 4 приема"})
        assert reg.frequency_per_day == 4.0

    def test_1_priem(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "1 прием"})
        assert reg.frequency_per_day == 1.0

    # ── Range "каждые N-M часов" ─────────────────────────────────

    def test_every_6_8_hours(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "каждые 6-8 часов"})
        assert reg.frequency_per_day == 4.0  # 24/6

    def test_every_8_12_ch(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "каждые 8-12 ч"})
        assert reg.frequency_per_day == 3.0  # 24/8

    def test_every_3_nedeli(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "каждые 3 недели"})
        assert reg.frequency_per_day == 1.0 / 21.0

    # ── "раз в N часов" (no leading 1) ───────────────────────────

    def test_raz_v_4_chasa(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "раз в 4 часа"})
        assert reg.frequency_per_day == 6.0  # 24/4

    def test_raz_v_4_6_chasov(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "раз в 4-6 часов"})
        assert reg.frequency_per_day == 6.0  # 24/4

    # ── "1 раз через N дней" ─────────────────────────────────────

    def test_1_raz_cherez_10_dney(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "1 раз через 10 дней"})
        assert reg.frequency_per_day == 1.0 / 10.0

    # ── Default "в сутки"/"в день"/"суточная доза" ────────────────

    def test_v_sutki_alone(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "в сутки"})
        assert reg.frequency_per_day == 1.0

    def test_v_den_alone(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "в день"})
        assert reg.frequency_per_day == 1.0

    def test_sutochnaya_doza_alone(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "суточная доза"})
        assert reg.frequency_per_day == 1.0

    def test_kak_mozhno_skoree(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "как можно скорее после травмы"})
        assert reg.frequency_per_day == 1.0

    def test_razovaya_doza(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "разовая доза"})
        assert reg.frequency_per_day == 1.0

    # ── "3 раза" alone (no period) ───────────────────────────────

    def test_3_raza_alone(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "3 раза"})
        assert reg.frequency_per_day == 3.0

    # ── "с интервалом в N нед" ───────────────────────────────────

    def test_s_intervalom_4_ned(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "с интервалом в 4 нед"})
        assert reg.frequency_per_day == 1.0 / 28.0

    # ── Should still be None (genuinely ambiguous) ───────────────

    def test_1_2_alone_still_none(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "1-2"})
        assert reg.frequency_per_day is None

    def test_po_sheme_still_none(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "в соответствии с инструкцией к препарату"})
        assert reg.frequency_per_day is None


# ── Regression tests: C5, H1, H2, H5 ──────────────────────────────


class TestC5RangeConsistency:
    """C5: "2-3 раза в сутки" collapsed to 3.0 (matching started at the "3"),
    while "2–3 р/сут" gave 2.0. Same text, opposite answers, and nothing
    recorded that a range had been seen."""

    def test_word_form_takes_lower_bound(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "2-3 раза в сутки"})
        assert reg.frequency_per_day == 2.0

    def test_word_form_flags_range(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "2-3 раза в сутки"})
        assert reg.frequency_is_range is True

    def test_en_dash_form_takes_lower_bound(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "2–3 р/сут"})
        assert reg.frequency_per_day == 2.0

    def test_en_dash_form_flags_range(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "2–3 р/сут"})
        assert reg.frequency_is_range is True

    def test_both_forms_agree(self):
        word = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "2-3 раза в сутки"})
        slash = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "2–3 р/сут"})
        assert word.frequency_per_day == slash.frequency_per_day
        assert word.frequency_is_range == slash.frequency_is_range

    def test_em_dash_word_form(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "2—3 раза в сутки"})
        assert reg.frequency_per_day == 2.0
        assert reg.frequency_is_range is True

    def test_word_range_v_day(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "3-4 раза в день"})
        assert reg.frequency_per_day == 3.0
        assert reg.frequency_is_range is True

    def test_word_range_slash_sut(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "2-3 раза/сут"})
        assert reg.frequency_per_day == 2.0
        assert reg.frequency_is_range is True

    def test_hours_range_flags_range(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "каждые 6-8 часов"})
        assert reg.frequency_per_day == 4.0
        assert reg.frequency_is_range is True

    def test_raz_v_hours_range_flags_range(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "раз в 4-6 часов"})
        assert reg.frequency_per_day == 6.0
        assert reg.frequency_is_range is True

    def test_doses_range_flags_range(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "в 2-3 приема"})
        assert reg.frequency_per_day == 2.0
        assert reg.frequency_is_range is True

    def test_scalar_does_not_flag_range(self):
        for text in ("2 раза в день", "1 раз в день", "каждые 8 часов", "bid", "через день"):
            reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": text})
            assert reg.frequency_is_range is False, text

    def test_default_is_range_false(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "в сутки"})
        assert reg.frequency_is_range is False

    def test_unparsed_clears_range_flag(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "по схеме"})
        assert reg.frequency_per_day is None
        assert reg.frequency_is_range is False

    def test_range_flag_survives_round_trip(self):
        from medical_normalizer.models import NormalizedRegimen as R

        reg = FrequencyParser.parse(R(), {"frequency": "2-3 раза в сутки"})
        restored = R.from_dict(reg.to_dict_with_range())
        assert restored.frequency_is_range is True
        assert restored.frequency_per_day == 2.0


class TestH1Qod:
    """H1: `(?:qd|od|s.i.d.)` matched the "od" inside "qod" and was checked
    first, so qod (every other day) was reported as once-daily."""

    def test_qod_is_half_daily(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "qod"})
        assert reg.frequency_per_day == 0.5

    def test_Qod_case_insensitive(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "QOD"})
        assert reg.frequency_per_day == 0.5

    def test_q_od_spaced(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "q od"})
        assert reg.frequency_per_day == 0.5

    def test_qd_still_once_daily(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "qd"})
        assert reg.frequency_per_day == 1.0

    def test_od_still_once_daily(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "od"})
        assert reg.frequency_per_day == 1.0

    def test_sid_still_once_daily(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "s.i.d."})
        assert reg.frequency_per_day == 1.0

    def test_bid_still_twice(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "bid"})
        assert reg.frequency_per_day == 2.0

    def test_tid_still_thrice(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "tid"})
        assert reg.frequency_per_day == 3.0

    def test_qid_still_four(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "qid"})
        assert reg.frequency_per_day == 4.0


class TestH5EveryNDays:
    """H5: the every-N-days patterns required a literal leading "1", so
    "каждые 3 дня" parsed to None and the regimen was REJECTed."""

    def test_every_three_days(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "каждые 3 дня"})
        assert reg.frequency_per_day == 1.0 / 3.0

    def test_every_two_days(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "каждые 2 дня"})
        assert reg.frequency_per_day == 0.5

    def test_every_ten_days(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "каждые 10 дней"})
        assert reg.frequency_per_day == 0.1

    def test_every_14_days(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "каждые 14 дней"})
        assert reg.frequency_per_day == 1.0 / 14.0

    def test_every_one_day(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "каждые 1 день"})
        assert reg.frequency_per_day == 1.0

    def test_every_six_sutki(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "каждые 6 суток"})
        assert reg.frequency_per_day == 1.0 / 6.0

    def test_every_three_days_not_flagged_as_range(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "каждые 3 дня"})
        assert reg.frequency_is_range is False

    def test_every_three_days_no_longer_rejects(self):
        from medical_normalizer.normalizer import MedicalNormalizer
        from medical_normalizer.validator import Verdict

        r = MedicalNormalizer.normalize({
            "antibiotic": "Цефтриаксон", "dose": "1,0", "unit": "г",
            "route": "в/в", "frequency": "каждые 3 дня", "duration": "10 дней",
            "age_group": "взрослые", "regimen_type": "first_line",
        })
        assert r.validation.verdict == Verdict.PASS

    def test_one_raz_v_arbitrary_n_days(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "1 раз в 7 дней"})
        assert reg.frequency_per_day == 1.0 / 7.0

    def test_one_raz_cherez_arbitrary_n_days(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "1 раз через 21 день"})
        assert reg.frequency_per_day == 1.0 / 21.0

    def test_weeks_pattern_still_wins_for_weeks(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": "каждые 3 недели"})
        assert reg.frequency_per_day == 1.0 / 21.0


class TestH2NonStringInputs:
    """H2: every parser raised AttributeError on int / list / dict inputs."""

    def test_int_frequency_does_not_raise(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": 3})
        assert reg.frequency_per_day is None

    def test_int_frequency_is_recorded(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": 3})
        assert any(w.startswith("MISSING_FIELD_INPUT:frequency") for w in reg.warnings)

    def test_list_frequency_does_not_raise(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": ["2 раза"]})
        assert reg.frequency_per_day is None

    def test_dict_frequency_does_not_raise(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": {"n": 2}})
        assert reg.frequency_per_day is None

    def test_none_frequency_is_not_an_error(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {"frequency": None})
        assert reg.frequency_per_day is None
        assert reg.warnings == []

    def test_absent_frequency_is_not_an_error(self):
        reg = FrequencyParser.parse(NormalizedRegimen(), {})
        assert reg.frequency_per_day is None
        assert reg.warnings == []

    def test_marker_reaches_parser_error(self):
        from medical_normalizer.models import MISSING_FIELD_INPUT
        from medical_normalizer.normalizer import MedicalNormalizer

        r = MedicalNormalizer.normalize({
            "antibiotic": "Цефтриаксон", "dose": "1,0", "unit": "г",
            "route": "в/в", "frequency": 3, "duration": "7 дней",
        })
        codes = {e.error_type for e in r.errors}
        assert MISSING_FIELD_INPUT in codes
        # the pipeline still completed
        assert "validator" in r.parser_execution_order
        assert "frequency" in r.parser_execution_order
