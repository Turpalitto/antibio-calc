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
