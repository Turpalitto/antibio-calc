"""Stage 6: DoseCalculation — computes the initial dose. No adjustments here.

Source: docs/superpowers/specs/clinical-decision-engine-v1.md §6.2.

Adult: fixed dose straight from SQLite (candidate.dose/frequency). Pediatric:
mg/kg/day from drugs_reference.pediatric_dosing x weight_kg, clamped to
max_daily_mg. Renal/hepatic adjustment is Stage 7's job (DoseAdjustment) —
this stage never touches renal_function/hepatic_impairment, and never
excludes (only WARNING + DoseCalculationMethod.UNCALCULATED on failure,
per Invariant #11).

Known data gap (see PROJECT_STATE.md): pediatric_dosing is absent for all
40 drugs in db/index.json today, so the pediatric branch always ends in
WARNING "PEDS_DOSING_UNKNOWN" against production data. The branch is fully
implemented so it activates automatically once that field is populated.
"""

from __future__ import annotations

import dataclasses
import time

from clinical_engine.models import (
    ConfidenceLevel,
    DecisionCode,
    DoseCalculationMethod,
    DoseDetail,
    Recommendation,
    SafetyAction,
    SafetyFlag,
    SafetyLevel,
    StageTrace,
)
from clinical_engine._population import resolve_population_target
from clinical_engine.pipeline import PipelineState, StageContext, StageResult


def _uncalculated(dose_unit: str) -> DoseDetail:
    return DoseDetail(
        calculated_dose_mg=None,
        dose_unit=dose_unit,
        frequency_per_day=None,
        duration_days=None,
        max_daily_mg=None,
        calculation_method=DoseCalculationMethod.UNCALCULATED,
        adjustment_applied=None,
        calculation_note=None,
    )


