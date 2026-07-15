"""Stage 9: RankRecommendations — weighted scoring of survivors only.

Source: docs/superpowers/specs/clinical-decision-engine-v1.md §7.1.

Constitutional Invariant #3: RankRecommendations operates ONLY on
state.candidates. It cannot access state.excluded, add candidates, change
SafetyFlags, or change DoseDetail. It reorders and numbers. Period.

Two sub-formulas the spec names but does not fully define
(safety_penalty, score_population_match) are implemented here with
documented, conservative defaults -- see DECISIONS.md 2026-07-10.

No per-candidate "Ranked #{i}" StageTrace is emitted: DecisionCode has no
member for "ranked" (same reasoning as every other stage's silent-success
path in this codebase -- see RegimenLoad/HardSafetyFilter docstrings). The
final rank is visible directly on each Recommendation.rank instead.
"""

from __future__ import annotations

import dataclasses
import time

from clinical_engine._population import resolve_population_target
from clinical_engine.models import PatientQuery, Recommendation, SafetyLevel
from clinical_engine.pipeline import PipelineState, ScoreWeights, StageContext, StageResult

# §7.1 therapy_line_partial_score. Only "first"/"alternative"/"reserve" rows
# are defined by the spec; a preference outside that set degrades to the
# same conservative value the table uses for "unknown" candidates (0.1).
_THERAPY_LINE_PARTIAL: dict[str, dict[str, float]] = {
    "first": {"first": 1.0, "alternative": 0.5, "reserve": 0.3, "prophylaxis": 0.2, "empiric": 0.4, "unknown": 0.1},
    "alternative": {"first": 0.3, "alternative": 1.0, "reserve": 0.5, "prophylaxis": 0.2, "empiric": 0.4, "unknown": 0.1},
    "reserve": {"first": 0.2, "alternative": 0.5, "reserve": 1.0, "prophylaxis": 0.1, "empiric": 0.3, "unknown": 0.1},
}
_UNDEFINED_PREFERENCE_PARTIAL = 0.1

_SAFETY_PENALTY_PER_WARNING = 0.5  # see DECISIONS.md 2026-07-10


def _therapy_line_score(preference: str | None, candidate_line: str, weights: ScoreWeights) -> float:
    if preference is None:
        return weights.therapy_line_match * 0.5 if candidate_line == "first" else 0.0
    if candidate_line == preference:
        return weights.therapy_line_match
    row = _THERAPY_LINE_PARTIAL.get(preference)
    if row is None:
        return _UNDEFINED_PREFERENCE_PARTIAL
    return row.get(candidate_line, row["unknown"])


def _normalize_recency(guideline_year: int | None) -> float:
    if guideline_year is None:
        return 0.0
    if guideline_year >= 2024:
        return 1.0
    if guideline_year >= 2021:
        return 0.7
    if guideline_year >= 2016:
        return 0.4
    return 0.2


def _safety_fit_score(rec: Recommendation, weights: ScoreWeights) -> float:
    warning_count = sum(1 for f in rec.safety_flags if f.level is SafetyLevel.WARNING)
    return max(0.0, weights.safety_fit - _SAFETY_PENALTY_PER_WARNING * warning_count)


def _population_match_score(rec: Recommendation, query: PatientQuery, target: str | None) -> float:
    c = rec.candidate
    if target is None:
        return 0.5  # ambiguous -- can't assert match or mismatch
    if target == "adult":
        return 1.0 if c.adult else 0.0
    return 1.0 if c.child else 0.0  # "child" / "neonate"


class RankRecommendations:
    name = "RankRecommendations"

    def run(self, state: PipelineState, ctx: StageContext) -> StageResult:
        start = time.perf_counter()
        query = state.patient
        preferences = query.preferences
        weights = ctx.score_weights
        target = resolve_population_target(query, ctx.constants)

        scored: list[Recommendation] = []
        for rec in state.candidates:
            c = rec.candidate
            breakdown: dict[str, float] = {}

            breakdown["therapy_line"] = _therapy_line_score(
                preferences.therapy_line, c.therapy_line, weights
            )
            breakdown["confidence"] = c.confidence * weights.confidence
            breakdown["evidence_recency"] = _normalize_recency(c.guideline_year) * weights.evidence_recency
            breakdown["safety_fit"] = _safety_fit_score(rec, weights)
            breakdown["route_preference"] = (
                weights.route_preference
                if preferences.route_preference is not None and c.route == preferences.route_preference
                else 0.0
            )
            breakdown["population_match"] = (
                _population_match_score(rec, query, target) * weights.population_match
            )
            interaction_value = rec.interaction_severity.value if rec.interaction_severity else 0
            breakdown["interaction_penalty"] = -(interaction_value * weights.interaction_penalty)

            score = max(0.0, sum(breakdown.values()))
            scored.append(dataclasses.replace(rec, score=score, score_breakdown=breakdown))

        # Stable sort: ties keep the deterministic input order (SQLite
        # ORDER BY regimen_id) -- no extra tie-break needed (Invariant #2).
        ranked = sorted(scored, key=lambda r: r.score, reverse=True)
        ranked = [dataclasses.replace(r, rank=i) for i, r in enumerate(ranked, start=1)]

        new_state = dataclasses.replace(state, candidates=tuple(ranked))
        elapsed_ms = (time.perf_counter() - start) * 1000
        return StageResult(state=new_state, metrics={"ranked": len(ranked)}, elapsed_ms=elapsed_ms)
