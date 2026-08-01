from __future__ import annotations

import dataclasses
import json

import pytest

from clinical_engine.personal import (
    PersonalModeError,
    attest,
    build_personal_bundle,
    load_owner_profile,
    load_personal_bundle,
    register_owner,
    sha256_text,
)


def _regimen_payload() -> dict:
    return {
        "regimen_id": "personal-reg-1",
        "diagnosis": "Острый синусит",
        "icd10": ["J01.9"],
        "therapy_line": "first",
        "drug": "амоксициллин",
        "components": ["амоксициллин"],
        "dose": {
            "value_min": 500,
            "value_max": 1000,
            "unit": "mg",
            "basis": "PER_ADMINISTRATION",
            "formulation_basis": "active ingredient",
            "route": "oral",
            "frequency": "3 times/day",
            "duration": "5-7 days",
            "maximum_dose": "NOT_STATED",
        },
        "population": {
            "eligible_groups": ["adult"],
            "adult": "eligible",
            "pediatric": "not in reviewed subset",
            "neonatal": "not in reviewed subset",
            "pregnancy": "source states individual assessment",
            "lactation": "source states individual assessment",
            "renal": "dose adjustment required by renal function",
            "hepatic": "NOT_STATED",
        },
        "safety": {
            "allergy_classes": ["penicillin"],
            "contraindications": ["immediate beta-lactam hypersensitivity"],
            "interactions": [],
            "warnings": ["owner selection required"],
            "requires_weight_kg": False,
            "requires_renal_function": True,
            "requires_pregnancy_status": True,
            "requires_hepatic_function": False,
        },
        "provenance": {
            "guideline_id": "kr-1",
            "guideline_title": "Острый синусит",
            "rubricator_id": "rub-1",
            "rubricator_version": "2025-1",
            "approval_year": 2025,
            "source_url": "https://cr.minzdrav.gov.ru/schema/1",
            "guideline_status": "CURRENT",
        },
        "terminology_mappings": [
            {"source": "Амоксициллин", "normalized": "амоксициллин", "system": "ATC", "code": "J01CA04"}
        ],
        "alternatives": [{"regimen_id": "alt-1", "rejection_reason": "owner did not attest exact source"}],
    }


def _binding() -> dict:
    return {
        "disease_id": "sinusitis_adult",
        "scenario_id": "sinusitis_standard",
        "line_number": 1,
        "route": "per_os",
        "drug_ref": "amoxicillin",
        "regimen_index": 0,
        "binding_version": "1",
        "calculator_regimen_sha256": "sha256:" + "d" * 64,
    }


def _registered(tmp_path):
    return register_owner(
        tmp_path,
        owner_id="owner-1",
        display_name="Owner Physician",
        professional_role="physician",
        organisation="Local practice",
        registered_at="2026-08-01T08:00:00+00:00",
    )


def _attested(tmp_path):
    profile, token = _registered(tmp_path)
    event = attest(
        tmp_path,
        raw_token=token,
        regimen_payload=_regimen_payload(),
        source_page=17,
        source_quote="Амоксициллин 500–1000 мг 3 раза в сутки.",
        pdf_sha256="sha256:" + "a" * 64,
        calculator_binding=_binding(),
        rationale="Exact source and calculator binding reviewed",
        attested_at="2026-08-01T09:00:00+00:00",
    )
    return profile, token, event


def _built(tmp_path):
    profile, token, event = _attested(tmp_path)
    path = build_personal_bundle(
        tmp_path,
        raw_token=token,
        attestation_event_ids=[event["event_id"]],
        bundle_version="owner-1.1",
        build_version="personal-builder-1",
        built_at="2026-08-01T10:00:00+00:00",
        stale_after="2026-09-01T10:00:00+00:00",
    )
    return profile, token, event, path


def test_register_owner_returns_token_but_persists_only_hash(tmp_path):
    profile, raw_token = _registered(tmp_path)
    persisted = (tmp_path / "owner_profile.json").read_text(encoding="utf-8")
    assert raw_token not in persisted
    assert profile.mode_token_sha256 == sha256_text(raw_token)
    assert profile.active and not profile.persist_patient_data
    with pytest.raises(dataclasses.FrozenInstanceError):
        profile.active = False


def test_registration_never_overwrites_existing_owner(tmp_path):
    _registered(tmp_path)
    with pytest.raises(PersonalModeError) as caught:
        _registered(tmp_path)
    assert caught.value.code == "LOCAL_ARTIFACT_EXISTS"


