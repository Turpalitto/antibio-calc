"""H-4 regression: the API must not drop the engine's safety verdict.

The engine computed PREGNANCY_CI / RENAL_ADJ_UNPARSED / ALLERGY_* and
``SafetySummary``; the v1 transport emitted only identifiers and then stamped
``Status.APPROVED`` with ``notes=[]``. A caller could not distinguish a clean
recommendation from one carrying a contraindication.

These tests pin the pass-through. They do not re-test the engine — see
clinical_engine/tests/test_models.py::TestSafetySummary.
"""

from __future__ import annotations

from types import SimpleNamespace

from clinical_engine.api.service import handle_recommend
from clinical_engine.corpus.locator import CorpusLocator
from clinical_engine.api.service import ApiContext
from clinical_engine.models import SafetyAction, SafetyLevel

import pytest


_Q = {"api_version": "1", "query": {"diagnosis": "острый гайморит", "patient": {"age": 35}}}


def _flag(code="PREGNANCY_CI", action=SafetyAction.STOP_IMMEDIATELY, ack=True):
    return SimpleNamespace(
        code=code, level=SafetyLevel.ABSOLUTE_CONTRAINDICATION, message=f"{code} raised",
        drug_ref="cotrimoxazole", stage="hard_safety_filter", action=action,
        requires_physician_acknowledgement=ack)


def _engine(*, summary=None, flags=(), dose_patient_specific=True):
    rec = SimpleNamespace(
        candidate=SimpleNamespace(regimen_id="5351", guideline_id="g1",
                                  therapy_line="first_line"),
        safety_flags=list(flags),
        dose=SimpleNamespace(dose_is_patient_specific=dose_patient_specific),
        interaction_severity=None,
    )
    return SimpleNamespace(
        accepted=(rec,), excluded=(), safety_flags=tuple(flags),
        engine_notes=(SimpleNamespace(code="CURATED_APPROVED", message="curated: 1"),),
        safety_summary=summary)


def _summary(*, requires_review, codes=("PREGNANCY_CI",)):
    return SimpleNamespace(
        status="REVIEW_REQUIRED" if requires_review else "CLEARED",
        requires_physician_review=requires_review, total_flags=len(codes),
        flag_counts={c: 1 for c in codes}, flag_codes=tuple(codes),
        most_severe_action=SafetyAction.STOP_IMMEDIATELY,
        actions=(SafetyAction.STOP_IMMEDIATELY,),
        requires_physician_acknowledgement=len(codes),
        absolute_contraindications=len(codes),
        dose_is_patient_specific=False)


class _Engine:
    """Minimal CuratedEngine-shaped recommender carrying a SafetySummary."""

    def __init__(self, result):
        self._result = result

    def recommend(self, query):
        return self._result


def _ctx(tmp_path, engine):
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "normalized_regimens.sqlite").write_text("", encoding="utf-8")
    (root / "metadata.sqlite").write_text("", encoding="utf-8")
    return ApiContext(corpus=CorpusLocator(root),
                      curated_knowledge_path=str(tmp_path / "k.json"),
                      recommender=_Engine(engine))


def test_clean_set_is_approved(tmp_path):
    code, body = handle_recommend(
        _ctx(tmp_path, _engine(summary=_summary(requires_review=False, codes=()))), _Q)
    assert code == 200
    assert body["status"] == "APPROVED"
    assert body["safety_summary"]["status"] == "CLEARED"
    assert body["notes"] == []


def test_review_required_is_not_stamped_approved(tmp_path):
    """The core H-4 assertion: a flagged set must never read APPROVED."""
    code, body = handle_recommend(
        _ctx(tmp_path, _engine(summary=_summary(requires_review=True),
                                flags=(_flag(),))), _Q)
    assert code == 200
    assert body["status"] == "REVIEW_REQUIRED"
    assert [n["code"] for n in body["notes"]] == ["CLINICAL_REVIEW_REQUIRED"]
    # the recommendation is still delivered — just not as a clean approval
    assert body["recommendations"][0]["regimen_id"] == "5351"


def test_flags_are_attached_per_recommendation(tmp_path):
    code, body = handle_recommend(
        _ctx(tmp_path, _engine(summary=_summary(requires_review=True),
                                flags=(_flag(),))), _Q)
    rec = body["recommendations"][0]
    assert rec["safety_flags"][0]["code"] == "PREGNANCY_CI"
    assert rec["safety_flags"][0]["action"] == "stop_immediately"
    assert rec["requires_physician_acknowledgement"] is True
    assert rec["most_severe_action"] == "stop_immediately"


def test_non_patient_specific_dose_is_marked(tmp_path):
    """A dose the engine could not adjust for this patient must say so."""
    code, body = handle_recommend(
        _ctx(tmp_path, _engine(summary=_summary(requires_review=True),
                                flags=(_flag("RENAL_ADJ_UNPARSED",
                                             action=SafetyAction.AVOID_IF_POSSIBLE),),
                                dose_patient_specific=False)), _Q)
    assert body["recommendations"][0]["dose_is_patient_specific"] is False
    assert body["safety_summary"]["dose_is_patient_specific"] is False


def test_clean_recommendation_has_no_flag_fields(tmp_path):
    code, body = handle_recommend(
        _ctx(tmp_path, _engine(summary=_summary(requires_review=False, codes=()))), _Q)
    rec = body["recommendations"][0]
    assert "safety_flags" not in rec
    assert rec["dose_is_patient_specific"] is True


def test_engine_without_summary_still_works(tmp_path):
    """Legacy/fake engines have no SafetySummary; must not crash."""
    code, body = handle_recommend(_ctx(tmp_path, _engine(summary=None)), _Q)
    assert code == 200 and body["status"] == "APPROVED"
    assert body["safety_summary"] is None
