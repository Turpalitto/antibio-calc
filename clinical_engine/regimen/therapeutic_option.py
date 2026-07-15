"""TherapeuticOption — class-level clinical knowledge, distinct from ClinicalRegimen (P5.5).

Design authority: RC024_CLASS_LEVEL_ANALYSIS.md, THERAPEUTIC_OPTION_RULES.md.

A TherapeuticOption represents "this drug class / these alternatives are indicated for X,"
WITHOUT a single dose/route/frequency/duration — the defining property that distinguishes
it from a ClinicalRegimen. It is NOT a ClinicalRegimen subtype and does not inherit from it
(they are siblings under a shared, informal "ClinicalKnowledge" concept, not a class
hierarchy — kept as two independent, unrelated dataclasses per RC024_CLASS_LEVEL_ANALYSIS.md
"do not force class-level statements into the regimen shape").

Reuses LifecycleState from clinical_regimen.py (same 9-state governance model, P5.2) — the
approval/review discipline is identical; only the clinical SHAPE differs.
"""
from __future__ import annotations

from dataclasses import dataclass

from clinical_engine.regimen.clinical_regimen import UNKNOWN, FieldProvenance, LifecycleState


@dataclass(frozen=True)
class TherapeuticOption:
    # ---- Identity ----
    option_id: str
    version: int
    status: LifecycleState

    # ---- Minimal required fields (per the mandate) ----
    indication: str                          # diagnosis / clinical indication this option addresses
    therapeutic_class: str                   # e.g. "макролиды", "цефалоспорины 4-го поколения"
    alternatives: tuple[str, ...] = ()        # specific drug names, if the source lists any (may be empty for a bare class statement)
    selection_conditions: str = UNKNOWN       # e.g. "при аллергии на бета-лактамы" — factors guiding choice; UNKNOWN if not stated
    contraindications: tuple[str, ...] = ()   # linked kb_p44 Contraindication conditions, where deterministically resolvable

    # ---- Source & provenance (same discipline as ClinicalRegimen) ----
    source: str = ""                          # source_pdf
    source_page: str = ""
    source_quote: str = ""
    guideline_id: str = ""
    field_provenance: tuple[tuple[str, FieldProvenance], ...] = ()

    # ---- Governance (same lifecycle model as ClinicalRegimen, P5.2) ----
    lifecycle_state: LifecycleState = LifecycleState.ASSEMBLED
    review_status: str = "pending"
    approved_by: str = ""
    approved_at: str = ""

    # ---- Migration lineage (where this came from) ----
    origin_regimen_id: str = ""              # the REJECT ClinicalRegimen candidate this was derived from
    origin_category: str = ""                # "A_therapeutic_class_recommendation" | "B_alternative_therapy_statement"

    def has_complete_provenance(self) -> bool:
        """Migration gate (Task 4): only migrate REJECT -> TherapeuticOption with 100% provenance."""
        return bool(self.source and self.source_page and self.source_quote and self.guideline_id)

    def provenance_for(self, field_name: str):
        for name, prov in self.field_provenance:
            if name == field_name:
                return prov
        return None
