from __future__ import annotations

import json
import hashlib

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
    # A forged owner_signature is now caught at bundle load (the activation
    # record pins the digests), so the refusal surfaces as the runtime's
    # REVIEW_REQUIRED envelope instead of the guard's BLOCKED one. The stable
    # code and the empty recommendation list are unchanged.
    assert blocked["status"] in {"BLOCKED", "REVIEW_REQUIRED"}
    assert blocked["recommendations"] == []
    assert blocked["review"]["code"] == "BUNDLE_SIGNATURE_INVALID"
    # ...and the read-only reporting path is gated on the same invariant, so it
    # can no longer report recommendation_eligible=True for a forged bundle.
    assert runtime.health()["recommendation_eligible"] is False
    assert runtime.health()["code"] == "BUNDLE_SIGNATURE_INVALID"


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


def test_runtime_recovers_lost_token_only_before_clinical_artifacts(tmp_path):
    runtime = PersonalRuntime(tmp_path)
    runtime.register_owner({
        "owner_id": "owner-1", "display_name": "Broken Name",
        "professional_role": "physician", "organisation": "Broken Org",
    })

    recovered = runtime.recover_owner({
        "owner_id": "khatiev_turpal",
        "display_name": "Хатиев Турпал Хусаинович",
        "professional_role": "physician",
        "organisation": "МЕГИ",
    })
    profile = json.loads((tmp_path / "owner_profile.json").read_text(encoding="utf-8"))
    assert recovered["status"] == "RECOVERED"
    assert recovered["session_token"] not in json.dumps(profile)
    assert profile["display_name"] == "Хатиев Турпал Хусаинович"
    assert profile["organisation"] == "МЕГИ"

    (tmp_path / "owner_attestations.jsonl").write_text("{}\n", encoding="utf-8")
    try:
        runtime.recover_owner({
            "owner_id": "owner-2", "display_name": "Other",
            "professional_role": "physician", "organisation": "Other",
        })
    except Exception as exc:
        assert getattr(exc, "code", None) == "OWNER_RECOVERY_FORBIDDEN"
    else:
        raise AssertionError("recovery must fail after clinical artifacts exist")


