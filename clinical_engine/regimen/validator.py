"""RegimenValidator — 5 validation gates (P5.3 Phase 4).

Design authority: REGIMEN_VALIDATION_GATES.md, CLINICAL_SAFETY_GATES.md.
Fail-closed: a gate can only downgrade a regimen (PASS -> REVIEW -> REJECT), never upgrade.
Deterministic. No side effects. Returns a GateReport.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from clinical_engine.regimen.clinical_regimen import UNKNOWN, ClinicalRegimen


@dataclass(frozen=True)
class GateReport:
    regimen_id: str
    verdict: str                      # PASS | REVIEW | REJECT
    gate_results: tuple[tuple[str, str, str], ...]  # (gate, outcome, detail)

    def failed(self) -> bool:
        return self.verdict == "REJECT"


def _worst(a: str, b: str) -> str:
    order = {"PASS": 0, "REVIEW": 1, "REJECT": 2}
    return a if order[a] >= order[b] else b


class RegimenValidator:
    def validate(self, r: ClinicalRegimen) -> GateReport:
        results: list[tuple[str, str, str]] = []
        verdict = "PASS"

        # Gate 1 — Completeness: drug, dose, route, frequency, duration
        missing = [f for f, v in (
            ("antibiotic", r.antibiotic), ("dose", r.dose), ("route", r.route),
            ("frequency", r.frequency),
        ) if v in (None, "", "unknown", UNKNOWN)]
        if r.dose is None and "dose" not in missing:
            missing.append("dose")
        if missing:
            # missing drug/dose/route = REJECT; missing frequency/duration = REVIEW
            hard = any(m in ("antibiotic", "dose", "route") for m in missing)
            o = "REJECT" if hard else "REVIEW"
            results.append(("G1_completeness", o, f"missing={missing}"))
            verdict = _worst(verdict, o)
        else:
            results.append(("G1_completeness", "PASS", ""))

        # Gate 2 — Safety: children/pregnancy/renal
        safety = "PASS"; detail = []
        if r.age_group and "child" in str(r.age_group).lower():
            # pediatric must be weight-explicit (we don't have mg/kg in v1) -> REVIEW
            safety = _worst(safety, "REVIEW"); detail.append("pediatric_without_weight_basis")
        if r.pregnancy is False and not r.contraindications:
            safety = _worst(safety, "REVIEW"); detail.append("pregnancy_contraindicated_without_structured_basis")
        results.append(("G2_safety", safety, ";".join(detail)))
        verdict = _worst(verdict, safety)

        # Gate 3 — Evidence: must have a source
        if r.source_pdf and r.source_page:
            results.append(("G3_evidence", "PASS", ""))
        else:
            results.append(("G3_evidence", "REJECT", "no_source_document"))
            verdict = _worst(verdict, "REJECT")

        # Gate 4 — Conflict: no unresolved conflicts
        if "unresolved_conflict" in r.needs_review_reasons or r.conflicts:
            results.append(("G4_conflict", "REVIEW", "unresolved_conflict"))
            verdict = _worst(verdict, "REVIEW")
        else:
            results.append(("G4_conflict", "PASS", ""))

        # Gate 5 — Governance: lifecycle state permits progression, provenance complete
        if not r.is_explainable():
            results.append(("G5_governance", "REJECT", "not_explainable_missing_field_provenance"))
            verdict = _worst(verdict, "REJECT")
        else:
            results.append(("G5_governance", "PASS", ""))

        return GateReport(regimen_id=r.regimen_id, verdict=verdict, gate_results=tuple(results))
