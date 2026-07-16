"""Phase 3-6 — Source-backed dose semantics parser (RC-030).

Classifies each regimen's dose into an explicit semantic_type by searching a
bounded text window around the matched dose number inside `source_quote` for
explicit Russian/English per-day / per-dose signals. Never infers semantics
from frequency alone, except for the one case where inference is not a guess
at all: frequency == 1 makes "per administration" and "per day" algebraically
identical (see RESOLVED_BY_FREQUENCY_ONE below) — this is arithmetic, not a
clinical assumption.

If the dose number cannot be located in source_quote at all, or the window
around it contains no explicit signal, or contains conflicting signals, the
result is AMBIGUOUS — never guessed.
"""
from __future__ import annotations

import re
import time
import uuid
from typing import Optional

from .parser import parse_dose_expression
from .models import PARSED, UNPARSED
from .semantics_models import DoseSemantics

WINDOW_CHARS = 90

# Explicit "N times per day" style phrases — these mean the number attached to
# them is a SINGLE-ADMINISTRATION amount repeated N times/day. Covers both
# digit ("2 раза") and spelled-out ("два раза") Russian frequency counts.
_RU_NUMBER_WORD = r"(?:\d+(?:[.,]\d+)?|один|одна|два|две|три|четыре|пять|шесть|дважды|трижды)"
_FREQ_MULTIPLIER_RE = re.compile(
    rf"{_RU_NUMBER_WORD}\s*раз(?:а|ов)?\s+в\s+(?:сутки|день)"
    r"|(?:once|twice|three times|four times)\s+(?:a|per)\s+day"
    r"|\d+\s*(?:x|×)\s*/?\s*day",
    re.IGNORECASE,
)

# "every N hours" — administration-interval phrasing, implies per-dose.
_EVERY_N_HOURS_RE = re.compile(
    r"каждые\s+\d+(?:\s*-\s*\d+)?\s*ч(?:ас\w*)?|every\s+\d+\s*hours?",
    re.IGNORECASE,
)

# Explicit per-administration nouns.
_PER_DOSE_NOUN_RE = re.compile(
    r"на\s+введени\w*|за\s+одно\s+введени\w*|разов\w*\s+доз\w*"
    r"|per\s+dose|per\s+administration|single\s+dose",
    re.IGNORECASE,
)

# Explicit per-day markers NOT part of a "N раз в сутки" frequency clause
# (that case is handled by _FREQ_MULTIPLIER_RE and takes priority).
_PLAIN_PER_DAY_RE = re.compile(
    r"/\s*сут(?:ки)?\b|\bв\s+сутки\b|суточн\w*\s+доз\w*|/\s*day\b|per\s+day",
    re.IGNORECASE,
)

_MAX_DOSE_RE = re.compile(
    r"не\s+более|максимальн\w*\s+сут\w*\s+доз\w*|максимальн\w*\s+разов\w*\s+доз\w*"
    r"|не\s+превышать|max(?:imum)?\s+(?:daily|single)\s+dose",
    re.IGNORECASE,
)

# Numeric max-dose value, restricted to mass units (мг/г/гр) so duration
# phrases like "не более 24 часов" are never captured as a dose.
_MAX_DOSE_VALUE_RE = re.compile(
    r"не\s+более\s+(\d+(?:[.,]\d+)?)\s*(мг|г|гр)\b"
    r"|max(?:imum)?\s+(?:daily|single)\s+dose\D{0,10}(\d+(?:[.,]\d+)?)\s*(mg|g)\b",
    re.IGNORECASE,
)

_MG_PER_UNIT = {"мг": 1.0, "г": 1000.0, "гр": 1000.0, "mg": 1.0, "g": 1000.0}


def extract_max_dose_value_from_window(window: str) -> Optional[tuple[float, str]]:
    """Return (value_in_mg, matched_text) for the first source-backed numeric
    max-dose statement found within the given text window, or None."""
    m = _MAX_DOSE_VALUE_RE.search(window)
    if not m:
        return None
    if m.group(1) is not None:
        value_str, unit = m.group(1), m.group(2)
    else:
        value_str, unit = m.group(3), m.group(4)
    value = float(value_str.replace(",", "."))
    factor = _MG_PER_UNIT.get(unit.lower(), 1.0)
    return value * factor, m.group(0)


