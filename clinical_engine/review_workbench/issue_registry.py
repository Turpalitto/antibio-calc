"""Import source-backed clinical findings into permanent review storage."""

from __future__ import annotations

import json
from pathlib import Path

from .storage import ReviewStore


def import_clinical_data_issues(store: ReviewStore, source: str | Path) -> dict[str, int]:
    """Import source-backed findings, refusing any batch without provenance.

    Every imported issue is stamped with the audit's own ``meta.generated_at`` — the time
    the finding was detected, not the time it was imported. If that field is missing the
    stamp silently becomes an empty string and the finding can no longer be tied to the
    audit run that produced it, so the batch is rejected instead.

    The check lives here rather than in a caller because this function writes the rows:
    any path that reaches it, including a direct one, must satisfy the invariant.
    """
    document = json.loads(Path(source).read_text(encoding="utf-8-sig"))
    timestamp = str(document.get("meta", {}).get("generated_at") or "").strip()
    if not timestamp:
        raise ValueError(
            f"{Path(source).name} is missing meta.generated_at; refusing to import "
            "clinical findings without provenance"
        )
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

