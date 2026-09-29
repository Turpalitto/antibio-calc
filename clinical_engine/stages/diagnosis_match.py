"""Stage 1: DiagnosisMatch — diagnosis/ICD-10 -> guideline_ids.

Source: docs/superpowers/specs/clinical-decision-engine-v1.md §3.1, §10.1.

P1-B: uses TerminologyProvider.normalize_diagnosis (when use_terminology_binding)
for synonyms, ICD norm, spelling tolerance. Produces full Diagnosis Resolution
trace for every decision (Clinical Traceability Rule).

Reads: ctx.diagnosis_provider (resources/diagnosis_index.json, via reader)
Degrade: no match -> empty guideline_ids + StageTrace(NO_MATCH), not an
exception (§8.4 "Clinical no-data" is not EngineError).
"""

from __future__ import annotations

import dataclasses
import time

from typing import TYPE_CHECKING

from clinical_engine.models import (
    ConfidenceLevel,
    DecisionCode,
    SafetyAction,
    SafetyFlag,
    SafetyLevel,
    StageTrace,
)
from clinical_engine.pipeline import PipelineState, StageContext, StageResult
from clinical_engine.terminology import DiagnosisNormalization

if TYPE_CHECKING:
    from clinical_engine.readers.diagnosis_reader import DiagnosisLookup


