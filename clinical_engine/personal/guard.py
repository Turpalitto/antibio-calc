"""External fail-closed guard for PERSONAL_PHYSICIAN mode."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

from .bundle import compute_owner_signature, sha256_text
from .models import OWNER_BUNDLE_STATUS, PERSONAL_MODE, OwnerProfile, PersonalModeError, PersonalPhysicianBundle


@dataclass(frozen=True, slots=True)
class GuardDecision:
    allowed: bool
    status: str
    code: str
    detail: str


class PersonalPhysicianGuard:
    """Validate local activation without touching Production Guard or Engine."""

    def __init__(
        self,
        *,
        profile: OwnerProfile,
        bundle: PersonalPhysicianBundle,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if profile.owner_id != bundle.owner_id or bundle.status != OWNER_BUNDLE_STATUS:
            raise PersonalModeError("GUARD_CONFIGURATION_INVALID", "profile/bundle identity or status mismatch")
        self._profile = profile
        self._bundle = bundle
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def evaluate(self, *, request: Any, host: str, origin: str) -> GuardDecision:
        mode = _value(_request_value(request, "operating_mode"))
        if mode != PERSONAL_MODE:
            return _blocked("PERSONAL_MODE_NOT_ENABLED", "operating_mode must be PERSONAL_PHYSICIAN")
        if not _loopback_host(host) or not _loopback_origin(origin):
            return _blocked("NON_LOOPBACK_REQUEST", "host and origin must both be loopback")
        if not self._profile.active:
            return _blocked("OWNER_INACTIVE", "physician-owner registration is inactive")
        if not self._profile.request_audit_local or not self._profile.request_audit_append_only:
            return _blocked("AUDIT_POLICY_INVALID", "request audit must be local and append-only")
        if self._profile.persist_patient_data:
            return _blocked("PATIENT_PERSISTENCE_FORBIDDEN", "patient persistence must be disabled")

        owner_id = _personal_value(request, "owner_id")
        if owner_id != self._profile.owner_id:
            return _blocked("OWNER_MISMATCH", "request owner does not match active bundle owner")
        token = _personal_value(request, "mode_token") or _personal_value(request, "session_token")
        if not isinstance(token, str) or not token:
            return _blocked("MODE_TOKEN_MISSING", "local mode token is required")
        if not hmac.compare_digest(sha256_text(token), self._profile.mode_token_sha256):
            return _blocked("MODE_TOKEN_INVALID", "local mode token does not match owner session")
        if not hmac.compare_digest(
            compute_owner_signature(self._bundle.payload_sha256, token),
            self._bundle.owner_signature,
        ):
            return _blocked("BUNDLE_SIGNATURE_INVALID", "bundle owner signature does not match session")
        acknowledgement = _personal_value(request, "acknowledged")
        # The accepted v2 DTO has no separate acknowledgement field. Its
        # explicit operating_mode + owner-bound session_token is the handshake;
        # the API envelope supplies the mandatory non-dismissible banner.
        if acknowledgement is not None and acknowledgement is not True:
            return GuardDecision(
                False,
                "REVIEW_REQUIRED",
                "OWNER_ACKNOWLEDGEMENT_REQUIRED",
                "single-physician experimental-mode acknowledgement is required",
            )

        try:
            now = self._clock()
        except Exception as exc:
            raise PersonalModeError("GUARD_CONFIGURATION_INVALID", "clock failed") from exc
        if not isinstance(now, datetime):
            raise PersonalModeError("GUARD_CONFIGURATION_INVALID", "clock must return datetime")
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        stale_after = _parse_timestamp(self._bundle.stale_after, "stale_after")
        built_at = _parse_timestamp(self._bundle.built_at, "built_at")
        if stale_after <= built_at:
            raise PersonalModeError("BUNDLE_TIME_INVALID", "stale_after must be later than built_at")
        if now >= stale_after:
            return _blocked("BUNDLE_STALE", f"bundle became stale at {self._bundle.stale_after}")
        if any(item.provenance.guideline_status != "CURRENT" for item in self._bundle.regimens):
            return _blocked("GUIDELINE_STATUS_NOT_CURRENT", "all served guidelines must be CURRENT")
        return GuardDecision(True, "OWNER_REVIEWED", "GUARD_PASSED", "personal-mode guard passed")


def _blocked(code: str, detail: str) -> GuardDecision:
    return GuardDecision(False, "BLOCKED", code, detail)


def _loopback_host(value: str) -> bool:
    if not isinstance(value, str) or not value or any(ch.isspace() for ch in value):
        return False
    if value == "::1":
        return True
    try:
        parsed = urlsplit(f"//{value}")
    except ValueError:
        return False
    if parsed.username or parsed.password or parsed.path not in ("",):
        return False
    return (parsed.hostname or "").lower().rstrip(".") in {"localhost", "127.0.0.1", "::1"}


def _loopback_origin(value: str) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        return False
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        return False
    return (parsed.hostname or "").lower().rstrip(".") in {"localhost", "127.0.0.1", "::1"}


def _request_value(request: Any, key: str) -> Any:
    if isinstance(request, Mapping):
        return request.get(key)
    return getattr(request, key, None)


def _personal_value(request: Any, key: str) -> Any:
    direct = _request_value(request, key)
    if direct is not None:
        return direct
    context = _request_value(request, "personal_context")
    if isinstance(context, Mapping):
        return context.get(key)
    return getattr(context, key, None) if context is not None else None


def _value(value: Any) -> Any:
    return getattr(value, "value", value)


def _parse_timestamp(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise PersonalModeError("BUNDLE_TIME_INVALID", f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise PersonalModeError("BUNDLE_TIME_INVALID", f"{field} must include timezone")
    return parsed.astimezone(timezone.utc)


__all__ = ["GuardDecision", "PersonalPhysicianGuard"]
