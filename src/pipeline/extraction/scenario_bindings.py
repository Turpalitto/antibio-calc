"""Bind calculator treatment scenarios to verified dose-table rows from regimen candidate specs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Sequence

ARTIFACT_TYPE = "SCENARIO_DOSE_TABLE_BINDINGS"
SCHEMA_VERSION = "1.0.0"
BINDING_VERSION = "scenario-dose-row-1"
SCENARIO_LINKAGE_BLOCKER = "DOSE_TABLE_NOT_LINKED_TO_TREATMENT_SCENARIO"

ATC_TO_DRUG_REF = {
    "J01CA04": "amoxicillin",
    "J01CR01": "ampicillin_sulbactam",
    "J01CR02": "amoxiclav",
    "J01CR05": "piperacillin_tazobactam",
    "J01DD04": "ceftriaxone",
    "J01FA09": "clarithromycin",
    "J01FA10": "azithromycin",
    "J01FF01": "clindamycin",
    "J01MA12": "levofloxacin",
    "J01MA14": "moxifloxacin",
}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha256_pin(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _one(items: list[dict[str, Any]], key: str, value: Any, label: str) -> dict[str, Any]:
    matches = [x for x in items if x.get(key) == value]
    if len(matches) != 1:
        raise ValueError(f"{label} is not unique for {key}={value!r}")
    return matches[0]


def build_binding_artifact(db: dict[str, Any], spec: dict[str, Any], disease_id: str, created: str) -> dict[str, Any]:
    disease = _one(list(db.get("recommendations", [])), "id", disease_id, "disease")
    if not disease.get("calculation_blocked"):
        raise ValueError(f"{disease_id}: calculation must stay blocked")
    cr_id = str(disease.get("cr_id") or "")
    if not cr_id or spec.get("guideline_id") != cr_id:
        raise ValueError(f"{disease_id}: spec guideline_id {spec.get('guideline_id')!r} != disease cr_id {cr_id!r}")
    bindings: list[dict[str, Any]] = []
    for scenario in disease.get("scenarios", []):
        for line in scenario.get("lines", []):
            for drug in line.get("drugs", []):
                drug_ref = drug.get("drug_ref")
                if not drug_ref:
                    raise ValueError(f"{disease_id}/{scenario.get('id')}: drug_ref missing")
                rows = [row for row in spec.get("row_groups", []) if ATC_TO_DRUG_REF.get(row.get("atc")) == drug_ref]
                exact = [row for row in rows if "ATC_FOR_COMBINATION_NOT_EXACT" not in (row.get("blocking_reasons") or [])]
                candidates = exact or rows
                if len(candidates) != 1:
                    raise ValueError(f"{disease_id}/{scenario.get('id')}/{drug_ref}: dose-table row is not unique ({len(candidates)} candidates)")
                row_index = spec["row_groups"].index(candidates[0])
                for regimen_index in range(len(drug.get("regimens", []))):
                    bindings.append({
                        "scenario_id": scenario.get("id"),
                        "line_number": line.get("line_number"),
                        "drug_ref": drug_ref,
                        "regimen_index": regimen_index,
                        "spec_row_index": row_index,
                    })
    if not bindings:
        raise ValueError(f"{disease_id}: no bindings produced")
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "disease_id": disease_id,
        "cr_id": cr_id,
        "created": created,
        "binding_version": BINDING_VERSION,
        "calculation_blocked": True,
        "expected_disease_sha256": _sha256_pin(disease),
        "expected_spec_row_groups_sha256": _sha256_pin(spec.get("row_groups", [])),
        "bindings": bindings,
    }


def _first_int(value: Any) -> int | None:
    if value is None:
        return None
    match = re.search(r"\d+", str(value))
    return int(match.group()) if match else None


def _linkage(scenario: dict[str, Any], drug: dict[str, Any], regimen: dict[str, Any], row: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    blockers = list(row.get("blocking_reasons") or [])
    routes = list(drug.get("route") or [])
    if {"MULTIPLE_ROUTES", "MULTIPLE_DOSE_ROUTE_OPTIONS"} & set(blockers):
        route_status = "AMBIGUOUS"
    elif len(routes) == 1:
        route_status = "LINKED"
    else:
        route_status = "NOT_RECORDED"
    row_duration = row.get("duration")
    spec_duration = spec.get("duration")
    calc_duration = regimen.get("duration_days")
    if row_duration:
        duration_status = "ROW"
    elif spec_duration:
        duration_status = "GLOBAL_SPEC"
    else:
        duration_status = "NOT_SPECIFIED"
    duration_review = (
        row_duration is not None
        and calc_duration is not None
        and _first_int(calc_duration) != _first_int(row_duration)
    )
    if scenario.get("age_group") == "adult":
        age_weight_status = "GUIDELINE_SCOPE_ADULT"
    else:
        age_weight_status = "POPULATION_SCOPE_REVIEW"
        if any(str(b).startswith("MULTIPLE_") and str(b).endswith("_STRATA") for b in blockers):
            age_weight_status = "MULTIPLE_STRATA_REVIEW"
        elif row.get("population_constraints"):
            age_weight_status = "CONSTRAINTS_PRESENT_REVIEW"
        else:
            age_weight_status = "NOT_CONSTRAINED"
    remaining = [b for b in blockers if b != SCENARIO_LINKAGE_BLOCKER]
    severity_status = "DOSE_TABLE_NOT_STRATIFIED"
    unblock_eligible = (
        not remaining
        and severity_status == "LINKED"
        and route_status == "LINKED"
        and age_weight_status == "GUIDELINE_SCOPE_ADULT"
        and not duration_review
    )
    return {
        "severity": severity_status,
        "route": route_status,
        "duration": duration_status,
        "age_weight": age_weight_status,
        "duration_review_required": duration_review,
        "remaining_blockers": remaining,
        "unblock_eligible": unblock_eligible,
    }


def verify_scenario_bindings(db_path: str | Path, bindings_dir: str | Path, specs_dir: str | Path) -> dict[str, Any]:
    db = json.loads(Path(db_path).read_text(encoding="utf-8-sig"))
    artifacts = {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(Path(bindings_dir).glob("*.json"))
    }
    if not artifacts:
        raise ValueError(f"{bindings_dir}: no binding artifacts found")
    reports: list[dict[str, Any]] = []
    total_bindings = 0
    for name, artifact in artifacts.items():
        if artifact.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(f"{name}: unsupported schema_version {artifact.get('schema_version')!r}")
        if artifact.get("artifact_type") != ARTIFACT_TYPE:
            raise ValueError(f"{name}: unsupported artifact_type {artifact.get('artifact_type')!r}")
        if artifact.get("binding_version") != BINDING_VERSION:
            raise ValueError(f"{name}: unsupported binding_version {artifact.get('binding_version')!r}")
        if artifact.get("calculation_blocked") is not True:
            raise ValueError(f"{name}: calculation_blocked must stay true")
        disease = _one(list(db.get("recommendations", [])), "id", artifact.get("disease_id"), f"{name}: disease")
        if not disease.get("calculation_blocked"):
            raise ValueError(f"{name}: disease {artifact.get('disease_id')!r} must stay calculation-blocked")
        cr_id = str(disease.get("cr_id") or "")
        if artifact.get("cr_id") != cr_id:
            raise ValueError(f"{name}: cr_id {artifact.get('cr_id')!r} != disease cr_id {cr_id!r}")
        spec_path = Path(specs_dir) / f"{cr_id}.json"
        if not spec_path.is_file():
            raise ValueError(f"{name}: spec {spec_path} is missing")
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        if spec.get("guideline_id") != cr_id:
            raise ValueError(f"{name}: spec guideline_id {spec.get('guideline_id')!r} != cr_id {cr_id!r}")
        if artifact.get("expected_disease_sha256") != _sha256_pin(disease):
            raise ValueError(f"{name}: calculator disease record changed since binding was created")
        if artifact.get("expected_spec_row_groups_sha256") != _sha256_pin(spec.get("row_groups", [])):
            raise ValueError(f"{name}: spec row_groups changed since binding was created")
        row_groups = list(spec.get("row_groups", []))
        seen: set[tuple[Any, Any, Any, Any]] = set()
        binding_reports: list[dict[str, Any]] = []
        for binding in artifact.get("bindings", []):
            key = (binding.get("scenario_id"), binding.get("line_number"), binding.get("drug_ref"), binding.get("regimen_index"))
            if key in seen:
                raise ValueError(f"{name}: duplicate binding {key}")
            seen.add(key)
            scenario = _one(list(disease.get("scenarios", [])), "id", binding.get("scenario_id"), f"{name}: scenario")
            line = _one(list(scenario.get("lines", [])), "line_number", binding.get("line_number"), f"{name}: line")
            drug = _one(list(line.get("drugs", [])), "drug_ref", binding.get("drug_ref"), f"{name}: drug")
            regimens = list(drug.get("regimens", []))
            regimen_index = binding.get("regimen_index")
            if not isinstance(regimen_index, int) or regimen_index < 0 or regimen_index >= len(regimens):
                raise ValueError(f"{name}: regimen_index {regimen_index!r} is invalid")
            row_index = binding.get("spec_row_index")
            if not isinstance(row_index, int) or row_index < 0 or row_index >= len(row_groups):
                raise ValueError(f"{name}: spec_row_index {row_index!r} is invalid")
            row = row_groups[row_index]
            if ATC_TO_DRUG_REF.get(row.get("atc")) != binding.get("drug_ref"):
                raise ValueError(f"{name}: spec row {row_index} ATC {row.get('atc')!r} does not match drug_ref {binding.get('drug_ref')!r}")
            linkage = _linkage(scenario, drug, regimens[regimen_index], row, spec)
            binding_reports.append({
                "scenario_id": binding.get("scenario_id"),
                "line_number": binding.get("line_number"),
                "drug_ref": binding.get("drug_ref"),
                "regimen_index": regimen_index,
                "spec_row_index": row_index,
                "spec_page": row.get("page"),
                "spec_row": row.get("row_start"),
                "atc": row.get("atc"),
                **linkage,
            })
        expected_keys = set()
        for scenario in disease.get("scenarios", []):
            for line in scenario.get("lines", []):
                for drug in line.get("drugs", []):
                    for regimen_index in range(len(drug.get("regimens", []))):
                        expected_keys.add((scenario.get("id"), line.get("line_number"), drug.get("drug_ref"), regimen_index))
        if seen != expected_keys:
            missing = sorted(expected_keys - seen)
            extra = sorted(seen - expected_keys)
            raise ValueError(f"{name}: binding coverage mismatch; missing={missing} extra={extra}")
        eligible = sum(b["unblock_eligible"] for b in binding_reports)
        total_bindings += len(binding_reports)
        reports.append({
            "disease_id": artifact.get("disease_id"),
            "cr_id": cr_id,
            "binding_count": len(binding_reports),
            "unblock_eligible_count": eligible,
            "bindings": binding_reports,
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_count": len(artifacts),
        "binding_count": total_bindings,
        "diseases": reports,
    }


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify scenario-to-dose-table bindings for calculator diseases")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--bindings", required=True, type=Path)
    parser.add_argument("--specs", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = verify_scenario_bindings(args.db, args.bindings, args.specs)
    text = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ["build_binding_artifact", "verify_scenario_bindings"]
