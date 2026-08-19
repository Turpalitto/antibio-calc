"""Synchronize calculator source identity from an official-card audit.

Only source ID, year/date and URL are updated.  Calculation blocking and all
clinical regimen fields are deliberately untouched.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence


SOURCE_FIELDS = ("cr_id", "cr_year", "cr_updated", "source_url")
_TITLE_STOP_PREFIXES = {
    "инфек", "забол", "взрос", "детей", "детск", "остры", "хрони",
    "лечен", "профи", "орган", "систе",
}
_TITLE_ALIASES = {
    "mastitis_puerperal": ("молочн",),
    "pid": ("тазов",),
    "h_pylori": ("язвен",),
    "cap_child": ("пневм",),
    "postpartum_endometritis": ("после",),
}


def title_compatible(disease_id: str, disease_name: str, card_name: str) -> bool:
    def prefixes(value: str) -> set[str]:
        words = re.findall(r"[a-zа-яё]+", value.casefold().replace("ё", "е"))
        return {
            word[:5] for word in words if len(word) >= 5 and word[:5] not in _TITLE_STOP_PREFIXES
        }

    card_prefixes = prefixes(card_name)
    if prefixes(disease_name).intersection(card_prefixes):
        return True
    return any(alias in card_name.casefold().replace("ё", "е") for alias in _TITLE_ALIASES.get(disease_id, ()))


def planned_updates(
    diseases: Sequence[Mapping[str, Any]],
    inventory: Mapping[str, Any],
    official_audit: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rows = {str(row.get("disease_id")): row for row in inventory.get("rows", [])}
    cards = {
        str(card.get("requested_id") or card.get("id")): card
        for card in official_audit.get("cards", [])
        if card.get("apply_status_calculated") == 1
    }
    changes: list[dict[str, Any]] = []
    for disease in diseases:
        disease_id = str(disease.get("id") or "")
        row = rows.get(disease_id)
        if not row:
            continue
        metadata = row.get("latest_local_metadata") or {}
        requested_id = str(metadata.get("CodeVersion") or row.get("declared_cr_id") or "")
        card = cards.get(requested_id)
        if not card:
            continue
        if not title_compatible(disease_id, str(disease.get("name") or ""), str(card.get("name") or "")):
            continue
        publish_date = str(card.get("publish_date") or "")
        desired = {
            "cr_id": str(card["id"]),
            "cr_year": int(publish_date[:4]) if len(publish_date) >= 4 else disease.get("cr_year"),
            "cr_updated": publish_date[:10] if len(publish_date) >= 10 else disease.get("cr_updated"),
            "source_url": str(card["source_url"]),
        }
        before = {field: disease.get(field) for field in SOURCE_FIELDS}
        if before != desired:
            changes.append({"disease_id": disease_id, "before": before, "after": desired})
    return changes


def apply_updates(
    disease_dir: str | Path,
    inventory: Mapping[str, Any],
    official_audit: Mapping[str, Any],
) -> list[dict[str, Any]]:
    all_changes: list[dict[str, Any]] = []
    for path in sorted(Path(disease_dir).glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        diseases = payload.get("recommendations", [])
        changes = planned_updates(diseases, inventory, official_audit)
        if not changes:
            continue
        by_id = {item["disease_id"]: item["after"] for item in changes}
        for disease in diseases:
            desired = by_id.get(str(disease.get("id") or ""))
            if desired:
                disease.update(desired)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        all_changes.extend({**item, "file": str(path)} for item in changes)
    return all_changes


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync verified official source metadata")
    parser.add_argument("--disease-dir", required=True)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--official-audit", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    inventory = json.loads(Path(args.inventory).read_text(encoding="utf-8"))
    audit = json.loads(Path(args.official_audit).read_text(encoding="utf-8"))
    if args.apply:
        changes = apply_updates(args.disease_dir, inventory, audit)
    else:
        changes = []
        for path in sorted(Path(args.disease_dir).glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            changes.extend(
                {**item, "file": str(path)}
                for item in planned_updates(payload.get("recommendations", []), inventory, audit)
            )
    report = {
        "artifact_type": "OFFICIAL_SOURCE_METADATA_SYNC",
        "schema_version": "1.0.0",
        "applied": bool(args.apply),
        "change_count": len(changes),
        "changes": changes,
        "warning": "No clinical regimen or calculation status is modified.",
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"applied": report["applied"], "changes": len(changes)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
