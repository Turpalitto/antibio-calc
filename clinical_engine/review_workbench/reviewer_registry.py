"""Reviewer registration and the canonical reviewer-identity validation contract.

Real reviewers (Reviewer A, Reviewer B, Adjudicator, Medical QA Lead) must be
registered by the owner with real professional information before any
clinical decision may be submitted. This module never fabricates or
pre-populates a reviewer record.

This is the single, canonical identity system for the Review Workbench —
`ReviewService` must depend on it rather than accepting free-text reviewer
strings (GOV-001).

It also owns reviewer *session tokens* (see :meth:`ReviewerRegistry.issue_session_token`).
Registration answers "is this reviewer_id string a registered person?";
it never answered "is the caller that reviewer?", which is why the HTTP surface
used to trust whatever `reviewer_id` a request body carried. Only the SHA-256
of a session token is persisted, comparisons are `hmac.compare_digest`, and
the raw token is returned exactly once and never stored.
"""

from __future__ import annotations

import hmac
import json
import secrets
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .auth import OWNER_SESSION, match_token_digest, sha256_text
from .models import ReviewRole, TargetType


class ReviewerRegistrationError(RuntimeError):
    pass


# Deterministic failure reason codes (Phase 2).
REVIEWER_NOT_REGISTERED = "REVIEWER_NOT_REGISTERED"
REVIEWER_INACTIVE = "REVIEWER_INACTIVE"
ROLE_NOT_AUTHORISED = "ROLE_NOT_AUTHORISED"
SCOPE_NOT_AUTHORISED = "SCOPE_NOT_AUTHORISED"
CREDENTIAL_EXPIRED = "CREDENTIAL_EXPIRED"
SELF_REVIEW_FORBIDDEN = "SELF_REVIEW_FORBIDDEN"
ADMIN_CLINICAL_ACTION_FORBIDDEN = "ADMIN_CLINICAL_ACTION_FORBIDDEN"

CLINICAL_ROLES = frozenset({
    ReviewRole.REVIEWER_A, ReviewRole.REVIEWER_B, ReviewRole.ADJUDICATOR, ReviewRole.MEDICAL_QA_LEAD,
})

# Actions an ADMINISTRATOR may never perform — clinical review/decision actions.
# "add_note", "assign", "view_packet", "request_adjudication" remain administrative/operational
# and are not blocked here; "administer" is always allowed.
CLINICAL_ACTIONS = frozenset({
    "claim", "submit_first", "submit_second", "adjudicate", "qa_signoff", "close", "waive",
})


@dataclass(frozen=True, slots=True)
class ReviewerRecord:
    reviewer_id: str
    display_name: str
    professional_role: str
    credential_reference: str
    organisation: str
    authorised_scope: tuple[str, ...]
    target_type_scope: tuple[str, ...]  # empty = all target types authorised
    active: bool
    registered_at: str
    registered_by: str
    credential_expires_at: str  # empty = does not expire
    version: int


