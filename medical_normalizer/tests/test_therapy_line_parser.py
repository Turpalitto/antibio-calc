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


# ── Regression tests: M12, H2 ─────────────────────────────────────


class TestM12FuzzyMatch:
    """M12: the fuzzy loop was a bidirectional substring test, so a 1-char
    input such as "а" matched "первая", and the FIRST key in dict insertion
    order won rather than the best match."""

    def test_single_char_does_not_match(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": "а"})
        assert reg.therapy_line == "unknown"

    def test_two_char_input_does_not_match(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": "ли"})
        assert reg.therapy_line == "unknown"

    def test_three_char_input_does_not_match(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": "пер"})
        assert reg.therapy_line == "unknown"

    def test_min_length_constant(self):
        assert TherapyLineParser.MIN_FUZZY_LENGTH == 4

    def test_vtoraya_liniya(self):
        # "вторая линия" previously fell through to "unknown"
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": "вторая линия"})
        assert reg.therapy_line == "reserve"

    def test_pervaya_liniya(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": "первая линия"})
        assert reg.therapy_line == "first"

    def test_vtoraya_liniya_uppercase(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": "ВТОРАЯ ЛИНИЯ"})
        assert reg.therapy_line == "reserve"

    def test_alternativnaya_feminine(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": "альтернативная"})
        assert reg.therapy_line == "alternative"

    def test_longest_match_wins(self):
        # "препарат первой линии" (len 21) must beat "первая" (len 6);
        # both map to "first", so use a discriminating pair instead:
        # "препарат резерва" -> reserve must not be captured by an earlier
        # shorter "first" key.
        reg = TherapyLineParser.parse(
            NormalizedRegimen(), {"regimen_type": "препарат резерва"}
        )
        assert reg.therapy_line == "reserve"

    def test_profilaktika_therapy_sentence(self):
        reg = TherapyLineParser.parse(
            NormalizedRegimen(), {"regimen_type": "профилактика терапии"}
        )
        assert reg.therapy_line == "prophylaxis"

    def test_embedded_key_still_matches(self):
        reg = TherapyLineParser.parse(
            NormalizedRegimen(), {"regimen_type": "эмпирическая терапия тяжелой пневмонии"}
        )
        assert reg.therapy_line == "first"

    def test_longest_first_ordering_is_enforced(self):
        # The registry is pre-sorted longest-key-first, which is what makes the
        # match "best" rather than "first in dict insertion order".
        lengths = [len(k) for k, _ in TherapyLineParser._MAPPING_LONGEST_FIRST]
        assert lengths == sorted(lengths, reverse=True)
        assert lengths[0] == max(len(k) for k in TherapyLineParser._MAPPING)

    def test_gibberish_still_unknown(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": "непонятно"})
        assert reg.therapy_line == "unknown"

    def test_direct_mapping_still_wins_over_fuzzy(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": "reserve"})
        assert reg.therapy_line == "reserve"


class TestH2NonStringInputs:
    def test_int_regimen_type_does_not_raise(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": 5})
        assert reg.therapy_line == "unknown"

    def test_int_regimen_type_is_recorded(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": 5})
        assert any(w.startswith("MISSING_FIELD_INPUT:regimen_type") for w in reg.warnings)

    def test_list_regimen_type_does_not_raise(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": ["first_line"]})
        assert reg.therapy_line == "unknown"

    def test_dict_regimen_type_does_not_raise(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": {"line": 1}})
        assert reg.therapy_line == "unknown"

    def test_null_regimen_type_is_not_an_error(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {"regimen_type": None})
        assert reg.therapy_line == "unknown"
        assert reg.warnings == []

    def test_absent_regimen_type_is_not_an_error(self):
        reg = TherapyLineParser.parse(NormalizedRegimen(), {})
        assert reg.therapy_line == "unknown"
        assert reg.warnings == []
