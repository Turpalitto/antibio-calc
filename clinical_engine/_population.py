"""Shared population-resolution helper.

Audit fix L1 (Milestone 9): `resolve_population_target` was previously a
private `_resolve_target` living inside stages/population_filter.py and
imported cross-stage by dose_calculation and rank_recommendations — hidden
coupling on a sibling stage's private symbol. It is domain logic shared by
three stages, so it lives here in a neutral module (not a stage).

No I/O, no mutation — a pure function over PatientQuery + ClinicalConstants.

Two safety rules live here (both were silent, both are patient-critical):

* **C-3 — a stated preference never overrides the patient's age.** A stated
  `preferences.population` is a *hint* from the caller; age is a *fact* about
  the patient. The old code returned the preference immediately, so
  age=0.25 (3 months) + preference "adult" resolved to ADULT and
  DoseCalculation took the adult fixed-dose branch — amoxicillin 500 mg for a
  4.2 kg infant (~119 mg/kg), no flag, outcome ACCEPTED. Age now always wins
  when it is present and readable; a conflicting preference is reported
  through the resolution reason, never silently honoured.
* **L-1 — the child band lower bound is validated.** `child_min` was bound and
  never used, so a negative age fell into the child band. An age outside
  [0, child_max] is not a population fact and degrades to ambiguous (which the
  stages report as a WARNING), it is never rounded into a band.
"""

from __future__ import annotations

from dataclasses import dataclass

from clinical_engine.models import PatientQuery
from clinical_engine.pipeline import ClinicalConstants

# spec §3.1: "neonate -> age < 28 days"; child band upper bound 18y.
_DEFAULT_NEONATE_BAND = (0.0, 28 / 365)
_DEFAULT_CHILD_BAND = (0.0, 18.0)
_VALID_TARGETS = frozenset({"adult", "child", "neonate"})


@dataclass(frozen=True, slots=True)
class PopulationResolution:
    """Effective population target + WHY (Clinical Traceability Rule)."""

    target: str | None  # "adult" | "child" | "neonate" | None (ambiguous)
    reason: str
    preference_conflict: bool = False  # a stated preference was overridden by age


def resolve_population(query: PatientQuery, constants: ClinicalConstants) -> PopulationResolution:
    """Resolve the effective population target with a traceable reason."""
    preference = query.preferences.population
    age = query.patient.age

    # Age first: a fact beats a hint (C-3).
    if age is not None:
        derived, age_reason = _target_from_age(age, constants)
        if preference is None:
            return PopulationResolution(derived, f"age-derived: {age_reason}")
        if preference not in _VALID_TARGETS:
            # Unusable value: it is not a fact, so it must not block the age
            # fact. Recorded, never guessed into a band.
            return PopulationResolution(
                derived,
                f"age-derived: {age_reason}; unrecognized population preference "
                f"{preference!r} ignored",
            )
        if preference == derived:
            return PopulationResolution(
                derived, f"age-derived: {age_reason}; preference {preference!r} agrees"
            )
        return PopulationResolution(
            derived,
            f"age-derived: {age_reason}; stated population preference "
            f"{preference!r} conflicts with patient age and was overridden",
            preference_conflict=True,
        )

    if preference in _VALID_TARGETS:
        return PopulationResolution(
            preference, f"stated preference {preference!r} (age unknown)"
        )
    if preference is not None:
        return PopulationResolution(
            None, f"unrecognized population preference {preference!r} and age unknown"
        )
    return PopulationResolution(None, "age unknown and no population preference")


def resolve_population_target(query: PatientQuery, constants: ClinicalConstants) -> str | None:
    """Backwards-compatible target-only view of :func:`resolve_population`."""
    return resolve_population(query, constants).target


def _target_from_age(
    age: float, constants: ClinicalConstants
) -> tuple[str | None, str]:
    """(target, reason) derived from age alone. None target == ambiguous."""
    if age < 0:
        # L-1: an impossible age is not a population fact.
        return None, f"age {age} is negative/out of range"

    neonate_min, neonate_max = constants.age_bands.get("neonate", _DEFAULT_NEONATE_BAND)
    if neonate_min <= age <= neonate_max:
        return "neonate", f"age {age} within neonate band [{neonate_min}, {neonate_max}]"

    child_min, child_max = constants.age_bands.get("child", _DEFAULT_CHILD_BAND)
    if child_min <= age <= child_max:
        return "child", f"age {age} within child band [{child_min}, {child_max}]"

    if age > child_max:
        return "adult", f"age {age} above child band max {child_max}"
    # Above the neonate floor but below the child floor: no band owns it.
    return None, f"age {age} falls in no configured population band"
