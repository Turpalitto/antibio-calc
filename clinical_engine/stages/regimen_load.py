"""Stage 2: RegimenLoad — guideline_ids -> candidates (ValidationPolicy filter).

Source: docs/superpowers/specs/clinical-decision-engine-v1.md §3.1, §3.6, §10.1.

Reads: ctx.regimen_provider (via adapter), ctx.drug_safety_provider (resolve), ctx.diagnosis_provider (year join). P0-2 ports.

Two joins SQLiteReader deliberately leaves undone (see its module docstring)
happen here:
  - drug_ref: via DrugReferenceReader.resolve_drug_ref(drug_normalized)
  - guideline_year: via DiagnosisEntry, not SQLite (§5.3 field comment)

Implementation note: PipelineState only carries guideline_ids (tuple[str,
...]), not the DiagnosisEntry objects DiagnosisMatch resolved them from
(§5.7 fixes that shape). So this stage re-queries
``diagnosis_provider.lookup()`` with the same PatientQuery to rebuild a
guideline_id -> guideline_year map. JsonDiagnosisProvider caches its whole
index in memory (§4.2), so this is an in-memory dict lookup, not a second
I/O round-trip.

Degrade: guideline_id found but no regimens in SQLite -> empty candidates,
no exception (§8.4).
"""

from __future__ import annotations

import dataclasses
import time

from clinical_engine.models import Recommendation
from clinical_engine.pipeline import PipelineState, StageContext, StageResult


class RegimenLoad:
    name = "RegimenLoad"

    def run(self, state: PipelineState, ctx: StageContext) -> StageResult:
        start = time.perf_counter()

        if not state.guideline_ids:
            return StageResult(state=state, metrics={"candidates_loaded": 0}, elapsed_ms=0.0)

        # P1-B: use same normalized form as DiagnosisMatch when flag (consistency for year lookup)
        diag = state.patient.diagnosis
        icd = state.patient.icd10
        if ctx.config.use_terminology_binding:
            norm = ctx.terminology_provider.normalize_diagnosis(diag, icd)
            if norm:
                diag = norm.normalized_diagnosis or diag
                icd = norm.normalized_icd or icd
        entries = ctx.diagnosis_provider.lookup(diag, icd)
        year_by_guideline = {e.guideline_id: e.guideline_year for e in entries}

        # P0-2: use regimen_provider (adapter or legacy duck). Identical.
        raw_candidates = ctx.regimen_provider.load_regimens(
            state.guideline_ids, policy=ctx.config.validation_policy
        )

        recommendations = []
        for candidate in raw_candidates:
            # P0-2: use drug_safety_provider
            drug_ref = ctx.drug_safety_provider.resolve_drug_ref(candidate.drug_normalized)
            # P1: use terminology for atc if flag (additive, improves binding)
            atc = None
            if ctx.config.use_terminology_binding and drug_ref:
                atc = ctx.terminology_provider.get_atc(drug_ref)
            candidate = dataclasses.replace(
                candidate,
                drug_ref=drug_ref,
                atc_code=atc or candidate.atc_code,
                guideline_year=year_by_guideline.get(candidate.guideline_id),
            )
            recommendations.append(
                Recommendation(
                    candidate=candidate,
                    dose=None,
                    safety_flags=(),
                    interaction_severity=None,
                )
            )

        new_state = dataclasses.replace(state, candidates=tuple(recommendations))
        elapsed_ms = (time.perf_counter() - start) * 1000
        return StageResult(
            state=new_state,
            metrics={"candidates_loaded": len(recommendations)},
            elapsed_ms=elapsed_ms,
        )
