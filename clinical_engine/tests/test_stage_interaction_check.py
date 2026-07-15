"""Milestone 7: Stage 8 — InteractionCheck.

Per DECISIONS.md 2026-07-10: free text can only ever yield
InteractionSeverity.UNKNOWN (never guessed higher). The CONTRAINDICATED/
MAJOR/MODERATE/MINOR branches are fully implemented but unreachable without
a structured interactions field on DrugInfo, which doesn't exist yet -- so
those are tested here by monkeypatching _check_structured_interactions,
proving the code path itself is correct and ready to activate.
"""

from __future__ import annotations

from clinical_engine.models import (
    DecisionCode,
    InteractionSeverity,
    Patient,
    PatientQuery,
    SafetyLevel,
)
from clinical_engine.pipeline import PipelineState, StageContext
from clinical_engine.stages import interaction_check as ic_module
from clinical_engine.stages.interaction_check import InteractionCheck
from clinical_engine.tests.conftest import make_candidate, make_recommendation


def _state(current_meds: tuple[str, ...], drug_ref: str | None) -> PipelineState:
    c = make_candidate("r1", drug_ref=drug_ref)
    rec = make_recommendation(c)
    query = PatientQuery(patient=Patient(current_meds=current_meds))
    return PipelineState(patient=query, candidates=(rec,))


class TestNoCurrentMeds:
    def test_empty_current_meds_skips_entirely(self, stage_context: StageContext) -> None:
        state = _state((), "amoxicillin")
        result = InteractionCheck().run(state, stage_context)
        assert result.state.candidates == state.candidates  # untouched, same objects
        assert result.state.safety_flags == ()
        assert result.state.traces == ()


class TestFreeTextMatch:
    def test_no_interactions_data_is_silent(self, stage_context: StageContext) -> None:
        state = _state(("аллопуринол",), "unmapped_drug")  # interactions=None
        result = InteractionCheck().run(state, stage_context)
        assert result.state.candidates[0].safety_flags == ()

    def test_substring_match_yields_unknown_not_moderate(
        self, stage_context: StageContext
    ) -> None:
        # amoxicillin fixture interactions text mentions "аллопуринолом"
        state = _state(("аллопуринол",), "amoxicillin")
        result = InteractionCheck().run(state, stage_context)
        rec = result.state.candidates[0]
        assert rec.interaction_severity is InteractionSeverity.UNKNOWN
        flags = rec.safety_flags
        assert len(flags) == 1
        assert flags[0].code == "INTERACTION_UNKNOWN"
        assert flags[0].level is SafetyLevel.WARNING
        assert any(t.decision_code is DecisionCode.INTERACTION for t in result.state.traces)

    def test_no_match_is_silent(self, stage_context: StageContext) -> None:
        state = _state(("совершенно неродственный препарат",), "amoxicillin")
        result = InteractionCheck().run(state, stage_context)
        rec = result.state.candidates[0]
        assert rec.safety_flags == ()
        assert rec.interaction_severity is None

    def test_never_excludes_on_unknown_severity(self, stage_context: StageContext) -> None:
        state = _state(("аллопуринол",), "amoxicillin")
        result = InteractionCheck().run(state, stage_context)
        assert len(result.state.candidates) == 1
        assert result.state.excluded == ()

    def test_multiple_current_meds_one_match_still_single_flag(
        self, stage_context: StageContext
    ) -> None:
        state = _state(("неродственный препарат", "аллопуринол", "ещё один"), "amoxicillin")
        result = InteractionCheck().run(state, stage_context)
        assert len(result.state.candidates[0].safety_flags) == 1

    def test_drug_ref_unresolved_is_silent(self, stage_context: StageContext) -> None:
        state = _state(("аллопуринол",), None)
        result = InteractionCheck().run(state, stage_context)
        assert result.state.candidates[0].safety_flags == ()


