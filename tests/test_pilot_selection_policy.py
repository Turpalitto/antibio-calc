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
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

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


# ── сквозной словарь осей: queue_builder пишет, pilot_policy читает ───────────


@dataclass
class FakeRegimen:
    age_group: str = "adult"
    pregnancy: bool = False
    renal_adjustment: bool = False
    dose: object = 500
    unit: str = "мг"
    conflicts: tuple = ()
    source_pdf: str = "kr.pdf"
    source_page: int = 3
    source_quote: str = "цитата из КР"


# Каждая ось, которую выдаёт queue_builder._regimen_axes, и ярус, куда она обязана попасть
# по спецификации владельца в PHYSICIAN_PILOT_POLICY.md.
AXIS_TO_TIER = {
    "pediatric": (FakeRegimen(age_group="child"), 1),
    "pregnancy": (FakeRegimen(pregnancy=True), 2),
    "renal": (FakeRegimen(renal_adjustment=True), 3),
    "missing_dose": (FakeRegimen(dose=None), 5),
    "missing_unit": (FakeRegimen(unit=""), 5),
    "clinical_conflict": (FakeRegimen(conflicts=("c",)), 6),
    "source_mismatch": (FakeRegimen(source_pdf=""), 7),
}


@pytest.mark.parametrize("axis", sorted(AXIS_TO_TIER))
def test_every_axis_queue_builder_emits_reaches_its_tier(axis: str) -> None:
    """Ни одна сохранённая ось не должна теряться между двумя модулями.

    Ярус 5 по спецификации владельца — «missing dose OR unit», но раньше проверялись
    только ``missing_unit`` и ``issue_type``: режим без дозы, но с единицей получал ось
    ``missing_dose`` от ``queue_builder`` и уходил в ярус 99 «no_owner_tier_match».
    """
    from clinical_engine.review_workbench.queue_builder import _regimen_axes

    regimen, expected_tier = AXIS_TO_TIER[axis]
    axes = tuple(sorted(set(_regimen_axes(regimen))))
    assert axis in axes, f"queue_builder не выдал ось {axis}, получено {axes}"

    task = FakeTask("t", safety_axes=axes)
    tiers = [m.tier for m in match_tiers(task, {})]
    assert expected_tier in tiers, f"ось {axis} не попала в ярус {expected_tier}: {tiers}"
    assert all(m.origin == "STORED" for m in match_tiers(task, {}))


def test_a_regimen_with_no_dose_but_with_a_unit_is_not_left_unmatched() -> None:
    """Регрессия на конкретный случай: доза отсутствует, единица есть."""
    from clinical_engine.review_workbench.queue_builder import _regimen_axes

    axes = tuple(sorted(set(_regimen_axes(FakeRegimen(dose=None, unit="мг")))))
    assert axes == ("missing_dose",), axes

    task = FakeTask("no-dose", safety_axes=axes)
    tier, label, origin, _tiebreak, _task_id = primary_rank(task, {})
    assert (tier, label, origin) == (5, "missing_dose_or_unit", "STORED"), (tier, label, origin)


def test_the_only_axis_read_but_never_stored_is_the_documented_allergy_gap() -> None:
    """`severe_allergy` читается, но не сохраняется — и это задокументировано.

    ``PHYSICIAN_PILOT_POLICY.md``: сохранённых тегов аллергии в системе 0 из 9 153,
    поэтому ярус 4 опирается на ключевое слово. Любая ДРУГАЯ нечитаемая ось — дефект.
    """
    from clinical_engine.review_workbench.queue_builder import _regimen_axes

    emitted = set()
    for regimen, _tier in AXIS_TO_TIER.values():
        emitted |= set(_regimen_axes(regimen))

    # Что читает pilot_policy как сохранённые оси (по коду match_tiers).
    read_as_stored = {
        "pediatric", "pregnancy", "renal", "missing_unit", "missing_dose",
        "clinical_conflict", "source_mismatch",
    }
    unread = emitted - read_as_stored
    assert unread == set(), f"оси выдаются, но не читаются: {sorted(unread)}"

    # А ось аллергии queue_builder не выдаёт — ярус 4 живёт на ключевом слове.
    assert not any("allerg" in a for a in emitted)
    allergy_task = FakeTask("allergy", safety_axes=())
    derived = match_tiers(allergy_task, {"indication": "тяжёлая аллергия на пенициллин"})
    assert [(m.tier, m.origin) for m in derived] == [(4, "DERIVED_REVIEW_SIGNAL")], derived


