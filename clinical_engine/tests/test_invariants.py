"""Constitutional Invariant tests (spec §10.1 Tier 4, §12).

These protect the architecture itself, independent of any one stage's
business logic. As more stages land, add invariant coverage here rather
than re-deriving it ad hoc in stage test files.
"""

from __future__ import annotations

import dataclasses

import pytest

from clinical_engine.config import EngineConfig
from clinical_engine.engine import Engine
from clinical_engine.models import Patient, PatientQuery, Preferences
from clinical_engine.pipeline import ClinicalConstants, PipelineState, ScoreWeights, StageContext
from clinical_engine.stages.diagnosis_match import DiagnosisMatch
from clinical_engine.stages.dose_adjustment import DoseAdjustment
from clinical_engine.stages.dose_calculation import DoseCalculation
from clinical_engine.stages.hard_safety_filter import HardSafetyFilter
from clinical_engine.stages.interaction_check import InteractionCheck
from clinical_engine.stages.population_filter import PopulationFilter
from clinical_engine.stages.rank_recommendations import RankRecommendations
from clinical_engine.stages.regimen_load import RegimenLoad
from clinical_engine.stages.therapy_line_select import TherapyLineSelect
from clinical_engine.stages.trace import Trace
from clinical_engine.tests.conftest import make_candidate, make_recommendation

_ALL_STAGES = (
    DiagnosisMatch(),
    RegimenLoad(),
    PopulationFilter(),
    TherapyLineSelect(),
    HardSafetyFilter(),
    DoseCalculation(),
    DoseAdjustment(),
    InteractionCheck(),
    RankRecommendations(),
    Trace(),
)


def _run_all_stages(state: PipelineState, ctx: StageContext) -> tuple[PipelineState, ...]:
    """Runs the currently-wired pipeline, returning the state after each stage."""
    snapshots = []
    for stage in _ALL_STAGES:
        state = stage.run(state, ctx).state
        snapshots.append(state)
    return tuple(snapshots)


# ── Invariant #4: all public dataclasses frozen ─────────────────────────


def test_all_dataclasses_frozen() -> None:
    import clinical_engine.config as config_module
    import clinical_engine.models as models_module
    import clinical_engine.pipeline as pipeline_module

    for module in (models_module, config_module, pipeline_module):
        for name in dir(module):
            obj = getattr(module, name)
            if dataclasses.is_dataclass(obj):
                assert obj.__dataclass_params__.frozen, f"{module.__name__}.{name} must be frozen"


# ── Invariant: PatientQuery is immutable ────────────────────────────────


class TestPatientQueryImmutable:
    def test_replace_does_not_mutate_original(self) -> None:
        q = PatientQuery(diagnosis="CAP", patient=Patient(age=30))
        q2 = dataclasses.replace(q, diagnosis="UTI")
        assert q.diagnosis == "CAP"
        assert q2.diagnosis == "UTI"

    def test_direct_assignment_raises(self) -> None:
        q = PatientQuery(diagnosis="CAP")
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(q, "diagnosis", "mutated")


# ── Invariant: PipelineState replaced, never mutated ────────────────────


class TestPipelineStateImmutable:
    def test_stages_return_new_state_objects(self, stage_context: StageContext) -> None:
        query = PatientQuery(diagnosis="vnebolnichnaya pnevmoniya")
        state0 = PipelineState(patient=query)
        state1 = DiagnosisMatch().run(state0, stage_context).state
        assert state1 is not state0
        assert state0.guideline_ids == ()  # original untouched
        assert state1.guideline_ids == ("g_cap_adult",)

    def test_direct_assignment_raises(self) -> None:
        state = PipelineState(patient=PatientQuery())
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(state, "guideline_ids", ("x",))


# ── Invariant #6: StageTrace is immutable and append-only ───────────────


class TestTraceAppendOnly:
    def test_traces_only_grow_across_the_pipeline(self, stage_context: StageContext) -> None:
        query = PatientQuery(diagnosis="vnebolnichnaya pnevmoniya")
        state = PipelineState(patient=query)
        snapshots = _run_all_stages(state, stage_context)
        lengths = [len(s.traces) for s in snapshots]
        assert lengths == sorted(lengths)  # non-decreasing

    def test_earlier_traces_are_a_prefix_of_later_traces(
        self, stage_context: StageContext
    ) -> None:
        # Use an ambiguous-population patient so PopulationFilter also emits a trace.
        query = PatientQuery(diagnosis="vnebolnichnaya pnevmoniya")
        state = PipelineState(patient=query)
        snapshots = _run_all_stages(state, stage_context)
        for earlier, later in zip(snapshots, snapshots[1:]):
            assert later.traces[: len(earlier.traces)] == earlier.traces


# ── Invariant #1: once excluded, forever excluded (excluded only grows) ─


