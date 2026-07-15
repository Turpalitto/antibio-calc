"""P5.5 tests — class-level knowledge separation.

Design authority: RC024_CLASS_LEVEL_ANALYSIS.md, THERAPEUTIC_OPTION_RULES.md.
"""
import os

import pytest

from clinical_engine.regimen.clinical_regimen import UNKNOWN, ClinicalRegimen, LifecycleState
from clinical_engine.regimen.reject_classifier import ClassificationInput, classify
from clinical_engine.regimen.class_level_migration import migrate_class_level_rejects
from clinical_engine.regimen.assembly_engine import RegimenAssemblyEngine
from clinical_engine.regimen.validator import RegimenValidator

NR = r"C:\clinrec_downloader\normalized_regimens.sqlite"
KB = "kb_p44.db"


def _reg(**kw):
    base = dict(
        regimen_id="r1", version=1, status=LifecycleState.ASSEMBLED, diagnosis="d", icd_mkb="A01.0",
        age_group="adult", weight_range=UNKNOWN, pregnancy=None, renal_adjustment=False,
        therapy_line="first", antibiotic="макролиды", dose=None, unit="", frequency=None,
        duration_recommended=None, duration_min=None, duration_max=None, route="unknown",
        guideline_id="343", evidence_level=UNKNOWN, contraindications=(),
        source_pdf="x.pdf", source_page="1", source_quote="Рекомендуются макролиды широкого спектра.",
        validation_verdict="REJECT",
    )
    base.update(kw)
    return ClinicalRegimen(**base)


# --- classifier correctness ---
def test_classifies_class_recommendation_as_A():
    cat = classify(ClassificationInput("r1", "макролиды широкого спектра", None, "unknown",
                                       "Рекомендуются макролиды широкого спектра действия."))
    assert cat == "A_therapeutic_class_recommendation"


def test_classifies_alternative_list_as_B():
    cat = classify(ClassificationInput(
        "r2", "ампициллин", None, "unknown",
        "В качестве альтернативной терапии: ампициллин, амоксициллин или цефтриаксон."))
    assert cat == "B_alternative_therapy_statement"


def test_classifies_dose_present_route_missing_as_C():
    cat = classify(ClassificationInput("r3", "тедизолид", 200.0, "unknown", "Тедизолид 200 мг в сутки."))
    assert cat == "C_specific_regimen_missing_extraction"


def test_classifies_noise_as_D():
    cat = classify(ClassificationInput("r4", "H R Z E", None, "unknown", "5** H R E"))
    assert cat == "D_invalid_noise"


# --- class recommendation accepted (as TherapeuticOption, never as ClinicalRegimen) ---
def test_class_recommendation_migrates_to_therapeutic_option():
    r = _reg()
    result = migrate_class_level_rejects([r])
    assert len(result.therapeutic_options) == 1
    opt = result.therapeutic_options[0]
    assert opt.therapeutic_class == "макролиды"
    assert opt.origin_category == "A_therapeutic_class_recommendation"
    assert len(result.unmigrated_regimens) == 0


# --- missing dose is NEVER accepted as a ClinicalRegimen (no fabrication) ---
def test_missing_dose_never_produces_a_fabricated_regimen():
    r = _reg()
    result = migrate_class_level_rejects([r])
    # it becomes a TherapeuticOption (no dose field exists on that type at all)
    assert result.therapeutic_options[0].__dict__.get("dose", "NO_SUCH_FIELD") == "NO_SUCH_FIELD"
    # confirm TherapeuticOption literally has no dose/route/frequency/duration fields
    from clinical_engine.regimen.therapeutic_option import TherapeuticOption
    field_names = TherapeuticOption.__dataclass_fields__.keys()
    assert "dose" not in field_names and "route" not in field_names and "frequency" not in field_names


def test_specific_regimen_missing_extraction_stays_a_regimen_not_promoted():
    r = _reg(antibiotic="тедизолид", dose=200.0, route="unknown",
             source_quote="Тедизолид назначают по 200 мг 1 раз в сутки.")
    result = migrate_class_level_rejects([r])
    assert len(result.therapeutic_options) == 0
    assert len(result.unmigrated_regimens) == 1
    assert "reject_category:C_specific_regimen_missing_extraction" in result.unmigrated_regimens[0].needs_review_reasons


# --- provenance required for migration (Task 4 gate) ---
def test_migration_blocked_without_complete_provenance():
    r = _reg(source_pdf="")  # incomplete provenance
    result = migrate_class_level_rejects([r])
    assert len(result.therapeutic_options) == 0
    assert result.metrics.migration_blocked_incomplete_provenance == 1
    assert len(result.unmigrated_regimens) == 1


def test_metrics_partition_is_exhaustive():
    regs = [
        _reg(regimen_id="a"),  # A
        _reg(regimen_id="b", antibiotic="ампициллин",
             source_quote="Альтернативная терапия: ампициллин или цефтриаксон."),  # B
        _reg(regimen_id="c", antibiotic="тедизолид", dose=200.0,
             source_quote="Тедизолид 200 мг в сутки."),  # C
        _reg(regimen_id="d", antibiotic="H R Z E", source_quote="5** H R E"),  # D
    ]
    result = migrate_class_level_rejects(regs)
    total = (result.metrics.classified_A + result.metrics.classified_B +
             result.metrics.classified_C + result.metrics.classified_D)
    assert total == len(regs) == 4
    assert result.metrics.classified_A == 1
    assert result.metrics.classified_C == 1
    assert result.metrics.classified_D == 1


# --- real full-corpus run ---
def test_real_class_level_migration_matches_analysis_report():
    if not os.path.exists(NR):
        pytest.skip("normalized_regimens.sqlite not available")
    res = RegimenAssemblyEngine(NR, KB).assemble()
    val = RegimenValidator()
    rejects = [r for r in res.regimens if val.validate(r).verdict == "REJECT"]
    assert len(rejects) == 1132

    mig = migrate_class_level_rejects(rejects)
    assert mig.metrics.classified_A + mig.metrics.classified_B + \
        mig.metrics.classified_C + mig.metrics.classified_D == 1132
    # matches RC024_CLASS_LEVEL_ANALYSIS.md verified counts
    assert mig.metrics.classified_A == 627
    assert mig.metrics.classified_B == 25
    assert mig.metrics.classified_C == 457
    assert mig.metrics.classified_D == 23
    # every migrated option has complete provenance
    assert all(o.has_complete_provenance() for o in mig.therapeutic_options)