def _write_extracted_candidate_fixture(root, db_path):
    db_path.write_text(json.dumps({
        "drugs_reference": {"amoxicillin": {"forms": [{"form_type": "powder_for_suspension", "concentration_mg_per_ml": 50}]}},
        "recommendations": [{
            "id": "aom_child", "name": "Острый средний отит у детей",
            "mkb10": ["H65.0", "H65.1", "H66.0"], "cr_id": "314", "cr_year": 2024,
            "source_url": "https://cr.minzdrav.gov.ru/recomend/314",
            "scenarios": [{"id": "aom_child_standard", "age_group": "child", "lines": [{
                "line_number": 1, "line_label": "Первая линия", "drugs": [{
                    "drug_ref": "amoxicillin", "route": ["per_os"], "regimens": [{
                        "age_group": "child", "dose_mg_kg_day": 60,
                        "dose_range_mg_kg_day": [50, 60], "freq_per_day": 3,
                        "duration_days": "7-10", "regimen_label": "60 мг/кг/сут в 3 приёма",
                    }],
                }],
            }]}],
        }],
    }, ensure_ascii=False), encoding="utf-8")
    artifact_dir = root / "extracted_candidates"
    artifact_dir.mkdir(parents=True)
    candidates = [{
            "candidate_id": "erc_aom_amox", "review_status": "REVIEW_REQUIRED",
            "calculation_ready": True, "blocking_reasons": [],
            "guideline": {"id": "314", "title": "Отит средний острый", "approval_year": 2024,
                          "status": "CURRENT", "source_url": "https://cr.minzdrav.gov.ru/recomend/314",
                          "pdf_sha256": "sha256:" + "a" * 64},
            "diagnosis": "Острый средний отит у детей", "icd10": ["H65.0", "H65.1", "H66.0"],
            "therapy_line": "first", "drug": "Амоксициллин", "atc": "J01CA04",
            "dose": {"value_min": 50.0, "value_max": 60.0, "unit": "mg/kg/day",
                     "basis": "MG_KG_PER_DAY", "route": "oral",
                     "frequency_min_per_day": 2, "frequency_max_per_day": 3,
                     "duration": "7-10 days", "maximum_dose": "NOT_STATED_IN_TABLE_ROW"},
            "source": {"pdf_path": "C:/secret/current.pdf", "page": 21, "table_index": 0,
                       "table_row": 3, "wording": "Амоксициллин — дети: 50-60 мг/кг/сут в 2-3 приема",
                       "cells": [], "secondary_evidence": [{"page": 25, "wording": "7-10 дней"}]},
        }]
    payload = json.dumps(
        candidates, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    candidates_sha256 = "sha256:" + hashlib.sha256(payload).hexdigest()
    artifact_dir.joinpath("314.json").write_text(json.dumps({
        "schema_version": "1.0.0", "artifact_type": "EXTRACTED_REGIMEN_CANDIDATES",
        "guideline_id": "314", "source_pdf_sha256": "sha256:" + "a" * 64,
        "candidates_sha256": candidates_sha256, "candidates": candidates,
    }, ensure_ascii=False), encoding="utf-8")
    specs = root / "candidate_specs"
    specs.mkdir()
    specs.joinpath("314.json").write_text(json.dumps({
        "guideline_id": "314", "expected_pdf_sha256": "sha256:" + "a" * 64,
        "expected_candidates_sha256": candidates_sha256,
    }), encoding="utf-8")
    return specs


def test_runtime_lists_and_attests_server_loaded_extracted_candidate(tmp_path):
    db_path = tmp_path / "calculator.json"
    specs = _write_extracted_candidate_fixture(tmp_path, db_path)
    runtime = PersonalRuntime(
        tmp_path, calculator_db_path=db_path, candidate_specs_dir=specs
    )
    registration = runtime.register_owner({
        "owner_id": "owner-1", "display_name": "Owner Physician",
        "professional_role": "physician", "organisation": "independent practice",
    })

    listing = runtime.list_extracted_candidates("314")
    candidate = listing["candidates"][0]
    assert "pdf_path" not in candidate["source"]
    assert len(candidate["calculator_options"]) == 1
    result = runtime.attest_extracted_candidate({
        "session_token": registration["session_token"], "guideline_id": "314",
        "candidate_id": "erc_aom_amox",
        "calculator_binding": candidate["calculator_options"][0]["binding"],
        "rationale": "Проверены строка таблицы, суточная доза, кратность и длительность",
    })
    assert result["status"] == "ATTESTED"
    event = json.loads((tmp_path / "owner_attestations.jsonl").read_text(encoding="utf-8"))
    assert event["regimen_payload"]["dose"]["value_min"] == 50.0
    assert "стр. 25" in event["source_quote"]
    assert event["calculator_binding"]["calculator_regimen_sha256"].startswith("sha256:")


def test_runtime_blocks_tampered_extracted_candidate_artifact(tmp_path):
    db_path = tmp_path / "calculator.json"
    specs = _write_extracted_candidate_fixture(tmp_path, db_path)
    artifact_path = tmp_path / "extracted_candidates" / "314.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["candidates"][0]["dose"]["value_max"] = 900.0
    artifact_path.write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")
    runtime = PersonalRuntime(
        tmp_path, calculator_db_path=db_path, candidate_specs_dir=specs
    )
    try:
        runtime.list_extracted_candidates("314")
    except Exception as exc:
        assert getattr(exc, "code", None) == "EXTRACTED_SOURCE_CONTRACT_MISMATCH"
    else:
        raise AssertionError("tampered extracted candidate must fail closed")


def test_runtime_lists_candidate_but_offers_no_binding_for_blocked_disease(tmp_path):
    db_path = tmp_path / "calculator.json"
    specs = _write_extracted_candidate_fixture(tmp_path, db_path)
    db = json.loads(db_path.read_text(encoding="utf-8"))
    db["recommendations"][0]["calculation_blocked"] = True
    db["recommendations"][0]["calculation_block_reason"] = "owner review pending"
    db_path.write_text(json.dumps(db, ensure_ascii=False), encoding="utf-8")
    runtime = PersonalRuntime(
        tmp_path, calculator_db_path=db_path, candidate_specs_dir=specs
    )
    listing = runtime.list_extracted_candidates("314")
    assert listing["candidates"][0]["calculator_options"] == []


def test_calculator_binding_rejects_source_blocked_disease(tmp_path):
    from clinical_engine.personal.calculator_binding import resolve_binding

    db_path = tmp_path / "calculator.json"
    db_path.write_text(json.dumps({"recommendations": [{
        "id": "sinusitis_child", "calculation_blocked": True,
        "calculation_block_reason": "current PDF pending", "scenarios": [],
    }]}), encoding="utf-8")
    try:
        resolve_binding({"disease_id": "sinusitis_child"}, db_path)
    except Exception as exc:
        assert getattr(exc, "code", None) == "CALCULATOR_SOURCE_BLOCKED"
    else:
        raise AssertionError("source-blocked disease must reject calculator binding")


# --- M8: a request refused for calculator drift MUST be audited ---------------


def _activated(tmp_path):
    """Register an owner, attest the fixture regimen and activate a bundle."""
    runtime = PersonalRuntime(tmp_path)
    registration = runtime.register_owner({
        "owner_id": "owner-1", "display_name": "Owner Physician",
        "professional_role": "physician", "organisation": "independent practice",
    })
    token = registration["session_token"]
    attestation = runtime.attest({
        "session_token": token, "regimen_payload": _regimen(), "source_page": 24,
        "source_quote": "Амоксициллин 500–1000 мг 3 раза в сутки.",
        "pdf_sha256": "sha256:" + "a" * 64, "calculator_binding": _binding(),
        "rationale": "reviewed",
    })
    runtime.build_bundle({
        "session_token": token, "attestation_event_ids": [attestation["event_id"]],
        "bundle_version": "owner-1.0", "stale_days": 30,
    })
    request = v2_contract.parse_recommend_request({
        "api_version": "2", "operating_mode": "PERSONAL_PHYSICIAN",
        "owner_id": "owner-1", "session_token": token,
        "query": {
            "diagnosis": "Острый средний отит у детей", "icd10": "H66.0",
            "patient": {"pregnant": False, "renal_function": "normal",
                        "contraindications_cleared": True, "interactions_reviewed": True},
            "preferences": {"population": "child"},
        },
    })
    return runtime, token, request


def test_calculator_binding_drift_refusal_is_written_to_the_request_audit(tmp_path, monkeypatch):
    """M8: the drift refusal returned BEFORE ``_append_request_audit``, so the
    one event an auditor most wants — a request refused because the calculator
    regimen changed after owner attestation — was never recorded."""
    runtime, _token, request = _activated(tmp_path)
    assert runtime.health()["recommendation_eligible"] is True
    audit_path = tmp_path / "request_audit.jsonl"
    assert not audit_path.exists()

    def drifted(binding, _db):
        return {"calculator_regimen_sha256": "sha256:" + "0" * 64}

    monkeypatch.setattr("clinical_engine.personal.runtime.verified_binding", drifted)
    result = runtime.recommend(
        request=request, host="127.0.0.1", origin="http://127.0.0.1:8980"
    )
    monkeypatch.undo()

    assert result["status"] == "REVIEW_REQUIRED"
    assert result["recommendations"] == []
    assert result["review"]["code"] == "CALCULATOR_BINDING_DRIFT"
    assert audit_path.is_file(), "the drift refusal must be audited"
    event = json.loads(audit_path.read_text(encoding="utf-8").splitlines()[-1])
    assert event["status"] == "REVIEW_REQUIRED"
    assert event["review_code"] == "CALCULATOR_BINDING_DRIFT"
    assert event["regimen_ids"] == []


# --- M9: list_attestations must use the hash-chain-verified loader ------------


def test_list_attestations_reports_a_healthy_ledger(tmp_path):
    runtime, _token, _request = _activated(tmp_path)
    listing = runtime.list_attestations()
    assert listing["status"] == "ok"
    assert [item["regimen_id"] for item in listing["attestations"]] == ["sinusitis-amox-adult"]


def test_list_attestations_rejects_a_tampered_ledger_instead_of_reporting_ok(tmp_path):
    """M9: ``list_attestations`` re-read the ledger with raw read_text() +
    json.loads and NO verification, so a tampered ledger was reported
    ``{"status": "ok"}``."""
    runtime, _token, _request = _activated(tmp_path)
    ledger = tmp_path / "owner_attestations.jsonl"
    lines = ledger.read_text(encoding="utf-8").splitlines()
    event = json.loads(lines[0])
    event["rationale"] = "tampered after attestation"
    ledger.write_text(json.dumps(event, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":")) + "\n", encoding="utf-8")
    try:
        runtime.list_attestations()
    except Exception as exc:
        assert getattr(exc, "code", None) == "ATTESTATION_LEDGER_INVALID"
    else:
        raise AssertionError("a tampered ledger must never be reported as healthy")


