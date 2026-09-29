"""Tests for route_parser.py."""

from medical_normalizer.route_parser import RouteParser
from medical_normalizer.models import NormalizedRegimen


class TestRouteParser:
    def test_oral(self):
        reg = RouteParser.parse(NormalizedRegimen(), {"route": "внутрь"})
        assert reg.route == "oral"

    def test_iv(self):
        reg = RouteParser.parse(NormalizedRegimen(), {"route": "в/в"})
        assert reg.route == "iv"

    def test_im(self):
        reg = RouteParser.parse(NormalizedRegimen(), {"route": "в/м"})
        assert reg.route == "im"

    def test_iv_or_im(self):
        reg = RouteParser.parse(NormalizedRegimen(), {"route": "в/в или в/м"})
        parts = reg.route.split("|")
        assert "iv" in parts
        assert "im" in parts

    def test_topical(self):
        reg = RouteParser.parse(NormalizedRegimen(), {"route": "местно"})
        assert reg.route == "topical"

    def test_inhalation(self):
        reg = RouteParser.parse(NormalizedRegimen(), {"route": "ингаляционно"})
        assert reg.route == "inhalation"

    def test_ophthalmic(self):
        reg = RouteParser.parse(NormalizedRegimen(), {"route": "глазные капли"})
        assert reg.route == "ophthalmic"

    def test_empty(self):
        reg = RouteParser.parse(NormalizedRegimen(), {"route": ""})
        assert reg.route == "unknown"

    def test_none(self):
        reg = RouteParser.parse(NormalizedRegimen(), {"route": None})
        assert reg.route == "unknown"

    def test_no_route_key(self):
        reg = RouteParser.parse(NormalizedRegimen(), {})
        assert reg.route == "unknown"

    def test_iv_full(self):
        reg = RouteParser.parse(NormalizedRegimen(), {"route": "внутривенно"})
        assert reg.route == "iv"

    def test_im_full(self):
        reg = RouteParser.parse(NormalizedRegimen(), {"route": "внутримышечно"})
        assert reg.route == "im"

    def test_per_os(self):
        reg = RouteParser.parse(NormalizedRegimen(), {"route": "per os"})
        assert reg.route == "oral"

    def test_iv_comma_im(self):
        reg = RouteParser.parse(NormalizedRegimen(), {"route": "в/в, в/м"})
        parts = reg.route.split("|")
        assert "iv" in parts
        assert "im" in parts


# ── Regression tests: M16, H2 ─────────────────────────────────────


class TestM16SlashRoutes:
    """M16: the "/" -> "|" entry in route_dictionary.json was unreachable
    because the compound splitter only handled "," and " или "."""

    def test_double_slash_sequence(self):
        reg = RouteParser.parse(NormalizedRegimen(), {"route": "в/в/в/м"})
        assert reg.route == "iv|im"

    def test_triple_slash_sequence_order_preserved(self):
        reg = RouteParser.parse(NormalizedRegimen(), {"route": "в/м/в/в"})
        assert reg.route == "im|iv"

    def test_slash_sequence_deduplicates(self):
        reg = RouteParser.parse(NormalizedRegimen(), {"route": "в/в/в/в"})
        assert reg.route == "iv"

    def test_single_slash_abbreviation_unchanged(self):
        reg = RouteParser.parse(NormalizedRegimen(), {"route": "в/в"})
        assert reg.route == "iv"

    def test_comma_still_wins(self):
        reg = RouteParser.parse(NormalizedRegimen(), {"route": "в/в, в/м"})
        assert reg.route == "iv|im"

    def test_ili_still_wins(self):
        reg = RouteParser.parse(NormalizedRegimen(), {"route": "в/в или в/м"})
        assert reg.route == "iv|im"

    def test_unknown_slash_sequence_still_unknown(self):
        reg = RouteParser.parse(NormalizedRegimen(), {"route": "внутрь/чрескожно"})
        assert reg.route == "unknown"

    def test_garbage_slash_sequence_unknown(self):
        reg = RouteParser.parse(NormalizedRegimen(), {"route": "а/б/в"})
        assert reg.route == "unknown"


class TestH2NonStringInputs:
    def test_int_route_does_not_raise(self):
        reg = RouteParser.parse(NormalizedRegimen(), {"route": 5})
        assert reg.route == "unknown"

    def test_int_route_is_recorded(self):
        reg = RouteParser.parse(NormalizedRegimen(), {"route": 5})
        assert any(w.startswith("MISSING_FIELD_INPUT:route") for w in reg.warnings)

    def test_list_route_does_not_raise(self):
        reg = RouteParser.parse(NormalizedRegimen(), {"route": ["в/в"]})
        assert reg.route == "unknown"

    def test_dict_route_does_not_raise(self):
        reg = RouteParser.parse(NormalizedRegimen(), {"route": {"code": "iv"}})
        assert reg.route == "unknown"

    def test_null_route_is_not_an_error(self):
        reg = RouteParser.parse(NormalizedRegimen(), {"route": None})
        assert reg.route == "unknown"
        assert reg.warnings == []

    def test_absent_route_is_not_an_error(self):
        reg = RouteParser.parse(NormalizedRegimen(), {})
        assert reg.route == "unknown"
        assert reg.warnings == []

    def test_marker_reaches_parser_error(self):
        from medical_normalizer.models import MISSING_FIELD_INPUT
        from medical_normalizer.normalizer import MedicalNormalizer

        r = MedicalNormalizer.normalize({
            "antibiotic": "Цефтриаксон", "dose": "1,0", "unit": "г",
            "route": 5, "frequency": "1 раз в день", "duration": "7 дней",
        })
        assert MISSING_FIELD_INPUT in {e.error_type for e in r.errors}
        assert "route" in r.parser_execution_order
