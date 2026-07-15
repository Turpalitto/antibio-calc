"""Phase 4 — Dose expression parser.

assembled_regimens.sqlite already splits the numeric dose out into a `dose`
column, so this module does not re-parse free text numbers. Its job is to
interpret the `unit` string into structured fields (numerator unit, whether it
is weight-scaled, and whether the source specifies per-dose or per-day) and to
detect units that cannot be safely interpreted.

Never infers a denominator_time that is not explicitly present in the unit
string. "mg/kg" alone is left ambiguous (denominator_time=None) on purpose —
downstream calculation must BLOCK rather than guess.
"""
from __future__ import annotations

from .models import DoseExpression, PARSED, UNPARSED

# Units that convert cleanly to mg (numerator side)
_MG_EQUIVALENT = {
    "mg": 1.0,
    "g": 1000.0,
    "мг": 1.0,
    "г": 1000.0,
}

_NON_MASS_ATOMIC = {"iu", "ml", "мл"}  # kept in their own unit, no mg conversion
_UNPARSEABLE_TOKENS = {"", "%", "капли", "капель", "капля"}


def parse_unit(raw_unit: str) -> tuple[bool, bool]:
    """Return (is_compound_or_unknown, has_semicolon) for a raw unit string."""
    has_semicolon = ";" in (raw_unit or "")
    return has_semicolon, has_semicolon


def parse_dose_expression(dose: float | None, unit: str | None, frequency: float | None) -> DoseExpression:
    raw_unit = (unit or "").strip()
    source_expression = f"{dose if dose is not None else ''} {raw_unit}".strip()

    if dose is None or raw_unit == "":
        return DoseExpression(
            numeric_min=dose, numeric_max=dose, numerator_unit=None,
            denominator_weight=False, denominator_time=None, per_dose_or_per_day=None,
            frequency=frequency, max_single_dose=None, max_daily_dose=None,
            source_expression=source_expression or "(empty)", parser_status=UNPARSED,
        )

    unit_lower = raw_unit.lower()

    # Compound / duplicated unit strings (e.g. "г; мг/кг", "мл/кг/сут; мл/кг/сут")
    if ";" in raw_unit:
        return DoseExpression(
            numeric_min=dose, numeric_max=dose, numerator_unit=None,
            denominator_weight=False, denominator_time=None, per_dose_or_per_day=None,
            frequency=frequency, max_single_dose=None, max_daily_dose=None,
            source_expression=source_expression, parser_status=UNPARSED,
        )

    if unit_lower in _UNPARSEABLE_TOKENS:
        return DoseExpression(
            numeric_min=dose, numeric_max=dose, numerator_unit=None,
            denominator_weight=False, denominator_time=None, per_dose_or_per_day=None,
            frequency=frequency, max_single_dose=None, max_daily_dose=None,
            source_expression=source_expression, parser_status=UNPARSED,
        )

    denominator_weight = "kg" in unit_lower or "/кг" in unit_lower
    denominator_time = None
    if "day" in unit_lower or "сут" in unit_lower or "/day" in unit_lower:
        denominator_time = "day"
    elif "dose" in unit_lower or "/доз" in unit_lower or "прием" in unit_lower:
        denominator_time = "dose"

    # Strip qualifiers to find the base numerator unit token
    base_token = unit_lower.split("/")[0].strip()

    numerator_unit: str | None
    if base_token in ("mg", "мг"):
        numerator_unit = "mg"
    elif base_token in ("g", "г"):
        numerator_unit = "mg"  # converted below by calculator using the mg-equivalent factor
    elif base_token in ("iu",):
        numerator_unit = "IU"
    elif base_token in ("ml", "мл"):
        numerator_unit = "mL"
    else:
        numerator_unit = None

    if numerator_unit is None:
        return DoseExpression(
            numeric_min=dose, numeric_max=dose, numerator_unit=None,
            denominator_weight=denominator_weight, denominator_time=denominator_time,
            per_dose_or_per_day=denominator_time, frequency=frequency,
            max_single_dose=None, max_daily_dose=None,
            source_expression=source_expression, parser_status=UNPARSED,
        )

    numeric_min = dose
    numeric_max = dose
    if base_token in ("g", "г"):
        numeric_min = dose * _MG_EQUIVALENT[base_token]
        numeric_max = numeric_min

    return DoseExpression(
        numeric_min=numeric_min, numeric_max=numeric_max, numerator_unit=numerator_unit,
        denominator_weight=denominator_weight, denominator_time=denominator_time,
        per_dose_or_per_day=denominator_time, frequency=frequency,
        max_single_dose=None,  # assembled_regimens has no max-dose columns — never inferred
        max_daily_dose=None,
        source_expression=source_expression, parser_status=PARSED,
    )
