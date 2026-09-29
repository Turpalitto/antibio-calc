"""Regression tests for the API-v1 patient-field validation hardening.

API v1 used to coerce ``patient`` fields with bare ``bool()``/``tuple()``. That
fail-opened on safety-relevant fields: a JSON string ``"allergies": "amoxicillin"``
became one allergy per CHARACTER (so a recorded allergy matched nothing and no
contraindication was raised), and ``"pregnant": "false"`` became a pregnant
patient. API v2 already rejected these via ``_string_tuple`` / explicit bool
checks; v1 now does the same.
"""

from __future__ import annotations

import pytest

from clinical_engine.api import contract, v2_contract
from clinical_engine.api.service import ApiContext, handle_recommend
from clinical_engine.corpus.locator import CorpusLocator


def _body(patient: dict, **query) -> dict:
    payload = {"api_version": "1", "query": {"diagnosis": "острый гайморит", "patient": patient}}
    payload["query"].update(query)
    return payload


def _ctx(tmp_path) -> ApiContext:
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "normalized_regimens.sqlite").write_text("", encoding="utf-8")
    (root / "metadata.sqlite").write_text("", encoding="utf-8")
    return ApiContext(corpus=CorpusLocator(root), curated_knowledge_path=str(tmp_path / "k.json"))


# ── the three reported fail-opens ───────────────────────────────────────────


def test_allergies_as_a_bare_string_is_rejected_not_exploded_into_characters():
    """Before: ``tuple("amoxicillin")`` -> ('a','m','o','x',...), so a patient
    allergic to amoxicillin matched nothing and no contraindication was raised."""
    with pytest.raises(contract.RequestError) as exc:
        contract.parse_recommend_request(_body({"allergies": "amoxicillin"}))
    assert exc.value.code == "INVALID_REQUEST"
    assert "array of strings" in exc.value.detail


def test_allergies_of_non_string_items_is_rejected():
    with pytest.raises(contract.RequestError):
        contract.parse_recommend_request(_body({"allergies": ["penicillin", 7]}))


def test_pregnant_as_the_string_false_is_rejected_not_read_as_true():
    """Before: ``bool("false")`` is True, so a client sending the STRING "false"
    silently created a pregnant patient."""
    for value in ("false", "False", "true", "no", 0, 1, ""):
        with pytest.raises(contract.RequestError) as exc:
            contract.parse_recommend_request(_body({"pregnant": value}))
        assert exc.value.code == "INVALID_REQUEST"
        assert "boolean" in exc.value.detail


def test_age_has_real_type_validation():
    with pytest.raises(contract.RequestError) as exc:
        contract.parse_recommend_request(_body({"age": "not-a-number"}))
    assert exc.value.code == "INVALID_REQUEST"
    assert "numeric" in exc.value.detail
    # booleans are not numbers here either
    with pytest.raises(contract.RequestError):
        contract.parse_recommend_request(_body({"age": True}))


# ── the rest of the patient/preference surface ──────────────────────────────


@pytest.mark.parametrize("field", ["age", "weight_kg"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_numbers_are_rejected_in_both_api_versions(field, value):
    """``json.loads`` accepts NaN/Infinity and every comparison against them is
    False, so range validation silently passed them."""
    with pytest.raises(contract.RequestError) as exc:
        contract.parse_recommend_request(_body({field: value}))
    assert "finite" in exc.value.detail
    with pytest.raises(v2_contract.RequestError) as v2_exc:
        v2_contract.parse_recommend_request({
            "api_version": "2", "operating_mode": "PERSONAL_PHYSICIAN",
            "owner_id": "o", "session_token": "t",
            "query": {"diagnosis": "x", "patient": {field: value}},
        })
    assert "finite" in v2_exc.value.detail


def test_weight_kg_must_be_positive_and_age_may_be_zero():
    assert contract.parse_recommend_request(
        _body({"age": 0, "weight_kg": 0.5})
    ).patient.age == 0.0
    with pytest.raises(contract.RequestError) as exc:
        contract.parse_recommend_request(_body({"weight_kg": 0}))
    assert "greater than zero" in exc.value.detail
    with pytest.raises(contract.RequestError) as exc:
        contract.parse_recommend_request(_body({"weight_kg": -1}))
    assert "greater than zero" in exc.value.detail


def test_hepatic_impairment_must_be_a_real_boolean():
    with pytest.raises(contract.RequestError) as exc:
        contract.parse_recommend_request(_body({"hepatic_impairment": "true"}))
    assert "boolean" in exc.value.detail
    assert contract.parse_recommend_request(
        _body({"hepatic_impairment": True})
    ).patient.hepatic_impairment is True


def test_renal_function_must_be_a_string():
    with pytest.raises(contract.RequestError) as exc:
        contract.parse_recommend_request(_body({"renal_function": 3}))
    assert "string" in exc.value.detail
    assert contract.parse_recommend_request(
        _body({"renal_function": "  normal  "})
    ).patient.renal_function == "normal"


def test_current_meds_uses_the_same_rule_as_allergies():
    with pytest.raises(contract.RequestError):
        contract.parse_recommend_request(_body({"current_meds": "warfarin"}))
    assert contract.parse_recommend_request(
        _body({"current_meds": ["warfarin", " "], "allergies": ["Пенициллины"]})
    ).patient.current_meds == ("warfarin",)


def test_diagnosis_and_icd10_must_be_strings():
    with pytest.raises(contract.RequestError) as exc:
        contract.parse_recommend_request(_body({}, diagnosis=42))
    assert "string" in exc.value.detail
    with pytest.raises(contract.RequestError):
        contract.parse_recommend_request({"api_version": "1", "query": {"icd10": ["J01.9"]}})


def test_preference_fields_must_be_strings():
    for field in ("therapy_line", "route_preference", "population"):
        with pytest.raises(contract.RequestError) as exc:
            contract.parse_recommend_request(_body({}, preferences={field: ["a"]}))
        assert "string" in exc.value.detail


def test_valid_v1_request_is_unchanged():
    """The frozen happy path still parses exactly as before."""
    req = contract.parse_recommend_request({
        "api_version": "1",
        "query": {
            "diagnosis": "острый гайморит",
            "patient": {
                "age": 35, "weight_kg": 70, "pregnant": False, "hepatic_impairment": False,
                "renal_function": "normal", "allergies": ["Пенициллины"], "current_meds": [],
            },
            "preferences": {"population": "adult"},
        },
    })
    assert req.diagnosis == "острый гайморит"
    assert req.patient.allergies == ("Пенициллины",)
    assert req.patient.age == 35.0
    assert req.patient.pregnant is False
    assert req.preferences.population == "adult"


# ── the HTTP surface returns 400, not 500 ───────────────────────────────────


def test_handle_recommend_returns_400_for_a_malformed_patient_block(tmp_path):
    code, body = handle_recommend(_ctx(tmp_path), _body({"allergies": "amoxicillin"}))
    assert code == 400
    assert body["status"] == "ERROR"
    assert body["errors"][0]["code"] == "INVALID_REQUEST"


def test_handle_recommend_returns_400_for_the_string_false_pregnancy(tmp_path):
    code, body = handle_recommend(_ctx(tmp_path), _body({"pregnant": "false"}))
    assert code == 400
    assert body["errors"][0]["code"] == "INVALID_REQUEST"
