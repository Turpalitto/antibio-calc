"""Stage 5: HardSafetyFilter — absolute clinical exclusions.

Source: docs/superpowers/specs/clinical-decision-engine-v1.md §6.1.

This is the first stage allowed to permanently exclude a candidate
(Invariant #1: once excluded, forever excluded). Everything here follows
the "degraded mode" principle from Invariant #11: missing data produces a
WARNING and the candidate survives; only *positive* evidence of a
contraindication excludes. Unknown is never treated as safe, and never
treated as contraindicated.

Allergy classes are resolved through the curated ``allergy_class_hierarchy``
(``AllergyClassResolver``, M-4) rather than the per-drug ``allergy_class_map``
alone, so a drug absent from that map but present in db/index.json is still
classifiable instead of producing ALLERGY_UNVERIFIABLE for every allergic
patient, and so a detailed class label ("Полусинтетические пенициллины
широкого спектра") compares equal to the family the physician stated
("Пенициллины"). Documented cross-reactivity (penicillin <-> cephalosporin)
raises a WARNING, never an exclusion.

Trace note: like RegimenLoad (Milestone 3), this stage does not emit a
StageTrace for the boring "survived every check" case — DecisionCode has no
member for "no decision", and the spec's own pseudocode literally writes
"DecisionCode.(none)" for that branch, which isn't a real enum value. Traces
are only emitted for actual decisions: an exclusion, or a degraded-mode
warning worth auditing.
"""

from __future__ import annotations

import dataclasses
import re
import time

from clinical_engine.models import (
    ConfidenceLevel,
    DecisionCode,
    PregnancyCategory,
    Recommendation,
    SafetyAction,
    SafetyFlag,
    SafetyLevel,
    StageTrace,
)
from clinical_engine.pipeline import PipelineState, StageContext, StageResult
from clinical_engine.terminology import AllergyClassResolver

# "N мес(яц...)" / "N лет|год(а)" -- the spec's own algorithm names a
# parse_age_restriction() helper (distinct from the free-text interactions/
# renal prose Invariant #13 forbids parsing). This handles only the narrow
# "<number> <unit>" shape actually present in db/index.json (e.g. "18 лет",
# "6 мес"). Anything else -> None (unparseable, never guessed).
_AGE_PATTERN = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(мес|месяц\w*|лет|год\w*)\s*$", re.IGNORECASE)


def _parse_age_restriction(raw: str | None) -> float | None:
    if not raw:
        return None
    match = _AGE_PATTERN.match(raw)
    if not match:
        return None
    value = float(match.group(1).replace(",", "."))
    unit = match.group(2).lower()
    if unit.startswith("мес"):
        return value / 12.0
    return value  # лет/год* -> years


def _norm(class_name: str) -> str:
    """Comparison key for allergy class names (case/whitespace tolerant)."""
    return " ".join(class_name.split()).casefold()


