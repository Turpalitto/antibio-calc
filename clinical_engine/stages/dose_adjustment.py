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
prose at runtime, so the keyword classification happens at PREPARATION time
in DrugReferenceReader, which stores it as
``DrugInfo.renal_adjustment_level`` / ``hepatic_adjustment_level``
(OrganAdjustmentLevel). This stage reads only those enums. In v1:
  - renal: level NONE -> nothing to do. Any other level (CAUTION,
    PROHIBITED, UNKNOWN) with a value present -> WARNING
    "RENAL_ADJ_UNPARSED", dose numerically unadjusted.
  - hepatic: level NONE -> nothing to do. level PROHIBITED / CAUTION /
    UNKNOWN with a value present -> WARNING "HEPATIC_ADJ_UNPARSED", dose
    unadjusted, NEVER excluded: the text says "при тяжёлой печёночной
    недостаточности" / "с осторожностью" and Patient carries only a boolean,
    so the severity of the patient's hepatic impairment is unknown and an
    absolute exclusion cannot be justified from it.
Both branches are structured so a future, human-reviewed structured field
can be wired in without changing this stage's shape.

Because neither branch ever produces a real numeric adjustment in v1, the
"renal + hepatic both adjusted -> most conservative" rule (§6.3 part 3) has
no reachable case yet and is intentionally not implemented -- add it back
alongside whichever adjustment lands its first structured data.

