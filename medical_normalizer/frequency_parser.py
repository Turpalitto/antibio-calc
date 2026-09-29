"""FrequencyParser — extract times per day from frequency text.

Range policy (C5): when the source states a RANGE ("2-3 раза в сутки",
"2-3 р/сут", "каждые 6-8 часов"), frequency_per_day holds the LOWER bound and
frequency_is_range is set to True. The lower bound is the conservative
(never-overdose) default and matches the pre-existing en-dash behaviour.
"""

from __future__ import annotations

import re
from typing import ClassVar

from medical_normalizer.models import MISSING_FIELD_INPUT, NormalizedRegimen


def _coerce_text(val) -> str:
    """Coerce a raw text value to a lowered, stripped string.

    A non-string (int / list / dict) yields "" — the caller records a
    MISSING_FIELD_INPUT ParserError (H2) rather than letting .strip() raise.
    """
    if val is None or not isinstance(val, str):
        return ""
    return val.strip().lower()


def _is_malformed(val) -> bool:
    """True when a field was supplied but is not usable text (H2).

    A genuinely absent (or explicitly null) field is a modelled state — the
    parser reports "no information" and the pipeline continues. A field that
    arrives as an int / float / list / dict is a real extraction defect: it
    used to raise AttributeError from .strip()/.lower() and is now recorded
    as a ParserError via the MISSING_FIELD_INPUT marker.
    """
    return val is not None and not isinstance(val, str)


