"""MedicalNormalizer -- single entry point for the normalization pipeline.

Responsibilities:
    - Orchestrate the fixed parser pipeline
    - Coordinate ConfidenceCalculator and Validator
    - Capture parser failures without stopping the pipeline
    - Return an immutable NormalizedResult

Rules:
    - NEVER parse text (delegated to parsers)
    - NEVER validate fields (delegated to Validator)
    - NEVER calculate confidence (delegated to ConfidenceCalculator)
    - NEVER modify the raw input
    - Deterministic: same input -> same output, no randomness, no timestamps
      inside normalized data

Pipeline order (fixed):
    DrugParser -> DoseNormalizer -> RouteParser -> FrequencyParser ->
    DurationParser -> PopulationParser (Age, Pregnancy, GFR) ->
    TherapyLineParser -> ConfidenceCalculator -> Validator -> NormalizedResult
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from medical_normalizer.confidence import ConfidenceCalculator, ConfidenceResult
from medical_normalizer.drug_parser import DoseNormalizer, DrugParser
from medical_normalizer.duration_parser import DurationParser
from medical_normalizer.frequency_parser import FrequencyParser
from medical_normalizer.models import NormalizedRegimen
from medical_normalizer.population_parser import AgeParser, GFRParser, PregnancyParser
from medical_normalizer.route_parser import RouteParser
from medical_normalizer.therapy_line_parser import TherapyLineParser
from medical_normalizer.validator import ValidationReport, Validator


# ── Configuration ───────────────────────────────────────────


NORMALIZER_VERSION: str = "1.0.0"


@dataclass(frozen=True)
class NormalizerConfig:
    """Central configuration for the normalizer pipeline."""

    version: str = NORMALIZER_VERSION

    # Fixed parser execution order (canonical names)
    parser_order: tuple[str, ...] = (
        "drug",
        "dose",
        "route",
        "frequency",
        "duration",
        "population",
        "therapy_line",
    )

    # Parsers that should be skipped (by canonical name)
    disabled_parsers: frozenset[str] = frozenset()

    # Post-parser steps (always run after parsers, cannot be disabled)
    post_steps: tuple[str, ...] = ("confidence", "validator")


# Default singleton config
_CONFIG = NormalizerConfig()


# ── Error / result containers ───────────────────────────────


@dataclass(frozen=True)
class ParserError:
    """A captured parser failure."""

    parser: str
    error_type: str
    error_message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "parser": self.parser,
            "error_type": self.error_type,
            "error_message": self.error_message,
        }


@dataclass(frozen=True)
class NormalizedResult:
    """Immutable output of MedicalNormalizer.normalize()."""

    regimen: NormalizedRegimen
    confidence: ConfidenceResult
    validation: ValidationReport
    warnings: tuple[str, ...]
    errors: tuple[ParserError, ...]
    execution_metadata: dict[str, Any]
    normalizer_version: str
    parser_execution_order: tuple[str, ...]
    processing_time: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "regimen": self.regimen.to_dict(),
            "confidence": {
                "overall_confidence": self.confidence.overall_confidence,
                "field_confidence": self.confidence.field_confidence,
                "parser_confidence": self.confidence.parser_confidence,
            },
            "validation": self.validation.to_dict(),
            "warnings": list(self.warnings),
            "errors": [e.to_dict() for e in self.errors],
            "execution_metadata": self.execution_metadata,
            "normalizer_version": self.normalizer_version,
            "parser_execution_order": list(self.parser_execution_order),
            "processing_time": self.processing_time,
        }


@dataclass(frozen=True)
class BatchResult:
    """Immutable output of MedicalNormalizer.normalize_batch()."""

    results: tuple[NormalizedResult, ...]
    processed_count: int
    failed_count: int
    skipped_count: int
    metadata: dict[str, Any]

    @property
    def total_count(self) -> int:
        return self.processed_count + self.skipped_count

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.results if not r.errors)

    def to_dict(self) -> dict[str, Any]:
        return {
            "results": [r.to_dict() for r in self.results],
            "processed_count": self.processed_count,
            "failed_count": self.failed_count,
            "skipped_count": self.skipped_count,
            "metadata": self.metadata,
        }


# ── MedicalNormalizer ───────────────────────────────────────


class MedicalNormalizer:
    """Single entry point for normalizing antibiotic regimens.

    No other part of the project should instantiate parsers directly.
    Use MedicalNormalizer.normalize() for one regimen or
    MedicalNormalizer.normalize_batch() for many.
    """

    config: NormalizerConfig = _CONFIG

    # ── Public API ───────────────────────────────────────

    @classmethod
    def normalize(
        cls,
        raw: dict[str, Any],
        config: NormalizerConfig | None = None,
    ) -> NormalizedResult:
        """Normalize a single raw regimen dict into a NormalizedResult.

        - Deep-copies raw input (immutable input)
        - Runs the fixed parser pipeline
        - Captures parser failures without stopping
        - Runs ConfidenceCalculator then Validator
        - Returns an immutable NormalizedResult
        """
        cfg = config if config is not None else cls.config
        start = time.perf_counter()

        # Immutable input: deep-copy raw so parsers cannot mutate the original
        raw_copy = cls._safe_copy_raw(raw)

        regimen = NormalizedRegimen()
        warnings: list[str] = []
        errors: list[ParserError] = []
        executed: list[str] = []

        # Run parser pipeline
        for parser_name in cfg.parser_order:
            if parser_name in cfg.disabled_parsers:
                warnings.append(f"Parser '{parser_name}' disabled, skipped.")
                continue
            err = cls._run_parser(parser_name, regimen, raw_copy, executed)
            if err is not None:
                errors.append(err)

        # Run post-parser steps (confidence, validator)
        confidence = cls._run_confidence(regimen, errors, warnings, executed)
        validation = cls._run_validator(regimen, errors, warnings, executed)

        # Aggregate validation warnings into result warnings
        for vw in validation.warnings:
            warnings.append(f"[{vw.field}] {vw.message}")

        elapsed = time.perf_counter() - start
        metadata = cls._build_metadata(
            cfg, executed, errors, warnings, elapsed, raw_copy
        )

        return NormalizedResult(
            regimen=regimen,
            confidence=confidence,
            validation=validation,
            warnings=tuple(warnings),
            errors=tuple(errors),
            execution_metadata=metadata,
            normalizer_version=cfg.version,
            parser_execution_order=tuple(executed),
            processing_time=elapsed,
        )

    @classmethod
    def normalize_batch(
        cls,
        raws: list[dict[str, Any]],
        progress_callback: Callable[[int, int, NormalizedResult], None] | None = None,
        skip_indices: set[int] | None = None,
        config: NormalizerConfig | None = None,
    ) -> BatchResult:
        """Normalize a batch of raw regimen dicts.

        - progress_callback(index, total, result) called after each item
        - skip_indices: indices to skip (resume compatibility)
        - Architecture supports future multiprocessing (each item independent,
          config is frozen/shareable). Not implemented now.
        """
        cfg = config if config is not None else cls.config
        skip = skip_indices or set()
        total = len(raws)
        results: list[NormalizedResult] = []
        processed = 0
        failed = 0
        skipped = 0

        for i, raw in enumerate(raws):
            if i in skip:
                skipped += 1
                continue
            result = cls.normalize(raw, config=cfg)
            results.append(result)
            processed += 1
            if result.errors:
                failed += 1
            if progress_callback is not None:
                progress_callback(i, total, result)

        metadata = {
            "total_input": total,
            "processed": processed,
            "failed": failed,
            "skipped": skipped,
            "normalizer_version": cfg.version,
            "parser_order": list(cfg.parser_order),
            "disabled_parsers": sorted(cfg.disabled_parsers),
            "multiprocessing": False,
        }

        return BatchResult(
            results=tuple(results),
            processed_count=processed,
            failed_count=failed,
            skipped_count=skipped,
            metadata=metadata,
        )

    # ── Parser dispatch ──────────────────────────────────

    @classmethod
    def _run_parser(
        cls,
        name: str,
        regimen: NormalizedRegimen,
        raw: dict[str, Any],
        executed: list[str],
    ) -> ParserError | None:
        """Run a single parser by canonical name. Returns error or None."""
        try:
            if name == "drug":
                DrugParser.parse(regimen, raw)
            elif name == "dose":
                DoseNormalizer.parse(regimen, raw)
            elif name == "route":
                RouteParser.parse(regimen, raw)
            elif name == "frequency":
                FrequencyParser.parse(regimen, raw)
            elif name == "duration":
                DurationParser.parse(regimen, raw)
            elif name == "population":
                cls._run_population(regimen, raw, executed)
            elif name == "therapy_line":
                TherapyLineParser.parse(regimen, raw)
            else:
                return ParserError(
                    parser=name,
                    error_type="UnknownParser",
                    error_message=f"No parser registered for '{name}'.",
                )
            executed.append(name)
            return None
        except Exception as exc:
            return ParserError(
                parser=name,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )

    @classmethod
    def _run_population(
        cls,
        regimen: NormalizedRegimen,
        raw: dict[str, Any],
        executed: list[str],
    ) -> None:
        """Run the three population sub-parsers in sequence."""
        for sub_name, parser_cls in (
            ("age", AgeParser),
            ("pregnancy", PregnancyParser),
            ("gfr", GFRParser),
        ):
            try:
                parser_cls.parse(regimen, raw)
                executed.append(f"population.{sub_name}")
            except Exception:
                # Re-raise to be caught by _run_parser's try/except
                # but record which sub-parser failed
                raise

    # ── Post-parser steps ────────────────────────────────

    @classmethod
    def _run_confidence(
        cls,
        regimen: NormalizedRegimen,
        errors: list[ParserError],
        warnings: list[str],
        executed: list[str],
    ) -> ConfidenceResult:
        """Run ConfidenceCalculator on the normalized regimen."""
        try:
            result = ConfidenceCalculator.calculate(regimen)
            executed.append("confidence")
            return result
        except Exception as exc:
            errors.append(ParserError(
                parser="confidence",
                error_type=type(exc).__name__,
                error_message=str(exc),
            ))
            # Return a zero-confidence result as fallback
            from medical_normalizer.confidence import ConfidenceResult as CR
            return CR(
                overall_confidence=0.0,
                field_confidence={},
                parser_confidence=None,
                calculation_metadata={"error": str(exc)},
            )

    @classmethod
    def _run_validator(
        cls,
        regimen: NormalizedRegimen,
        errors: list[ParserError],
        warnings: list[str],
        executed: list[str],
    ) -> ValidationReport:
        """Run Validator on the normalized regimen."""
        try:
            report = Validator.validate(regimen)
            executed.append("validator")
            return report
        except Exception as exc:
            errors.append(ParserError(
                parser="validator",
                error_type=type(exc).__name__,
                error_message=str(exc),
            ))
            # Return a REJECT report as fallback
            from medical_normalizer.validator import (
                ValidationReport as VR,
                Verdict,
            )
            return VR(verdict=Verdict.REJECT, issues=[], metadata={"error": str(exc)})

    # ── Helpers ──────────────────────────────────────────

    @staticmethod
    def _safe_copy_raw(raw: Any) -> dict[str, Any]:
        """Deep-copy raw input. Handle non-dict gracefully."""
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            # Malformed input: treat as empty dict
            return {}
        return copy.deepcopy(raw)

    @classmethod
    def _build_metadata(
        cls,
        cfg: NormalizerConfig,
        executed: list[str],
        errors: list[ParserError],
        warnings: list[str],
        elapsed: float,
        raw_copy: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "parsers_executed": list(executed),
            "parser_count": len(executed),
            "error_count": len(errors),
            "warning_count": len(warnings),
            "disabled_parsers": sorted(cfg.disabled_parsers),
            "input_keys": sorted(raw_copy.keys()) if raw_copy else [],
            "has_input": bool(raw_copy),
        }
