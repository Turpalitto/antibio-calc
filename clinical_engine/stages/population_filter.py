"""Stage 3: PopulationFilter — patient age/preferences -> adult/child/neonate.

Source: docs/superpowers/specs/clinical-decision-engine-v1.md §3.1, §10.1.

Hard filter: population is treated as an objective applicability fact (a
pediatric-only regimen does not physically apply to an adult), unlike
therapy_line (Stage 4, a soft ranking preference — see DECISIONS.md
2026-07-10). Non-matching candidates move to state.excluded with a reason,
never silently dropped (Invariant #1: excluded only grows).

Degrade: age is None and no preferences.population -> ambiguous, no
filtering applied (ranking/downstream stages see everyone) -- missing data
never causes a silent exclude (Invariant #11).

Known schema gap (see DECISIONS.md 2026-07-10): RecommendationCandidate has
only adult/child booleans, no separate neonate flag -- "neonate" target
matches on candidate.child, same as "child".
"""

from __future__ import annotations

import dataclasses
import time

from clinical_engine._population import resolve_population_target
from clinical_engine.models import ConfidenceLevel, DecisionCode, StageTrace
from clinical_engine.pipeline import PipelineState, StageContext, StageResult


def _matches(target: str, candidate_adult: bool, candidate_child: bool) -> bool:
    if target == "adult":
        return candidate_adult
    if target in ("child", "neonate"):
        return candidate_child
    return True  # unreachable given callers, but never silently exclude


class PopulationFilter:
    name = "PopulationFilter"

    def run(self, state: PipelineState, ctx: StageContext) -> StageResult:
        start = time.perf_counter()
        target = resolve_population_target(state.patient, ctx.constants)

        traces = state.traces
        if target is None:
            traces = traces + (
                StageTrace(
                    stage_name=self.name,
                    decision_code=DecisionCode.POPULATION,
                    reason="Age unknown and no population preference; no population filtering applied",
                    decision_confidence=ConfidenceLevel.LOW,
                ),
            )

        kept = []
        excluded = list(state.excluded)
        for rec in state.candidates:
            c = rec.candidate
            if target is None or _matches(target, c.adult, c.child):
                kept.append(rec)
            else:
                excluded.append(
                    (
                        rec,
                        f"population_mismatch: target={target}, "
                        f"candidate adult={c.adult} child={c.child}",
                    )
                )

        new_state = dataclasses.replace(
            state, candidates=tuple(kept), excluded=tuple(excluded), traces=traces
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        return StageResult(
            state=new_state,
            metrics={
                "population_target": target or "ambiguous",
                "excluded_this_stage": len(excluded) - len(state.excluded),
            },
            elapsed_ms=elapsed_ms,
        )
