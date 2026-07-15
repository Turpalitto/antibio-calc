"""Unified physician-curated knowledge layer (P3 INT-4).

Composes the curated diagnosis layer + curated regimen layer into one canonical,
read-only query surface with explicit review-required semantics (never a silent
fallback to unapproved data). Additive: the base Engine, routing, and safety
stages are unchanged; curated enforcement is an opt-in wrapper.
"""

from clinical_engine.curated.knowledge import (
    ApprovedChain,
    CuratedEngine,
    CuratedKnowledge,
    ReviewRequired,
)

__all__ = ["CuratedKnowledge", "CuratedEngine", "ApprovedChain", "ReviewRequired"]
