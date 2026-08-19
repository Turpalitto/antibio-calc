import json

from src.pipeline.extraction.sync_official_source_metadata import (
    apply_updates,
    planned_updates,
    title_compatible,
)


def _fixtures():
    inventory = {"rows": [{
        "disease_id": "aom", "declared_cr_id": "314_2",
        "latest_local_metadata": {"CodeVersion": "314_2"},
    }]}
    audit = {"cards": [{
        "requested_id": "314_2", "id": "314_3",
        "name": "Отит средний острый",
        "publish_date": "2024-10-28T00:00:00",
        "source_url": "https://cr.minzdrav.gov.ru/view-cr/314_3",
        "apply_status_calculated": 1,
    }]}
    return inventory, audit


def test_planned_update_changes_only_source_identity_fields():
    inventory, audit = _fixtures()
    diseases = [{
        "id": "aom", "name": "Острый средний отит у взрослых", "cr_id": "314_2", "cr_year": 2022,
        "cr_updated": "2022", "source_url": "old", "calculation_blocked": True,
        "scenarios": [{"id": "unchanged"}],
    }]
    changes = planned_updates(diseases, inventory, audit)
    assert changes[0]["after"] == {
        "cr_id": "314_3", "cr_year": 2024, "cr_updated": "2024-10-28",
        "source_url": "https://cr.minzdrav.gov.ru/view-cr/314_3",
    }
    assert diseases[0]["scenarios"] == [{"id": "unchanged"}]


def test_apply_updates_preserves_clinical_and_blocking_fields(tmp_path):
    inventory, audit = _fixtures()
    path = tmp_path / "respiratory.json"
    path.write_text(json.dumps({"recommendations": [{
        "id": "aom", "name": "Острый средний отит у взрослых", "cr_id": "314_2", "cr_year": 2022,
        "cr_updated": "2022", "source_url": "old", "calculation_blocked": True,
        "scenarios": [{"dose": 50}],
    }]}), encoding="utf-8")
    changes = apply_updates(tmp_path, inventory, audit)
    updated = json.loads(path.read_text(encoding="utf-8"))["recommendations"][0]
    assert len(changes) == 1
    assert updated["calculation_blocked"] is True
    assert updated["scenarios"] == [{"dose": 50}]
    assert updated["cr_id"] == "314_3"


def test_title_compatibility_rejects_numeric_code_collision():
    assert not title_compatible("omphalitis", "Омфалит новорождённых", "Туберкулез у взрослых")
    assert not title_compatible("diphtheria", "Дифтерия", "Регматогенная отслойка сетчатки")
    assert title_compatible("mastitis_puerperal", "Послеродовой мастит", "Воспалительные заболевания молочных желез")