class HardSafetyFilter:
    name = "HardSafetyFilter"

    def run(self, state: PipelineState, ctx: StageContext) -> StageResult:
        start = time.perf_counter()
        patient = state.patient.patient
        # M-4: the class vocabulary is the curated allergy_class_hierarchy
        # (allergy_class_map is its reverse index in production). Built once per
        # run from the frozen constants — no I/O, no state.
        resolver = AllergyClassResolver(ctx.constants)
        # P1 terminology binding additionally contributes the ATC-derived
        # fallback (J01C* -> Пенициллины) when the curated sources are silent.
        atc_fallback = (
            getattr(ctx.terminology_provider, "get_atc", None)
            if ctx.config.use_terminology_binding else None
        )

        kept: list[Recommendation] = []
        excluded = list(state.excluded)
        safety_flags = list(state.safety_flags)
        traces = list(state.traces)

        for rec in state.candidates:
            c = rec.candidate
            # P0-2: drug_safety_provider (wraps reader, identical)
            drug_info = ctx.drug_safety_provider.get_drug_info(c.drug_ref) if c.drug_ref else None

            if drug_info is None:
                flag = SafetyFlag(
                    level=SafetyLevel.WARNING,
                    code="DRUG_UNKNOWN",
                    message=f"'{c.drug_normalized}' not found in drug reference; safety checks skipped",
                    drug_ref=c.drug_ref or "",
                    stage=self.name,
                    action=SafetyAction.MONITOR_CLOSELY,
                    requires_physician_acknowledgement=False,
                )
                safety_flags.append(flag)
                traces.append(
                    StageTrace(
                        stage_name=self.name,
                        decision_code=DecisionCode.NO_MATCH,
                        reason=f"{c.drug_normalized} (regimen {c.regimen_id}): drug_ref unresolved, safety checks skipped",
                        decision_confidence=ConfidenceLevel.HIGH,
                    )
                )
                kept.append(dataclasses.replace(rec, safety_flags=rec.safety_flags + (flag,)))
                continue

            rec_flags: list[SafetyFlag] = []
            excluded_here = False
            exclusion_reason = ""

            # 1. Allergy check (ABSOLUTE) -- canonical family via the curated
            # class hierarchy. Audit fix M1 (Milestone 9): case-insensitive
            # comparison, and a WARNING when the patient states allergies but
            # the drug's class cannot be resolved (Unknown != Safe -- never
            # silently include an unverifiable drug for an allergic patient).
            if patient.allergies:
                atc = None
                if atc_fallback is not None and c.drug_ref:
                    atc = atc_fallback(c.drug_ref)
                resolution = resolver.resolve(
                    c.drug_ref, drug_info.drug_class or None, atc=atc
                )
                drug_class = resolution.class_name
                # The patient's stated allergies are normalized onto the same
                # family vocabulary, so "пенициллины" and the detailed class
                # label "Полусинтетические пенициллины широкого спектра" both
                # compare equal to the family "Пенициллины".
                allergies_lower = {
                    _norm(resolver.canonical_family(a)) for a in patient.allergies if a.strip()
                }
                if drug_class is None:
                    rec_flags.append(
                        SafetyFlag(
                            level=SafetyLevel.WARNING,
                            code="ALLERGY_UNVERIFIABLE",
                            message=(
                                f"{c.drug_normalized}: drug class unknown, cannot verify "
                                "against patient's stated allergies"
                            ),
                            drug_ref=c.drug_ref,
                            stage=self.name,
                            action=SafetyAction.MONITOR_CLOSELY,
                            requires_physician_acknowledgement=True,
                        )
                    )
                elif _norm(drug_class) in allergies_lower:
                    flag = SafetyFlag(
                        level=SafetyLevel.ABSOLUTE_CONTRAINDICATION,
                        code="ALLERGY",
                        message=f"{c.drug_normalized} is {drug_class}, patient allergic",
                        drug_ref=c.drug_ref,
                        stage=self.name,
                        action=SafetyAction.STOP_IMMEDIATELY,
                        requires_physician_acknowledgement=True,
                    )
                    rec_flags.append(flag)
                    traces.append(
                        StageTrace(
                            stage_name=self.name,
                            decision_code=DecisionCode.ALLERGY,
                            reason=(
                                f"{c.drug_normalized} (regimen {c.regimen_id}): "
                                f"patient allergic to {drug_class} "
                                f"(class resolved via {resolution.source})"
                            ),
                            decision_confidence=ConfidenceLevel.FULL,
                        )
                    )
                    excluded_here = True
                    exclusion_reason = f"allergy: {drug_class}"
                else:
                    # M-4: documented, non-absolute cross-reactivity. Warns,
                    # never excludes -- the real-world risk is a minority of
                    # patients and depends on the side chain, which is not in
                    # the data.
                    for related in resolver.cross_reactive_with(drug_class):
                        if _norm(related) in allergies_lower:
                            flag = SafetyFlag(
                                level=SafetyLevel.WARNING,
                                code="ALLERGY_CROSS_REACTIVITY",
                                message=(
                                    f"{c.drug_normalized} is {drug_class}, cross-reactive with "
                                    f"the stated {related} allergy — avoid if an alternative "
                                    "exists, acknowledge before use"
                                ),
                                drug_ref=c.drug_ref,
                                stage=self.name,
                                action=SafetyAction.AVOID_IF_POSSIBLE,
                                requires_physician_acknowledgement=True,
                            )
                            rec_flags.append(flag)
                            traces.append(
                                StageTrace(
                                    stage_name=self.name,
                                    decision_code=DecisionCode.ALLERGY,
                                    reason=(
                                        f"{c.drug_normalized} (regimen {c.regimen_id}): "
                                        f"{drug_class} cross-reacts with stated {related} allergy"
                                    ),
                                    decision_confidence=ConfidenceLevel.MEDIUM,
                                )
                            )
                            break

            # 2. Pregnancy check (ABSOLUTE / CAUTION / UNKNOWN)
            if not excluded_here and patient.pregnant:
                category = drug_info.pregnancy_category
                source_text = drug_info.pregnancy_source_text
                # C-1: keep the verbatim source text next to the enum, so a
                # trimester-conditional contraindication ("противопоказан в I и
                # III триместрах") is visible to the physician instead of being
                # flattened into an opaque category.
                suffix = f" (source: {source_text!r})" if source_text else ""
                if category is PregnancyCategory.PROHIBITED:
                    flag = SafetyFlag(
                        level=SafetyLevel.ABSOLUTE_CONTRAINDICATION,
                        code="PREGNANCY_CI",
                        message=(
                            f"{c.drug_normalized} is contraindicated in pregnancy{suffix}"
                        ),
                        drug_ref=c.drug_ref,
                        stage=self.name,
                        action=SafetyAction.STOP_IMMEDIATELY,
                        requires_physician_acknowledgement=True,
                    )
                    rec_flags.append(flag)
                    traces.append(
                        StageTrace(
                            stage_name=self.name,
                            decision_code=DecisionCode.PREGNANCY,
                            reason=(
                                f"{c.drug_normalized} (regimen {c.regimen_id}): "
                                f"pregnancy_category=PROHIBITED{suffix}"
                            ),
                            decision_confidence=ConfidenceLevel.FULL,
                        )
                    )
                    excluded_here = True
                    exclusion_reason = "pregnancy: prohibited"
                elif category is PregnancyCategory.CAUTION:
                    rec_flags.append(
                        SafetyFlag(
                            level=SafetyLevel.WARNING,
                            code="PREGNANCY_CAUTION",
                            message=f"{c.drug_normalized}: use in pregnancy with caution{suffix}",
                            drug_ref=c.drug_ref,
                            stage=self.name,
                            action=SafetyAction.MONITOR_CLOSELY,
                            requires_physician_acknowledgement=False,
                        )
                    )
                elif category is PregnancyCategory.UNKNOWN:
                    rec_flags.append(
                        SafetyFlag(
                            level=SafetyLevel.WARNING,
                            code="PREGNANCY_UNKNOWN",
                            message=f"{c.drug_normalized}: pregnancy safety not classified",
                            drug_ref=c.drug_ref,
                            stage=self.name,
                            action=SafetyAction.MONITOR_CLOSELY,
                            requires_physician_acknowledgement=False,
                        )
                    )
                # ALLOWED -> no flag, no exclusion.

            # 3. Age restriction check (ABSOLUTE)
            if not excluded_here:
                has_restriction = (
                    drug_info.age_restriction_min is not None
                    or drug_info.age_restriction_max is not None
                )
                if patient.age is None:
                    if has_restriction:
                        rec_flags.append(
                            SafetyFlag(
                                level=SafetyLevel.WARNING,
                                code="AGE_UNKNOWN",
                                message=f"{c.drug_normalized} has an age restriction but patient age is unknown",
                                drug_ref=c.drug_ref,
                                stage=self.name,
                                action=SafetyAction.MONITOR_CLOSELY,
                                requires_physician_acknowledgement=False,
                            )
                        )
                else:
                    min_age = _parse_age_restriction(drug_info.age_restriction_min)
                    max_age = _parse_age_restriction(drug_info.age_restriction_max)
                    # L-2: a restriction that exists but cannot be parsed used to
                    # be skipped silently, even with a known age — the drug
                    # looked exactly as safe as one with no restriction. Degrade
                    # to an explicit flag instead.
                    unparsed = [
                        raw
                        for raw in (
                            drug_info.age_restriction_min,
                            drug_info.age_restriction_max,
                        )
                        if raw and _parse_age_restriction(raw) is None
                    ]
                    if unparsed:
                        rec_flags.append(
                            SafetyFlag(
                                level=SafetyLevel.WARNING,
                                code="AGE_RESTRICTION_UNPARSED",
                                message=(
                                    f"{c.drug_normalized}: age restriction "
                                    f"{unparsed!r} could not be parsed; the age check was "
                                    "skipped for this drug"
                                ),
                                drug_ref=c.drug_ref,
                                stage=self.name,
                                action=SafetyAction.MONITOR_CLOSELY,
                                requires_physician_acknowledgement=True,
                            )
                        )
                    if min_age is not None and patient.age < min_age:
                        flag = SafetyFlag(
                            level=SafetyLevel.ABSOLUTE_CONTRAINDICATION,
                            code="AGE_BELOW_MIN",
                            message=f"{c.drug_normalized}: patient age {patient.age} below minimum {min_age}",
                            drug_ref=c.drug_ref,
                            stage=self.name,
                            action=SafetyAction.STOP_IMMEDIATELY,
                            requires_physician_acknowledgement=True,
                        )
                        rec_flags.append(flag)
                        traces.append(
                            StageTrace(
                                stage_name=self.name,
                                decision_code=DecisionCode.AGE,
                                reason=f"{c.drug_normalized} (regimen {c.regimen_id}): age {patient.age} < min {min_age}",
                                decision_confidence=ConfidenceLevel.FULL,
                            )
                        )
                        excluded_here = True
                        exclusion_reason = "age: below minimum"
                    elif max_age is not None and patient.age > max_age:
                        flag = SafetyFlag(
                            level=SafetyLevel.ABSOLUTE_CONTRAINDICATION,
                            code="AGE_ABOVE_MAX",
                            message=f"{c.drug_normalized}: patient age {patient.age} above maximum {max_age}",
                            drug_ref=c.drug_ref,
                            stage=self.name,
                            action=SafetyAction.STOP_IMMEDIATELY,
                            requires_physician_acknowledgement=True,
                        )
                        rec_flags.append(flag)
                        traces.append(
                            StageTrace(
                                stage_name=self.name,
                                decision_code=DecisionCode.AGE,
                                reason=f"{c.drug_normalized} (regimen {c.regimen_id}): age {patient.age} > max {max_age}",
                                decision_confidence=ConfidenceLevel.FULL,
                            )
                        )
                        excluded_here = True
                        exclusion_reason = "age: above maximum"

            # 4. Contraindication check (ABSOLUTE) -- always free text today
            # (0/40 drugs have this field populated -- see DECISIONS.md
            # 2026-07-10). Invariant #13 forbids parsing prose at runtime, so
            # a present-but-unstructured value can only ever produce a
            # WARNING, never an exclusion, until drugs_reference gets a
            # structured contraindications field.
            if not excluded_here and drug_info.contraindications is not None:
                rec_flags.append(
                    SafetyFlag(
                        level=SafetyLevel.WARNING,
                        code="CI_UNPARSED",
                        message=f"{c.drug_normalized}: contraindications text present but not structured, review manually",
                        drug_ref=c.drug_ref,
                        stage=self.name,
                        action=SafetyAction.MONITOR_CLOSELY,
                        requires_physician_acknowledgement=False,
                    )
                )

            updated_rec = dataclasses.replace(
                rec, safety_flags=rec.safety_flags + tuple(rec_flags)
            )
            safety_flags.extend(rec_flags)

            if excluded_here:
                excluded.append((updated_rec, exclusion_reason))
            else:
                kept.append(updated_rec)

        new_state = dataclasses.replace(
            state,
            candidates=tuple(kept),
            excluded=tuple(excluded),
            safety_flags=tuple(safety_flags),
            traces=tuple(traces),
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        return StageResult(
            state=new_state,
            metrics={
                "excluded_this_stage": len(excluded) - len(state.excluded),
                "flags_raised": len(safety_flags) - len(state.safety_flags),
            },
            elapsed_ms=elapsed_ms,
        )
