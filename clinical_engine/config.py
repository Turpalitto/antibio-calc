"""EngineConfig + ValidationPolicy profiles.

Source: docs/superpowers/specs/clinical-decision-engine-v1.md section 5.6.
No I/O here — Profiles.* are trivial dataclass factories, not loaders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from clinical_engine.models import ValidationPolicy

# M-2: profiles whose "no verdict filter" behaviour loads REJECT rows. A REJECT
# row is one the normalizer itself could not accept, so anything built from it
# is a research artifact, never a clinical recommendation. Defined here (not in
# the reader) so config.py stays the single place a caller inspects.
NON_CLINICAL_POLICIES: frozenset[ValidationPolicy] = frozenset(
    {ValidationPolicy.DEBUG, ValidationPolicy.AUDIT}
)

# Audit fix M3 (Milestone 9): default resource paths are anchored to the
# package location, not the process CWD, so Profiles.production(...) etc.
# work regardless of where the engine is launched from. Callers can still
# override any path explicitly.
_PACKAGE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _PACKAGE_DIR.parent
_DEFAULT_DRUG_REFERENCE = str(_REPO_ROOT / "db" / "index.json")
_DEFAULT_DIAGNOSIS_INDEX = str(_PACKAGE_DIR / "resources" / "diagnosis_index.json")
_DEFAULT_CLINICAL_CONSTANTS = str(_PACKAGE_DIR / "resources" / "clinical_constants.json")


@dataclass(frozen=True, slots=True)
class EngineConfig:
    sqlite_path: str
    drug_reference_path: str = field(default_factory=lambda: _DEFAULT_DRUG_REFERENCE)
    diagnosis_index_path: str = field(default_factory=lambda: _DEFAULT_DIAGNOSIS_INDEX)
    score_profile: str = "default"  # which score_profiles/*.json to use
    clinical_constants_path: str = field(default_factory=lambda: _DEFAULT_CLINICAL_CONSTANTS)
    validation_policy: ValidationPolicy = ValidationPolicy.STRICT
    debug: bool = False
    cache_readers: bool = True
    # Milestone 13 (Release Readiness): Production Guard. When True and the
    # diagnosis_index status is AUTO_GENERATED_DRAFT / PARTIALLY_CURATED,
    # Engine.__init__ refuses to start (uncurated clinical routing must not be
    # used in production). When False, it emits an explicit warning instead.
    # Safe by default (True). Does not change any medical logic.
    strict_mode: bool = True

    # P0-2: Feature flag for Provider Ports migration.
    # False (default) = legacy direct reader access in StageContext (exact prior behavior).
    # True = use RegimenProvider / DiagnosisProvider / DrugSafetyProvider (adapters).
    # Legacy + providers coexist during migration. Flip only after equality tests.
    use_provider_ports: bool = False

    # P0-4: Bundle wrapping migration flag.
    # When True, prefer loading resources via BundleLoader (P0-3) where manifests available.
    # Goal: identical behavior. Additive only.
    use_bundles: bool = False

    # P1: Terminology binding flag.
    # When True, use TerminologyProvider for ATC/allergy_class instead of direct map.
    # Additive, fallback preserved. Clinical value: better standardization.
    use_terminology_binding: bool = False

    @property
    def is_non_clinical_profile(self) -> bool:
        """True for profiles that load non-clinical data (M-2).

        DEBUG/AUDIT load REJECT-verdict regimens, so a result built under them
        is a research artifact. Every consumer of such a config must record
        that fact (Engine.recommend attaches a WARN EngineNote).
        """
        return self.validation_policy in NON_CLINICAL_POLICIES


class Profiles:
    """Named EngineConfig presets (§3.6 ValidationPolicy table).

    M-2: research/development/audit must keep strict_mode=False (they exist to
    run against an uncurated index at all) but they are NOT clinical modes.
    They are therefore marked via the derived `is_non_clinical_profile`, and
    Engine.recommend() records a WARN EngineNote in the result so a
    non-clinical run can never be mistaken for a clinical one.
    """

    @staticmethod
    def production(sqlite_path: str) -> EngineConfig:
        return EngineConfig(sqlite_path=sqlite_path, validation_policy=ValidationPolicy.STRICT,
                            strict_mode=True)

    @staticmethod
    def research(sqlite_path: str) -> EngineConfig:
        return EngineConfig(
            sqlite_path=sqlite_path, validation_policy=ValidationPolicy.ALLOW_REVIEW,
            strict_mode=False,
        )

    @staticmethod
    def development(sqlite_path: str) -> EngineConfig:
        return EngineConfig(
            sqlite_path=sqlite_path, validation_policy=ValidationPolicy.DEBUG, debug=True,
            strict_mode=False,  # M-2: non-clinical profile; result carries a WARN note
        )

    @staticmethod
    def audit(sqlite_path: str) -> EngineConfig:
        return EngineConfig(sqlite_path=sqlite_path, validation_policy=ValidationPolicy.AUDIT,
                            strict_mode=False)  # M-2: non-clinical profile
