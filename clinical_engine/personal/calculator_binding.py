"""Exact binding verification against the generated calculator database."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Any, Mapping
from .models import PersonalModeError

DEFAULT_CALCULATOR_DB = Path(__file__).resolve().parents[2] / "db" / "antibio_db.json"

def verified_binding(binding: Mapping[str, Any], db_path: str | Path = DEFAULT_CALCULATOR_DB) -> dict[str, Any]:
    raw, db = dict(binding), json.loads(Path(db_path).read_text(encoding="utf-8-sig"))
    disease = _one(db.get("recommendations", []), "id", raw.get("disease_id"), "disease")
    scenario = _one(disease.get("scenarios", []), "id", raw.get("scenario_id"), "scenario")
    lines = [x for x in scenario.get("lines", []) if x.get("line_number") == raw.get("line_number")]
    matches = []
    for line in lines:
        for drug in line.get("drugs", []):
            identity = drug.get("drug_ref") == raw.get("drug_ref") if raw.get("drug_ref") else drug.get("combo_ref") == raw.get("combo_ref")
            if identity and raw.get("route") in drug.get("route", []): matches.append((line, drug))
    if len(matches) != 1: raise PersonalModeError("CALCULATOR_BINDING_INVALID", "drug/route binding is not unique")
    line, drug = matches[0]
    regimens = drug.get("regimens", [])
    if raw.get("regimen_label") is not None:
        selected = [x for x in regimens if x.get("regimen_label") == raw["regimen_label"]]
        if len(selected) != 1: raise PersonalModeError("CALCULATOR_BINDING_INVALID", "regimen_label is not unique")
        regimen = selected[0]
    else:
        index = raw.get("regimen_index")
        if not isinstance(index, int) or index < 0 or index >= len(regimens): raise PersonalModeError("CALCULATOR_BINDING_INVALID", "regimen_index is invalid")
        regimen = regimens[index]
    projection = {"disease":{k:disease.get(k) for k in ("id","name","mkb10","cr_id","cr_year","source_url")},"scenario":{"id":scenario.get("id"),"age_group":scenario.get("age_group")},"line":{"line_number":line.get("line_number"),"line_label":line.get("line_label")},"drug":{k:drug.get(k) for k in ("drug_ref","combo_ref","route")},"regimen":regimen}
    canonical = json.dumps(projection, ensure_ascii=False, sort_keys=True, separators=(",",":"), allow_nan=False)
    raw["calculator_regimen_sha256"] = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
    return raw

def _one(items:list[dict[str,Any]], key:str, value:Any, label:str)->dict[str,Any]:
    matches=[x for x in items if x.get(key)==value]
    if len(matches)!=1: raise PersonalModeError("CALCULATOR_BINDING_INVALID", f"{label} binding is not unique")
    return matches[0]
