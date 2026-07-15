# Medical Normalizer v1 — Design Doc

**Date:** 2026-07-09
**Project:** ANTIBIO
**Status:** Approved

---

## Purpose

Transform extracted free-text antibiotic regimens into normalized structured medical objects for search, dose calculator, RAG, API, and doctor application.

## Context

- Extraction pipeline: complete (294 guidelines, 2675 regimens, SQLite consistent)
- Extraction is frozen — no modifications
- Input: regimen objects from `knowledge_base.json` with fields (antibiotic, dose, unit, frequency, route, duration, age_group, regimen_type, source_quote, etc.)
- Output: normalized table `normalized_regimens` in `metadata.sqlite`

## Architecture

**Pattern:** Dataclass pipeline (typed, modular, testable)

Each parser is a pure function:

```
RawRegimen → ParserResult[NormalizedRegimen]
```

### Core types

```python
@dataclass
class NormalizedRegimen:
    # Identity
    source_id: int                    # FK to extraction_raw
    clinrec_id: int
    
    # Drug
    drug_original: str
    drug_normalized: str
    drug_components: list[DrugComponent]
    atc_code: str | None
    
    # Dose
    dose_value: float | None
    dose_unit: str | None            # normalized: mg, g, mcg, ml, IU
    
    # Administration
    route: str                       # normalized: oral, iv, im, topical, ophthalmic, otic, inhalation, unknown | compound: iv|im
    frequency_per_day: float | None
    duration_days_min: float | None
    duration_days_max: float | None
    duration_days_recommended: float | None
    
    # Population
    adult: bool
    child: bool
    pregnancy: bool | None
    renal_adjustment: bool
    
    # Therapy
    therapy_line: str                # first, alternative, reserve, unknown
    
    # Metadata
    confidence: float                # overall (weighted per-field)
    warnings: list[str]

@dataclass
class DrugComponent:
    name: str
    dose_value: float | None
    dose_unit: str | None

@dataclass
class ParserResult:
    regimen: NormalizedRegimen
    field_confidence: dict[str, float]  # per-field confidence
    warnings: list[str]
    errors: list[str]
```

### Parser list (each modifies only own fields)

| Parser | Fields | Dependency |
|--------|--------|------------|
| DrugParser | drug_original, drug_normalized, drug_components, atc_code | dictionary.py |
| DoseParser | dose_value, dose_unit | - |
| RouteParser | route | dictionary.py |
| FrequencyParser | frequency_per_day | - |
| DurationParser | duration_days_min, duration_days_max, duration_days_recommended | - |
| AgeParser | adult, child | - |
| PregnancyParser | pregnancy | - |
| GFRParser | renal_adjustment | - |
| TherapyLineParser | therapy_line | - |

### Pipeline flow

```
RawRegimen
  → DrugParser.parse(regimen) → sets drug fields
  → DoseParser.parse(regimen) → sets dose fields
  → RouteParser.parse(regimen) → sets route
  → FrequencyParser.parse(regimen) → sets frequency_per_day
  → DurationParser.parse(regimen) → sets duration fields
  → AgeParser.parse(regimen) → sets adult/child
  → PregnancyParser.parse(regimen) → sets pregnancy
  → GFRParser.parse(regimen) → sets renal_adjustment
  → TherapyLineParser.parse(regimen) → sets therapy_line
  → ConfidenceCalculator.calculate(field_confidence) → sets confidence
```

### Parsers share no state

Each parser receives the full regimen dict and returns only the fields it owns. The normalizer merges results.

### Confidence

**Overall confidence** = weighted average of required-field confidences.

- Required fields (weight 3): drug_normalized, dose_value, route, frequency_per_day
- Important fields (weight 2): duration_days, adult/child, therapy_line
- Optional fields (weight 1): atc_code, pregnancy, renal_adjustment

Missing optional fields do NOT reduce overall confidence.

Per-field confidence levels:
- 0.99: exact match / direct extraction (e.g., `regimen_type` → `therapy_line`)
- 0.90: synonym match (dictionary lookup)
- 0.80: regex extraction (e.g., dose from text)
- 0.60: inference from surrounding context
- 0.40: uncertain / heuristic
- 0.00: not found / cannot determine

### Error handling

- Permissive: never raise exceptions
- On bad input: log warning, set field confidence=0.0, return partial result
- Pipeline always produces a result, never breaks mid-stream
- Errors collected in ParserResult.errors, warnings in ParserResult.warnings

## Data flow

### Input source

Normalizer reads from `knowledge_base.json` or directly from `metadata.sqlite` (antibiotic_regimens table).

### Output storage

Table: `normalized_regimens` in `metadata.sqlite`

**Schema:**
```sql
CREATE TABLE normalized_regimens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER,
    clinrec_id INTEGER,
    drug_original TEXT,
    drug_normalized TEXT,
    drug_components TEXT,  -- JSON array
    atc_code TEXT,
    dose_value REAL,
    dose_unit TEXT,
    route TEXT,
    frequency_per_day REAL,
    duration_days_min REAL,
    duration_days_max REAL,
    duration_days_recommended REAL,
    adult INTEGER,
    child INTEGER,
    pregnancy INTEGER,
    renal_adjustment INTEGER,
    therapy_line TEXT,
    confidence REAL,
    warnings TEXT,  -- JSON array
    created_at TEXT,
    updated_at TEXT,
    UNIQUE(source_id, clinrec_id) ON CONFLICT DO UPDATE
);
```

**Upsert strategy:** `INSERT ... ON CONFLICT(source_id, clinrec_id) DO UPDATE` — preserves manual edits, review flags, metadata added later.

## Package structure

```
medical_normalizer/
├── __init__.py
├── dictionary.py           # Drug synonyms, route synonyms, unit normalization
├── models.py               # Dataclasses: NormalizedRegimen, DrugComponent, ParserResult
├── drug_parser.py          # DrugParser
├── dose_parser.py          # DoseParser
├── route_parser.py         # RouteParser
├── frequency_parser.py     # FrequencyParser
├── duration_parser.py      # DurationParser
├── population_parser.py    # AgeParser + PregnancyParser + GFRParser
├── therapy_line_parser.py  # TherapyLineParser
├── confidence.py           # ConfidenceCalculator
├── normalizer.py           # Pipeline orchestrator
├── db.py                   # SQLite read/write
├── tests/
│   ├── __init__.py
│   ├── test_dictionary.py
│   ├── test_drug_parser.py
│   ├── test_dose_parser.py
│   ├── test_route_parser.py
│   ├── test_frequency_parser.py
│   ├── test_duration_parser.py
│   ├── test_population_parser.py
│   ├── test_therapy_line_parser.py
│   ├── test_confidence.py
│   └── test_normalizer.py
```

## Testing

- Minimum 150 unit tests
- Each parser has dedicated test file
- Edge cases: empty input, None values, mixed Russian/Latin, ranges, combinations
- No extraction code in tests
- Pure function testing (no DB dependency for parser tests)
