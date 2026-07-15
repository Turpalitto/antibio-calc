"""Explainable deterministic review priority scoring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .models import PriorityBand, Severity

_WEIGHTS = {
    "pediatric": 35,
    "pregnancy": 35,
    "renal": 35,
    "severe_allergy": 45,
    "missing_dose": 45,
    "ambiguous_dose": 45,
    "missing_unit": 40,
    "clinical_conflict": 40,
    "source_mismatch": 45,
    "lineage_uncertainty": 35,
    "golden_failure": 50,
    "missing_metadata": 20,
    "formatting": 5,
}

_SEVERITY_BASE = {
    Severity.CRITICAL: 60,
    Severity.HIGH: 40,
    Severity.MEDIUM: 20,
    Severity.LOW: 0,
}

_HIGH_REASONS = frozenset({
    "pediatric", "pregnancy", "renal", "severe_allergy", "missing_dose",
    "ambiguous_dose", "missing_unit", "clinical_conflict", "source_mismatch",
    "lineage_uncertainty", "golden_failure",
})


@dataclass(frozen=True, slots=True)
class PriorityResult:
    score: int
    band: PriorityBand
    contributing_reasons: tuple[str, ...]
    source_issue_ids: tuple[str, ...]


def score_priority(*, severity: Severity, safety_axes: Iterable[str] = (), reasons: Iterable[str] = (),
                   source_issue_ids: Iterable[str] = ()) -> PriorityResult:
    normalized = sorted({str(value).strip().casefold() for value in (*safety_axes, *reasons) if str(value).strip()})
    contributions = [(reason, _WEIGHTS[reason]) for reason in normalized if reason in _WEIGHTS]
    score = min(100, _SEVERITY_BASE[severity] + sum(weight for _, weight in contributions))
    if _HIGH_REASONS.intersection(normalized):
        score = max(60, score)
    elif "missing_metadata" in normalized:
        score = max(25, score)
    band = PriorityBand.HIGH if score >= 60 else PriorityBand.MEDIUM if score >= 25 else PriorityBand.LOW
    labels = tuple(f"{reason}:{weight}" for reason, weight in contributions)
    return PriorityResult(score, band, labels, tuple(sorted(set(source_issue_ids))))
