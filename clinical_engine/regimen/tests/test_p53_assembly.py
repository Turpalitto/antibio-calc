"""P5.3 regression suite — assembly, provenance, conflict, lifecycle, approval, negatives.

Runs on real data when available (normalized_regimens.sqlite + kb_p44.db); the
deterministic/unit tests run everywhere with synthetic fixtures.
"""
import os
import sqlite3
import tempfile

import pytest

from clinical_engine.regimen.clinical_regimen import (
    UNKNOWN, ClinicalRegimen, FieldProvenance, LifecycleState,
)
from clinical_engine.regimen.conflict_detector import RegimenConflictDetector
from clinical_engine.regimen.validator import RegimenValidator
from clinical_engine.regimen.approval_workflow import ApprovalWorkflow, IllegalTransition
from clinical_engine.regimen.store import AssembledRegimenStore, ImmutabilityViolation

NR = r"C:\clinrec_downloader\normalized_regimens.sqlite"
KB = "kb_p44.db"


def _reg(**kw):
    base = dict(
        regimen_id="r1", version=1, status=LifecycleState.ASSEMBLED, diagnosis="d", icd_mkb="A01.0",
        age_group="adult", weight_range=UNKNOWN, pregnancy=None, renal_adjustment=False,
        therapy_line="first", antibiotic="amoxicillin", dose=0.5, unit="g", frequency=2.0,
        duration_recommended=7.0, duration_min=5.0, duration_max=10.0, route="oral",
        guideline_id="343", evidence_level=UNKNOWN, contraindications=(),
        field_provenance=tuple((f, FieldProvenance("r1", "x.pdf", "page 1", "normalized_regimens"))
                               for f in ("antibiotic", "dose", "route")),
        source_pdf="x.pdf", source_page="1", validation_verdict="PASS",
    )
    base.update(kw)
    return ClinicalRegimen(**base)


# --- provenance / explainability ---
def test_regimen_is_explainable_requires_source_line():
    assert _reg().is_explainable()
    assert not _reg(source_page="").is_explainable()
    assert not _reg(field_provenance=()).is_explainable()


# --- conflict detection (never silent) ---
def test_conflict_detector_flags_dose_disagreement():
    a = _reg(regimen_id="a", dose=0.5)
    b = _reg(regimen_id="b", dose=1.0)
    conflicts = RegimenConflictDetector().detect([a, b])
    assert any(c.field == "dose" and c.severity == "HIGH" for c in conflicts)
    assert all(c.resolution_status == "UNRESOLVED" for c in conflicts)


def test_conflict_detector_flags_different_first_line_drug():
    a = _reg(regimen_id="a", antibiotic="amoxicillin", therapy_line="first")
    b = _reg(regimen_id="b", antibiotic="ceftriaxone", therapy_line="first")
    conflicts = RegimenConflictDetector().detect([a, b])
    assert any(c.field == "first_line_drug" for c in conflicts)


def test_conflict_detection_is_deterministic():
    a = _reg(regimen_id="a", dose=0.5); b = _reg(regimen_id="b", dose=1.0)
    assert RegimenConflictDetector().detect([a, b]) == RegimenConflictDetector().detect([b, a])


# --- validation gates ---
def test_gate1_rejects_missing_dose():
    rep = RegimenValidator().validate(_reg(dose=None))
    assert rep.verdict == "REJECT"
    assert any(g[0] == "G1_completeness" and g[1] == "REJECT" for g in rep.gate_results)


def test_gate3_rejects_missing_source():
    rep = RegimenValidator().validate(_reg(source_pdf="", source_page=""))
    assert rep.verdict == "REJECT"


def test_gate4_reviews_on_conflict():
    rep = RegimenValidator().validate(_reg(needs_review_reasons=("unresolved_conflict",)))
    assert rep.verdict in ("REVIEW", "REJECT")
    assert any(g[0] == "G4_conflict" for g in rep.gate_results)


def test_clean_regimen_passes():
    assert RegimenValidator().validate(_reg()).verdict == "PASS"


# --- approval workflow / lifecycle ---
def test_no_draft_to_published():
    wf = ApprovalWorkflow()
    assert not wf.can_transition(LifecycleState.DRAFT, LifecycleState.PUBLISHED)
    with pytest.raises(IllegalTransition):
        wf.transition(_reg(status=LifecycleState.DRAFT), LifecycleState.PUBLISHED, actor="dr_smith")


def test_approval_requires_named_human():
    wf = ApprovalWorkflow()
    r = _reg(status=LifecycleState.REVIEW_REQUIRED)
    with pytest.raises(IllegalTransition):
        wf.transition(r, LifecycleState.PHYSICIAN_APPROVED, actor="system")
    approved = wf.transition(r, LifecycleState.PHYSICIAN_APPROVED, actor="dr_smith")
    assert approved.status == LifecycleState.PHYSICIAN_APPROVED
    assert approved.approved_by == "dr_smith"


def test_automated_advance_stops_at_review():
    wf = ApprovalWorkflow()
    r = wf.advance_automated(_reg(), verdict="PASS")
    assert r.status == LifecycleState.REVIEW_REQUIRED  # never auto-approves


def test_automated_reject_routes_to_rejected():
    r = ApprovalWorkflow().advance_automated(_reg(), verdict="REJECT")
    assert r.status == LifecycleState.REJECTED


# --- storage immutability ---
def test_store_is_insert_only_immutable():
    path = os.path.join(tempfile.gettempdir(), "p53_test_store.sqlite")
    if os.path.exists(path):
        os.unlink(path)
    store = AssembledRegimenStore(path)
    store.insert(_reg())
    with pytest.raises(ImmutabilityViolation):
        store.insert(_reg())  # same (regimen_id, version) -> immutable
    assert store.count() == 1
    store.close()


# --- real-data assembly (skips if data absent) ---
def test_real_assembly_produces_explainable_regimens():
    if not os.path.exists(NR):
        pytest.skip("normalized_regimens.sqlite not available")
    from clinical_engine.regimen.assembly_engine import RegimenAssemblyEngine
    res = RegimenAssemblyEngine(NR, KB).assemble(limit=200)
    assert res.metrics.assembled_count > 0
    # every assembled regimen must be explainable to a source line (core criterion)
    assert all(r.is_explainable() for r in res.regimens if r.validation_verdict == "PASS")
    # enrichment coverage is measured, not assumed
    assert 0.0 <= res.metrics.enrichment_coverage <= 1.0
