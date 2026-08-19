"""Local runtime and owner-workflow facade for PERSONAL_PHYSICIAN mode.

All mutable artifacts live under a gitignored local directory.  The facade
reloads and validates the active immutable bundle for every recommendation,
then writes a minimized append-only audit event before releasing the result.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from .bundle import (
    attest,
    build_personal_bundle,
    load_owner_profile,
    recover_unactivated_owner,
    register_owner,
    sha256_text,
)
from .models import OWNER_BUNDLE_STATUS, PersonalModeError
from .calculator_binding import DEFAULT_CALCULATOR_DB, verified_binding
from .extracted_candidates import ExtractedCandidateStore
from .recommender import PersonalModeService


DEFAULT_STATE_DIR = Path(__file__).resolve().parents[2] / ".local" / "personal_physician"


class PersonalRuntime:
    """State-dir-backed local service used by the API adapter."""

    def __init__(self, state_dir: str | Path | None = None, *, calculator_db_path: str | Path = DEFAULT_CALCULATOR_DB, candidate_specs_dir: str | Path | None = None) -> None:
        configured = state_dir or os.environ.get("ANTIBIO_PERSONAL_STATE_DIR")
        self.state_dir = Path(configured or DEFAULT_STATE_DIR).resolve()
        self.calculator_db_path = Path(calculator_db_path).resolve()
        self.candidate_specs_dir = Path(candidate_specs_dir).resolve() if candidate_specs_dir else None
        self._lock = threading.RLock()

    @property
    def profile_path(self) -> Path:
        return self.state_dir / "owner_profile.json"

    @property
    def active_pointer_path(self) -> Path:
        return self.state_dir / "active_bundle.json"

    @property
    def extracted_candidates(self) -> ExtractedCandidateStore:
        if self.candidate_specs_dir is None:
            return ExtractedCandidateStore(self.state_dir, self.calculator_db_path)
        return ExtractedCandidateStore(
            self.state_dir, self.calculator_db_path, self.candidate_specs_dir
        )

    def health(self) -> dict[str, Any]:
        base = {
            "status": "blocked",
            "ready": False,
            "recommendation_eligible": False,
            "mode": "PERSONAL_PHYSICIAN",
            "owner_registered": self.profile_path.is_file(),
            "governance_status": OWNER_BUNDLE_STATUS,
            "bundle_version": None,
            "regimen_count": 0,
        }
        try:
            service = self._load_service()
        except PersonalModeError as exc:
            base["code"] = exc.code
            return base
        details = service.health()
        base.update(details)
        base["recommendation_eligible"] = bool(details.get("ready"))
        return base

    def recommend(self, *, request: Any, host: str, origin: str) -> dict[str, Any]:
        try:
            service = self._load_service()
        except PersonalModeError as exc:
            return self._blocked(exc.code, exc.detail)

        result = service.recommend(request=request, host=host, origin=origin)
        for item in result.get("recommendations", []):
            binding = item.get("calculator_binding") if isinstance(item, dict) else None
            if not isinstance(binding, dict) or verified_binding(binding, self.calculator_db_path).get("calculator_regimen_sha256") != binding.get("calculator_regimen_sha256"):
                return self._blocked("CALCULATOR_BINDING_DRIFT", "calculator regimen changed after owner attestation", bundle_version=service.bundle_version)
            item["calculator_binding_verified"] = True
        try:
            self._append_request_audit(request=request, result=result)
        except (OSError, ValueError, TypeError):
            return self._blocked(
                "LOCAL_AUDIT_WRITE_FAILED",
                "local append-only request audit could not be written",
                bundle_version=service.bundle_version,
            )
        return result

    def register_owner(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            profile, token = register_owner(
                self.state_dir,
                owner_id=_required_text(payload, "owner_id"),
                display_name=_required_text(payload, "display_name"),
                professional_role=_required_text(payload, "professional_role"),
                organisation=_required_text(payload, "organisation"),
            )
        return {
            "status": "REGISTERED",
            "owner_id": profile.owner_id,
            "session_token": token,
            "token_displayed_once": True,
            "persist_patient_data": False,
        }

    def recover_owner(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            profile, token = recover_unactivated_owner(
                self.state_dir,
                owner_id=_required_text(payload, "owner_id"),
                display_name=_required_text(payload, "display_name"),
                professional_role=_required_text(payload, "professional_role"),
                organisation=_required_text(payload, "organisation"),
            )
        return {
            "status": "RECOVERED",
            "owner_id": profile.owner_id,
            "session_token": token,
            "token_displayed_once": True,
            "persist_patient_data": False,
        }

    def attest(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            event = attest(
                self.state_dir,
                raw_token=_required_text(payload, "session_token"),
                regimen_payload=_required_object(payload, "regimen_payload"),
                source_page=_required_integer(payload, "source_page"),
                source_quote=_required_text(payload, "source_quote"),
                pdf_sha256=_required_text(payload, "pdf_sha256"),
                calculator_binding=verified_binding(_required_object(payload, "calculator_binding"), self.calculator_db_path),
                rationale=_required_text(payload, "rationale"),
            )
        return {
            "status": "ATTESTED",
            "event_id": event["event_id"],
            "sequence": event["sequence"],
            "governance_status": OWNER_BUNDLE_STATUS,
        }

    def list_extracted_candidates(self, guideline_id: str) -> dict[str, Any]:
        return self.extracted_candidates.list(guideline_id)

    def attest_extracted_candidate(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        guideline_id = _required_text(payload, "guideline_id")
        candidate = self.extracted_candidates.get(
            guideline_id, _required_text(payload, "candidate_id")
        )
        if not candidate.get("calculation_ready") or candidate.get("blocking_reasons"):
            raise PersonalModeError(
                "EXTRACTED_CANDIDATE_AMBIGUOUS",
                ", ".join(candidate.get("blocking_reasons") or ["candidate is not calculation-ready"]),
            )
        binding = self.extracted_candidates.validate_binding(
            candidate, _required_object(payload, "calculator_binding")
        )
        source = candidate["source"]
        secondary = source.get("secondary_evidence") or []
        quote = source["wording"]
        if secondary:
            quote += "\n" + "\n".join(
                f"Дополнительный источник, стр. {item['page']}: {item['wording']}"
                for item in secondary
            )
        with self._lock:
            event = attest(
                self.state_dir,
                raw_token=_required_text(payload, "session_token"),
                regimen_payload=self.extracted_candidates.regimen_payload(candidate),
                source_page=int(source["page"]),
                source_quote=quote,
                pdf_sha256=candidate["guideline"]["pdf_sha256"],
                calculator_binding=binding,
                rationale=_required_text(payload, "rationale"),
            )
        return {
            "status": "ATTESTED",
            "event_id": event["event_id"],
            "sequence": event["sequence"],
            "candidate_id": candidate["candidate_id"],
            "governance_status": OWNER_BUNDLE_STATUS,
        }

    def build_bundle(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        token = _required_text(payload, "session_token")
        profile = load_owner_profile(self.profile_path)
        if not secrets.compare_digest(sha256_text(token), profile.mode_token_sha256):
            raise PersonalModeError("MODE_TOKEN_INVALID", "owner session token does not match")
        event_ids = payload.get("attestation_event_ids")
        if not isinstance(event_ids, list) or any(not isinstance(item, str) for item in event_ids):
            raise PersonalModeError(
                "ATTESTATION_SELECTION_INVALID", "attestation_event_ids must be an array of strings"
            )
        stale_days = payload.get("stale_days", 30)
        if isinstance(stale_days, bool) or not isinstance(stale_days, int) or not 1 <= stale_days <= 365:
            raise PersonalModeError("BUNDLE_TIME_INVALID", "stale_days must be an integer from 1 to 365")
        now = datetime.now(timezone.utc)
        with self._lock:
            bundle_path = build_personal_bundle(
                self.state_dir,
                raw_token=token,
                attestation_event_ids=event_ids,
                bundle_version=_required_text(payload, "bundle_version"),
                build_version=str(payload.get("build_version") or "personal-runtime-1"),
                built_at=now.isoformat(),
                stale_after=(now + timedelta(days=stale_days)).isoformat(),
            )
            self._write_active_pointer(bundle_path)
            service = self._load_service()
        return {
            "status": "ACTIVATED",
            "bundle_version": service.bundle_version,
            "recommendation_eligible": bool(service.health().get("ready")),
            "governance_status": OWNER_BUNDLE_STATUS,
        }

    def list_attestations(self) -> dict[str, Any]:
        path = self.state_dir / "owner_attestations.jsonl"
        events: list[dict[str, Any]] = []
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                raw = json.loads(line)
                events.append({
                    "event_id": raw.get("event_id"),
                    "sequence": raw.get("sequence"),
                    "regimen_id": (raw.get("regimen_payload") or {}).get("regimen_id"),
                    "attested_at": raw.get("attested_at"),
                    "status": raw.get("status"),
                })
        return {"status": "ok", "attestations": events}

    def _load_service(self) -> PersonalModeService:
        if not self.profile_path.is_file():
            raise PersonalModeError("OWNER_NOT_REGISTERED", "local physician-owner is not registered")
        if not self.active_pointer_path.is_file():
            raise PersonalModeError("PERSONAL_BUNDLE_NOT_ACTIVE", "no personal bundle is active")
        try:
            pointer = json.loads(self.active_pointer_path.read_text(encoding="utf-8"))
            filename = pointer["filename"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise PersonalModeError("ACTIVE_BUNDLE_POINTER_INVALID", "active bundle pointer is invalid") from exc
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise PersonalModeError("ACTIVE_BUNDLE_POINTER_INVALID", "active bundle filename is invalid")
        bundle_path = (self.state_dir / filename).resolve()
        if bundle_path.parent != self.state_dir or not bundle_path.is_file():
            raise PersonalModeError("PERSONAL_BUNDLE_NOT_FOUND", "active personal bundle is missing")
        return PersonalModeService.from_paths(self.profile_path, bundle_path)

    def _write_active_pointer(self, bundle_path: Path) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.active_pointer_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"filename": bundle_path.name}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.active_pointer_path)

    def _append_request_audit(self, *, request: Any, result: Mapping[str, Any]) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        path = self.state_dir / "request_audit.jsonl"
        diagnosis = getattr(request, "diagnosis", None)
        icd10 = getattr(request, "icd10", None)
        event = {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "mode": "PERSONAL_PHYSICIAN",
            "owner_id_sha256": _digest(getattr(request, "owner_id", "")),
            "query_sha256": _digest(f"{diagnosis or ''}|{icd10 or ''}"),
            "status": result.get("status"),
            "bundle_version": result.get("bundle_version"),
            "regimen_ids": [
                item.get("regimen_id")
                for item in result.get("recommendations", [])
                if isinstance(item, Mapping)
            ],
            "review_code": (result.get("review") or {}).get("code"),
        }
        with self._lock:
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    @staticmethod
    def _blocked(code: str, detail: str, *, bundle_version: str | None = None) -> dict[str, Any]:
        return {
            "status": "REVIEW_REQUIRED",
            "recommendations": [],
            "bundle_version": bundle_version,
            "review": {"code": code, "detail": detail},
            "trace": {"participating_stages": ["personal_runtime"]},
        }


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _required_text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PersonalModeError("OWNER_WORKFLOW_INPUT_INVALID", f"{key} is required")
    return value.strip()


def _required_integer(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PersonalModeError("OWNER_WORKFLOW_INPUT_INVALID", f"{key} must be a positive integer")
    return value


def _required_object(payload: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise PersonalModeError("OWNER_WORKFLOW_INPUT_INVALID", f"{key} must be an object")
    return value


__all__ = ["DEFAULT_STATE_DIR", "PersonalRuntime"]
