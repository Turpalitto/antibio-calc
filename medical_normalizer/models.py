"""Dataclasses for normalized antibiotic regimens."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class _Unset:
    """Sentinel type for "argument was not supplied".

    Needed because ``0.0`` is a meaningful confidence value and therefore
    cannot double as "use the default" (M18).
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return "<UNSET>"

    def __bool__(self) -> bool:
        return False


UNSET: Any = _Unset()

#: Prefix of a warning marker written by a parser when its input field was
#: absent, empty, or not a string. MedicalNormalizer promotes these markers
#: into ParserError entries in NormalizedResult.errors (H2).
MISSING_FIELD_INPUT: str = "MISSING_FIELD_INPUT"


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
    # RC-030 repair Phase 9 — additive range preservation. dose_value stays the
    # LOWER bound for legacy scalar consumers (byte-identical to prior behavior);
    # dose_max is always separately present; dose_is_range signals scalar
    # consumers are incomplete. These are NOT written to to_dict() (authoritative
    # DB serialization is unchanged) — use to_dict_with_range().
    #
    # dose_value semantics (explicit, see DoseNormalizer.parse):
    #   * plain scalar "500"          -> 500.0  (verbatim)
    #   * range "1,0-2,0"             -> 1.0    (LOWER bound; upper in dose_max)
    #   * combination "875/125"       -> 1000.0 (TOTAL strength; components in
    #                                         drug_components, count in
    #                                         dose_component_count)
    dose_min: float | None = None
    dose_max: float | None = None
    dose_is_range: bool | None = None
    dose_range_raw: str | None = None
    dose_basis_raw: str | None = None
    dose_source_start: int | None = None
    dose_source_end: int | None = None
    dose_range_confidence: float | None = None
    # Number of component doses found in a "A/B(/C)" combination strength.
    # None = not a combination strength; N >= 2 = combination.
    dose_component_count: int | None = None

    # Route
    route: str = "unknown"

    # Frequency
    frequency_per_day: float | None = None
    # True when the source text stated a frequency RANGE ("2-3 раза в сутки").
    # frequency_per_day then holds the LOWER bound (never-overdose default).
    frequency_is_range: bool = False

    # Duration
    duration_days_min: float | None = None
    duration_days_max: float | None = None
    duration_days_recommended: float | None = None

    # Population
    # NOTE: adult defaults to True for backward compatibility, so adult/child
    # alone cannot distinguish "evidence says adult" from "nothing was said".
    # population_stated records whether AgeParser actually found population
    # evidence, so confidence scoring does not treat the default as evidence.
    adult: bool = True
    child: bool = False
    population_stated: bool = False
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

    def to_dict_with_range(self) -> dict[str, Any]:
        """to_dict() plus the full-fidelity fields. Used only by
        experimental range-preserving artifacts, never by the authoritative DB
        writer.

        Round-trips losslessly through from_dict().
        """
        d = self.to_dict()
        d.update({
            "dose_min": self.dose_min, "dose_max": self.dose_max,
            "dose_is_range": self.dose_is_range, "dose_range_raw": self.dose_range_raw,
            "dose_basis_raw": self.dose_basis_raw,
            "dose_source_start": self.dose_source_start, "dose_source_end": self.dose_source_end,
            "dose_range_confidence": self.dose_range_confidence,
            "dose_component_count": self.dose_component_count,
            "frequency_is_range": self.frequency_is_range,
            "population_stated": self.population_stated,
        })
        return d

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
            # RC-030 range fields — previously dropped here, which made
            # to_dict_with_range() -> from_dict() lossy (M2).
            dose_min=d.get("dose_min"),
            dose_max=d.get("dose_max"),
            dose_is_range=d.get("dose_is_range"),
            dose_range_raw=d.get("dose_range_raw"),
            dose_basis_raw=d.get("dose_basis_raw"),
            dose_source_start=d.get("dose_source_start"),
            dose_source_end=d.get("dose_source_end"),
            dose_range_confidence=d.get("dose_range_confidence"),
            dose_component_count=d.get("dose_component_count"),
            route=d.get("route", "unknown"),
            frequency_per_day=d.get("frequency_per_day"),
            frequency_is_range=bool(d.get("frequency_is_range", False)),
            duration_days_min=d.get("duration_days_min"),
            duration_days_max=d.get("duration_days_max"),
            duration_days_recommended=d.get("duration_days_recommended"),
            adult=d.get("adult", True),
            child=d.get("child", False),
            population_stated=bool(d.get("population_stated", False)),
            pregnancy=d.get("pregnancy"),
            renal_adjustment=d.get("renal_adjustment", False),
            therapy_line=d.get("therapy_line", "unknown"),
            confidence=d.get("confidence", 0.0),
            warnings=d.get("warnings", []),
        )


@dataclass
class ConfidenceScore:
    """Per-field confidence for a parsed regimen.

    ``overall`` uses an UNSET sentinel as its default so an explicitly
    supplied ``overall=0.0`` is distinguishable from "not supplied" (M18).
    """

    overall: Any = UNSET
    fields: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Captured at construction time: after __post_init__ the sentinel has
        # already been replaced by a number, so the flag cannot be re-derived
        # from `self.overall` afterwards.
        self._explicit_overall = not isinstance(self.overall, _Unset)
        if not self._explicit_overall:
            if self.fields:
                self.overall = sum(self.fields.values()) / len(self.fields)
            else:
                self.overall = 0.0
        elif self.overall is None:
            self.overall = 0.0

    @property
    def overall_was_set(self) -> bool:
        """True when the caller supplied an explicit ``overall`` at construction.

        Reflects construction-time state; a later attribute assignment does
        not change it.
        """
        return bool(getattr(self, "_explicit_overall", False))


@dataclass
class ParserResult:
    """Result of parsing one regimen through the normalizer pipeline."""

    regimen: NormalizedRegimen = field(default_factory=NormalizedRegimen)
    field_confidence: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def confidence(self) -> float:
        """Weighted overall confidence — same calculation as
        ConfidenceCalculator.calculate_overall (M5).

        The import is local to avoid a module-level cycle
        (confidence.py imports models.py).
        """
        from medical_normalizer.confidence import ConfidenceCalculator

        return ConfidenceCalculator.calculate_overall(self.field_confidence)
