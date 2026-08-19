from src.pipeline.extraction.official_card_audit import (
    build_audit,
    build_registry_audit,
    build_exact_registry_audit,
    candidate_card_ids,
    compact_card,
)


def test_candidate_card_ids_prefers_latest_metadata_revision():
    inventory = {"rows": [
        {"declared_cr_id": "281", "latest_local_metadata": {"CodeVersion": "281_3"}},
        {"declared_cr_id": "281_3", "latest_local_metadata": None},
        {"declared_cr_id": "—", "latest_local_metadata": None},
    ]}
    assert candidate_card_ids(inventory) == ["281_3"]


def test_compact_card_excludes_large_document_body():
    card = compact_card({
        "id": "281_3", "code": 281, "version": 3,
        "name": "Инфекция мочевых путей", "apply_status": "Применяется",
        "apply_status_calculated": 1, "obj": {"sections": ["large"]},
        "NPC_approved": True,
    })
    assert card["source_url"].endswith("/281_3")
    assert card["npc_approved"] is True
    assert "obj" not in card


def test_build_audit_reports_failures_without_treating_them_as_verified():
    inventory = {"rows": [
        {"declared_cr_id": "10_5", "latest_local_metadata": None},
        {"declared_cr_id": "281_3", "latest_local_metadata": None},
    ]}

    def fetcher(card_id):
        if card_id == "10_5":
            raise OSError("offline")
        return {"id": card_id, "apply_status": "Применяется", "apply_status_calculated": 1}

    audit = build_audit(inventory, fetcher=fetcher, captured_at="2026-08-02T00:00:00Z")
    assert audit["requested_count"] == 2
    assert audit["verified_count"] == 1
    assert audit["applicable_count"] == 1
    assert audit["failures"] == [{"requested_id": "10_5", "error": "offline"}]


def test_registry_audit_detects_newer_current_revision():
    inventory = {"rows": [
        {"declared_cr_id": "281_2", "latest_local_metadata": None},
        {"declared_cr_id": "999_1", "latest_local_metadata": None},
    ]}
    registry = [{
        "Code": 281, "Version": 3, "CodeVersion": "281_3",
        "Name": "Инфекция мочевых путей", "Status": 0,
        "ApplyStatusCalculated": 1, "Mkbs": [{"MkbCode": "N10"}],
    }]
    audit = build_registry_audit(
        inventory,
        registry_fetcher=lambda: registry,
        captured_at="2026-08-02T00:00:00Z",
    )
    assert audit["verified_count"] == 1
    assert audit["revision_change_count"] == 1
    assert audit["cards"][0]["id"] == "281_3"
    assert audit["failures"][0]["requested_id"] == "999_1"


def test_exact_registry_audit_requires_each_requested_revision():
    inventory = {"rows": [
        {"declared_cr_id": "281_3", "latest_local_metadata": None},
        {"declared_cr_id": "999_1", "latest_local_metadata": None},
    ]}

    def fetcher(card_id):
        if card_id == "999_1":
            raise ValueError("not current")
        return {"Code": 281, "Version": 3, "CodeVersion": card_id,
                "ApplyStatusCalculated": 1}

    audit = build_exact_registry_audit(
        inventory, fetcher=fetcher, captured_at="2026-08-02T00:00:00Z"
    )
    assert audit["verified_count"] == 1
    assert audit["applicable_count"] == 1
    assert audit["failures"] == [{"requested_id": "999_1", "error": "not current"}]
