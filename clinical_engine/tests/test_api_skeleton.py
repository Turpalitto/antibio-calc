"""P3 INT-5a — API skeleton / versioning / contract / health tests.

Handlers are tested directly (no server). A FastAPI TestClient check confirms
the HTTP binding wires the same handlers. Corpus is a temp/absent locator so
tests never depend on the real 3.6 GB corpus.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clinical_engine.api import contract
from clinical_engine.api.service import ApiContext, handle_health, handle_recommend, handle_version
from clinical_engine.corpus.locator import CorpusLocator


def _ctx(tmp_path: Path, *, corpus_present=False, knowledge=None) -> ApiContext:
    root = tmp_path / "corpus"
    if corpus_present:
        root.mkdir()
        (root / "normalized_regimens.sqlite").write_text("", encoding="utf-8")
        (root / "metadata.sqlite").write_text("", encoding="utf-8")
    kpath = tmp_path / "curated_knowledge.json"
    if knowledge is not None:
        kpath.write_text(json.dumps(knowledge, ensure_ascii=False), encoding="utf-8")
    return ApiContext(corpus=CorpusLocator(root), curated_knowledge_path=str(kpath))


# ── versioning ─────────────────────────────────────────────────


def test_version_endpoint(tmp_path):
    code, body = handle_version(_ctx(tmp_path))
    assert code == 200
    assert body["api_version"] == "1"
    assert body["supported_api_versions"] == ["1"]
    # error taxonomy is published for clients
    assert "review_required" in body["error_categories"]
    assert "CORPUS_UNAVAILABLE" in body["error_categories"]["corpus_unavailable"]


def test_error_code_categories_are_consistent():
    # every code maps back to exactly one category
    for cat, codes in contract.ERROR_CATEGORIES.items():
        for c in codes:
            assert contract.CODE_TO_CATEGORY[c] == cat


# ── health ─────────────────────────────────────────────────────


def test_health_degraded_without_corpus(tmp_path):
    code, body = handle_health(_ctx(tmp_path, corpus_present=False))
    assert code == 200
    assert body["ready"] is False and body["status"] == "degraded"
    assert body["corpus"]["available"] is False
    assert body["curated_knowledge"]["present"] is False


def test_health_ok_with_corpus(tmp_path):
    code, body = handle_health(_ctx(tmp_path, corpus_present=True))
    assert body["ready"] is True and body["status"] == "ok"
    assert body["corpus"]["available"] is True


def test_health_reports_knowledge_meta(tmp_path):
    knowledge = {"meta": {"status": "CURATED", "guideline_set_version": "curated-2026-07-11",
                          "counts": {"complete_links": 3}}}
    _, body = handle_health(_ctx(tmp_path, corpus_present=True, knowledge=knowledge))
    assert body["curated_knowledge"]["status"] == "CURATED"
    assert body["curated_knowledge"]["knowledge_version"] == "curated-2026-07-11"


# ── request contract ───────────────────────────────────────────


def test_parse_valid_request():
    req = contract.parse_recommend_request(
        {"api_version": "1", "query": {"diagnosis": "острый гайморит",
                                       "patient": {"age": 35, "allergies": ["Пенициллины"]}}})
    assert req.diagnosis == "острый гайморит"
    assert req.patient.allergies == ("Пенициллины",)


def test_parse_rejects_unsupported_version():
    with pytest.raises(contract.RequestError) as e:
        contract.parse_recommend_request({"api_version": "99", "query": {"diagnosis": "x"}})
    assert e.value.code == "UNSUPPORTED_API_VERSION"


def test_parse_rejects_missing_query():
    with pytest.raises(contract.RequestError) as e:
        contract.parse_recommend_request({"api_version": "1"})
    assert e.value.code == "INVALID_REQUEST"


def test_parse_requires_diagnosis_or_icd():
    with pytest.raises(contract.RequestError) as e:
        contract.parse_recommend_request({"api_version": "1", "query": {"patient": {"age": 5}}})
    assert e.value.code == "INVALID_REQUEST"


# ── recommend request-contract enforcement (INT-5b-1) ──────────


def test_recommend_rejects_bad_request(tmp_path):
    ctx = _ctx(tmp_path, corpus_present=True)
    code, body = handle_recommend(ctx, {"api_version": "1"})  # missing query
    assert code == 400
    assert body["errors"][0]["code"] == "INVALID_REQUEST"


def test_recommend_rejects_unsupported_version(tmp_path):
    ctx = _ctx(tmp_path, corpus_present=True)
    code, body = handle_recommend(ctx, {"api_version": "99", "query": {"diagnosis": "x"}})
    assert code == 400
    assert body["errors"][0]["code"] == "UNSUPPORTED_API_VERSION"


# ── HTTP binding wires the same handlers ───────────────────────


def test_fastapi_binding_health_and_version(tmp_path):
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from clinical_engine.api.app import create_app

    app = create_app(_ctx(tmp_path, corpus_present=True))
    client = TestClient(app)
    r = client.get("/v1/health")
    assert r.status_code == 200 and r.json()["ready"] is True
    v = client.get("/v1/version")
    assert v.status_code == 200 and v.json()["api_version"] == "1"
    # no recommender wired on this ctx -> explicit review-required, never a silent rec
    rec = client.post("/v1/recommend", json={"api_version": "1", "query": {"diagnosis": "x"}})
    assert rec.status_code == 200 and rec.json()["status"] == "REVIEW_REQUIRED"
