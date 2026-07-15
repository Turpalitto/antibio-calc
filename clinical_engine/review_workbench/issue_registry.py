"""Import source-backed clinical findings into permanent review storage."""

from __future__ import annotations

import json
from pathlib import Path

from .storage import ReviewStore


def import_clinical_data_issues(store: ReviewStore, source: str | Path) -> dict[str, int]:
    document = json.loads(Path(source).read_text(encoding="utf-8-sig"))
    timestamp = str(document.get("meta", {}).get("generated_at") or "")
    added = 0
    for raw in document.get("issues", []):
        issue = {
            "issue_id": str(raw["issue_id"]),
            "object_id": str(raw.get("regimen_id") or raw.get("guideline_id") or raw["issue_id"]),
            "object_type": "ClinicalRegimen",
            "source": str(raw.get("guideline_id") or ""),
            "page_cell_provenance": {"source_quote": raw.get("kr_quote", "")},
            "category": str(raw.get("issue_code") or raw.get("problem_type") or "OTHER"),
            "severity": str(raw.get("severity") or "Medium").upper(),
            "clinical_impact": str(raw.get("description") or "Requires clinical review"),
            "detected_by": str(raw.get("verification") or "clinical_data_audit"),
            "status": "PENDING",
            "reviewer": "",
            "resolution": "",
            "timestamp": timestamp,
            "payload": raw,
        }
        added += store.import_issue(issue)
    return {"source": len(document.get("issues", [])), "added": added}

