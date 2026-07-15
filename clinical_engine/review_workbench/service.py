"""Governed local service for two-reviewer clinical validation."""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import (
    AuditEvent, ClinicalReviewTask, FINAL_STATES, ReviewDecision, ReviewRole, ReviewState,
)
from .permissions import require
from .storage import ReviewStore


class InvalidTransition(RuntimeError):
    pass


def resolve_source_wording(provenance: list[dict[str, Any]], payload: dict[str, Any]) -> list[str | None]:
    """RC-027 canonical fix — REVIEW_PACKET_CONTRACT.md precedence, tiers 1-4, else None (tier 5).

    Tolerates every provenance-dict shape already in production storage (FieldProvenance-derived
    {"field","source_object_id",...}, {"source_quote": ...}, golden-case {"author","source",...})
    without requiring any producer or stored review_targets row to change. One resolved string per
    provenance entry, in storage order — never re-sorted, never deduplicated, never fabricated.
    """
    target_level_quote = payload.get("source_quote") or None          # tier 3

    if not provenance:
        return [target_level_quote] if target_level_quote else [None]

    resolved: list[str | None] = []
    for entry in provenance:
        wording = (
            entry.get("original_text")                    # tier 1: field-level original_text
            or entry.get("source_quote")                   # tier 2: field-level source_quote
            or target_level_quote                           # tier 3: target payload's own source_quote
            or entry.get("source")                          # tier 4: golden-case provenance {"source": ...}
            or None
        )
        resolved.append(wording or None)
    return resolved


def source_wording_missing(resolved: list[str | None]) -> bool:
    """True when tiers 1-4 produced nothing usable for ANY entry — packet is review_blocked."""
    return not any(resolved)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _final_state(decision: ReviewDecision) -> ReviewState:
    mapping = {
        ReviewDecision.ACCEPT: ReviewState.ACCEPTED,
        ReviewDecision.ACCEPT_WITH_NOTE: ReviewState.ACCEPTED_WITH_NOTE,
        ReviewDecision.REJECT_FIDELITY: ReviewState.REJECTED_FIDELITY,
        ReviewDecision.REJECT_CLINICAL: ReviewState.REJECTED_CLINICAL,
        ReviewDecision.NEEDS_INFO: ReviewState.NEEDS_INFO,
        ReviewDecision.ABSTAIN: ReviewState.ABSTAINED,
    }
    return mapping[decision]


