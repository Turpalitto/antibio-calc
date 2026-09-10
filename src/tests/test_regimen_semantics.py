"""Разбор длительности курса и сборка человекочитаемой метки режима.

``duration_days`` в БД калькулятора — это дословный текст из клинических
рекомендаций, и он смешивает три разных смысла: длительность курса
(«7-10 дней»), режим введения («введение не менее 60 мин») и количество
приёмов («3 приёма»). Раньше всё это отдавалось в UI как есть, а рядом
механически дописывалось «дней». Эти тесты фиксируют, что смыслы разделены.
"""

from __future__ import annotations

import json

import pytest

from db.regimen_semantics import (
    AT_LEAST,
    AT_MOST,
    CONDITION_DEPENDENT,
    DOSE_COUNT,
    FIXED,
    INFUSION_CONSTRAINT,
    INTERMITTENT,
    LIFELONG,
    MISSING,
    NOT_FIXED,
    NOT_STATED,
    RANGE,
    SINGLE_DOSE,
    annotate_regimens,
    build_label,
    parse_duration,
)


@pytest.mark.parametrize(
    ("raw", "kind", "value_min", "value_max", "unit"),
    [
        (None, MISSING, None, None, None),
        ("", MISSING, None, None, None),
        (7, FIXED, 7.0, 7.0, "day"),
        (7.0, FIXED, 7.0, 7.0, "day"),
        ("10-14", RANGE, 10.0, 14.0, "day"),
        ("10—14", RANGE, 10.0, 14.0, "day"),
        ("7-10 дней", RANGE, 7.0, 10.0, "day"),
        ("7-10 дней (до нормализации температуры)", RANGE, 7.0, 10.0, "day"),
        ("7 дней", FIXED, 7.0, 7.0, "day"),
        ("5 сут", FIXED, 5.0, 5.0, "day"),
        ("3 суток", FIXED, 3.0, 3.0, "day"),
        ("3 недели", FIXED, 3.0, 3.0, "week"),
        ("3 месяца", FIXED, 3.0, 3.0, "month"),
        ("14 дн", FIXED, 14.0, 14.0, "day"),
        # Одна доза — 1 введение, а не «0 дней»: ноль обнулил бы любой
        # downstream-расчёт числа приёмов.
        ("однократно", SINGLE_DOSE, 1.0, 1.0, "administration"),
        ("Однократно.", SINGLE_DOSE, 1.0, 1.0, "administration"),
        ("одна предоперационная доза", SINGLE_DOSE, 1.0, 1.0, "administration"),
        ("не менее 7 дней", AT_LEAST, 7.0, None, "day"),
        ("не менее 3 месяцев", AT_LEAST, 3.0, None, "month"),
        ("до 14 дней", AT_MOST, None, 14.0, "day"),
        ("не более 24 часов после операции", AT_MOST, None, 24.0, "hour"),
        ("до 6 месяцев или до появления побочных эффектов", AT_MOST, None, 6.0, "month"),
        ("3 приема", DOSE_COUNT, 3.0, 3.0, "administration"),
        # Интермиттирующая схема не даёт суммарной длительности — чисел нет.
        ("3 дня подряд в неделю", INTERMITTENT, None, None, None),
        ("пожизненно", LIFELONG, None, None, None),
        ("пожизненная терапия", LIFELONG, None, None, None),
        ("не указано", NOT_STATED, None, None, None),
        ("до нормализации температуры", CONDITION_DEPENDENT, None, None, None),
        ("до полного рассасывания инфильтрата", CONDITION_DEPENDENT, None, None, None),
        ("по ситуации", CONDITION_DEPENDENT, None, None, None),
        ("периоперационная антибиотикопрофилактика", NOT_FIXED, None, None, None),
    ],
)
def test_parse_duration(
    raw: object, kind: str, value_min: float | None, value_max: float | None, unit: str | None
) -> None:
    parsed = parse_duration(raw)

    assert parsed["kind"] == kind
    assert parsed["value_min"] == value_min
    assert parsed["value_max"] == value_max
    assert parsed["unit"] == unit


