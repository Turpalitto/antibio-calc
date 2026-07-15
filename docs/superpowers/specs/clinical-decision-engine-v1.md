# Clinical Decision Engine v1 — Design Specification

> **Status:** FROZEN. Changes only via RFC.
> **Phase:** ANTIBIO v0.5 — Clinical Decision Engine
> **Date:** 2026-07-10
> **Prerequisite phases:** v0.1 (Downloader), v0.2 (Extraction), v0.3 (Normalizer), v0.4 (Quality Improvement), Medical Dictionary subsystem — all complete.

---

## Table of Contents

1. [Purpose & Scope](#1-purpose--scope)
2. [Architecture](#2-architecture)
3. [Data Flow & Data Sources](#3-data-flow--data-sources)
4. [Module Responsibilities](#4-module-responsibilities)
5. [Public Interfaces](#5-public-interfaces)
6. [Safety Stages](#6-safety-stages)
7. [Ranking, Trace, Versioning & Confidence](#7-ranking-trace-versioning--confidence)
8. [Error Handling](#8-error-handling)
9. [Performance](#9-performance)
10. [Testing Strategy](#10-testing-strategy)
11. [Extension Points](#11-extension-points)
12. [Constitutional Invariants](#12-constitutional-invariants)
13. [Future Versions](#13-future-versions)

---

## 1. Purpose & Scope

### 1.1 Goal

Build a Clinical Decision Engine — the medical reasoning layer of ANTIBIO. The engine takes a patient query (diagnosis + patient parameters) and returns a ranked, safety-filtered, fully-traced set of antibiotic recommendations derived from normalized clinical guideline data.

### 1.2 What the Engine Does

- Matches diagnoses to clinical guidelines
- Loads normalized regimens from SQLite
- Filters by population (adult/child/neonate)
- Selects therapy lines (first/alternative/reserve/prophylaxis/empiric)
- Applies absolute safety exclusions (allergy, pregnancy, age, contraindications)
- Calculates doses (adult fixed, pediatric mg/kg/day)
- Adjusts doses (renal, hepatic)
- Checks drug-drug interactions
- Ranks recommendations by weighted scoring
- Produces full audit trail with evidence traceability

### 1.3 What the Engine NEVER Does

- **Never parses PDFs** — no pipeline imports
- **Never normalizes text** — no medical_normalizer parser imports
- **Never accesses raw extraction** (`extraction_raw.json`, `knowledge_base.json`)
- **Never writes** to SQLite, drugs_reference, or diagnosis_index
- **Never creates duplicate drug-safety reference** — drugs_reference is the single source
- **Never exposes `guideline_id`** in public API — it is internal

### 1.4 Form

Importable Python library (`clinical_engine/`). Pure functions + frozen dataclasses. No network. No I/O at import time. Lazy resource loading.

---

## 2. Architecture

### 2.1 Package Layout

```
clinical_engine/
├── __init__.py              # public API: Engine, PatientQuery, RecommendationSet
├── config.py                # EngineConfig + ValidationPolicy + Profiles
├── engine.py                # Engine — orchestrates the 10-stage pipeline
├── models.py                # all dataclasses (frozen, slots)
├── pipeline.py              # PipelineStage Protocol + PluginHook enum + runner
├── cache.py                 # EngineCache stub (v1: no-op, v1.1+: LRU)
│
├── stages/                  # one module per pipeline stage (pure functions)
│   ├── diagnosis_match.py
│   ├── regimen_load.py
│   ├── population_filter.py
│   ├── therapy_line_select.py
│   ├── hard_safety_filter.py
│   ├── dose_calculation.py
│   ├── dose_adjustment.py
│   ├── interaction_check.py
│   ├── rank_recommendations.py
│   └── trace.py
│
├── readers/                 # only layer that touches external data (read-only)
│   ├── sqlite_reader.py         # SQLite → RecommendationCandidate (domain object)
│   ├── drug_reference_reader.py # drugs_reference JSON → DrugInfo (domain object)
│   └── diagnosis_reader.py      # DiagnosisProvider Protocol + JsonDiagnosisProvider
│
├── resources/               # engine-owned curated resources
│   ├── diagnosis_index.json     # diagnosis term/ICD-10 → guideline_id (~294 entries)
│   ├── score_profiles/          # configurable ranking profiles
│   │   ├── default.json
│   │   ├── ent.json
│   │   ├── urology.json
│   │   ├── icu.json
│   │   └── pediatrics.json
│   └── clinical_constants.json  # age bands, GFR thresholds, units, allergy class map
│
├── plugins/                 # extension point for future AI (re-ranker, hint generator)
│   └── __init__.py              # PluginHook-based hooks
│
└── tests/
    ├── fixtures/
    │   ├── test.sqlite
    │   ├── test_drugs_reference.json
    │   ├── test_diagnosis_index.json
    │   └── golden_cases.py
    ├── test_stage_*.py          # stage isolation tests
    ├── test_integration.py      # full pipeline tests
    ├── test_invariants.py       # constitutional invariant tests
    └── test_performance.py      # latency target tests
```

### 2.2 Pipeline (10 stages)

```
PatientQuery
  1. DiagnosisMatch         (diagnosis_index → guideline_ids)
  2. RegimenLoad            (SQLite, ValidationPolicy filter)
  3. PopulationFilter       (adult/child/neonate + age band)
  4. TherapyLineSelect      (first/alternative/reserve/prophylaxis/empiric)
  5. HardSafetyFilter       (allergy, CI, pregnancy, age — absolute excludes)
  6. DoseCalculation        (adult fixed, peds mg/kg/day)
  7. DoseAdjustment         (renal/hepatic adjustments, max doses)
  8. InteractionCheck       (drug-drug, severity classification)
  9. RankRecommendations    (weighted scoring — only after all clinical filters)
  10. Trace                 (audit trail assembly + metadata + runtime)
  → RecommendationSet
```

### 2.3 Key Architectural Decisions

| Decision | Rationale |
|----------|-----------|
| Sequential pipeline (Approach A) | Deterministic, auditable, each stage independently testable. Clinical safety demands determinism. |
| Absolute safety as dedicated stages | HardSafetyFilter + InteractionCheck(Contraindicated) = absolute excludes. Never soft-scored. |
| Scoring confined to final stage | RankRecommendations operates only on survivors. Never resurrects excluded. |
| Domain objects layer | Readers return typed domain objects. Pipeline never sees SQLite columns or JSON keys. |
| Immutable PipelineState | `frozen=True, slots=True`. Mutation only via `dataclasses.replace()`. Impossible to accidentally mutate state. |
| DiagnosisProvider Protocol | Today JSON, tomorrow SQLite — engine doesn't change. |
| Interactions from drugs_reference | Single source of truth. No separate interaction_rules.json. |
| Config via EngineConfig | Constructor doesn't grow: weights, debug, cache, plugins all in config. |
| `guideline_id` is internal | Public API uses diagnosis names + ICD-10 codes. guideline_id never in PatientQuery. |

---

## 3. Data Flow & Data Sources

### 3.1 Data Flow: PatientQuery to RecommendationSet

```
Doctor / Application
    |
    v
+------------------------------------------------------------------+
|  Engine.recommend(PatientQuery)                                  |
|                                                                  |
|  PatientQuery = {                                                |
|    diagnosis: str | None,       # "vnebolnichnaya pnevmoniya"    |
|    icd10: str | None,           # "J18"                          |
|    patient: Patient {                                           |
|      age: float | None,                                          |
|      weight_kg: float | None,   # for pediatrics                |
|      pregnant: bool,                                             |
|      renal_function: float | None,  # GFR ml/min                |
|      hepatic_impairment: bool,                                   |
|      allergies: tuple[str, ...],   # drug classes                |
|      current_meds: tuple[str, ...], # for InteractionCheck       |
|    },                                                            |
|    preferences: Preferences {                                    |
|      therapy_line: str | None,  # "first" | "alternative" | ...  |
|      route_preference: str | None,                               |
|      population: str | None,    # "adult" | "child" | "neonate"  |
|    },                                                            |
|  }                                                               |
+------------------------------------------------------------------+
    |
    v
+--- Pipeline (10 stages, each pure, returns StageResult) --------+
|                                                                 |
|  1. DiagnosisMatch                                              |
|     reads: DiagnosisProvider (resources/diagnosis_index.json)   |
|     input: diagnosis str OR icd10 code                          |
|     output: guideline_ids: tuple[str, ...]                      |
|     degrade: not found -> empty result + engine_note            |
|    |                                                            |
|  2. RegimenLoad                                                 |
|     reads: SQLiteReader (NormalizerDB.load_by_guideline)        |
|     filter: ValidationPolicy (STRICT -> PASS only,              |
|             ALLOW_REVIEW -> PASS+REVIEW,                        |
|             DEBUG -> all)                                       |
|     output: candidates: tuple[Recommendation, ...]              |
|    |                                                            |
|  3. PopulationFilter                                            |
|     input: patient.age, preferences.population                 |
|     logic: adult->adult=True, child->child=True,                |
|            neonate->age < 28 days                               |
|    |                                                            |
|  4. TherapyLineSelect                                           |
|     input: preferences.therapy_line                            |
|     logic: "first"->therapy_line="first", etc.                  |
|            None -> all lines retained (ranking decides)         |
|    |                                                            |
|  5. HardSafetyFilter                                            |
|     reads: DrugReferenceReader (pregnancy_category,             |
|            age_restriction, contraindications)                  |
|     ABSOLUTE excludes: allergy, pregnancy CI, age, CI           |
|     ABSOLUTE decision -- never soft-scored                      |
|    |                                                            |
|  6. DoseCalculation                                             |
|     reads: DrugReferenceReader (pediatric_dosing)               |
|     adult: SQLite dose_value x frequency -> daily dose          |
|     peds: drugs_reference.pediatric_dosing.mg_per_kg_day        |
|           x weight_kg, clamp max_daily_mg                       |
|    |                                                            |
|  7. DoseAdjustment                                              |
|     reads: DrugReferenceReader (renal_adjustment,               |
|            hepatic_adjustment)                                  |
|     renal: GFR < threshold -> modify dose/freq                  |
|     hepatic: hepatic_impairment -> per drug data                |
|     CAN ESCALATE to excluded (hepatic CI)                       |
|    |                                                            |
|  8. InteractionCheck                                            |
|     reads: DrugReferenceReader.get_interactions(drug_ref)       |
|            + patient.current_meds                               |
|     CONTRAINDICATED -> exclude (absolute)                       |
|     MAJOR/MODERATE/MINOR/UNKNOWN -> warning + rank penalty      |
|    |                                                            |
|  9. RankRecommendations                                         |
|     reads: resources/score_profiles/{profile}.json              |
|     scoring (ONLY after all clinical filters):                  |
|       therapy_line, confidence, evidence recency,               |
|       safety fit, route, population, interaction penalty        |
|     plugin hooks: BeforeRanking / AfterRanking                  |
|    |                                                            |
|  10. Trace                                                      |
|     assembles: all StageTrace (Decision/Reason/Evidence)        |
|     + EngineMetadata (5 versions) + EngineRuntime               |
|     + DecisionContext (future LLM/logging hook)                 |
|     + source traceability (pdf/page/quote/section)              |
|     -> RecommendationSet                                        |
+-----------------------------------------------------------------+
    |
    v
+-----------------------------------------------------------------+
|  RecommendationSet = {                                          |
|    accepted: tuple[Recommendation, ...]  # sorted by rank      |
|    excluded: tuple[tuple[Recommendation, str], ...]            |
|    warnings: tuple[SafetyFlag, ...]    # non-excluding         |
|    traces: tuple[StageTrace, ...]       # full audit trail     |
|    safety_flags: tuple[SafetyFlag, ...]                       |
|    metadata: EngineMetadata              # 5 versions          |
|    runtime: EngineRuntime                # per-run info        |
|    decision_context: DecisionContext     # future hook         |
|    engine_notes: tuple[EngineNote, ...]  # system notes for UI |
|    query: PatientQuery                   # echo input          |
|    elapsed_ms: float                     # total pipeline time |
|  }                                                              |
+-----------------------------------------------------------------+
    |
    v
Doctor / Application
```

### 3.2 Data Sources — Roles & Boundaries

| Source | Type | Owner | Engine reads | Engine writes | Role |
|--------|------|-------|-------------|---------------|------|
| `metadata.sqlite` | SQLite | Pipeline | `normalized_regimens` (regimens only) | never | Single source of truth for **regimens**: drug/dose/route/freq/duration/population/therapy_line/confidence/verdict/source |
| `db/index.json` `drugs_reference` | JSON | antibio-calc | drugs_reference object | never | Single source of truth for **drug safety metadata**: renal/hepatic/pregnancy/age/CI/interactions/forms/dilution/pediatric_dosing |
| `resources/diagnosis_index.json` | JSON | clinical_engine | diagnosis-to-guideline_id map | never | Routing: diagnosis/ICD-10 to guideline_id (~294 entries, human-curated) |
| `resources/score_profiles/*.json` | JSON | clinical_engine | ranking weights per profile | never | Stage 9 config (therapy_line/confidence/recency/safety/route/population/interaction weights) |
| `resources/clinical_constants.json` | JSON | clinical_engine | age bands, GFR thresholds, allergy class map, units | never | Constants for PopulationFilter + DoseAdjustment |

### 3.3 One Source of Truth Per Domain

| Domain | Single source | Engine does NOT create duplicates |
|--------|-------------|----------------------------------|
| Regimens | SQLite | no |
| Drug safety | drugs_reference (`db/index.json`) | no interaction_rules.json, no separate safety.json |
| Diagnosis routing | `resources/diagnosis_index.json` | no |
| Ranking config | `resources/score_profiles/*.json` | no |
| Clinical constants | `resources/clinical_constants.json` | no |

### 3.4 Domain Objects Layer

```
SQLite (RegimenRecord)
    |
    v  SQLiteReader.to_candidate()
RecommendationCandidate (domain object -- pipeline knows nothing of SQLite)
    |
    v  Pipeline stages

drugs_reference JSON
    |
    v  DrugReferenceReader.get_drug_info()
DrugInfo (domain object -- pipeline knows nothing of JSON)
    |
    v  Pipeline stages

diagnosis_index JSON
    |
    v  JsonDiagnosisProvider.lookup()
DiagnosisEntry (domain object -- pipeline knows nothing of JSON)
    |
    v  DiagnosisMatch stage
```

### 3.5 drug_ref — Join Key

SQLite stores `drug_normalized` (e.g. `"amoxicillin"` in Russian). drugs_reference uses keys like `"amoxicillin"` in Latin. Engine needs a bridge:

- `DrugReferenceReader` holds internal mapping `drug_normalized -> drug_ref` (built from drugs_reference `inn` fields + synonyms).
- Mapping lives **inside reader** — not a separate file, not a second reference.
- If mapping not found -> stage works in degraded mode (WARNING flag, not crash).

### 3.6 ValidationPolicy — What Enters Pipeline

| Policy | Regimens from SQLite | Use case |
|--------|---------------------|----------|
| `STRICT` | only `validation_verdict = PASS` | Production, doctor |
| `ALLOW_REVIEW` | PASS + REVIEW | Research, audit |
| `DEBUG` | PASS + REVIEW + REJECT | Development, testing |
| `AUDIT` | all regimens, no clinical filters | Quality analysis (bypass safety stages) |

Applied at stage 2 (RegimenLoad). REJECT regimens never reach safety/ranking in STRICT mode.

---

## 4. Module Responsibilities

### 4.1 One Role Per Module

| Module | Responsibility | Does NOT do |
|--------|---------------|-------------|
| `config.py` | EngineConfig + ValidationPolicy + Profiles | I/O, logic |
| `engine.py` | Orchestrate pipeline, inject readers into stages, return RecommendationSet | Clinical logic |
| `models.py` | All dataclasses (frozen) | I/O, logic |
| `pipeline.py` | PipelineStage Protocol + PluginHook + runner | Clinical logic |
| `cache.py` | EngineCache stub (future LRU) | Everything else |
| `readers/sqlite_reader.py` | SQLite to RecommendationCandidate | Clinical logic, writes |
| `readers/drug_reference_reader.py` | drugs_reference JSON to DrugInfo | Clinical logic, writes |
| `readers/diagnosis_reader.py` | DiagnosisProvider Protocol + JsonDiagnosisProvider | Clinical logic, writes |
| `stages/*.py` | One pure pipeline stage each | I/O, mutation of input state |
| `plugins/__init__.py` | PluginHook hooks | Clinical logic |
| `resources/*.json` | Curated data | Code |

### 4.2 Readers Return Domain Objects

Readers are the **only** layer that touches SQLite or JSON files. They return typed domain objects. Stages never open files, run SQL, or parse JSON.

**SQLiteReader:**
- `load_regimens(guideline_ids: tuple[str, ...]) -> list[RecommendationCandidate]`
- Transforms `RegimenRecord` to `RecommendationCandidate` (maps columns to domain fields)
- Validates data types at read time (guard against corrupt SQLite)

**DrugReferenceReader:**
- `get_drug_info(drug_ref: str) -> DrugInfo | None`
- `resolve_drug_ref(drug_normalized: str) -> str | None`
- `get_interactions(drug_ref) -> str | None`
- `get_pregnancy_category(drug_ref) -> str | None`
- `get_renal_adjustment(drug_ref) -> str | None`
- Loads all `DrugInfo` once at init, caches in memory (frozen dict)

**DiagnosisProvider (Protocol):**
- `lookup(diagnosis: str | None, icd10: str | None) -> list[DiagnosisEntry]`
- Implementations: `JsonDiagnosisProvider` (v1), `SQLiteDiagnosisProvider` (future)

---

## 5. Public Interfaces

### 5.1 Enums (all in models.py)

```python
class ValidationPolicy(Enum):
    STRICT = "strict"
    ALLOW_REVIEW = "allow_review"
    DEBUG = "debug"
    AUDIT = "audit"

class SafetyLevel(Enum):
    WARNING = "warning"
    ABSOLUTE_CONTRAINDICATION = "absolute_contraindication"

class InteractionSeverity(Enum):
    UNKNOWN = 0       # cannot classify -- NOT defaulted to moderate
    MINOR = 1
    MODERATE = 2
    MAJOR = 3
    CONTRAINDICATED = 4

class PregnancyCategory(Enum):
    PROHIBITED = "prohibited"
    CAUTION = "caution"
    ALLOWED = "allowed"
    UNKNOWN = "unknown"

class RecommendationOutcome(Enum):
    ACCEPTED = "accepted"
    EXCLUDED = "excluded"
    WARNING = "warning"

class ClinicalPriority(Enum):
    FIRST_CHOICE = "first_choice"
    ALTERNATIVE = "alternative"
    RESERVE = "reserve"
    SALVAGE = "salvage"
    EXPERIMENTAL = "experimental"

class DecisionCode(Enum):
    ALLERGY = "allergy"
    PREGNANCY = "pregnancy"
    RENAL = "renal"
    AGE = "age"
    THERAPY_LINE = "therapy_line"
    POPULATION = "population"
    INTERACTION = "interaction"
    NO_MATCH = "no_match"
    DIAGNOSIS_RESOLVED = "diagnosis_resolved"  # added in audit remediation for semantic correctness on successful diagnosis match
    DRUG_UNKNOWN = "drug_unknown"
    DOSE_UNCALCULABLE = "dose_uncalculable"
    CI = "ci"
    HEPATIC = "hepatic"

class ConfidenceLevel(Enum):
    """Discrete confidence -- no false precision."""
    NONE = 0.0
    LOW = 0.25
    MEDIUM = 0.5
    HIGH = 0.75
    FULL = 1.0

class NoteSeverity(Enum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"

class DoseCalculationMethod(Enum):
    FIXED = "fixed"
    MG_PER_KG = "mg_per_kg"
    RENAL_ADJUSTED = "renal_adjusted"
    HEPATIC_ADJUSTED = "hepatic_adjusted"
    UNCALCULATED = "uncalculated"

class SafetyAction(Enum):
    """What the UI/physician should do."""
    STOP_IMMEDIATELY = "stop_immediately"
    AVOID_IF_POSSIBLE = "avoid_if_possible"
    MONITOR_CLOSELY = "monitor_closely"
    INFORM_PATIENT = "inform_patient"
```

### 5.2 Input Dataclasses (frozen=True, slots=True)

```python
@dataclass(frozen=True, slots=True)
class Patient:
    age: float | None = None
    weight_kg: float | None = None
    pregnant: bool = False
    renal_function: float | None = None     # GFR ml/min
    hepatic_impairment: bool = False
    allergies: tuple[str, ...] = ()          # drug classes
    current_meds: tuple[str, ...] = ()       # for InteractionCheck

@dataclass(frozen=True, slots=True)
class Preferences:
    therapy_line: str | None = None
    route_preference: str | None = None
    population: str | None = None

@dataclass(frozen=True, slots=True)
class PatientQuery:
    diagnosis: str | None = None
    icd10: str | None = None
    patient: Patient = field(default_factory=Patient)
    preferences: Preferences = field(default_factory=Preferences)
```

### 5.3 Domain Objects (readers return these)

```python
@dataclass(frozen=True, slots=True)
class DiagnosisEntry:
    guideline_id: str
    diagnosis_name: str
    icd10_codes: tuple[str, ...]
    guideline_title: str
    guideline_year: int | None
    guideline_revision_date: str | None      # full date, not just year
    source_url: str

@dataclass(frozen=True, slots=True)
class DrugForm:
    form_type: str
    concentration: str
    concentration_mg_per_ml: float | None = None
    notes: str | None = None

@dataclass(frozen=True, slots=True)
class DilutionRoute:
    solvent_options: tuple[dict[str, Any], ...]
    concentration_standard_mg_ml: float | None = None
    administration_time_min: float | None = None
    infusion_time_min: float | None = None
    contraindications: str | None = None
    cautions: str | None = None
    steps: tuple[str, ...] = ()

@dataclass(frozen=True, slots=True)
class PediatricDosing:
    mg_per_kg_day: float | None = None
    max_daily_mg: float | None = None
    weight_min_kg: float | None = None
    weight_max_kg: float | None = None
    age_min: str | None = None
    age_max: str | None = None
    freq_per_day: int | None = None

@dataclass(frozen=True, slots=True)
class DrugInfo:
    drug_ref: str
    inn: str
    drug_class: str
    renal_adjustment: str | None
    hepatic_adjustment: str | None
    pregnancy_category: PregnancyCategory
    age_restriction_min: str | None
    age_restriction_max: str | None
    contraindications: str | None
    interactions: str | None
    monitoring: str | None
    forms: tuple[DrugForm, ...]
    dilution: dict[str, DilutionRoute]
    pediatric_dosing: PediatricDosing | None

@dataclass(frozen=True, slots=True)
class RecommendationCandidate:
    regimen_id: str
    guideline_id: str
    drug_normalized: str
    drug_ref: str | None
    dose: float | None
    dose_unit: str
    route: str
    frequency: float | None
    duration_min: float | None
    duration_max: float | None
    duration_recommended: float | None
    therapy_line: str
    adult: bool
    child: bool
    pregnancy: bool | None
    renal_adjustment: bool
    atc_code: str
    confidence: float
    validation_verdict: str
    source_pdf: str
    source_page: str
    source_quote: str
    source_section: str               # v1: empty (SQLite lacks this column; future schema extension)
    diagnosis: str
    mkb: str
    guideline_year: int | None        # from DiagnosisEntry (diagnosis_index), not SQLite
```

### 5.4 Safety, Trace, Dose, Confidence

```python
@dataclass(frozen=True, slots=True)
class SafetyFlag:
    level: SafetyLevel
    code: str                                  # "ALLERGY", "PREGNANCY_CI", ...
    message: str                               # human-readable
    drug_ref: str
    stage: str                                 # which stage raised it
    action: SafetyAction                       # what physician should do
    requires_physician_acknowledgement: bool   # for Flutter UI confirmation

@dataclass(frozen=True, slots=True)
class Evidence:
    source_pdf: str
    source_page: str
    source_quote: str
    source_section: str
    guideline_title: str | None
    guideline_year: int | None
    guideline_revision_date: str | None        # full date
    source_url: str | None

@dataclass(frozen=True, slots=True)
class StageTrace:
    stage_name: str
    decision_code: DecisionCode
    reason: str
    evidence: Evidence | None = None
    decision_confidence: ConfidenceLevel = ConfidenceLevel.FULL
    # immutable + append-only (invariant #6)

@dataclass(frozen=True, slots=True)
class DoseDetail:
    calculated_dose_mg: float | None
    dose_unit: str
    frequency_per_day: float | None
    duration_days: float | None
    max_daily_mg: float | None
    calculation_method: DoseCalculationMethod
    adjustment_applied: str | None
    calculation_note: str | None
    adjustment_history: tuple[str, ...] = ()   # ["base: 500mg", "renal: 250mg", "final: 250mg"]

@dataclass(frozen=True, slots=True)
class ConfidenceBreakdown:
    source: float           # SQLite overall_confidence
    decision: float         # mean of stage DecisionConfidence values
    dose: float             # dose calculation state
    completeness: float     # warning flags penalty
    evidence: float         # guideline recency
    final: float            # weighted sum
```

### 5.5 Recommendation and Result

```python
@dataclass(frozen=True, slots=True)
class Recommendation:
    candidate: RecommendationCandidate
    dose: DoseDetail | None
    safety_flags: tuple[SafetyFlag, ...]
    interaction_severity: InteractionSeverity | None
    outcome: RecommendationOutcome | None = None
    rank: int | None = None
    score: float | None = None
    score_breakdown: dict[str, float] = field(default_factory=dict)
    trace: tuple[StageTrace, ...] = ()
    confidence: float = 0.0
    confidence_breakdown: ConfidenceBreakdown | None = None
    clinical_priority: ClinicalPriority | None = None

@dataclass(frozen=True, slots=True)
class EngineNote:
    code: str
    message: str
    stage: str
    severity: NoteSeverity

@dataclass(frozen=True, slots=True)
class EngineMetadata:
    decision_engine_version: str              # "1.0.0" -- engine SEMVER
    knowledge_dataset_version: str            # "KB-2026-07-09" -- dataset version, not file hash
    normalizer_version: str                   # from SQLite rows
    dictionary_version: str                   # medical_dictionary/metadata.json version
    guideline_version: str                    # guideline set version (from diagnosis_index)

@dataclass(frozen=True, slots=True)
class EngineRuntime:
    generated_at: str                         # ISO 8601 timestamp
    elapsed_ms: float
    profile: ValidationPolicy
    pipeline_time_breakdown: dict[str, float] # {"diagnosis": 1.2, "safety": 4.1, ...}

@dataclass(frozen=True, slots=True)
class DecisionContext:
    """Future LLM/logging integration point."""
    patient: Patient
    query: PatientQuery
    engine_metadata: EngineMetadata
    runtime: EngineRuntime
    profile: ValidationPolicy

@dataclass(frozen=True, slots=True)
class RecommendationSet:
    accepted: tuple[Recommendation, ...]
    excluded: tuple[tuple[Recommendation, str], ...]
    warnings: tuple[SafetyFlag, ...]
    traces: tuple[StageTrace, ...]
    safety_flags: tuple[SafetyFlag, ...]
    metadata: EngineMetadata
    runtime: EngineRuntime
    decision_context: DecisionContext
    engine_notes: tuple[EngineNote, ...]
    query: PatientQuery
    elapsed_ms: float

@dataclass(frozen=True, slots=True)
class DecisionReport:
    """Complete clinical decision report. Exportable."""
    query: PatientQuery
    accepted: tuple[Recommendation, ...]
    excluded: tuple[tuple[Recommendation, str], ...]
    warnings: tuple[SafetyFlag, ...]
    traces: tuple[StageTrace, ...]
    confidence_breakdowns: dict[str, ConfidenceBreakdown]
    metadata: EngineMetadata
    runtime: EngineRuntime
    engine_notes: tuple[EngineNote, ...]

    def to_dict(self) -> dict[str, Any]: ...
    def to_json(self) -> str: ...
    # to_pdf() deferred to v2 (requires rendering library)
```

### 5.6 config.py

```python
@dataclass(frozen=True, slots=True)
class EngineConfig:
    sqlite_path: str
    drug_reference_path: str = "db/index.json"
    diagnosis_index_path: str = "clinical_engine/resources/diagnosis_index.json"
    score_profile: str = "default"            # which score_profiles/*.json to use
    clinical_constants_path: str = "clinical_engine/resources/clinical_constants.json"
    validation_policy: ValidationPolicy = ValidationPolicy.STRICT
    debug: bool = False
    cache_readers: bool = True

class Profiles:
    @staticmethod
    def production(sqlite_path: str) -> EngineConfig: ...
    @staticmethod
    def research(sqlite_path: str) -> EngineConfig: ...
    @staticmethod
    def development(sqlite_path: str) -> EngineConfig: ...
    @staticmethod
    def audit(sqlite_path: str) -> EngineConfig: ...
```

### 5.7 pipeline.py

```python
class PipelineStage(Protocol):
    name: str
    def run(self, state: PipelineState, ctx: StageContext) -> StageResult: ...

class PluginHook(Enum):
    BEFORE_RANKING = "before_ranking"
    AFTER_RANKING = "after_ranking"
    BEFORE_DOSE = "before_dose"
    AFTER_DOSE = "after_dose"
    BEFORE_RETURN = "before_return"

@dataclass(frozen=True, slots=True)
class ClinicalConstants:
    """Typed constants -- not dict."""
    age_bands: dict[str, tuple[float, float]]
    renal_thresholds: dict[str, float]
    allergy_class_map: dict[str, str]
    allergy_class_hierarchy: dict[str, tuple[str, ...]]
    # Note: interaction severity keywords are NOT here -- they belong to
    # preparation-time tooling that builds structured fields in drugs_reference.
    # Engine does not parse interaction text at runtime (invariant #13).

@dataclass(frozen=True, slots=True)
class ScoreWeights:
    """Typed score weights -- not dict."""
    therapy_line_match: float
    confidence: float
    evidence_recency: float
    safety_fit: float
    route_preference: float
    population_match: float
    interaction_penalty: float

@dataclass(frozen=True, slots=True)
class StageContext:
    config: EngineConfig
    sqlite_reader: SQLiteReader
    drug_ref_reader: DrugReferenceReader
    diagnosis_provider: DiagnosisProvider
    constants: ClinicalConstants
    score_weights: ScoreWeights

@dataclass(frozen=True, slots=True)
class StageResult:
    state: PipelineState
    metrics: dict[str, Any] = field(default_factory=dict)
    elapsed_ms: float = 0.0
    warnings: tuple[str, ...] = ()

@dataclass(frozen=True, slots=True)
class PipelineState:
    # immutable -- stages use dataclasses.replace()
    patient: PatientQuery
    guideline_ids: tuple[str, ...] = ()
    candidates: tuple[Recommendation, ...] = ()
    excluded: tuple[tuple[Recommendation, str], ...] = ()
    traces: tuple[StageTrace, ...] = ()        # immutable + append-only
    safety_flags: tuple[SafetyFlag, ...] = ()
```

### 5.8 engine.py

```python
class Engine:
    def __init__(self, config: EngineConfig) -> None: ...
    def recommend(self, query: PatientQuery) -> RecommendationSet: ...
    def build_report(self, result: RecommendationSet) -> DecisionReport: ...
    @property
    def metadata(self) -> EngineMetadata: ...
```

### 5.9 Engine Usage

```python
from clinical_engine import Engine, PatientQuery, Patient, Preferences, Profiles

engine = Engine(Profiles.production("C:/clinrec_downloader/metadata.sqlite"))
result = engine.recommend(PatientQuery(
    diagnosis="vnebolnichnaya pnevmoniya",
    patient=Patient(age=45),
    preferences=Preferences(therapy_line="first"),
))
# result.accepted[0].rank == 1
# result.metadata.decision_engine_version
# result.traces -- full audit trail
# result.engine_notes -- system notes for UI

report = engine.build_report(result)
report.to_json()  # export
```

---

## 6. Safety Stages

### 6.1 Stage 5: HardSafetyFilter

**Responsibility:** Absolute clinical exclusions. Drugs that must NEVER reach the patient. No soft scoring, no "maybe". Excluded drugs are final.

**Reads:** DrugReferenceReader (pregnancy_category, age_restriction, contraindications), ClinicalConstants (allergy_class_map, allergy_class_hierarchy)

**Algorithm:**

```
FOR each candidate IN state.candidates:
    drug_info = drug_ref_reader.get_drug_info(candidate.drug_ref)

    IF drug_info IS None:
        -> WARNING flag "DRUG_UNKNOWN", keep candidate
        -> trace: DecisionCode.NO_MATCH, confidence=HIGH
        -> CONTINUE

    # 1. Allergy check (ABSOLUTE) -- checks class hierarchy
    drug_class = constants.allergy_class_map.get(candidate.drug_ref)
    IF drug_class IN patient.allergies:
        -> EXCLUDE
        -> SafetyFlag(ABSOLUTE_CONTRAINDICATION, "ALLERGY",
             "{drug} is {class}, patient allergic",
             action=STOP_IMMEDIATELY, requires_ack=True)
        -> trace: DecisionCode.ALLERGY, confidence=FULL
        -> CONTINUE

    # 2. Pregnancy check (ABSOLUTE)
    IF patient.pregnant AND drug_info.pregnancy_category == PROHIBITED:
        -> EXCLUDE
        -> SafetyFlag(ABSOLUTE_CONTRAINDICATION, "PREGNANCY_CI",
             action=STOP_IMMEDIATELY, requires_ack=True)
        -> trace: DecisionCode.PREGNANCY, confidence=FULL
        -> CONTINUE

    # 3. Age restriction check (ABSOLUTE)
    IF patient.age IS NOT None:
        min_age = parse_age_restriction(drug_info.age_restriction_min)
        max_age = parse_age_restriction(drug_info.age_restriction_max)
        IF min_age IS NOT None AND patient.age < min_age:
            -> EXCLUDE, trace: DecisionCode.AGE, confidence=FULL
        IF max_age IS NOT None AND patient.age > max_age:
            -> EXCLUDE, trace: DecisionCode.AGE, confidence=FULL

    # 4. Contraindication check (ABSOLUTE)
    IF drug_info.contraindications IS NOT None:
        matched_cis = match_contraindications(drug_info.contraindications, patient)
        IF matched_cis:
            -> EXCLUDE, trace: DecisionCode.CI, confidence=HIGH

    # 5. Survived all checks
    -> keep in candidates
    -> trace: DecisionCode.(none), "Passed safety filter", confidence=FULL

RETURN: candidates (survivors), excluded (with reasons), safety_flags
```

**Edge cases:**

| Case | Behavior |
|------|----------|
| `drug_ref` not in drugs_reference | WARNING (not exclude) -- "DRUG_UNKNOWN", candidate passes |
| `patient.age` is None | Skip age check, add WARNING "AGE_UNKNOWN" |
| `pregnancy_category` is UNKNOWN | Skip pregnancy check, add WARNING |
| `pregnancy_category` = CAUTION | NOT excluded -- passes to warnings, rank penalty |
| `contraindications` text unparseable | Skip CI check, WARNING "CI_UNPARSED" |
| `allergies` empty | Skip allergy check |

**Degraded mode principle:** Missing data -> WARNING, never silent exclude. Only exclude on **positive** evidence of contraindication. False exclusion is as dangerous as false inclusion.

**Allergy class hierarchy:** checks not just drug name but entire class. Example: penicillins -> (amoxicillin, ampicillin, amoxiclav, piperacillin, ...). All drugs in the class are excluded if patient is allergic to the class.

**Pregnancy categories (internal Enum):** `PregnancyCategory.PROHIBITED` -> exclude. `CAUTION` -> warning + rank penalty. `ALLOWED` -> pass. `UNKNOWN` -> warning, pass.

**Plugin hooks:** None. Safety is non-negotiable, no plugin override.

### 6.2 Stage 6: DoseCalculation

**Responsibility:** Calculate base dose. Adult: from SQLite. Pediatric: mg/kg/day from drugs_reference. No adjustments yet (stage 7).

**Reads:** candidate.dose/frequency (from SQLite), DrugReferenceReader.pediatric_dosing

**Algorithm:**

```
FOR each candidate IN state.candidates:
    population = resolve_population(patient, preferences)

    IF population == "adult" OR (candidate.adult AND NOT candidate.child):
        # Adult: fixed dose from SQLite
        IF candidate.dose IS NOT None AND candidate.frequency IS NOT None:
            -> DoseDetail(
                calculated_dose_mg=candidate.dose,
                frequency_per_day=candidate.frequency,
                duration_days=candidate.duration_recommended,
                calculation_method=FIXED,
                calculation_note=None,
                adjustment_history=("base: {dose}mg",)
            )
        ELSE:
            -> WARNING "DOSE_UNCALCULABLE"
            -> DoseDetail(calculation_method=UNCALCULATED, ...)

    ELIF population == "child" OR "neonate":
        # Pediatric: mg/kg/day from drugs_reference
        peds = drug_info.pediatric_dosing

        IF peds IS None:
            -> WARNING "PEDS_DOSING_UNKNOWN"
            -> DoseDetail(calculation_method=UNCALCULATED, ...)
            -> trace: DecisionCode.DOSE_UNCALCULABLE, confidence=HIGH
            -> CONTINUE

        IF patient.weight_kg IS None:
            -> WARNING "WEIGHT_REQUIRED_FOR_PEDS"
            -> DoseDetail(calculation_method=UNCALCULATED, ...)
            -> trace: DecisionCode.DOSE_UNCALCULABLE, confidence=FULL
            -> CONTINUE

        # Check weight band
        IF peds.weight_min_kg AND weight_kg < peds.weight_min_kg:
            -> WARNING "BELOW_WEIGHT_BAND"
        IF peds.weight_max_kg AND weight_kg > peds.weight_max_kg:
            -> WARNING "ABOVE_WEIGHT_BAND"

        daily_dose_mg = peds.mg_per_kg_day * patient.weight_kg

        # Clamp to max daily
        IF peds.max_daily_mg IS NOT None:
            daily_dose_mg = min(daily_dose_mg, peds.max_daily_mg)

        single_dose_mg = daily_dose_mg / candidate.frequency

        -> DoseDetail(
            calculated_dose_mg=single_dose_mg,
            max_daily_mg=peds.max_daily_mg,
            calculation_method=MG_PER_KG,
            calculation_note=f"{peds.mg_per_kg_day} mg/kg/day x {weight_kg} kg = {daily_dose_mg} mg/day",
            adjustment_history=(f"base: {daily_dose_mg}mg/day",)
        )
        -> trace: "Pediatric dose calculated", confidence=FULL

    ELSE:
        -> WARNING "POPULATION_AMBIGUOUS"
        -> DoseDetail(calculation_method=UNCALCULATED, ...)
```

**Edge cases:**

| Case | Behavior |
|------|----------|
| SQLite dose is None | WARNING, uncalculated |
| Peds drug not in drugs_reference | WARNING "PEDS_DOSING_UNKNOWN", uncalculated |
| Weight missing for peds | WARNING "WEIGHT_REQUIRED", uncalculated |
| Weight outside band | WARNING but still calculates (clinician reviews) |
| Neonate without neonatal-specific dosing | WARNING "NEONATE_DOSING_UNKNOWN" |
| frequency is None | daily_dose calculated but single_dose=None |

**Plugin hook:** `BEFORE_DOSE` -- allows plugin to inject custom dosing logic.

### 6.3 Stage 7: DoseAdjustment

**Responsibility:** Modify calculated dose for renal/hepatic impairment. Operates on DoseDetail from stage 6.

**Reads:** DrugReferenceReader (renal_adjustment, hepatic_adjustment), ClinicalConstants (renal_thresholds)

**Algorithm:**

```
FOR each candidate IN state.candidates:
    IF candidate.dose.calculation_method == UNCALCULATED:
        -> skip (can't adjust what wasn't calculated)
        -> CONTINUE

    adjustments = []

    # 1. Renal adjustment
    IF patient.renal_function IS NOT None:
        renal_data = drug_info.renal_adjustment

        IF renal_data IS None OR renal_data == "Not required":
            -> no adjustment needed
        ELIF renal_data is structured:  # {"threshold": 30, "action": "extend_interval"}
            # Apply structured rules directly -- no text parsing at runtime
            IF patient.renal_function < renal_data.threshold:
                adjusted_dose = apply_renal_adjustment(candidate.dose, renal_data)
                -> replace DoseDetail with adjusted values
                -> calculation_method=RENAL_ADJUSTED
                -> adjustment_history += ("renal GFR {value}: {adjusted}",)
                -> SafetyFlag(WARNING, "RENAL_ADJ",
                     action=MONITOR_CLOSELY, requires_ack=False)
                -> trace: DecisionCode.RENAL, confidence=HIGH
                adjustments.append("renal")
            ELSE:
                -> trace: "GFR {value} above threshold for {drug}", confidence=HIGH
        ELSE:
            # Free text only -- do NOT parse at runtime (invariant #13)
            -> WARNING "RENAL_ADJ_UNPARSED"
            -> dose unadjusted, clinician reviews manually
            -> trace: DecisionCode.RENAL, confidence=MEDIUM

    # 2. Hepatic adjustment
    IF patient.hepatic_impairment:
        hepatic_text = drug_info.hepatic_adjustment

        IF hepatic_text IS None:
            -> WARNING "HEPATIC_NO_DATA"
        ELIF "Prohibited" in hepatic_text OR "Contraindicated" in hepatic_text:
            -> EXCLUDE (escalate to absolute)
            -> SafetyFlag(ABSOLUTE_CONTRAINDICATION, "HEPATIC_CI",
                 action=STOP_IMMEDIATELY, requires_ack=True)
            -> trace: DecisionCode.HEPATIC, confidence=FULL
            -> move to excluded[]
        ELIF "Caution" in hepatic_text:
            -> SafetyFlag(WARNING, "HEPATIC_CAUTION",
                 action=MONITOR_CLOSELY)
            -> no dose change
        ELSE:
            -> parse specific adjustment
            -> calculation_method=HEPATIC_ADJUSTED
            -> adjustment_history += ("hepatic: {adjusted}",)
            adjustments.append("hepatic")

    # 3. Both renal + hepatic
    IF "renal" in adjustments AND "hepatic" in adjustments:
        -> most conservative (lowest dose, longest interval)
        -> SafetyFlag(WARNING, "RENAL_HEPATIC_DUAL", action=MONITOR_CLOSELY)

    IF NOT adjustments:
        -> trace: "No adjustment needed", confidence=FULL
```

**Key safety principle:** DoseAdjustment CAN ESCALATE to exclusion (hepatic CI). It CANNOT de-escalate a HardSafetyFilter exclusion.

**Structured renal adjustment:** drugs_reference should be gradually migrated to structured fields (`{"threshold": 30, "action": "extend_interval"}`). Engine applies structured rules directly. If only free text exists -> WARNING "RENAL_ADJ_UNPARSED", dose unadjusted. No free-text parsing at runtime (invariant #13).

**Adjustment history:** Each adjustment appends to `DoseDetail.adjustment_history` tuple. Physician sees full chain: base -> renal -> hepatic -> final.

**Plugin hook:** `AFTER_DOSE` -- allows plugin to validate adjusted dose.

### 6.4 Stage 8: InteractionCheck

**Responsibility:** Check drug-drug interactions against patient's current medications. Classify severity. Does NOT exclude by default -- clinician decides. But `CONTRAINDICATED` severity IS an absolute exclusion.

**Reads:** DrugReferenceReader.get_interactions(drug_ref), ClinicalConstants.interaction_keywords

**Algorithm:**

```
IF patient.current_meds IS EMPTY:
    -> skip (no interactions to check)
    -> trace: "No current meds, interactions skipped"
    -> RETURN state unchanged

FOR each candidate IN state.candidates:
    drug_info = drug_ref_reader.get_drug_info(candidate.drug_ref)

    IF drug_info.interactions IS None:
        -> no interaction data for this drug
        -> CONTINUE

    # v1: check for structured interaction fields first
    # (drugs_reference gradually migrated from free text to structured)
    IF drug_info has structured_interactions:
        # Apply structured rules directly -- no text parsing at runtime
        matched = check_structured_interactions(drug_info, patient.current_meds)
        IF NOT matched:
            -> CONTINUE
        severity = matched.severity   # already classified in drugs_reference
    ELSE:
        # Free text only -- do NOT parse at runtime (invariant #13)
        # Check if any current_med name appears in interactions text
        has_match = any(med in drug_info.interactions for med in patient.current_meds)
        IF NOT has_match:
            -> CONTINUE
        # Match found but cannot classify -- UNKNOWN, not guessed
        severity = InteractionSeverity.UNKNOWN

    IF severity == CONTRAINDICATED:
        -> EXCLUDE
        -> SafetyFlag(ABSOLUTE_CONTRAINDICATION, "INTERACTION_CI",
             action=STOP_IMMEDIATELY, requires_ack=True)
        -> trace: DecisionCode.INTERACTION, confidence=FULL

    ELIF severity == MAJOR:
        -> SafetyFlag(WARNING, "INTERACTION_MAJOR",
             action=AVOID_IF_POSSIBLE, requires_ack=False)
        -> trace: DecisionCode.INTERACTION, confidence=HIGH
        -> candidate stays, rank penalized

    ELIF severity == MODERATE:
        -> SafetyFlag(WARNING, "INTERACTION_MODERATE",
             action=MONITOR_CLOSELY)

    ELIF severity == MINOR:
        -> SafetyFlag(WARNING, "INTERACTION_MINOR",
             action=INFORM_PATIENT)

    ELIF severity == UNKNOWN:
        -> SafetyFlag(WARNING, "INTERACTION_UNKNOWN",
             action=MONITOR_CLOSELY)
        -> trace: DecisionCode.INTERACTION, confidence=MEDIUM
        -> NOT defaulted to MODERATE -- physician sees "classification unknown"

RETURN: candidates with interaction_severity + safety_flags
```

**Severity classification** (applied at drugs_reference preparation time, NOT at runtime):

| Severity | Keywords (for preparation-time classification) |
|----------|----------|
| CONTRAINDICATED (4) | "contraindicated", "life-threatening", "never mix", "strictly prohibited" |
| MAJOR (3) | "dangerous", "inactivation", "antagonism", "bleeding risk", "serotonin syndrome" |
| MODERATE (2) | "caution", "reduces effect", "increases risk", "inhibits CYP", "QT prolongation" |
| MINOR (1) | "reduces absorption", "antacids", "may reduce", "minor" |
| UNKNOWN (0) | no keyword match -- shown as unknown, NOT defaulted |

**Structured interactions migration:** drugs_reference should be gradually migrated to structured interaction fields (e.g., `{" interacts_with": "warfarin", "severity": "major", "note": "..."}`). Engine applies structured rules. If only free text exists -> severity=UNKNOWN. The keyword table above guides the preparation-time classification, not runtime parsing.

**Edge cases:**

| Case | Behavior |
|------|----------|
| `current_meds` empty | Skip entirely |
| `interactions` text is None | Skip, no warning |
| No keyword matches severity | UNKNOWN (not MODERATE) |
| Multiple current meds match | Highest severity wins |
| Drug interacts with itself | Skip self-match |

### 6.5 Safety Invariant Chain (Constitution)

```
HardSafetyFilter --> EXCLUDED = FINAL (no resurrection)
                              |
DoseCalculation ---> no exclusions (calculates or warns)
                              |
DoseAdjustment ----> CAN ESCALATE to excluded (hepatic CI)
                     cannot de-escalate HardSafety exclusions
                              |
InteractionCheck --> CONTRAINDICATED -> excluded (FINAL)
                     MAJOR/MODERATE/MINOR/UNKNOWN -> warning + rank penalty
                              |
RankRecommendations -> operates ONLY on survivors
                       NEVER touches excluded[]
```

---

## 7. Ranking, Trace, Versioning & Confidence

### 7.1 Stage 9: RankRecommendations

**Responsibility:** Score surviving candidates with weighted system. Operates ONLY on `state.candidates`. Never touches `state.excluded`. Scores acceptable options -- it does not make clinical decisions.

**Reads:** ScoreWeights (from `resources/score_profiles/{profile}.json`)

**ScoreWeights (typed, frozen):**

```python
@dataclass(frozen=True, slots=True)
class ScoreWeights:
    therapy_line_match: float = 3.0
    confidence: float = 2.0
    evidence_recency: float = 1.5
    safety_fit: float = 2.5
    route_preference: float = 1.0
    population_match: float = 1.5
    interaction_penalty: float = 0.5    # multiplied by severity (1-4)
```

**Score profiles** (`resources/score_profiles/*.json`):
- `default.json` -- general clinical use
- `ent.json` -- ENT infections (emphasizes first-line, oral route)
- `urology.json` -- urological infections (emphasizes renal safety)
- `icu.json` -- ICU (emphasizes IV route, safety, interactions)
- `pediatrics.json` -- pediatric (emphasizes weight-based dosing, age safety)

**Algorithm:**

```
# Plugin hook: BEFORE_RANKING
state = run_plugins(PluginHook.BEFORE_RANKING, state)

FOR each candidate IN state.candidates:
    score = 0.0
    score_breakdown = {}

    # 1. Therapy line match (highest weight)
    IF preferences.therapy_line IS NOT None:
        IF candidate.therapy_line == preferences.therapy_line:
            score += weights.therapy_line_match
        ELSE:
            partial = therapy_line_partial_score(pref, candidate.therapy_line)
            score += partial
    ELSE:
        IF candidate.therapy_line == "first":
            score += weights.therapy_line_match * 0.5  # clinical convention

    # 2. Confidence (from SQLite overall_confidence)
    score += candidate.confidence * weights.confidence

    # 3. Evidence recency (guideline_year)
    IF candidate.guideline_year IS NOT None:
        recency = normalize_recency(candidate.guideline_year)  # 0.0-1.0
        score += recency * weights.evidence_recency

    # 4. Safety fit (penalize warnings)
    flag_penalty = sum(safety_penalty(f) for f in candidate.safety_flags if f.level == WARNING)
    safety_score = max(0.0, weights.safety_fit - flag_penalty)
    score += safety_score

    # 5. Route preference
    IF preferences.route_preference IS NOT None:
        IF candidate.route == preferences.route_preference:
            score += weights.route_preference

    # 6. Population match
    score += score_population_match(candidate, patient) * weights.population_match

    # 7. Interaction severity penalty (numeric: Unknown=0..Contraindicated=4)
    IF candidate.interaction_severity IS NOT None:
        sev = candidate.interaction_severity.value
        score -= sev * weights.interaction_penalty

    candidate.score = score           # via replace()
    candidate.score_breakdown = score_breakdown

# Sort by score descending
ranked = sorted(state.candidates, key=lambda c: c.score, reverse=True)

# Assign ranks (1-based)
FOR i, candidate IN enumerate(ranked, start=1):
    candidate = replace(candidate, rank=i)
    -> trace: "Ranked #{i}", confidence=FULL

# Plugin hook: AFTER_RANKING
state = run_plugins(PluginHook.AFTER_RANKING, state)

RETURN: state with candidates sorted + ranked
```

**therapy_line_partial_score:**

| Preference | first | alternative | reserve | prophylaxis | empiric | unknown |
|------------|-------|-------------|---------|-------------|---------|---------|
| "first" | 1.0 | 0.5 | 0.3 | 0.2 | 0.4 | 0.1 |
| "alternative" | 0.3 | 1.0 | 0.5 | 0.2 | 0.4 | 0.1 |
| "reserve" | 0.2 | 0.5 | 1.0 | 0.1 | 0.3 | 0.1 |

**normalize_recency:**

| guideline_year | score |
|----------------|-------|
| 2024-2026 | 1.0 |
| 2021-2023 | 0.7 |
| 2016-2020 | 0.4 |
| < 2016 | 0.2 |

**Key ranking invariant:** RankRecommendations operates ONLY on `state.candidates`. It CANNOT:
- Access `state.excluded`
- Add candidates
- Change SafetyFlags
- Change DoseDetail
- Drop score below 0.0 (minimum = 0.0)

### 7.2 Stage 10: Trace

**Responsibility:** Assemble full decision audit trail. No clinical decisions. Creates the auditable record.

**Output: RecommendationSet**

**Algorithm:**

```
# Determine outcome for each candidate
accepted = []
FOR each candidate IN state.candidates:
    IF candidate.safety_flags contains ABSOLUTE_CONTRAINDICATION:
        outcome = EXCLUDED   # defensive (should not happen)
    ELIF candidate.safety_flags contains WARNING:
        outcome = WARNING
    ELSE:
        outcome = ACCEPTED
    candidate = replace(candidate, outcome=outcome)
    accepted.append(candidate)

# Collect excluded with outcome
excluded_final = []
FOR each (rec, reason) IN state.excluded:
    rec = replace(rec, outcome=EXCLUDED)
    excluded_final.append((rec, reason))

# Collect non-excluding warnings
all_warnings = [f for f in state.safety_flags if f.level == WARNING]

# Build EngineMetadata (5 versions)
metadata = EngineMetadata(
    decision_engine_version=ENGINE_VERSION,
    knowledge_dataset_version=...,   # "KB-2026-07-09"
    normalizer_version=...,
    dictionary_version=...,
    guideline_version=...,
)

# Build EngineRuntime
runtime = EngineRuntime(
    generated_at=iso_timestamp,
    elapsed_ms=total_elapsed,
    profile=config.validation_policy,
    pipeline_time_breakdown={stage_name: elapsed_ms for each stage},
)

# Build DecisionContext (future LLM/logging hook)
decision_context = DecisionContext(
    patient=state.patient,
    query=original_query,
    engine_metadata=metadata,
    runtime=runtime,
    profile=config.validation_policy,
)

# Plugin hook: BEFORE_RETURN
state = run_plugins(PluginHook.BEFORE_RETURN, state)

RETURN RecommendationSet(...)
```

### 7.3 Confidence Propagation

Each Recommendation carries a final confidence combining:

1. **Source confidence** -- `overall_confidence` from SQLite (normalization quality)
2. **Decision confidence** -- per-stage `DecisionConfidence` (mean of all stage trace values)
3. **Dose confidence** -- whether dose was calculated, adjusted, or uncalculated
4. **Completeness confidence** -- absence of safety warning flags
5. **Evidence confidence** -- guideline recency

**Formula:**

```
recommendation_confidence = (
    source_confidence * 0.35 +
    decision_confidence_mean * 0.25 +
    dose_confidence * 0.20 +
    completeness_confidence * 0.10 +
    evidence_confidence * 0.10
)
```

**DecisionConfidence per stage (discrete ConfidenceLevel):**

| Stage | Decision | Confidence | Reason |
|-------|----------|-----------|--------|
| HardSafetyFilter | ALLERGY | FULL | Exact drug class match with patient allergy |
| HardSafetyFilter | PREGNANCY | FULL | Drug pregnancy category explicitly PROHIBITED |
| DoseAdjustment | RENAL | HIGH | GFR value known, threshold established, drug in reference |
| DoseAdjustment | RENAL | MEDIUM | Threshold established, but renal text unstructured |
| InteractionCheck | INTERACTION | MEDIUM | Interactions text parsed, match found, severity=UNKNOWN |
| DiagnosisMatch | NO_MATCH | NONE | Diagnosis not found in index |

**ConfidenceBreakdown:**

```python
@dataclass(frozen=True, slots=True)
class ConfidenceBreakdown:
    source: float           # SQLite overall_confidence
    decision: float         # mean of stage DecisionConfidence values
    dose: float             # 1.0 if calculated, 0.5 if adjusted, 0.0 if uncalculated
    completeness: float     # 1.0 if no warnings, -0.1 per warning
    evidence: float         # guideline recency (0.2-1.0)
    final: float            # weighted sum
```

### 7.4 Versioning

**EngineMetadata (frozen):**

| Field | Source | Example |
|-------|--------|---------|
| `decision_engine_version` | Engine SEMVER | "1.0.0" |
| `knowledge_dataset_version` | Dataset label | "KB-2026-07-09" |
| `normalizer_version` | SQLite rows (normalizer_version column) | "1.2.0" |
| `dictionary_version` | medical_dictionary/metadata.json | "1.0.0" |
| `guideline_version` | diagnosis_index.json guideline_set_version | "2024-07" |

**EngineRuntime (frozen, separate from metadata):**

| Field | Description |
|-------|-------------|
| `generated_at` | ISO 8601 timestamp (per-run, not engine property) |
| `elapsed_ms` | Total pipeline execution time |
| `profile` | Which ValidationPolicy was used |
| `pipeline_time_breakdown` | Per-stage elapsed time: {"diagnosis": 1.2, "safety": 4.1, ...} |

**Reproducibility:** Any RecommendationSet can be fully reproduced given:
- PatientQuery (echoed in result)
- EngineConfig (paths + profile)
- 5 version strings (which data was used)

If any component updates (normalizer reprocesses SQLite, dictionary adds synonyms, engine updates logic), versions change -> old results distinguishable from new.

### 7.5 Source Traceability (full)

```python
@dataclass(frozen=True, slots=True)
class Evidence:
    source_pdf: str
    source_page: str
    source_quote: str
    source_section: str               # "Antibacterial therapy, p.28, para 2"
    guideline_title: str | None       # "Community-acquired pneumonia in adults"
    guideline_year: int | None        # 2024
    guideline_revision_date: str | None  # "2024-03-15"
    source_url: str | None            # "https://cr.minzdrav.gov.ru/recomend/654"
```

Each Recommendation includes `trace: tuple[StageTrace, ...]`, where each StageTrace may include Evidence. Evidence traceability is populated from:
- `RecommendationCandidate.source_pdf/page/quote/section` (from SQLite)
- `DiagnosisEntry.guideline_title/year/revision_date/source_url` (from diagnosis index)

**Physician view example:**

```
Recommendation: Amoxicillin 500mg x 3/day, 5-7 days
|-- Rank: #1 (score: 8.7)
|-- Source: CR "Community-acquired pneumonia in adults" (2024)
|   |-- URL: https://cr.minzdrav.gov.ru/recomend/654
|   |-- Section: "Antibacterial therapy", p.28
|   |-- Quote: "Drug of choice -- amoxicillin 500mg 3x/day 5-7 days"
|-- Confidence: 0.87
|   |-- Source: 0.92
|   |-- Decision: 0.90
|   |-- Dose: 1.00
|   |-- Completeness: 0.70 (1 warning: interaction minor)
|-- Safety: WARNING (interaction minor -- antacids reduce absorption)
|-- Versions: engine 1.0.0 / normalizer 1.2.0 / dict 1.0.0 / guideline 2024-07
```

---

## 8. Error Handling

### 8.1 Fail-Safe Principle

The engine ALWAYS returns a `RecommendationSet`. It NEVER throws exceptions to the caller for clinical "no data" conditions -- those are represented as empty results with reasons, not exceptions.

### 8.2 Two Error Classes

| Class | Examples | Behavior | Throws? |
|-------|---------|----------|---------|
| **Clinical no-data** | Diagnosis not found, no regimens in SQLite, peds dosing unknown, renal text unstructured | `RecommendationSet` with empty `accepted`, filled `excluded`, `engine_notes` + `traces` with `DecisionCode` | NO |
| **Infrastructure error** | SQLite file missing, JSON diag_index corrupt, drugs_reference path wrong, DB locked | `EngineError` (checked exception) with context | YES |

### 8.3 EngineError

```python
class EngineError(Exception):
    """Infrastructure error. Clinical no-data is NOT EngineError."""
    code: EngineErrorCode
    detail: str
    stage: str | None       # which stage encountered it

class EngineErrorCode(Enum):
    SQLITE_NOT_FOUND = "sqlite_not_found"
    SQLITE_CORRUPT = "sqlite_corrupt"
    DRUG_REFERENCE_NOT_FOUND = "drug_ref_not_found"
    DIAGNOSIS_INDEX_NOT_FOUND = "diag_index_not_found"
    SCORE_PROFILE_NOT_FOUND = "score_profile_not_found"
    RESOURCE_PARSE_ERROR = "resource_parse_error"
    READER_INIT_FAILED = "reader_init_failed"
```

### 8.4 Per-Stage Degraded Mode

| Stage | Degraded mode | Caller sees |
|-------|--------------|-------------|
| DiagnosisMatch | Diagnosis not found | Empty `accepted`, `engine_notes: ["Diagnosis not found"]`, trace: NO_MATCH |
| RegimenLoad | guideline_id found, no regimens in SQLite | Empty `accepted`, `engine_notes: ["No regimens extracted"]` |
| HardSafetyFilter | drug_ref not found | WARNING "DRUG_UNKNOWN", candidate passes |
| DoseCalculation | Weight missing for peds | WARNING "WEIGHT_REQUIRED", DoseDetail.uncalculated |
| DoseAdjustment | Renal text unstructured | WARNING "RENAL_ADJ_UNPARSED", dose unadjusted |
| InteractionCheck | Interactions text missing | Skip, no warning |
| RankRecommendations | No candidates | Empty `accepted`, no ranking |
| Trace | Always runs | RecommendationSet assembled |

### 8.5 EngineNote

```python
@dataclass(frozen=True, slots=True)
class EngineNote:
    code: str                # "NO_DIAGNOSIS_MATCH", "PEDS_DOSING_UNKNOWN", ...
    message: str             # human-readable
    stage: str               # which stage produced the note
    severity: NoteSeverity   # INFO, WARN, ERROR (system error, not clinical)
```

---

## 9. Performance

### 9.1 Targets (v1, 2675 regimens in SQLite)

| Operation | Target | Rationale |
|-----------|--------|-----------|
| `Engine.__init__` (reader load) | <100ms | Lazy init; drugs_reference + diag_index cached |
| `Engine.recommend()` full pipeline | <50ms | 10 stages, ~2675 regimens filtered to ~5-20 candidates |
| SQLite query (load_by_guideline) | <5ms | Indexed by guideline_id, usually 5-20 rows |
| DiagnosisMatch | <1ms | JSON lookup, ~294 entries, in-memory |
| HardSafetyFilter (20 candidates) | <2ms | N x drug_ref lookup, in-memory |
| DoseCalculation | <1ms | Arithmetic, no I/O |
| RankRecommendations | <1ms | Sort <=20 items |
| Trace | <1ms | List concatenation |

### 9.2 Strategies

1. **Reader load at init (lazy-on-first-query):** DrugReferenceReader loads drugs_reference once, caches all DrugInfo in memory. Subsequent `get_drug_info()` = O(1) dict lookup.
2. **SQLite connection reuse:** SQLiteReader opens one connection at init, reuses. No open/close per query.
3. **StageContext preloading:** Context can preload common data (e.g., all DrugInfo for candidates) in one pass.
4. **Pipeline short-circuit:** If DiagnosisMatch returns 0 guideline_ids -> stages 2-9 skipped -> Trace -> empty RecommendationSet.
5. **Cache (v1 stub):** v1: each recommend() runs full pipeline (no cache, fully deterministic). v1.1+: LRU cache on PatientQuery -> RecommendationSet.
6. **No network calls.** Purely local (SQLite + JSON files).

### 9.3 Scalability Projections

| Data volume | Expected recommend() | Limit |
|-------------|---------------------|-------|
| 2,675 regimens (current) | <50ms | SQLite sufficient |
| 10,000 regimens | <100ms | SQLite sufficient |
| 50,000 regimens | <300ms | SQLite + indexes |
| >50,000 regimens | -- | PostgreSQL migration (v1.x) |
| >100,000 regimens | -- | Multiprocessing + cache (v2) |

---

## 10. Testing Strategy

### 10.1 Five Testing Tiers

#### Tier 1: Stage Isolation (unit tests)
Each stage tested independently. Pure function: input -> output.

Coverage per stage:

| Stage | Key tests |
|-------|-----------|
| DiagnosisMatch | Name match, ICD-10 match, no match, multiple guideline_ids |
| RegimenLoad | Verdict filter (STRICT/ALLOW_REVIEW/DEBUG/AUDIT), empty guideline |
| PopulationFilter | Adult/child/neonate, age None, ambiguous |
| TherapyLineSelect | First/alternative/reserve/prophylaxis/empiric, no preference |
| HardSafetyFilter | Allergy (class hierarchy), pregnancy, age, CI, missing drug_ref, missing age |
| DoseCalculation | Adult fixed, peds mg/kg, weight missing, peds dosing unknown, max_daily clamp |
| DoseAdjustment | Renal, hepatic, both, hepatic CI escalation, no GFR, unstructured text |
| InteractionCheck | Minor/moderate/major/contraindicated/unknown, no current_meds, no interaction text |
| RankRecommendations | Sort, therapy_line score, confidence score, recency, safety penalty, interaction penalty, ties, empty |
| Trace | Full trace assembled, all versions populated, runtime, decision_context |

#### Tier 2: Integration (full pipeline)
Tests entire pipeline from PatientQuery to RecommendationSet.

#### Tier 3: Golden Clinical Cases
Doctor-verified input-output pairs. Tests that must NOT change without doctor review.

```python
GOLDEN_CASES = [
    GoldenCase(
        name="CAP adult, outpatient, no risk factors",
        query=PatientQuery(diagnosis="CAP", patient=Patient(age=45)),
        expected_first_drug="amoxicillin",
        expected_first_line="first",
        expected_route="per_os",
        expected_confidence_range=(0.7, 1.0),
    ),
    GoldenCase(
        name="Doxycycline + pregnancy -> excluded",
        query=PatientQuery(diagnosis="Lyme", patient=Patient(age=30, pregnant=True)),
        expected_excluded_drugs=["doxycycline"],
        expected_exclusion_code="PREGNANCY_CI",
    ),
    GoldenCase(
        name="Penicillin allergy -> all beta-lactams excluded",
        query=PatientQuery(diagnosis="pneumonia",
            patient=Patient(age=50, allergies=("penicillins",))),
        expected_excluded_contains=["amoxicillin", "amoxiclav"],
        expected_first_not_in_class="macrolides",
    ),
]
```

Golden cases verify clinical correctness, not just pipeline mechanics. Adding/changing a golden case requires doctor review.

#### Tier 4: Invariant Tests
Tests that verify "constitution" compliance.

```python
def test_excluded_never_resurrected(): ...
def test_deterministic_output(): ...        # same input -> same output (ignoring runtime)
def test_ranking_cannot_exclude(): ...      # ranking adds 0 to excluded
def test_all_dataclasses_frozen(): ...      # all models frozen=True
```

#### Tier 5: Performance Tests
```python
def test_recommend_under_50ms(): ...
```

### 10.2 Coverage Summary

| Tier | Test count (target) | Verifies |
|------|---------------------|----------|
| Stage isolation | ~150-200 | Each stage's logic independently |
| Integration | ~20-30 | Full pipeline, policy configurations |
| Golden cases | ~15-25 (doctor-verified) | Clinical correctness |
| Invariants | ~10-15 | "Constitution" compliance |
| Performance | ~3-5 | Latency targets |
| **Total** | **~200-275** | |

### 10.3 Test Fixtures

- `tests/fixtures/test.sqlite` -- small SQLite with ~50 regimens (predictable data)
- `tests/fixtures/test_drugs_reference.json` -- subset of drugs_reference (5-10 drugs)
- `tests/fixtures/test_diagnosis_index.json` -- 10-20 diagnosis entries
- `tests/fixtures/golden_cases.py` -- doctor-verified input-output pairs

Fixtures are programmatically created (no dependency on production SQLite). Tests do NOT require `C:\clinrec_downloader\metadata.sqlite`.

---

## 11. Extension Points

| Point | Mechanism | Version | What it extends |
|-------|----------|---------|-----------------|
| `DiagnosisProvider` | Protocol | v1 | Diagnosis source (JSON -> SQLite -> API) |
| `PipelineStage` | Protocol | v1 | New stages (pharmacokinetics, resistance) |
| `PluginHook` | Enum + callbacks | v1 | LLM re-ranker, dose validator, hint generator |
| `ValidationPolicy` / `Profiles` | Enum | v1 | Modes (production, research, development, audit) |
| `ScoreProfile` | JSON files | v1 | Clinical scenario ranking (default, ENT, ICU, peds) |
| `ClinicalConstants` | JSON file | v1 | Thresholds, age bands without code |
| `DrugReferenceReader` | Class | v1 | New drug metadata source |
| `EngineCache` | Class | v1 stub | LRU/redis caching (v1.1+) |
| `DecisionReport` | Export | v1 | PDF-ready report for physician |
| `InteractionSeverity` | Enum | v1 | Future severity levels |
| `ClinicalPriority` | Enum | v1 | Drug priority classification |
| `ConfidenceLevel` | Enum (discrete) | v1 | Confidence levels (0/0.25/0.5/0.75/1.0) |
| `EngineNote` | Dataclass | v1 | System notes for UI |

**Plugin behavior constraint:** PluginHook callbacks may reorder, annotate, or suggest. They CANNOT exclude, de-exclude, or modify SafetyFlags.

---

## 12. Constitutional Invariants

These invariants are the "constitution" of the engine. They cannot be changed without a formal RFC.

1. **Once excluded, forever excluded.** `state.excluded` only grows, never shrinks. No stage can move a candidate from `excluded` back to `candidates`.

2. **Deterministic output.** Identical inputs (PatientQuery + SQLite + drugs_reference + diagnosis_index + EngineConfig) -> identical RecommendationSet. No randomness, no timestamps in decision data. (Timestamp is in `runtime`, not in decision data.)

3. **Ranking does not touch safety.** RankRecommendations cannot access `excluded`, cannot add/remove SafetyFlags, cannot change DoseDetail. It reorders and numbers. Period.

4. **All dataclasses frozen.** Mutation only via `dataclasses.replace()`. No in-place mutation anywhere.

5. **Stages do no I/O.** All data access through `StageContext` readers. Pure functions.

6. **StageTrace is immutable and append-only.** Traces are never modified or deleted once created.

7. **Readers return domain objects.** Pipeline never sees SQLite column names or JSON keys.

8. **`guideline_id` is internal.** Public API uses diagnosis names + ICD-10 codes. guideline_id never appears in PatientQuery.

9. **One source of truth per domain.** No duplicate drug safety, no duplicate regimens.

10. **Engine never writes.** Readers are read-only. Engine produces RecommendationSet, nothing else.

11. **Missing data -> WARNING, never silent exclude.** Only positive evidence of contraindication -> exclusion. False exclusion is as dangerous as false inclusion.

12. **DoseAdjustment can escalate.** It can add to `excluded` (hepatic CI). It cannot de-escalate HardSafetyFilter exclusions.

13. **Interaction text structured at preparation time, not parsed at runtime.** drugs_reference gets structured fields. Engine applies rules. If structured field missing -> UNKNOWN severity, not guessed.

14. **Plugin behavior cannot override safety.** PluginHook callbacks may reorder, annotate, or suggest. They cannot exclude, de-exclude, or modify SafetyFlags.

15. **Every decision has DecisionConfidence.** Discrete ConfidenceLevel (0/0.25/0.5/0.75/1.0). Propagated to `recommendation.confidence`. Explicit, not precise.

---

## 13. Future Versions

| Version | Features |
|---------|----------|
| **v1.0** (this spec) | 10 stages, 4 policies, 5 score profiles, DecisionReport, golden cases |
| **v1.1** | Cache (LRU), DrugReferenceReader for SQLite-based drug ref, structured renal/interaction fields |
| **v1.2** | LLM re-ranker plugin (AfterRanking hook), API-based DiagnosisProvider |
| **v2.0** | Multiprocessing for large datasets, PDF export (DecisionReport.to_pdf), Flutter integration |

### Future AI Integration

The `DecisionContext` object (patient + query + metadata + runtime + profile) is the designated integration point for future LLM-based features:
- **AfterRanking plugin:** LLM re-ranks candidates based on clinical nuance not captured in scoring
- **BeforeReturn plugin:** LLM generates clinical reasoning hints for the physician
- **AfterDose plugin:** LLM validates adjusted doses against protocol

AI integration does NOT modify the core pipeline. It hooks into designated `PluginHook` points. The 10-stage deterministic flow remains unchanged.

---
