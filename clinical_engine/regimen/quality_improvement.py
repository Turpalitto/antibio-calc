"""P5.4 Quality Improvement pass — applied AFTER unchanged P5.3 assembly (no architecture change).

Design authority: DOSE_NORMALIZATION_POLICY.md, RC024_DOSE_AUDIT_REPORT.md.

This module does NOT modify assembly_engine.py, validator.py, or approval_workflow.py
(P5.3 is architecturally frozen per the P5.4 mandate). It consumes an already-built
AssemblyResult and applies ONLY the safe, source-backed normalizations proven viable
by the audit: route recovery from literal source_quote text (RC024 Category E). Every
recovered field carries FieldProvenance. Ambiguous/unrecoverable cases are left exactly
as the unchanged P5.3 pipeline produced them.

normalized_regimens.sqlite, kb_p44.db, and the Clinical Engine are never touched.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from clinical_engine.regimen.assembly_engine import AssemblyResult
from clinical_engine.regimen.clinical_regimen import ClinicalRegimen
from clinical_engine.regimen.field_normalization import (
    NormalizationRunMetrics, canonicalize_unit, recover_route_from_quote,
)
from clinical_engine.regimen.validator import GateReport, RegimenValidator


@dataclass
class QualityImprovementResult:
    regimens: list[ClinicalRegimen]
    metrics: NormalizationRunMetrics
    before_verdicts: dict[str, int]
    after_verdicts: dict[str, int]


def _needs_route_recovery(r: ClinicalRegimen) -> bool:
    return not (r.route or "").strip() or r.route == "unknown"


def apply_quality_improvements(result: AssemblyResult) -> QualityImprovementResult:
    validator = RegimenValidator()
    metrics = NormalizationRunMetrics()

    # --- BEFORE metrics (re-validate the unchanged P5.3 output; does not mutate anything) ---
    before = {"PASS": 0, "REVIEW": 0, "REJECT": 0}
    for r in result.regimens:
        before[validator.validate(r).verdict] += 1

    improved: list[ClinicalRegimen] = []
    for r in result.regimens:
        new_r = r
        if _needs_route_recovery(r):
            metrics.examined += 1
            outcome = recover_route_from_quote(
                r.source_quote, r.regimen_id, r.source_pdf, r.source_page)
            if outcome.recovered:
                new_prov = r.field_provenance + (("route", outcome.provenance),)
                new_r = replace(new_r, route=outcome.value, field_provenance=new_prov)
                metrics.route_recovered += 1
            elif "ambiguous" in outcome.reason:
                metrics.route_ambiguous_skipped += 1
            else:
                metrics.route_no_match_skipped += 1

        # cosmetic unit canonicalization (never changes the numeric dose)
        canon_unit = canonicalize_unit(new_r.unit)
        if canon_unit != new_r.unit:
            new_r = replace(new_r, unit=canon_unit)
            metrics.unit_canonicalized += 1

        improved.append(new_r)

    # --- AFTER metrics (re-validate the improved set) ---
    after = {"PASS": 0, "REVIEW": 0, "REJECT": 0}
    revalidated: list[ClinicalRegimen] = []
    for r in improved:
        rep = validator.validate(r)
        after[rep.verdict] += 1
        revalidated.append(replace(r, validation_verdict=rep.verdict))

    return QualityImprovementResult(
        regimens=revalidated, metrics=metrics, before_verdicts=before, after_verdicts=after,
    )
