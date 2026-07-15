"""Shared population-resolution helper.

Audit fix L1 (Milestone 9): `resolve_population_target` was previously a
private `_resolve_target` living inside stages/population_filter.py and
imported cross-stage by dose_calculation and rank_recommendations — hidden
coupling on a sibling stage's private symbol. It is domain logic shared by
three stages, so it lives here in a neutral module (not a stage).

No I/O, no mutation — a pure function over PatientQuery + ClinicalConstants.
"""

from __future__ import annotations

from clinical_engine.models import PatientQuery
from clinical_engine.pipeline import ClinicalConstants

# spec §3.1: "neonate -> age < 28 days"; child band upper bound 18y.
_DEFAULT_NEONATE_BAND = (0.0, 28 / 365)
_DEFAULT_CHILD_BAND = (0.0, 18.0)
_VALID_TARGETS = frozenset({"adult", "child", "neonate"})


def resolve_population_target(query: PatientQuery, constants: ClinicalConstants) -> str | None:
    """Resolve the effective population target for a query.

    Returns "adult" | "child" | "neonate" | None (ambiguous — age unknown
    and no usable preference). Never guesses on an unrecognized preference.
    """
    preference = query.preferences.population
    if preference in _VALID_TARGETS:
        return preference
    if preference is not None:
        return None  # unrecognized value -> degrade to ambiguous, don't guess

    age = query.patient.age
    if age is None:
        return None

    neonate_min, neonate_max = constants.age_bands.get("neonate", _DEFAULT_NEONATE_BAND)
    if neonate_min <= age <= neonate_max:
        return "neonate"

    child_min, child_max = constants.age_bands.get("child", _DEFAULT_CHILD_BAND)
    if age <= child_max:
        return "child"

    return "adult"