**C-2(b) / H-5 — an unapplied adjustment marks the dose as not
patient-specific.** Emitting a fully-formed `calculated_dose_mg` while
flagging *_ADJ_UNPARSED let a consumer treat an adult fixed dose as an
adjusted dose for a renally/hepatically impaired patient. Degraded mode is
preserved (no silent exclusion, the number is still shown for reference), but
``DoseDetail.dose_is_patient_specific`` is now set to False, the reason is
appended to ``adjustment_history``, and the flag's action is escalated above
the purely advisory MONITOR_CLOSELY in proportion to the source text
(CAUTION/PROHIBITED -> AVOID_IF_POSSIBLE, and physician acknowledgement is
required) so the flag cannot be mistaken for routine monitoring.
"""

from __future__ import annotations

import dataclasses
import time

from clinical_engine.models import (
    ConfidenceLevel,
    DecisionCode,
    DoseCalculationMethod,
    OrganAdjustmentLevel,
    Recommendation,
    SafetyAction,
    SafetyFlag,
    SafetyLevel,
    StageTrace,
)
from clinical_engine.pipeline import PipelineState, StageContext, StageResult

# Action escalation per load-time level. UNKNOWN prose keeps the historical
# MONITOR_CLOSELY (we cannot tell how loud the source text is), but a level
# the reader positively identified as "с осторожностью"/"противопоказан" is
# escalated so the flag is not merely advisory.
_LEVEL_ACTION: dict[OrganAdjustmentLevel, tuple[SafetyAction, bool]] = {
    OrganAdjustmentLevel.PROHIBITED: (SafetyAction.AVOID_IF_POSSIBLE, True),
    OrganAdjustmentLevel.CAUTION: (SafetyAction.AVOID_IF_POSSIBLE, True),
    OrganAdjustmentLevel.UNKNOWN: (SafetyAction.MONITOR_CLOSELY, False),
    OrganAdjustmentLevel.NONE: (SafetyAction.MONITOR_CLOSELY, False),
}


def _non_specific_dose(rec: Recommendation, reason: str) -> Recommendation:
    """Mark the dose as not patient-specific and record why (C-2(b)/H-5)."""
    dose = rec.dose
    assert dose is not None  # caller only reaches here for calculated doses
    updated = dataclasses.replace(
        dose,
        dose_is_patient_specific=False,
        adjustment_applied=f"{dose.adjustment_applied}; {reason}" if dose.adjustment_applied
        else f"none applied: {reason}",
        calculation_note=(
            f"{dose.calculation_note} | NOT patient-specific: {reason}"
            if dose.calculation_note
            else f"NOT patient-specific: {reason}"
        ),
        adjustment_history=dose.adjustment_history + (f"unapplied: {reason}",),
    )
    return dataclasses.replace(rec, dose=updated)


class DoseAdjustment:
    name = "DoseAdjustment"

    def run(self, state: PipelineState, ctx: StageContext) -> StageResult:
        start = time.perf_counter()
        patient = state.patient.patient
        gfr = patient.gfr_ml_min

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
            unapplied: list[str] = []

            # 1. Renal adjustment -- see module docstring: always degraded in v1.
            if patient.renal_function is not None and drug_info is not None:
                if gfr is None:
                    # L-4: renal data was supplied but is not a readable GFR.
                    # Degrade loudly: silently skipping the check would let a
                    # renally-impaired patient through with no renal review.
                    new_flags.append(
                        SafetyFlag(
                            level=SafetyLevel.WARNING,
                            code="RENAL_DATA_UNPARSEABLE",
                            message=(
                                f"{c.drug_normalized}: renal_function "
                                f"{patient.renal_function!r} is not a GFR in ml/min; "
                                "renal dosing could not be reviewed"
                            ),
                            drug_ref=c.drug_ref or "",
                            stage=self.name,
                            action=SafetyAction.AVOID_IF_POSSIBLE,
                            requires_physician_acknowledgement=True,
                        )
                    )
                    traces.append(
                        StageTrace(
                            stage_name=self.name,
                            decision_code=DecisionCode.RENAL,
                            reason=(
                                f"{c.drug_normalized} (regimen {c.regimen_id}): "
                                f"renal_function {patient.renal_function!r} unparseable, "
                                "renal check skipped"
                            ),
                            decision_confidence=ConfidenceLevel.LOW,
                        )
                    )
                    unapplied.append("renal_data_unparseable")
                else:
                    renal_level = drug_info.renal_adjustment_level
                    if renal_level is not OrganAdjustmentLevel.NONE and drug_info.renal_adjustment:
                        action, requires_ack = _LEVEL_ACTION[renal_level]
                        flag = SafetyFlag(
                            level=SafetyLevel.WARNING,
                            code="RENAL_ADJ_UNPARSED",
                            message=(
                                f"{c.drug_normalized}: renal adjustment guidance present but "
                                f"unstructured ({renal_level.value}); review manually"
                            ),
                            drug_ref=c.drug_ref or "",
                            stage=self.name,
                            action=action,
                            requires_physician_acknowledgement=requires_ack,
                        )
                        new_flags.append(flag)
                        unapplied.append("renal_adjustment_unparsed")
                        traces.append(
                            StageTrace(
                                stage_name=self.name,
                                decision_code=DecisionCode.RENAL,
                                reason=(
                                    f"{c.drug_normalized} (regimen {c.regimen_id}): "
                                    f"renal_adjustment text unparsed "
                                    f"({renal_level.value}), dose NOT renal-adjusted"
                                ),
                                decision_confidence=ConfidenceLevel.MEDIUM,
                            )
                        )

            # 2. Hepatic adjustment -- never excludes (see module docstring).
            if patient.hepatic_impairment:
                hepatic_level = drug_info.hepatic_adjustment_level if drug_info else None
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
                elif hepatic_level is not OrganAdjustmentLevel.NONE:
                    level = hepatic_level or OrganAdjustmentLevel.UNKNOWN
                    action, requires_ack = _LEVEL_ACTION[level]
                    new_flags.append(
                        SafetyFlag(
                            level=SafetyLevel.WARNING,
                            code="HEPATIC_ADJ_UNPARSED",
                            message=(
                                f"{c.drug_normalized}: hepatic adjustment guidance present but "
                                f"unstructured ({level.value}); review manually"
                            ),
                            drug_ref=c.drug_ref or "",
                            stage=self.name,
                            action=action,
                            requires_physician_acknowledgement=requires_ack,
                        )
                    )
                    unapplied.append("hepatic_adjustment_unparsed")
                    traces.append(
                        StageTrace(
                            stage_name=self.name,
                            decision_code=DecisionCode.HEPATIC,
                            reason=(
                                f"{c.drug_normalized} (regimen {c.regimen_id}): "
                                f"hepatic_adjustment text unparsed ({level.value}), "
                                "dose NOT hepatic-adjusted, not excluded"
                            ),
                            decision_confidence=ConfidenceLevel.MEDIUM,
                        )
                    )

            updated_rec = dataclasses.replace(rec, safety_flags=rec.safety_flags + tuple(new_flags))
            if unapplied:
                updated_rec = _non_specific_dose(updated_rec, "+".join(unapplied))
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
