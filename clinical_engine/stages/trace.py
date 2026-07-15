"""Stage 10: Trace — assigns final outcome to every Recommendation.

Source: docs/superpowers/specs/clinical-decision-engine-v1.md §7.2.

This stage only sets `Recommendation.outcome` (ACCEPTED / WARNING /
EXCLUDED). Assembling the final RecommendationSet (EngineMetadata,
EngineRuntime, DecisionContext) is Engine.recommend()'s job, not a
PipelineStage's -- PipelineStage.run() returns a StageResult wrapping
PipelineState like every other stage (Invariant #5, uniform pipeline
shape), not the top-level RecommendationSet dataclass.

No clinical decisions here -- purely a labeling pass over what earlier
stages already decided.
"""

from __future__ import annotations

import dataclasses
import time

from clinical_engine.models import RecommendationOutcome, SafetyLevel
from clinical_engine.pipeline import PipelineState, StageContext, StageResult


class Trace:
    name = "Trace"

    def run(self, state: PipelineState, ctx: StageContext) -> StageResult:
        start = time.perf_counter()

        labeled_candidates = tuple(
            dataclasses.replace(rec, outcome=self._outcome_for(rec))
            for rec in state.candidates
        )
        labeled_excluded = tuple(
            (dataclasses.replace(rec, outcome=RecommendationOutcome.EXCLUDED), reason)
            for rec, reason in state.excluded
        )

        new_state = dataclasses.replace(
            state, candidates=labeled_candidates, excluded=labeled_excluded
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        return StageResult(state=new_state, elapsed_ms=elapsed_ms)

    @staticmethod
    def _outcome_for(rec) -> RecommendationOutcome:
        if any(f.level is SafetyLevel.ABSOLUTE_CONTRAINDICATION for f in rec.safety_flags):
            # Defensive: should not happen -- ABSOLUTE_CONTRAINDICATION
            # flags are always paired with an exclusion by the stage that
            # raised them (HardSafetyFilter, InteractionCheck).
            return RecommendationOutcome.EXCLUDED
        if any(f.level is SafetyLevel.WARNING for f in rec.safety_flags):
            return RecommendationOutcome.WARNING
        return RecommendationOutcome.ACCEPTED