class TestExcludedOnlyGrows:
    def test_population_filter_never_shrinks_excluded(self, stage_context: StageContext) -> None:
        query = PatientQuery(patient=Patient(age=45))
        recs = (
            make_recommendation(make_candidate("r1", adult=True, child=False)),
            make_recommendation(make_candidate("r2", adult=False, child=True)),
        )
        prior_excluded = ((recs[1], "excluded_upstream_for_testing"),)
        state = PipelineState(
            patient=query, candidates=recs, excluded=prior_excluded
        )
        result = PopulationFilter().run(state, stage_context)
        assert len(result.state.excluded) >= len(prior_excluded)
        assert prior_excluded[0] in result.state.excluded

    def test_excluded_candidates_never_reappear_in_candidates(
        self, stage_context: StageContext
    ) -> None:
        query = PatientQuery(patient=Patient(age=45))
        recs = (
            make_recommendation(make_candidate("adult_only", adult=True, child=False)),
            make_recommendation(make_candidate("child_only", adult=False, child=True)),
        )
        state = PipelineState(patient=query, candidates=recs)
        result = PopulationFilter().run(state, stage_context)
        excluded_ids = {rec.candidate.regimen_id for rec, _ in result.state.excluded}
        candidate_ids = {rec.candidate.regimen_id for rec in result.state.candidates}
        assert excluded_ids.isdisjoint(candidate_ids)

    def test_hard_safety_filter_exclusion_survives_into_final_state(
        self, stage_context: StageContext
    ) -> None:
        """A genuine safety exclusion (allergy), not a population mismatch,
        must still respect Invariant #1 once it happens."""
        from clinical_engine.stages.hard_safety_filter import HardSafetyFilter

        query = PatientQuery(patient=Patient(allergies=("Пенициллины",)))
        recs = (make_recommendation(make_candidate("r1", drug_ref="amoxicillin")),)
        state = PipelineState(patient=query, candidates=recs)
        after_safety = HardSafetyFilter().run(state, stage_context).state
        assert after_safety.candidates == ()
        assert len(after_safety.excluded) == 1
        # A hypothetical later stage receiving this state cannot see "r1" in
        # candidates again -- there is no code path that removes from excluded.
        assert after_safety.excluded[0][0].candidate.regimen_id == "r1"


# ── Invariant #2: deterministic output ──────────────────────────────────


class TestDeterministicOutput:
    def test_engine_recommend_is_deterministic(self, engine_config: EngineConfig) -> None:
        query = PatientQuery(diagnosis="vnebolnichnaya pnevmoniya", patient=Patient(age=45))
        with Engine(engine_config) as engine:
            r1 = engine.recommend(query)
            r2 = engine.recommend(query)

        def _fingerprint(rset):
            return tuple(
                (
                    rec.candidate.regimen_id,
                    rec.candidate.guideline_id,
                    rec.candidate.drug_ref,
                    rec.candidate.guideline_year,
                )
                for rec in rset.accepted
            )

        assert _fingerprint(r1) == _fingerprint(r2)
        assert r1.excluded == r2.excluded
        assert len(r1.traces) == len(r2.traces)

    def test_stage_run_is_deterministic(self, stage_context: StageContext) -> None:
        query = PatientQuery(diagnosis="vnebolnichnaya pnevmoniya")
        state = PipelineState(patient=query)
        r1 = DiagnosisMatch().run(state, stage_context)
        r2 = DiagnosisMatch().run(state, stage_context)
        assert r1.state.guideline_ids == r2.state.guideline_ids


# ── Invariant #3: ranking never touches excluded/safety ─────────────────


def test_ranking_cannot_exclude(stage_context: StageContext) -> None:
    """RankRecommendations must only reorder/number state.candidates, never
    read or write state.excluded, never add/remove SafetyFlags, never
    change DoseDetail (Invariant #3)."""
    survivor = make_recommendation(make_candidate("survivor"))
    excluded_rec = make_recommendation(make_candidate("excluded_one"))
    prior_excluded = ((excluded_rec, "allergy"),)
    state = PipelineState(
        patient=PatientQuery(), candidates=(survivor,), excluded=prior_excluded
    )
    result = RankRecommendations().run(state, stage_context)
    assert result.state.excluded == prior_excluded  # byte-identical
    assert result.state.candidates[0].safety_flags == survivor.safety_flags
    assert result.state.candidates[0].dose == survivor.dose


def test_excluded_candidates_never_resurrected_by_ranking(stage_context: StageContext) -> None:
    """A candidate present in state.excluded before RankRecommendations must
    never appear in state.candidates after it."""
    survivor = make_recommendation(make_candidate("survivor"))
    excluded_rec = make_recommendation(make_candidate("excluded_one"))
    state = PipelineState(
        patient=PatientQuery(),
        candidates=(survivor,),
        excluded=((excluded_rec, "allergy"),),
    )
    result = RankRecommendations().run(state, stage_context)
    candidate_ids = {r.candidate.regimen_id for r in result.state.candidates}
    assert "excluded_one" not in candidate_ids
    assert len(result.state.candidates) == 1  # count unchanged, only reordered/scored


# ── Full pipeline: rank never resurrects excluded end-to-end ────────────


class TestFullPipelineRankingInvariant:
    def test_allergy_excluded_candidate_never_reaches_final_accepted(
        self, engine_config: EngineConfig
    ) -> None:
        query = PatientQuery(
            diagnosis="vnebolnichnaya pnevmoniya",
            patient=Patient(allergies=("Пенициллины",)),
        )
        with Engine(engine_config) as engine:
            result = engine.recommend(query)
        accepted_ids = {r.candidate.regimen_id for r in result.accepted}
        excluded_ids = {r.candidate.regimen_id for r, _ in result.excluded}
        assert accepted_ids.isdisjoint(excluded_ids)
        assert len(result.excluded) == 1
