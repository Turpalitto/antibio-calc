"""Round-trip tests for ReviewStore — the review workbench's persistence layer.

``storage.py`` is the most-imported untested module in the workbench (16 importers). Its
serialisation seam is the risky part: every enum is written as ``member.value`` and read
back as ``Enum(row[...])``. The two must agree for every member, and a mismatch raises
``ValueError`` on read rather than at write — so it surfaces only when a stored task is
loaded, potentially long after the row was written.

``TargetType`` is the one enum whose member names differ from its values
(``CLINICAL_REGIMEN`` -> ``"ClinicalRegimen"``), which makes it the case most likely to
break if anyone "normalises" the enum or hand-writes a SQL literal.

These tests drive the real ``ReviewStore`` against a temporary SQLite file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clinical_engine.review_workbench.models import (
    ClinicalReviewTask,
    PriorityBand,
    ReviewState,
    Severity,
    TargetType,
)
from clinical_engine.review_workbench.storage import ReviewStore


def _task(index: int, target_type: TargetType, severity: Severity, band: PriorityBand) -> ClinicalReviewTask:
    return ClinicalReviewTask(
        task_id=f"t{index}",
        task_key=f"k{index}",
        target_type=target_type,
        target_id=f"obj{index}",
        target_version=1,
        priority_score=10,
        priority=band,
        issue_type="TEST_ISSUE",
        severity=severity,
        safety_axes=("pediatric", "missing_unit"),
        source_references=({"guideline_id": "1269"},),
        provenance_references=({"field": "dose"},),
        reason_codes=("pediatric:35", "missing_unit:40"),
        created_at="2026-01-01T00:00:00+00:00",
    )


def test_every_enum_combination_survives_a_write_and_read(tmp_path: Path) -> None:
    """Все комбинации перечислений переживают запись и чтение без расхождений."""
    combinations = list(
        (target_type, severity, band)
        for target_type in TargetType
        for severity in Severity
        for band in PriorityBand
    )
    assert len(combinations) == 72, len(combinations)

    store_path = tmp_path / "roundtrip.sqlite"
    with ReviewStore(store_path) as store:
        for index, (target_type, severity, band) in enumerate(combinations, start=1):
            task = _task(index, target_type, severity, band)
            store.add_target(task.target_type, task.target_id, task.target_version, {"n": index}, [], [])
            assert store.add_task(task) is True, index

        for index, (target_type, severity, band) in enumerate(combinations, start=1):
            loaded = store.get_task(f"t{index}")
            assert loaded.target_type is target_type, (index, loaded.target_type)
            assert loaded.severity is severity, (index, loaded.severity)
            assert loaded.priority is band, (index, loaded.priority)
            assert loaded.lifecycle_state is ReviewState.PENDING, loaded.lifecycle_state


def test_collection_fields_survive_the_round_trip(tmp_path: Path) -> None:
    """Кортежи и вложенные словари читаются обратно тем же содержимым."""
    store_path = tmp_path / "collections.sqlite"
    with ReviewStore(store_path) as store:
        task = _task(1, TargetType.CLINICAL_REGIMEN, Severity.HIGH, PriorityBand.HIGH)
        store.add_target(task.target_type, task.target_id, 1, {"n": 1}, [], [])
        store.add_task(task)
        loaded = store.get_task("t1")

    assert tuple(loaded.safety_axes) == ("pediatric", "missing_unit")
    assert tuple(loaded.reason_codes) == ("pediatric:35", "missing_unit:40")
    assert tuple(loaded.source_references) == ({"guideline_id": "1269"},)
    assert tuple(loaded.provenance_references) == ({"field": "dose"},)


def test_target_type_values_differ_from_member_names(tmp_path: Path) -> None:
    """Предусловие: у TargetType имя участника не равно значению.

    Если кто-нибудь «нормализует» перечисление или впишет значение строкой в SQL,
    этот тест напомнит, что хранение идёт по значению.
    """
    assert TargetType.CLINICAL_REGIMEN.value == "ClinicalRegimen"
    assert TargetType.CLINICAL_REGIMEN.name != TargetType.CLINICAL_REGIMEN.value

    store_path = tmp_path / "values.sqlite"
    with ReviewStore(store_path) as store:
        task = _task(1, TargetType.CLINICAL_REGIMEN, Severity.HIGH, PriorityBand.HIGH)
        store.add_target(task.target_type, task.target_id, 1, {}, [], [])
        store.add_task(task)
        raw = store.connection.execute(
            "SELECT target_type FROM review_tasks WHERE task_id='t1'"
        ).fetchone()
    assert raw["target_type"] == "ClinicalRegimen", raw["target_type"]


def test_other_enums_use_the_member_name_as_the_value() -> None:
    """Остальные перечисления хранятся именем — и это закреплено."""
    for enum in (Severity, PriorityBand, ReviewState):
        mismatched = [(m.name, m.value) for m in enum if m.name != m.value]
        assert mismatched == [], f"{enum.__name__}: {mismatched}"


def test_filtering_by_enum_uses_the_stored_value(tmp_path: Path) -> None:
    """Фильтры list_tasks принимают перечисление и сравнивают с сохранённым значением."""
    store_path = tmp_path / "filter.sqlite"
    with ReviewStore(store_path) as store:
        for index, target_type in enumerate(TargetType, start=1):
            task = _task(index, target_type, Severity.HIGH, PriorityBand.HIGH)
            store.add_target(task.target_type, task.target_id, 1, {}, [], [])
            store.add_task(task)

        for target_type in TargetType:
            found = store.list_tasks(target_type=target_type, limit=100)
            assert len(found) == 1, (target_type, len(found))
            assert found[0].target_type is target_type

        assert len(store.list_tasks(limit=100)) == len(list(TargetType))


def test_readding_the_same_task_is_refused_not_duplicated(tmp_path: Path) -> None:
    """Повторное добавление той же задачи не создаёт вторую запись."""
    store_path = tmp_path / "dedup.sqlite"
    with ReviewStore(store_path) as store:
        task = _task(1, TargetType.CLINICAL_REGIMEN, Severity.HIGH, PriorityBand.HIGH)
        store.add_target(task.target_type, task.target_id, 1, {}, [], [])
        assert store.add_task(task) is True
        assert store.add_task(task) is False
        assert len(store.list_tasks(limit=100)) == 1


def test_a_task_cannot_reference_a_missing_target(tmp_path: Path) -> None:
    """Внешний ключ обязывает регистрировать цель до задачи.

    Это не формальность: без цели пакет ревью нечем наполнить.
    """
    import sqlite3

    store_path = tmp_path / "fk.sqlite"
    with ReviewStore(store_path) as store:
        task = _task(1, TargetType.CLINICAL_REGIMEN, Severity.HIGH, PriorityBand.HIGH)
        with pytest.raises(sqlite3.IntegrityError):
            store.add_task(task)
