"""Tests for PHYSICIAN_PILOT_V1 — the pilot-batch selection policy.

``PHYSICIAN_PILOT_POLICY.md`` fixes the hierarchy of evidence:

* ``STORED`` — the task's own ``safety_axes``/``issue_type``, written at ingestion from
  real, structured data;
* ``DERIVED_REVIEW_SIGNAL`` — a keyword regex over the target's free text, used only
  because stored tags are absent for that category. The document says it "can produce a
  false positive on an unrelated mention of the same word", is "a selection aid, not a
  clinical claim", and is "never treated as equivalent to a physician's own judgment".

The selection order inside a tier used to be decided by string comparison of the ``origin``
field, so ``"DERIVED_REVIEW_SIGNAL" < "STORED"`` purely because D sorts before S. A keyword
hit in free text therefore outranked a curated stored safety axis in the same tier — the
weaker evidence won, by an accident of naming rather than by decision. Renaming the
constant would have silently reversed the order again.

The order is now an explicit ``_ORIGIN_RANK``. These tests pin it.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from clinical_engine.review_workbench.pilot_policy import (
    POLICY_NAME,
    TIERS,
    _ORIGIN_RANK,
    _sort_key,
    match_tiers,
    primary_rank,
    select_quota_capped,
)


@dataclass
class FakeTask:
    task_id: str
    safety_axes: tuple = ()
    issue_type: str = ""
    priority_score: int = 0


def test_policy_identity_is_stable() -> None:
    """Имя и состав ярусов — контракт с владельцем, менять его незаметно нельзя."""
    assert POLICY_NAME == "PHYSICIAN_PILOT_V1"
    assert [label for _tier, label in TIERS] == [
        "pediatric", "pregnancy", "renal", "severe_allergy",
        "missing_dose_or_unit", "unresolved_conflict", "source_mismatch",
    ]


# ── сила свидетельства внутри яруса ─────────────────────────────────────────


def test_stored_axis_outranks_a_keyword_hit_in_the_same_tier() -> None:
    """Кураторская сохранённая ось важнее попадания по ключевому слову."""
    stored = FakeTask("stored-axis", safety_axes=("pediatric",), priority_score=10)
    derived = FakeTask("keyword-only", priority_score=10)

    rank_stored = primary_rank(stored, {"indication": "отит"})
    rank_derived = primary_rank(derived, {"indication": "детский отит"})

    assert rank_stored[0] == rank_derived[0] == 1, "оба должны попасть в ярус pediatric"
    assert rank_stored[2] == "STORED"
    assert rank_derived[2] == "DERIVED_REVIEW_SIGNAL"

    selected = select_quota_capped([(rank_stored, stored), (rank_derived, derived)], 1)
    assert [t.task_id for t in selected] == ["stored-axis"], selected


def test_the_order_does_not_depend_on_input_order() -> None:
    """Детерминизм: перестановка входа не меняет выбор."""
    stored = FakeTask("stored-axis", safety_axes=("pediatric",), priority_score=10)
    derived = FakeTask("keyword-only", priority_score=10)
    rank_stored = primary_rank(stored, {"indication": "отит"})
    rank_derived = primary_rank(derived, {"indication": "детский отит"})

    forward = select_quota_capped([(rank_stored, stored), (rank_derived, derived)], 1)
    backward = select_quota_capped([(rank_derived, derived), (rank_stored, stored)], 1)
    assert [t.task_id for t in forward] == [t.task_id for t in backward] == ["stored-axis"]


def test_origin_rank_is_explicit_and_not_an_alphabetical_accident() -> None:
    """Порядок задан числом, а не сравнением строк.

    Проверка намеренно утверждает обратное алфавиту: строково
    ``DERIVED_REVIEW_SIGNAL`` < ``STORED``, но по силе свидетельства STORED первый.
    """
    assert _ORIGIN_RANK["STORED"] < _ORIGIN_RANK["DERIVED_REVIEW_SIGNAL"]
    assert "DERIVED_REVIEW_SIGNAL" < "STORED", (
        "предусловие: строковое сравнение даёт противоположный порядок — "
        "именно поэтому нужен явный ранг"
    )
    assert _ORIGIN_RANK["NONE"] > _ORIGIN_RANK["DERIVED_REVIEW_SIGNAL"]

    stored = FakeTask("s", safety_axes=("pediatric",))
    derived = FakeTask("d")
    key_stored = _sort_key((primary_rank(stored, {}), stored))
    key_derived = _sort_key((primary_rank(derived, {"indication": "детский отит"}), derived))
    assert key_stored < key_derived, (key_stored, key_derived)


def test_priority_score_still_decides_within_one_origin() -> None:
    """Внутри одного origin выигрывает более высокий priority_score."""
    high = FakeTask("hi-prio", safety_axes=("pediatric",), priority_score=99)
    low = FakeTask("lo-prio", safety_axes=("pediatric",), priority_score=1)

    selected = select_quota_capped(
        [(primary_rank(low, {}), low), (primary_rank(high, {}), high)], 1
    )
    assert [t.task_id for t in selected] == ["hi-prio"], selected


def test_more_matched_tiers_outrank_fewer_within_one_origin() -> None:
    """Задача, попавшая в большее число ярусов, идёт раньше при равном приоритете."""
    broad = FakeTask("broad", safety_axes=("pediatric", "pregnancy"), priority_score=5)
    narrow = FakeTask("narrow", safety_axes=("pediatric",), priority_score=5)

    rank_broad = primary_rank(broad, {})
    rank_narrow = primary_rank(narrow, {})
    assert rank_broad[0] == rank_narrow[0] == 1
    assert rank_broad[3] < rank_narrow[3], (rank_broad, rank_narrow)

    selected = select_quota_capped(
        [(rank_narrow, narrow), (rank_broad, broad)], 1
    )
    assert [t.task_id for t in selected] == ["broad"], selected


# ── происхождение сигнала ───────────────────────────────────────────────────


def test_a_keyword_match_is_never_labelled_stored() -> None:
    """Главное правило документа: производный сигнал не выдаётся за сохранённый."""
    task = FakeTask("kw", safety_axes=())
    for tier, label, origin in [
        (m.tier, m.label, m.origin) for m in match_tiers(task, {"indication": "детский отит"})
    ]:
        assert origin == "DERIVED_REVIEW_SIGNAL", (tier, label, origin)


def test_a_stored_axis_is_labelled_stored() -> None:
    task = FakeTask("st", safety_axes=("pediatric",))
    matches = match_tiers(task, {"indication": "отит"})
    assert [(m.tier, m.label, m.origin) for m in matches] == [(1, "pediatric", "STORED")]


def test_no_signal_gives_the_last_tier_and_no_match_label() -> None:
    task = FakeTask("none")
    assert match_tiers(task, {"indication": "обычный отит"}) == []
    tier, label, origin, _tiebreak, task_id = primary_rank(task, {"indication": "обычный отит"})
    assert (tier, label, origin, task_id) == (99, "no_owner_tier_match", "NONE", "none")


def test_issue_type_alone_reaches_the_dose_and_conflict_tiers() -> None:
    dose = FakeTask("dose", issue_type="DOSE_UNIT_GROUP")
    conflict = FakeTask("conflict", issue_type="CONFLICT_DOSE")
    assert [(m.tier, m.origin) for m in match_tiers(dose, {})] == [(5, "STORED")]
    assert [(m.tier, m.origin) for m in match_tiers(conflict, {})] == [(6, "STORED")]


# ── квоты ──────────────────────────────────────────────────────────────────


def test_one_numerous_tier_cannot_consume_the_whole_batch() -> None:
    """Требование фазы 6: ни один ярус не забирает всю выборку."""
    many = [
        FakeTask(f"ped-{i}", safety_axes=("pediatric",), priority_score=i) for i in range(20)
    ]
    few = [FakeTask(f"preg-{i}", safety_axes=("pregnancy",), priority_score=i) for i in range(2)]

    scored = [(primary_rank(t, {}), t) for t in many + few]
    selected = select_quota_capped(scored, 10)

    labels = []
    for task in selected:
        labels.append("pediatric" if task.task_id.startswith("ped") else "pregnancy")
    assert "pregnancy" in labels, f"малочисленный ярус вытеснен: {labels}"
    assert len(selected) == 10


def test_selection_never_exceeds_the_requested_count() -> None:
    tasks = [FakeTask(f"t{i}", safety_axes=("pediatric",)) for i in range(30)]
    scored = [(primary_rank(t, {}), t) for t in tasks]
    for count in (1, 3, 7, 30, 100):
        assert len(select_quota_capped(scored, count)) == min(count, 30), count


def test_no_task_is_selected_twice() -> None:
    tasks = [FakeTask(f"t{i}", safety_axes=("pediatric", "renal")) for i in range(10)]
    scored = [(primary_rank(t, {}), t) for t in tasks]
    selected = select_quota_capped(scored, 10)
    ids = [t.task_id for t in selected]
    assert len(ids) == len(set(ids)), ids


def test_an_empty_queue_selects_nothing() -> None:
    assert select_quota_capped([], 10) == []
