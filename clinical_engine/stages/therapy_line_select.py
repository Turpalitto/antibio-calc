"""Stage 4: TherapyLineSelect — records the therapy_line preference for ranking.

Source: docs/superpowers/specs/clinical-decision-engine-v1.md §3.1, §7.1, §10.1.

Implementation note (see DECISIONS.md 2026-07-10): this stage does NOT
hard-filter candidates by preferences.therapy_line. RankRecommendations
(Stage 9, §7.1) scores therapy-line match via a partial-credit table
(e.g. preference="first", candidate="alternative" -> 0.5, not 0) that only
makes sense if mismatched candidates survive to reach it. Hard-filtering
here would make that table dead code. So this stage only appends a
StageTrace recording the resolved preference; it never changes
state.candidates or state.excluded.
"""

from __future__ import annotations

import dataclasses
import time

from clinical_engine.models import ConfidenceLevel, DecisionCode, StageTrace
from clinical_engine.pipeline import PipelineState, StageContext, StageResult


class TherapyLineSelect:
    name = "TherapyLineSelect"

    def run(self, state: PipelineState, ctx: StageContext) -> StageResult:
        start = time.perf_counter()
        preference = state.patient.preferences.therapy_line

        traces = state.traces
        if preference is not None:
            traces = traces + (
                StageTrace(
                    stage_name=self.name,
                    decision_code=DecisionCode.THERAPY_LINE,
                    reason=(
                        f"Preference '{preference}' recorded; RankRecommendations "
                        "will score matches, no candidates excluded here"
                    ),
                    decision_confidence=ConfidenceLevel.FULL,
                ),
            )

        new_state = dataclasses.replace(state, traces=traces)
        elapsed_ms = (time.perf_counter() - start) * 1000
        return StageResult(
            state=new_state,
            metrics={"therapy_line_preference": preference},
            elapsed_ms=elapsed_ms,
        )
