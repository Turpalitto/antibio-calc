from __future__ import annotations

import json

from clinical_engine.api import v2_contract
from clinical_engine.personal.runtime import PersonalRuntime


def _regimen() -> dict:
    return {
        "regimen_id": "sinusitis-amox-adult",
        "diagnosis": "Острый средний отит у детей",
        "icd10": ["H66.0"],
        "therapy_line": "first",
        "drug": "амоксициллин",
        "components": ["амоксициллин"],
        "dose": {
            "value_min": 500, "value_max": 1000, "unit": "mg",
            "basis": "PER_ADMINISTRATION", "formulation_basis": "active ingredient",
            "route": "oral", "frequency": "3 times/day", "duration": "5-7 days",
            "maximum_dose": "NOT_STATED",
        },
        "population": {
            "eligible_groups": ["child"], "adult": "not reviewed", "pediatric": "eligible", "neonatal": "not reviewed",
            "pregnancy": "individual assessment", "lactation": "individual assessment",
            "renal": "renal input required", "hepatic": "NOT_STATED",
        },
        "safety": {
            "allergy_classes": ["penicillin"], "contraindications": ["hypersensitivity"],
            "interactions": [], "warnings": [], "requires_weight_kg": False,
            "requires_renal_function": True, "requires_pregnancy_status": True,
            "requires_hepatic_function": False,
        },
        "provenance": {
            "guideline_id": "kr-sinusitis", "guideline_title": "Острый синусит",
            "rubricator_id": "rub-1", "rubricator_version": "2026-1", "approval_year": 2026,
            "source_url": "https://cr.minzdrav.gov.ru/clin-rec", "guideline_status": "CURRENT",
        },
        "terminology_mappings": [
            {"source": "Амоксициллин", "normalized": "амоксициллин", "system": "ATC", "code": "J01CA04"}
        ],
        "alternatives": [{"regimen_id": "NONE_STATED", "rejection_reason": "No alternative included in this owner-reviewed subset"}],
    }


def _binding() -> dict:
    return {
        "disease_id": "aom_child", "scenario_id": "aom_child_standard",
        "line_number": 1, "route": "per_os", "drug_ref": "amoxicillin",
        "regimen_index": 0, "binding_version": "1",
    }


def test_runtime_owner_attestation_activation_recommendation_and_minimized_audit(tmp_path):
    runtime = PersonalRuntime(tmp_path)
    assert runtime.health()["code"] == "OWNER_NOT_REGISTERED"

    registration = runtime.register_owner({
        "owner_id": "owner-1", "display_name": "Owner Physician",
        "professional_role": "physician", "organisation": "independent practice",
    })
    token = registration["session_token"]
    assert token not in (tmp_path / "owner_profile.json").read_text(encoding="utf-8")

    attestation = runtime.attest({
        "session_token": token, "regimen_payload": _regimen(), "source_page": 24,
        "source_quote": "Амоксициллин 500–1000 мг 3 раза в сутки.",
        "pdf_sha256": "sha256:" + "a" * 64, "calculator_binding": _binding(),
        "rationale": "Exact source, dose basis and calculator binding reviewed",
    })
    activated = runtime.build_bundle({
        "session_token": token, "attestation_event_ids": [attestation["event_id"]],
        "bundle_version": "owner-1.0", "stale_days": 30,
    })
    assert activated["recommendation_eligible"] is True

    request = v2_contract.parse_recommend_request({
        "api_version": "2", "operating_mode": "PERSONAL_PHYSICIAN",
        "owner_id": "owner-1", "session_token": token,
        "query": {
            "diagnosis": "Острый средний отит у детей", "icd10": "H66.0",
            "patient": {"pregnant": False, "renal_function": "normal", "contraindications_cleared": True, "interactions_reviewed": True},
            "preferences": {"population": "child"},
        },
    })
    result = runtime.recommend(
        request=request, host="127.0.0.1", origin="http://127.0.0.1:8980"
    )
    assert result["status"] == "OWNER_REVIEWED"
    returned_binding = result["recommendations"][0]["calculator_binding"]
    assert all(returned_binding[key] == value for key, value in _binding().items())

    audit_text = (tmp_path / "request_audit.jsonl").read_text(encoding="utf-8")
    assert token not in audit_text
    assert "Острый средний отит у детей" not in audit_text
    audit = json.loads(audit_text)
    assert audit["status"] == "OWNER_REVIEWED"
    assert audit["regimen_ids"] == ["sinusitis-amox-adult"]

    bundle_path = next(tmp_path.glob("personal_physician_bundle_*.json"))
    bundle_doc = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle_doc["owner_signature"] = "hmac-sha256:" + "f" * 64
    bundle_path.write_text(json.dumps(bundle_doc, ensure_ascii=False), encoding="utf-8")
    blocked = runtime.recommend(
        request=request, host="127.0.0.1", origin="http://127.0.0.1:8980"
    )
    assert blocked["status"] == "BLOCKED"
    assert blocked["review"]["code"] == "BUNDLE_SIGNATURE_INVALID"


def test_runtime_never_activates_without_explicit_bundle_build(tmp_path):
    runtime = PersonalRuntime(tmp_path)
    registration = runtime.register_owner({
        "owner_id": "owner-1", "display_name": "Owner Physician",
        "professional_role": "physician", "organisation": "independent practice",
    })
    request = v2_contract.parse_recommend_request({
        "api_version": "2", "operating_mode": "PERSONAL_PHYSICIAN",
        "owner_id": "owner-1", "session_token": registration["session_token"],
        "query": {"diagnosis": "Острый синусит", "patient": {}},
    })
    result = runtime.recommend(request=request, host="localhost", origin="http://localhost:8980")
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["recommendations"] == []
    assert result["review"]["code"] == "PERSONAL_BUNDLE_NOT_ACTIVE"
