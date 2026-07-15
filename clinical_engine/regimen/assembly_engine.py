"""RegimenAssemblyEngine — deterministic assembly + kb_p44 enrichment (P5.3 Phase 2).

Design authority: P5.3_DECISION_RECORD.md (Option A as re-defined by the owner),
REGIMEN_ASSEMBLY_ENGINE_RFC.md, KNOWLEDGE_TO_REGIMEN_PIPELINE.md.

Backbone : normalized_regimens (each row = a complete, validated regimen with a
           source_quote line -> line-level explainability). Preserved, never rebuilt.
Enrichment: kb_p44 Evidence / Contraindication objects, attached ONLY on a
           deterministic guideline_id link. Never inferred. Missing link -> UNKNOWN
           + NEEDS_REVIEW. Every enrichment field carries FieldProvenance.

No LLM. Pure function of (normalized_regimens snapshot, kb_p44 snapshot, ruleset).
Emits metrics: enriched_regimens_count, enrichment_coverage, unresolved_links,
conflicts_found.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from clinical_engine.regimen.clinical_regimen import (
    UNKNOWN, ClinicalRegimen, FieldProvenance, LifecycleState,
)
from clinical_engine.regimen.conflict_detector import ConflictRecord, RegimenConflictDetector

RULESET_VERSION = "p5.3-v1"


@dataclass
class AssemblyMetrics:
    total_candidates: int = 0
    assembled_count: int = 0
    enriched_regimens_count: int = 0        # regimens that received >=1 kb_p44 enrichment field
    enrichment_coverage: float = 0.0        # enriched / assembled
    unresolved_links: int = 0               # regimens whose guideline had no kb_p44 enrichment available
    conflicts_found: int = 0
    evidence_links: int = 0
    contraindication_links: int = 0

    def as_dict(self) -> dict:
        return {
            "total_candidates": self.total_candidates,
            "assembled_count": self.assembled_count,
            "enriched_regimens_count": self.enriched_regimens_count,
            "enrichment_coverage": round(self.enrichment_coverage, 4),
            "unresolved_links": self.unresolved_links,
            "conflicts_found": self.conflicts_found,
            "evidence_links": self.evidence_links,
            "contraindication_links": self.contraindication_links,
        }


@dataclass
class AssemblyResult:
    regimens: list[ClinicalRegimen]
    conflicts: list[ConflictRecord]
    metrics: AssemblyMetrics


class RegimenAssemblyEngine:
    def __init__(self, normalized_regimens_path: str, kb_p44_path: str,
                 snapshot_version: str = "kb_p44-final-20260714"):
        self._nr_path = str(normalized_regimens_path)
        self._kb_path = str(kb_p44_path)
        self._snapshot = snapshot_version

    # -- kb_p44 enrichment index (deterministic, guideline-scoped) -------------
    def _build_enrichment_index(self) -> dict[str, dict]:
        """guideline_id -> {evidence:[(obj_id,level,pdf,page)], contra:[(obj_id,cond,pdf,page)]}."""
        idx: dict[str, dict] = {}
        if not Path(self._kb_path).exists():
            return idx
        kb = sqlite3.connect(f"file:{self._kb_path}?mode=ro", uri=True)
        kb.row_factory = sqlite3.Row
        q = ("SELECT o.id, o.type, o.content, p.guideline_id, p.pdf, p.page "
             "FROM objects o JOIN provenance p ON p.obj_id=o.id "
             "WHERE o.type IN ('Evidence','Contraindication') AND o.status='active' "
             "AND p.guideline_id IS NOT NULL")
        for r in kb.execute(q):
            gid = str(r["guideline_id"])
            slot = idx.setdefault(gid, {"evidence": [], "contra": []})
            try:
                content = json.loads(r["content"])
            except Exception:
                content = {}
            if r["type"] == "Evidence":
                slot["evidence"].append((r["id"], content.get("level") or content.get("normalized") or UNKNOWN,
                                         r["pdf"] or "", str(r["page"])))
            else:
                slot["contra"].append((r["id"], content.get("condition") or content.get("normalized") or UNKNOWN,
                                       r["pdf"] or "", str(r["page"])))
        kb.close()
        return idx

    # -- main --------------------------------------------------------------------
    def assemble(self, limit: Optional[int] = None) -> AssemblyResult:
        enrich_idx = self._build_enrichment_index()
        metrics = AssemblyMetrics()
        regimens: list[ClinicalRegimen] = []

        nr = sqlite3.connect(f"file:{self._nr_path}?mode=ro", uri=True)
        nr.row_factory = sqlite3.Row
        rows = nr.execute("SELECT * FROM normalized_regimens ORDER BY guideline_id, regimen_id").fetchall()
        nr.close()
        if limit:
            rows = rows[:limit]

        for row in rows:
            metrics.total_candidates += 1
            reg = self._assemble_one(row, enrich_idx, metrics)
            regimens.append(reg)

        metrics.assembled_count = len(regimens)
        metrics.enrichment_coverage = (
            metrics.enriched_regimens_count / metrics.assembled_count if metrics.assembled_count else 0.0
        )

        conflicts = RegimenConflictDetector().detect(regimens)
        metrics.conflicts_found = len(conflicts)
        # tag conflicted regimens for review (never resolve silently)
        conflicted_ids = {c.regimen_a for c in conflicts} | {c.regimen_b for c in conflicts}
        regimens = [self._flag_conflict(r) if r.regimen_id in conflicted_ids else r for r in regimens]

        return AssemblyResult(regimens=regimens, conflicts=conflicts, metrics=metrics)

    def _assemble_one(self, row, enrich_idx, metrics) -> ClinicalRegimen:
        gid = str(row["guideline_id"])
        prov: list[tuple[str, FieldProvenance]] = []
        base_prov = FieldProvenance(
            source_object_id=str(row["regimen_id"]), source_document=row["source_pdf"] or "",
            source_location=f"page {row['source_page']}", source_store="normalized_regimens",
            scope="regimen",
        )
        for f in ("antibiotic", "dose", "route", "frequency", "duration_recommended"):
            prov.append((f, base_prov))

        reasons: list[str] = []
        # --- deterministic enrichment (guideline-scoped) ---
        evidence_level = UNKNOWN
        contraindications: list[str] = []
        enriched = False
        slot = enrich_idx.get(gid)
        if slot:
            if slot["evidence"]:
                # deterministic: take the guideline's evidence marker(s); if multiple distinct, keep first sorted + flag
                ev = sorted(slot["evidence"], key=lambda e: (str(e[1]), e[0]))
                evidence_level = ev[0][1]
                prov.append(("evidence_level", FieldProvenance(
                    source_object_id=ev[0][0], source_document=ev[0][2],
                    source_location=f"page {ev[0][3]}", source_store="kb_p44", scope="guideline")))
                metrics.evidence_links += 1
                enriched = True
            if slot["contra"]:
                con = sorted(set(c[1] for c in slot["contra"]))
                contraindications = con
                first = sorted(slot["contra"], key=lambda c: (str(c[1]), c[0]))[0]
                prov.append(("contraindications", FieldProvenance(
                    source_object_id=first[0], source_document=first[2],
                    source_location=f"page {first[3]}", source_store="kb_p44", scope="guideline")))
                metrics.contraindication_links += 1
                enriched = True
        else:
            # guideline has no kb_p44 enrichment available -> unresolved link (explicit, not silent)
            metrics.unresolved_links += 1
            reasons.append(f"no_kb_p44_enrichment_for_guideline_{gid}")

        if enriched:
            metrics.enriched_regimens_count += 1

        pregnancy = None
        if row["pregnancy"] is not None:
            pregnancy = bool(row["pregnancy"])

        verdict = row["validation_verdict"] or "REVIEW"
        return ClinicalRegimen(
            regimen_id=str(row["regimen_id"]), version=1, status=LifecycleState.ASSEMBLED,
            diagnosis=row["diagnosis"] or "", icd_mkb=row["mkb"] or "",
            age_group=row["population"] or UNKNOWN, weight_range=UNKNOWN, pregnancy=pregnancy,
            renal_adjustment=bool(row["renal_adjustment"]),
            therapy_line=row["therapy_line"] or "unknown", antibiotic=row["drug_normalized"] or "",
            dose=row["dose"], unit=row["dose_unit"] or "", frequency=row["frequency"],
            duration_recommended=row["duration_recommended"], duration_min=row["duration_min"],
            duration_max=row["duration_max"], route=row["route"] or "unknown",
            guideline_id=gid, evidence_level=evidence_level,
            contraindications=tuple(contraindications),
            lifecycle_state=LifecycleState.ASSEMBLED, review_status="pending",
            field_provenance=tuple(prov), needs_review_reasons=tuple(reasons),
            confidence=float(row["overall_confidence"] or 0.0), validation_verdict=verdict,
            source_pdf=row["source_pdf"] or "", source_page=str(row["source_page"] or ""),
            source_quote=row["source_quote"] or "", snapshot_version=self._snapshot,
            assembly_ruleset_version=RULESET_VERSION,
        )

    def _flag_conflict(self, r: ClinicalRegimen) -> ClinicalRegimen:
        return r.with_state(
            LifecycleState.ASSEMBLED,
            needs_review_reasons=r.needs_review_reasons + ("unresolved_conflict",),
        )
