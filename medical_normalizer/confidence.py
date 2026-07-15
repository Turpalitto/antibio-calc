"""ConfidenceCalculator — compute weighted overall confidence per regimen.

Responsibilities:
    - Calculate per-field confidence from NormalizedRegimen structure
    - Accept parser-provided confidence via ParserResult and/or ConfidenceScore
    - Compute weighted overall confidence
    - Return calculation metadata for debugging

Rules:
    - Missing OPTIONAL (weight 1) fields do NOT reduce confidence
    - Required (weight 3) and Important (weight 2) fields ARE penalized if missing
    - Not-applicable optional fields (confidence 0.0) are ignored
    - Confidence is always between 0.0 and 1.0
    - NEVER modifies regimen data
    - NEVER performs validation or text parsing
    - NEVER inspects raw extraction text or source_quote
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from medical_normalizer.dictionary import DRUG_SYNONYMS
from medical_normalizer.models import ConfidenceScore, NormalizedRegimen, ParserResult


# ── Configuration (no magic constants scattered in code) ─────


@dataclass(frozen=True)
class ConfidenceConfig:
    """Central configuration for confidence calculation."""

    # Weight tiers
    weight_required: int = 3
    weight_important: int = 2
    weight_optional: int = 1

    # Confidence tiers
    exact_match: float = 0.99        # dictionary-verified or explicit field
    inferred: float = 0.90           # inferred from structured data
    inferred_partial: float = 0.85   # partial inference (e.g. duration min only)
    inferred_low: float = 0.80       # low-confidence boolean inference
    uncertain: float = 0.60          # present but unverified
    not_found: float = 0.0           # missing / not applicable

    # Rounding precision for aggregated scores
    round_digits: int = 4

    # Field categories — names match NormalizedRegimen / spec
    required_fields: tuple[str, ...] = ("drug", "dose", "route", "frequency")
    important_fields: tuple[str, ...] = ("duration", "population", "therapy_line")
    optional_fields: tuple[str, ...] = ("atc_code", "pregnancy", "renal_adjustment")

    @property
    def all_fields(self) -> tuple[str, ...]:
        return self.required_fields + self.important_fields + self.optional_fields

    @property
    def weights(self) -> dict[str, int]:
        w: dict[str, int] = {}
        for f in self.required_fields:
            w[f] = self.weight_required
        for f in self.important_fields:
            w[f] = self.weight_important
        for f in self.optional_fields:
            w[f] = self.weight_optional
        return w


# Default singleton config
_CONFIG = ConfidenceConfig()


@dataclass
class ConfidenceResult:
    """Output of ConfidenceCalculator.calculate()."""

    overall_confidence: float
    field_confidence: dict[str, float]
    parser_confidence: float | None
    calculation_metadata: dict[str, Any] = field(default_factory=dict)


class ConfidenceCalculator:
    """Compute per-field and weighted overall confidence.

    Pure: never modifies regimen, never parses text, never validates.
    No parser should know how confidence is calculated.
    """

    config: ConfidenceConfig = _CONFIG

    # ── Public API ───────────────────────────────────────

    @classmethod
    def calculate(
        cls,
        regimen: NormalizedRegimen,
        parser_result: ParserResult | None = None,
        confidence_score: ConfidenceScore | None = None,
    ) -> ConfidenceResult:
        """Full confidence calculation.

        Returns ConfidenceResult with overall, per-field, parser, metadata.
        """
        field_conf = cls.calculate_field_confidence(
            regimen, parser_result, confidence_score
        )
        overall = cls.calculate_overall(field_conf)
        parser_conf = cls.calculate_parser_score(parser_result, confidence_score)
        metadata = cls._build_metadata(field_conf)

        return ConfidenceResult(
            overall_confidence=overall,
            field_confidence=field_conf,
            parser_confidence=parser_conf,
            calculation_metadata=metadata,
        )

    @classmethod
    def calculate_field(
        cls,
        field_name: str,
        regimen: NormalizedRegimen,
        parser_result: ParserResult | None = None,
        confidence_score: ConfidenceScore | None = None,
    ) -> float:
        """Calculate confidence for a single field.

        Priority: parser_result.field_confidence > confidence_score.fields
        > inferred from regimen structure.
        """
        cfg = cls.config

        if parser_result and field_name in parser_result.field_confidence:
            val = parser_result.field_confidence[field_name]
        elif confidence_score and field_name in confidence_score.fields:
            val = confidence_score.fields[field_name]
        else:
            infer_func = cls._infer_funcs().get(field_name)
            if infer_func is None:
                return cfg.not_found
            val = infer_func(regimen)

        return cls._clamp(val)

    @classmethod
    def calculate_overall(
        cls,
        field_confidence: dict[str, float],
    ) -> float:
        """Compute weighted average from field confidences.

        Optional fields with 0.0 confidence (missing / not applicable) are
        excluded so they never reduce the overall score.
        """
        cfg = cls.config
        total_weight = 0
        weighted_sum = 0.0

        for fname, conf in field_confidence.items():
            weight = cfg.weights.get(fname, 0)
            if weight == 0:
                continue
            # Missing optional field → no penalty
            if weight == cfg.weight_optional and conf <= cfg.not_found:
                continue
            total_weight += weight
            weighted_sum += conf * weight

        overall = weighted_sum / total_weight if total_weight > 0 else 0.0
        return round(cls._clamp(overall), cfg.round_digits)

    @classmethod
    def calculate_parser_score(
        cls,
        parser_result: ParserResult | None = None,
        confidence_score: ConfidenceScore | None = None,
    ) -> float | None:
        """Parser-level confidence.

        Priority: explicit ConfidenceScore.overall > average of
        parser_result.field_confidence > average of confidence_score.fields.
        Returns None if no parser data is available.
        """
        cfg = cls.config

        has_score = (
            confidence_score is not None
            and (bool(confidence_score.fields) or confidence_score.overall != 0.0)
        )
        if has_score:
            return round(cls._clamp(confidence_score.overall), cfg.round_digits)

        if parser_result is not None and parser_result.field_confidence:
            values = list(parser_result.field_confidence.values())
            return round(sum(values) / len(values), cfg.round_digits)

        return None

    # ── Internal helpers ─────────────────────────────────

    @classmethod
    def calculate_field_confidence(
        cls,
        regimen: NormalizedRegimen,
        parser_result: ParserResult | None = None,
        confidence_score: ConfidenceScore | None = None,
    ) -> dict[str, float]:
        """Calculate confidence for ALL configured fields."""
        result: dict[str, float] = {}
        for fname in cls.config.all_fields:
            result[fname] = cls.calculate_field(
                fname, regimen, parser_result, confidence_score
            )
        return result

    @classmethod
    def _build_metadata(
        cls,
        field_conf: dict[str, float],
    ) -> dict[str, Any]:
        """Build debug metadata showing which fields were included/excluded."""
        cfg = cls.config
        included: list[str] = []
        excluded: list[str] = []

        for fname, conf in field_conf.items():
            weight = cfg.weights.get(fname, 0)
            if weight == cfg.weight_optional and conf <= cfg.not_found:
                excluded.append(fname)
            else:
                included.append(fname)

        return {
            "included_fields": included,
            "excluded_fields": excluded,
            "weights": cfg.weights,
            "total_weight": sum(cfg.weights[f] for f in included),
            "field_count": len(field_conf),
            "included_count": len(included),
            "excluded_count": len(excluded),
        }

    @staticmethod
    def _clamp(value: float) -> float:
        """Clamp a confidence value to [0.0, 1.0]."""
        if value < 0.0:
            return 0.0
        if value > 1.0:
            return 1.0
        return float(value)

    # ── Per-field inference functions ────────────────────

    _known_drugs_cache: set[str] | None = None

    @classmethod
    def _get_known_drugs(cls) -> set[str]:
        if cls._known_drugs_cache is None:
            cache: set[str] = set()
            for k, v in DRUG_SYNONYMS.items():
                cache.add(k.lower())
                cache.add(v.lower())
            cls._known_drugs_cache = cache
        return cls._known_drugs_cache

    @classmethod
    def _infer_drug(cls, r: NormalizedRegimen) -> float:
        cfg = cls.config
        if not r.drug_normalized:
            return cfg.not_found
        if r.drug_normalized.lower() in cls._get_known_drugs():
            return cfg.exact_match
        return cfg.uncertain

    @classmethod
    def _infer_dose(cls, r: NormalizedRegimen) -> float:
        cfg = cls.config
        if r.dose_value is not None and r.dose_value > 0:
            return cfg.inferred
        return cfg.not_found

    @classmethod
    def _infer_route(cls, r: NormalizedRegimen) -> float:
        cfg = cls.config
        if r.route and r.route != "unknown":
            return cfg.inferred
        return cfg.not_found

    @classmethod
    def _infer_frequency(cls, r: NormalizedRegimen) -> float:
        cfg = cls.config
        if r.frequency_per_day is not None and r.frequency_per_day > 0:
            return cfg.inferred
        return cfg.not_found

    @classmethod
    def _infer_duration(cls, r: NormalizedRegimen) -> float:
        cfg = cls.config
        if r.duration_days_min is not None:
            return cfg.inferred_partial
        return cfg.not_found

    @classmethod
    def _infer_population(cls, r: NormalizedRegimen) -> float:
        cfg = cls.config
        if r.adult or r.child:
            return cfg.inferred
        return cfg.not_found

    @classmethod
    def _infer_therapy_line(cls, r: NormalizedRegimen) -> float:
        cfg = cls.config
        if r.therapy_line and r.therapy_line != "unknown":
            return cfg.exact_match
        return cfg.not_found

    @classmethod
    def _infer_atc_code(cls, r: NormalizedRegimen) -> float:
        cfg = cls.config
        if r.atc_code:
            return cfg.exact_match
        return cfg.not_found

    @classmethod
    def _infer_pregnancy(cls, r: NormalizedRegimen) -> float:
        cfg = cls.config
        if r.pregnancy is not None:
            return cfg.inferred_low
        return cfg.not_found

    @classmethod
    def _infer_renal(cls, r: NormalizedRegimen) -> float:
        cfg = cls.config
        if r.renal_adjustment:
            return cfg.inferred_low
        return cfg.not_found

    @classmethod
    def _infer_funcs(cls) -> dict[str, Callable[[NormalizedRegimen], float]]:
        return {
            "drug": cls._infer_drug,
            "dose": cls._infer_dose,
            "route": cls._infer_route,
            "frequency": cls._infer_frequency,
            "duration": cls._infer_duration,
            "population": cls._infer_population,
            "therapy_line": cls._infer_therapy_line,
            "atc_code": cls._infer_atc_code,
            "pregnancy": cls._infer_pregnancy,
            "renal_adjustment": cls._infer_renal,
        }
