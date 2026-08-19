"""Local bridge from queued PDF extraction candidates to owner attestation."""

from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path
from typing import Any, Mapping

from .calculator_binding import resolve_binding
from .models import PersonalModeError


_GUIDELINE_ID = re.compile(r"^[A-Za-z0-9_.-]+$")
DEFAULT_CANDIDATE_SPECS = (
    Path(__file__).resolve().parents[2] / "clinical_sources" / "regimen_candidate_specs"
)
_DRUG_REFS = {
    "J01CA04": "amoxicillin",
    "J01CR02": "amoxiclav",
    "J01CR01": "ampicillin_sulbactam",
    "J01DD04": "ceftriaxone",
    "J01DC02": "cefuroxime",
    "J01DD08": "cefixime",
    "J01FA09": "clarithromycin",
    "J01FA07": "josamycin",
    "J01FA10": "azithromycin",
    "J01FA03": "midecamycin",
    "J01FF01": "clindamycin",
}


class ExtractedCandidateStore:
    def __init__(
        self,
        root: str | Path,
        calculator_db_path: str | Path,
        candidate_specs_dir: str | Path = DEFAULT_CANDIDATE_SPECS,
    ) -> None:
        self.root = Path(root).resolve() / "extracted_candidates"
        self.calculator_db_path = Path(calculator_db_path).resolve()
        self.candidate_specs_dir = Path(candidate_specs_dir).resolve()

    def list(self, guideline_id: str) -> dict[str, Any]:
        artifact = self._artifact(guideline_id)
        candidates = []
        for candidate in artifact.get("candidates", []):
            item = json.loads(json.dumps(candidate, ensure_ascii=False))
            item["calculator_options"] = self._calculator_options(item)
            # Never expose a machine-local PDF path through the browser API.
            item.get("source", {}).pop("pdf_path", None)
            candidates.append(item)
        return {
            "status": "REVIEW_REQUIRED",
            "guideline_id": guideline_id,
            "source_pdf_sha256": artifact.get("source_pdf_sha256"),
            "candidates": candidates,
        }

    def get(self, guideline_id: str, candidate_id: str) -> dict[str, Any]:
        artifact = self._artifact(guideline_id)
        matches = [item for item in artifact.get("candidates", []) if item.get("candidate_id") == candidate_id]
        if len(matches) != 1:
            raise PersonalModeError("EXTRACTED_CANDIDATE_NOT_FOUND", candidate_id)
        return matches[0]

    def validate_binding(self, candidate: Mapping[str, Any], binding: Mapping[str, Any]) -> dict[str, Any]:
        verified, projection = resolve_binding(binding, self.calculator_db_path)
        regimen = projection["regimen"]
        dose = candidate["dose"]
        selected_dose = regimen.get("dose_mg_kg_day")
        selected_frequency = regimen.get("freq_per_day")
        if not isinstance(selected_dose, (int, float)) or not dose["value_min"] <= selected_dose <= dose["value_max"]:
            raise PersonalModeError("CANDIDATE_BINDING_DOSE_MISMATCH", "calculator dose is outside extracted PDF range")
        fmin, fmax = dose.get("frequency_min_per_day"), dose.get("frequency_max_per_day")
        if not isinstance(selected_frequency, int) or not isinstance(fmin, int) or not isinstance(fmax, int) or not fmin <= selected_frequency <= fmax:
            raise PersonalModeError("CANDIDATE_BINDING_FREQUENCY_MISMATCH", "calculator frequency is outside extracted PDF range")
        route_map = {"oral": "per_os", "intravenous": "iv", "intramuscular": "im"}
        expected_route = route_map.get(str(dose.get("route")))
        if expected_route is None or verified.get("route") != expected_route:
            raise PersonalModeError("CANDIDATE_BINDING_ROUTE_MISMATCH", "calculator route does not exactly match extracted route")
        return verified

    def regimen_payload(self, candidate: Mapping[str, Any]) -> dict[str, Any]:
        dose = candidate["dose"]
        guideline = candidate["guideline"]
        frequency = _frequency_text(dose.get("frequency_min_per_day"), dose.get("frequency_max_per_day"))
        return {
            "regimen_id": candidate["candidate_id"],
            "diagnosis": candidate["diagnosis"],
            "icd10": candidate["icd10"],
            "therapy_line": candidate["therapy_line"],
            "drug": candidate["drug"],
            "components": [candidate["drug"]],
            "dose": {
                "value_min": dose["value_min"], "value_max": dose["value_max"],
                "unit": "mg/kg/day", "basis": "MG_KG_PER_DAY",
                "formulation_basis": "active ingredient stated in guideline row",
                "route": dose["route"], "frequency": frequency,
                "duration": dose["duration"], "maximum_dose": dose["maximum_dose"],
            },
            "population": {
                "eligible_groups": ["child"], "adult": "not included in this extracted row",
                "pediatric": "eligible per pediatric table column", "neonatal": "NOT_STATED",
                "pregnancy": "NOT_APPLICABLE_TO_PEDIATRIC_ROW", "lactation": "NOT_STATED",
                "renal": "requires separate clinical review", "hepatic": "requires separate clinical review",
            },
            "safety": {
                "allergy_classes": [], "contraindications": [], "interactions": [],
                "warnings": ["Safety data are not derived from this dose table row; review separately"],
                "requires_weight_kg": True, "requires_renal_function": True,
                "requires_pregnancy_status": False, "requires_hepatic_function": True,
            },
            "provenance": {
                "guideline_id": str(guideline["id"]), "guideline_title": guideline["title"],
                "rubricator_id": str(guideline["id"]), "rubricator_version": str(guideline["approval_year"]),
                "approval_year": guideline["approval_year"], "source_url": guideline["source_url"],
                "guideline_status": "CURRENT",
            },
            "terminology_mappings": [{
                "source": candidate["drug"], "normalized": candidate["drug"],
                "system": "ATC", "code": candidate["atc"],
            }],
            "alternatives": [],
        }

    def _artifact(self, guideline_id: str) -> dict[str, Any]:
        if not isinstance(guideline_id, str) or not _GUIDELINE_ID.fullmatch(guideline_id):
            raise PersonalModeError("GUIDELINE_ID_INVALID", "invalid guideline identifier")
        path = self.root / f"{guideline_id}.json"
        if not path.is_file():
            raise PersonalModeError("EXTRACTED_CANDIDATES_NOT_FOUND", guideline_id)
        try:
            artifact = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PersonalModeError("EXTRACTED_CANDIDATES_INVALID", guideline_id) from exc
        if artifact.get("artifact_type") != "EXTRACTED_REGIMEN_CANDIDATES" or artifact.get("guideline_id") != guideline_id:
            raise PersonalModeError("EXTRACTED_CANDIDATES_INVALID", guideline_id)
        self._verify_source_contract(guideline_id, artifact)
        return artifact

    def _verify_source_contract(self, guideline_id: str, artifact: Mapping[str, Any]) -> None:
        spec_path = self.candidate_specs_dir / f"{guideline_id}.json"
        if not spec_path.is_file():
            raise PersonalModeError("EXTRACTED_SOURCE_SPEC_NOT_FOUND", guideline_id)
        try:
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PersonalModeError("EXTRACTED_SOURCE_SPEC_INVALID", guideline_id) from exc
        expected_pdf = str(spec.get("expected_pdf_sha256") or "").lower()
        expected_candidates = str(spec.get("expected_candidates_sha256") or "").lower()
        actual_pdf = str(artifact.get("source_pdf_sha256") or "").lower()
        payload = json.dumps(
            artifact.get("candidates"), ensure_ascii=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        actual_candidates = "sha256:" + hashlib.sha256(payload).hexdigest()
        if (
            str(spec.get("guideline_id")) != guideline_id
            or not expected_pdf
            or actual_pdf != expected_pdf
            or not expected_candidates
            or actual_candidates != expected_candidates
            or str(artifact.get("candidates_sha256") or "").lower() != expected_candidates
        ):
            raise PersonalModeError(
                "EXTRACTED_SOURCE_CONTRACT_MISMATCH",
                "local artifact does not match the pinned PDF/candidate source contract",
            )
        for candidate in artifact.get("candidates") or []:
            guideline = candidate.get("guideline") or {}
            if str(guideline.get("id")) != guideline_id or str(guideline.get("pdf_sha256") or "").lower() != expected_pdf:
                raise PersonalModeError(
                    "EXTRACTED_SOURCE_CONTRACT_MISMATCH",
                    "candidate provenance does not match the pinned source contract",
                )

    def _calculator_options(self, candidate: Mapping[str, Any]) -> list[dict[str, Any]]:
        if not candidate.get("calculation_ready"):
            return []
        db = json.loads(self.calculator_db_path.read_text(encoding="utf-8-sig"))
        drug_ref = _DRUG_REFS.get(str(candidate.get("atc")))
        route = {"oral": "per_os", "intravenous": "iv", "intramuscular": "im"}.get(candidate["dose"].get("route"))
        if not drug_ref or not route:
            return []
        drug_reference = (db.get("drugs_reference") or {}).get(drug_ref) or {}
        if candidate.get("formulation_required") == "oral_suspension":
            has_verified_liquid = any(
                form.get("form_type") in {"suspension", "syrup", "granules", "powder_for_suspension"}
                and isinstance(form.get("concentration_mg_per_ml"), (int, float))
                and form.get("concentration_mg_per_ml") > 0
                for form in drug_reference.get("forms", [])
            )
            if not has_verified_liquid:
                return []
        options: list[dict[str, Any]] = []
        for disease in db.get("recommendations", []):
            if str(disease.get("cr_id")) != str(candidate["guideline"]["id"]):
                continue
            if disease.get("calculation_blocked"):
                continue
            for scenario in disease.get("scenarios", []):
                if scenario.get("age_group") not in {"child", "all"}:
                    continue
                for line in scenario.get("lines", []):
                    for drug in line.get("drugs", []):
                        if drug.get("drug_ref") != drug_ref or route not in drug.get("route", []):
                            continue
                        for index, regimen in enumerate(drug.get("regimens", [])):
                            selected = regimen.get("dose_mg_kg_day")
                            freq = regimen.get("freq_per_day")
                            dose = candidate["dose"]
                            if not isinstance(selected, (int, float)) or not dose["value_min"] <= selected <= dose["value_max"]:
                                continue
                            if not isinstance(freq, int) or not dose["frequency_min_per_day"] <= freq <= dose["frequency_max_per_day"]:
                                continue
                            binding = {
                                "disease_id": disease["id"], "scenario_id": scenario["id"],
                                "line_number": line["line_number"], "route": route,
                                "drug_ref": drug_ref, "regimen_index": index, "binding_version": "extracted-pdf-1",
                            }
                            verified, _ = resolve_binding(binding, self.calculator_db_path)
                            options.append({
                                "label": regimen.get("regimen_label") or f"{selected} мг/кг/сут, {freq} р/сут",
                                "binding": verified,
                            })
        return options


def _frequency_text(low: int | None, high: int | None) -> str:
    if low is None or high is None:
        return "NOT_EXTRACTED"
    return f"{low} times/day" if low == high else f"{low}-{high} times/day"


__all__ = ["DEFAULT_CANDIDATE_SPECS", "ExtractedCandidateStore"]