def _find_dose_window(source_quote: str, dose: float) -> Optional[tuple[str, int]]:
    """Return (window_text, anchor_offset) where anchor_offset is the position
    of the matched dose token within window_text, or None if not locatable."""
    if not source_quote or dose is None:
        return None
    candidates = []
    if dose == int(dose):
        candidates.append(str(int(dose)))
    for txt in (f"{dose:g}", f"{dose:.1f}", f"{dose:.2f}"):
        candidates.append(txt)
        candidates.append(txt.replace(".", ","))
    seen = set()
    for token in candidates:
        if token in seen or not token:
            continue
        seen.add(token)
        idx = source_quote.find(token)
        if idx == -1:
            continue
        start = max(0, idx - WINDOW_CHARS // 3)
        end = min(len(source_quote), idx + len(token) + WINDOW_CHARS)
        return source_quote[start:end], idx - start
    return None


def _overlaps(span_a: tuple[int, int], span_b: tuple[int, int]) -> bool:
    return span_a[0] < span_b[1] and span_b[0] < span_a[1]


def _nearest(matches: list, anchor: int):
    def distance(m) -> int:
        s, e = m.span()
        if anchor < s:
            return s - anchor
        if anchor > e:
            return anchor - e
        return 0
    return min(matches, key=distance)


def _detect_period_signal(window: str, anchor: int) -> tuple[Optional[str], Optional[str], str]:
    """Return (time_denominator, matched_fragment, ambiguity_status).

    `anchor` is the position of the actual dose token inside `window`. When a
    window contains signals belonging to more than one dose alternative
    (e.g. "500 mg 3x/day or 875 mg 2x/day"), the signal *nearest* the anchor
    is used — not simply the first one found — to avoid attributing a
    neighboring dose's frequency clause to this one.

    "N раз в сутки" is itself a per-dose signal that textually contains the
    substring "в сутки" — matching that phrase against the plain per-day
    pattern too would be a spurious self-conflict, not a genuine second
    signal. Any plain-per-day match whose span overlaps a per-dose match is
    discarded before comparing the two signal sets.
    """
    per_dose_matches = (
        list(_FREQ_MULTIPLIER_RE.finditer(window))
        + list(_EVERY_N_HOURS_RE.finditer(window))
        + list(_PER_DOSE_NOUN_RE.finditer(window))
    )

    plain_day_matches = [
        m for m in _PLAIN_PER_DAY_RE.finditer(window)
        if not any(_overlaps(m.span(), pd.span()) for pd in per_dose_matches)
    ]

    if per_dose_matches and plain_day_matches:
        nearest_dose = _nearest(per_dose_matches, anchor)
        nearest_day = _nearest(plain_day_matches, anchor)
        # If one signal type is unambiguously closer to the anchor than the
        # other, prefer it — it's the one actually describing this dose.
        dist_dose = abs(nearest_dose.start() - anchor) if anchor < nearest_dose.start() else \
            (anchor - nearest_dose.end() if anchor > nearest_dose.end() else 0)
        dist_day = abs(nearest_day.start() - anchor) if anchor < nearest_day.start() else \
            (anchor - nearest_day.end() if anchor > nearest_day.end() else 0)
        if dist_dose < dist_day:
            return "dose", nearest_dose.group(0), "UNAMBIGUOUS"
        if dist_day < dist_dose:
            return "day", nearest_day.group(0), "UNAMBIGUOUS"
        return None, None, "AMBIGUOUS_CONFLICTING_SIGNAL"
    if per_dose_matches:
        return "dose", _nearest(per_dose_matches, anchor).group(0), "UNAMBIGUOUS"
    if plain_day_matches:
        return "day", _nearest(plain_day_matches, anchor).group(0), "UNAMBIGUOUS"
    return None, None, "AMBIGUOUS_NO_SIGNAL"


def extract_max_dose_signal(source_quote: str) -> Optional[str]:
    if not source_quote:
        return None
    m = _MAX_DOSE_RE.search(source_quote)
    return m.group(0) if m else None


def classify_regimen(regimen: dict) -> DoseSemantics:
    dose = regimen.get("dose")
    unit = regimen.get("unit") or ""
    frequency = regimen.get("frequency")
    source_quote = regimen.get("source_quote") or ""
    regimen_id = str(regimen.get("regimen_id"))
    version = regimen.get("version") or 1

    expr = parse_dose_expression(dose, unit, frequency)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    base = dict(
        semantics_id=f"ds_{uuid.uuid4().hex[:16]}",
        regimen_id=regimen_id, regimen_version=version,
        numeric_min=expr.numeric_min, numeric_max=expr.numeric_max,
        numerator_unit=expr.numerator_unit, weight_denominator=expr.denominator_weight,
        frequency=frequency, max_single_dose=None, max_daily_dose=None,
        source_expression=expr.source_expression, normalized_expression="",
        provenance={"source_pdf": regimen.get("source_pdf"), "source_page": regimen.get("source_page"),
                    "guideline_id": regimen.get("guideline_id")},
        derived_from=f"assembled_regimens.sqlite:{regimen_id}:{version}",
        confidence=regimen.get("confidence") or 0.0,
        created_at=now, matched_fragment=None,
    )

    if dose is None:
        # Category K (MISSING) vs L (NOT_A_DOSABLE_REGIMEN): a fully empty
        # regimen row (no dose, no unit, no frequency, no duration) with a
        # long free-text "antibiotic" field is very likely a mis-extracted
        # procedure/diagnostic description, not a real drug regimen.
        antibiotic = regimen.get("antibiotic") or ""
        looks_like_non_dosable = (
            unit == "" and frequency is None and regimen.get("duration_recommended") is None
            and len(antibiotic) > 60
        )
        return DoseSemantics(
            semantic_type="NOT_APPLICABLE" if looks_like_non_dosable else "MISSING",
            time_denominator=None, administration_scope=None,
            parser_status=UNPARSED, ambiguity_status="NOT_APPLICABLE",
            **base,
        )

    if expr.parser_status == UNPARSED:
        return DoseSemantics(
            semantic_type="UNPARSED", time_denominator=None, administration_scope=None,
            parser_status=UNPARSED, ambiguity_status="NOT_APPLICABLE",
            **base,
        )

    window_result = _find_dose_window(source_quote, dose)
    max_signal = extract_max_dose_signal(source_quote)
    max_value_mg = None
    dose_token_located = window_result is not None

    if window_result is None:
        time_denom, fragment, ambiguity = None, None, "AMBIGUOUS_NO_SIGNAL"
        base["provenance"] = {**base["provenance"],
                              "note": "SOURCE_TEXT_INCOMPLETE: dose value not locatable in source_quote text"}
    else:
        window, anchor = window_result
        time_denom, fragment, ambiguity = _detect_period_signal(window, anchor)
        max_result = extract_max_dose_value_from_window(window)
        if max_result is not None:
            max_value_mg, max_match_text = max_result
            base["provenance"] = {**base["provenance"], "max_dose_match": max_match_text}

    weight_based = expr.denominator_weight

    if time_denom is None and frequency == 1.0 and dose_token_located:
        # Algebraic shortcut, not a clinical guess: with one administration
        # per day, per-dose and per-day quantities are numerically identical.
        # Only applies when the dose token was actually found in source_quote
        # — if it wasn't (SOURCE_TEXT_INCOMPLETE), we have no evidence this
        # number even belongs to this sentence, so no shortcut is safe.
        time_denom = "day"
        ambiguity = "RESOLVED_BY_FREQUENCY_ONE"
        fragment = fragment or "(frequency=1: per-dose and per-day are algebraically identical)"

    is_range = expr.numeric_min != expr.numeric_max

    if time_denom == "day":
        semantic_type = "RANGE_PER_DAY" if is_range else ("WEIGHT_PER_DAY" if weight_based else "FIXED_PER_DAY")
    elif time_denom == "dose":
        semantic_type = "RANGE_PER_DOSE" if is_range else ("WEIGHT_PER_DOSE" if weight_based else "FIXED_PER_DOSE")
    else:
        semantic_type = "AMBIGUOUS"

    base["matched_fragment"] = fragment
    if max_signal:
        base["provenance"] = {**base["provenance"], "max_dose_signal": max_signal}
    if max_value_mg is not None:
        if time_denom == "day":
            base["max_daily_dose"] = max_value_mg
        elif time_denom == "dose":
            base["max_single_dose"] = max_value_mg
        # else: max-dose value found but this row's own period is unresolved —
        # do not attach it to either field rather than guess which one it caps.

    return DoseSemantics(
        semantic_type=semantic_type,
        time_denominator=time_denom,
        administration_scope=fragment,
        parser_status=PARSED,
        ambiguity_status=ambiguity,
        **base,
    )