class DoseCalculation:
    name = "DoseCalculation"

    def run(self, state: PipelineState, ctx: StageContext) -> StageResult:
        start = time.perf_counter()
        query = state.patient
        patient = query.patient

        # Resolved once per query -- same helper PopulationFilter (Stage 3)
        # uses, so "adult"/"child"/"neonate"/None(ambiguous) agree everywhere.
        target = resolve_population_target(query, ctx.constants)

        updated: list[Recommendation] = []
        traces = list(state.traces)
        safety_flags = list(state.safety_flags)

        for rec in state.candidates:
            c = rec.candidate
            # §6.2: the ambiguous-population fallback to candidate flags is
            # ONLY defined for the adult branch ("candidate.adult AND NOT
            # candidate.child") -- there is no equivalent fallback for peds.
            # This is intentional, not an oversight: adult fixed-dose
            # passthrough is low-risk to infer when ambiguous; pediatric
            # weight-based dosing is not, so it requires an unambiguous
            # resolved population before it is attempted at all.
            is_adult_branch = target == "adult" or (
                target is None and c.adult and not c.child
            )
            is_peds_branch = (not is_adult_branch) and target in ("child", "neonate")

            if is_adult_branch:
                if c.dose is not None and c.frequency is not None:
                    dose = DoseDetail(
                        calculated_dose_mg=c.dose,
                        dose_unit=c.dose_unit or "",
                        frequency_per_day=c.frequency,
                        duration_days=c.duration_recommended,
                        max_daily_mg=None,
                        calculation_method=DoseCalculationMethod.FIXED,
                        adjustment_applied=None,
                        calculation_note=None,
                        adjustment_history=(f"base: {c.dose}{c.dose_unit}",),
                    )
                    updated.append(dataclasses.replace(rec, dose=dose))
                else:
                    flag = self._flag(c.drug_ref, "DOSE_UNCALCULABLE",
                                       f"{c.drug_normalized}: dose or frequency missing from source data")
                    safety_flags.append(flag)
                    traces.append(self._trace(c, "dose/frequency missing for adult regimen"))
                    updated.append(
                        dataclasses.replace(
                            rec,
                            dose=_uncalculated(c.dose_unit or ""),
                            safety_flags=rec.safety_flags + (flag,),
                        )
                    )

            elif is_peds_branch:
                # P0-2: via drug_safety_provider (adapter)
                drug_info = ctx.drug_safety_provider.get_drug_info(c.drug_ref) if c.drug_ref else None
                peds = drug_info.pediatric_dosing if drug_info else None

                if peds is None or peds.mg_per_kg_day is None:
                    flag = self._flag(c.drug_ref, "PEDS_DOSING_UNKNOWN",
                                       f"{c.drug_normalized}: no pediatric mg/kg/day data available")
                    safety_flags.append(flag)
                    traces.append(self._trace(c, "pediatric dosing unknown", ConfidenceLevel.HIGH))
                    updated.append(
                        dataclasses.replace(
                            rec, dose=_uncalculated("mg"), safety_flags=rec.safety_flags + (flag,)
                        )
                    )
                    continue

                if patient.weight_kg is None:
                    flag = self._flag(c.drug_ref, "WEIGHT_REQUIRED_FOR_PEDS",
                                       f"{c.drug_normalized}: patient weight required for mg/kg dosing")
                    safety_flags.append(flag)
                    traces.append(self._trace(c, "patient weight required for pediatric dosing"))
                    updated.append(
                        dataclasses.replace(
                            rec, dose=_uncalculated("mg"), safety_flags=rec.safety_flags + (flag,)
                        )
                    )
                    continue

                extra_flags: list[SafetyFlag] = []
                if peds.weight_min_kg is not None and patient.weight_kg < peds.weight_min_kg:
                    extra_flags.append(
                        self._flag(c.drug_ref, "BELOW_WEIGHT_BAND",
                                    f"{c.drug_normalized}: weight {patient.weight_kg}kg below band min {peds.weight_min_kg}kg")
                    )
                if peds.weight_max_kg is not None and patient.weight_kg > peds.weight_max_kg:
                    extra_flags.append(
                        self._flag(c.drug_ref, "ABOVE_WEIGHT_BAND",
                                    f"{c.drug_normalized}: weight {patient.weight_kg}kg above band max {peds.weight_max_kg}kg")
                    )

                daily_dose_mg = peds.mg_per_kg_day * patient.weight_kg
                if peds.max_daily_mg is not None:
                    daily_dose_mg = min(daily_dose_mg, peds.max_daily_mg)

                if c.frequency:
                    single_dose_mg = daily_dose_mg / c.frequency
                    note = (
                        f"{peds.mg_per_kg_day} mg/kg/day x {patient.weight_kg} kg "
                        f"= {daily_dose_mg} mg/day"
                    )
                    # No trace here: a successful calculation isn't a
                    # DecisionCode.DOSE_UNCALCULABLE moment, and no other
                    # DecisionCode fits "dose calculated OK" -- same
                    # precedent as RegimenLoad/HardSafetyFilter's silent
                    # success path (see their module docstrings).
                else:
                    # Edge case (§6.2 table): frequency is None -> daily dose
                    # known, but it can't be split into a single dose.
                    single_dose_mg = None
                    note = f"{daily_dose_mg} mg/day total; frequency unknown, cannot split into single dose"

                dose = DoseDetail(
                    calculated_dose_mg=single_dose_mg,
                    dose_unit="mg",
                    frequency_per_day=c.frequency,
                    duration_days=c.duration_recommended,
                    max_daily_mg=peds.max_daily_mg,
                    calculation_method=DoseCalculationMethod.MG_PER_KG,
                    adjustment_applied=None,
                    calculation_note=note,
                    adjustment_history=(f"base: {daily_dose_mg}mg/day",),
                )
                safety_flags.extend(extra_flags)
                updated.append(
                    dataclasses.replace(
                        rec, dose=dose, safety_flags=rec.safety_flags + tuple(extra_flags)
                    )
                )

            else:
                flag = self._flag(c.drug_ref, "POPULATION_AMBIGUOUS",
                                   f"{c.drug_normalized}: cannot determine adult vs pediatric dosing")
                safety_flags.append(flag)
                traces.append(self._trace(c, "population ambiguous, dose not calculated"))
                updated.append(
                    dataclasses.replace(
                        rec, dose=_uncalculated(c.dose_unit or ""), safety_flags=rec.safety_flags + (flag,)
                    )
                )

        new_state = dataclasses.replace(
            state,
            candidates=tuple(updated),
            safety_flags=tuple(safety_flags),
            traces=tuple(traces),
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        return StageResult(
            state=new_state,
            metrics={
                "uncalculated": sum(
                    1
                    for r in updated
                    if r.dose is not None
                    and r.dose.calculation_method is DoseCalculationMethod.UNCALCULATED
                )
            },
            elapsed_ms=elapsed_ms,
        )

    @staticmethod
    def _flag(drug_ref: str | None, code: str, message: str) -> SafetyFlag:
        return SafetyFlag(
            level=SafetyLevel.WARNING,
            code=code,
            message=message,
            drug_ref=drug_ref or "",
            stage="DoseCalculation",
            action=SafetyAction.MONITOR_CLOSELY,
            requires_physician_acknowledgement=False,
        )

    @staticmethod
    def _trace(
        candidate, reason: str, confidence: ConfidenceLevel = ConfidenceLevel.FULL
    ) -> StageTrace:
        return StageTrace(
            stage_name="DoseCalculation",
            decision_code=DecisionCode.DOSE_UNCALCULABLE,
            reason=f"{candidate.drug_normalized} (regimen {candidate.regimen_id}): {reason}",
            decision_confidence=confidence,
        )
