"""Triage of the DOSA-derived extended disease records into clinical categories.

Source-prover module only: it CLASSIFIES the builder/source-layer records for a
physician to review. It NEVER enables calculation, never hints at unblock, and
never attests (the P5.6/P6 physician gate is owner/physician only).

Categories are engineering-rough groupings of the underlying guideline topic, not
a medical decision. Rules are keyword-substring driven off the guideline name and
are deliberately coarse. A physician MUST re-review each record before any
calculation is ever enabled.

Artifact layout:
{
  schema_version, artifact_type 'DOSA_EXTENSION_TRIAGE', generated_by, created,
  categories: [{name, description, records:[{id, cr_id, name, topic}]}],
  note
}
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

ARTIFACT_TYPE = "DOSA_EXTENSION_TRIAGE"
SCHEMA_VERSION = "1.0.0"

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Category keyword rules, applied in order (first match wins). Values lowercased.
_RULES: list[tuple[str, str, list[str]]] = [
    (
        "congenital_cardiac_prophylaxis",
        "Врождённые пороки сердца — профилактика инфекционного эндокардита",
        [
            "трехпредсерд", "стеноз аорты", "дефект аортолегочн", "аортолегочной",
            "сердце", "порок", "перегородки",
        ],
    ),
    (
        "surgical_prophylaxis",
        "Периоперационная антибиотикопрофилактика (хирургическая)",
        [
            "грыж", "грыжа", "сколиоз", "тазового кольца", "таза", "бедренн",
            "коленного", "деформации стопы", "стопе", "катаракта", "кесарева",
            "связок", "пкс", "операци", "хирургическ", "родоразрешение",
            "перелом", "глазниц", "перелом",
        ],
    ),
    (
        "oncology",
        "Онкология (фебрильная нейтропения / профилактика ПЖП)",
        [
            "опухол", "гепатобластом", "нейробластом", "лейкоз", "лейкеми",
            "рак ", "рак_", "рака", "лимфом", "герминогенн",
        ],
    ),
    (
        "immunodeficiency_pjp",
        "Иммунодефицит / профилактика пневмоцистной пневмонии",
        [
            "иммунодефицит", "иммунной недостаточност", "иммунодефициты",
            "средиземноморск", "юношеский артрит", "аортоартериит", "системный склероз",
            "склероз", "ритуксимаб", "циклофосфамид",
        ],
    ),
    (
        "metabolic_genetic",
        "Метаболические / генетические (редкие) — амбулаторная анти-микробная поддержка",
        [
            "ацидеми", "ацидури", "кистозный фиброз", "муковисцидоз",
            "серповидно", "клеточн",
        ],
    ),
    (
        "infection",
        "Инфекции (классическое дозирование)",
        [
            "гидрав", "гидрад", "хориоамнионит", "лимфогранулём", "трихомониаз",
            "язвенный колит", "крон", "пневм", "пиодерми", "бартолин",
            "эритема", "эритемы", "менингит", "вентрикулит", "выкидыш",
            "аборт", "отравление грибам", "дерматит", "баланопостит",
            "кератит", "бронхит", "травма",
        ],
    ),
]

# Sub-atomic override: ids whose category _RULES would misclassify (last word).
_OVERRIDES: dict[str, str] = {
    "pnevmotsistnaia_pnevmoniia": "immunodeficiency_pjp",  # ВИЧ -> ПЖП prophylaxis
    "prisoedinenie_infektsii_pri_tkin": "immunodeficiency_pjp",  # ТКИН
    "otravlenie_gribami_soderzhashchimi_amanitin": "infection",  # аманитин токсин + бензилпенициллин
    "vykidysh_samoproizvolnyi_abort": "infection",
    "vnutricherepnye_gnoinye_oslozhneniia_meningit_ili_ventrikulit": "infection",  # ЧМТ + менингит/вентрикулит
}


def _guess_category(name: str, record_id: str) -> str:
    if record_id in _OVERRIDES:
        return _OVERRIDES[record_id]
    low = str(name).lower()
    for cat, _desc, kws in _RULES:
        if any(kw in low for kw in kws):
            return cat
    return "unclassified"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def build_triage(diseases_records: list[dict[str, Any]]) -> dict[str, Any]:
    categories: dict[str, dict[str, Any]] = {}
    for cat, desc, _kws in _RULES:
        categories[cat] = {"name": desc, "records": []}
    categories["unclassified"] = {"name": "Не классифицировано", "records": []}

    for rec in diseases_records:
        cat = _guess_category(
            str(rec.get("name", rec.get("id", ""))),
            str(rec.get("id", "")),
        )
        categories[cat]["records"].append(
            {
                "id": rec.get("id"),
                "cr_id": rec.get("cr_id"),
                "name": rec.get("name"),
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "generated_by": "dosa_extension_triage.py",
        "created": date.today().isoformat(),
        "scope_note": (
            "Инженерная классификация записей source-слоя по теме КР. НЕ является "
            "врачебным решением/аттестацией. Требует повторного врачебного ревью. "
            "Все записи остаются calculation_blocked=True до врачебного зерна."
        ),
        "categories": [{"key": k, **v} for k, v in categories.items() if v["records"]],
        "total": len(diseases_records),
    }


def _main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default=str(PROJECT_ROOT / "db" / "antibio_db.json"))
    p.add_argument("--extended", default=str(PROJECT_ROOT / "db" / "diseases" / "extended_dosa.json"),
                   help="Source-layer extension category file (the 46 records to triage).")
    p.add_argument("--output", required=True)
    args = p.parse_args(argv)

    ext = _read_json(Path(args.extended))
    target = ext.get("recommendations", [])

    artifact = build_triage(target)
    Path(args.output).write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(
        {"artifact_type": ARTIFACT_TYPE, "total": artifact["total"],
         "categories": {c["key"]: len(c["records"]) for c in artifact["categories"]}},
        ensure_ascii=False,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
