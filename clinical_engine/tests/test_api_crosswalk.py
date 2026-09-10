"""API tests for GET /v1/guidelines/{disease_id} (КР corpus navigation).

The endpoint is read-only navigation. These tests pin the guarantees that keep it
from becoming a back door into clinical decisioning:

* it reports ``calculation_blocked`` verbatim and never overrides it;
* it declares ``purpose: NAVIGATION_ONLY``;
* it fails closed (503) when the crosswalk artifact is missing — it never
  answers "no guidelines exist" for a broken artifact;
* it is reachable over the real FastAPI adapter.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clinical_engine.api import service
from clinical_engine.api.contract import API_VERSION
from clinical_engine.corpus.locator import CorpusLocator
from clinical_engine.crosswalk import build_crosswalk, write_crosswalk


CALCULATOR = {
    "recommendations": [
        {
            "id": "tonsillitis_child",
            "name": "Острый тонзиллит у детей",
            "cr_id": "306_3",
            "cr_year": 2024,
            "mkb10": ["J03", "J03.0"],
            "source_url": "https://cr.minzdrav.gov.ru/view-cr/306_3",
            "calculation_blocked": True,
            "source_verification_status": "SOURCE_SPEC_PENDING_CALCULATOR_BINDING",
        },
        {
            "id": "orphan",
            "name": "Нозология без корпуса",
            "cr_id": "999_1",
            "cr_year": None,
            "mkb10": ["Z99.9"],
            "source_url": None,
            "calculation_blocked": True,
            "source_verification_status": "SOURCE_SPEC_MISSING",
        },
    ]
}

INDEX = {
    "meta": {"status": "AUTO_GENERATED_DRAFT"},
    "entries": [
        {
            "guideline_id": "1269",
            "guideline_title": "Острый тонзиллит и фарингит",
            "guideline_year": 2024,
            "guideline_revision_date": None,
            "diagnosis_name": "Острый стрептококковый тонзиллит",
            "icd10_codes": ["J03", "J03.9"],
            "source_url": "",
        }
    ],
}


@pytest.fixture()
def ctx(tmp_path: Path) -> service.ApiContext:
    db_path = tmp_path / "antibio_db.json"
    db_path.write_text(json.dumps(CALCULATOR, ensure_ascii=False), encoding="utf-8")
    crosswalk_path = write_crosswalk(build_crosswalk(CALCULATOR, INDEX), tmp_path / "crosswalk.json")
    return service.ApiContext(
        corpus=CorpusLocator(),
        crosswalk_path=str(crosswalk_path),
        calculator_db_path=str(db_path),
    )


def test_returns_links_and_reports_the_block_verbatim(ctx):
    status, body = service.handle_calculator_guidelines(ctx, "tonsillitis_child")
    assert status == 200
    assert body["api_version"] == API_VERSION
    assert body["purpose"] == "NAVIGATION_ONLY"
    assert body["guideline_count"] == 1
    assert body["guidelines"][0]["guideline_id"] == "1269"
    assert body["guidelines"][0]["method"] == "ICD10_EXACT"
    # The navigation layer must not soften the calculator's own gate.
    assert body["disease"]["calculation_blocked"] is True
    assert body["disease"]["source_verification_status"] == "SOURCE_SPEC_PENDING_CALCULATOR_BINDING"
    assert body["disease"]["mkb10"] == ["J03", "J03.0"]


def test_unknown_disease_is_404(ctx):
    status, body = service.handle_calculator_guidelines(ctx, "does_not_exist")
    assert status == 404
    assert body["errors"][0]["code"] == "DIAGNOSIS_NOT_FOUND"


def test_disease_without_corpus_links_returns_an_empty_list_not_an_error(ctx):
    status, body = service.handle_calculator_guidelines(ctx, "orphan")
    assert status == 200
    assert body["guideline_count"] == 0
    assert body["guidelines"] == []


def test_blank_disease_id_is_a_bad_request(ctx):
    status, body = service.handle_calculator_guidelines(ctx, "   ")
    assert status == 400
    assert body["errors"][0]["code"] == "INVALID_REQUEST"


def test_missing_crosswalk_fails_closed(tmp_path):
    db_path = tmp_path / "antibio_db.json"
    db_path.write_text(json.dumps(CALCULATOR, ensure_ascii=False), encoding="utf-8")
    broken = service.ApiContext(
        corpus=CorpusLocator(),
        crosswalk_path=str(tmp_path / "absent.json"),
        calculator_db_path=str(db_path),
    )
    status, body = service.handle_calculator_guidelines(broken, "tonsillitis_child")
    assert status == 503
    assert body["status"] == "ERROR"
    assert body["errors"][0]["code"] == "KNOWLEDGE_UNAVAILABLE"


def test_missing_calculator_db_fails_closed(tmp_path):
    crosswalk_path = write_crosswalk(build_crosswalk(CALCULATOR, INDEX), tmp_path / "crosswalk.json")
    broken = service.ApiContext(
        corpus=CorpusLocator(),
        crosswalk_path=str(crosswalk_path),
        calculator_db_path=str(tmp_path / "absent_db.json"),
    )
    status, body = service.handle_calculator_guidelines(broken, "tonsillitis_child")
    assert status == 503
    assert body["errors"][0]["code"] == "KNOWLEDGE_UNAVAILABLE"


def test_route_is_exposed_by_the_fastapi_adapter(ctx):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from clinical_engine.api.app import create_app

    client = TestClient(create_app(ctx))

    ok = client.get("/v1/guidelines/tonsillitis_child")
    assert ok.status_code == 200
    assert ok.json()["guideline_count"] == 1

    missing = client.get("/v1/guidelines/nope")
    assert missing.status_code == 404


def test_endpoint_answers_from_the_committed_artifacts():
    """Smoke test over the real shipped DB + crosswalk (no fixtures)."""
    ctx = service.ApiContext(corpus=CorpusLocator())
    status, body = service.handle_calculator_guidelines(ctx, "mastitis_puerperal")
    assert status == 200
    assert body["purpose"] == "NAVIGATION_ONLY"
    assert body["guideline_count"] >= 1
    titles = " ".join(item["guideline_title"].lower() for item in body["guidelines"])
    assert "молочн" in titles