# ── v1 и каноническая политика не должны разъезжаться ─────────────────────────


def _v1_module():
    import importlib

    return importlib.import_module("generate_pilot_review_batch")


def test_v1_script_shares_the_canonical_issue_type_sets() -> None:
    """Исторический скрипт v1 обязан брать наборы из канонического модуля.

    Раньше он объявлял собственные копии ``DOSE_ISSUE_TYPES`` и
    ``CONFLICT_ISSUE_TYPES``. Два независимых набора одной политики разъезжаются
    при первом же изменении — и это уже случилось с ярусом 5.
    """
    from clinical_engine.review_workbench.pilot_policy import (
        CONFLICT_ISSUE_TYPES,
        DOSE_ISSUE_TYPES,
    )

    v1 = _v1_module()
    assert v1.DOSE_ISSUE_TYPES is DOSE_ISSUE_TYPES
    assert v1.CONFLICT_ISSUE_TYPES is CONFLICT_ISSUE_TYPES


def test_v1_tier_table_agrees_with_the_canonical_match_tiers() -> None:
    """Таблица ярусов v1 даёт тот же результат, что ``match_tiers``.

    Проверяется на тех же семи осях: если одна из реализаций изменится,
    расхождение станет видимым.
    """
    from clinical_engine.review_workbench.queue_builder import _regimen_axes

    v1 = _v1_module()

    @dataclass
    class V1Task:
        task_id: str = "t"
        safety_axes: tuple = ()
        issue_type: str = ""
        priority_score: int = 0

    for axis, (regimen, expected_tier) in AXIS_TO_TIER.items():
        axes = tuple(sorted(set(_regimen_axes(regimen))))
        task = V1Task(safety_axes=axes)
        v1_matches = [
            rank for rank, _label, fn in v1.RANK_ORDER if fn(task, "")
        ]
        assert expected_tier in v1_matches, (
            f"ось {axis}: v1 не дал ярус {expected_tier}, получено {v1_matches}"
        )
        assert v1_matches == sorted(v1_matches), v1_matches


def test_v1_is_marked_superseded() -> None:
    """Читатель скрипта v1 должен сразу видеть, что канонический — v2."""
    source = (ROOT / "generate_pilot_review_batch.py").read_text(encoding="utf-8")
    header = source.split('"""')[1]
    assert "SUPERSEDED" in header, "в шапке v1 нет пометки о замене"
    assert "generate_pilot_review_batch_v2.py" in header


def test_the_documented_conflict_issue_types_are_forward_looking() -> None:
    """`CONFLICT_*` — коды из проектного документа, данных с ними пока нет.

    ``CLINICAL_DECISION_ENGINE_DESIGN.md`` предписывает поднимать ``CONFLICT_DOSE`` и
    ``CONFLICT_DURATION``; ярус 6 при этом живёт через сохранённую ось
    ``clinical_conflict``, поэтому отсутствие таких ``issue_type`` в данных не делает
    ветку мёртвой по сути — она защита на будущее.
    """
    from clinical_engine.review_workbench.pilot_policy import CONFLICT_ISSUE_TYPES

    assert CONFLICT_ISSUE_TYPES == {
        "CONFLICT_FIRST_LINE_DRUG", "CONFLICT_DOSE", "CONFLICT_DURATION",
    }

    # Ярус 6 достижим через ось, которую queue_builder действительно выдаёт.
    conflict = FakeTask("c", safety_axes=("clinical_conflict",))
    assert [(m.tier, m.origin) for m in match_tiers(conflict, {})] == [(6, "STORED")]

    # И через issue_type из проектного документа — тоже.
    forward = FakeTask("f", issue_type="CONFLICT_DURATION")
    assert [(m.tier, m.origin) for m in match_tiers(forward, {})] == [(6, "STORED")]
