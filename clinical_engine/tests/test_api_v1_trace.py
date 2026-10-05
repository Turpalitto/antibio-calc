"""D4 (audit 2026-10-05) — v1 envelope exposes the stage-trace chain.

The Clinical Traceability Law requires every recommendation to answer which
stages participated, which regimens were considered, why alternatives were
rejected and which evidence backed the decision. v1 used to drop all of it;
`contract.envelope` now always carries a `trace` key and `service._trace_obj`
serializes `RecommendationSet.traces/excluded` when the engine ran.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from clinical_engine.api.service import ApiContext, handle_recommend
from clinical_engine.corpus.locator import CorpusLocator
from clinical_engine.models import (
    ConfidenceLevel,
    DecisionCode,
    Evidence,
    StageTrace,
)


class _Cand:
    def __init__(self, rid, gid, line="first_line"):
        self.regimen_id, self.guideline_id, self.therapy_line = rid, gid, line


class _Rec:
    def __init__(self, cand):
        self.candidate = cand


class _Note:
    def __init__(self, code, message):
        self.code, self.message = code, message


@dataclass
class _Result:
    accepted: tuple[Any, ...] = ()
    engine_notes: tuple[Any, ...] = ()
    excluded: tuple[Any, ...] = ()
    traces: tuple[Any, ...] = ()


class _TraceEngine:
    """Accepted + one excluded candidate + a real StageTrace chain."""

    def recommend(self, query):
        return _Result(
            accepted=(_Rec(_Cand("5351", "343")),),
            engine_notes=(_Note("CURATED_APPROVED", "curated: 1 approved"),),
            excluded=(
                (_Rec(_Cand("5352", "343")), "population mismatch: age 35 vs child"),
            ),
            traces=(
                StageTrace(
                    stage_name="diagnosis_match",
                    decision_code=DecisionCode.DIAGNOSIS_RESOLVED,
                    reason="острый гайморит -> CR 343",
                    evidence=Evidence(
                        source_pdf="/corpus/343.pdf",
                        source_page="12",
                        source_quote="—",
                        source_section="Treatment",
                        guideline_title="Острый риносинусит",
                        guideline_year=2024,
                        guideline_revision_date="2024-03-01",
                        source_url="https://cr.minzdrav.gov.ru/343",
                    ),
                ),
                StageTrace(
                    stage_name="population_filter",
                    decision_code=DecisionCode.POPULATION,
                    reason="adult population matched",
                ),
                StageTrace(  # duplicate stage name → participating_stages stays unique
                    stage_name="diagnosis_match",
                    decision_code=DecisionCode.DIAGNOSIS_RESOLVED,
                    reason="duplicate stage record",
                ),
            ),
        )


class _ApprovedEngine:
    def recommend(self, query):
        return _Result(
            accepted=(_Rec(_Cand("5351", "343")),),
            engine_notes=(_Note("CURATED_APPROVED", "curated: 1 approved"),),
        )


def _ctx(tmp_path: Path, *, recommender=None) -> ApiContext:
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "normalized_regimens.sqlite").write_text("", encoding="utf-8")
    (root / "metadata.sqlite").write_text("", encoding="utf-8")
    return ApiContext(
        corpus=CorpusLocator(root),
        curated_knowledge_path=str(tmp_path / "k.json"),
        recommender=recommender,
    )


_Q = {"api_version": "1", "query": {"diagnosis": "острый гайморит", "patient": {"age": 35}}}


def test_trace_key_always_present(tmp_path):
    _, body = handle_recommend(_ctx(tmp_path, recommender=_ApprovedEngine()), _Q)
    assert "trace" in body
    assert body["trace"]["participating_stages"] == []
    assert body["trace"]["stages"] == []
    # considered_regimens still reflects the accepted set (fakes carry no traces)
    assert body["trace"]["considered_regimens"] == [
        {"regimen_id": "5351", "guideline_id": "343",
         "accepted": True, "rejection_reasons": []}
    ]


def test_trace_exposes_stage_chain_and_rejections(tmp_path):
    _, body = handle_recommend(_ctx(tmp_path, recommender=_TraceEngine()), _Q)
    trace = body["trace"]
    # question 5: participating stages, unique, in first-seen order
    assert trace["participating_stages"] == ["diagnosis_match", "population_filter"]
    # questions 5 + 7: full stage records with evidence
    stages = trace["stages"]
    assert len(stages) == 3
    assert stages[0]["stage"] == "diagnosis_match"
    assert stages[0]["decision_code"] == "diagnosis_resolved"
    assert stages[0]["decision_confidence"] == 1.0  # ConfidenceLevel.FULL
    ev = stages[0]["evidence"]
    assert ev["guideline_title"] == "Острый риносинусит"
    assert ev["guideline_year"] == 2024
    # local corpus path must never leave the API
    assert "source_pdf" not in ev
    assert "/corpus/" not in str(trace)
    # questions 2 + 6: considered regimens incl. rejection reason
    considered = trace["considered_regimens"]
    assert {c["regimen_id"] for c in considered} == {"5351", "5352"}
    rejected = [c for c in considered if not c["accepted"]]
    assert rejected == [{"regimen_id": "5352", "guideline_id": "343",
                         "accepted": False,
                         "rejection_reasons": ["population mismatch: age 35 vs child"]}]


def test_trace_present_on_review_required_path(tmp_path):
    class _ReviewEngine:
        def recommend(self, query):
            return _Result(
                engine_notes=(_Note("REVIEW_REQUIRED",
                                    "NO_APPROVED_DIAGNOSIS: not approved"),),
            )

    _, body = handle_recommend(_ctx(tmp_path, recommender=_ReviewEngine()), _Q)
    assert body["status"] == "REVIEW_REQUIRED"
    assert body["trace"] == {"participating_stages": [], "stages": [],
                             "considered_regimens": []}


def test_trace_empty_when_engine_never_ran(tmp_path):
    root = tmp_path / "corpus"  # corpus_present=False path
    ctx = ApiContext(corpus=CorpusLocator(root),
                     curated_knowledge_path=str(tmp_path / "k.json"),
                     recommender=_ApprovedEngine())
    code, body = handle_recommend(ctx, _Q)
    assert code == 503
    assert body["trace"] == {}


def test_trace_empty_on_parse_error(tmp_path):
    code, body = handle_recommend(_ctx(tmp_path, recommender=_ApprovedEngine()),
                                  {"api_version": "1"})
    assert code == 400
    assert body["trace"] == {}
