"""RouteParser — normalize administration route."""

from medical_normalizer.dictionary import RouteNormalizer
from medical_normalizer.models import MISSING_FIELD_INPUT, NormalizedRegimen


class RouteParser:
    """Normalize route string to controlled vocabulary."""

    @classmethod
    def parse(cls, regimen: NormalizedRegimen, raw: dict) -> NormalizedRegimen:
        route_value = raw.get("route") if isinstance(raw, dict) else None
        # H2: a non-string route (int / list / dict) used to raise
        # AttributeError from .strip(). It is now recorded as a ParserError
        # (via the MISSING_FIELD_INPUT marker) and the pipeline continues.
        # An absent / null route stays "unknown" — a modelled state.
        if route_value is not None and not isinstance(route_value, str):
            regimen.route = "unknown"
            if not regimen.warnings:
                regimen.warnings = []
            marker = f"{MISSING_FIELD_INPUT}:route"
            if marker not in regimen.warnings:
                regimen.warnings.append(marker)
            return regimen

        regimen.route = RouteNormalizer.normalize(
            route_value.strip() if route_value else ""
        )
        return regimen


        regimen.route = RouteNormalizer.normalize(route_value.strip())
        return regimen