def test_list_attestations_raises_a_stable_error_on_a_corrupt_line(tmp_path):
    """M9 (b): one corrupt line raised an unhandled JSONDecodeError, which the
    API adapter turned into a 500 instead of a stable domain error."""
    runtime, _token, _request = _activated(tmp_path)
    (tmp_path / "owner_attestations.jsonl").write_text("{not json\n", encoding="utf-8")
    try:
        runtime.list_attestations()
    except Exception as exc:
        assert getattr(exc, "code", None) == "ATTESTATION_LEDGER_INVALID"
    else:
        raise AssertionError("a corrupt ledger line must fail closed")


def test_list_attestations_on_an_absent_ledger_is_empty_not_an_error(tmp_path):
    runtime = PersonalRuntime(tmp_path)
    runtime.register_owner({
        "owner_id": "owner-1", "display_name": "Owner Physician",
        "professional_role": "physician", "organisation": "independent practice",
    })
    assert runtime.list_attestations() == {"status": "ok", "attestations": []}


# --- M12: unstated safety data must be recorded as UNKNOWN, not as "none" -----


def test_extracted_candidate_payload_records_unknown_safety_reasons(tmp_path):
    """M12: the payload hardcoded empty ``contraindications``/``interactions``
    (and an empty ``allergy_classes``), which made
    CONTRAINDICATION_SCREEN_REQUIRED / INTERACTION_SCREEN_REQUIRED /
    ALLERGY_CONTRAINDICATION unreachable — a fail-open on a signal that feeds the
    physician review queue. The dose-table row states none of them, so they are
    now recorded as explicit unknowns."""
    from clinical_engine.personal.extracted_candidates import ExtractedCandidateStore

    specs = _write_extracted_candidate_fixture(tmp_path, tmp_path / "calculator.json")
    store = ExtractedCandidateStore(tmp_path, tmp_path / "calculator.json", specs)
    candidate = store.get("314", "erc_aom_amox")
    payload = store.regimen_payload(candidate)

    assert payload["safety"]["contraindications"] == ["NOT_EXTRACTED_FROM_DOSE_TABLE_ROW"]
    assert payload["safety"]["interactions"] == ["NOT_EXTRACTED_FROM_DOSE_TABLE_ROW"]
    # J01CA04 -> penicillin, so the allergy gate is no longer vacuous
    assert payload["safety"]["allergy_classes"] == ["penicillin"]
    # the pediatric eligibility set the payload does actually claim
    assert payload["population"]["eligible_groups"] == ["child"]