def test_parse_duration_keeps_the_matched_fragment_as_basis() -> None:
    """Врач должен видеть, по какому фрагменту принята классификация."""

    assert parse_duration("7-10 дней (до нормализации температуры)")["basis"] == "7-10 дней"
    assert parse_duration("до 14 дней")["basis"] == "до 14 дн"
    assert parse_duration(None)["basis"] is None


def test_course_wins_over_infusion_constraint_in_one_sentence() -> None:
    """«введение … 1-2 часа; курс 7 дней» — это 7 дней, а не инфузия."""

    parsed = parse_duration("введение в течение 1-2 часов; курс 7 дней (до 10 дней)")

    assert parsed["kind"] == FIXED
    assert parsed["value_min"] == 7.0
    assert parsed["unit"] == "day"


@pytest.mark.parametrize(
    ("raw", "kind", "unit"),
    [
        ("введение не менее 30 мин", INFUSION_CONSTRAINT, "minute"),
        ("медленная инфузия не менее 60 минут", INFUSION_CONSTRAINT, "minute"),
        ("инфузия 1-2 часа", INFUSION_CONSTRAINT, "hour"),
        ("введение в течение 1-2 часов", INFUSION_CONSTRAINT, "hour"),
    ],
)
def test_administration_rate_is_not_a_course_duration(raw: str, kind: str, unit: str) -> None:
    """Скорость введения — не длительность курса; путаница здесь клинически опасна."""

    parsed = parse_duration(raw)

    assert parsed["kind"] == kind
    assert parsed["unit"] == unit


def test_pre_procedure_timing_is_not_an_infusion_constraint() -> None:
    """«за 30-60 минут до процедуры» — про время, а не про скорость инфузии."""

    parsed = parse_duration("за 30-60 минут до процедуры")

    assert parsed["kind"] == NOT_FIXED
    assert parsed["value_min"] is None


@pytest.mark.parametrize(
    ("regimen", "expected"),
    [
        ({"dose_mg_kg_day": 45, "freq_per_day": 3, "duration_days": "7-10"}, "45 мг/кг/сут 3 р/д 7-10 дн"),
        ({"dose_mg_day_fixed": 2000, "freq_per_day": 4}, "2000 мг/сут 4 р/д"),
        ({"single_dose_mg": 500, "freq_per_day": 1, "duration_days": "однократно"}, "500 мг однократно"),
        ({"single_dose_mg": 500, "freq_per_day": 4, "duration_days": "7-10 дней"}, "500 мг 4 р/д 7-10 дн"),
        ({"dose_mg_day_fixed": 1200, "freq_per_day": 2, "duration_days": "3 месяца"}, "1200 мг/сут 2 р/д"),
        ({"dose_mg_day_fixed": 600, "freq_per_day": 2, "duration_days": "не менее 7 дней"}, "600 мг/сут 2 р/д"),
        ({"dose_mg_day_fixed": 600, "freq_per_day": 2, "duration_days": "до 14 дней"}, "600 мг/сут 2 р/д"),
        ({"dose_mg_day_fixed": 500, "freq_per_day": 1, "duration_days": "пожизненно"}, "500 мг/сут 1 р/д"),
        # Суточная доза + «однократно» читается однозначно; «1 р/д» было бы шумом.
        ({"dose_mg_day_fixed": 500, "freq_per_day": 1, "duration_days": "однократно"}, "500 мг/сут однократно"),
        (
            {"dose_mg_day_fixed": 500, "freq_per_day": 1, "duration_days": "введение не менее 60 мин"},
            "500 мг/сут 1 р/д",
        ),
        # Без дозы метку собрать нельзя — лучше None, чем выдуманная строка.
        ({}, None),
        ({"freq_per_day": 3}, None),
    ],
)
def test_build_label(regimen: dict, expected: str | None) -> None:
    assert build_label(regimen, parse_duration(regimen.get("duration_days"))) == expected


def test_build_label_prefers_single_dose_like_the_calculator() -> None:
    """Приоритет дозы повторяет computeDose() в калькуляторе."""

    regimen = {"single_dose_mg": 500, "dose_mg_kg_day": 45, "freq_per_day": 3}

    assert build_label(regimen, parse_duration(None)) == "500 мг 3 р/д"


