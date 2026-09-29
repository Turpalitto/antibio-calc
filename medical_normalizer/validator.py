"""Validator — validate a normalized regimen against business rules.

Responsibilities:
    - Run AFTER all parsers and AFTER ConfidenceCalculator
    - Validate only the structured NormalizedRegimen object
    - Produce a ValidationReport with issues + overall verdict

Rules:
    - NEVER parse raw text
    - NEVER normalize data
    - NEVER modify regimen, confidence, or parser output
    - Validation is additive: collects issues, does not short-circuit

Verdicts:
    PASS    — no ERROR, no REVIEW issues (warnings only or clean)
    REVIEW  — at least one REVIEW issue, no ERROR
    REJECT  — at least one ERROR issue
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from medical_normalizer.dictionary import DRUG_SYNONYMS, ROUTE_SYNONYMS
from medical_normalizer.models import NormalizedRegimen


# ── Configuration (no magic constants scattered in code) ─────


@dataclass(frozen=True)
class ValidatorConfig:
    """Central configuration for regimen validation."""

    # Required fields (must be present and non-empty)
    required_fields: tuple[str, ...] = ("drug", "dose", "route", "frequency")

    # Controlled vocabularies
    valid_routes: tuple[str, ...] = (
        "oral", "iv", "im", "topical", "ophthalmic", "inhalation", "otic",
    )
    valid_therapy_lines: tuple[str, ...] = (
        "first", "alternative", "reserve", "unknown",
    )
    # Canonical units produced by UnitNormalizer from
    # medical_dictionary/unit_dictionary.json (L6: this tuple must stay in
    # sync with that file — every canonical value in the dictionary is
    # listed here, plus the additional clinical units below).
    valid_units: tuple[str, ...] = (
        "g", "mg", "mcg", "ml", "mg/kg", "mg/kg/day", "IU", "thousand_IU",
        # additional clinically legitimate units that the dictionary does not
        # canonicalize (BSA dosing, weight, activity, counts)
        "mg/m2", "mcg/kg", "kg", "mmol", "tablet", "vial", "ng",
    )
    # Unmapped-but-legitimate raw unit forms. UnitNormalizer returns the
    # cleaned (lowercased) input when it has no mapping, so a Russian BSA
    # dose arrives as "мг/м2". Accepting these exact forms keeps a legitimate
    # dose out of DOSE_UNIT_UNKNOWN without rewriting anything here — the
    # Validator never normalizes data, it only recognises the vocabulary.
    valid_unit_aliases: tuple[str, ...] = (
        "мг/м2", "мг/м²", "мг/кг/сут", "мг/кг/сутки", "кг",
        "мкг/кг", "мг/кг/сут.",
    )

    # Numeric bounds — applied to dose_value AND to dose_min / dose_max (C4)
    dose_min: float = 0.0
    dose_max: float = 1_000_000.0
    frequency_min: float = 0.0
    frequency_max: float = 24.0
    duration_min: float = 0.0
    duration_max: float = 365.0

    # ATC format: letter + 2 digits + 2 letters + 2 digits (e.g. J01DD04)
    atc_pattern: str = r"^[A-Z]\d{2}[A-Z]{2}\d{2}$"

    # Component dose consistency tolerance (ratio)
    component_dose_tolerance: float = 0.0


# Default singleton config
_CONFIG = ValidatorConfig()


# ── Severity / verdict enums ────────────────────────────────


class Severity(str, Enum):
    """Issue severity levels."""

    WARNING = "warning"
    REVIEW = "review"
    ERROR = "error"


class Verdict(str, Enum):
    """Overall validation verdict."""

    PASS = "PASS"
    REVIEW = "REVIEW"
    REJECT = "REJECT"


# ── Data containers ─────────────────────────────────────────


@dataclass
class ValidationIssue:
    """A single validation finding."""

    code: str
    severity: Severity
    message: str
    field: str
    suggested_fix: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "field": self.field,
            "suggested_fix": self.suggested_fix,
        }


@dataclass
class ValidationReport:
    """Full validation result: verdict + issues + metadata."""

    verdict: Verdict
    issues: list[ValidationIssue] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.verdict == Verdict.PASS

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]

    @property
    def reviews(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.REVIEW]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "issues": [i.to_dict() for i in self.issues],
            "metadata": self.metadata,
        }


# ── Validator ───────────────────────────────────────────────


class Validator:
    """Validate a NormalizedRegimen against business rules.

    Pure: never modifies regimen, confidence, or parser output.
    Additive: collects all issues, never short-circuits.
    """

    config: ValidatorConfig = _CONFIG

    # ── Public API ───────────────────────────────────────

    @classmethod
    def validate(cls, regimen: NormalizedRegimen) -> ValidationReport:
        """Run all checks and return a ValidationReport."""
        issues: list[ValidationIssue] = []
        for check in cls._checks():
            issues.extend(check(regimen))

        verdict = cls._derive_verdict(issues)
        metadata = cls._build_metadata(regimen, issues, verdict)
        return ValidationReport(verdict=verdict, issues=issues, metadata=metadata)

    @classmethod
    def validate_field(
        cls,
        field_name: str,
        regimen: NormalizedRegimen,
    ) -> list[ValidationIssue]:
        """Run only the checks for a single field."""
        out: list[ValidationIssue] = []
        for check in cls._checks():
            for issue in check(regimen):
                if issue.field == field_name:
                    out.append(issue)
        return out

    @classmethod
    def is_valid(cls, regimen: NormalizedRegimen) -> bool:
        """True if verdict is PASS (no ERROR, no REVIEW)."""
        return cls.validate(regimen).verdict == Verdict.PASS

    # ── Verdict derivation ───────────────────────────────

    @staticmethod
    def _derive_verdict(issues: list[ValidationIssue]) -> Verdict:
        has_error = any(i.severity == Severity.ERROR for i in issues)
        has_review = any(i.severity == Severity.REVIEW for i in issues)
        if has_error:
            return Verdict.REJECT
        if has_review:
            return Verdict.REVIEW
        return Verdict.PASS

    # ── Metadata ─────────────────────────────────────────

    @classmethod
    def _build_metadata(
        cls,
        regimen: NormalizedRegimen,
        issues: list[ValidationIssue],
        verdict: Verdict,
    ) -> dict[str, Any]:
        errors = [i for i in issues if i.severity == Severity.ERROR]
        reviews = [i for i in issues if i.severity == Severity.REVIEW]
        warnings = [i for i in issues if i.severity == Severity.WARNING]
        return {
            "verdict": verdict.value,
            "issue_count": len(issues),
            "error_count": len(errors),
            "review_count": len(reviews),
            "warning_count": len(warnings),
            "checks_run": len(cls._checks()),
            "drug_normalized": regimen.drug_normalized,
            "has_components": bool(regimen.drug_components),
        }

    # ── Check registry ───────────────────────────────────

    _checks_cache: list[Callable[[NormalizedRegimen], list[ValidationIssue]]] | None = None

    @classmethod
    def _checks(cls) -> list[Callable[[NormalizedRegimen], list[ValidationIssue]]]:
        """The check registry. Built once and cached (L7).

        The registry is a fixed list of bound classmethods, so rebuilding it
        on every validate() call was pure overhead; tests that swap
        Validator.config still work because the checks read cls.config at
        call time.
        """
        if cls._checks_cache is None:
            cls._checks_cache = [
                cls.check_required_fields,
                cls.check_drug_exists,
                cls.check_dose_positive,
                cls.check_frequency_valid,
                cls.check_duration_valid,
                cls.check_route_valid,
                cls.check_component_consistency,
                cls.check_atc_format,
                cls.check_pregnancy_consistency,
                cls.check_renal_adjustment_consistency,
            ]
        return cls._checks_cache

    # ── Individual checks ────────────────────────────────

    @classmethod
    def check_required_fields(
        cls, regimen: NormalizedRegimen
    ) -> list[ValidationIssue]:
        """Required fields must be present and non-empty."""
        cfg = cls.config
        issues: list[ValidationIssue] = []
        for fname in cfg.required_fields:
            if cls._is_missing(fname, regimen):
                issues.append(ValidationIssue(
                    code="REQUIRED_MISSING",
                    severity=Severity.ERROR,
                    message=f"Required field '{fname}' is missing or empty.",
                    field=fname,
                    suggested_fix=cls._suggest_required(fname, regimen),
                ))
        return issues

    @classmethod
    def check_drug_exists(
        cls, regimen: NormalizedRegimen
    ) -> list[ValidationIssue]:
        """drug_normalized should be a known drug (in DRUG_SYNONYMS values)."""
        if not regimen.drug_normalized:
            return []
        known = cls._known_drugs()
        if regimen.drug_normalized.lower() not in known:
            return [ValidationIssue(
                code="DRUG_UNKNOWN",
                severity=Severity.REVIEW,
                message=(
                    f"Drug '{regimen.drug_normalized}' is not in the known "
                    f"drug dictionary."
                ),
                field="drug",
                suggested_fix=None,
            )]
        return []

    @classmethod
    def check_dose_positive(
        cls, regimen: NormalizedRegimen
    ) -> list[ValidationIssue]:
        """All dose checks: value, range bounds and unit.

        Additive by contract (H6): the three early `return`s previously made
        the function short-circuit, so DOSE_UNIT_UNKNOWN was silently
        suppressed whenever a numeric check fired.

        H3: an unknown unit is a REVIEW, so it must no longer hide a
        DOSE_NOT_POSITIVE ERROR. When the unit is not in the controlled
        vocabulary the dose NUMBERS cannot be judged against unit-specific
        limits, so the numeric finding is downgraded to WARNING — the
        pipeline still surfaces the problem and the verdict still moves away
        from PASS.
        """
        cfg = cls.config
        issues: list[ValidationIssue] = []

        unit_known = cls._unit_in_vocabulary(regimen.dose_unit)
        numeric_trustworthy = unit_known

        for attr in ("dose_value", "dose_min", "dose_max"):
            val = getattr(regimen, attr, None)
            if val is None:
                continue
            field_label = attr if attr != "dose_value" else "dose"
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                issues.append(ValidationIssue(
                    code="DOSE_NOT_NUMERIC",
                    severity=Severity.ERROR,
                    message=f"{field_label} value {val!r} is not a number.",
                    field="dose",
                    suggested_fix=None,
                ))
                continue
            if not math.isfinite(float(val)):
                # C1 defence-in-depth: every comparison against NaN is False,
                # so an unguarded NaN produced NO issue at all and a clean
                # PASS with dose=NULL. DoseNormalizer already refuses
                # non-finite input at parse time.
                issues.append(ValidationIssue(
                    code="DOSE_NOT_FINITE",
                    severity=Severity.ERROR,
                    message=f"{field_label} value {val!r} is not finite.",
                    field="dose",
                    suggested_fix=None,
                ))
                continue
            if val <= cfg.dose_min:
                issues.append(ValidationIssue(
                    code="DOSE_NOT_POSITIVE",
                    severity=Severity.ERROR if numeric_trustworthy else Severity.WARNING,
                    message=f"Dose value {field_label}={val} must be > 0.",
                    field="dose",
                    suggested_fix=None,
                ))
                continue
            if val > cfg.dose_max:
                issues.append(ValidationIssue(
                    code="DOSE_OUT_OF_RANGE",
                    severity=Severity.ERROR if numeric_trustworthy else Severity.WARNING,
                    message=(
                        f"Dose value {field_label}={val} exceeds maximum "
                        f"{cfg.dose_max}."
                    ),
                    field="dose",
                    suggested_fix=None,
                ))

        # C4: dose_max >= dose_min when both are present.
        mn = regimen.dose_min
        mx = regimen.dose_max
        if (
            isinstance(mn, (int, float))
            and isinstance(mx, (int, float))
            and math.isfinite(float(mn))
            and math.isfinite(float(mx))
            and mn > mx
        ):
            issues.append(ValidationIssue(
                code="DOSE_RANGE_INVERTED",
                severity=Severity.ERROR,
                message=(
                    f"dose_min {mn} is greater than dose_max {mx}."
                ),
                field="dose",
                suggested_fix=None,
            ))

        if regimen.dose_unit and not unit_known:
            issues.append(ValidationIssue(
                code="DOSE_UNIT_UNKNOWN",
                severity=Severity.REVIEW,
                message=(
                    f"Dose unit '{regimen.dose_unit}' is not in the controlled "
                    f"vocabulary."
                ),
                field="dose",
                suggested_fix=None,
            ))

        return issues

    @classmethod
    def _unit_in_vocabulary(cls, unit: str | None) -> bool:
        """True when the unit is recognised (empty/None counts as known)."""
        if not unit:
            return True
        cfg = cls.config
        if unit in cfg.valid_units:
            return True
        return unit.strip().lower() in cfg.valid_unit_aliases

    @classmethod
    def check_frequency_valid(
        cls, regimen: NormalizedRegimen
    ) -> list[ValidationIssue]:
        """frequency_per_day must be within (0, 24]."""
        cfg = cls.config
        if regimen.frequency_per_day is None:
            return []
        f = regimen.frequency_per_day
        if f <= cfg.frequency_min:
            return [ValidationIssue(
                code="FREQUENCY_NOT_POSITIVE",
                severity=Severity.ERROR,
                message=f"Frequency {f} must be > 0 per day.",
                field="frequency",
                suggested_fix=None,
            )]
        if f > cfg.frequency_max:
            return [ValidationIssue(
                code="FREQUENCY_OUT_OF_RANGE",
                severity=Severity.ERROR,
                message=f"Frequency {f} exceeds maximum {cfg.frequency_max}.",
                field="frequency",
                suggested_fix=None,
            )]
        return []

    @classmethod
    def check_duration_valid(
        cls, regimen: NormalizedRegimen
    ) -> list[ValidationIssue]:
        """Duration min/max/recommended must be within [0, 365]."""
        cfg = cls.config
        issues: list[ValidationIssue] = []
        for attr in ("duration_days_min", "duration_days_max", "duration_days_recommended"):
            val = getattr(regimen, attr, None)
            if val is None:
                continue
            if val < cfg.duration_min:
                issues.append(ValidationIssue(
                    code="DURATION_NEGATIVE",
                    severity=Severity.ERROR,
                    message=f"{attr} {val} must be >= 0.",
                    field="duration",
                    suggested_fix=None,
                ))
                continue
            if val > cfg.duration_max:
                issues.append(ValidationIssue(
                    code="DURATION_OUT_OF_RANGE",
                    severity=Severity.ERROR,
                    message=f"{attr} {val} exceeds maximum {cfg.duration_max}.",
                    field="duration",
                    suggested_fix=None,
                ))
        # min <= max when both present
        mn = regimen.duration_days_min
        mx = regimen.duration_days_max
        if mn is not None and mx is not None and mn > mx:
            issues.append(ValidationIssue(
                code="DURATION_MIN_GT_MAX",
                severity=Severity.ERROR,
                message=(
                    f"duration_days_min {mn} is greater than "
                    f"duration_days_max {mx}."
                ),
                field="duration",
                suggested_fix=None,
            ))
        return issues

    @classmethod
    def check_route_valid(
        cls, regimen: NormalizedRegimen
    ) -> list[ValidationIssue]:
        """route must be in controlled vocabulary or 'unknown'."""
        cfg = cls.config
        if not regimen.route:
            return []
        if regimen.route == "unknown":
            return [ValidationIssue(
                code="ROUTE_UNKNOWN",
                severity=Severity.REVIEW,
                message="Route is 'unknown' — cannot verify administration path.",
                field="route",
                suggested_fix=None,
            )]
        # compound routes: "iv|im"
        parts = regimen.route.split("|")
        for part in parts:
            if part not in cfg.valid_routes:
                return [ValidationIssue(
                    code="ROUTE_INVALID",
                    severity=Severity.ERROR,
                    message=(
                        f"Route '{part}' is not in the controlled vocabulary."
                    ),
                    field="route",
                    suggested_fix=None,
                )]
        return []

    @classmethod
    def check_component_consistency(
        cls, regimen: NormalizedRegimen
    ) -> list[ValidationIssue]:
        """Combination drugs: drug_components must align with drug_normalized."""
        issues: list[ValidationIssue] = []
        drug = regimen.drug_normalized or ""
        has_components = bool(regimen.drug_components)
        # M17: "/" is a component separator as well as "+" — Russian
        # combination strengths are written both ways.
        is_combination = "+" in drug or "/" in drug

        if is_combination and not has_components:
            issues.append(ValidationIssue(
                code="COMBINATION_MISSING_COMPONENTS",
                severity=Severity.REVIEW,
                message=(
                    f"Drug '{drug}' is a combination but drug_components is empty."
                ),
                field="drug_components",
                suggested_fix=None,
            ))
        if has_components and not is_combination:
            issues.append(ValidationIssue(
                code="COMPONENTS_WITHOUT_COMBINATION",
                severity=Severity.REVIEW,
                message=(
                    f"drug_components populated but drug '{drug}' is not a "
                    f"combination."
                ),
                field="drug_components",
                suggested_fix=None,
            ))
        # Each component must have a name
        for i, comp in enumerate(regimen.drug_components):
            if not comp.name:
                issues.append(ValidationIssue(
                    code="COMPONENT_NAME_MISSING",
                    severity=Severity.ERROR,
                    message=f"Component at index {i} has no name.",
                    field="drug_components",
                    suggested_fix=None,
                ))
        return issues

    @classmethod
    def check_atc_format(
        cls, regimen: NormalizedRegimen
    ) -> list[ValidationIssue]:
        """atc_code, if present, must match the ATC format pattern."""
        cfg = cls.config
        if not regimen.atc_code:
            return []
        # L12: re.match + "$" accepts a trailing newline ("J01DD04\n"
        # validated). fullmatch requires the whole string to be consumed.
        if not re.fullmatch(cfg.atc_pattern, regimen.atc_code):
            return [ValidationIssue(
                code="ATC_FORMAT_INVALID",
                # L11: WARNING let a garbage ATC code still yield PASS. A code
                # that cannot be parsed must not be silently accepted.
                severity=Severity.ERROR,
                message=(
                    f"ATC code '{regimen.atc_code}' does not match the "
                    f"expected format (e.g. J01DD04)."
                ),
                field="atc_code",
                suggested_fix=None,
            )]
        return []

    @classmethod
    def check_pregnancy_consistency(
        cls, regimen: NormalizedRegimen
    ) -> list[ValidationIssue]:
        """pregnancy flag consistency (only if applicable)."""
        if regimen.pregnancy is None:
            return []
        # pregnancy=True requires a population flag set
        if regimen.pregnancy and not (regimen.adult or regimen.child):
            return [ValidationIssue(
                code="PREGNANCY_WITHOUT_POPULATION",
                severity=Severity.REVIEW,
                message=(
                    "pregnancy=True but neither adult nor child is set."
                ),
                field="pregnancy",
                suggested_fix="Set adult=True or child=True.",
            )]
        return []

    @classmethod
    def check_renal_adjustment_consistency(
        cls, regimen: NormalizedRegimen
    ) -> list[ValidationIssue]:
        """renal_adjustment flag consistency (only if applicable)."""
        if not regimen.renal_adjustment:
            return []
        # renal_adjustment=True requires a population flag set
        if not (regimen.adult or regimen.child):
            return [ValidationIssue(
                code="RENAL_WITHOUT_POPULATION",
                severity=Severity.REVIEW,
                message=(
                    "renal_adjustment=True but neither adult nor child is set."
                ),
                field="renal_adjustment",
                suggested_fix="Set adult=True or child=True.",
            )]
        return []

    # ── Internal helpers ─────────────────────────────────

    @classmethod
    def _is_missing(cls, field_name: str, regimen: NormalizedRegimen) -> bool:
        if field_name == "drug":
            return not regimen.drug_normalized
        if field_name == "dose":
            return regimen.dose_value is None
        if field_name == "route":
            return not regimen.route or regimen.route == "unknown"
        if field_name == "frequency":
            return regimen.frequency_per_day is None
        return False

    @classmethod
    def _suggest_required(
        cls, field_name: str, regimen: NormalizedRegimen
    ) -> str | None:
        if field_name == "drug" and regimen.drug_original:
            return f"Normalize drug_original '{regimen.drug_original}'."
        if field_name == "route":
            return "Re-run RouteParser on the raw route text."
        if field_name == "frequency":
            return "Re-run FrequencyParser on the raw frequency text."
        return None

    _known_drugs_cache: set[str] | None = None

    @classmethod
    def _known_drugs(cls) -> set[str]:
        if cls._known_drugs_cache is None:
            cache: set[str] = set()
            for k, v in DRUG_SYNONYMS.items():
                cache.add(k.lower())
                cache.add(v.lower())
            cls._known_drugs_cache = cache
        return cls._known_drugs_cache

    @classmethod
    def invalidate_cache(cls) -> None:
        """Drop the cached known-drug set (H7).

        The cache mirrors medical_dictionary JSON, which can be reloaded at
        runtime via ``medical_dictionary.loader.reload_all()``; without this
        hook the cached set stayed stale for the life of the process. See
        ``medical_normalizer.confidence.invalidate_caches``.
        """
        cls._known_drugs_cache = None
