#!/usr/bin/env python
"""Build-time derivation of regimen semantics for the calculator database.

Two problems this solves without touching clinical content:

* **485 of 638 regimens have no ``regimen_label``.** The HTML calculator
  silently falls back to an inline expression
  (``dose_mg_kg_day + ' мг/кг' + freq + ' р/д'``), so the same regimen renders
  differently in the chip list, in the personal-mode trace and in a printed
  prescription. ``regimen_label`` is also the human-facing key of
  ``calculator_binding`` (``resolve_binding``), which cannot select a regimen
  that has none.
* **360 of 638 ``duration_days`` values are free text.** The calculator prints
  them verbatim, which is correct, but nothing downstream can tell
  «7-10 дней» from «однократно» from «пожизненно».

Both derivations are **pure functions of fields that already exist**. Nothing is
invented: when the text does not state a duration, ``kind`` is ``NOT_FIXED`` and
no numbers are produced. The original ``duration_days`` string is always kept
verbatim (ARCHITECTURAL_INVARIANTS.md INV-09 — never discard original wording).

Applied by ``db/build_db.py``. Never modifies a field that is already set.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0.0"

# Duration classes. Machine-readable; the physician-facing string stays as-is.
FIXED = "FIXED"
RANGE = "RANGE"
SINGLE_DOSE = "SINGLE_DOSE"
AT_LEAST = "AT_LEAST"
AT_MOST = "AT_MOST"
CONDITION_DEPENDENT = "CONDITION_DEPENDENT"
LIFELONG = "LIFELONG"
NOT_FIXED = "NOT_FIXED"
# The source explicitly says the duration is not stated — different from a
# sentence we merely failed to parse.
NOT_STATED = "NOT_STATED"
MISSING = "MISSING"

# An infusion/administration-rate constraint ("введение не менее 30 мин") is NOT
# a course duration and must not be confused with one.
INFUSION_CONSTRAINT = "INFUSION_CONSTRAINT"
# Intermittent schedules ("3 дня подряд в неделю") are not a total day count.
INTERMITTENT = "INTERMITTENT"
# A stated number of administrations ("3 приема"), not a duration.
DOSE_COUNT = "DOSE_COUNT"

DURATION_KINDS = (
    FIXED,
    RANGE,
    SINGLE_DOSE,
    AT_LEAST,
    AT_MOST,
    DOSE_COUNT,
    INTERMITTENT,
    INFUSION_CONSTRAINT,
    CONDITION_DEPENDENT,
    LIFELONG,
    NOT_FIXED,
    NOT_STATED,
    MISSING,
)

_NUM = r"\d+(?:[.,]\d+)?"
_DAY_WORDS = r"(?:дн|сут|сутки|суток|день|дня|дней)"
_MONTH_WORDS = r"(?:мес|месяц|месяца|месяцев)"
_WEEK_WORDS = r"(?:нед|неделя|недели|недель)"
_HOUR_WORDS = r"(?:час|часа|часов|ч)"
_MIN_WORDS = r"(?:мин|минут|минуты|минуту)"

_RE_EXACT_NUMBER = re.compile(rf"^\s*({_NUM})\s*{_DAY_WORDS}?\s*$", re.IGNORECASE)
_RE_EXACT_RANGE = re.compile(rf"^\s*({_NUM})\s*[-–—]\s*({_NUM})\s*{_DAY_WORDS}?\b", re.IGNORECASE)
_RE_EXACT_MONTH = re.compile(rf"^\s*({_NUM})\s*{_MONTH_WORDS}\w*\s*$", re.IGNORECASE)
_RE_EXACT_WEEK = re.compile(rf"^\s*({_NUM})\s*{_WEEK_WORDS}\w*\s*$", re.IGNORECASE)
_RE_EXACT_HOUR = re.compile(rf"^\s*({_NUM})\s*{_HOUR_WORDS}\w*\s*$", re.IGNORECASE)

# "курс 7 дней", "курс составляет 7-10 суток", "курс не менее 10 дней"
_RE_COURSE = re.compile(
    rf"курс\w*\s*(?:составляет\s*)?(?:не\s+менее\s*)?({_NUM})\s*(?:[-–—]\s*({_NUM})\s*)?{_DAY_WORDS}",
    re.IGNORECASE,
)
_RE_LEADING_RANGE = re.compile(rf"({_NUM})\s*[-–—]\s*({_NUM})\s*{_DAY_WORDS}", re.IGNORECASE)
_RE_LEADING_NUMBER_DAY = re.compile(rf"({_NUM})\s*{_DAY_WORDS}\b", re.IGNORECASE)
_RE_LEADING_MONTH = re.compile(rf"({_NUM})\s*{_MONTH_WORDS}\w*", re.IGNORECASE)
_RE_LEADING_WEEK = re.compile(rf"({_NUM})\s*{_WEEK_WORDS}\w*", re.IGNORECASE)
_RE_AT_LEAST = re.compile(rf"не\s+менее(?:,)?\s*(?:чем\s*)?(?:за\s*)?({_NUM})\s*({_DAY_WORDS}|{_MONTH_WORDS})", re.IGNORECASE)
_RE_AT_MOST = re.compile(
    rf"(?:не\s+более|до)\s*({_NUM})\s*({_HOUR_WORDS}|{_DAY_WORDS}|{_MONTH_WORDS})", re.IGNORECASE
)
_RE_INFUSION = re.compile(rf"(?:введени\w*|инфузи\w*|капельно)[^.;]*?({_NUM})\s*({_MIN_WORDS}|{_HOUR_WORDS})", re.IGNORECASE)
_RE_INFUSION_RANGE = re.compile(rf"(?:введени\w*|инфузи\w*|капельно)[^.;]*?({_NUM})\s*[-–—]\s*({_NUM})\s*({_MIN_WORDS}|{_HOUR_WORDS})", re.IGNORECASE)
_RE_DOSE_COUNT = re.compile(rf"^\s*({_NUM})\s*(?:прием|приём|доз)", re.IGNORECASE)
_RE_WITHIN = re.compile(rf"в\s+течени\w+\s+({_NUM})\s*({_HOUR_WORDS}|{_DAY_WORDS})", re.IGNORECASE)

_SINGLE_DOSE_WORDS = ("однократно", "однократн", "single dose", "одна доза", "одну дозу", "одной дозой", "одна предоперационная доза")
_LIFELONG_WORDS = ("пожизненно", "пожизненн")
_CONDITION_WORDS = (
    "до момента",
    "до санации",
    "на протяжении",
    "всего периода",
    "индивидуально",
    "по клинической",
    "до разрешения",
    "до нормализации",
    "в течение всего",
    "до полного",
    "длительно",
    "длительный курс",
    "вплоть до",
    "по ситуации",
    "до повышения",
    "до появления",
    "до достижения",
    "до восстановления",
)
_NOT_STATED_WORDS = ("не указано", "не определено", "не регламентировано", "не определена", "не приведено")
_INTERMITTENT_WORDS = ("в неделю", "в нед", "через день", "раз в неделю", "подряд в неделю", "еженедельно")
_HOURS_WORDS = ("час", "ч")


def _unit_of(word: str) -> str:
    """Map a matched Russian quantity word onto a unit name."""
    lowered = word.lower()
    if "мин" in lowered:
        return "minute"
    if "час" in lowered or lowered.startswith("ч"):
        return "hour"
    if "мес" in lowered:
        return "month"
    if "нед" in lowered:
        return "week"
    return "day"


def _to_float(value: str) -> float:
    return float(value.replace(",", "."))


def _fmt(value: float) -> str:
    """``5.0`` -> ``5``, ``7.5`` -> ``7.5``."""
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def _result(kind: str, value_min=None, value_max=None, unit=None, basis=None) -> dict[str, Any]:
    """Uniform shape. Numbers are always expressed in ``unit`` — never silently
    converted to days, and never invented when the source states none."""
    return {"kind": kind, "value_min": value_min, "value_max": value_max, "unit": unit, "basis": basis}


_RE_EXACT_MONTH = re.compile(rf"^\s*({_NUM})\s*(мес|месяц|месяца|месяцев)\w*\s*$", re.IGNORECASE)
_RE_LEADING_MONTH = re.compile(rf"({_NUM})\s*(мес|месяц|месяца|месяцев)\w*", re.IGNORECASE)


def parse_duration(raw: Any) -> dict[str, Any]:
    """Classify a ``duration_days`` value. Never invents a number.

    Returns ``{kind, value_min, value_max, unit, basis}``. ``unit`` states what
    the numbers mean (``day`` / ``month`` / ``week`` / ``hour`` / ``minute`` /
    ``administration``); values are ``None`` when the source states no quantity.
    ``basis`` quotes the fragment the classification came from, so a physician
    can re-check it at a glance. The original string is always preserved
    verbatim in ``duration_days`` (INV-09).
    """
    if raw is None:
        return _result(MISSING)

    if isinstance(raw, (int, float)):
        value = float(raw)
        return _result(FIXED, value, value, "day", _fmt(value))

    text = str(raw).strip()
    if not text:
        return _result(MISSING)
    lowered = text.lower()

    # 1. Plain numeric forms.
    exact_number = _RE_EXACT_NUMBER.match(text)
    if exact_number:
        value = _to_float(exact_number.group(1))
        return _result(FIXED, value, value, "day", text)
    exact_range = _RE_EXACT_RANGE.match(text)
    if exact_range:
        return _result(RANGE, _to_float(exact_range.group(1)), _to_float(exact_range.group(2)), "day",
                       exact_range.group(0).strip())
    exact_month = _RE_EXACT_MONTH.match(text)
    if exact_month:
        value = _to_float(exact_month.group(1))
        return _result(FIXED, value, value, "month", text)
    exact_week = _RE_EXACT_WEEK.match(text)
    if exact_week:
        value = _to_float(exact_week.group(1))
        return _result(FIXED, value, value, "week", text)
    exact_hour = _RE_EXACT_HOUR.match(text)
    if exact_hour:
        value = _to_float(exact_hour.group(1))
        return _result(AT_MOST, None, value, "hour", text)

    # 2. An explicit "курс N дней" always wins over an infusion-rate clause that
    #    happens to sit in the same sentence.
    course = _RE_COURSE.search(text)
    if course:
        low = _to_float(course.group(1))
        high = _to_float(course.group(2)) if course.group(2) else low
        kind = RANGE if course.group(2) else FIXED
        return _result(kind, low, high, "day", course.group(0).strip())

    # 3. Single-dose / lifelong statements.
    if any(word in lowered for word in _SINGLE_DOSE_WORDS):
        # Одна доза — это 1 введение, а не «0 дней»: 0 заставил бы любой
        # downstream-расчёт (приёмов = частота × дней) молча обнулиться.
        return _result(SINGLE_DOSE, 1.0, 1.0, "administration", "однократно")
    if any(word in lowered for word in _LIFELONG_WORDS):
        return _result(LIFELONG, basis="пожизненно")

    # 4. Counted administrations, not a duration.
    dose_count = _RE_DOSE_COUNT.match(text)
    if dose_count:
        value = _to_float(dose_count.group(1))
        return _result(DOSE_COUNT, value, value, "administration", dose_count.group(0).strip())

    # 5. Intermittent schedules ("3 дня подряд в неделю").
    if any(word in lowered for word in _INTERMITTENT_WORDS):
        return _result(INTERMITTENT, basis=text)

    # 6. Infusion / administration-rate constraint — NOT a course duration.
    infusion_range = _RE_INFUSION_RANGE.search(text)
    if infusion_range:
        unit = "minute" if "мин" in infusion_range.group(3).lower() else "hour"
        return _result(INFUSION_CONSTRAINT, _to_float(infusion_range.group(1)), _to_float(infusion_range.group(2)),
                       unit, infusion_range.group(0).strip())
    infusion = _RE_INFUSION.search(text)
    if infusion:
        unit = "minute" if "мин" in infusion.group(2).lower() else "hour"
        value = _to_float(infusion.group(1))
        return _result(INFUSION_CONSTRAINT, value, value, unit, infusion.group(0).strip())

    # 7. Bounds.
    at_least = _RE_AT_LEAST.search(text)
    if at_least:
        unit = "month" if "мес" in at_least.group(2).lower() else "day"
        return _result(AT_LEAST, _to_float(at_least.group(1)), None, unit, at_least.group(0).strip())
    within = _RE_WITHIN.search(text)
    if within:
        unit = _unit_of(within.group(2))
        value = _to_float(within.group(1))
        return _result(AT_MOST, None, value, unit, within.group(0).strip())
    at_most = _RE_AT_MOST.search(text)
    if at_most:
        unit = _unit_of(at_most.group(2))
        return _result(AT_MOST, None, _to_float(at_most.group(1)), unit, at_most.group(0).strip())

    # 8. Explicitly not stated, then condition-dependent wording.
    if any(word in lowered for word in _NOT_STATED_WORDS):
        return _result(NOT_STATED, basis=text)
    if any(word in lowered for word in _CONDITION_WORDS):
        return _result(CONDITION_DEPENDENT, basis=text)

    # 9. Leading quantities inside a longer sentence.
    leading_range = _RE_LEADING_RANGE.search(text)
    if leading_range:
        return _result(RANGE, _to_float(leading_range.group(1)), _to_float(leading_range.group(2)), "day",
                       leading_range.group(0).strip())
    leading_number = _RE_LEADING_NUMBER_DAY.search(text)
    if leading_number:
        value = _to_float(leading_number.group(1))
        return _result(FIXED, value, value, "day", leading_number.group(0).strip())
    leading_month = _RE_LEADING_MONTH.search(text)
    if leading_month:
        value = _to_float(leading_month.group(1))
        return _result(FIXED, value, value, "month", leading_month.group(0).strip())
    leading_week = _RE_LEADING_WEEK.search(text)
    if leading_week:
        value = _to_float(leading_week.group(1))
        return _result(FIXED, value, value, "week", leading_week.group(0).strip())

    return _result(NOT_FIXED, basis=text)


def build_label(regimen: dict[str, Any], parsed: dict[str, Any]) -> str | None:
    """Compose a regimen label from dose + frequency + duration.

    Dose precedence mirrors ``computeDose()`` in the calculator: the single dose
    is the source of truth (КР text usually states a per-administration dose),
    then mg/kg/day, then a fixed daily total.
    """
    single = regimen.get("single_dose_mg")
    per_kg = regimen.get("dose_mg_kg_day")
    fixed = regimen.get("dose_mg_day_fixed")
    freq = regimen.get("freq_per_day")

    if isinstance(single, (int, float)):
        dose_part = f"{_fmt(float(single))} мг"
    elif isinstance(per_kg, (int, float)):
        dose_part = f"{_fmt(float(per_kg))} мг/кг/сут"
    elif isinstance(fixed, (int, float)):
        dose_part = f"{_fmt(float(fixed))} мг/сут"
    else:
        return None

    if not isinstance(freq, (int, float)) or freq <= 0:
        return dose_part

    if parsed["kind"] == SINGLE_DOSE and freq == 1:
        return f"{dose_part} однократно"
    freq_part = f"{_fmt(float(freq))} р/д"

    duration_part = ""
    if parsed.get("unit") == "day":
        low, high = parsed.get("value_min"), parsed.get("value_max")
        if parsed["kind"] == FIXED and low is not None:
            duration_part = f" {_fmt(float(low))} дн"
        elif parsed["kind"] == RANGE and low is not None and high is not None:
            duration_part = f" {_fmt(float(low))}-{_fmt(float(high))} дн"

    return f"{dose_part} {freq_part}{duration_part}"


def annotate_regimens(db: dict[str, Any]) -> dict[str, int]:
    """Add ``duration_parsed`` (always) and ``regimen_label`` (when missing).

    Labels are de-duplicated **within one drug entry**, because
    ``calculator_binding.resolve_binding`` requires ``regimen_label`` to select
    exactly one regimen. Existing labels are never rewritten — but they are
    counted when checking for collisions.
    """
    stats = {"regimens": 0, "labels_added": 0, "labels_existing": 0, "durations_parsed": 0, "collisions_renamed": 0}
    kind_counts: dict[str, int] = {}

    for disease in db.get("recommendations", []):
        for scenario in disease.get("scenarios") or []:
            for line in scenario.get("lines") or []:
                for drug in line.get("drugs") or []:
                    used: set[str] = set()
                    pending: list[tuple[dict[str, Any], int]] = []
                    for index, regimen in enumerate(drug.get("regimens") or []):
                        stats["regimens"] += 1
                        parsed = parse_duration(regimen.get("duration_days"))
                        regimen["duration_parsed"] = parsed
                        stats["durations_parsed"] += 1
                        kind_counts[parsed["kind"]] = kind_counts.get(parsed["kind"], 0) + 1

                        existing = regimen.get("regimen_label")
                        if isinstance(existing, str) and existing.strip():
                            stats["labels_existing"] += 1
                            used.add(existing)
                            continue
                        pending.append((regimen, index))

                    for regimen, _index in pending:
                        parsed = regimen["duration_parsed"]
                        label = build_label(regimen, parsed)
                        if label is None:
                            continue
                        if label in used:
                            suffix = 2
                            while f"{label} · вариант {suffix}" in used:
                                suffix += 1
                            label = f"{label} · вариант {suffix}"
                            stats["collisions_renamed"] += 1
                        used.add(label)
                        regimen["regimen_label"] = label
                        stats["labels_added"] += 1

    stats["duration_kinds"] = dict(sorted(kind_counts.items()))
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Derive regimen labels + duration semantics (in place)")
    parser.add_argument("--db", default="db/antibio_db.json", type=Path)
    args = parser.parse_args(argv)

    db = json.loads(args.db.read_text(encoding="utf-8-sig"))
    stats = annotate_regimens(db)
    args.db.write_text(json.dumps(db, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
