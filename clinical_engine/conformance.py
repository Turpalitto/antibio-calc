"""Conformance Validator (P2-1).

Additive only. Provides reporting (flag issues) for non-conforming bundles/manifests.
Default behavior unchanged. Opt-in for CI / strict checks.

Reuses frozen manifest validation + loader checks (P0-1/P0-3).
The frozen Bundle Loader received an RFC-approved additive extension while preserving default behavior and compatibility. No domain logic, no clinical paths.

Per Arch v3 P12 (open for extension).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from clinical_engine.bundles.loader import LoadedBundle, BundleLoadError
from clinical_engine.manifest import BundleManifest, validate_manifest, load_manifest


@dataclass(frozen=True, slots=True)
class ConformanceIssue:
    """Single conformance issue. Traceable."""

    code: str
    message: str
    severity: str  # "ERROR" | "WARNING"
    field: str | None = None


@dataclass(frozen=True, slots=True)
class ConformanceResult:
    """Result of conformance check. conformant=True iff no ERRORs."""

    conformant: bool
    issues: tuple[ConformanceIssue, ...]
    bundle_id: str | None = None


class ConformanceValidator:
    """Collects issues instead of (only) raising.

    strict_unknown=False (default) preserves I10 tolerance.
    strict_unknown=True: unknown fields -> ERROR (for curation/CI gates).
    """

    def __init__(self, *, strict_unknown: bool = False) -> None:
        self.strict_unknown = strict_unknown

    def validate_manifest(
        self, manifest: dict[str, Any] | BundleManifest
    ) -> ConformanceResult:
        """Validate manifest dict or typed. Collects issues."""
        issues: list[ConformanceIssue] = []
        bundle_id: str | None = None

        raw: dict[str, Any]
        if isinstance(manifest, BundleManifest):
            raw = {
                "schema_version": manifest.schema_version,
                "version": manifest.version,
                "requires_kernel": manifest.requires_kernel,
                "bundle_format": manifest.bundle_format,
                "content_hash": manifest.content_hash,
                "bundle_id": manifest.bundle_id,
                "bundle_type": manifest.bundle_type,
                "curation_status": manifest.curation_status,
                "expiry": manifest.expiry,
            }
            bundle_id = manifest.bundle_id
        else:
            raw = manifest
            bundle_id = raw.get("bundle_id")

        try:
            validate_manifest(raw)
        except ValueError as exc:
            issues.append(ConformanceIssue(
                code="MANIFEST_VALIDATION_ERROR",
                message=str(exc),
                severity="ERROR",
            ))

        # I10: optional strict on unknown
        if isinstance(manifest, dict):
            # simplistic: we know the expected from schema load, but to avoid
            # duplicating frozen schema, use presence after basic validate.
            # For strict, flag extra top-level keys not in known set.
            if self.strict_unknown:
                known = {
                    "schema_version", "version", "requires_kernel", "bundle_format",
                    "content_hash", "bundle_id", "bundle_type", "curation_status",
                    "generated_by", "source_refs", "jurisdiction", "specialty",
                    "signatures", "depends_on", "supersedes", "expiry",
                    "freshness_policy", "stats", "notes",
                }
                for k in raw:
                    if k not in known:
                        issues.append(ConformanceIssue(
                            code="UNKNOWN_FIELD",
                            message=f"Unknown field in strict mode: {k}",
                            severity="ERROR",
                            field=k,
                        ))

        # Additional policy-like checks (curation for prod intent example)
        curation = raw.get("curation_status") if isinstance(raw, dict) else getattr(manifest, "curation_status", None)
        if curation == "AUTO_GENERATED_DRAFT":
            issues.append(ConformanceIssue(
                code="DRAFT_IN_PRODUCTION_CONTEXT",
                message="curation_status is DRAFT; not suitable for production gate",
                severity="WARNING",
            ))

        conformant = not any(i.severity == "ERROR" for i in issues)
        return ConformanceResult(
            conformant=conformant,
            issues=tuple(issues),
            bundle_id=bundle_id,
        )

    def validate_loaded_bundle(self, loaded: LoadedBundle) -> ConformanceResult:
        """Validate a LoadedBundle from loader."""
        result = self.validate_manifest(loaded.manifest)
        # attach loader warnings as WARNING issues if present
        extra: list[ConformanceIssue] = []
        for w in loaded.warnings:
            extra.append(ConformanceIssue(
                code="LOADER_WARNING",
                message=w,
                severity="WARNING",
            ))
        all_issues = result.issues + tuple(extra)
        conformant = result.conformant and not any(i.severity == "ERROR" for i in extra)
        return ConformanceResult(
            conformant=conformant,
            issues=all_issues,
            bundle_id=result.bundle_id or loaded.manifest.bundle_id,
        )


def check_conformance(
    manifest_or_bundle: dict[str, Any] | BundleManifest | LoadedBundle,
    *,
    strict_unknown: bool = False,
) -> ConformanceResult:
    """Convenience. Returns report (never raises for reporting use)."""
    v = ConformanceValidator(strict_unknown=strict_unknown)
    if isinstance(manifest_or_bundle, LoadedBundle):
        return v.validate_loaded_bundle(manifest_or_bundle)
    return v.validate_manifest(manifest_or_bundle)