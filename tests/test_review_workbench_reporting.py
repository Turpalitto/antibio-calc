"""Tests for the review-workbench queue reporting and workload projection.

``reporting.py`` had no test coverage. Two of its lookups are by key and therefore fail
loudly only at runtime, on data rather than at import:

* ``PLANNING_MINUTES[task.priority.value]`` — a new ``PriorityBand`` member without a
  planning figure would raise ``KeyError`` part-way through the aggregation;
* ``store.metrics()["average_review_time_seconds"]`` — a renamed metric key would raise
  ``KeyError`` after the whole queue had been walked.

The projection also carries a deliberate honesty label,
``PLANNING_ESTIMATE_NOT_BENCHMARK``, because the minutes-per-priority figures are planning
assumptions rather than measurements. That label is the thing that keeps the number from
being quoted as observed data, so it is pinned here too.

These tests drive the real ``ReviewStore`` and the real ``summarize_queue``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clinical_engine.review_workbench.models import (
    ClinicalReviewTask,
    PriorityBand,
    Severity,
    TargetType,
)
from clinical_engine.review_workbench.reporting import PLANNING_MINUTES, summarize_queue
from clinical_engine.review_workbench.storage import ReviewStore


def _build_store(path: Path) -> ReviewStore:
    store = ReviewStore(path)
    rows = [
        # target_type, severity, band, axes, guideline_id, payload
        (TargetType.CLINICAL_REGIMEN, Severity.HIGH, PriorityBand.HIGH,
         ("pediatric", "missing_unit"), "g1", {"diagnosis": "отит"}),
        (TargetType.CLINICAL_REGIMEN, Severity.MEDIUM, PriorityBand.MEDIUM,
         ("pediatric",), "g1", {"indication": "синусит"}),
        (TargetType.THERAPEUTIC_OPTION, Severity.LOW, PriorityBand.LOW,
         (), "", {"diagnosis_id": "H66"}),
    ]
    for index, (target_type, severity, band, axes, guideline, payload) in enumerate(rows, start=1):
        store.add_target(
            target_type, f"obj{index}", 1, payload, [],
            [{"guideline_id": guideline}] if guideline else [],
        )
        store.add_task(ClinicalReviewTask(
            task_id=f"t{index}", task_key=f"k{index}", target_type=target_type,
            target_id=f"obj{index}", target_version=1, priority_score=10, priority=band,
            issue_type="TEST_ISSUE", severity=severity, safety_axes=axes,
            source_references=({"guideline_id": guideline},) if guideline else (),
            provenance_references=(), reason_codes=(),
            created_at="2026-01-01T00:00:00+00:00",
        ))
    return store


@pytest.fixture()
def report(tmp_path: Path) -> dict:
    with _build_store(tmp_path / "reporting.sqlite") as store:
        return summarize_queue(store)


# ── обращения по ключу: полнота перечислений ─────────────────────────────────


def test_planning_minutes_covers_every_priority_band() -> None:
    """Новое значение PriorityBand без цифры планирования дало бы KeyError."""
    covered = {band.value for band in PriorityBand}
    assert set(PLANNING_MINUTES) == covered, (
        sorted(set(PLANNING_MINUTES) ^ covered)
    )


def test_planning_minutes_are_positive_and_ordered_by_priority() -> None:
    """Высокий приоритет планируется дольше низкого — иначе порядок бессмыслен."""
    assert PLANNING_MINUTES["HIGH"] > PLANNING_MINUTES["MEDIUM"] > PLANNING_MINUTES["LOW"] > 0


def test_the_metrics_key_the_report_reads_exists(tmp_path: Path) -> None:
    """``store.metrics()["average_review_time_seconds"]`` — обращение по ключу."""
    with _build_store(tmp_path / "metrics.sqlite") as store:
        metrics = store.metrics()
    assert "average_review_time_seconds" in metrics, sorted(metrics)


# ── агрегация ────────────────────────────────────────────────────────────────


def test_severity_counts_are_exact(report: dict) -> None:
    assert report["measured"]["by_severity"] == {"HIGH": 1, "MEDIUM": 1, "LOW": 1}


def test_a_task_with_several_axes_counts_once_per_axis(report: dict) -> None:
    """Ось считается по вхождениям, поэтому сумма больше числа задач — это намеренно."""
    axes = report["measured"]["by_safety_axis"]
    assert axes == {"pediatric": 2, "missing_unit": 1, "NONE": 1}, axes


def test_a_task_without_axes_is_counted_as_none_not_dropped(report: dict) -> None:
    """Задача без осей не исчезает из отчёта."""
    assert report["measured"]["by_safety_axis"]["NONE"] == 1


def test_diagnosis_falls_back_through_the_payload_fields(report: dict) -> None:
    """diagnosis → indication → diagnosis_id → UNKNOWN."""
    diagnoses = report["measured"]["by_diagnosis"]
    assert diagnoses == {"отит": 1, "синусит": 1, "H66": 1}, diagnoses


def test_a_task_without_a_guideline_is_counted_as_unknown(report: dict) -> None:
    guidelines = report["measured"]["by_guideline"]
    assert guidelines == {"g1": 2, "UNKNOWN": 1}, guidelines


def test_projected_minutes_are_the_sum_of_per_task_lookups(report: dict) -> None:
    """Проекция — сумма по задачам, а не отдельная оценка."""
    expected = (
        PLANNING_MINUTES["HIGH"] + PLANNING_MINUTES["MEDIUM"] + PLANNING_MINUTES["LOW"]
    )
    projection = report["workload_projection"]
    assert projection["projected_minutes"] == expected == 39
    assert projection["projected_hours"] == round(expected / 60, 2)


# ── честность подписи ────────────────────────────────────────────────────────


def test_the_projection_is_labelled_an_estimate_not_a_benchmark(report: dict) -> None:
    """Минуты на приоритет — допущение планирования, а не измерение.

    Подпись — единственное, что мешает числу быть процитированным как наблюдаемые данные.
    """
    projection = report["workload_projection"]
    assert projection["status"] == "PLANNING_ESTIMATE_NOT_BENCHMARK"
    assert projection["minutes_per_priority"] == PLANNING_MINUTES
    # Рядом с допущением всегда стоит фактическое измерение, если оно есть.
    assert "actual_average_review_time_seconds" in projection


def test_measured_block_carries_the_store_metrics(report: dict) -> None:
    """Измеренная часть отчёта включает метрики хранилища, а не только срезы."""
    measured = report["measured"]
    for key in ("total", "total_pending", "by_state", "by_type", "by_priority"):
        assert key in measured, sorted(measured)


def test_an_empty_queue_reports_zeros_without_dividing_by_anything(tmp_path: Path) -> None:
    with ReviewStore(tmp_path / "empty.sqlite") as store:
        report = summarize_queue(store)
    assert report["measured"]["by_severity"] == {}
    assert report["workload_projection"]["projected_minutes"] == 0
    assert report["workload_projection"]["projected_hours"] == 0
