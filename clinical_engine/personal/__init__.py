"""Additive local-only PERSONAL_PHYSICIAN bundle service."""

from .bundle import (
    attest,
    build_personal_bundle,
    compute_owner_signature,
    compute_payload_sha256,
    load_owner_profile,
    load_personal_bundle,
    load_personal_service,
    recover_unactivated_owner,
    register_owner,
    sha256_text,
)
from .guard import GuardDecision, PersonalPhysicianGuard
from .models import (
    OWNER_BUNDLE_STATUS,
    PERSONAL_MODE,
    OwnerAttestation,
    OwnerProfile,
    PersonalModeError,
    PersonalPhysicianBundle,
    PersonalRecommendationResult,
    PersonalRegimen,
)
from .recommender import PersonalModeService, PersonalRecommender
from .runtime import DEFAULT_STATE_DIR, PersonalRuntime

__all__ = [
    "GuardDecision", "OWNER_BUNDLE_STATUS", "OwnerAttestation", "OwnerProfile",
    "PERSONAL_MODE", "PersonalModeError", "PersonalModeService", "PersonalPhysicianBundle",
    "PersonalPhysicianGuard", "PersonalRecommendationResult", "PersonalRecommender",
    "PersonalRegimen", "attest", "build_personal_bundle", "compute_owner_signature", "compute_payload_sha256",
    "load_owner_profile", "load_personal_bundle", "load_personal_service",
    "recover_unactivated_owner", "register_owner", "sha256_text", "DEFAULT_STATE_DIR", "PersonalRuntime",
]
