"""Tests for therapy_line_parser.py."""

from medical_normalizer.therapy_line_parser import TherapyLineParser
from medical_normalizer.models import NormalizedRegimen


class TestTherapyLineParser:
    def test_first_line(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": "first_line"})
        assert reg.therapy_line == "first"

    def test_alternative(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": "alternative"})
        assert reg.therapy_line == "alternative"

    def test_reserve(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": "reserve"})
        assert reg.therapy_line == "reserve"

    def test_empty(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": ""})
        assert reg.therapy_line == "unknown"

    def test_none(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": None})
        assert reg.therapy_line == "unknown"

    def test_no_key(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {})
        assert reg.therapy_line == "unknown"

    def test_russian_pervaya(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": "первая линия"})
        assert reg.therapy_line == "first"

    def test_russian_alternativa(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": "альтернативный"})
        assert reg.therapy_line == "alternative"

    def test_russian_rezerv(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": "резерв"})
        assert reg.therapy_line == "reserve"

    def test_first_line_with_dash(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": "first-line"})
        assert reg.therapy_line == "first"

    def test_firstline_concat(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": "firstline"})
        assert reg.therapy_line == "first"

    def test_russian_rezervny(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": "резервный препарат"})
        assert reg.therapy_line == "reserve"

    def test_gibberish(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": "непонятно"})
        assert reg.therapy_line == "unknown"

    def test_case_insensitive(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": "FIRST_LINE"})
        assert reg.therapy_line == "first"

    def test_russian_vtoroy_linii(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": "второй линии"})
        assert reg.therapy_line == "reserve"

    def test_whitespace(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": "  first_line  "})
        assert reg.therapy_line == "first"

    def test_pervyy_vybor(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": "первый выбор"})
        assert reg.therapy_line == "first"

    # ── New mappings from real failing data (prophylaxis 568, empiric 499) ──

    def test_prophylaxis(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": "prophylaxis"})
        assert reg.therapy_line == "prophylaxis"

    def test_empiric(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": "empiric"})
        assert reg.therapy_line == "first"

    def test_prophylaxis_case_insensitive(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": "PROPHYLAXIS"})
        assert reg.therapy_line == "prophylaxis"

    def test_empiric_case_insensitive(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": "EMPIRIC"})
        assert reg.therapy_line == "first"

    def test_russian_profilaktika(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": "профилактика"})
        assert reg.therapy_line == "prophylaxis"

    def test_russian_empiricheskiy(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": "эмпирическая"})
        assert reg.therapy_line == "first"

    def test_russian_empiricheskiy_therapy(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": "эмпирическая терапия"})
        assert reg.therapy_line == "first"
