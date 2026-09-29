"""Shared fixtures for clinical_engine reader tests.

Per spec §10.3, fixtures are programmatically created — no dependency on
production C:\\clinrec_downloader\\metadata.sqlite. The SQLite fixture is
built by running the real (frozen) MedicalNormalizer + NormalizerDB, not by
hand-crafting rows, so it reflects actual PASS/REVIEW/REJECT behavior.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from medical_normalizer.db import NormalizerDB
from medical_normalizer.normalizer import MedicalNormalizer

from clinical_engine.models import Recommendation, RecommendationCandidate
from clinical_engine.readers.diagnosis_reader import JsonDiagnosisProvider

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def make_candidate(
    regimen_id: str = "r1",
    *,
    guideline_id: str = "g1",
    drug_normalized: str = "Test",
    drug_ref: str | None = None,
    adult: bool = True,
    child: bool = False,
    therapy_line: str = "first",
    **overrides: object,
) -> RecommendationCandidate:
    """Minimal RecommendationCandidate factory for stage-isolation tests
    that don't need a real SQLite row (unlike the M2 reader tests)."""
    base = dict(
        regimen_id=regimen_id,
        guideline_id=guideline_id,
        drug_normalized=drug_normalized,
        drug_ref=drug_ref,
        dose=1.0,
        dose_unit="mg",
        route="oral",
        frequency=1.0,
        duration_min=None,
        duration_max=None,
        duration_recommended=None,
        therapy_line=therapy_line,
        adult=adult,
        child=child,
        pregnancy=None,
        renal_adjustment=False,
        atc_code="",
        confidence=0.9,
        validation_verdict="PASS",
        source_pdf="",
        source_page="",
        source_quote="",
        source_section="",
        diagnosis="",
        mkb="",
        guideline_year=None,
    )
    base.update(overrides)
    return RecommendationCandidate(**base)


def make_recommendation(candidate: RecommendationCandidate | None = None, **kwargs: object) -> Recommendation:
    return Recommendation(
        candidate=candidate or make_candidate(),
        dose=kwargs.pop("dose", None),
        safety_flags=kwargs.pop("safety_flags", ()),
        interaction_severity=kwargs.pop("interaction_severity", None),
        **kwargs,
    )


@pytest.fixture
def candidate_factory():
    return make_candidate


@pytest.fixture
def recommendation_factory():
    return make_recommendation

# (guideline_id, regimen_id, raw_regimen, source kwargs) — a small, varied set
# spanning two guidelines and all three verdicts.
_ROWS: list[tuple[str, str, dict, dict]] = [
    (
        "g_cap_adult",
        "r1",
        {
            "antibiotic": "Амоксициллин",
            "dose": "500",
            "unit": "мг",
            "route": "внутрь",
            "frequency": "3 раза в сутки",
            "duration": "5-7 дней",
            "age_group": "взрослые",
            "regimen_type": "first_line",
        },
        {
            "source_pdf": "cr654.pdf",
            "source_page": "28",
            "source_quote": "Amoxicillin 500mg 3x/day 5-7 days",
            "diagnosis": "CAP",
            "mkb": "J18",
        },
    ),
    (
        "g_cap_adult",
        "r2",
        {
            # No dose/route/frequency at all -> REJECT (REQUIRED_MISSING)
            "antibiotic": "Доксициклин",
        },
        {"source_pdf": "cr654.pdf", "source_page": "29", "diagnosis": "CAP", "mkb": "J18"},
    ),
    (
        "g_cap_adult",
        "r3",
        {
            # Unknown drug name -> DRUG_UNKNOWN -> REVIEW (dose/route/freq present)
            "antibiotic": "Нонэксистентоцин",
            "dose": "400",
            "unit": "мг",
            "route": "внутрь",
            "frequency": "2 раза в сутки",
            "regimen_type": "alternative",
        },
        {"source_pdf": "cr654.pdf", "source_page": "30", "diagnosis": "CAP", "mkb": "J18"},
    ),
    (
        "g_cystitis",
        "r1",
        {
            "antibiotic": "Фосфомицин",
            "dose": "3",
            "unit": "г",
            "route": "внутрь",
            "frequency": "1 раз",
            "duration": "однократно",
            "age_group": "взрослые",
            "regimen_type": "first_line",
        },
        {
            "source_pdf": "cr100.pdf",
            "source_page": "5",
            "source_quote": "Fosfomycin 3g single dose",
            "diagnosis": "acute cystitis",
            "mkb": "N30",
        },
    ),
]