@dataclass(frozen=True, slots=True)
class ReviewerActionResult:
    """Deterministic result of validate_reviewer_action (Phase 1)."""
    allowed: bool
    reason_code: str
    reviewer_record_version: int
    role: str
    scope: tuple[str, ...]
    checked_at: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReviewerRegistry:
    """SQLite-backed reviewer registry, separate from the review-task database."""

    def __init__(self, path: str | Path = "reviewer_registry.sqlite") -> None:
        self.path = str(path)
        self._lock = threading.RLock()
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS reviewers(
                reviewer_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                professional_role TEXT NOT NULL,
                credential_reference TEXT NOT NULL DEFAULT '',
                organisation TEXT NOT NULL,
                authorised_scope TEXT NOT NULL,
                target_type_scope TEXT NOT NULL DEFAULT '[]',
                active INTEGER NOT NULL DEFAULT 1,
                registered_at TEXT NOT NULL,
                registered_by TEXT NOT NULL,
                credential_expires_at TEXT NOT NULL DEFAULT '',
                version INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS reviewer_sessions(
                session_id TEXT PRIMARY KEY,
                reviewer_id TEXT NOT NULL UNIQUE,
                token_sha256 TEXT NOT NULL,
                issued_at TEXT NOT NULL
            );
            """
        )
        self.connection.commit()

    def close(self) -> None:
        with self._lock:
            self.connection.close()

    def __enter__(self) -> "ReviewerRegistry":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def register(
        self,
        *,
        reviewer_id: str,
        display_name: str,
        professional_role: str,
        organisation: str,
        authorised_scope: tuple[ReviewRole, ...],
        registered_at: str,
        registered_by: str,
        credential_reference: str = "",
        target_type_scope: tuple[TargetType, ...] = (),
        credential_expires_at: str = "",
    ) -> ReviewerRecord:
        if not reviewer_id.strip() or not display_name.strip():
            raise ReviewerRegistrationError("reviewer_id and display_name are required")
        if not organisation.strip():
            raise ReviewerRegistrationError("organisation is required")
        if not authorised_scope:
            raise ReviewerRegistrationError("authorised_scope must include at least one role")
        if not registered_by.strip():
            raise ReviewerRegistrationError("registered_by (owner/authority performing registration) is required")
        with self._lock:
            existing = self.connection.execute(
                "SELECT 1 FROM reviewers WHERE reviewer_id=?", (reviewer_id,)
            ).fetchone()
            if existing:
                raise ReviewerRegistrationError(f"reviewer_id already registered: {reviewer_id}")
            self.connection.execute(
                """INSERT INTO reviewers
                   (reviewer_id, display_name, professional_role, credential_reference,
                    organisation, authorised_scope, target_type_scope, active, registered_at,
                    registered_by, credential_expires_at, version)
                   VALUES (?,?,?,?,?,?,?,1,?,?,?,1)""",
                (
                    reviewer_id, display_name, professional_role, credential_reference,
                    organisation, json.dumps([r.value for r in authorised_scope]),
                    json.dumps([t.value for t in target_type_scope]),
                    registered_at, registered_by, credential_expires_at,
                ),
            )
            self.connection.commit()
        return self.get(reviewer_id)

    def get(self, reviewer_id: str) -> ReviewerRecord:
        row = self.connection.execute(
            "SELECT * FROM reviewers WHERE reviewer_id=?", (reviewer_id,)
        ).fetchone()
        if row is None:
            raise ReviewerRegistrationError(f"Unknown reviewer_id: {reviewer_id}")
        return self._row_to_record(row)

    def deactivate(self, reviewer_id: str) -> None:
        with self._lock:
            cur = self.connection.execute(
                "UPDATE reviewers SET active=0, version=version+1 WHERE reviewer_id=?", (reviewer_id,)
            )
            self.connection.commit()
            if cur.rowcount == 0:
                raise ReviewerRegistrationError(f"Unknown reviewer_id: {reviewer_id}")

    # --- session tokens (authentication) -------------------------------------
    #
    # Same shape as PERSONAL_PHYSICIAN owner sessions: a `secrets.token_urlsafe(32)`
    # raw token, of which only the SHA-256 is persisted, compared with
    # `hmac.compare_digest`, returned to the caller exactly once and never
    # written to the review database, the review audit log, or any file.

    def issue_session_token(self, reviewer_id: str) -> str:
        """Mint (or re-mint) a session token and return the raw value once.

        Re-issuing replaces the previous digest, so a token handed out earlier
        stops working immediately. Refuses an unknown or deactivated reviewer —
        registration alone is not what authorises, and neither is possession of
        a token for a person who was never registered or who has been stood
        down.
        """
        if reviewer_id != OWNER_SESSION:
            record = self.get(reviewer_id)
            if not record.active:
                raise ReviewerRegistrationError(
                    f"REVIEWER_INACTIVE: cannot issue a session token for {reviewer_id}"
                )
        raw_token = secrets.token_urlsafe(32)
        with self._lock:
            self.connection.execute(
                "DELETE FROM reviewer_sessions WHERE reviewer_id=?", (reviewer_id,)
            )
            self.connection.execute(
                "INSERT INTO reviewer_sessions(session_id,reviewer_id,token_sha256,issued_at) "
                "VALUES(?,?,?,?)",
                (uuid.uuid4().hex, reviewer_id, sha256_text(raw_token), _now()),
            )
            self.connection.commit()
        return raw_token

    def authenticate_session_token(self, raw_token: Any) -> str | None:
        """Return the reviewer_id a raw token belongs to, or None.

        The digest comparison itself lives in :mod:`.auth`
        (:func:`~.auth.match_token_digest`) so all the crypto is in one place;
        this method only owns the rows. Returns None rather than raising for any
        malformed input — the caller decides the status code.
        """
        with self._lock:
            rows = self.connection.execute(
                "SELECT reviewer_id, token_sha256 FROM reviewer_sessions"
            ).fetchall()
        return match_token_digest([(row["reviewer_id"], row["token_sha256"]) for row in rows],
                                  raw_token)

    def revoke_session_token(self, reviewer_id: str) -> None:
        with self._lock:
            self.connection.execute(
                "DELETE FROM reviewer_sessions WHERE reviewer_id=?", (reviewer_id,)
            )
            self.connection.commit()

    def owner_token_state(self) -> str:
        """``"ABSENT"`` or ``"ISSUED"``. Never reveals the token itself."""
        with self._lock:
            row = self.connection.execute(
                "SELECT 1 FROM reviewer_sessions WHERE reviewer_id=?", (OWNER_SESSION,)
            ).fetchone()
        return "ISSUED" if row is not None else "ABSENT"

    def ensure_owner_token(self, raw_token: str | None = None) -> str | None:
        """Persist only the SHA-256 of the owner token; return the raw value.

        With no ``raw_token`` and none stored yet, a fresh one is generated and
        returned. With no ``raw_token`` and one already stored, returns ``None``:
        the raw value is not recoverable from disk, and the process simply does
        not know it. That is deliberately NOT an error — restarting the
        workbench must not invalidate the operator's saved token. Supplying a
        ``raw_token`` that does not match the stored digest IS an error: it means
        the operator believes they are the owner and are not.
        """
        if raw_token is not None and (not isinstance(raw_token, str) or not raw_token.strip()):
            raise ReviewerRegistrationError("owner token must be a non-empty string")
        with self._lock:
            row = self.connection.execute(
                "SELECT token_sha256 FROM reviewer_sessions WHERE reviewer_id=?", (OWNER_SESSION,)
            ).fetchone()
            if row is not None:
                if raw_token is None:
                    return None
                if not hmac.compare_digest(sha256_text(raw_token.strip()), row["token_sha256"]):
                    raise ReviewerRegistrationError(
                        "OWNER_TOKEN_MISMATCH: supplied owner token does not match the stored digest"
                    )
                return raw_token.strip()
            issued = (raw_token or secrets.token_urlsafe(32)).strip()
            self.connection.execute(
                "INSERT INTO reviewer_sessions(session_id,reviewer_id,token_sha256,issued_at) "
                "VALUES(?,?,?,?)",
                (uuid.uuid4().hex, OWNER_SESSION, sha256_text(issued), _now()),
            )
            self.connection.commit()
        return issued

    def list_active(self, role: ReviewRole | None = None) -> list[ReviewerRecord]:
        rows = self.connection.execute("SELECT * FROM reviewers WHERE active=1").fetchall()
        records = [self._row_to_record(row) for row in rows]
        if role is None:
            return records
        return [record for record in records if role.value in record.authorised_scope]

    def require_registered_active(self, reviewer_id: str, role: ReviewRole) -> ReviewerRecord:
        """Raise unless reviewer_id is registered, active, and authorised for role."""
        record = self.get(reviewer_id)
        if not record.active:
            raise ReviewerRegistrationError(f"Reviewer is inactive: {reviewer_id}")
        if role.value not in record.authorised_scope:
            raise ReviewerRegistrationError(
                f"Reviewer {reviewer_id} is not authorised for role {role.value}"
            )
        return record

    def validate_reviewer_action(
        self,
        reviewer_id: str,
        required_role: ReviewRole,
        target_type: TargetType,
        action: str,
    ) -> ReviewerActionResult:
        """Canonical, deterministic identity/role/scope/credential check
        (Phase 1). Never raises — callers inspect `.allowed`/`.reason_code`.
        Display names are never used as an identity key; only `reviewer_id`."""
        checked_at = _now()

        if required_role is ReviewRole.ADMINISTRATOR and action in CLINICAL_ACTIONS:
            return ReviewerActionResult(
                allowed=False, reason_code=ADMIN_CLINICAL_ACTION_FORBIDDEN,
                reviewer_record_version=0, role=required_role.value, scope=(), checked_at=checked_at,
            )

        try:
            record = self.get(reviewer_id)
        except ReviewerRegistrationError:
            return ReviewerActionResult(
                allowed=False, reason_code=REVIEWER_NOT_REGISTERED,
                reviewer_record_version=0, role=required_role.value, scope=(), checked_at=checked_at,
            )

        if not record.active:
            return ReviewerActionResult(
                allowed=False, reason_code=REVIEWER_INACTIVE,
                reviewer_record_version=record.version, role=required_role.value,
                scope=record.authorised_scope, checked_at=checked_at,
            )

        if required_role.value not in record.authorised_scope:
            return ReviewerActionResult(
                allowed=False, reason_code=ROLE_NOT_AUTHORISED,
                reviewer_record_version=record.version, role=required_role.value,
                scope=record.authorised_scope, checked_at=checked_at,
            )

        if record.target_type_scope and target_type.value not in record.target_type_scope:
            return ReviewerActionResult(
                allowed=False, reason_code=SCOPE_NOT_AUTHORISED,
                reviewer_record_version=record.version, role=required_role.value,
                scope=record.authorised_scope, checked_at=checked_at,
            )

        if record.credential_expires_at:
            try:
                expiry = datetime.fromisoformat(record.credential_expires_at.replace("Z", "+00:00"))
                if expiry <= datetime.now(timezone.utc):
                    return ReviewerActionResult(
                        allowed=False, reason_code=CREDENTIAL_EXPIRED,
                        reviewer_record_version=record.version, role=required_role.value,
                        scope=record.authorised_scope, checked_at=checked_at,
                    )
            except ValueError:
                return ReviewerActionResult(
                    allowed=False, reason_code=CREDENTIAL_EXPIRED,
                    reviewer_record_version=record.version, role=required_role.value,
                    scope=record.authorised_scope, checked_at=checked_at,
                )

        return ReviewerActionResult(
            allowed=True, reason_code="OK", reviewer_record_version=record.version,
            role=required_role.value, scope=record.authorised_scope, checked_at=checked_at,
        )

    def _row_to_record(self, row: sqlite3.Row) -> ReviewerRecord:
        return ReviewerRecord(
            reviewer_id=row["reviewer_id"],
            display_name=row["display_name"],
            professional_role=row["professional_role"],
            credential_reference=row["credential_reference"],
            organisation=row["organisation"],
            authorised_scope=tuple(json.loads(row["authorised_scope"])),
            target_type_scope=tuple(json.loads(row["target_type_scope"])),
            active=bool(row["active"]),
            registered_at=row["registered_at"],
            registered_by=row["registered_by"],
            credential_expires_at=row["credential_expires_at"],
            version=row["version"],
        )


def pilot_status(registry: ReviewerRegistry) -> str:
    """WAITING_FOR_REVIEWERS unless at least one distinct active Reviewer A and
    one distinct active Reviewer B are registered. Never returns anything else
    on the basis of invented or assumed identities."""
    reviewers_a = registry.list_active(ReviewRole.REVIEWER_A)
    reviewers_b = registry.list_active(ReviewRole.REVIEWER_B)
    if not reviewers_a or not reviewers_b:
        return "WAITING_FOR_REVIEWERS"
    if all(a.reviewer_id in {b.reviewer_id for b in reviewers_b} for a in reviewers_a) and len(reviewers_a) == 1:
        return "WAITING_FOR_REVIEWERS"  # only one distinct person is registered across both roles
    return "REVIEWERS_REGISTERED"
