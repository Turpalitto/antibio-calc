"""ClinicalRegimen — canonical, immutable regimen aggregate (P5.3 Phase 1).

Design authority: CLINICAL_REGIMEN_MODEL.md, P5.3_DECISION_RECORD.md.

This is the domain model produced by the Regimen Assembly Layer. It is IMMUTABLE
(frozen dataclass): a change produces a new version, never an in-place edit
(VERSIONING_GOVERNANCE.md). Every field that is *enriched* from kb_p44 carries a
FieldProvenance; base fields carry the normalized_regimens source. Missing/
non-deterministic linkage is represented as UNKNOWN, never guessed
(P5.3_DECISION_RECORD.md rules 3 & 5).

No LLM. No inference. Pure data + provenance.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Optional


UNKNOWN = "UNKNOWN"  # explicit sentinel for non-deterministic / absent linkage


class LifecycleState(str, Enum):
    """CLINICAL_KNOWLEDGE_LIFECYCLE.md — the 9-state canonical lifecycle."""
    DRAFT = "DRAFT"
    EXTRACTED = "EXTRACTED"
    ASSEMBLED = "ASSEMBLED"
    VALIDATED = "VALIDATED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    PHYSICIAN_APPROVED = "PHYSICIAN_APPROVED"
    PUBLISHED = "PUBLISHED"
    SUPERSEDED = "SUPERSEDED"
    DEPRECATED = "DEPRECATED"
    REJECTED = "REJECTED"  # fail-closed terminal (CLINICAL_KNOWLEDGE_LIFECYCLE.md §4)


@dataclass(frozen=True)
class FieldProvenance:
    """Per-field lineage. Every enrichment field MUST have one (Decision Record rule 4)."""
    source_object_id: str      # normalized_regimens regimen_id, or kb_p44 object id
    source_document: str       # source pdf filename
    source_location: str       # page / table cell / quote reference
    source_store: str          # "normalized_regimens" | "kb_p44"
    scope: str = "regimen"     # "regimen" (row-specific) | "guideline" (guideline-scoped enrichment)


@dataclass(frozen=True)
class ConflictRef:
    """Marks a field whose value is contested across sources (see conflict_detector)."""
    field: str
    conflict_id: str


@dataclass(frozen=True)
class ClinicalRegimen:
    # ---- Identity ----
    regimen_id: str
    version: int
    status: LifecycleState

    # ---- Clinical context ----
    diagnosis: str
    icd_mkb: str
    age_group: str                       # or UNKNOWN
    weight_range: str                    # or UNKNOWN (kb_p44/normalized rarely carry this)
    pregnancy: Optional[bool]            # None == unknown (explicit)
    renal_adjustment: bool

    # ---- Therapy ----
    therapy_line: str                    # "first" | "alternative" | ... (from normalized_regimens)
    antibiotic: str
    dose: Optional[float]
    unit: str
    frequency: Optional[float]
    duration_recommended: Optional[float]
    duration_min: Optional[float]
    duration_max: Optional[float]
    route: str
    alternatives: tuple[str, ...] = ()   # regimen_ids of sibling alternatives (deterministic link)

    # ---- Evidence (enrichment from kb_p44 where deterministic) ----
    guideline_id: str = ""
    evidence_level: str = UNKNOWN        # enriched from kb_p44 Evidence; UNKNOWN if no det. link
    contraindications: tuple[str, ...] = ()  # enriched from kb_p44 Contraindication; () if none linked

    # ---- Governance ----
    lifecycle_state: LifecycleState = LifecycleState.ASSEMBLED
    review_status: str = "pending"
    approved_by: str = ""
    approved_at: str = ""

    # ---- Provenance & quality ----
    field_provenance: tuple[tuple[str, FieldProvenance], ...] = ()  # (field_name, FieldProvenance)
    conflicts: tuple[ConflictRef, ...] = ()
    needs_review_reasons: tuple[str, ...] = ()
    confidence: float = 0.0
    validation_verdict: str = "REVIEW"   # PASS | REVIEW | REJECT (frozen engine vocabulary)
    source_pdf: str = ""
    source_page: str = ""
    source_quote: str = ""
    snapshot_version: str = ""
    assembly_ruleset_version: str = "p5.3-v1"

    def with_state(self, state: LifecycleState, **kw) -> "ClinicalRegimen":
        """Return a NEW immutable regimen with an advanced lifecycle state (never mutate)."""
        return replace(self, status=state, lifecycle_state=state, **kw)

    def provenance_for(self, field_name: str) -> Optional[FieldProvenance]:
        for name, prov in self.field_provenance:
            if name == field_name:
                return prov
        return None

    def is_explainable(self) -> bool:
        """Core success criterion: every present therapy field traces to a source line."""
        required = ["antibiotic", "dose", "route"]
        for f in required:
            if self.provenance_for(f) is None:
                return False
        # a regimen must trace to a concrete source line
        return bool(self.source_pdf and self.source_page)
