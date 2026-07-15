"""Schema-versioned SQLite review store with append-only decision history."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .models import (
    AuditEvent, ClinicalReviewTask, PriorityBand, ReviewAssignment, ReviewDecisionRecord,
    ReviewRole, ReviewState, Severity, TargetType,
)

SCHEMA_VERSION = 2

# Governance states that are NOT terminal for metrics/"pending" purposes.
_TERMINAL_STATE_VALUES = ("PHYSICIAN_APPROVED", "REJECTED", "CLOSED")


class ConcurrencyError(RuntimeError):
    pass


class ImmutableRecordError(RuntimeError):
    pass


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class ReviewStore:
    def __init__(self, path: str | Path = "review_workbench.sqlite") -> None:
        self.path = str(path)
        self._lock = threading.RLock()
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA busy_timeout=5000")
        self._migrate()

    def close(self) -> None:
        with self._lock:
            self.connection.close()

    def __enter__(self) -> "ReviewStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _column_names(self, table: str) -> set[str]:
        return {row[1] for row in self.connection.execute(f"PRAGMA table_info({table})").fetchall()}

    def _migrate(self) -> None:
        schema_exists = self.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_meta'"
        ).fetchone()
        if schema_exists:
            row = self.connection.execute("SELECT version FROM schema_meta").fetchone()
            existing_version = None if row is None else row[0]
            if existing_version is not None and existing_version not in (1, SCHEMA_VERSION):
                self.connection.close()
                raise RuntimeError(f"Unsupported review schema version: {existing_version}")

        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS schema_meta(version INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS review_targets(
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            target_version INTEGER NOT NULL,
            snapshot_hash TEXT NOT NULL,
            payload TEXT NOT NULL,
            provenance TEXT NOT NULL,
            source_references TEXT NOT NULL,
            PRIMARY KEY(target_type,target_id,target_version)
        );
        CREATE TABLE IF NOT EXISTS review_tasks(
            task_id TEXT PRIMARY KEY,
            task_key TEXT NOT NULL UNIQUE,
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            target_version INTEGER NOT NULL,
            priority_score INTEGER NOT NULL,
            priority TEXT NOT NULL,
            issue_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            safety_axes TEXT NOT NULL,
            source_references TEXT NOT NULL,
            provenance_references TEXT NOT NULL,
            lifecycle_state TEXT NOT NULL,
            assigned_reviewer TEXT NOT NULL DEFAULT '',
            second_reviewer TEXT NOT NULL DEFAULT '',
            adjudicator TEXT NOT NULL DEFAULT '',
            decision TEXT NOT NULL DEFAULT '',
            reason_codes TEXT NOT NULL,
            comments TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            claimed_at TEXT NOT NULL DEFAULT '',
            completed_at TEXT NOT NULL DEFAULT '',
            revision INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(target_type,target_id,target_version)
                REFERENCES review_targets(target_type,target_id,target_version)
        );
        CREATE TABLE IF NOT EXISTS review_events(
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            actor TEXT NOT NULL,
            role TEXT NOT NULL,
            event_type TEXT NOT NULL,
            from_state TEXT NOT NULL,
            to_state TEXT NOT NULL,
            decision TEXT NOT NULL DEFAULT '',
            reason_codes TEXT NOT NULL,
            comments TEXT NOT NULL DEFAULT '',
            timestamp TEXT NOT NULL,
            UNIQUE(task_id,sequence),
            FOREIGN KEY(task_id) REFERENCES review_tasks(task_id)
        );
        CREATE TABLE IF NOT EXISTS clinical_data_issues(
            issue_id TEXT PRIMARY KEY,
            object_id TEXT NOT NULL,
            object_type TEXT NOT NULL,
            source TEXT NOT NULL,
            page_cell_provenance TEXT NOT NULL,
            category TEXT NOT NULL,
            severity TEXT NOT NULL,
            clinical_impact TEXT NOT NULL,
            detected_by TEXT NOT NULL,
            status TEXT NOT NULL,
            reviewer TEXT NOT NULL DEFAULT '',
            resolution TEXT NOT NULL DEFAULT '',
            timestamp TEXT NOT NULL,
            payload TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_review_queue ON review_tasks(lifecycle_state,priority_score DESC);
        CREATE INDEX IF NOT EXISTS idx_review_target ON review_tasks(target_type,target_id,target_version);
        CREATE INDEX IF NOT EXISTS idx_issue_status ON clinical_data_issues(status,severity);
        CREATE TRIGGER IF NOT EXISTS review_events_no_update BEFORE UPDATE ON review_events
        BEGIN SELECT RAISE(ABORT,'review_events are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS review_events_no_delete BEFORE DELETE ON review_events
        BEGIN SELECT RAISE(ABORT,'review_events are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS review_targets_no_update BEFORE UPDATE ON review_targets
        BEGIN SELECT RAISE(ABORT,'review_targets are immutable'); END;
        CREATE TRIGGER IF NOT EXISTS review_targets_no_delete BEFORE DELETE ON review_targets
        BEGIN SELECT RAISE(ABORT,'review_targets are immutable'); END;
        """)

        # --- v1 -> v2 additive migration: new task columns + assignments/decisions tables ---
        existing_task_columns = self._column_names("review_tasks")
        new_task_columns = {
            "qa_reviewer": "TEXT NOT NULL DEFAULT ''",
            "first_decision": "TEXT NOT NULL DEFAULT ''",
            "first_reason_codes": "TEXT NOT NULL DEFAULT '[]'",
            "first_comments": "TEXT NOT NULL DEFAULT ''",
            "second_decision": "TEXT NOT NULL DEFAULT ''",
            "second_reason_codes": "TEXT NOT NULL DEFAULT '[]'",
            "second_comments": "TEXT NOT NULL DEFAULT ''",
            "consensus_result": "TEXT NOT NULL DEFAULT ''",
            "qa_verdict": "TEXT NOT NULL DEFAULT ''",
            "close_outcome": "TEXT NOT NULL DEFAULT ''",
        }
        for column, ddl in new_task_columns.items():
            if column not in existing_task_columns:
                self.connection.execute(f"ALTER TABLE review_tasks ADD COLUMN {column} {ddl}")

        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS review_assignments(
            assignment_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            reviewer_id TEXT NOT NULL,
            assigned_role TEXT NOT NULL,
            assigned_by TEXT NOT NULL,
            assigned_at TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            revoked_at TEXT NOT NULL DEFAULT '',
            reason TEXT NOT NULL DEFAULT '',
            FOREIGN KEY(task_id) REFERENCES review_tasks(task_id)
        );
        CREATE INDEX IF NOT EXISTS idx_assignment_task ON review_assignments(task_id, active);
        CREATE TABLE IF NOT EXISTS review_decisions(
            decision_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            target_version INTEGER NOT NULL,
            reviewer_id TEXT NOT NULL,
            reviewer_role TEXT NOT NULL,
            verdict TEXT NOT NULL,
            reason_codes TEXT NOT NULL,
            rationale TEXT NOT NULL DEFAULT '',
            source_verified INTEGER NOT NULL DEFAULT 0,
            submitted_at TEXT NOT NULL,
            decision_sequence INTEGER NOT NULL,
            supersedes_decision_id TEXT NOT NULL DEFAULT '',
            UNIQUE(task_id, decision_sequence),
            FOREIGN KEY(task_id) REFERENCES review_tasks(task_id)
        );
        CREATE TRIGGER IF NOT EXISTS review_decisions_no_update BEFORE UPDATE ON review_decisions
        BEGIN SELECT RAISE(ABORT,'review_decisions are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS review_decisions_no_delete BEFORE DELETE ON review_decisions
        BEGIN SELECT RAISE(ABORT,'review_decisions are append-only'); END;
        CREATE TABLE IF NOT EXISTS review_rejected_attempts(
            attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            actor TEXT NOT NULL,
            role TEXT NOT NULL,
            action TEXT NOT NULL,
            reason_code TEXT NOT NULL,
            timestamp TEXT NOT NULL
        );
        """)

        row = self.connection.execute("SELECT version FROM schema_meta").fetchone()
        if row is None:
            self.connection.execute("INSERT INTO schema_meta(version) VALUES(?)", (SCHEMA_VERSION,))
        elif row[0] != SCHEMA_VERSION:
            self.connection.execute("UPDATE schema_meta SET version=?", (SCHEMA_VERSION,))
        self.connection.commit()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                yield
            except Exception:
                self.connection.rollback()
                raise
            else:
                self.connection.commit()

    def add_target(self, target_type: TargetType, target_id: str, target_version: int,
                   payload: dict[str, Any], provenance: list[dict[str, Any]],
                   source_references: list[dict[str, Any]]) -> None:
        with self._lock:
            payload_json = _json(payload)
            provenance_json = _json(provenance)
            sources_json = _json(source_references)
            snapshot_json = _json({
                "payload": payload,
                "provenance": provenance,
                "source_references": source_references,
            })
            digest = hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()
            existing = self.connection.execute(
                "SELECT snapshot_hash FROM review_targets WHERE target_type=? AND target_id=? AND target_version=?",
                (target_type.value, target_id, target_version),
            ).fetchone()
            if existing:
                if existing[0] != digest:
                    raise ImmutableRecordError("Target version already exists with different content")
                return
            self.connection.execute(
                "INSERT INTO review_targets VALUES(?,?,?,?,?,?,?)",
                (target_type.value, target_id, target_version, digest, payload_json,
                 provenance_json, sources_json),
            )
            self.connection.commit()

    def add_task(self, task: ClinicalReviewTask) -> bool:
        with self._lock:
            cursor = self.connection.execute("""
            INSERT OR IGNORE INTO review_tasks(
                task_id,task_key,target_type,target_id,target_version,priority_score,priority,
                issue_type,severity,safety_axes,source_references,provenance_references,
                lifecycle_state,assigned_reviewer,second_reviewer,adjudicator,qa_reviewer,decision,
                reason_codes,comments,first_decision,first_reason_codes,first_comments,
                second_decision,second_reason_codes,second_comments,consensus_result,qa_verdict,
                close_outcome,created_at,claimed_at,completed_at,revision
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            task.task_id, task.task_key, task.target_type.value, task.target_id, task.target_version,
            task.priority_score, task.priority.value, task.issue_type, task.severity.value,
            _json(task.safety_axes), _json(task.source_references), _json(task.provenance_references),
            task.lifecycle_state.value, task.assigned_reviewer, task.second_reviewer, task.adjudicator,
            task.qa_reviewer, task.decision, _json(task.reason_codes), task.comments,
            task.first_decision, _json(task.first_reason_codes), task.first_comments,
            task.second_decision, _json(task.second_reason_codes), task.second_comments,
            task.consensus_result, task.qa_verdict, task.close_outcome,
            task.created_at, task.claimed_at, task.completed_at, task.revision,
        ))
            self.connection.commit()
            return cursor.rowcount == 1

    def _events(self, task_id: str) -> tuple[AuditEvent, ...]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT * FROM review_events WHERE task_id=? ORDER BY sequence", (task_id,)
            ).fetchall()
        return tuple(AuditEvent(
            sequence=row["sequence"], actor=row["actor"], role=ReviewRole(row["role"]),
            event_type=row["event_type"], from_state=ReviewState(row["from_state"]),
            to_state=ReviewState(row["to_state"]), decision=row["decision"],
            reason_codes=tuple(json.loads(row["reason_codes"])), comments=row["comments"],
            timestamp=row["timestamp"],
        ) for row in rows)

    def _task(self, row: sqlite3.Row) -> ClinicalReviewTask:
        return ClinicalReviewTask(
            task_id=row["task_id"], task_key=row["task_key"], target_type=TargetType(row["target_type"]),
            target_id=row["target_id"], target_version=row["target_version"],
            priority_score=row["priority_score"], priority=PriorityBand(row["priority"]),
            issue_type=row["issue_type"], severity=Severity(row["severity"]),
            safety_axes=tuple(json.loads(row["safety_axes"])),
            source_references=tuple(json.loads(row["source_references"])),
            provenance_references=tuple(json.loads(row["provenance_references"])),
            lifecycle_state=ReviewState(row["lifecycle_state"]), assigned_reviewer=row["assigned_reviewer"],
            second_reviewer=row["second_reviewer"], adjudicator=row["adjudicator"],
            qa_reviewer=row["qa_reviewer"],
            decision=row["decision"], reason_codes=tuple(json.loads(row["reason_codes"])),
            comments=row["comments"],
            first_decision=row["first_decision"], first_reason_codes=tuple(json.loads(row["first_reason_codes"])),
            first_comments=row["first_comments"],
            second_decision=row["second_decision"], second_reason_codes=tuple(json.loads(row["second_reason_codes"])),
            second_comments=row["second_comments"],
            consensus_result=row["consensus_result"], qa_verdict=row["qa_verdict"],
            close_outcome=row["close_outcome"],
            created_at=row["created_at"], claimed_at=row["claimed_at"],
            completed_at=row["completed_at"], revision=row["revision"],
            audit_history=self._events(row["task_id"]),
        )

    def get_task(self, task_id: str) -> ClinicalReviewTask:
        with self._lock:
            row = self.connection.execute("SELECT * FROM review_tasks WHERE task_id=?", (task_id,)).fetchone()
            if row is None:
                raise KeyError(task_id)
            return self._task(row)

    def list_tasks(self, *, target_type: TargetType | None = None, priority: PriorityBand | None = None,
                   state: ReviewState | None = None, safety_axis: str | None = None,
                   limit: int = 100, offset: int = 0) -> list[ClinicalReviewTask]:
        clauses: list[str] = []
        values: list[Any] = []
        if target_type:
            clauses.append("target_type=?"); values.append(target_type.value)
        if priority:
            clauses.append("priority=?"); values.append(priority.value)
        if state:
            clauses.append("lifecycle_state=?"); values.append(state.value)
        if safety_axis:
            clauses.append("EXISTS (SELECT 1 FROM json_each(review_tasks.safety_axes) WHERE value=?)")
            values.append(safety_axis)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._lock:
            rows = self.connection.execute(
                f"SELECT * FROM review_tasks{where} ORDER BY priority_score DESC,created_at,task_id LIMIT ? OFFSET ?",
                (*values, limit, offset),
            ).fetchall()
            return [self._task(row) for row in rows]

    def transition(self, previous: ClinicalReviewTask, current: ClinicalReviewTask, event: AuditEvent) -> ClinicalReviewTask:
        with self.transaction():
            cursor = self.connection.execute("""
                UPDATE review_tasks SET lifecycle_state=?,assigned_reviewer=?,second_reviewer=?,adjudicator=?,
                    qa_reviewer=?,decision=?,reason_codes=?,comments=?,
                    first_decision=?,first_reason_codes=?,first_comments=?,
                    second_decision=?,second_reason_codes=?,second_comments=?,
                    consensus_result=?,qa_verdict=?,close_outcome=?,
                    claimed_at=?,completed_at=?,revision=revision+1
                WHERE task_id=? AND revision=?
            """, (
                current.lifecycle_state.value, current.assigned_reviewer, current.second_reviewer,
                current.adjudicator, current.qa_reviewer, current.decision, _json(current.reason_codes),
                current.comments,
                current.first_decision, _json(current.first_reason_codes), current.first_comments,
                current.second_decision, _json(current.second_reason_codes), current.second_comments,
                current.consensus_result, current.qa_verdict, current.close_outcome,
                current.claimed_at, current.completed_at, current.task_id, previous.revision,
            ))
            if cursor.rowcount != 1:
                raise ConcurrencyError(f"Stale task revision: {previous.task_id}")
            self.connection.execute("""
                INSERT INTO review_events(task_id,sequence,actor,role,event_type,from_state,to_state,
                    decision,reason_codes,comments,timestamp) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """, (
                current.task_id, event.sequence, event.actor, event.role.value, event.event_type,
                event.from_state.value, event.to_state.value, event.decision,
                _json(event.reason_codes), event.comments, event.timestamp,
            ))
        return self.get_task(current.task_id)

    def log_rejected_attempt(self, *, task_id: str, actor: str, role: ReviewRole, action: str,
                             reason_code: str, timestamp: str) -> None:
        """Phase 2: every rejected reviewer-validation attempt is audit-logged
        without any task-state change."""
        with self._lock:
            self.connection.execute(
                "INSERT INTO review_rejected_attempts(task_id,actor,role,action,reason_code,timestamp) "
                "VALUES(?,?,?,?,?,?)",
                (task_id, actor, role.value, action, reason_code, timestamp),
            )
            self.connection.commit()

    def list_rejected_attempts(self, task_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT * FROM review_rejected_attempts WHERE task_id=? ORDER BY attempt_id", (task_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    # --- Phase 3: review assignments -----------------------------------------

    def add_assignment(self, assignment: ReviewAssignment) -> None:
        with self._lock:
            self.connection.execute(
                "INSERT INTO review_assignments(assignment_id,task_id,reviewer_id,assigned_role,"
                "assigned_by,assigned_at,active,revoked_at,reason) VALUES(?,?,?,?,?,?,?,?,?)",
                (assignment.assignment_id, assignment.task_id, assignment.reviewer_id,
                 assignment.assigned_role.value, assignment.assigned_by, assignment.assigned_at,
                 1 if assignment.active else 0, assignment.revoked_at, assignment.reason),
            )
            self.connection.commit()

    def revoke_assignment(self, assignment_id: str, *, revoked_at: str, reason: str) -> None:
        with self._lock:
            cur = self.connection.execute(
                "UPDATE review_assignments SET active=0, revoked_at=?, reason=? WHERE assignment_id=?",
                (revoked_at, reason, assignment_id),
            )
            self.connection.commit()
            if cur.rowcount == 0:
                raise KeyError(assignment_id)

    def list_assignments(self, task_id: str, *, active_only: bool = False) -> list[ReviewAssignment]:
        clause = " AND active=1" if active_only else ""
        with self._lock:
            rows = self.connection.execute(
                f"SELECT * FROM review_assignments WHERE task_id=?{clause} ORDER BY assigned_at", (task_id,)
            ).fetchall()
            return [ReviewAssignment(
                assignment_id=row["assignment_id"], task_id=row["task_id"], reviewer_id=row["reviewer_id"],
                assigned_role=ReviewRole(row["assigned_role"]), assigned_by=row["assigned_by"],
                assigned_at=row["assigned_at"], active=bool(row["active"]), revoked_at=row["revoked_at"],
                reason=row["reason"],
            ) for row in rows]

    def active_assignment_for_role(self, task_id: str, role: ReviewRole) -> ReviewAssignment | None:
        for assignment in self.list_assignments(task_id, active_only=True):
            if assignment.assigned_role is role:
                return assignment
        return None

    # --- Phase 8: immutable decision ledger -----------------------------------

    def record_decision(self, decision: ReviewDecisionRecord) -> None:
        with self._lock:
            self.connection.execute(
                "INSERT INTO review_decisions(decision_id,task_id,target_version,reviewer_id,"
                "reviewer_role,verdict,reason_codes,rationale,source_verified,submitted_at,"
                "decision_sequence,supersedes_decision_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (decision.decision_id, decision.task_id, decision.target_version, decision.reviewer_id,
                 decision.reviewer_role.value, decision.verdict, _json(decision.reason_codes),
                 decision.rationale, 1 if decision.source_verified else 0, decision.submitted_at,
                 decision.decision_sequence, decision.supersedes_decision_id),
            )
            self.connection.commit()

    def list_decisions(self, task_id: str) -> list[ReviewDecisionRecord]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT * FROM review_decisions WHERE task_id=? ORDER BY decision_sequence", (task_id,)
            ).fetchall()
            return [ReviewDecisionRecord(
                decision_id=row["decision_id"], task_id=row["task_id"], target_version=row["target_version"],
                reviewer_id=row["reviewer_id"], reviewer_role=ReviewRole(row["reviewer_role"]),
                verdict=row["verdict"], reason_codes=tuple(json.loads(row["reason_codes"])),
                rationale=row["rationale"], source_verified=bool(row["source_verified"]),
                submitted_at=row["submitted_at"], decision_sequence=row["decision_sequence"],
                supersedes_decision_id=row["supersedes_decision_id"],
            ) for row in rows]

    def target_snapshot(self, task: ClinicalReviewTask) -> dict[str, Any]:
        with self._lock:
            row = self.connection.execute(
                "SELECT * FROM review_targets WHERE target_type=? AND target_id=? AND target_version=?",
                (task.target_type.value, task.target_id, task.target_version),
            ).fetchone()
            if row is None:
                raise KeyError(f"target:{task.target_type.value}:{task.target_id}:{task.target_version}")
            return {
                "payload": json.loads(row["payload"]),
                "provenance": json.loads(row["provenance"]),
                "source_references": json.loads(row["source_references"]),
                "snapshot_hash": row["snapshot_hash"],
            }

    def import_issue(self, issue: dict[str, Any]) -> bool:
        with self._lock:
            cursor = self.connection.execute("""
            INSERT OR IGNORE INTO clinical_data_issues VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            issue["issue_id"], issue["object_id"], issue["object_type"], issue["source"],
            _json(issue.get("page_cell_provenance", {})), issue["category"], issue["severity"],
            issue["clinical_impact"], issue["detected_by"], issue.get("status", "PENDING"),
            issue.get("reviewer", ""), issue.get("resolution", ""), issue["timestamp"], _json(issue),
        ))
            self.connection.commit()
            return cursor.rowcount == 1

    def list_issues(self, *, status: str | None = None, severity: str | None = None,
                    limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        if status:
            clauses.append("status=?")
            values.append(status)
        if severity:
            clauses.append("severity=?")
            values.append(severity)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._lock:
            rows = self.connection.execute(
                f"SELECT payload FROM clinical_data_issues{where} "
                "ORDER BY CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 "
                "WHEN 'MEDIUM' THEN 2 ELSE 3 END,issue_id LIMIT ? OFFSET ?",
                (*values, limit, offset),
            ).fetchall()
            return [json.loads(row[0]) for row in rows]

    def metrics(self) -> dict[str, Any]:
        with self._lock:
            total = self.connection.execute("SELECT COUNT(*) FROM review_tasks").fetchone()[0]
            placeholders = ",".join("?" for _ in _TERMINAL_STATE_VALUES)
            pending = self.connection.execute(
                f"SELECT COUNT(*) FROM review_tasks WHERE lifecycle_state NOT IN ({placeholders})",
                _TERMINAL_STATE_VALUES,
            ).fetchone()[0]
            by_type = dict(self.connection.execute("SELECT target_type,COUNT(*) FROM review_tasks GROUP BY target_type"))
            by_priority = dict(self.connection.execute("SELECT priority,COUNT(*) FROM review_tasks GROUP BY priority"))
            by_state = dict(self.connection.execute("SELECT lifecycle_state,COUNT(*) FROM review_tasks GROUP BY lifecycle_state"))
            completed = self.connection.execute(
                "SELECT AVG((julianday(completed_at)-julianday(created_at))*86400) FROM review_tasks "
                "WHERE completed_at<>''"
            ).fetchone()[0]
            return {"total": total, "total_pending": pending, "by_type": by_type,
                    "by_priority": by_priority, "by_state": by_state,
                    "average_review_time_seconds": completed}
