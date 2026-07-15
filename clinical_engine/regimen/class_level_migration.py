"""Class-level migration — REJECT ClinicalRegimen -> TherapeuticOption (P5.5 Task 4).

Design authority: THERAPEUTIC_OPTION_RULES.md, RC024_CLASS_LEVEL_ANALYSIS.md.

Additive over UNCHANGED P5.3/P5.4 output. Does not modify assembly_engine.py,
validator.py, approval_workflow.py, or normalized_regimens.sqlite/kb_p44.db. Only
migrates a REJECT ClinicalRegimen candidate to a TherapeuticOption when:
  1. Its classification is A (therapeutic class) or B (alternative statement), AND
  2. has_complete_provenance() is true (100% provenance — mandate rule 4).
Everything else (C, D, or A/B with incomplete provenance) is left as an unmigrated
REJECT ClinicalRegimen candidate, unchanged, flagged.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from clinical_engine.regimen.clinical_regimen import ClinicalRegimen, FieldProvenance, LifecycleState
from clinical_engine.regimen.reject_classifier import ClassificationInput, classify
from clinical_engine.regimen.therapeutic_option import TherapeuticOption

_MIGRATABLE = {"A_therapeutic_class_recommendation", "B_alternative_therapy_statement"}


@dataclass
class ClassLevelMigrationMetrics:
    reject_examined: int = 0
    classified_A: int = 0
    classified_B: int = 0
    classified_C: int = 0
    classified_D: int = 0
    migrated_to_therapeutic_option: int = 0
    migration_blocked_incomplete_provenance: int = 0

    def as_dict(self) -> dict:
        return {
            "reject_examined": self.reject_examined,
            "classified_A_therapeutic_class": self.classified_A,
            "classified_B_alternative_statement": self.classified_B,
            "classified_C_specific_missing_extraction": self.classified_C,
            "classified_D_invalid_noise": self.classified_D,
            "migrated_to_therapeutic_option": self.migrated_to_therapeutic_option,
            "migration_blocked_incomplete_provenance": self.migration_blocked_incomplete_provenance,
        }


@dataclass
class ClassLevelMigrationResult:
    therapeutic_options: list[TherapeuticOption]
    unmigrated_regimens: list[ClinicalRegimen]   # everything NOT migrated (still REJECT, still ClinicalRegimen)
    metrics: ClassLevelMigrationMetrics


def _to_option(r: ClinicalRegimen, category: str) -> TherapeuticOption:
    prov = FieldProvenance(
        source_object_id=r.regimen_id, source_document=r.source_pdf,
        source_location=f"page {r.source_page}", source_store="normalized_regimens",
        scope="regimen",
    )
    return TherapeuticOption(
        option_id=f"opt_{r.regimen_id}", version=1, status=LifecycleState.ASSEMBLED,
        indication=r.diagnosis, therapeutic_class=r.antibiotic,
        alternatives=(r.antibiotic,) if category == "B_alternative_therapy_statement" else (),
        selection_conditions="UNKNOWN", contraindications=r.contraindications,
        source=r.source_pdf, source_page=r.source_page, source_quote=r.source_quote,
        guideline_id=r.guideline_id,
        field_provenance=(("indication", prov), ("therapeutic_class", prov)),
        lifecycle_state=LifecycleState.ASSEMBLED, review_status="pending",
        origin_regimen_id=r.regimen_id, origin_category=category,
    )


def migrate_class_level_rejects(reject_regimens: list[ClinicalRegimen]) -> ClassLevelMigrationResult:
    metrics = ClassLevelMigrationMetrics()
    options: list[TherapeuticOption] = []
    unmigrated: list[ClinicalRegimen] = []

    for r in reject_regimens:
        metrics.reject_examined += 1
        cat = classify(ClassificationInput(
            regimen_id=r.regimen_id, drug_original=r.antibiotic, dose=r.dose,
            route=r.route, source_quote=r.source_quote))

        if cat == "A_therapeutic_class_recommendation":
            metrics.classified_A += 1
        elif cat == "B_alternative_therapy_statement":
            metrics.classified_B += 1
        elif cat == "C_specific_regimen_missing_extraction":
            metrics.classified_C += 1
        else:
            metrics.classified_D += 1

        if cat in _MIGRATABLE:
            option = _to_option(r, cat)
            if option.has_complete_provenance():
                options.append(option)
                metrics.migrated_to_therapeutic_option += 1
                continue
            metrics.migration_blocked_incomplete_provenance += 1

        # C, D, or A/B blocked on provenance -> unmigrated, unchanged ClinicalRegimen candidate
        unmigrated.append(replace(r, needs_review_reasons=r.needs_review_reasons + (f"reject_category:{cat}",)))

    return ClassLevelMigrationResult(therapeutic_options=options, unmigrated_regimens=unmigrated, metrics=metrics)
