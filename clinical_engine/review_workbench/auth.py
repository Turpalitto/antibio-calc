"""Session-token authentication for the Review Workbench HTTP surface.

This is a port of the pattern `clinical_engine/personal/` already uses for
PERSONAL_PHYSICIAN mode (``guard.py`` + ``bundle.py`` + ``runtime.py``), not a
second, weaker scheme:

* the workbench binds to loopback and refuses any request whose peer, ``Host``
  or ``Origin`` is not loopback — the same check as
  ``clinical_engine/api/app.py::_loopback``;
* a session token is ``secrets.token_urlsafe(32)``;
* only ``sha256(token)`` is ever persisted (``ReviewerRegistry``), and the raw
  token is returned exactly once, never written to the database, the review
  audit log, or any file;
* every comparison is ``hmac.compare_digest`` over the digest, never ``==``;
* identity is derived from the authenticated session. A JSON body that names a
  *different* reviewer is a rejection, never a silent preference.

Why this module exists at all: before it, every write endpoint in ``api.py``
read the acting identity straight out of the JSON body
(``service.claim(task_id, reviewer=request.actor, ...)``), and
``ReviewerRegistry`` only answers "is this reviewer_id string a registered
person?". It cannot answer "is the caller that reviewer?". Anyone who could
reach the port could therefore claim to be any registered reviewer and drive a
record to ``PHYSICIAN_APPROVED``.

Scope: the HTTP boundary only. ``ReviewService`` stays an in-process API whose
own authorisation is the registry plus ``permissions.py``; it is deliberately
NOT given a token parameter, so the service-layer tests keep testing the service
layer.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

# Header carrying the session token on every state-changing and every
# packet-reading endpoint.
TOKEN_HEADER = "X-Review-Token"

# Pseudo-identity of the workbench owner session. It is NOT a registered
# reviewer, so the registry refuses every clinical action for it — it exists
# only to mint and revoke reviewer sessions.
OWNER_SESSION = "__workbench_owner__"

# Deterministic reason codes (surfaced in the 401/403 body and the audit trail).
REVIEW_TOKEN_MISSING = "REVIEW_TOKEN_MISSING"
REVIEW_TOKEN_INVALID = "REVIEW_TOKEN_INVALID"
NON_LOOPBACK_REQUEST = "NON_LOOPBACK_REQUEST"
IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
OWNER_SESSION_REQUIRED = "OWNER_SESSION_REQUIRED"
OWNER_SESSION_NOT_A_REVIEWER = "OWNER_SESSION_NOT_A_REVIEWER"
REVIEW_AUTH_UNAVAILABLE = "REVIEW_AUTH_UNAVAILABLE"

# Mirrors clinical_engine/api/app.py::_loopback. "testclient" is the peer name
# the Starlette TestClient presents; it is a loopback stand-in, not a wildcard.
_LOOPBACK_PEERS = frozenset({"127.0.0.1", "::1", "testclient"})
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class AuthError(RuntimeError):
    """Authentication failed. Carries no acting identity — HTTP 401."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class IdentityMismatchError(RuntimeError):
    """Authenticated, but the request body named somebody else — HTTP 403."""

    def __init__(self, reason_code: str = IDENTITY_MISMATCH) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class Session:
    """A proved caller identity. The ONLY source of the acting reviewer."""

    reviewer_id: str
    is_owner: bool = False


def sha256_text(value: str) -> str:
    """The single hashing primitive for this package: SHA-256, hex, UTF-8."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def match_token_digest(stored_digests: list[tuple[str, str]], raw_token: Any) -> str | None:
    """Return the identity whose stored SHA-256 matches ``raw_token``, else None.

    Every stored digest is compared with ``hmac.compare_digest`` and the loop
    does not break early, so neither the comparison nor the number of stored
    sessions leaks through timing which one matched. No ``==`` on a token, ever.
    """
    if not isinstance(raw_token, str) or not raw_token:
        return None
    candidate = sha256_text(raw_token)
    matched: str | None = None
    for identity, digest in stored_digests:
        if hmac.compare_digest(candidate, digest):
            matched = identity
    return matched


def is_loopback_request(request: Any) -> bool:
    """True only for a request that provably came from this machine.

    Same three checks as ``clinical_engine/api/app.py``: the peer address, the
    ``Host`` the client addressed, and — when a browser sends one — the
    ``Origin``. An absent ``Origin`` is allowed because local CLI/native
    clients do not send one; a *present* non-loopback ``Origin`` is refused, so
    a web page on another host cannot drive the workbench with a stolen token.
    """
    try:
        peer = (request.client.host if request.client else "").lower()
        if peer not in _LOOPBACK_PEERS:
            return False
        if (request.url.hostname or "").lower() not in _LOOPBACK_HOSTS:
            return False
        origin = request.headers.get("origin")
        if not origin:
            return True
        return (urlsplit(origin).hostname or "").lower() in _LOOPBACK_HOSTS
    except Exception:
        # A malformed request object must not be able to make the check pass.
        return False


def authenticate(request: Any, registry: Any) -> Session:
    """Prove who is calling, or raise :class:`AuthError`. Fails closed.

    Any unexpected exception — a closed database, a corrupted registry, a
    non-string header — is converted into a rejection. There is no code path
    through this function that returns a :class:`Session` without having
    compared a SHA-256 digest with ``hmac.compare_digest``.
    """
    if not is_loopback_request(request):
        raise AuthError(NON_LOOPBACK_REQUEST)
    raw = request.headers.get(TOKEN_HEADER)
    if not isinstance(raw, str) or not raw.strip():
        raise AuthError(REVIEW_TOKEN_MISSING)
    try:
        reviewer_id = registry.authenticate_session_token(raw.strip())
    except Exception as error:
        raise AuthError(REVIEW_AUTH_UNAVAILABLE) from error
    if reviewer_id is None:
        raise AuthError(REVIEW_TOKEN_INVALID)
    return Session(reviewer_id=reviewer_id, is_owner=reviewer_id == OWNER_SESSION)


def require_reviewer_session(request: Any, registry: Any) -> Session:
    """A session for a *registered* reviewer. The owner token gets 403 here."""
    session = authenticate(request, registry)
    if session.is_owner:
        raise IdentityMismatchError(OWNER_SESSION_NOT_A_REVIEWER)
    return session


def resolve_actor(session: Session, *claimed: str | None) -> str:
    """The acting identity is the session. Body identities may only AGREE.

    Each positional argument is an identity the caller supplied in the request
    body or query string (``actor``, ``assigned_by``, ``reviewer_id``). A blank
    or absent value means "not claimed" and is fine — the session supplies the
    identity. A value that names somebody other than the authenticated session
    is a contradiction and is rejected; it is never resolved in favour of
    either side.
    """
    for claim in claimed:
        if claim is None:
            continue
        text = str(claim).strip()
        if not text or text == session.reviewer_id:
            continue
        raise IdentityMismatchError(IDENTITY_MISMATCH)
    return session.reviewer_id


__all__ = [
    "AuthError", "IdentityMismatchError", "NON_LOOPBACK_REQUEST", "OWNER_SESSION",
    "OWNER_SESSION_NOT_A_REVIEWER", "OWNER_SESSION_REQUIRED", "REVIEW_AUTH_UNAVAILABLE",
    "REVIEW_TOKEN_INVALID", "REVIEW_TOKEN_MISSING", "Session", "TOKEN_HEADER",
    "authenticate", "is_loopback_request", "match_token_digest", "require_reviewer_session",
    "resolve_actor", "sha256_text",
]
