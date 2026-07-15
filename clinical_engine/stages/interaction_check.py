"""Stage 8: InteractionCheck — drug-drug interactions against current_meds.

Source: docs/superpowers/specs/clinical-decision-engine-v1.md §6.4.

Structured data only decides severity. Free text can only ever produce
InteractionSeverity.UNKNOWN — never MAJOR/MODERATE/MINOR/CONTRAINDICATED
(that classification happens at drugs_reference preparation time, not
here, per Invariant #13). UNKNOWN is not defaulted to MODERATE: the
physician sees "classification unknown", not a guessed severity.

Only CONTRAINDICATED excludes (Invariant #1, permanent). MAJOR/MODERATE/
MINOR/UNKNOWN only warn and never touch state.excluded (Constitution §6.5:
"MAJOR/MODERATE/MINOR/UNKNOWN -> warning + rank penalty").

Per DECISIONS.md 2026-07-10: DrugInfo (frozen, §5.3) has no structured
interactions field today, so _check_structured_interactions() always
returns None and the CONTRAINDICATED/MAJOR/MODERATE/MINOR branches are
unreachable against current data — but fully implemented so they activate
the moment drugs_reference gets a human-reviewed structured field.
"""

from __future__ import annotations

import dataclasses
import time

from clinical_engine.models import (
    ConfidenceLevel,
    DecisionCode,
    DrugInfo,
    InteractionSeverity,
    Recommendation,
    SafetyAction,
    SafetyFlag,
    SafetyLevel,
    StageTrace,
)
from clinical_engine.pipeline import PipelineState, StageContext, StageResult


def _check_structured_interactions(
    drug_info: DrugInfo, current_meds: tuple[str, ...]
) -> InteractionSeverity | None:
    """Would return the highest-severity structured match, if any.

    Always None in v1 -- DrugInfo has no structured_interactions field to
    check (see module docstring). Kept as its own function so wiring a
    future structured field only requires changing this one spot.
    """
    return None


def _own_identities(candidate_ref: str | None, drug_normalized: str, drug_info: DrugInfo) -> set[str]:
    names = {candidate_ref, drug_normalized, drug_info.inn}
    return {n.strip().lower() for n in names if n}


def _text_match(interactions_text: str, current_meds: tuple[str, ...], own: set[str]) -> bool:
    haystack = interactions_text.lower()
    for med in current_meds:
        med_norm = med.strip().lower()
        if not med_norm or med_norm in own:
            continue  # self-interaction: a drug does not interact with itself
        if med_norm in haystack:
            return True
    return False


_SEVERITY_FLAGS: dict[InteractionSeverity, tuple[str, SafetyLevel, SafetyAction, bool]] = {
    InteractionSeverity.CONTRAINDICATED: (
        "INTERACTION_CI", SafetyLevel.ABSOLUTE_CONTRAINDICATION, SafetyAction.STOP_IMMEDIATELY, True,
    ),
    InteractionSeverity.MAJOR: (
        "INTERACTION_MAJOR", SafetyLevel.WARNING, SafetyAction.AVOID_IF_POSSIBLE, False,
    ),
    InteractionSeverity.MODERATE: (
        "INTERACTION_MODERATE", SafetyLevel.WARNING, SafetyAction.MONITOR_CLOSELY, False,
    ),
    InteractionSeverity.MINOR: (
        "INTERACTION_MINOR", SafetyLevel.WARNING, SafetyAction.INFORM_PATIENT, False,
    ),
    InteractionSeverity.UNKNOWN: (
        "INTERACTION_UNKNOWN", SafetyLevel.WARNING, SafetyAction.MONITOR_CLOSELY, False,
    ),
}

# Only these severities get a StageTrace per §6.4's pseudocode (MODERATE/
# MINOR only raise a SafetyFlag, no explicit trace line).
_TRACED_SEVERITIES: dict[InteractionSeverity, ConfidenceLevel] = {
    InteractionSeverity.CONTRAINDICATED: ConfidenceLevel.FULL,
    InteractionSeverity.MAJOR: ConfidenceLevel.HIGH,
    InteractionSeverity.UNKNOWN: ConfidenceLevel.MEDIUM,
}


class InteractionCheck:
    name = "InteractionCheck"

    def run(self, state: PipelineState, ctx: StageContext) -> StageResult:
        start = time.perf_counter()
        current_meds = state.patient.patient.current_meds

        if not current_meds:
            return StageResult(state=state, metrics={"checked": 0}, elapsed_ms=0.0)

        updated: list[Recommendation] = []
        excluded = list(state.excluded)
        safety_flags = list(state.safety_flags)
        traces = list(state.traces)
        checked = 0

        for rec in state.candidates:
            c = rec.candidate
            # P0-2: via drug_safety_provider (adapter)
            drug_info = ctx.drug_safety_provider.get_drug_info(c.drug_ref) if c.drug_ref else None

            if drug_info is None or drug_info.interactions is None:
                updated.append(rec)
                continue

            own = _own_identities(c.drug_ref, c.drug_normalized, drug_info)
            relevant_meds = tuple(m for m in current_meds if m.strip().lower() not in own)
            if not relevant_meds:
                updated.append(rec)
                continue

            checked += 1
            severity = _check_structured_interactions(drug_info, relevant_meds)
            if severity is None:
                if not _text_match(drug_info.interactions, relevant_meds, own):
                    updated.append(rec)
                    continue
                severity = InteractionSeverity.UNKNOWN  # never guessed higher

            code, level, action, requires_ack = _SEVERITY_FLAGS[severity]
            flag = SafetyFlag(
                level=level,
                code=code,
                message=f"{c.drug_normalized}: interaction with current medication (severity={severity.name})",
                drug_ref=c.drug_ref or "",
                stage=self.name,
                action=action,
                requires_physician_acknowledgement=requires_ack,
            )
            safety_flags.append(flag)

            if severity in _TRACED_SEVERITIES:
                traces.append(
                    StageTrace(
                        stage_name=self.name,
                        decision_code=DecisionCode.INTERACTION,
                        reason=f"{c.drug_normalized} (regimen {c.regimen_id}): interaction severity={severity.name}",
                        decision_confidence=_TRACED_SEVERITIES[severity],
                    )
                )

            updated_rec = dataclasses.replace(
                rec,
                interaction_severity=severity,
                safety_flags=rec.safety_flags + (flag,),
            )

            if severity is InteractionSeverity.CONTRAINDICATED:
                excluded.append((updated_rec, "interaction: contraindicated"))
            else:
                updated.append(updated_rec)

        new_state = dataclasses.replace(
            state,
            candidates=tuple(updated),
            excluded=tuple(excluded),
            safety_flags=tuple(safety_flags),
            traces=tuple(traces),
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        return StageResult(
            state=new_state,
            metrics={"checked": checked, "excluded_this_stage": len(excluded) - len(state.excluded)},
            elapsed_ms=elapsed_ms,
        )
