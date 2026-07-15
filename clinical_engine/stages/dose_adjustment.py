"""Stage 7: DoseAdjustment — modifies an already-calculated dose. Never computes one.

Source: docs/superpowers/specs/clinical-decision-engine-v1.md §6.3.

Only touches candidates whose DoseCalculation (Stage 6) succeeded
(calculation_method != UNCALCULATED) — "can't adjust what wasn't
calculated". Renal and hepatic checks are independent of each other and of
Stage 6; this stage never recomputes calculated_dose_mg from scratch, only
modifies (or, for hepatic, escalates) what Stage 6 produced.

Per DECISIONS.md 2026-07-10: both renal_adjustment and hepatic_adjustment
are unstructured free text for every drug in db/index.json today
(DrugInfo's fields are typed str | None, not a structured
{"threshold": ..., "action": ...} shape). Invariant #13 forbids parsing
prose at runtime, so in v1:
  - renal: text present -> WARNING "RENAL_ADJ_UNPARSED", dose unadjusted.
  - hepatic: text present -> WARNING "HEPATIC_ADJ_UNPARSED", dose
    unadjusted, NEVER escalated to exclusion. The spec's hepatic
    "Prohibited"/"Contraindicated" keyword-escalation branch is
    deliberately NOT implemented here — see DECISIONS.md for why inferring
    an absolute exclusion from free text is a materially different (and
    rejected) risk than the pregnancy_category keyword classification.
Both branches are structured so a future, human-reviewed structured field
can be wired in without changing this stage's shape.

Because neither branch ever produces a real numeric adjustment in v1, the
"renal + hepatic both adjusted -> most conservative" rule (§6.3 part 3) has
no reachable case yet and is intentionally not implemented -- add it back
alongside whichever adjustment lands its first structured data.
"""

from __future__ import annotations

import dataclasses
import time

from clinical_engine.models import (
    ConfidenceLevel,
    DecisionCode,
    DoseCalculationMethod,
    Recommendation,
    SafetyAction,
    SafetyFlag,
    SafetyLevel,
    StageTrace,
)
from clinical_engine.pipeline import PipelineState, StageContext, StageResult

_RENAL_NO_ADJUSTMENT_SENTINELS = {"not required", "не требуется"}


class DoseAdjustment:
    name = "DoseAdjustment"

    def run(self, state: PipelineState, ctx: StageContext) -> StageResult:
        start = time.perf_counter()
        patient = state.patient.patient

        updated: list[Recommendation] = []
        safety_flags = list(state.safety_flags)
        traces = list(state.traces)

        for rec in state.candidates:
            c = rec.candidate

            if rec.dose is None or rec.dose.calculation_method is DoseCalculationMethod.UNCALCULATED:
                updated.append(rec)
                continue

            # P0-2: via drug_safety_provider (adapter)
            drug_info = ctx.drug_safety_provider.get_drug_info(c.drug_ref) if c.drug_ref else None
            new_flags: list[SafetyFlag] = []

            # 1. Renal adjustment -- see module docstring: always degraded in v1.
            if patient.renal_function is not None and drug_info is not None:
                renal_text = drug_info.renal_adjustment
                if renal_text and renal_text.strip().lower() not in _RENAL_NO_ADJUSTMENT_SENTINELS:
                    flag = SafetyFlag(
                        level=SafetyLevel.WARNING,
                        code="RENAL_ADJ_UNPARSED",
                        message=f"{c.drug_normalized}: renal adjustment guidance present but unstructured, review manually",
                        drug_ref=c.drug_ref or "",
                        stage=self.name,
                        action=SafetyAction.MONITOR_CLOSELY,
                        requires_physician_acknowledgement=False,
                    )
                    new_flags.append(flag)
                    traces.append(
                        StageTrace(
                            stage_name=self.name,
                            decision_code=DecisionCode.RENAL,
                            reason=f"{c.drug_normalized} (regimen {c.regimen_id}): renal_adjustment text unparsed, dose unadjusted",
                            decision_confidence=ConfidenceLevel.MEDIUM,
                        )
                    )

            # 2. Hepatic adjustment -- never escalates to exclude in v1.
            if patient.hepatic_impairment:
                if drug_info is None or drug_info.hepatic_adjustment is None:
                    new_flags.append(
                        SafetyFlag(
                            level=SafetyLevel.WARNING,
                            code="HEPATIC_NO_DATA",
                            message=f"{c.drug_normalized}: no hepatic adjustment data available",
                            drug_ref=c.drug_ref or "",
                            stage=self.name,
                            action=SafetyAction.MONITOR_CLOSELY,
                            requires_physician_acknowledgement=False,
                        )
                    )
                else:
                    new_flags.append(
                        SafetyFlag(
                            level=SafetyLevel.WARNING,
                            code="HEPATIC_ADJ_UNPARSED",
                            message=f"{c.drug_normalized}: hepatic adjustment guidance present but unstructured, review manually",
                            drug_ref=c.drug_ref or "",
                            stage=self.name,
                            action=SafetyAction.MONITOR_CLOSELY,
                            requires_physician_acknowledgement=False,
                        )
                    )
                    traces.append(
                        StageTrace(
                            stage_name=self.name,
                            decision_code=DecisionCode.HEPATIC,
                            reason=f"{c.drug_normalized} (regimen {c.regimen_id}): hepatic_adjustment text unparsed, dose unadjusted, not excluded",
                            decision_confidence=ConfidenceLevel.MEDIUM,
                        )
                    )

            updated_rec = dataclasses.replace(rec, safety_flags=rec.safety_flags + tuple(new_flags))
            safety_flags.extend(new_flags)
            # v1: DoseAdjustment never excludes (hepatic escalation deliberately
            # disabled — see module docstring / DECISIONS.md). state.excluded is
            # left untouched, passed through by dataclasses.replace() below.
            updated.append(updated_rec)

        new_state = dataclasses.replace(
            state,
            candidates=tuple(updated),
            safety_flags=tuple(safety_flags),
            traces=tuple(traces),
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        return StageResult(
            state=new_state,
            metrics={"flags_raised": len(safety_flags) - len(state.safety_flags)},
            elapsed_ms=elapsed_ms,
        )