class TestSelfInteraction:
    def test_own_inn_in_current_meds_is_not_a_match(self, stage_context: StageContext) -> None:
        # patient is already taking amoxicillin -- its own inn appears in
        # current_meds; it must not be flagged as interacting with itself.
        state = _state(("Амоксициллин",), "amoxicillin")
        result = InteractionCheck().run(state, stage_context)
        assert result.state.candidates[0].safety_flags == ()

    def test_own_drug_ref_in_current_meds_is_not_a_match(
        self, stage_context: StageContext
    ) -> None:
        state = _state(("amoxicillin",), "amoxicillin")
        result = InteractionCheck().run(state, stage_context)
        assert result.state.candidates[0].safety_flags == ()

    def test_self_and_real_interaction_together_only_flags_the_real_one(
        self, stage_context: StageContext
    ) -> None:
        state = _state(("amoxicillin", "аллопуринол"), "amoxicillin")
        result = InteractionCheck().run(state, stage_context)
        assert len(result.state.candidates[0].safety_flags) == 1


class TestStructuredSeverityBranches:
    """CONTRAINDICATED/MAJOR/MODERATE/MINOR are unreachable without a
    structured field on DrugInfo (see module docstring) -- verified here by
    monkeypatching the (currently always-None) structured lookup."""

    def test_contraindicated_excludes(self, stage_context: StageContext, monkeypatch) -> None:
        monkeypatch.setattr(
            ic_module, "_check_structured_interactions",
            lambda drug_info, meds: InteractionSeverity.CONTRAINDICATED,
        )
        state = _state(("warfarin",), "amoxicillin")
        result = InteractionCheck().run(state, stage_context)
        assert result.state.candidates == ()
        rec, reason = result.state.excluded[0]
        assert "contraindicated" in reason
        assert rec.safety_flags[0].code == "INTERACTION_CI"
        assert rec.safety_flags[0].level is SafetyLevel.ABSOLUTE_CONTRAINDICATION
        assert rec.safety_flags[0].requires_physician_acknowledgement is True

    def test_major_warns_never_excludes(self, stage_context: StageContext, monkeypatch) -> None:
        monkeypatch.setattr(
            ic_module, "_check_structured_interactions",
            lambda drug_info, meds: InteractionSeverity.MAJOR,
        )
        state = _state(("warfarin",), "amoxicillin")
        result = InteractionCheck().run(state, stage_context)
        assert len(result.state.candidates) == 1
        assert result.state.excluded == ()
        assert result.state.candidates[0].safety_flags[0].code == "INTERACTION_MAJOR"

    def test_moderate_warns_no_trace(self, stage_context: StageContext, monkeypatch) -> None:
        monkeypatch.setattr(
            ic_module, "_check_structured_interactions",
            lambda drug_info, meds: InteractionSeverity.MODERATE,
        )
        state = _state(("warfarin",), "amoxicillin")
        result = InteractionCheck().run(state, stage_context)
        assert result.state.candidates[0].safety_flags[0].code == "INTERACTION_MODERATE"
        assert result.state.traces == ()  # §6.4: MODERATE gets no trace line

    def test_minor_warns_no_trace(self, stage_context: StageContext, monkeypatch) -> None:
        monkeypatch.setattr(
            ic_module, "_check_structured_interactions",
            lambda drug_info, meds: InteractionSeverity.MINOR,
        )
        state = _state(("warfarin",), "amoxicillin")
        result = InteractionCheck().run(state, stage_context)
        assert result.state.candidates[0].safety_flags[0].code == "INTERACTION_MINOR"
        assert result.state.traces == ()

    def test_excluded_never_resurrected_after_contraindicated(
        self, stage_context: StageContext, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            ic_module, "_check_structured_interactions",
            lambda drug_info, meds: InteractionSeverity.CONTRAINDICATED,
        )
        state = _state(("warfarin",), "amoxicillin")
        result = InteractionCheck().run(state, stage_context)
        excluded_ids = {rec.candidate.regimen_id for rec, _ in result.state.excluded}
        candidate_ids = {rec.candidate.regimen_id for rec in result.state.candidates}
        assert excluded_ids.isdisjoint(candidate_ids)


class TestEmptyCandidates:
    def test_no_candidates_is_a_noop(self, stage_context: StageContext) -> None:
        query = PatientQuery(patient=Patient(current_meds=("аллопуринол",)))
        state = PipelineState(patient=query)
        result = InteractionCheck().run(state, stage_context)
        assert result.state.candidates == ()
