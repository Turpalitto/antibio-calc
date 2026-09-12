"""Tests for importing source-backed clinical findings into review storage.

``issue_registry.import_clinical_data_issues`` writes rows into permanent review storage,
and every row carries a provenance stamp taken from the audit document's own
``meta.generated_at`` — the time the finding was detected, not the time it was imported.

Before this change that stamp fell back to an empty string when the field was missing:

    timestamp = str(document.get("meta", {}).get("generated_at") or "")

Nothing anywhere in the repository validated it (verified by grepping every ``raise`` and
``assert`` that mentions ``generated_at`` — there were none), so a findings file without the
field imported successfully and produced 4,506-plus clinical findings that could no longer
be tied to the audit run that produced them. The refusal now lives in the function that
writes the rows, so every path into storage satisfies the invariant, including a direct one.

These tests drive the real ``ReviewStore``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clinical_engine.review_workbench.issue_registry import import_clinical_data_issues
from clinical_engine.review_workbench.storage import ReviewStore


def _write(path: Path, issues: list[dict], meta: dict | None = None) -> Path:
    document: dict = {"issues": issues}
    if meta is not None:
        document["meta"] = meta
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


SAMPLE_ISSUES = [
    {
        "issue_id": "i1",
        "regimen_id": "r1",
        "guideline_id": "1269",
        "issue_code": "DOSE_NOT_EXTRACTED",
        "severity": "high",
        "description": "Доза не извлечена",
        "kr_quote": "цитата из КР",
        "verification": "clinical_data_audit",
    },
    {
        "issue_id": "i2",
        "guideline_id": "858_1",
        "problem_type": "OTHER_PROBLEM",
        "severity": "low",
    },
]

STAMP = "2026-07-01T10:00:00Z"


# ── отказ без происхождения ──────────────────────────────────────────────────


def test_a_document_without_generated_at_is_refused(tmp_path: Path) -> None:
    """Без meta.generated_at находку нельзя привязать к аудиту, который её нашёл."""
    source = _write(tmp_path / "no_meta.json", SAMPLE_ISSUES)
    with ReviewStore(tmp_path / "store.sqlite") as store:
        with pytest.raises(ValueError, match="missing meta.generated_at"):
            import_clinical_data_issues(store, source)
        assert store.list_issues(limit=10) == [], "отказ должен предшествовать записи"


def test_an_empty_or_blank_stamp_is_refused_too(tmp_path: Path) -> None:
    """Пустая строка и строка из пробелов — то же отсутствие, а не значение."""
    for name, meta in (
        ("empty", {"generated_at": ""}),
        ("blank", {"generated_at": "   "}),
    ):
        source = _write(tmp_path / f"{name}.json", SAMPLE_ISSUES, meta)
        with ReviewStore(tmp_path / f"{name}.sqlite") as store:
            with pytest.raises(ValueError, match="missing meta.generated_at"):
                import_clinical_data_issues(store, source)


def test_the_error_names_the_offending_file(tmp_path: Path) -> None:
    """В сообщении должно быть имя файла — иначе непонятно, что чинить."""
    source = _write(tmp_path / "findings_without_stamp.json", SAMPLE_ISSUES)
    with ReviewStore(tmp_path / "store.sqlite") as store:
        with pytest.raises(ValueError, match="findings_without_stamp.json"):
            import_clinical_data_issues(store, source)


# ── нормальный импорт ────────────────────────────────────────────────────────


def test_every_imported_issue_carries_the_audit_stamp(tmp_path: Path) -> None:
    """Штамп берётся из документа, а не из времени импорта."""
    source = _write(tmp_path / "ok.json", SAMPLE_ISSUES, {"generated_at": STAMP})
    with ReviewStore(tmp_path / "store.sqlite") as store:
        result = import_clinical_data_issues(store, source)
        issues = store.list_issues(limit=10)

    assert result == {"source": 2, "added": 2}, result
    assert len(issues) == 2
    for issue in issues:
        assert issue["timestamp"] == STAMP, issue["issue_id"]


def test_reimporting_the_same_file_adds_nothing(tmp_path: Path) -> None:
    """Импорт идемпотентен: повторный прогон не дублирует находки."""
    source = _write(tmp_path / "ok.json", SAMPLE_ISSUES, {"generated_at": STAMP})
    with ReviewStore(tmp_path / "store.sqlite") as store:
        assert import_clinical_data_issues(store, source)["added"] == 2
        assert import_clinical_data_issues(store, source)["added"] == 0
        assert len(store.list_issues(limit=10)) == 2


def test_the_whole_payload_is_kept_for_the_reviewer(tmp_path: Path) -> None:
    """Исходная запись сохраняется целиком — ревьюеру нужны все поля."""
    source = _write(tmp_path / "ok.json", SAMPLE_ISSUES, {"generated_at": STAMP})
    with ReviewStore(tmp_path / "store.sqlite") as store:
        import_clinical_data_issues(store, source)
        issue = next(i for i in store.list_issues(limit=10) if i["issue_id"] == "i1")

    assert issue["payload"]["kr_quote"] == "цитата из КР"
    assert issue["page_cell_provenance"] == {"source_quote": "цитата из КР"}
    assert issue["status"] == "PENDING"
    assert issue["reviewer"] == ""
    assert issue["resolution"] == ""


# ── разрешения полей ─────────────────────────────────────────────────────────


def test_severity_is_uppercased_into_the_stored_vocabulary(tmp_path: Path) -> None:
    source = _write(tmp_path / "ok.json", SAMPLE_ISSUES, {"generated_at": STAMP})
    with ReviewStore(tmp_path / "store.sqlite") as store:
        import_clinical_data_issues(store, source)
        by_id = {i["issue_id"]: i for i in store.list_issues(limit=10)}

    assert by_id["i1"]["severity"] == "HIGH"
    assert by_id["i2"]["severity"] == "LOW"


def test_a_missing_severity_defaults_to_medium(tmp_path: Path) -> None:
    source = _write(tmp_path / "ok.json", [{"issue_id": "i3"}], {"generated_at": STAMP})
    with ReviewStore(tmp_path / "store.sqlite") as store:
        import_clinical_data_issues(store, source)
        assert store.list_issues(limit=10)[0]["severity"] == "MEDIUM"


def test_category_falls_back_through_issue_code_then_problem_type(tmp_path: Path) -> None:
    source = _write(tmp_path / "ok.json", SAMPLE_ISSUES, {"generated_at": STAMP})
    with ReviewStore(tmp_path / "store.sqlite") as store:
        import_clinical_data_issues(store, source)
        by_id = {i["issue_id"]: i for i in store.list_issues(limit=10)}

    assert by_id["i1"]["category"] == "DOSE_NOT_EXTRACTED"
    assert by_id["i2"]["category"] == "OTHER_PROBLEM"


def test_category_defaults_to_other_when_nothing_is_stated(tmp_path: Path) -> None:
    source = _write(tmp_path / "ok.json", [{"issue_id": "i4"}], {"generated_at": STAMP})
    with ReviewStore(tmp_path / "store.sqlite") as store:
        import_clinical_data_issues(store, source)
        assert store.list_issues(limit=10)[0]["category"] == "OTHER"


def test_object_id_prefers_the_regimen_then_the_guideline(tmp_path: Path) -> None:
    """Идентификатор объекта: regime_id, иначе guideline_id, иначе issue_id."""
    source = _write(tmp_path / "ok.json", SAMPLE_ISSUES, {"generated_at": STAMP})
    with ReviewStore(tmp_path / "store.sqlite") as store:
        import_clinical_data_issues(store, source)
        by_id = {i["issue_id"]: i for i in store.list_issues(limit=10)}

    assert by_id["i1"]["object_id"] == "r1"
    assert by_id["i2"]["object_id"] == "858_1"


def test_an_issue_with_no_ids_falls_back_to_its_own_id(tmp_path: Path) -> None:
    source = _write(tmp_path / "ok.json", [{"issue_id": "i5"}], {"generated_at": STAMP})
    with ReviewStore(tmp_path / "store.sqlite") as store:
        import_clinical_data_issues(store, source)
        assert store.list_issues(limit=10)[0]["object_id"] == "i5"


def test_the_source_field_records_the_guideline(tmp_path: Path) -> None:
    source = _write(tmp_path / "ok.json", SAMPLE_ISSUES, {"generated_at": STAMP})
    with ReviewStore(tmp_path / "store.sqlite") as store:
        import_clinical_data_issues(store, source)
        by_id = {i["issue_id"]: i for i in store.list_issues(limit=10)}

    assert by_id["i1"]["source"] == "1269"
    assert by_id["i2"]["source"] == "858_1"


def test_a_missing_description_gets_a_reviewable_placeholder(tmp_path: Path) -> None:
    source = _write(tmp_path / "ok.json", [{"issue_id": "i6"}], {"generated_at": STAMP})
    with ReviewStore(tmp_path / "store.sqlite") as store:
        import_clinical_data_issues(store, source)
        issue = store.list_issues(limit=10)[0]
    assert issue["clinical_impact"] == "Requires clinical review"
    assert issue["detected_by"] == "clinical_data_audit"


# ── формат входного файла ────────────────────────────────────────────────────


def test_a_bom_prefixed_file_is_accepted(tmp_path: Path) -> None:
    """Документы пишутся с BOM; чтение идёт через utf-8-sig."""
    source = tmp_path / "bom.json"
    source.write_text(
        json.dumps({"meta": {"generated_at": STAMP}, "issues": SAMPLE_ISSUES}),
        encoding="utf-8-sig",
    )
    with ReviewStore(tmp_path / "store.sqlite") as store:
        assert import_clinical_data_issues(store, source)["added"] == 2


def test_a_document_with_no_issues_imports_nothing_without_error(tmp_path: Path) -> None:
    source = _write(tmp_path / "empty.json", [], {"generated_at": STAMP})
    with ReviewStore(tmp_path / "store.sqlite") as store:
        assert import_clinical_data_issues(store, source) == {"source": 0, "added": 0}
