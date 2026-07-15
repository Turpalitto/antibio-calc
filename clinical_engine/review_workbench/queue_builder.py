"""Deterministic P5.6 target snapshots and initial review queue generation."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from clinical_engine.regimen.assembly_engine import RegimenAssemblyEngine
from clinical_engine.regimen.class_level_migration import migrate_class_level_rejects
from clinical_engine.regimen.quality_improvement import apply_quality_improvements

from .dose_unit_audit import audit as audit_unitless_doses, import_into_store
from .issue_registry import import_clinical_data_issues
from .models import ClinicalReviewTask, Severity, TargetType
from .priority import score_priority
from .storage import ReviewStore


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _task_identity(target_type: TargetType, target_id: str, target_version: int, issue_type: str) -> tuple[str, str]:
    key = f"{target_type.value}|{target_id}|{target_version}|{issue_type}"
    return "crt_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:24], key


class QueueBuilder:
    def __init__(self, store: ReviewStore) -> None:
        self.store = store
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.created = Counter()

    def add(self, *, target_type: TargetType, target_id: str, target_version: int,
            payload: dict[str, Any], provenance: list[dict[str, Any]], sources: list[dict[str, Any]],
            issue_type: str, severity: Severity, safety_axes: list[str], reasons: list[str],
            source_issue_ids: list[str] | None = None) -> bool:
        if target_type in {TargetType.CLINICAL_REGIMEN, TargetType.THERAPEUTIC_OPTION}:
            if not provenance or not sources or not all(source.get("pdf") and source.get("page") for source in sources):
                raise ValueError(f"{target_type.value} review target requires complete source provenance")
        source_issue_ids = source_issue_ids or []
        priority = score_priority(severity=severity, safety_axes=safety_axes, reasons=reasons,
                                  source_issue_ids=source_issue_ids)
        task_id, task_key = _task_identity(target_type, target_id, target_version, issue_type)
        self.store.add_target(target_type, target_id, target_version, payload, provenance, sources)
        task = ClinicalReviewTask(
            task_id=task_id, task_key=task_key, target_type=target_type, target_id=target_id,
            target_version=target_version, priority_score=priority.score, priority=priority.band,
            issue_type=issue_type, severity=severity, safety_axes=tuple(sorted(set(safety_axes))),
            source_references=tuple(sources), provenance_references=tuple(provenance),
            reason_codes=priority.contributing_reasons, created_at=self.created_at,
        )
        added = self.store.add_task(task)
        if added:
            self.created[target_type.value] += 1
        return added


def _regimen_axes(regimen: Any) -> list[str]:
    axes: list[str] = []
    age = str(regimen.age_group or "").casefold()
    if any(token in age for token in ("child", "pediatric", "newborn", "дет", "реб", "новорожд")):
        axes.append("pediatric")
    if regimen.pregnancy is True:
        axes.append("pregnancy")
    if regimen.renal_adjustment:
        axes.append("renal")
    if regimen.dose is None:
        axes.append("missing_dose")
    if not str(regimen.unit or "").strip() or regimen.unit == "UNKNOWN":
        axes.append("missing_unit")
    if regimen.conflicts:
        axes.append("clinical_conflict")
    if not regimen.source_pdf or not regimen.source_page or not regimen.source_quote:
        axes.append("source_mismatch")
    return axes


def _regimen_sources(regimen: Any) -> list[dict[str, Any]]:
    return [{
        "pdf": regimen.source_pdf, "page": regimen.source_page, "guideline_id": regimen.guideline_id,
        "source_quote": regimen.source_quote,
    }]


def _regimen_provenance(regimen: Any) -> list[dict[str, Any]]:
    return [{"field": name, **_jsonable(provenance)} for name, provenance in regimen.field_provenance]


def build_initial_queue(*, store_path: str | Path, normalized_db: str | Path, kb_db: str | Path,
                        corpus_manifest: str | Path, issues_json: str | Path,
                        golden_directory: str | Path) -> dict[str, Any]:
    with ReviewStore(store_path) as store:
        issue_import = import_clinical_data_issues(store, issues_json)
        dose_audit = audit_unitless_doses(kb_db)
        dose_imported = import_into_store(store, dose_audit)
        builder = QueueBuilder(store)

        assembly = RegimenAssemblyEngine(str(normalized_db), str(kb_db)).assemble()
        quality = apply_quality_improvements(assembly)
        review_regimens = [item for item in quality.regimens if item.validation_verdict != "REJECT"]
        rejects = [item for item in quality.regimens if item.validation_verdict == "REJECT"]
        migration = migrate_class_level_rejects(rejects)
        if len(review_regimens) != 1556 or len(migration.therapeutic_options) != 652:
            raise RuntimeError(
                f"Authoritative review population drift: regimens={len(review_regimens)}, "
                f"options={len(migration.therapeutic_options)}"
            )

        for regimen in review_regimens:
            axes = _regimen_axes(regimen)
            severity = Severity.HIGH if axes else Severity.MEDIUM
            builder.add(
                target_type=TargetType.CLINICAL_REGIMEN, target_id=regimen.regimen_id,
                target_version=regimen.version, payload=_jsonable(regimen),
                provenance=_regimen_provenance(regimen), sources=_regimen_sources(regimen),
                issue_type="CLINICAL_REGIMEN_VALIDATION", severity=severity,
                safety_axes=axes, reasons=axes or ["missing_metadata"],
            )

        for option in migration.therapeutic_options:
            sources = [{"pdf": option.source, "page": option.source_page,
                        "guideline_id": option.guideline_id, "source_quote": option.source_quote}]
            provenance = [{"field": name, **_jsonable(value)} for name, value in option.field_provenance]
            builder.add(
                target_type=TargetType.THERAPEUTIC_OPTION, target_id=option.option_id,
                target_version=option.version, payload=_jsonable(option), provenance=provenance,
                sources=sources, issue_type="THERAPEUTIC_OPTION_VALIDATION", severity=Severity.MEDIUM,
                safety_axes=[], reasons=["missing_metadata"],
            )

        manifest = json.loads(Path(corpus_manifest).read_text(encoding="utf-8"))
        for document in manifest["documents"]:
            if document["inclusion_state"] != "REVIEW_REQUIRED":
                continue
            builder.add(
                target_type=TargetType.CORPUS_EXCLUSION_DECISION, target_id=document["sha256"],
                target_version=1, payload=document, provenance=[],
                sources=[{"pdf": document["file"], "locations": document["source_locations"]}],
                issue_type="CORPUS_INCLUSION_UNCERTAINTY", severity=Severity.HIGH,
                safety_axes=["source_mismatch"], reasons=["source_mismatch"],
            )

        for case_path in sorted(Path(golden_directory).glob("*.json")):
            if case_path.name.startswith("_") or case_path.name == "schema.json":
                continue
            case = json.loads(case_path.read_text(encoding="utf-8"))
            builder.add(
                target_type=TargetType.GOLDEN_CASE, target_id=str(case["id"]), target_version=1,
                payload=case, provenance=[case.get("provenance", {})],
                sources=[{"source": case.get("provenance", {}).get("source", "")}],
                issue_type="GOLDEN_DATASET_FAILURE", severity=Severity.HIGH,
                safety_axes=["golden_failure"], reasons=["golden_failure"],
            )

        issue_document = json.loads(Path(issues_json).read_text(encoding="utf-8-sig"))
        for issue in issue_document["issues"]:
            if str(issue.get("severity", "")).upper() not in {"HIGH", "CRITICAL"}:
                continue
            payload = _jsonable(issue)
            builder.add(
                target_type=TargetType.CLINICAL_DATA_ISSUE, target_id=str(issue["issue_id"]),
                target_version=1, payload=payload,
                provenance=[{"source_quote": issue.get("kr_quote", "")}],
                sources=[{"guideline_id": issue.get("guideline_id"), "source_quote": issue.get("kr_quote", "")}],
                issue_type=str(issue.get("issue_code") or "CLINICAL_DATA_ISSUE"),
                severity=Severity(str(issue.get("severity", "HIGH")).upper()),
                safety_axes=[], reasons=[
                    "missing_dose" if "DOSE" in str(issue.get("issue_code")) else "missing_metadata"
                ], source_issue_ids=[str(issue["issue_id"])],
            )

        dose_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for issue in dose_audit["records"]:
            provenance = issue["page_cell_provenance"]
            guideline_id = next((str(item.get("guideline_id")) for item in provenance if item.get("guideline_id")), "UNKNOWN")
            dose_groups[(guideline_id, issue["category"])].append(issue)
        for (guideline_id, category), group in sorted(dose_groups.items()):
            group_id = hashlib.sha256(f"{guideline_id}|{category}".encode("utf-8")).hexdigest()[:20]
            high = any(item["severity"] == "HIGH" for item in group)
            builder.add(
                target_type=TargetType.CLINICAL_DATA_ISSUE, target_id=f"dose_group_{group_id}",
                target_version=1,
                payload={"guideline_id": guideline_id, "category": category, "count": len(group),
                         "issue_ids": [item["issue_id"] for item in group]},
                provenance=[item for issue in group for item in issue["page_cell_provenance"][:1]],
                sources=[{"guideline_id": guideline_id}], issue_type="DOSE_UNIT_GROUP",
                severity=Severity.HIGH if high else Severity.MEDIUM,
                safety_axes=["missing_unit"], reasons=["missing_unit"],
                source_issue_ids=[item["issue_id"] for item in group],
            )

        for conflict in assembly.conflicts:
            builder.add(
                target_type=TargetType.CONFLICT_RECORD, target_id=conflict.conflict_id,
                target_version=1, payload=_jsonable(conflict), provenance=[],
                sources=[{"guideline_id": conflict.guideline_a}, {"guideline_id": conflict.guideline_b}],
                issue_type=f"CONFLICT_{conflict.field.upper()}",
                severity=Severity(conflict.severity), safety_axes=["clinical_conflict"],
                reasons=["clinical_conflict"],
            )

        metrics = store.metrics()
        return {
            "assembly": assembly.metrics.as_dict(),
            "quality_before": quality.before_verdicts,
            "quality_after": quality.after_verdicts,
            "migration": migration.metrics.as_dict(),
            "clinical_issue_import": issue_import,
            "dose_issue_imported": dose_imported,
            "dose_audit": {key: value for key, value in dose_audit.items() if key != "records"},
            "created_by_type": dict(builder.created),
            "queue_metrics": metrics,
        }