# P1 terminology demonstration data (includes the unmapped_pen row for ATC demo)
P1_TERMINOLOGY_ROWS: list[tuple[str, str, dict, dict]] = _ROWS + [
    (
        "g_cap_adult",
        "r_unmapped_pen",
        {
            "antibiotic": "unmapped_pen",
            "dose": "500",
            "unit": "мг",
            "route": "внутрь",
            "frequency": "3 раза в сутки",
            "duration": "5-7 дней",
            "age_group": "взрослые",
            "regimen_type": "alternative",
        },
        {
            "source_pdf": "cr654.pdf",
            "source_page": "28",
            "source_quote": "Unmapped pen for demo",
            "diagnosis": "CAP",
            "mkb": "J18",
        },
    ),
    (
        "g_sinusitis",
        "r1",
        {
            "antibiotic": "Амоксициллин",
            "dose": "500",
            "unit": "мг",
            "route": "внутрь",
            "frequency": "3 раза в сутки",
            "duration": "5-7 дней",
            "age_group": "взрослые",
            "regimen_type": "first_line",
        },
        {
            "source_pdf": "cr200.pdf",
            "source_page": "10",
            "source_quote": "Amox for sinus",
            "diagnosis": "sinus",
            "mkb": "J01",
        },
    ),
]


def _build_sqlite(path: Path, rows: list[tuple[str, str, dict, dict]] | None = None) -> None:
    if rows is None:
        rows = _ROWS
    db = NormalizerDB.connect(path)
    try:
        for guideline_id, regimen_id, raw, source in rows:
            result = MedicalNormalizer.normalize(raw)
            db.save(result, guideline_id=guideline_id, regimen_id=regimen_id, **source)
    finally:
        db.close()


@pytest.fixture
def sqlite_path(tmp_path: Path) -> Path:
    path = tmp_path / "test.sqlite"
    _build_sqlite(path)
    return path


@pytest.fixture
def p1_terminology_sqlite_path(tmp_path: Path) -> Path:
    """Dedicated fixture for P1 terminology tests (includes r_unmapped_pen for ATC demo)."""
    path = tmp_path / "p1_terminology.sqlite"
    _build_sqlite(path, P1_TERMINOLOGY_ROWS)
    return path


@pytest.fixture
def drug_reference_path() -> Path:
    return FIXTURES_DIR / "test_drugs_reference.json"


@pytest.fixture
def diagnosis_index_path() -> Path:
    return FIXTURES_DIR / "test_diagnosis_index.json"


@pytest.fixture
def clinical_constants_path() -> Path:
    return FIXTURES_DIR / "test_clinical_constants.json"


@pytest.fixture
def engine_config(
    sqlite_path: Path,
    drug_reference_path: Path,
    diagnosis_index_path: Path,
    clinical_constants_path: Path,
):
    from clinical_engine.config import EngineConfig

    return EngineConfig(
        sqlite_path=str(sqlite_path),
        drug_reference_path=str(drug_reference_path),
        diagnosis_index_path=str(diagnosis_index_path),
        clinical_constants_path=str(clinical_constants_path),
    )


@pytest.fixture
def p1_engine_config(
    p1_terminology_sqlite_path: Path,
    drug_reference_path: Path,
    diagnosis_index_path: Path,
    clinical_constants_path: Path,
):
    """Dedicated config for P1 terminology tests using P1 sqlite fixture."""
    from clinical_engine.config import EngineConfig

    return EngineConfig(
        sqlite_path=str(p1_terminology_sqlite_path),
        drug_reference_path=str(drug_reference_path),
        diagnosis_index_path=str(diagnosis_index_path),
        clinical_constants_path=str(clinical_constants_path),
    )


def write_drug_reference(tmp_path: Path, drugs_reference: dict) -> Path:
    """Write a minimal db/index.json-shaped drug reference and return its path.

    Used by tests that need a drug whose safety prose the shipped fixture does
    not contain (a hepatic contraindication, a pediatric record with/without
    freq_per_day, a class label that matches no curated family). Keeping this
    here means no test has to edit the shared fixture JSON.
    """
    path = tmp_path / "custom_drugs_reference.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"meta": {"version": "test-generated"}, "drugs_reference": drugs_reference},
                   ensure_ascii=False),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def make_drug_reference_context(
    sqlite_path: Path,
    diagnosis_index_path: Path,
    clinical_constants_path: Path,
    tmp_path: Path,
):
    """Factory: a real StageContext whose drug reference (and optionally the
    clinical constants) are test-defined.

    Pass ``constants={...}`` to use a family vocabulary the shipped test fixture
    does not carry (e.g. Цефалоспорины, for cross-reactivity coverage).
    """
    from clinical_engine.config import EngineConfig
    from clinical_engine.engine import _load_clinical_constants
    from clinical_engine.pipeline import ScoreWeights, StageContext
    from clinical_engine.readers.drug_reference_reader import (
        DrugReferenceReader,
        DrugSafetyProviderAdapter,
    )
    from clinical_engine.readers.sqlite_reader import RegimenProviderAdapter, SQLiteReader
    from clinical_engine.terminology import BasicTerminologyProvider

    reader = SQLiteReader(sqlite_path)
    counter = {"n": 0}

    def _factory(drugs_reference: dict, constants: dict | None = None) -> StageContext:
        index = counter["n"]
        counter["n"] += 1
        ref_path = write_drug_reference(tmp_path / f"ref{index}", drugs_reference)
        drug_ref_r = DrugReferenceReader(ref_path)
        if constants is None:
            consts = _load_clinical_constants(clinical_constants_path)
        else:
            const_path = tmp_path / f"constants{index}.json"
            const_path.write_text(json.dumps(constants, ensure_ascii=False), encoding="utf-8")
            consts = _load_clinical_constants(const_path)
        return StageContext(
            config=EngineConfig(sqlite_path=str(sqlite_path)),
            sqlite_reader=reader,
            drug_ref_reader=drug_ref_r,
            diagnosis_provider=JsonDiagnosisProvider(diagnosis_index_path),
            regimen_provider=RegimenProviderAdapter(reader),
            drug_safety_provider=DrugSafetyProviderAdapter(drug_ref_r),
            terminology_provider=BasicTerminologyProvider(consts),
            constants=consts,
            score_weights=ScoreWeights(),
        )

    yield _factory
    reader.close()


