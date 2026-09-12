"""Tests for the review-workbench role policy that is actually enforced.

``clinical_engine/review_workbench/permissions.py`` used to declare a ``PERMISSIONS``
matrix and a ``require()`` helper under the docstring "Administrators cannot approve
medicine". Nothing in the repository imported it — not the service, not the API, not the
package ``__init__``. The policy was enforced instead by two other places:

* ``service._SINGLE_ROLE_ACTIONS`` — actions with exactly one legitimate acting role, so a
  reviewer cannot reuse a role they legitimately hold to perform someone else's action;
* ``reviewer_registry.validate_reviewer_action`` + ``CLINICAL_ACTIONS`` — identity, role,
  scope and credential checks, including the rule that an administrator may not perform a
  clinical action.

So the dead file was not merely redundant, it was wrong about the action vocabulary: it
listed ``claim_first``, ``claim_second`` and ``administer``, none of which the service ever
validates (the service uses ``claim``), and it omitted ``qa_signoff``, ``assign`` and
``view_packet``, which it does. Wiring it in would have denied ``qa_signoff`` to everyone.

These tests pin the policy that is really enforced, so the statement "administrators cannot
approve medicine" survives as an executable check rather than as a file no one reads.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from clinical_engine.review_workbench.models import ReviewRole, TargetType
from clinical_engine.review_workbench.reviewer_registry import (
    ADMIN_CLINICAL_ACTION_FORBIDDEN,
    CLINICAL_ACTIONS,
    ReviewerRegistry,
)
from clinical_engine.review_workbench.service import ReviewService

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "clinical_engine" / "review_workbench" / "service.py"


def _validated_actions() -> set[str]:
    """Действия, которые service.py действительно проверяет через _validate()."""
    source = SERVICE.read_text(encoding="utf-8")
    return set(re.findall(r'self\._validate\([^)]*?,\s*"([a-z_]+)"\)', source))


def _registry(tmp_path: Path) -> ReviewerRegistry:
    registry = ReviewerRegistry(tmp_path / "reviewers.sqlite")
    registry.register(
        reviewer_id="admin-1",
        display_name="Администратор",
        professional_role="administrator",
        organisation="Клиника",
        authorised_scope=(ReviewRole.ADMINISTRATOR,),
        registered_at="2026-01-01T00:00:00+00:00",
        registered_by="owner",
    )
    return registry


# ── политика, которая действительно применяется ──────────────────────────────


def test_administrator_is_forbidden_from_every_clinical_action(tmp_path: Path) -> None:
    """Администратор не утверждает лекарства — ни по одному клиническому действию.

    Это и была формулировка в удалённом мёртвом файле. Здесь она проверяется
    поведением, а не декларацией.
    """
    registry = _registry(tmp_path)
    assert CLINICAL_ACTIONS, "CLINICAL_ACTIONS не должен быть пустым"

    denied = {}
    for action in sorted(CLINICAL_ACTIONS):
        result = registry.validate_reviewer_action(
            "admin-1", ReviewRole.ADMINISTRATOR, TargetType.CLINICAL_REGIMEN, action
        )
        denied[action] = (result.allowed, result.reason_code)

    assert all(not allowed for allowed, _ in denied.values()), denied
    assert {code for _, code in denied.values()} == {ADMIN_CLINICAL_ACTION_FORBIDDEN}, denied


def test_administrator_may_still_add_notes_and_view(tmp_path: Path) -> None:
    """Запрет касается клинических действий, а не административных."""
    registry = _registry(tmp_path)
    for action in ("add_note", "view_packet"):
        assert action not in CLINICAL_ACTIONS, f"{action} не должно быть клиническим действием"


def test_every_validated_action_is_classified() -> None:
    """Каждое проверяемое действие отнесено к клиническим или к служебным.

    Действие, которого нет ни там, ни там, означало бы незакрытую политику.
    """
    administrative = {"assign", "claim", "request_adjudication", "add_note", "view_packet"}
    actions = _validated_actions()

    assert actions, "service.py должен вызывать _validate()"
    unclassified = actions - CLINICAL_ACTIONS - administrative
    assert unclassified == set(), f"действия вне классификации: {sorted(unclassified)}"


def test_single_role_actions_map_to_the_expected_role() -> None:
    """Действия с единственной законной ролью закреплены явно.

    Без этого рецензент А мог бы вызвать adjudicate(), передав role=REVIEWER_A —
    роль, на которую он законно зарегистрирован.
    """
    expected = {
        "submit_first": ReviewRole.REVIEWER_A,
        "submit_second": ReviewRole.REVIEWER_B,
        "adjudicate": ReviewRole.ADJUDICATOR,
        "qa_signoff": ReviewRole.MEDICAL_QA_LEAD,
        "close": ReviewRole.MEDICAL_QA_LEAD,
        "waive": ReviewRole.MEDICAL_QA_LEAD,
    }
    assert ReviewService._SINGLE_ROLE_ACTIONS == expected, ReviewService._SINGLE_ROLE_ACTIONS


def test_every_single_role_action_is_also_a_clinical_action() -> None:
    """Действие с единственной ролью обязано быть клиническим.

    Иначе администратор прошёл бы проверку реестра, а карта единственных ролей
    была бы единственной преградой.
    """
    missing = set(ReviewService._SINGLE_ROLE_ACTIONS) - CLINICAL_ACTIONS
    assert missing == set(), f"не клинические, но с единственной ролью: {sorted(missing)}"


def test_the_dead_permission_matrix_is_gone() -> None:
    """Мёртвая матрица удалена и не должна вернуться незамеченной.

    Она была неверна в словаре действий: ``claim_first``/``claim_second``/``administer``
    не проверяются сервисом (он использует ``claim``), а ``qa_signoff``, ``assign`` и
    ``view_packet`` в ней отсутствовали. Подключение такой матрицы запретило бы
    ``qa_signoff`` всем.
    """
    assert not (ROOT / "clinical_engine" / "review_workbench" / "permissions.py").exists()

    source = SERVICE.read_text(encoding="utf-8")
    for name in ("claim_first", "claim_second", "administer"):
        assert f'"{name}"' not in source, f"{name} не должно появляться в service.py"

    for name in ("qa_signoff", "assign", "view_packet"):
        assert name in _validated_actions(), f"{name} должно проверяться сервисом"


def test_registry_rejects_an_unregistered_reviewer_before_any_role_check(tmp_path: Path) -> None:
    """Проверка идёт до ролевой: незарегистрированный не проходит ни в одной роли."""
    registry = ReviewerRegistry(tmp_path / "empty.sqlite")
    for role in ReviewRole:
        result = registry.validate_reviewer_action(
            "ghost", role, TargetType.CLINICAL_REGIMEN, "close"
        )
        assert not result.allowed, role


def test_role_must_be_in_the_reviewers_authorised_scope(tmp_path: Path) -> None:
    """Роль обязана входить в разрешённый объём записи рецензента."""
    registry = _registry(tmp_path)
    registry.register(
        reviewer_id="rev-a",
        display_name="Рецензент А",
        professional_role="physician",
        organisation="Клиника",
        authorised_scope=(ReviewRole.REVIEWER_A,),
        registered_at="2026-01-01T00:00:00+00:00",
        registered_by="owner",
    )

    own = registry.validate_reviewer_action(
        "rev-a", ReviewRole.REVIEWER_A, TargetType.CLINICAL_REGIMEN, "submit_first"
    )
    foreign = registry.validate_reviewer_action(
        "rev-a", ReviewRole.ADJUDICATOR, TargetType.CLINICAL_REGIMEN, "adjudicate"
    )
    assert own.allowed, (own.allowed, own.reason_code)
    assert not foreign.allowed, foreign.allowed
    assert foreign.reason_code == "ROLE_NOT_AUTHORISED", foreign.reason_code
