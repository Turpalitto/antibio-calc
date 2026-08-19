"""Fail-closed JSON loaders and deterministic payload validation."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .models import (
    Alternative,
    CalculatorBinding,
    DoseSemantics,
    OWNER_BUNDLE_STATUS,
    OwnerAttestation,
    OwnerProfile,
    PersonalModeError,
    PersonalPhysicianBundle,
    PersonalRegimen,
    PopulationSemantics,
    Provenance,
    SafetySemantics,
    TerminologyMapping,
)

SCHEMA_VERSION = "1.0.0"
_SHA256_PREFIX = "sha256:"
_HMAC_PREFIX = "hmac-sha256:"
_DOSE_BASES = {
    "PER_ADMINISTRATION",
    "DAILY_TOTAL",
    "MG_KG_PER_ADMINISTRATION",
    "MG_KG_PER_DAY",
}


def sha256_text(value: str) -> str:
    return _SHA256_PREFIX + hashlib.sha256(value.encode("utf-8")).hexdigest()


def compute_payload_sha256(bundle: Mapping[str, Any]) -> str:
    """Hash the canonical clinical payload, excluding only its digest fields.

    RFC 8785 is not assumed. The contract is explicit UTF-8 JSON with sorted
    keys, compact separators, Unicode preserved, and no NaN values.
    """
    projection = {
        key: value for key, value in bundle.items()
        if key not in {"payload_sha256", "owner_signature"}
    }
    projection = _without_attested_payload_digest(projection)
    try:
        canonical = json.dumps(
            projection,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PersonalModeError("BUNDLE_SCHEMA_INVALID", f"payload is not canonical JSON: {exc}") from exc
    return _SHA256_PREFIX + hashlib.sha256(canonical).hexdigest()


def compute_owner_signature(payload_sha256: str, raw_token: str) -> str:
    if not isinstance(raw_token, str) or not raw_token:
        raise PersonalModeError("MODE_TOKEN_INVALID", "owner session token is required")
    return _HMAC_PREFIX + hmac.new(
        raw_token.encode("utf-8"), payload_sha256.encode("ascii"), hashlib.sha256
    ).hexdigest()


def load_owner_profile(path: str | Path) -> OwnerProfile:
    raw = _read_json(path, "PROFILE")
    try:
        profile = OwnerProfile(
            owner_id=_text(raw, "owner_id"),
            display_name=_text(raw, "display_name"),
            professional_role=_text(raw, "professional_role"),
            organisation=_text(raw, "organisation"),
            registered_at=_text(raw, "registered_at"),
            active=_boolean(raw, "active"),
            mode_token_sha256=_sha256(raw, "mode_token_sha256"),
            request_audit_local=_boolean(raw, "request_audit_local"),
            request_audit_append_only=_boolean(raw, "request_audit_append_only"),
            persist_patient_data=_boolean(raw, "persist_patient_data", default=False),
        )
    except PersonalModeError as exc:
        raise PersonalModeError("PROFILE_INVALID", exc.detail) from exc
    if profile.persist_patient_data:
        raise PersonalModeError("PROFILE_INVALID", "persist_patient_data must be false")
    return profile


def load_personal_bundle(path: str | Path, *, profile: OwnerProfile) -> PersonalPhysicianBundle:
    raw = _read_json(path, "BUNDLE")
    _validate_top_level(raw)

    expected_hash = compute_payload_sha256(raw)
    actual_hash = _sha256(raw, "payload_sha256")
    if actual_hash != expected_hash:
        raise PersonalModeError(
            "BUNDLE_HASH_MISMATCH", f"computed {expected_hash}, received {actual_hash}"
        )

    regimens_raw = raw["regimens"]
    regimens = tuple(_parse_regimen(item, index=i) for i, item in enumerate(regimens_raw))
    bundle = PersonalPhysicianBundle(
        schema_version=_text(raw, "schema_version"),
        bundle_version=_text(raw, "bundle_version"),
        build_version=_text(raw, "build_version"),
        status=_text(raw, "status"),
        owner_id=_text(raw, "owner_id"),
        built_at=_text(raw, "built_at"),
        stale_after=_text(raw, "stale_after"),
        payload_sha256=actual_hash,
        owner_signature=_hmac_signature(raw, "owner_signature"),
        regimens=regimens,
    )

    if bundle.schema_version != SCHEMA_VERSION:
        raise PersonalModeError("BUNDLE_SCHEMA_UNSUPPORTED", bundle.schema_version)
    if bundle.status != OWNER_BUNDLE_STATUS:
        raise PersonalModeError("BUNDLE_STATUS_INVALID", bundle.status)
    if bundle.owner_id != profile.owner_id:
        raise PersonalModeError("BUNDLE_OWNER_MISMATCH", "bundle owner does not match profile")
    if not bundle.regimens:
        raise PersonalModeError("BUNDLE_SCHEMA_INVALID", "regimens must not be empty")
    if len({item.regimen_id for item in bundle.regimens}) != len(bundle.regimens):
        raise PersonalModeError("BUNDLE_SCHEMA_INVALID", "duplicate regimen_id")

    for regimen in bundle.regimens:
        if regimen.governance_status != OWNER_BUNDLE_STATUS:
            raise PersonalModeError("REGIMEN_STATUS_INVALID", regimen.regimen_id)
        attestation = regimen.attestation
        if attestation.status != OWNER_BUNDLE_STATUS:
            raise PersonalModeError("ATTESTATION_STATUS_INVALID", regimen.regimen_id)
        if attestation.owner_id != profile.owner_id:
            raise PersonalModeError("ATTESTATION_OWNER_MISMATCH", regimen.regimen_id)
        if attestation.attested_payload_sha256 != actual_hash:
            raise PersonalModeError("ATTESTATION_HASH_MISMATCH", regimen.regimen_id)
    return bundle


def load_personal_service(
    owner_profile_path: str | Path,
    bundle_path: str | Path,
    *,
    clock: Any | None = None,
):
    """Factory kept here to give API composition a single path-based entrypoint."""
    from .recommender import PersonalModeService

    profile = load_owner_profile(owner_profile_path)
    bundle = load_personal_bundle(bundle_path, profile=profile)
    return PersonalModeService(profile=profile, bundle=bundle, clock=clock)


def register_owner(
    local_dir: str | Path,
    *,
    owner_id: str,
    display_name: str,
    professional_role: str,
    organisation: str,
    registered_at: str | None = None,
) -> tuple[OwnerProfile, str]:
    """Create one local owner profile and return its one-time raw session token.

    The raw token is never written. Existing profiles are never overwritten.
    """
    root = Path(local_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    raw_token = secrets.token_urlsafe(32)
    raw = {
        "owner_id": _nonempty_argument(owner_id, "owner_id"),
        "display_name": _nonempty_argument(display_name, "display_name"),
        "professional_role": _nonempty_argument(professional_role, "professional_role"),
        "organisation": _nonempty_argument(organisation, "organisation"),
        "registered_at": registered_at or datetime.now(timezone.utc).isoformat(),
        "active": True,
        "mode_token_sha256": sha256_text(raw_token),
        "request_audit_local": True,
        "request_audit_append_only": True,
        "persist_patient_data": False,
    }
    _write_new_json(root / "owner_profile.json", raw)
    return load_owner_profile(root / "owner_profile.json"), raw_token


def recover_unactivated_owner(
    local_dir: str | Path,
    *,
    owner_id: str,
    display_name: str,
    professional_role: str,
    organisation: str,
    registered_at: str | None = None,
) -> tuple[OwnerProfile, str]:
    """Replace a lost-token profile only before any clinical approval exists."""
    root = Path(local_dir).resolve()
    profile_path = root / "owner_profile.json"
    if not profile_path.is_file():
        raise PersonalModeError("OWNER_NOT_REGISTERED", "owner profile does not exist")
    protected = [
        root / "owner_attestations.jsonl",
        root / "active_bundle.json",
        root / "request_audit.jsonl",
    ]
    protected.extend(root.glob("personal_physician_bundle_*.json"))
    if any(path.exists() for path in protected):
        raise PersonalModeError(
            "OWNER_RECOVERY_FORBIDDEN",
            "owner recovery is allowed only before attestations, bundles, or request audit exist",
        )

    raw_token = secrets.token_urlsafe(32)
    raw = {
        "owner_id": _nonempty_argument(owner_id, "owner_id"),
        "display_name": _nonempty_argument(display_name, "display_name"),
        "professional_role": _nonempty_argument(professional_role, "professional_role"),
        "organisation": _nonempty_argument(organisation, "organisation"),
        "registered_at": registered_at or datetime.now(timezone.utc).isoformat(),
        "active": True,
        "mode_token_sha256": sha256_text(raw_token),
        "request_audit_local": True,
        "request_audit_append_only": True,
        "persist_patient_data": False,
    }
    temporary = profile_path.with_suffix(".recovery.tmp")
    temporary.write_text(
        json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, profile_path)
    return load_owner_profile(profile_path), raw_token


def attest(
    local_dir: str | Path,
    *,
    raw_token: str,
    regimen_payload: Mapping[str, Any],
    source_page: int,
    source_quote: str,
    pdf_sha256: str,
    calculator_binding: Mapping[str, Any],
    rationale: str,
    attested_at: str | None = None,
) -> dict[str, Any]:
    """Append one explicit owner attestation event; never build/approve implicitly."""
    root = Path(local_dir).resolve()
    profile = load_owner_profile(root / "owner_profile.json")
    if not profile.active:
        raise PersonalModeError("OWNER_INACTIVE", "owner profile is inactive")
    if not isinstance(raw_token, str) or not secrets.compare_digest(sha256_text(raw_token), profile.mode_token_sha256):
        raise PersonalModeError("MODE_TOKEN_INVALID", "owner session token does not match")
    if not isinstance(regimen_payload, Mapping):
        raise PersonalModeError("ATTESTATION_INPUT_INVALID", "regimen_payload must be an object")
    if _contains_production_approval(regimen_payload):
        raise PersonalModeError("PRODUCTION_APPROVAL_FORBIDDEN", "personal attestation cannot claim production approval")
    if isinstance(source_page, bool) or not isinstance(source_page, int) or source_page < 1:
        raise PersonalModeError("ATTESTATION_INPUT_INVALID", "source_page must be a positive integer")
    quote = _nonempty_argument(source_quote, "source_quote")
    pdf_digest = _sha256({"pdf_sha256": pdf_sha256}, "pdf_sha256")
    binding = _validate_calculator_binding(calculator_binding)
    ledger_path = root / "owner_attestations.jsonl"
    events = _load_ledger(ledger_path)
    previous = events[-1]["event_sha256"] if events else None
    snapshot_digest = _hash_json({"pdf_sha256": pdf_digest, "source_page": source_page, "source_quote": quote})
    event: dict[str, Any] = {
        "event_id": str(uuid.uuid4()),
        "sequence": len(events) + 1,
        "owner_id": profile.owner_id,
        "attested_at": attested_at or datetime.now(timezone.utc).isoformat(),
        "rationale": _nonempty_argument(rationale, "rationale"),
        "status": OWNER_BUNDLE_STATUS,
        "previous_event_sha256": previous,
        "source_snapshot_sha256": snapshot_digest,
        "source_page": source_page,
        "source_quote": quote,
        "pdf_sha256": pdf_digest,
        "calculator_binding": binding,
        "regimen_payload": json.loads(json.dumps(regimen_payload, ensure_ascii=False, allow_nan=False)),
    }
    event["event_sha256"] = _hash_json(event)
    _append_json_line(ledger_path, event)
    return json.loads(json.dumps(event, ensure_ascii=False))


def build_personal_bundle(
    local_dir: str | Path,
    *,
    raw_token: str,
    attestation_event_ids: tuple[str, ...] | list[str],
    bundle_version: str,
    build_version: str,
    stale_after: str,
    built_at: str | None = None,
) -> Path:
    """Build one immutable version from an explicit, non-empty event allowlist."""
    root = Path(local_dir).resolve()
    profile = load_owner_profile(root / "owner_profile.json")
    if not isinstance(raw_token, str) or not secrets.compare_digest(
        sha256_text(raw_token), profile.mode_token_sha256
    ):
        raise PersonalModeError("MODE_TOKEN_INVALID", "owner session token does not match")
    event_ids = tuple(attestation_event_ids)
    if not event_ids or len(set(event_ids)) != len(event_ids):
        raise PersonalModeError("ATTESTATION_SELECTION_INVALID", "event IDs must be non-empty and unique")
    events = _load_ledger(root / "owner_attestations.jsonl")
    by_id = {event["event_id"]: event for event in events}
    missing = sorted(set(event_ids).difference(by_id))
    if missing:
        raise PersonalModeError("ATTESTATION_NOT_FOUND", ", ".join(missing))

    regimens: list[dict[str, Any]] = []
    for event_id in event_ids:
        event = by_id[event_id]
        if event["owner_id"] != profile.owner_id or event["status"] != OWNER_BUNDLE_STATUS:
            raise PersonalModeError("ATTESTATION_INVALID", event_id)
        regimen = json.loads(json.dumps(event["regimen_payload"], ensure_ascii=False))
        provenance = regimen.get("provenance")
        if not isinstance(provenance, dict):
            raise PersonalModeError("ATTESTATION_INPUT_INVALID", f"{event_id}: provenance missing")
        provenance.update({
            "source_pdf_sha256": event["pdf_sha256"],
            "source_page": event["source_page"],
            "source_wording": event["source_quote"],
        })
        regimen["provenance"] = provenance
        regimen["calculator_binding"] = event["calculator_binding"]
        regimen["governance_status"] = OWNER_BUNDLE_STATUS
        regimen["attestation"] = {
            "event_id": event["event_id"],
            "event_sha256": event["event_sha256"],
            "owner_id": profile.owner_id,
            "attested_at": event["attested_at"],
            "rationale": event["rationale"],
            "source_snapshot_sha256": event["source_snapshot_sha256"],
            "attested_payload_sha256": _SHA256_PREFIX + "0" * 64,
            "status": OWNER_BUNDLE_STATUS,
        }
        regimens.append(regimen)

    raw_bundle: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "bundle_version": _nonempty_argument(bundle_version, "bundle_version"),
        "build_version": _nonempty_argument(build_version, "build_version"),
        "status": OWNER_BUNDLE_STATUS,
        "owner_id": profile.owner_id,
        "built_at": built_at or datetime.now(timezone.utc).isoformat(),
        "stale_after": _nonempty_argument(stale_after, "stale_after"),
        "payload_sha256": _SHA256_PREFIX + "0" * 64,
        "owner_signature": _HMAC_PREFIX + "0" * 64,
        "regimens": regimens,
    }
    digest = compute_payload_sha256(raw_bundle)
    raw_bundle["payload_sha256"] = digest
    raw_bundle["owner_signature"] = compute_owner_signature(digest, raw_token)
    for regimen in raw_bundle["regimens"]:
        regimen["attestation"]["attested_payload_sha256"] = digest

    safe_version = raw_bundle["bundle_version"].replace("/", "_").replace("\\", "_")
    target = root / f"personal_physician_bundle_{safe_version}.json"
    _write_new_json(target, raw_bundle)
    # Re-read through all semantic gates before exposing the path.
    load_personal_bundle(target, profile=profile)
    return target


def _read_json(path: str | Path, kind: str) -> dict[str, Any]:
    source = Path(path)
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PersonalModeError(f"{kind}_INVALID_JSON", str(exc)) from exc
    if not isinstance(raw, dict):
        raise PersonalModeError(f"{kind}_SCHEMA_INVALID", "root must be an object")
    return raw


def _validate_top_level(raw: Mapping[str, Any]) -> None:
    required = {
        "schema_version", "bundle_version", "build_version", "status", "owner_id",
        "built_at", "stale_after", "payload_sha256", "owner_signature", "regimens",
    }
    missing = sorted(required.difference(raw))
    if missing:
        raise PersonalModeError("BUNDLE_SCHEMA_INVALID", f"missing fields: {', '.join(missing)}")
    _reject_unknown(raw, required, "bundle")
    if not isinstance(raw["regimens"], list):
        raise PersonalModeError("BUNDLE_SCHEMA_INVALID", "regimens must be an array")


def _parse_regimen(raw: Any, *, index: int) -> PersonalRegimen:
    if not isinstance(raw, dict):
        raise PersonalModeError("BUNDLE_SCHEMA_INVALID", f"regimens[{index}] must be an object")
    prefix = f"regimens[{index}]"
    _reject_unknown(raw, {"regimen_id","diagnosis","icd10","therapy_line","drug","components","dose","population","safety","provenance","terminology_mappings","alternatives","calculator_binding","attestation","governance_status"}, prefix)
    try:
        provenance_raw = _object(raw, "provenance")
        dose_raw = _object(raw, "dose")
        population_raw = _object(raw, "population")
        safety_raw = _object(raw, "safety")
        attestation_raw = _object(raw, "attestation")

        dose = DoseSemantics(
            value_min=_number(dose_raw, "value_min"),
            value_max=_number(dose_raw, "value_max"),
            unit=_text(dose_raw, "unit"),
            basis=_text(dose_raw, "basis"),
            formulation_basis=_text(dose_raw, "formulation_basis"),
            route=_text(dose_raw, "route"),
            frequency=_text(dose_raw, "frequency"),
            duration=_text(dose_raw, "duration"),
            maximum_dose=_text(dose_raw, "maximum_dose"),
        )
        if dose.value_min <= 0 or dose.value_max < dose.value_min:
            raise PersonalModeError("DOSE_SEMANTICS_INVALID", f"{prefix}.dose range")
        if dose.basis not in _DOSE_BASES:
            raise PersonalModeError("DOSE_SEMANTICS_INVALID", f"{prefix}.dose.basis")

        provenance = Provenance(
            guideline_id=_text(provenance_raw, "guideline_id"),
            guideline_title=_text(provenance_raw, "guideline_title"),
            rubricator_id=_text(provenance_raw, "rubricator_id"),
            rubricator_version=_text(provenance_raw, "rubricator_version"),
            approval_year=_integer(provenance_raw, "approval_year"),
            source_url=_text(provenance_raw, "source_url"),
            source_pdf_sha256=_sha256(provenance_raw, "source_pdf_sha256"),
            source_page=_integer(provenance_raw, "source_page"),
            source_wording=_text(provenance_raw, "source_wording"),
            guideline_status=_text(provenance_raw, "guideline_status"),
        )
        if provenance.approval_year < 1900 or provenance.source_page < 1:
            raise PersonalModeError("PROVENANCE_INVALID", prefix)
        if not provenance.source_url.startswith(("https://", "http://")):
            raise PersonalModeError("PROVENANCE_INVALID", f"{prefix}.provenance.source_url")

        population = PopulationSemantics(eligible_groups=_strings(population_raw, "eligible_groups", nonempty=True), **{
            key: _text(population_raw, key)
            for key in ("adult", "pediatric", "neonatal", "pregnancy", "lactation", "renal", "hepatic")
        })
        safety = SafetySemantics(
            allergy_classes=_strings(safety_raw, "allergy_classes"),
            contraindications=_strings(safety_raw, "contraindications"),
            interactions=_strings(safety_raw, "interactions"),
            warnings=_strings(safety_raw, "warnings"),
            requires_weight_kg=_boolean(safety_raw, "requires_weight_kg"),
            requires_renal_function=_boolean(safety_raw, "requires_renal_function"),
            requires_pregnancy_status=_boolean(safety_raw, "requires_pregnancy_status"),
            requires_hepatic_function=_boolean(safety_raw, "requires_hepatic_function"),
        )
        mappings = tuple(_parse_mapping(value) for value in _array(raw, "terminology_mappings", nonempty=True))
        alternatives = tuple(_parse_alternative(value) for value in _array(raw, "alternatives", nonempty=True))
        binding_raw = _object(raw, "calculator_binding")
        calculator_binding = CalculatorBinding(**_validate_calculator_binding(binding_raw))
        attestation = OwnerAttestation(
            event_id=_text(attestation_raw, "event_id"),
            event_sha256=_sha256(attestation_raw, "event_sha256"),
            owner_id=_text(attestation_raw, "owner_id"),
            attested_at=_text(attestation_raw, "attested_at"),
            rationale=_text(attestation_raw, "rationale"),
            source_snapshot_sha256=_sha256(attestation_raw, "source_snapshot_sha256"),
            attested_payload_sha256=_sha256(attestation_raw, "attested_payload_sha256"),
            status=_text(attestation_raw, "status"),
        )
        return PersonalRegimen(
            regimen_id=_text(raw, "regimen_id"),
            diagnosis=_text(raw, "diagnosis"),
            icd10=_strings(raw, "icd10", nonempty=True),
            therapy_line=_text(raw, "therapy_line"),
            drug=_text(raw, "drug"),
            components=_strings(raw, "components", nonempty=True),
            dose=dose,
            population=population,
            safety=safety,
            provenance=provenance,
            terminology_mappings=mappings,
            alternatives=alternatives,
            calculator_binding=calculator_binding,
            attestation=attestation,
            governance_status=_text(raw, "governance_status"),
        )
    except PersonalModeError:
        raise
    except (TypeError, ValueError) as exc:
        raise PersonalModeError("BUNDLE_SCHEMA_INVALID", f"{prefix}: {exc}") from exc


def _parse_mapping(raw: Any) -> TerminologyMapping:
    if not isinstance(raw, dict):
        raise PersonalModeError("TERMINOLOGY_MAPPING_INVALID", "mapping must be object")
    code = raw.get("code")
    if code is not None and (not isinstance(code, str) or not code.strip()):
        raise PersonalModeError("TERMINOLOGY_MAPPING_INVALID", "code must be non-empty or null")
    return TerminologyMapping(
        source=_text(raw, "source"), normalized=_text(raw, "normalized"),
        system=_text(raw, "system"), code=code,
    )


def _parse_alternative(raw: Any) -> Alternative:
    if not isinstance(raw, dict):
        raise PersonalModeError("BUNDLE_SCHEMA_INVALID", "alternative must be object")
    return Alternative(regimen_id=_text(raw, "regimen_id"), rejection_reason=_text(raw, "rejection_reason"))


def _validate_calculator_binding(raw: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise PersonalModeError("CALCULATOR_BINDING_INVALID", "calculator_binding must be an object")
    drug_ref = raw.get("drug_ref")
    combo_ref = raw.get("combo_ref")
    has_drug = isinstance(drug_ref, str) and bool(drug_ref.strip())
    has_combo = isinstance(combo_ref, (list, tuple)) and bool(combo_ref) and all(
        isinstance(item, str) and item.strip() for item in combo_ref
    )
    if has_drug == has_combo:
        raise PersonalModeError(
            "CALCULATOR_BINDING_INVALID", "exactly one of drug_ref or combo_ref is required"
        )
    regimen_label = raw.get("regimen_label")
    regimen_index = raw.get("regimen_index")
    has_label = isinstance(regimen_label, str) and bool(regimen_label.strip())
    has_index = isinstance(regimen_index, int) and not isinstance(regimen_index, bool) and regimen_index >= 0
    if not has_label and not has_index:
        raise PersonalModeError(
            "CALCULATOR_BINDING_INVALID", "regimen_label or non-negative regimen_index is required"
        )
    line_number = raw.get("line_number")
    if isinstance(line_number, bool) or not isinstance(line_number, int) or line_number < 1:
        raise PersonalModeError("CALCULATOR_BINDING_INVALID", "line_number must be a positive integer")
    return {
        "disease_id": _text(raw, "disease_id"),
        "scenario_id": _text(raw, "scenario_id"),
        "line_number": line_number,
        "route": _text(raw, "route"),
        "drug_ref": drug_ref.strip() if has_drug else None,
        "combo_ref": tuple(item.strip() for item in combo_ref) if has_combo else (),
        "regimen_label": regimen_label.strip() if has_label else None,
        "regimen_index": regimen_index if has_index else None,
        "binding_version": _text(raw, "binding_version"),
        "calculator_regimen_sha256": _sha256(raw, "calculator_regimen_sha256"),
    }


def _without_attested_payload_digest(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_attested_payload_digest(item)
            for key, item in value.items()
            if key != "attested_payload_sha256"
        }
    if isinstance(value, list):
        return [_without_attested_payload_digest(item) for item in value]
    return value


def _hash_json(value: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return _SHA256_PREFIX + hashlib.sha256(canonical).hexdigest()


def _write_new_json(path: Path, value: Mapping[str, Any]) -> None:
    data = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise PersonalModeError("LOCAL_ARTIFACT_EXISTS", f"refusing to overwrite {path}") from exc
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)


def _append_json_line(path: Path, value: Mapping[str, Any]) -> None:
    data = (json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        written = os.write(fd, data)
        if written != len(data):
            raise PersonalModeError("ATTESTATION_WRITE_FAILED", "incomplete ledger append")
        os.fsync(fd)
    finally:
        os.close(fd)


def _load_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    previous: str | None = None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise PersonalModeError("ATTESTATION_LEDGER_INVALID", str(exc)) from exc
    for index, line in enumerate(lines, 1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PersonalModeError("ATTESTATION_LEDGER_INVALID", f"line {index}: {exc}") from exc
        if not isinstance(event, dict):
            raise PersonalModeError("ATTESTATION_LEDGER_INVALID", f"line {index}: not an object")
        actual = event.get("event_sha256")
        unsigned = {key: value for key, value in event.items() if key != "event_sha256"}
        if actual != _hash_json(unsigned) or event.get("previous_event_sha256") != previous:
            raise PersonalModeError("ATTESTATION_LEDGER_INVALID", f"line {index}: hash chain mismatch")
        if event.get("sequence") != index:
            raise PersonalModeError("ATTESTATION_LEDGER_INVALID", f"line {index}: sequence mismatch")
        events.append(event)
        previous = actual
    return events


def _contains_production_approval(value: Any) -> bool:
    forbidden = {"APPROVED", "PHYSICIAN_APPROVED", "PUBLISHED", "PRODUCTION_CURATED"}
    if isinstance(value, str):
        return value.upper() in forbidden
    if isinstance(value, Mapping):
        return any(_contains_production_approval(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_production_approval(item) for item in value)
    return False


def _nonempty_argument(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PersonalModeError("LOCAL_INPUT_INVALID", f"{field} must be a non-empty string")
    return value.strip()


def _text(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PersonalModeError("BUNDLE_SCHEMA_INVALID", f"{key} must be a non-empty string")
    return value.strip()


def _sha256(raw: Mapping[str, Any], key: str) -> str:
    value = _text(raw, key).lower()
    if not value.startswith(_SHA256_PREFIX) or len(value) != len(_SHA256_PREFIX) + 64:
        raise PersonalModeError("BUNDLE_SCHEMA_INVALID", f"{key} must be sha256:<64 hex>")
    try:
        int(value[len(_SHA256_PREFIX):], 16)
    except ValueError as exc:
        raise PersonalModeError("BUNDLE_SCHEMA_INVALID", f"{key} must be sha256:<64 hex>") from exc
    return value


def _hmac_signature(raw: Mapping[str, Any], key: str) -> str:
    value = _text(raw, key).lower()
    if not value.startswith(_HMAC_PREFIX) or len(value) != len(_HMAC_PREFIX) + 64:
        raise PersonalModeError("BUNDLE_SIGNATURE_INVALID", f"{key} must be hmac-sha256:<64 hex>")
    try:
        int(value[len(_HMAC_PREFIX):], 16)
    except ValueError as exc:
        raise PersonalModeError(
            "BUNDLE_SIGNATURE_INVALID", f"{key} must be hmac-sha256:<64 hex>"
        ) from exc
    return value


def _number(raw: Mapping[str, Any], key: str) -> float:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PersonalModeError("DOSE_SEMANTICS_INVALID", f"{key} must be numeric")
    return float(value)


def _integer(raw: Mapping[str, Any], key: str) -> int:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise PersonalModeError("BUNDLE_SCHEMA_INVALID", f"{key} must be integer")
    return value


def _boolean(raw: Mapping[str, Any], key: str, *, default: bool | None = None) -> bool:
    value = raw.get(key, default)
    if not isinstance(value, bool):
        raise PersonalModeError("BUNDLE_SCHEMA_INVALID", f"{key} must be boolean")
    return value


def _object(raw: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise PersonalModeError("BUNDLE_SCHEMA_INVALID", f"{key} must be an object")
    return value


def _array(raw: Mapping[str, Any], key: str, *, nonempty: bool = False) -> list[Any]:
    value = raw.get(key)
    if not isinstance(value, list) or (nonempty and not value):
        requirement = "a non-empty array" if nonempty else "an array"
        raise PersonalModeError("BUNDLE_SCHEMA_INVALID", f"{key} must be {requirement}")
    return value


def _reject_unknown(raw: Mapping[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(raw).difference(allowed))
    if unknown:
        raise PersonalModeError("BUNDLE_SCHEMA_INVALID", f"{path}: unknown fields: {', '.join(unknown)}")


def _strings(raw: Mapping[str, Any], key: str, *, nonempty: bool = False) -> tuple[str, ...]:
    values = _array(raw, key, nonempty=nonempty)
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise PersonalModeError("BUNDLE_SCHEMA_INVALID", f"{key} items must be non-empty strings")
    return tuple(value.strip() for value in values)


__all__ = [
    "SCHEMA_VERSION", "attest", "build_personal_bundle", "compute_owner_signature", "compute_payload_sha256",
    "load_owner_profile", "load_personal_bundle", "load_personal_service",
    "recover_unactivated_owner", "register_owner", "sha256_text",
]
