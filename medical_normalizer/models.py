"""Dataclasses for normalized antibiotic regimens."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DrugComponent:
    """A single active component in a combination drug."""

    name: str
    dose_value: float | None = None
    dose_unit: str | None = None

    def __bool__(self) -> bool:
        return bool(self.name)


@dataclass
class NormalizedRegimen:
    """Normalized, structured representation of one antibiotic regimen."""

    source_id: int | None = None
    clinrec_id: int | None = None

    # Drug
    drug_original: str = ""
    drug_normalized: str = ""
    drug_components: list[DrugComponent] = field(default_factory=list)
    atc_code: str | None = None

    # Dose
    dose_value: float | None = None
    dose_unit: str | None = None

    # Route
    route: str = "unknown"

    # Frequency
    frequency_per_day: float | None = None

    # Duration
    duration_days_min: float | None = None
    duration_days_max: float | None = None
    duration_days_recommended: float | None = None

    # Population
    adult: bool = True
    child: bool = False
    pregnancy: bool | None = None
    renal_adjustment: bool = False

    # Therapy
    therapy_line: str = "unknown"

    # Metadata
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "clinrec_id": self.clinrec_id,
            "drug_original": self.drug_original,
            "drug_normalized": self.drug_normalized,
            "drug_components": [c.__dict__ for c in self.drug_components],
            "atc_code": self.atc_code,
            "dose_value": self.dose_value,
            "dose_unit": self.dose_unit,
            "route": self.route,
            "frequency_per_day": self.frequency_per_day,
            "duration_days_min": self.duration_days_min,
            "duration_days_max": self.duration_days_max,
            "duration_days_recommended": self.duration_days_recommended,
            "adult": self.adult,
            "child": self.child,
            "pregnancy": self.pregnancy,
            "renal_adjustment": self.renal_adjustment,
            "therapy_line": self.therapy_line,
            "confidence": self.confidence,
            "warnings": self.warnings,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> NormalizedRegimen:
        components = [
            DrugComponent(**c) if isinstance(c, dict) else c
            for c in d.get("drug_components", [])
        ]
        return cls(
            source_id=d.get("source_id"),
            clinrec_id=d.get("clinrec_id"),
            drug_original=d.get("drug_original", ""),
            drug_normalized=d.get("drug_normalized", ""),
            drug_components=components,
            atc_code=d.get("atc_code"),
            dose_value=d.get("dose_value"),
            dose_unit=d.get("dose_unit"),
            route=d.get("route", "unknown"),
            frequency_per_day=d.get("frequency_per_day"),
            duration_days_min=d.get("duration_days_min"),
            duration_days_max=d.get("duration_days_max"),
            duration_days_recommended=d.get("duration_days_recommended"),
            adult=d.get("adult", True),
            child=d.get("child", False),
            pregnancy=d.get("pregnancy"),
            renal_adjustment=d.get("renal_adjustment", False),
            therapy_line=d.get("therapy_line", "unknown"),
            confidence=d.get("confidence", 0.0),
            warnings=d.get("warnings", []),
        )


@dataclass
class ConfidenceScore:
    """Per-field confidence for a parsed regimen."""

    overall: float = 0.0
    fields: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.overall == 0.0 and self.fields:
            self.overall = sum(self.fields.values()) / len(self.fields)


@dataclass
class ParserResult:
    """Result of parsing one regimen through the normalizer pipeline."""

    regimen: NormalizedRegimen = field(default_factory=NormalizedRegimen)
    field_confidence: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def confidence(self) -> float:
        return ConfidenceScore(fields=self.field_confidence).overall