# Family vocabulary used by the cross-reactivity tests: the shipped test
# constants carry no cephalosporin family.
_CEPH_CONSTANTS = {
    "age_bands": {"neonate": [0.0, 0.076712], "child": [0.0, 18.0]},
    "renal_thresholds": {},
    "allergy_class_map": {"amoxicillin": "Пенициллины"},
    "allergy_class_hierarchy": {
        "Пенициллины": ["amoxicillin"],
        "Цефалоспорины": ["cefixime"],
        "Тетрациклины": ["doxycycline"],
    },
}


@pytest.fixture
def make_ceph_context(make_drug_reference_context):
    def _factory(drugs_reference: dict):
        return make_drug_reference_context(drugs_reference, constants=_CEPH_CONSTANTS)

    return _factory


@pytest.fixture
def production_context(sqlite_path: Path, diagnosis_index_path: Path, tmp_path: Path):
    """A real StageContext over the PRODUCTION drug reference + constants.

    db/index.json and resources/clinical_constants.json are the shipped
    clinical data; the bugs this suite guards (unclassified drugs, hepatic
    prose, trimester wording) are only visible there, not in the small test
    fixture. The SQLite fixture is irrelevant to the stages that use this.
    """
    import pytest as _pytest

    from clinical_engine.config import EngineConfig
    from clinical_engine.engine import _load_clinical_constants
    from clinical_engine.pipeline import ScoreWeights, StageContext
    from clinical_engine.readers.drug_reference_reader import (
        DrugReferenceReader,
        DrugSafetyProviderAdapter,
    )
    from clinical_engine.readers.sqlite_reader import RegimenProviderAdapter, SQLiteReader
    from clinical_engine.terminology import BasicTerminologyProvider

    index_path = FIXTURES_DIR.parents[2] / "db" / "index.json"
    constants_path = FIXTURES_DIR.parents[1] / "resources" / "clinical_constants.json"
    if not index_path.exists() or not constants_path.exists():
        _pytest.skip("db/index.json or clinical_constants.json not present in this checkout")

    constants = _load_clinical_constants(constants_path)
    drug_ref_r = DrugReferenceReader(index_path)
    reader = SQLiteReader(sqlite_path)
    try:
        yield StageContext(
            config=EngineConfig(
                sqlite_path=str(sqlite_path),
                drug_reference_path=str(index_path),
                clinical_constants_path=str(constants_path),
            ),
            sqlite_reader=reader,
            drug_ref_reader=drug_ref_r,
            diagnosis_provider=JsonDiagnosisProvider(diagnosis_index_path),
            regimen_provider=RegimenProviderAdapter(reader),
            drug_safety_provider=DrugSafetyProviderAdapter(drug_ref_r),
            terminology_provider=BasicTerminologyProvider(constants),
            constants=constants,
            score_weights=ScoreWeights(),
        )
    finally:
        reader.close()


@pytest.fixture
def stage_context(
    sqlite_path: Path,
    drug_reference_path: Path,
    diagnosis_index_path: Path,
    clinical_constants_path: Path,
):
    """A real StageContext (real readers, fixture-backed) for stage isolation tests."""
    from clinical_engine.config import EngineConfig
    from clinical_engine.engine import _load_clinical_constants
    from clinical_engine.pipeline import ScoreWeights, StageContext
    from clinical_engine.readers.diagnosis_reader import DiagnosisProviderAdapter, JsonDiagnosisProvider
    from clinical_engine.readers.drug_reference_reader import DrugReferenceReader, DrugSafetyProviderAdapter
    from clinical_engine.readers.sqlite_reader import RegimenProviderAdapter, SQLiteReader
    from clinical_engine.terminology import BasicTerminologyProvider

    reader = SQLiteReader(sqlite_path)
    drug_ref_r = DrugReferenceReader(drug_reference_path)
    diag_p = JsonDiagnosisProvider(diagnosis_index_path)
    ctx = StageContext(
        config=EngineConfig(sqlite_path=str(sqlite_path)),
        sqlite_reader=reader,
        drug_ref_reader=drug_ref_r,
        diagnosis_provider=diag_p,
        # P0-2 providers (adapters)
        regimen_provider=RegimenProviderAdapter(reader),
        drug_safety_provider=DrugSafetyProviderAdapter(drug_ref_r),
        # P1
        terminology_provider=BasicTerminologyProvider(_load_clinical_constants(clinical_constants_path)),
        constants=_load_clinical_constants(clinical_constants_path),
        score_weights=ScoreWeights(),
    )
    yield ctx
    reader.close()
