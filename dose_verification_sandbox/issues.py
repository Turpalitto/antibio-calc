"""Phase 12 — Defect recording.

Issues are appended to a local, sandbox-owned JSON file. This module never
opens or writes to assembled_regimens.sqlite, kb_p44.db, or any other source
clinical database, and never mutates ClinicalRegimen/TherapeuticOption values
or approval/review state.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Optional

from .models import DoseCalculationIssue, ISSUE_STATUSES

ISSUES_PATH = Path(__file__).parent / "data" / "issues.json"


def _load(path: Path = ISSUES_PATH) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _save(issues: list[dict], path: Path = ISSUES_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(issues, ensure_ascii=False, indent=2), encoding="utf-8")


def new_issue_id() -> str:
    return f"dvi_{uuid.uuid4().hex[:16]}"


def record_issue(issue: DoseCalculationIssue, path: Path = ISSUES_PATH) -> DoseCalculationIssue:
    issues = _load(path)
    issues.append(issue.to_dict())
    _save(issues, path)
    return issue


def list_issues(path: Path = ISSUES_PATH, status: Optional[str] = None) -> list[dict]:
    issues = _load(path)
    if status is not None:
        issues = [i for i in issues if i.get("status") == status]
    return issues


def update_issue_status(issue_id: str, new_status: str, path: Path = ISSUES_PATH) -> DoseCalculationIssue | None:
    if new_status not in ISSUE_STATUSES:
        raise ValueError(f"invalid issue status: {new_status}")
    issues = _load(path)
    updated = None
    for entry in issues:
        if entry.get("issue_id") == issue_id:
            entry["status"] = new_status
            updated = entry
            break
    if updated is not None:
        _save(issues, path)
    return updated
