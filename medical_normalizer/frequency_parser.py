"""FrequencyParser — extract times per day from frequency text."""

from __future__ import annotations

import re
from typing import ClassVar

from medical_normalizer.models import NormalizedRegimen


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

    _patterns: ClassVar[list[tuple[re.Pattern, float, str]]] = []

    @classmethod
    def _init_patterns(cls) -> None:
        if cls._patterns:
            return
        cls._patterns = [
            # every N-M hours (range, take min)
            (re.compile(r"кажд(?:ые|ый|ую)\s+(\d+)\s*[-\u2013]\s*\d+\s*ч"), 0.0, cls._EVERY_N_HOURS),
            (re.compile(r"кажд(?:ые|ый|ую)\s+(\d+)\s*[-\u2013]\s*\d+\s*часа"), 0.0, cls._EVERY_N_HOURS),
            # every N hours
            (re.compile(r"кажд(?:ые|ый|ую)\s+(\d+)\s*ч"), 0.0, cls._EVERY_N_HOURS),
            (re.compile(r"кажд(?:ые|ый|ую)\s+(\d+)\s*часа"), 0.0, cls._EVERY_N_HOURS),
            # "раз в N часов" (once every N hours)
            (re.compile(r"раз\s+в\s+(\d+)\s*[-\u2013]?\s*(?:\d+)?\s*ч"), 0.0, cls._EVERY_N_HOURS),
            (re.compile(r"раз\s+в\s+(\d+)\s*[-\u2013]?\s*(?:\d+)?\s*часа"), 0.0, cls._EVERY_N_HOURS),
            # Latin q8h
            (re.compile(r"q\s*(\d+)\s*h"), 0.0, cls._EVERY_N_HOURS),
            (re.compile(r"q\s*(\d+)\s*hrs?"), 0.0, cls._EVERY_N_HOURS),
            # N раз в день/сутки
            (re.compile(r"(\d+)\s*раз(?:а)?\s+(?:в|за)\s+(?:1\s+)?ден"), 0.0, cls._TIMES_PER),
            (re.compile(r"(\d+)\s*раз(?:а)?\s+(?:в|за)\s+сут"), 0.0, cls._TIMES_PER),
            # slash forms: N раза/сут, N р/сут, N р/сутки, Nр в сут
            # range first: "2–3 р/сут" (en-dash, take first)
            (re.compile(r"(\d+)[-\u2013]\d+\s*р\s*/\s*сут"), 0.0, cls._TIMES_PER),
            (re.compile(r"(\d+)\s*раз(?:а)?\s*/\s*сут"), 0.0, cls._TIMES_PER),
            (re.compile(r"(\d+)\s*р\s*/\s*сут(?:ки)?"), 0.0, cls._TIMES_PER),
            (re.compile(r"(\d+)\s*р\s+в\s+сут"), 0.0, cls._TIMES_PER),
            # N раз в неделю / месяц
            (re.compile(r"(\d+)\s*раз(?:а)?\s+в\s+нед"), 0.0, cls._TIMES_PER_WEEK),
            (re.compile(r"(\d+)\s*раз(?:а)?\s+в\s+мес"), 0.0, cls._TIMES_PER_MONTH),
            # 1 раз в N дней / 1 раз через N дней
            (re.compile(r"1\s*раз(?:а)?\s+в\s+(\d+)\s*дн"), 0.0, cls._EVERY_N_DAYS),
            (re.compile(r"1\s*раз(?:а)?\s+через\s+(\d+)\s*дн"), 0.0, cls._EVERY_N_DAYS),
            # каждые N недели / с интервалом N нед → 1/(N*7)
            (re.compile(r"кажд(?:ые|ый|ую)\s+(\d+)\s*нед"), 0.0, cls._EVERY_N_WEEKS),
            (re.compile(r"интервал\w*\s+(?:в\s+)?(\d+)\s*нед"), 0.0, cls._EVERY_N_WEEKS),
            # word-number times-per: один/два/три раза в день/сутки/неделю/месяц
            (re.compile(
                r"(один|одну|два|две|три|четыре|пять)\s+раз(?:а)?\s+(?:в|за)\s+(ден|сут|нед|мес)"
            ), 0.0, cls._WORD_TIMES_PER),
            # word adverbials: дважды/трижды/четырежды в день/сутки/неделю
            (re.compile(r"(дважды|трижды|четырежды)\s+(?:в|за)\s+(ден|сут|нед)"), 0.0, cls._WORD_ADV),
            # Latin N times/day
            (re.compile(r"(\d+)\s*(?:times?|x)\s*(?:per|a|/)\s*day"), 0.0, cls._TIMES_PER),
            # Latin static abbreviations
            (re.compile(r"(?:bid|bd|b\.i\.d\.)"), 2.0, cls._STATIC),
            (re.compile(r"(?:tid|tds|t\.i\.d\.)"), 3.0, cls._STATIC),
            (re.compile(r"(?:qid|q\.i\.d\.)"), 4.0, cls._STATIC),
            (re.compile(r"(?:qd|od|s\.i\.d\.)"), 1.0, cls._STATIC),
            (re.compile(r"(?:qh|q\.1?h)"), 24.0, cls._STATIC),
            (re.compile(r"q\s*[0o][d]"), 0.5, cls._STATIC),
            # в/на/за N(-M) приема/введения → N (range: take first)
            (re.compile(r"(?:в|на|за)\s+(\d+)\s*[-\u2013]\s*\d+\s*(?:прием|введен)"), 0.0, cls._TIMES_PER),
            (re.compile(r"(?:в|на|за)\s+(\d+)\s*(?:прием|введен)"), 0.0, cls._TIMES_PER),
            # word-number doses: в три приема
            (re.compile(r"(?:в|на)\s+(один|одну|два|две|три|четыре|пять)\s*(?:прием|введен)"), 0.0, cls._WORD_DOSES),
            # в сутки в N приема / за N введения в сутки
            (re.compile(r"в\s+сутки\s+в\s+(\d+)\s*прием"), 0.0, cls._TIMES_PER),
            (re.compile(r"за\s+(\d+)\s*введен\w*\s+в\s+сут"), 0.0, cls._TIMES_PER),
            # суточная доза разделенная на N приема / разделенных на N приема
            (re.compile(r"разделенн\w*\s+на\s+(\d+)\s*прием"), 0.0, cls._TIMES_PER),
            # N приема alone / 1 прием
            (re.compile(r"(\d+)\s*прием(?:а|ов)?\s*$"), 0.0, cls._TIMES_PER),
            # N раза alone (no period, implies per day)
            (re.compile(r"(\d+)\s*раза?\s*$"), 0.0, cls._TIMES_PER),
            # через день
            (re.compile(r"через\s+день"), 0.5, cls._STATIC),
            # ежедневно
            (re.compile(r"ежедн"), 1.0, cls._STATIC),
            # непрерывно / постоянно
            (re.compile(r"непрерывн|постоян"), 24.0, cls._STATIC),
            # однократно / двукратно / трехкратно
            (re.compile(r"однократн"), 1.0, cls._STATIC),
            (re.compile(r"двукратн"), 2.0, cls._STATIC),
            (re.compile(r"тр[её]хкратн"), 3.0, cls._STATIC),
            # капельно → usually once
            (re.compile(r"капельно"), 1.0, cls._STATIC),
            # как можно скорее → single dose
            (re.compile(r"как\s+можно\s+скоре"), 1.0, cls._STATIC),
            # разовая доза → single dose
            (re.compile(r"разов"), 1.0, cls._STATIC),
            # DEFAULTS (last): в сутки / в день / суточная доза → 1.0
            (re.compile(r"в\s+сутки"), 1.0, cls._STATIC),
            (re.compile(r"в\s+день"), 1.0, cls._STATIC),
            (re.compile(r"суточн"), 1.0, cls._STATIC),
        ]

    @classmethod
    def parse(cls, regimen: NormalizedRegimen, raw: dict) -> NormalizedRegimen:
        freq_raw = (raw.get("frequency", "") or "").strip().lower()
        if not freq_raw:
            regimen.frequency_per_day = None
            return regimen

        cls._init_patterns()

        for pattern, static_value, tag in cls._patterns:
            match = pattern.search(freq_raw)
            if not match:
                continue

            if tag == cls._STATIC:
                regimen.frequency_per_day = static_value
                return regimen

            if tag == cls._WORD_TIMES_PER:
                word = match.group(1)
                period = match.group(2)
                num = cls._WORD_TO_NUM.get(word, 1.0)
                divisor = cls._PERIOD_DIVISOR.get(period, 1.0)
                regimen.frequency_per_day = num / divisor
                return regimen

            if tag == cls._WORD_ADV:
                word = match.group(1)
                period = match.group(2)
                num = cls._WORD_TO_NUM.get(word, 1.0)
                divisor = cls._PERIOD_DIVISOR.get(period, 1.0)
                regimen.frequency_per_day = num / divisor
                return regimen

            if tag == cls._WORD_DOSES:
                word = match.group(1)
                regimen.frequency_per_day = cls._WORD_TO_NUM.get(word, 1.0)
                return regimen

            try:
                num = float(match.group(1))
            except (IndexError, ValueError, TypeError):
                continue

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
        return regimen