class ReviewService:
    def __init__(self, store: ReviewStore) -> None:
        self.store = store

    def list_queue(self, **filters: Any) -> list[ClinicalReviewTask]:
        return self.store.list_tasks(**filters)

    def get_task(self, task_id: str) -> ClinicalReviewTask:
        return self.store.get_task(task_id)

    def _apply(self, task: ClinicalReviewTask, updated: ClinicalReviewTask, *, actor: str,
               role: ReviewRole, event_type: str, decision: str = "",
               reason_codes: tuple[str, ...] = (), comments: str = "") -> ClinicalReviewTask:
        event = AuditEvent(
            sequence=len(task.audit_history) + 1, actor=actor, role=role, event_type=event_type,
            from_state=task.lifecycle_state, to_state=updated.lifecycle_state, decision=decision,
            reason_codes=reason_codes, comments=comments, timestamp=_now(),
        )
        return self.store.transition(task, updated, event)

    def claim(self, task_id: str, *, reviewer: str, role: ReviewRole,
              expected_revision: int) -> ClinicalReviewTask:
        task = self.get_task(task_id)
        if task.revision != expected_revision:
            raise InvalidTransition("Stale task revision")
        if task.lifecycle_state is ReviewState.PENDING:
            require("claim_first", role)
            updated = replace(task, lifecycle_state=ReviewState.CLAIMED,
                              assigned_reviewer=reviewer, claimed_at=_now())
            return self._apply(task, updated, actor=reviewer, role=role, event_type="CLAIM_FIRST")
        if task.lifecycle_state is ReviewState.SECOND_REVIEW:
            require("claim_second", role)
            if reviewer == task.assigned_reviewer:
                raise InvalidTransition("Self-second-review is forbidden")
            if task.second_reviewer and task.second_reviewer != reviewer:
                raise InvalidTransition("Second review already claimed")
            updated = replace(task, second_reviewer=reviewer)
            return self._apply(task, updated, actor=reviewer, role=role, event_type="CLAIM_SECOND")
        raise InvalidTransition(f"Cannot claim task in {task.lifecycle_state.value}")

    def release(self, task_id: str, *, reviewer: str, role: ReviewRole,
                expected_revision: int) -> ClinicalReviewTask:
        task = self.get_task(task_id)
        if task.revision != expected_revision or task.lifecycle_state is not ReviewState.CLAIMED:
            raise InvalidTransition("Only current CLAIMED revision can be released")
        if task.assigned_reviewer != reviewer or role is not ReviewRole.REVIEWER_A:
            raise InvalidTransition("Only assigned first reviewer can release")
        updated = replace(task, lifecycle_state=ReviewState.PENDING, assigned_reviewer="", claimed_at="")
        return self._apply(task, updated, actor=reviewer, role=role, event_type="RELEASE")

    def start_review(self, task_id: str, *, reviewer: str, role: ReviewRole,
                     expected_revision: int) -> ClinicalReviewTask:
        require("submit_first", role)
        task = self.get_task(task_id)
        if task.revision != expected_revision or task.lifecycle_state is not ReviewState.CLAIMED:
            raise InvalidTransition("Task is not claimable for first review")
        if task.assigned_reviewer != reviewer:
            raise InvalidTransition("Reviewer does not own task")
        updated = replace(task, lifecycle_state=ReviewState.IN_REVIEW)
        return self._apply(task, updated, actor=reviewer, role=role, event_type="START_REVIEW")

    def submit_first_review(self, task_id: str, *, reviewer: str, role: ReviewRole,
                            decision: ReviewDecision, reason_codes: tuple[str, ...], comments: str,
                            expected_revision: int, target_version: int) -> ClinicalReviewTask:
        require("submit_first", role)
        task = self.get_task(task_id)
        if task.revision != expected_revision or task.target_version != target_version:
            raise InvalidTransition("Stale task or target version")
        if task.lifecycle_state not in {ReviewState.CLAIMED, ReviewState.IN_REVIEW}:
            raise InvalidTransition("First review not allowed from current state")
        if task.assigned_reviewer != reviewer:
            raise InvalidTransition("Reviewer does not own task")
        next_state = (
            ReviewState.NEEDS_INFO if decision is ReviewDecision.NEEDS_INFO
            else ReviewState.ABSTAINED if decision is ReviewDecision.ABSTAIN
            else ReviewState.SECOND_REVIEW
        )
        updated = replace(task, lifecycle_state=next_state, decision=decision.value,
                          reason_codes=reason_codes, comments=comments)
        return self._apply(task, updated, actor=reviewer, role=role, event_type="SUBMIT_FIRST",
                           decision=decision.value, reason_codes=reason_codes, comments=comments)

    def submit_second_review(self, task_id: str, *, reviewer: str, role: ReviewRole,
                             decision: ReviewDecision, reason_codes: tuple[str, ...], comments: str,
                             expected_revision: int, target_version: int) -> ClinicalReviewTask:
        require("submit_second", role)
        task = self.get_task(task_id)
        if task.revision != expected_revision or task.target_version != target_version:
            raise InvalidTransition("Stale task or target version")
        if task.lifecycle_state is not ReviewState.SECOND_REVIEW or task.second_reviewer != reviewer:
            raise InvalidTransition("Second review not claimed by reviewer")
        if reviewer == task.assigned_reviewer:
            raise InvalidTransition("Self-second-review is forbidden")
        first = next((event.decision for event in task.audit_history if event.event_type == "SUBMIT_FIRST"), "")
        if decision in {ReviewDecision.NEEDS_INFO, ReviewDecision.ABSTAIN}:
            state = _final_state(decision)
        elif first == decision.value:
            state = _final_state(decision)
        else:
            state = ReviewState.NEEDS_ADJUDICATION
        completed_at = _now() if state in FINAL_STATES else ""
        updated = replace(task, lifecycle_state=state, decision=decision.value,
                          reason_codes=reason_codes, comments=comments, completed_at=completed_at)
        return self._apply(task, updated, actor=reviewer, role=role, event_type="SUBMIT_SECOND",
                           decision=decision.value, reason_codes=reason_codes, comments=comments)

    def adjudicate(self, task_id: str, *, adjudicator: str, role: ReviewRole,
                   decision: ReviewDecision, reason_codes: tuple[str, ...], comments: str,
                   expected_revision: int, target_version: int) -> ClinicalReviewTask:
        require("adjudicate", role)
        task = self.get_task(task_id)
        if task.revision != expected_revision or task.target_version != target_version:
            raise InvalidTransition("Stale task or target version")
        if task.lifecycle_state is not ReviewState.NEEDS_ADJUDICATION:
            raise InvalidTransition("Task does not require adjudication")
        if decision in {ReviewDecision.NEEDS_INFO, ReviewDecision.ABSTAIN}:
            state = _final_state(decision)
        else:
            state = _final_state(decision)
        updated = replace(task, lifecycle_state=state, adjudicator=adjudicator,
                          decision=decision.value, reason_codes=reason_codes, comments=comments,
                          completed_at=_now() if state in FINAL_STATES else "")
        return self._apply(task, updated, actor=adjudicator, role=role, event_type="ADJUDICATE",
                           decision=decision.value, reason_codes=reason_codes, comments=comments)

    def request_adjudication(self, task_id: str, *, actor: str, role: ReviewRole, reason: str,
                             expected_revision: int) -> ClinicalReviewTask:
        require("request_adjudication", role)
        if not reason.strip():
            raise ValueError("Adjudication request requires reason")
        task = self.get_task(task_id)
        if task.revision != expected_revision:
            raise InvalidTransition("Stale task revision")
        if task.lifecycle_state not in {
            ReviewState.IN_REVIEW, ReviewState.SECOND_REVIEW,
            ReviewState.NEEDS_INFO, ReviewState.ABSTAINED,
        }:
            raise InvalidTransition("Adjudication cannot be requested from current state")
        if role is not ReviewRole.MEDICAL_QA_LEAD and actor not in {
            task.assigned_reviewer, task.second_reviewer,
        }:
            raise InvalidTransition("Only assigned reviewer or Medical QA Lead can request adjudication")
        updated = replace(task, lifecycle_state=ReviewState.NEEDS_ADJUDICATION)
        return self._apply(task, updated, actor=actor, role=role, event_type="REQUEST_ADJUDICATION",
                           comments=reason.strip())

    def close(self, task_id: str, *, actor: str, role: ReviewRole,
              expected_revision: int) -> ClinicalReviewTask:
        require("close", role)
        task = self.get_task(task_id)
        if task.revision != expected_revision or task.lifecycle_state not in FINAL_STATES - {ReviewState.CLOSED}:
            raise InvalidTransition("Only completed decision can close")
        updated = replace(task, lifecycle_state=ReviewState.CLOSED)
        return self._apply(task, updated, actor=actor, role=role, event_type="CLOSE")

    def add_note(self, task_id: str, *, actor: str, role: ReviewRole, comments: str,
                 expected_revision: int) -> ClinicalReviewTask:
        require("add_note", role)
        if not comments.strip():
            raise ValueError("Governed note cannot be empty")
        task = self.get_task(task_id)
        if task.revision != expected_revision:
            raise InvalidTransition("Stale task revision")
        combined = "\n".join(value for value in (task.comments, comments.strip()) if value)
        updated = replace(task, comments=combined)
        return self._apply(task, updated, actor=actor, role=role, event_type="ADD_NOTE", comments=comments)

    def add_waiver(self, task_id: str, *, authority: str, role: ReviewRole, reason: str,
                   expires_at: str, expected_revision: int) -> ClinicalReviewTask:
        require("waive", role)
        if not authority.strip() or not reason.strip():
            raise ValueError("Waiver requires named authority and reason")
        try:
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("Waiver expiry must be ISO-8601") from error
        if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
            raise ValueError("Waiver expiry must be timezone-aware and in future")
        task = self.get_task(task_id)
        if task.revision != expected_revision:
            raise InvalidTransition("Stale task revision")
        note = f"WAIVER authority={authority.strip()} expires={expiry.isoformat()} reason={reason.strip()}"
        updated = replace(task, comments="\n".join(value for value in (task.comments, note) if value))
        return self._apply(task, updated, actor=authority, role=role, event_type="ADD_WAIVER", comments=note)

    def packet(self, task_id: str) -> dict[str, Any]:
        task = self.get_task(task_id)
        snapshot = self.store.target_snapshot(task)
        wording = resolve_source_wording(snapshot["provenance"], snapshot["payload"])
        blocked = source_wording_missing(wording)
        return {
            "task": asdict(task),
            "normalized_object": snapshot["payload"],
            "original_source_wording": wording,
            "source_wording_status": "MISSING" if blocked else "AVAILABLE",
            "review_blocked": blocked,
            "source_references": snapshot["source_references"],
            "field_level_provenance": snapshot["provenance"],
            "prior_versions": [],
            "detected_conflicts": snapshot["payload"].get("conflicts", []),
            "validation_failures": snapshot["payload"].get("needs_review_reasons", []),
            "decision_options": [decision.value for decision in ReviewDecision],
            "unsupported_checks": {"drug_interactions": "NOT AVAILABLE / UNSATISFIABLE"},
            "snapshot_hash": snapshot["snapshot_hash"],
        }

    def export_packet(self, task_id: str, path: str | Path) -> Path:
        destination = Path(path)
        destination.write_text(json.dumps(self.packet(task_id), ensure_ascii=False, indent=2, default=str),
                               encoding="utf-8")
        return destination

    def metrics(self) -> dict[str, Any]:
        result = self.store.metrics()
        diagnoses: dict[str, int] = {}
        antibiotics: dict[str, int] = {}
        safety: dict[str, int] = {}
        for task in self.store.list_tasks(limit=1_000_000):
            snapshot = self.store.target_snapshot(task)["payload"]
            diagnosis = str(snapshot.get("diagnosis") or snapshot.get("indication") or "UNKNOWN")
            antibiotic = str(snapshot.get("antibiotic") or snapshot.get("therapeutic_class") or "UNKNOWN")
            diagnoses[diagnosis] = diagnoses.get(diagnosis, 0) + 1
            antibiotics[antibiotic] = antibiotics.get(antibiotic, 0) + 1
            for axis in task.safety_axes:
                safety[axis] = safety.get(axis, 0) + 1
        result.update({"by_diagnosis": diagnoses, "by_antibiotic": antibiotics, "by_safety_category": safety})
        return result