class FrequencyParser:
    """Parse frequency text to number of times per day."""

    _EVERY_N_HOURS: ClassVar[str] = "every_n_hours"
    _STATIC: ClassVar[str] = "static"
    _TIMES_PER: ClassVar[str] = "times_per"
    _EVERY_N_DAYS: ClassVar[str] = "every_n_days"
    _WORD_TIMES_PER: ClassVar[str] = "word_times_per"
    _WORD_ADV: ClassVar[str] = "word_adv"
    _WORD_DOSES: ClassVar[str] = "word_doses"
    _TIMES_PER_WEEK: ClassVar[str] = "times_per_week"
    _TIMES_PER_MONTH: ClassVar[str] = "times_per_month"
    _EVERY_N_WEEKS: ClassVar[str] = "every_n_weeks"

    _WORD_TO_NUM: ClassVar[dict[str, float]] = {
        "один": 1.0, "одну": 1.0,
        "два": 2.0, "две": 2.0,
        "три": 3.0, "четыре": 4.0, "пять": 5.0,
        "дважды": 2.0, "трижды": 3.0, "четырежды": 4.0,
    }

    _PERIOD_DIVISOR: ClassVar[dict[str, float]] = {
        "дн": 1.0, "ден": 1.0, "сут": 1.0,
        "нед": 7.0, "мес": 30.0,
    }

    # (pattern, static_value, tag, is_range)
    _patterns: ClassVar[list[tuple[re.Pattern, float, str, bool]]] = []

    @classmethod
    def _init_patterns(cls) -> None:
        if cls._patterns:
            return
        cls._patterns = [
            # every N-M hours (range, take min)
            (re.compile(r"кажд(?:ые|ый|ую)\s+(\d+)\s*[-\u2013]\s*\d+\s*ч"), 0.0, cls._EVERY_N_HOURS, True),
            (re.compile(r"кажд(?:ые|ый|ую)\s+(\d+)\s*[-\u2013]\s*\d+\s*часа"), 0.0, cls._EVERY_N_HOURS, True),
            # every N hours
            (re.compile(r"кажд(?:ые|ый|ую)\s+(\d+)\s*ч"), 0.0, cls._EVERY_N_HOURS, False),
            (re.compile(r"кажд(?:ые|ый|ую)\s+(\d+)\s*часа"), 0.0, cls._EVERY_N_HOURS, False),
            # every N days — must precede the weeks patterns; N is arbitrary
            (re.compile(r"кажд(?:ые|ый|ую)\s+(\d+)\s*(?:дней|дня|день|дн|ден|сут)"), 0.0, cls._EVERY_N_DAYS, False),
            # "раз в N часов" (once every N hours) — trailing number = range
            (re.compile(r"раз\s+в\s+(\d+)\s*[-\u2013]?\s*(?:\d+)?\s*ч"), 0.0, cls._EVERY_N_HOURS, True),
            (re.compile(r"раз\s+в\s+(\d+)\s*[-\u2013]?\s*(?:\d+)?\s*часа"), 0.0, cls._EVERY_N_HOURS, True),
            # Latin q8h
            (re.compile(r"q\s*(\d+)\s*h"), 0.0, cls._EVERY_N_HOURS, False),
            (re.compile(r"q\s*(\d+)\s*hrs?"), 0.0, cls._EVERY_N_HOURS, False),
            # RANGE word forms FIRST (C5): "2-3 раза в сутки" previously matched
            # the scalar pattern at the "3", silently reporting the UPPER bound.
            (re.compile(r"(\d+)\s*[-\u2013\u2014]\s*(\d+)\s*раз(?:а)?\s*(?:в|за)\s+(?:1\s+)?(?:ден|сут)"), 0.0, cls._TIMES_PER, True),
            (re.compile(r"(\d+)\s*[-\u2013\u2014]\s*(\d+)\s*раз(?:а)?\s*(?:в|за)\s+(?:1\s+)?(?:нед|мес)"), 0.0, cls._TIMES_PER, True),
            (re.compile(r"(\d+)\s*[-\u2013\u2014]\s*(\d+)\s*раз(?:а)?\s*/\s*сут"), 0.0, cls._TIMES_PER, True),
            (re.compile(r"(\d+)\s*[-\u2013\u2014]\s*(\d+)\s*р\s*/\s*сут"), 0.0, cls._TIMES_PER, True),
            # N раз в день/сутки
            (re.compile(r"(\d+)\s*раз(?:а)?\s+(?:в|за)\s+(?:1\s+)?ден"), 0.0, cls._TIMES_PER, False),
            (re.compile(r"(\d+)\s*раз(?:а)?\s+(?:в|за)\s+сут"), 0.0, cls._TIMES_PER, False),
            # slash forms: N раза/сут, N р/сут, N р/сутки, Nр в сут
            (re.compile(r"(\d+)\s*раз(?:а)?\s*/\s*сут"), 0.0, cls._TIMES_PER, False),
            (re.compile(r"(\d+)\s*р\s*/\s*сут(?:ки)?"), 0.0, cls._TIMES_PER, False),
            (re.compile(r"(\d+)\s*р\s+в\s+сут"), 0.0, cls._TIMES_PER, False),
            # N раз в неделю / месяц
            (re.compile(r"(\d+)\s*раз(?:а)?\s+в\s+нед"), 0.0, cls._TIMES_PER_WEEK, False),
            (re.compile(r"(\d+)\s*раз(?:а)?\s+в\s+мес"), 0.0, cls._TIMES_PER_MONTH, False),
            # 1 раз в N дней / 1 раз через N дней (N arbitrary, all day forms)
            (re.compile(r"1\s*раз(?:а)?\s+в\s+(\d+)\s*(?:дней|дня|день|дн|ден)"), 0.0, cls._EVERY_N_DAYS, False),
            (re.compile(r"1\s*раз(?:а)?\s+через\s+(\d+)\s*(?:дней|дня|день|дн|ден)"), 0.0, cls._EVERY_N_DAYS, False),
            # каждые N недели / с интервалом N нед → 1/(N*7)
            (re.compile(r"кажд(?:ые|ый|ую)\s+(\d+)\s*нед"), 0.0, cls._EVERY_N_WEEKS, False),
            (re.compile(r"интервал\w*\s+(?:в\s+)?(\d+)\s*нед"), 0.0, cls._EVERY_N_WEEKS, False),
            # word-number times-per: один/два/три раза в день/сутки/неделю/месяц
            (re.compile(
                r"(один|одну|два|две|три|четыре|пять)\s+раз(?:а)?\s+(?:в|за)\s+(ден|сут|нед|мес)"
            ), 0.0, cls._WORD_TIMES_PER, False),
            # word adverbials: дважды/трижды/четырежды в день/сутки/неделю
            (re.compile(r"(дважды|трижды|четырежды)\s+(?:в|за)\s+(ден|сут|нед)"), 0.0, cls._WORD_ADV, False),
            # Latin N times/day
            (re.compile(r"(\d+)\s*(?:times?|x)\s*(?:per|a|/)\s*day"), 0.0, cls._TIMES_PER, False),
            # Latin static abbreviations.
            # qod ("every other day") MUST be tested before qd: the bare qd
            # alternative matched the "od" inside "qod" and reported once-daily
            # (H1). \b additionally stops bd/id from matching inside longer
            # tokens such as "qod" or "tid".
            (re.compile(r"q\s*[0o]\s*d"), 0.5, cls._STATIC, False),
            (re.compile(r"\b(?:bid|bd|b\.i\.d\.)"), 2.0, cls._STATIC, False),
            (re.compile(r"\b(?:tid|tds|t\.i\.d\.)"), 3.0, cls._STATIC, False),
            (re.compile(r"\b(?:qid|q\.i\.d\.)"), 4.0, cls._STATIC, False),
            (re.compile(r"\b(?:qd|od|s\.i\.d\.)"), 1.0, cls._STATIC, False),
            (re.compile(r"\b(?:qh|q\.1?h)"), 24.0, cls._STATIC, False),
            # в/на/за N(-M) приема/введения → N (range: take first)
            (re.compile(r"(?:в|на|за)\s+(\d+)\s*[-\u2013]\s*\d+\s*(?:прием|введен)"), 0.0, cls._TIMES_PER, True),
            (re.compile(r"(?:в|на|за)\s+(\d+)\s*(?:прием|введен)"), 0.0, cls._TIMES_PER, False),
            # word-number doses: в три приема
            (re.compile(r"(?:в|на)\s+(один|одну|два|две|три|четыре|пять)\s*(?:прием|введен)"), 0.0, cls._WORD_DOSES, False),
            # в сутки в N приема / за N введения в сутки
            (re.compile(r"в\s+сутки\s+в\s+(\d+)\s*прием"), 0.0, cls._TIMES_PER, False),
            (re.compile(r"за\s+(\d+)\s*введен\w*\s+в\s+сут"), 0.0, cls._TIMES_PER, False),
            # суточная доза разделенная на N приема / разделенных на N приема
            (re.compile(r"разделенн\w*\s+на\s+(\d+)\s*прием"), 0.0, cls._TIMES_PER, False),
            # N приема alone / 1 прием
            (re.compile(r"(\d+)\s*прием(?:а|ов)?\s*$"), 0.0, cls._TIMES_PER, False),
            # N раза alone (no period, implies per day)
            (re.compile(r"(\d+)\s*раза?\s*$"), 0.0, cls._TIMES_PER, False),
            # через день
            (re.compile(r"через\s+день"), 0.5, cls._STATIC, False),
            # ежедневно
            (re.compile(r"ежедн"), 1.0, cls._STATIC, False),
            # непрерывно / постоянно
            (re.compile(r"непрерывн|постоян"), 24.0, cls._STATIC, False),
            # однократно / двукратно / трехкратно
            (re.compile(r"однократн"), 1.0, cls._STATIC, False),
            (re.compile(r"двукратн"), 2.0, cls._STATIC, False),
            (re.compile(r"тр[её]хкратн"), 3.0, cls._STATIC, False),
            # капельно → usually once
            (re.compile(r"капельно"), 1.0, cls._STATIC, False),
            # как можно скорее → single dose
            (re.compile(r"как\s+можно\s+скоре"), 1.0, cls._STATIC, False),
            # разовая доза → single dose
            (re.compile(r"разов"), 1.0, cls._STATIC, False),
            # DEFAULTS (last): в сутки / в день / суточная доза → 1.0
            (re.compile(r"в\s+сутки"), 1.0, cls._STATIC, False),
            (re.compile(r"в\s+день"), 1.0, cls._STATIC, False),
            (re.compile(r"суточн"), 1.0, cls._STATIC, False),
        ]

    @classmethod
    def parse(cls, regimen: NormalizedRegimen, raw: dict) -> NormalizedRegimen:
        freq_value = raw.get("frequency") if isinstance(raw, dict) else None
        freq_raw = _coerce_text(freq_value)
        if not freq_raw:
            regimen.frequency_per_day = None
            regimen.frequency_is_range = False
            if _is_malformed(freq_value):
                _record_missing_input(regimen, "frequency")
            return regimen

        cls._init_patterns()

        for pattern, static_value, tag, is_range in cls._patterns:
            match = pattern.search(freq_raw)
            if not match:
                continue

            if tag == cls._STATIC:
                regimen.frequency_per_day = static_value
                regimen.frequency_is_range = False
                return regimen

            if tag == cls._WORD_TIMES_PER:
                word = match.group(1)
                period = match.group(2)
                num = cls._WORD_TO_NUM.get(word, 1.0)
                divisor = cls._PERIOD_DIVISOR.get(period, 1.0)
                regimen.frequency_per_day = num / divisor
                regimen.frequency_is_range = False
                return regimen

            if tag == cls._WORD_ADV:
                word = match.group(1)
                period = match.group(2)
                num = cls._WORD_TO_NUM.get(word, 1.0)
                divisor = cls._PERIOD_DIVISOR.get(period, 1.0)
                regimen.frequency_per_day = num / divisor
                regimen.frequency_is_range = False
                return regimen

            if tag == cls._WORD_DOSES:
                word = match.group(1)
                regimen.frequency_per_day = cls._WORD_TO_NUM.get(word, 1.0)
                regimen.frequency_is_range = False
                return regimen

            try:
                num = float(match.group(1))
            except (IndexError, ValueError, TypeError):
                continue

            # Range-shaped patterns take the LOWER bound and flag the fact.
            regimen.frequency_is_range = is_range

            if tag == cls._EVERY_N_HOURS:
                regimen.frequency_per_day = 24.0 / num if num > 0 else None
                return regimen

            if tag == cls._EVERY_N_DAYS:
                regimen.frequency_per_day = 1.0 / num if num > 0 else None
                return regimen

            if tag == cls._EVERY_N_WEEKS:
                regimen.frequency_per_day = 1.0 / (num * 7.0) if num > 0 else None
                return regimen

            if tag == cls._TIMES_PER:
                regimen.frequency_per_day = num
                return regimen

            if tag == cls._TIMES_PER_WEEK:
                regimen.frequency_per_day = num / 7.0
                return regimen

            if tag == cls._TIMES_PER_MONTH:
                regimen.frequency_per_day = num / 30.0
                return regimen

        regimen.frequency_per_day = None
        regimen.frequency_is_range = False
        return regimen


def _record_missing_input(regimen: NormalizedRegimen, field_name: str) -> None:
    """Record a MISSING_FIELD_INPUT marker on the regimen (H2).

    MedicalNormalizer._run_parser promotes these markers into real
    ParserError entries in NormalizedResult.errors, so the failure is
    recorded rather than silently swallowed — while the pipeline continues.
    """
    if not regimen.warnings:
        regimen.warnings = []
    marker = f"{MISSING_FIELD_INPUT}:{field_name}"
    if marker not in regimen.warnings:
        regimen.warnings.append(marker)
