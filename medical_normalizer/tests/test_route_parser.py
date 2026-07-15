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
