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

from clinical_engine.models import ConfidenceLevel, DecisionCode, StageTrace
from clinical_engine.pipeline import PipelineState, StageContext, StageResult
from clinical_engine.terminology import DiagnosisNormalization


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

        entries = ctx.diagnosis_provider.lookup(diag, icd)

        guideline_ids = tuple(dict.fromkeys(e.guideline_id for e in entries))

        # Build rich traceable Diagnosis Resolution block
        resolution_block = self._build_resolution_block(patient.diagnosis, patient.icd10, norm, guideline_ids, used_norm)

        elapsed_ms = (time.perf_counter() - start) * 1000

        if not guideline_ids:
            trace = StageTrace(
                stage_name=self.name,
                decision_code=DecisionCode.NO_MATCH,
                reason=resolution_block or "Diagnosis/ICD-10 not found in diagnosis_index",
                decision_confidence=ConfidenceLevel.NONE,
            )
            new_state = dataclasses.replace(
                state, guideline_ids=(), traces=state.traces + (trace,)
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
        new_state = dataclasses.replace(state, guideline_ids=guideline_ids, traces=new_traces)
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
    ) -> str:
        if not norm:
            return f"Original: {orig_d} | ICD: {orig_i} | No normalization (flag off or no change) | Selected: {list(guideline_ids)} | Routing decision: exact lookup matched these guidelines."
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
            "  Routing decision: post-normalization lookup matched exactly these guidelines. "
            "Alternatives lost: no other index entries matched the normalized diagnosis or ICD."
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