class DiagnosisMatch:
    name = "DiagnosisMatch"

    def run(self, state: PipelineState, ctx: StageContext) -> StageResult:
        start = time.perf_counter()
        patient = state.patient
        diag = patient.diagnosis
        icd = patient.icd10

        # P1-B: additive normalization when flag on. Prefer normalized form for lookup when flag
        # (ensures consistent name used in RegimenLoad re-lookup and follows RFC for every norm step).
        norm: DiagnosisNormalization | None = None
        used_norm = False
        if ctx.config.use_terminology_binding:
            norm = ctx.terminology_provider.normalize_diagnosis(diag, icd)
            if norm:
                diag = norm.normalized_diagnosis or diag
                icd = norm.normalized_icd or icd
                used_norm = True

        # M-1: full lookup result, so a name/ICD contradiction and multi-guideline
        # provenance are reported instead of being merged into one anonymous list.
        lookup = ctx.diagnosis_provider.lookup_ex(diag, icd)  # type: ignore[attr-defined]
        guideline_ids = lookup.guideline_ids

        safety_flags = state.safety_flags
        if lookup.conflict:
            by_name = [e.guideline_id for e in lookup.by_diagnosis]
            by_icd = [e.guideline_id for e in lookup.by_icd10]
            safety_flags = safety_flags + (
                SafetyFlag(
                    level=SafetyLevel.WARNING,
                    code="DIAGNOSIS_ROUTING_CONFLICT",
                    message=(
                        "diagnosis name and ICD-10 resolve to different guidelines "
                        f"(name -> {by_name}, ICD-10 -> {by_icd}); no guideline "
                        "selected — clarify the query"
                    ),
                    drug_ref="",
                    stage=self.name,
                    action=SafetyAction.AVOID_IF_POSSIBLE,
                    requires_physician_acknowledgement=True,
                ),
            )

        # Build rich traceable Diagnosis Resolution block
        resolution_block = self._build_resolution_block(
            patient.diagnosis, patient.icd10, norm, guideline_ids, used_norm, lookup
        )

        elapsed_ms = (time.perf_counter() - start) * 1000

        if not guideline_ids:
            trace = StageTrace(
                stage_name=self.name,
                decision_code=DecisionCode.NO_MATCH,
                reason=resolution_block or "Diagnosis/ICD-10 not found in diagnosis_index",
                decision_confidence=ConfidenceLevel.NONE,
            )
            new_state = dataclasses.replace(
                state, guideline_ids=(), traces=state.traces + (trace,), safety_flags=safety_flags
            )
            return StageResult(
                state=new_state,
                metrics={"guideline_ids_matched": 0},
                elapsed_ms=elapsed_ms,
            )

        # Success path: use dedicated DIAGNOSIS_RESOLVED code (fixed semantic misuse of NO_MATCH from prior P1-B hack).
        new_traces = state.traces
        if ctx.config.use_terminology_binding or used_norm:
            trace = StageTrace(
                stage_name=self.name,
                decision_code=DecisionCode.DIAGNOSIS_RESOLVED,
                reason="DIAGNOSIS_RESOLVED\n" + (resolution_block or f"Matched {len(guideline_ids)} guideline(s) for diagnosis"),
                decision_confidence=self._map_confidence(norm.confidence if norm else "LOW"),
            )
            new_traces = state.traces + (trace,)
        if lookup.mixed_provenance:
            # More than one guideline contributes regimens to this answer; every
            # Recommendation carries its own guideline_id, but the physician
            # must be told the list is not from a single source.
            new_traces = new_traces + (
                StageTrace(
                    stage_name=self.name,
                    decision_code=DecisionCode.DIAGNOSIS_RESOLVED,
                    reason=(
                        f"mixed guideline provenance: {list(guideline_ids)} — each "
                        "recommendation names its own guideline_id; conflicting "
                        "routings are not resolved by the engine"
                    ),
                    decision_confidence=ConfidenceLevel.MEDIUM,
                ),
            )
            safety_flags = safety_flags + (
                SafetyFlag(
                    level=SafetyLevel.WARNING,
                    code="MIXED_GUIDELINE_PROVENANCE",
                    message=(
                        f"recommendations come from {len(guideline_ids)} guidelines "
                        f"({list(guideline_ids)}); each result carries its guideline_id"
                    ),
                    drug_ref="",
                    stage=self.name,
                    action=SafetyAction.INFORM_PATIENT,
                    requires_physician_acknowledgement=False,
                ),
            )
        new_state = dataclasses.replace(
            state, guideline_ids=guideline_ids, traces=new_traces, safety_flags=safety_flags
        )
        return StageResult(
            state=new_state,
            metrics={"guideline_ids_matched": len(guideline_ids)},
            elapsed_ms=elapsed_ms,
        )

    @staticmethod
    def _build_resolution_block(
        orig_d: str | None,
        orig_i: str | None,
        norm: DiagnosisNormalization | None,
        guideline_ids: tuple[str, ...],
        used_norm: bool,
        lookup: "DiagnosisLookup | None" = None,
    ) -> str:
        if lookup is not None:
            by_name = [e.guideline_id for e in lookup.by_diagnosis]
            by_icd = [e.guideline_id for e in lookup.by_icd10]
            provenance = (
                f"  Matched by name: {by_name or 'none'}\n"
                f"  Matched by ICD-10: {by_icd or 'none'}\n"
                f"  Signals agree: {'NO — routing conflict, nothing selected' if lookup.conflict else 'yes'}\n"
            )
        else:
            provenance = ""
        if not norm:
            return (
                f"Original: {orig_d} | ICD: {orig_i} | No normalization "
                f"(flag off or no change) | Selected: {list(guideline_ids)} | "
                f"{provenance}Routing decision: the two lookup signals must agree; "
                "only their intersection is routed."
            )
        block = (
            "Diagnosis Resolution\n"
            f"  Original: {norm.original_diagnosis}\n"
            f"  Normalized: {norm.normalized_diagnosis}\n"
            f"  ICD: {norm.normalized_icd}\n"
            f"  Synonym: {norm.synonym_used or 'none'}\n"
            f"  ICD mapping: {norm.icd_mapping or 'none'}\n"
            f"  Confidence: {norm.confidence}\n"
            f"  Reason: {norm.reason}\n"
            f"  Source: {norm.source}\n"
            f"  Used normalization: {used_norm}\n"
            f"  Selected guidelines: {list(guideline_ids)}\n"
            f"{provenance}"
            "  Routing decision: post-normalization lookup; the diagnosis-name and "
            "ICD-10 signals must agree and only their intersection is routed. "
            "Alternatives lost: guidelines matched by exactly one of the two signals."
        )
        return block

    @staticmethod
    def _map_confidence(c: str) -> ConfidenceLevel:
        c = (c or "").upper()
        if c == "HIGH":
            return ConfidenceLevel.HIGH
        if c == "MEDIUM":
            return ConfidenceLevel.MEDIUM
        if c == "LOW":
            return ConfidenceLevel.LOW
        return ConfidenceLevel.NONE
