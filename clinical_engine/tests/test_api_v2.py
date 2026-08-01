from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from clinical_engine.api.app import create_app
from clinical_engine.api.service import ApiContext, handle_recommend_v2
from clinical_engine.api.v2_contract import RequestError, parse_recommend_request
from clinical_engine.corpus.locator import CorpusLocator
from clinical_engine.personal.runtime import PersonalRuntime
import pytest


def _payload(**changes):
    value = {
        "api_version": "2",
        "operating_mode": "PERSONAL_PHYSICIAN",
        "owner_id": "owner-1",
        "session_token": "local-token",
        "query": {
            "diagnosis": "острый средний отит",
            "patient": {"age": 4, "weight_kg": 18},
        },
    }
    value.update(changes)
    return value


def _context(tmp_path: Path, personal_service=None) -> ApiContext:
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "normalized_regimens.sqlite").write_bytes(b"")
    (root / "metadata.sqlite").write_bytes(b"")
    return ApiContext(corpus=CorpusLocator(root), personal_service=personal_service)


class _PersonalService:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def recommend(self, *, request, host, origin):
        self.calls.append((request, host, origin))
        return self.result

    def health(self):
        return {"recommendation_eligible": True, "bundle_version": "owner-bundle-1"}


def _recommendation():
    return {
        "regimen_id": "aom-child-amoxiclav",
        "guideline_id": "314",
        "governance_status": "OWNER_REVIEWED_EXPERIMENTAL",
        "drug": {"drug_ref": "amoxiclav", "name": "Амоксициллин/клавуланат"},
        "dose": {
            "dose_mg_kg_day": 45,
            "frequency_per_day": 2,
            "max_daily_mg": 3000,
            "duration_days": "5-7",
        },
        "calculator_binding": {
            "disease_id": "aom_child",
            "scenario_id": "aom_child_standard",
            "line_number": 1,
            "drug_ref": "amoxiclav",
            "route": "per_os",
            "regimen_label": "45 мг/кг/сут в 2 приёма",
        },
        "source": {"page": 24, "quote": "source wording", "pdf_sha256": "a" * 64},
        "trace": {"stages": ["PersonalPhysicianGuard", "DoseCalculation"]},
    }


def test_v2_unconfigured_is_review_required_and_empty(tmp_path):
    code, body = handle_recommend_v2(
        _context(tmp_path), _payload(), host="127.0.0.1"
    )
    assert code == 200
    assert body["status"] == "REVIEW_REQUIRED"
    assert body["recommendations"] == []
    assert body["review"]["code"] == "PERSONAL_MODE_NOT_CONFIGURED"
    assert body["status"] != "APPROVED"


def test_v2_owner_reviewed_full_result(tmp_path):
    service = _PersonalService({
        "status": "OWNER_REVIEWED",
        "bundle_version": "owner-bundle-1",
        "recommendations": [_recommendation()],
        "trace": {"request_audit_id": "audit-1"},
    })
    code, body = handle_recommend_v2(
        _context(tmp_path, service), _payload(), host="localhost", origin="http://localhost:8980"
    )
    assert code == 200
    assert body["status"] == "OWNER_REVIEWED"
    assert body["governance_status"] == "OWNER_REVIEWED_EXPERIMENTAL"
    assert body["recommendations"][0]["dose"]["dose_mg_kg_day"] == 45
    assert body["recommendations"][0]["calculator_binding"]["drug_ref"] == "amoxiclav"
    assert body["banner"]["dismissible"] is False
    assert service.calls[0][1:] == ("localhost", "http://localhost:8980")


def test_v2_forbidden_approved_status_is_blocked(tmp_path):
    service = _PersonalService({"status": "APPROVED", "recommendations": [_recommendation()]})
    _, body = handle_recommend_v2(
        _context(tmp_path, service), _payload(), host="127.0.0.1"
    )
    assert body["status"] == "BLOCKED"
    assert body["recommendations"] == []
    assert body["review"]["code"] == "INVALID_PERSONAL_SERVICE_STATUS"


def test_v2_rejects_wrong_governance_label(tmp_path):
    item = _recommendation()
    item["governance_status"] = "PHYSICIAN_APPROVED"
    service = _PersonalService({"status": "OWNER_REVIEWED", "recommendations": [item]})
    _, body = handle_recommend_v2(
        _context(tmp_path, service), _payload(), host="127.0.0.1"
    )
    assert body["status"] == "BLOCKED"
    assert body["recommendations"] == []


def test_v2_invalid_request_is_400(tmp_path):
    code, body = handle_recommend_v2(
        _context(tmp_path), {"api_version": "2"}, host="127.0.0.1"
    )
    assert code == 400
    assert body["status"] == "ERROR"
    assert body["recommendations"] == []


def test_v2_patient_booleans_are_strict_and_missing_pregnancy_stays_unknown():
    payload = _payload()
    payload["query"]["patient"]["pregnant"] = "false"
    with pytest.raises(RequestError):
        parse_recommend_request(payload)
    payload["query"]["patient"].pop("pregnant")
    request = parse_recommend_request(payload)
    assert request.patient.pregnant is None


def test_fastapi_v2_route_and_health(tmp_path):
    service = _PersonalService({
        "status": "OWNER_REVIEWED",
        "bundle_version": "owner-bundle-1",
        "recommendations": [_recommendation()],
    })
    client = TestClient(create_app(_context(tmp_path, service)), base_url="http://127.0.0.1")
    response = client.post("/v2/recommend", json=_payload())
    assert response.status_code == 200
    assert response.json()["status"] == "OWNER_REVIEWED"
    health = client.get("/v2/personal/health").json()
    assert health["configured"] is True
    assert health["recommendation_eligible"] is True
    assert health["production_mode_changed"] is False


def test_v1_contract_remains_version_one(tmp_path):
    client = TestClient(create_app(_context(tmp_path)))
    response = client.get("/v1/version")
    assert response.status_code == 200
    assert response.json()["api_version"] == "1"


def test_owner_registration_route_is_loopback_only_and_token_is_one_time(tmp_path):
    runtime = PersonalRuntime(tmp_path / "personal")
    client = TestClient(create_app(_context(tmp_path, runtime)), base_url="http://127.0.0.1")
    response = client.post("/v2/personal/register-owner", json={
        "owner_id": "owner-1", "display_name": "Owner Physician",
        "professional_role": "physician", "organisation": "independent practice",
    })
    assert response.status_code == 200
    token = response.json()["session_token"]
    assert token
    assert token not in (tmp_path / "personal" / "owner_profile.json").read_text(encoding="utf-8")

    blocked = client.post(
        "/v2/personal/attest",
        headers={"origin": "https://evil.example"},
        json={},
    )
    assert blocked.status_code == 403
    assert blocked.json()["recommendations"] == []
