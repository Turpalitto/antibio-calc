"""DurationParser — extract duration in days from text."""

from __future__ import annotations

import re
from typing import ClassVar

from medical_normalizer.models import NormalizedRegimen


class DurationParser:
    """Parse duration text to min/max/recommended days."""

    _RANGE: ClassVar[str] = "range"
    _SINGLE: ClassVar[str] = "single"
    _SKIP: ClassVar[str] = "skip"
    _STATIC_DOSE: ClassVar[str] = "static_dose"
    _MAX_HOURS: ClassVar[str] = "max_hours"
    _HOURS_SINGLE: ClassVar[str] = "hours_single"
    _MIN_WEEKS: ClassVar[str] = "min_weeks"
    _MAX_WEEKS: ClassVar[str] = "max_weeks"
    _RANGE_YEARS: ClassVar[str] = "range_years"
    _SINGLE_YEARS: ClassVar[str] = "single_years"

    _patterns: ClassVar[list[tuple[re.Pattern, str]]] = []

    @classmethod
    def _init_patterns(cls) -> None:
        if cls._patterns:
            return
        cls._patterns = [
            # RANGES first (before single-value patterns)
            (re.compile(r"(\d+)\s*[-–—]\s*(\d+)\s*(?:дн|сут|день|дня|дней)"), cls._RANGE),
            (re.compile(r"(\d+)\s*[-–—]\s*(\d+)\s*(?:day|days)"), cls._RANGE),
            (re.compile(r"(\d+)\s*[-–—]\s*(\d+)\s*$"), cls._RANGE),
            # range years: "2 - 3 лет"
            (re.compile(r"(\d+)\s*[-–—]\s*(\d+)\s*лет"), cls._RANGE_YEARS),

            # Single-dose markers → 1 day (high-count failing data)
            (re.compile(r"однократн"), cls._STATIC_DOSE),
            (re.compile(r"разов"), cls._STATIC_DOSE),
            (re.compile(r"одн[аа]\s+доз"), cls._STATIC_DOSE),
            (re.compile(r"одн[аа]\s+предоперационн"), cls._STATIC_DOSE),

            # Hours → days
            # "не более N часов" → max = N/24
            (re.compile(r"не\s*более\s*(\d+)\s*час"), cls._MAX_HOURS),
            # "в течение N часов" → single = N/24
            (re.compile(r"в\s+течение\s+(\d+)\s*час"), cls._HOURS_SINGLE),
            # bare "N часов" / "N часа" → single = N/24
            (re.compile(r"(\d+)\s*час"), cls._HOURS_SINGLE),

            # Weeks bounds
            # "не менее N(-х) недель" → min = N*7
            (re.compile(r"не\s*менее\s*(\d+)\s*[-\u2013]?\s*х?\s*нед"), cls._MIN_WEEKS),
            # "до N(-х) недель" → max = N*7
            (re.compile(r"до\s+(\d+)\s*[-\u2013]?\s*х?\s*нед"), cls._MAX_WEEKS),

            # Years single: "N лет"
            (re.compile(r"(\d+)\s*лет"), cls._SINGLE_YEARS),

            # SINGLE values (days/сут/нед/мес)
            (re.compile(r"(\d+)\s*(?:дн|сут|день|дня|дней|д)"), cls._SINGLE),
            (re.compile(r"(\d+)\s*(?:суток|сут)"), cls._SINGLE),
            (re.compile(r"(\d+)\s*(?:day|days)"), cls._SINGLE),
            (re.compile(r"(\d+)\s*(?:недел|нед)"), cls._SINGLE),
            (re.compile(r"(\d+)\s*(?:месяц|мес)"), cls._SINGLE),

            # SKIP markers (no recoverable value)
            (re.compile(r"длительн|длит"), cls._SKIP),
            (re.compile(r"не\s*указан"), cls._SKIP),
            (re.compile(r"на\s+весь\s+период"), cls._SKIP),
            (re.compile(r"до\s+окончани"), cls._SKIP),
            (re.compile(r"до\s+получени"), cls._SKIP),
            (re.compile(r"до\s+выявлени"), cls._SKIP),
            (re.compile(r"во\s+время\s+вс[ее]й"), cls._SKIP),
            (re.compile(r"на\s+вс[ее]х\s+этапах"), cls._SKIP),
            (re.compile(r"на\s+фон[еи]\s+провод"), cls._SKIP),
            (re.compile(r"при\s+связи\s+рецидив"), cls._SKIP),
            (re.compile(r"до\s+оператив"), cls._SKIP),
        ]

    @staticmethod
    def _apply_unit_multipliers(val: float, matched_text: str) -> float:
        """Multiply by 7 for weeks, 30 for months."""
        if "нед" in matched_text:
            val *= 7.0
        if "мес" in matched_text:
            val *= 30.0
        return val

    @classmethod
    def parse(cls, regimen: NormalizedRegimen, raw: dict) -> NormalizedRegimen:
        dur_raw = (raw.get("duration", "") or "").strip().lower()
        if not dur_raw:
            return regimen

        cls._init_patterns()

        for pattern, tag in cls._patterns:
            match = pattern.search(dur_raw)
            if not match:
                continue

            if tag == cls._SKIP:
                return regimen

            if tag == cls._STATIC_DOSE:
                regimen.duration_days_min = 1.0
                regimen.duration_days_max = 1.0
                regimen.duration_days_recommended = 1.0
                return regimen

            if tag == cls._MAX_HOURS:
                try:
                    hours = float(match.group(1))
                except (ValueError, TypeError, IndexError):
                    continue
                days = hours / 24.0
                regimen.duration_days_max = days
                regimen.duration_days_recommended = days
                return regimen

            if tag == cls._HOURS_SINGLE:
                try:
                    hours = float(match.group(1))
                except (ValueError, TypeError, IndexError):
                    continue
                days = hours / 24.0
                regimen.duration_days_min = days
                regimen.duration_days_max = days
                regimen.duration_days_recommended = days
                return regimen

            if tag == cls._MIN_WEEKS:
                try:
                    w = float(match.group(1))
                except (ValueError, TypeError, IndexError):
                    continue
                days = w * 7.0
                regimen.duration_days_min = days
                regimen.duration_days_recommended = days
                return regimen

            if tag == cls._MAX_WEEKS:
                try:
                    w = float(match.group(1))
                except (ValueError, TypeError, IndexError):
                    continue
                days = w * 7.0
                regimen.duration_days_max = days
                regimen.duration_days_recommended = days
                return regimen

            if tag == cls._RANGE_YEARS:
                groups = match.groups()
                try:
                    regimen.duration_days_min = float(groups[0]) * 365.0
                    regimen.duration_days_max = float(groups[1]) * 365.0
                    return regimen
                except (ValueError, TypeError, IndexError):
                    continue

            if tag == cls._SINGLE_YEARS:
                try:
                    val = float(match.group(1))
                except (ValueError, TypeError, IndexError):
                    continue
                days = val * 365.0
                regimen.duration_days_min = days
                regimen.duration_days_max = days
                regimen.duration_days_recommended = days
                return regimen

            groups = match.groups()

            if tag == cls._RANGE:
                if len(groups) >= 2 and groups[1] is not None:
                    try:
                        regimen.duration_days_min = float(groups[0])
                        regimen.duration_days_max = float(groups[1])
                        return regimen
                    except (ValueError, TypeError):
                        pass
                continue

            if tag == cls._SINGLE:
                if not groups:
                    continue
                try:
                    val = float(groups[0])
                except (ValueError, TypeError):
                    continue
                val = cls._apply_unit_multipliers(val, match.group(0))
                regimen.duration_days_min = val
                regimen.duration_days_max = val
                regimen.duration_days_recommended = val
                return regimen

        return regimen
