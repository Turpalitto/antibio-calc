"""RC-030 Part III — OwnerFidelityEvent validator.

Deterministic, dependency-free validation of exported owner-review events
against owner_fidelity_event_schema.json's rules. Does not touch any real
database; does not write anywhere. `validate_event`/`validate_events` are
pure functions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .validation_unit import HUMAN_FIDELITY_VERDICTS

EVENT_SCHEMA_VERSION = 1

# The only reviewer identity that makes an event a genuine local owner event.
# Anything else (including a spoofed/copied AI event with this field edited)
# is rejected — see the review_origin/AI-marker checks below, which catch the
# copy-with-edited-reviewer_id case even when reviewer_id itself says OWNER_LOCAL.
GENUINE_OWNER_REVIEWER_ID = "OWNER_LOCAL"

# AI-produced review artifacts (RC030_AI_PRE_REVIEW_REPORT.md,
# RC030_AUTONOMOUS_AI_AUDIT_REPORT.md) use a disjoint field vocabulary
# (review_origin, owner_verified, clinically_approved, human_validated) that
# never appears in a genuine OwnerFidelityEvent. Presence of any of these
# fields — regardless of their value, and regardless of what reviewer_id
# claims — marks the record as AI-provenanced and disqualifies it from owner
# validation. This is a defense-in-depth check on top of the reviewer_id
# check: it catches an AI event copied into owner shape with reviewer_id
# edited to OWNER_LOCAL but its AI provenance fields left in place.
_AI_PROVENANCE_MARKER_FIELDS = ("review_origin", "owner_verified", "clinically_approved", "human_validated")
_REJECTED_REVIEW_ORIGINS = {"AI_PRE_REVIEW", "AI_AUTONOMOUS_AUDIT"}

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")

_CONFIRMING_VERDICTS = {
    "CORRECT_EXPLICIT_PER_DAY", "CORRECT_EXPLICIT_PER_DOSE", "CORRECT_FIXED_DAILY",
    "CORRECT_FIXED_SINGLE", "CORRECT_RANGE_DAILY", "CORRECT_RANGE_SINGLE",
}

_REQUIRED_FIELDS = (
    "event_id", "event_version", "created_at", "reviewer_id", "unit_id",
    "regimen_id", "regimen_version", "canonical_verdict", "ui_action", "note",
    "source_packet_hash", "pdf_hash", "parser_version", "interface_version", "test_event",
)


@dataclass
class ValidationIssue:
    event_index: int
    field: str
    message: str


def validate_event(index: int, event: dict, known_records_by_hash: dict[str, dict]) -> list[ValidationIssue]:
    """`known_records_by_hash` maps evidence_hash -> record dict (regimen_version,
    pdf_hash) — the authoritative current state to check staleness/tampering against."""
    issues: list[ValidationIssue] = []

    for field in _REQUIRED_FIELDS:
        if field not in event:
            issues.append(ValidationIssue(index, field, "missing required field"))
    if issues:
        return issues  # can't check further without required fields

    # AI provenance check first and unconditionally: an AI event must never
    # pass as a genuine owner event, regardless of what reviewer_id claims.
    for marker in _AI_PROVENANCE_MARKER_FIELDS:
        if marker in event:
            issues.append(ValidationIssue(index, marker,
                                           f"AI-provenance field {marker!r} present — not a genuine owner event"))
    if event.get("review_origin") in _REJECTED_REVIEW_ORIGINS:
        issues.append(ValidationIssue(index, "review_origin",
                                       f"rejected AI review_origin {event['review_origin']!r}"))
    if issues:
        return issues  # AI-provenanced record: stop before it can look "mostly valid"

    if event["reviewer_id"] != GENUINE_OWNER_REVIEWER_ID:
        issues.append(ValidationIssue(index, "reviewer_id",
                                       f"genuine owner events require reviewer_id={GENUINE_OWNER_REVIEWER_ID!r}, got {event['reviewer_id']!r}"))

    if not isinstance(event["test_event"], bool):
        issues.append(ValidationIssue(index, "test_event",
                                       f"must be a JSON boolean, got {type(event['test_event']).__name__} {event['test_event']!r}"))

    if event["event_version"] != EVENT_SCHEMA_VERSION:
        issues.append(ValidationIssue(index, "event_version",
                                       f"unsupported schema version {event['event_version']} (expected {EVENT_SCHEMA_VERSION})"))

    if event["canonical_verdict"] not in HUMAN_FIDELITY_VERDICTS:
        issues.append(ValidationIssue(index, "canonical_verdict", f"unknown canonical verdict {event['canonical_verdict']!r}"))

    if not _HASH_RE.match(event["source_packet_hash"] or ""):
        issues.append(ValidationIssue(index, "source_packet_hash", "not a well-formed sha256 hex digest"))
    if not _HASH_RE.match(event["pdf_hash"] or ""):
        issues.append(ValidationIssue(index, "pdf_hash", "not a well-formed sha256 hex digest"))

    known = known_records_by_hash.get(event["source_packet_hash"])
    if known is None:
        issues.append(ValidationIssue(index, "source_packet_hash", "does not match any known record's evidence hash"))
    else:
        if known.get("regimen_version") != event["regimen_version"]:
            issues.append(ValidationIssue(index, "regimen_version",
                                           f"stale: event has {event['regimen_version']}, current is {known.get('regimen_version')}"))
        if known.get("pdf_hash") != event["pdf_hash"]:
            issues.append(ValidationIssue(index, "pdf_hash", "mismatch against known record"))

    if event["canonical_verdict"] in _CONFIRMING_VERDICTS and not (event["note"] or "").strip():
        issues.append(ValidationIssue(index, "note", "confirming verdict requires a non-empty source-backed note"))

    return issues


def validate_events(events: list[dict], known_records: list[dict]) -> list[ValidationIssue]:
    """`known_records` are dicts with at least evidence_hash/regimen_version/pdf_hash keys."""
    by_hash = {r["evidence_hash"]: r for r in known_records if "evidence_hash" in r}
    all_issues: list[ValidationIssue] = []
    for i, event in enumerate(events):
        all_issues.extend(validate_event(i, event, by_hash))

    for eid, idxs in find_duplicate_event_ids(events).items():
        for i in idxs[1:]:
            all_issues.append(ValidationIssue(i, "event_id", f"duplicate event_id {eid!r} (first seen at index {idxs[0]})"))

    all_issues.extend(validate_supersession_chain(events))
    return all_issues


def filter_real_events(events: list[dict]) -> list[dict]:
    """Test events must never enter real metrics — this is the single choke
    point precision calculation should be fed through.

    Fails closed on type ambiguity: only a `test_event` field that is
    strictly the JSON boolean `False` is treated as "real". A missing field,
    a non-bool value (e.g. the string `"false"`, or the int `0`), or `True`
    is excluded — the caller must run `validate_events` first to see *why*
    a record was rejected as invalid rather than merely "not real"."""
    return [e for e in events if isinstance(e.get("test_event"), bool) and e["test_event"] is False]


def find_duplicate_event_ids(events: list[dict]) -> dict[str, list[int]]:
    """Returns {event_id: [indices]} for every event_id seen more than once."""
    seen: dict[str, list[int]] = {}
    for i, e in enumerate(events):
        eid = e.get("event_id")
        if eid is not None:
            seen.setdefault(eid, []).append(i)
    return {eid: idxs for eid, idxs in seen.items() if len(idxs) > 1}


def validate_supersession_chain(events: list[dict]) -> list[ValidationIssue]:
    """Minimal, additive append-only guards. Does not attempt full DAG
    resolution of concurrent terminal events (deferred — see
    RC030_C4_ARCHITECTURE_AUDIT.md); only rejects the unambiguous violations:
    self-supersession, a 2-cycle, and a `supersedes_event_id`/
    `previous_event_id` that references an event_id not present in the
    supplied event list (dangling reference)."""
    issues: list[ValidationIssue] = []
    ids_present = {e.get("event_id") for e in events if e.get("event_id") is not None}
    supersedes_by_id = {
        e["event_id"]: e.get("supersedes_event_id")
        for e in events
        if e.get("event_id") is not None and e.get("supersedes_event_id")
    }

    for i, e in enumerate(events):
        eid = e.get("event_id")
        target = e.get("supersedes_event_id")
        if not target:
            continue
        if target == eid:
            issues.append(ValidationIssue(i, "supersedes_event_id", "self-supersession is not allowed"))
            continue
        if target not in ids_present:
            issues.append(ValidationIssue(i, "supersedes_event_id",
                                           f"references unknown event_id {target!r} (dangling reference)"))
            continue
        # 2-cycle: A supersedes B and B supersedes A.
        if supersedes_by_id.get(target) == eid:
            issues.append(ValidationIssue(i, "supersedes_event_id",
                                           f"supersession cycle between {eid!r} and {target!r}"))

    return issues