def test_annotate_never_overwrites_a_reviewed_label() -> None:
    db = {
        "recommendations": [
            {
                "id": "x",
                "scenarios": [
                    {
                        "lines": [
                            {
                                "drugs": [
                                    {
                                        "regimens": [
                                            {
                                                "regimen_label": "500 мг 3 р/д 7 дн (проверено)",
                                                "dose_mg_day_fixed": 1500,
                                                "freq_per_day": 3,
                                                "duration_days": "7",
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }

    stats = annotate_regimens(db)

    regimen = db["recommendations"][0]["scenarios"][0]["lines"][0]["drugs"][0]["regimens"][0]
    assert regimen["regimen_label"] == "500 мг 3 р/д 7 дн (проверено)"
    assert stats["labels_added"] == 0
    assert stats["labels_existing"] == 1


def test_annotate_disambiguates_duplicate_labels_within_one_drug() -> None:
    """Метка обязана быть уникальной в пределах препарата: по ней резолвится биндинг."""

    db = {
        "recommendations": [
            {
                "id": "x",
                "scenarios": [
                    {
                        "lines": [
                            {
                                "drugs": [
                                    {
                                        "regimens": [
                                            {"dose_mg_day_fixed": 1500, "freq_per_day": 3, "duration_days": "7"},
                                            {"dose_mg_day_fixed": 1500, "freq_per_day": 3, "duration_days": "7 сут"},
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }

    stats = annotate_regimens(db)

    labels = [r["regimen_label"] for r in db["recommendations"][0]["scenarios"][0]["lines"][0]["drugs"][0]["regimens"]]
    assert len(set(labels)) == 2
    assert labels[0] == "1500 мг/сут 3 р/д 7 дн"
    assert labels[1] == "1500 мг/сут 3 р/д 7 дн · вариант 2"
    assert stats["collisions_renamed"] == 1


def test_annotate_leaves_doseless_regimen_without_label() -> None:
    db = {
        "recommendations": [
            {"id": "x", "scenarios": [{"lines": [{"drugs": [{"regimens": [{"freq_per_day": 3, "duration_days": "7"}]}]}]}]}
        ]
    }

    stats = annotate_regimens(db)

    regimen = db["recommendations"][0]["scenarios"][0]["lines"][0]["drugs"][0]["regimens"][0]
    assert "regimen_label" not in regimen
    assert stats["labels_added"] == 0
    # duration_parsed проставляется даже там, где метку собрать нельзя.
    assert regimen["duration_parsed"]["kind"] == FIXED


def test_annotate_tolerates_malformed_shapes() -> None:
    db = {
        "recommendations": [
            {"id": "x"},
            {"id": "y", "scenarios": None},
            {"id": "z", "scenarios": [{"lines": [{"drugs": None}]}]},
        ]
    }

    stats = annotate_regimens(db)

    assert stats["regimens"] == 0


def test_annotate_reports_kind_histogram() -> None:
    db = {
        "recommendations": [
            {
                "id": "x",
                "scenarios": [
                    {
                        "lines": [
                            {
                                "drugs": [
                                    {
                                        "regimens": [
                                            {"dose_mg_day_fixed": 1500, "freq_per_day": 3, "duration_days": "7"},
                                            {"dose_mg_day_fixed": 1500, "freq_per_day": 3, "duration_days": None},
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }

    stats = annotate_regimens(db)

    assert stats["duration_kinds"] == {FIXED: 1, MISSING: 1}
    assert stats["durations_parsed"] == 2


def test_annotate_is_idempotent() -> None:
    db = {
        "recommendations": [
            {
                "id": "x",
                "scenarios": [
                    {
                        "lines": [
                            {
                                "drugs": [
                                    {
                                        "regimens": [
                                            {
                                                "dose_mg_day_fixed": 1500,
                                                "freq_per_day": 3,
                                                "duration_days": "7-10 дней",
                                            },
                                            {"dose_mg_day_fixed": 1500, "freq_per_day": 3, "duration_days": "7"},
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }

    annotate_regimens(db)
    first = json.loads(json.dumps(db))
    annotate_regimens(db)

    assert db == first
