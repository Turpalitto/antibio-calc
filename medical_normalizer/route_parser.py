"""RouteParser — normalize administration route."""

from medical_normalizer.dictionary import RouteNormalizer
from medical_normalizer.models import NormalizedRegimen


class RouteParser:
    """Normalize route string to controlled vocabulary."""

    @classmethod
    def parse(cls, regimen: NormalizedRegimen, raw: dict) -> NormalizedRegimen:
        route_raw = (raw.get("route", "") or "").strip()
        regimen.route = RouteNormalizer.normalize(route_raw)
        return regimen