def test_unmapped_atc_yields_an_explicit_unknown_allergy_class(tmp_path):
    from clinical_engine.personal.extracted_candidates import _allergy_class

    assert _allergy_class("J01DD04") == "cephalosporin"
    assert _allergy_class("J01FA10") == "macrolide"
    assert _allergy_class("J99ZZ99") == "allergy_class_not_stated_requires_review"
    assert _allergy_class(None) == "allergy_class_not_stated_requires_review"


def test_attested_extracted_candidate_requires_the_safety_screens(tmp_path):
    """End-to-end: the attested candidate now fails closed until the physician
    explicitly clears contraindications and interactions, because the source
    row never stated them."""
    db_path = tmp_path / "calculator.json"
    specs = _write_extracted_candidate_fixture(tmp_path, db_path)
    runtime = PersonalRuntime(tmp_path, calculator_db_path=db_path, candidate_specs_dir=specs)
    registration = runtime.register_owner({
        "owner_id": "owner-1", "display_name": "Owner Physician",
        "professional_role": "physician", "organisation": "independent practice",
    })
    token = registration["session_token"]
    candidate = runtime.list_extracted_candidates("314")["candidates"][0]
    runtime.attest_extracted_candidate({
        "session_token": token, "guideline_id": "314", "candidate_id": "erc_aom_amox",
        "calculator_binding": candidate["calculator_options"][0]["binding"],
        "rationale": "Проверены строка таблицы, суточная доза, кратность и длительность",
    })
    runtime.build_bundle({
        "session_token": token, "attestation_event_ids": [
            json.loads((tmp_path / "owner_attestations.jsonl").read_text(encoding="utf-8"))["event_id"]
        ],
        "bundle_version": "owner-child-1.0", "stale_days": 30,
    })
    request = v2_contract.parse_recommend_request({
        "api_version": "2", "operating_mode": "PERSONAL_PHYSICIAN",
        "owner_id": "owner-1", "session_token": token,
        "query": {
            "diagnosis": "Острый средний отит у детей", "icd10": "H66.0",
            "patient": {"weight_kg": 18, "renal_function": "normal"},
            "preferences": {"population": "child"},
        },
    })
    result = runtime.recommend(
        request=request, host="127.0.0.1", origin="http://127.0.0.1:8980"
    )
    assert result["status"] == "REVIEW_REQUIRED"
    reasons = result["trace"]["considered_regimens"][0]["rejection_reasons"]
    assert "CONTRAINDICATION_SCREEN_REQUIRED" in reasons
    assert "INTERACTION_SCREEN_REQUIRED" in reasons

    # ...and the allergy gate now fires for a recorded penicillin allergy
    allergic = v2_contract.parse_recommend_request({
        "api_version": "2", "operating_mode": "PERSONAL_PHYSICIAN",
        "owner_id": "owner-1", "session_token": token,
        "query": {
            "diagnosis": "Острый средний отит у детей", "icd10": "H66.0",
            "patient": {"weight_kg": 18, "renal_function": "normal", "allergies": ["penicillin"],
                        "contraindications_cleared": True, "interactions_reviewed": True},
            "preferences": {"population": "child"},
        },
    })
    blocked = runtime.recommend(
        request=allergic, host="127.0.0.1", origin="http://127.0.0.1:8980"
    )
    assert "ALLERGY_CONTRAINDICATION" in (
        blocked["trace"]["considered_regimens"][0]["rejection_reasons"]
    )
