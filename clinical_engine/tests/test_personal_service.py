from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from clinical_engine.api.v2_contract import PatientDTO, PreferencesDTO, V2RecommendRequest
from clinical_engine.api.service import handle_recommend_v2
from clinical_engine.personal import PersonalModeService, PersonalModeError, attest, build_personal_bundle, register_owner


@dataclass(frozen=True)
class _PersonalContext:
    owner_id: str
    mode_token: str
    acknowledged: bool = True


@dataclass(frozen=True)
class _Patient:
    age: float | None = 35
    weight_kg: float | None = 70
    renal_function: str | None = "normal"
    pregnant: bool | None = False
    allergies: tuple[str, ...] = ()
    contraindications_cleared: bool | None = True
    interactions_reviewed: bool | None = True


@dataclass(frozen=True)
class _Query:
    diagnosis: str | None = "Острый синусит"
    icd10: str | None = "J01.9"
    patient: _Patient | None = _Patient()


@dataclass(frozen=True)
class _V2RecommendRequest:
    operating_mode: str
    personal_context: _PersonalContext
    query: _Query


def _payload() -> dict:
    return {
        "regimen_id": "r1", "diagnosis": "Острый синусит", "icd10": ["J01.9"],
        "therapy_line": "first", "drug": "амоксициллин", "components": ["амоксициллин"],
        "dose": {"value_min": 500, "value_max": 1000, "unit": "mg", "basis": "PER_ADMINISTRATION",
                 "formulation_basis": "active ingredient", "route": "oral", "frequency": "3/day",
                 "duration": "5-7 days", "maximum_dose": "NOT_STATED"},
        "population": {"eligible_groups": ["adult"], "adult": "eligible", "pediatric": "NOT_STATED", "neonatal": "NOT_STATED",
                       "pregnancy": "individual assessment", "lactation": "individual assessment",
                       "renal": "renal input required", "hepatic": "NOT_STATED"},
        "safety": {"allergy_classes": ["penicillin"], "contraindications": ["hypersensitivity"],
                   "interactions": [], "warnings": [], "requires_weight_kg": False,
                   "requires_renal_function": True, "requires_pregnancy_status": True,
                   "requires_hepatic_function": False},
        "provenance": {"guideline_id": "g1", "guideline_title": "Guideline", "rubricator_id": "rub1",
                       "rubricator_version": "1", "approval_year": 2025,
                       "source_url": "https://cr.minzdrav.gov.ru/1", "guideline_status": "CURRENT"},
        "terminology_mappings": [{"source": "Амоксициллин", "normalized": "амоксициллин",
                                  "system": "ATC", "code": "J01CA04"}],
        "alternatives": [{"regimen_id": "r2", "rejection_reason": "not owner-attested"}],
    }


def _service(tmp_path):
    _, token = register_owner(
        tmp_path, owner_id="owner-1", display_name="Physician", professional_role="physician",
        organisation="Local", registered_at="2026-08-01T08:00:00+00:00",
    )
    event = attest(
        tmp_path, raw_token=token, regimen_payload=_payload(), source_page=4,
        source_quote="Амоксициллин 500–1000 мг 3 раза в сутки.",
        pdf_sha256="sha256:" + "c" * 64,
        calculator_binding={"disease_id": "sinusitis_adult", "scenario_id": "sinusitis_standard",
                            "line_number": 1, "route": "per_os", "drug_ref": "amoxicillin",
                            "regimen_index": 0, "binding_version": "1",
                            "calculator_regimen_sha256": "sha256:" + "d" * 64},
        rationale="Owner reviewed exact record", attested_at="2026-08-01T09:00:00+00:00",
    )
    bundle = build_personal_bundle(
        tmp_path, raw_token=token, attestation_event_ids=[event["event_id"]], bundle_version="v1",
        build_version="builder-1", built_at="2026-08-01T10:00:00+00:00",
        stale_after="2026-09-01T00:00:00+00:00",
    )
    service = PersonalModeService.from_paths(
        tmp_path / "owner_profile.json", bundle,
        clock=lambda: datetime(2026, 8, 2, tzinfo=timezone.utc),
    )
    return service, token


def _request(token, **context_changes):
    context = {"owner_id": "owner-1", "mode_token": token, "acknowledged": True}
    context.update(context_changes)
    return _V2RecommendRequest("PERSONAL_PHYSICIAN", _PersonalContext(**context), _Query())


def test_stable_positive_service_contract_and_complete_trace(tmp_path):
    service, token = _service(tmp_path)
    result = service.recommend(request=_request(token), host="127.0.0.1:8080", origin="http://localhost:8080")
    assert set(result) == {"status", "recommendations", "bundle_version", "trace"}
    assert result["status"] == "OWNER_REVIEWED"
    assert result["bundle_version"] == "v1"
    assert len(result["recommendations"]) == 1
    rec = result["recommendations"][0]
    assert rec["governance_status"] == "OWNER_REVIEWED_EXPERIMENTAL"
    assert rec["source"]["source_page"] == 4
    assert rec["dose"]["basis"] == "PER_ADMINISTRATION"
    assert rec["calculation"]["performed"] is False
    assert rec["local_mode_banner"]["dismissible"] is False
    assert result["trace"]["dose_calculation"] == "NOT_PERFORMED_SELECT_IN_CALCULATOR"
    assert "trace_serialization" in result["trace"]["participating_stages"]
    assert "APPROVED" not in str(result).replace("OWNER_REVIEWED", "")


