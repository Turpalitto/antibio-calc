"""P3 INT-5b-1 — recommend endpoint behaviour (envelope only, no clinical fields).

Validates the five required behaviours with an INJECTED recommender so the API
is exercised without building a real Engine over the read-only corpus:
approved, review-required, corpus-unavailable, invalid request, unsupported version.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from clinical_engine.api.service import ApiContext, handle_recommend
from clinical_engine.corpus.locator import CorpusLocator


# ── fakes: a CuratedEngine-shaped recommender ──────────────────
# _Result is a dataclass so CuratedEngine's dataclasses.replace() works on it.


class _Cand:
    def __init__(self, rid, gid, line):
        self.regimen_id, self.guideline_id, self.therapy_line = rid, gid, line


class _Rec:
    def __init__(self, cand): self.candidate = cand


class _Note:
    def __init__(self, code, message): self.code, self.message = code, message


@dataclass
class _Result:
    accepted: tuple[Any, ...] = ()
    engine_notes: tuple[Any, ...] = ()


class _ApprovedEngine:
    def recommend(self, query):
        return _Result(accepted=(_Rec(_Cand("5351", "343", "first_line")),),
                       engine_notes=(_Note("CURATED_APPROVED", "curated: 1 approved"),))


class _ReviewEngine:
    def recommend(self, query):
        return _Result(accepted=(),
                       engine_notes=(_Note("REVIEW_REQUIRED",
                                     "NO_APPROVED_DIAGNOSIS: diagnosis not physician-approved"),))


def _ctx(tmp_path: Path, *, corpus_present=True, recommender=None) -> ApiContext:
    root = tmp_path / "corpus"
    if corpus_present:
        root.mkdir()
        (root / "normalized_regimens.sqlite").write_text("", encoding="utf-8")
        (root / "metadata.sqlite").write_text("", encoding="utf-8")
    return ApiContext(corpus=CorpusLocator(root),
                      curated_knowledge_path=str(tmp_path / "k.json"),
                      recommender=recommender)


_Q = {"api_version": "1", "query": {"diagnosis": "острый гайморит", "patient": {"age": 35}}}


# ── the five required behaviours ───────────────────────────────


def test_approved_path(tmp_path):
    code, body = handle_recommend(_ctx(tmp_path, recommender=_ApprovedEngine()), _Q)
    assert code == 200 and body["status"] == "APPROVED"
    assert body["recommendations"][0]["regimen_id"] == "5351"
    assert body["recommendations"][0]["therapy_line"] == "first_line"
    # INT-5b-1: envelope only — no clinical fields yet
    assert "dose" not in body["recommendations"][0]
    assert body["errors"] == [] and body.get("review") is None


def test_review_required(tmp_path):
    code, body = handle_recommend(_ctx(tmp_path, recommender=_ReviewEngine()), _Q)
    assert code == 200                       # review-required is HTTP 200
    assert body["status"] == "REVIEW_REQUIRED"
    assert body["review"]["code"] == "NO_APPROVED_DIAGNOSIS"
    assert body["recommendations"] == []     # never a silent recommendation


def test_corpus_unavailable(tmp_path):
    code, body = handle_recommend(_ctx(tmp_path, corpus_present=False,
                                       recommender=_ApprovedEngine()), _Q)
    assert code == 503
    assert body["status"] == "ERROR"
    assert body["errors"][0]["code"] == "CORPUS_UNAVAILABLE"
    assert body["errors"][0]["category"] == "corpus_unavailable"


def test_invalid_request(tmp_path):
    code, body = handle_recommend(_ctx(tmp_path, recommender=_ApprovedEngine()),
                                  {"api_version": "1"})  # missing query
    assert code == 400 and body["errors"][0]["code"] == "INVALID_REQUEST"


def test_unsupported_api_version(tmp_path):
    code, body = handle_recommend(_ctx(tmp_path, recommender=_ApprovedEngine()),
                                  {"api_version": "99", "query": {"diagnosis": "x"}})
    assert code == 400 and body["errors"][0]["code"] == "UNSUPPORTED_API_VERSION"


# ── never-silent guarantees ────────────────────────────────────


def test_no_recommender_is_review_required_not_silent(tmp_path):
    code, body = handle_recommend(_ctx(tmp_path, recommender=None), _Q)
    assert code == 200 and body["status"] == "REVIEW_REQUIRED"
    assert body["review"]["code"] == "KNOWLEDGE_UNAVAILABLE"
    assert body["recommendations"] == []


def test_envelope_is_complete(tmp_path):
    _, body = handle_recommend(_ctx(tmp_path, recommender=_ApprovedEngine()), _Q)
    for key in ("api_version", "status", "knowledge_version", "recommendations", "errors", "notes"):
        assert key in body


def test_curated_engine_integration_real_wrapper(tmp_path):
    # Use the real CuratedEngine (INT-4) with an empty knowledge layer -> must be
    # review-required (never silent), proving the wrapper maps correctly.
    from clinical_engine.curated import CuratedEngine, CuratedKnowledge

    class _RawEngine:
        def recommend(self, query):
            return _Result(accepted=(_Rec(_Cand("5351", "343", "first_line")),))

    empty_knowledge = CuratedKnowledge({"approved_diagnoses": [], "approved_regimens": [], "links": []})
    curated = CuratedEngine(_RawEngine(), empty_knowledge)
    code, body = handle_recommend(_ctx(tmp_path, recommender=curated), _Q)
    assert body["status"] == "REVIEW_REQUIRED"          # empty curated layer withholds everything
    assert body["recommendations"] == []