def test_attestation_is_append_only_hash_chained_and_build_is_explicit(tmp_path):
    _, token, first = _attested(tmp_path)
    assert not list(tmp_path.glob("personal_physician_bundle_*.json"))
    second_payload = _regimen_payload()
    second_payload["regimen_id"] = "personal-reg-2"
    second = attest(
        tmp_path,
        raw_token=token,
        regimen_payload=second_payload,
        source_page=18,
        source_quote="Second exact quote",
        pdf_sha256="sha256:" + "b" * 64,
        calculator_binding=_binding(),
        rationale="Second explicit owner attestation",
        attested_at="2026-08-01T09:01:00+00:00",
    )
    lines = [json.loads(line) for line in (tmp_path / "owner_attestations.jsonl").read_text().splitlines()]
    assert [item["sequence"] for item in lines] == [1, 2]
    assert second["previous_event_sha256"] == first["event_sha256"]

    path = build_personal_bundle(
        tmp_path,
        raw_token=token,
        attestation_event_ids=[second["event_id"]],
        bundle_version="explicit-1",
        build_version="builder-1",
        built_at="2026-08-01T10:00:00+00:00",
        stale_after="2026-09-01T10:00:00+00:00",
    )
    bundle = load_personal_bundle(path, profile=load_owner_profile(tmp_path / "owner_profile.json"))
    assert [item.regimen_id for item in bundle.regimens] == ["personal-reg-2"]


def test_bundle_hash_attestation_and_source_dose_semantics_validate(tmp_path):
    profile, _, _, path = _built(tmp_path)
    bundle = load_personal_bundle(path, profile=profile)
    regimen = bundle.regimens[0]
    assert regimen.attestation.attested_payload_sha256 == bundle.payload_sha256
    assert regimen.provenance.source_page == 17
    assert regimen.provenance.source_wording.startswith("Амоксициллин")
    assert (regimen.dose.value_min, regimen.dose.value_max, regimen.dose.basis) == (
        500.0, 1000.0, "PER_ADMINISTRATION"
    )
    assert regimen.calculator_binding.disease_id == "sinusitis_adult"
    with pytest.raises(dataclasses.FrozenInstanceError):
        bundle.bundle_version = "changed"


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda doc: doc.update(status="PHYSICIAN_APPROVED"), "BUNDLE_HASH_MISMATCH"),
        (lambda doc: doc["regimens"][0]["dose"].pop("basis"), "BUNDLE_HASH_MISMATCH"),
        (lambda doc: doc["regimens"][0]["provenance"].pop("source_wording"), "BUNDLE_HASH_MISMATCH"),
        (lambda doc: doc["regimens"][0]["attestation"].update(attested_payload_sha256="sha256:" + "f" * 64), "ATTESTATION_HASH_MISMATCH"),
    ],
)
def test_tampering_fails_closed(tmp_path, mutation, code):
    profile, _, _, path = _built(tmp_path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    mutation(doc)
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(PersonalModeError) as caught:
        load_personal_bundle(path, profile=profile)
    assert caught.value.code == code


def test_rehashed_missing_semantics_still_rejected(tmp_path):
    from clinical_engine.personal import compute_payload_sha256

    profile, _, _, path = _built(tmp_path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["regimens"][0]["dose"].pop("basis")
    digest = compute_payload_sha256(doc)
    doc["payload_sha256"] = digest
    doc["regimens"][0]["attestation"]["attested_payload_sha256"] = digest
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(PersonalModeError) as caught:
        load_personal_bundle(path, profile=profile)
    assert caught.value.code in {"BUNDLE_SCHEMA_INVALID", "DOSE_SEMANTICS_INVALID"}


def test_attest_rejects_wrong_token_and_production_approval_claim(tmp_path):
    _, token = _registered(tmp_path)
    args = dict(
        regimen_payload=_regimen_payload(), source_page=1, source_quote="Exact quote",
        pdf_sha256="sha256:" + "a" * 64, calculator_binding=_binding(), rationale="Reviewed",
    )
    with pytest.raises(PersonalModeError) as caught:
        attest(tmp_path, raw_token="wrong", **args)
    assert caught.value.code == "MODE_TOKEN_INVALID"
    args["regimen_payload"]["status"] = "PHYSICIAN_APPROVED"
    with pytest.raises(PersonalModeError) as caught:
        attest(tmp_path, raw_token=token, **args)
    assert caught.value.code == "PRODUCTION_APPROVAL_FORBIDDEN"


def test_bundle_build_never_overwrites_version(tmp_path):
    _, token, event, _ = _built(tmp_path)
    with pytest.raises(PersonalModeError) as caught:
        build_personal_bundle(
            tmp_path, raw_token=token, attestation_event_ids=[event["event_id"]], bundle_version="owner-1.1",
            build_version="builder-1", built_at="2026-08-01T10:00:00+00:00",
            stale_after="2026-09-01T10:00:00+00:00",
        )
    assert caught.value.code == "LOCAL_ARTIFACT_EXISTS"