def test_exact_v2_contract_is_supported(tmp_path):
    service, token = _service(tmp_path)
    request = V2RecommendRequest(
        api_version="2",
        operating_mode="PERSONAL_PHYSICIAN",
        owner_id="owner-1",
        session_token=token,
        diagnosis="Острый синусит",
        icd10="J01.9",
            patient=PatientDTO(age=35, weight_kg=70, renal_function="normal", pregnant=False, contraindications_cleared=True, interactions_reviewed=True),
            preferences=PreferencesDTO(population="adult"),
    )
    result = service.recommend(
        request=request, host="localhost", origin="http://127.0.0.1:8080"
    )
    assert result["status"] == "OWNER_REVIEWED"
    assert result["recommendations"][0]["regimen_id"] == "r1"


def test_ipv6_loopback_is_supported(tmp_path):
    service, token = _service(tmp_path)
    result = service.recommend(
        request=_request(token), host="::1", origin="http://[::1]:8080"
    )
    assert result["status"] == "OWNER_REVIEWED"


def test_main_api_v2_adapter_accepts_personal_mode_service(tmp_path):
    service, token = _service(tmp_path)
    code, result = handle_recommend_v2(
        SimpleNamespace(personal_service=service),
        {
            "api_version": "2",
            "operating_mode": "PERSONAL_PHYSICIAN",
            "owner_id": "owner-1",
            "session_token": token,
            "query": {
                "diagnosis": "Острый синусит",
                "icd10": "J01.9",
                    "patient": {"age": 35, "weight_kg": 70, "renal_function": "normal", "pregnant": False, "contraindications_cleared": True, "interactions_reviewed": True},
                    "preferences": {"population": "adult"},
            },
        },
        host="localhost",
        origin="http://localhost:8080",
    )
    assert code == 200
    assert result["api_version"] == "2"
    assert result["status"] == "OWNER_REVIEWED"
    assert result["governance_status"] == "OWNER_REVIEWED_EXPERIMENTAL"
    assert result["banner"]["dismissible"] is False


@pytest.mark.parametrize(
    ("host", "origin", "changes", "code"),
    [
        ("antibio.example", "http://localhost", {}, "NON_LOOPBACK_REQUEST"),
        ("localhost", "https://evil.example", {}, "NON_LOOPBACK_REQUEST"),
        ("localhost.evil", "http://localhost", {}, "NON_LOOPBACK_REQUEST"),
        ("localhost", "http://localhost", {"owner_id": "other"}, "OWNER_MISMATCH"),
        ("localhost", "http://localhost", {"mode_token": "wrong"}, "MODE_TOKEN_INVALID"),
        ("localhost", "http://localhost", {"acknowledged": False}, "OWNER_ACKNOWLEDGEMENT_REQUIRED"),
    ],
)
def test_guard_failures_return_empty_stable_result(tmp_path, host, origin, changes, code):
    service, token = _service(tmp_path)
    result = service.recommend(request=_request(token, **changes), host=host, origin=origin)
    assert result["status"] in {"BLOCKED", "REVIEW_REQUIRED"}
    assert result["recommendations"] == []
    assert result["review"]["code"] == code
    assert result["bundle_version"] == "v1"


def test_wrong_mode_is_blocked_not_exception(tmp_path):
    service, token = _service(tmp_path)
    request = _V2RecommendRequest("production", _PersonalContext("owner-1", token), _Query())
    result = service.recommend(request=request, host="localhost", origin="http://localhost")
    assert result["status"] == "BLOCKED"
    assert result["review"]["code"] == "PERSONAL_MODE_NOT_ENABLED"


@pytest.mark.parametrize(
    ("patient", "reason"),
    [
        (_Patient(renal_function=None), "RENAL_FUNCTION_REQUIRED"),
        (_Patient(pregnant=None), "PREGNANCY_STATUS_REQUIRED"),
        (_Patient(allergies=("penicillin",)), "ALLERGY_CONTRAINDICATION"),
        (None, "PATIENT_CONTEXT_MISSING"),
    ],
)
def test_patient_context_failures_are_review_required(tmp_path, patient, reason):
    service, token = _service(tmp_path)
    request = _V2RecommendRequest("PERSONAL_PHYSICIAN", _PersonalContext("owner-1", token), _Query(patient=patient))
    result = service.recommend(request=request, host="localhost", origin="http://127.0.0.1:8080")
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["recommendations"] == []
    assert reason in result["trace"]["considered_regimens"][0]["rejection_reasons"]


def test_unknown_diagnosis_is_review_required_without_fallback(tmp_path):
    service, token = _service(tmp_path)
    request = _V2RecommendRequest(
        "PERSONAL_PHYSICIAN", _PersonalContext("owner-1", token),
        _Query(diagnosis="Unknown", icd10="Z99"),
    )
    result = service.recommend(request=request, host="localhost", origin="http://localhost")
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["review"]["code"] == "NO_OWNER_REVIEWED_REGIMEN"
    assert result["recommendations"] == []


def test_stale_bundle_is_blocked_and_health_reports_not_ready(tmp_path):
    service, token = _service(tmp_path)
    service._guard._clock = lambda: datetime(2026, 10, 1, tzinfo=timezone.utc)
    service._clock = service._guard._clock
    assert service.health()["ready"] is False
    result = service.recommend(request=_request(token), host="localhost", origin="http://localhost")
    assert result["status"] == "BLOCKED"
    assert result["review"]["code"] == "BUNDLE_STALE"


def test_malformed_bundle_raises_stable_personal_mode_error(tmp_path):
    service, _ = _service(tmp_path)
    bundle_path = next(tmp_path.glob("personal_physician_bundle_*.json"))
    bundle_path.write_text("{}", encoding="utf-8")
    with pytest.raises(PersonalModeError) as caught:
        PersonalModeService.from_paths(tmp_path / "owner_profile.json", bundle_path)
    assert caught.value.code == "BUNDLE_SCHEMA_INVALID"
