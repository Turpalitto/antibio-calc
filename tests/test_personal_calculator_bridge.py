from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "antibiotic_calc.html.template"


def _source() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def _js_function(source: str, name: str) -> str:
    start = source.index(f"function {name}(")
    brace = source.index("{", start)
    depth = 0
    quote = None
    escaped = False
    for index in range(brace, len(source)):
        char = source[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in "'\"`":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"unterminated JavaScript function: {name}")


def _run_binding(binding: dict) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable for JavaScript behavior test")
    source = _source()
    fixture = {
        "recommendations": [
            {
                "id": "disease-1",
                "scenarios": [
                    {
                        "id": "scenario-1",
                        "age_group": "all",
                        "lines": [
                            {
                                "line_number": 1,
                                "drugs": [
                                    {
                                        "drug_ref": "amoxicillin",
                                        "route": ["per_os"],
                                        "regimens": [
                                            {"age_group": "adult", "regimen_label": "adult"},
                                            {"age_group": "child", "regimen_label": "child exact"},
                                        ],
                                    },
                                    {
                                        "combo_ref": ["amoxicillin", "clavulanate"],
                                        "route": ["per_os"],
                                        "regimens": [
                                            {"age_group": "all", "regimen_label": "combo exact"}
                                        ],
                                    },
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
        "drugs_reference": {
            "amoxicillin": {"forms": [{"form_type": "tablet"}]},
            "clavulanate": {"forms": [{"form_type": "tablet"}]},
        },
    }
    script = "\n".join(
        [
            f"const DB = {json.dumps(fixture)};",
            "let activeAge = 'child';",
            _js_function(source, "getDrugRefs"),
            _js_function(source, "sameStringArray"),
            _js_function(source, "resolveCalculatorBinding"),
            f"const binding = {json.dumps(binding)};",
            "try { const r=resolveCalculatorBinding(binding); console.log(JSON.stringify({ok:true,index:r.regimenIndex,route:r.routeGroup,combo:r.drug.combo_ref||null})); } catch(e) { console.log(JSON.stringify({ok:false,error:e.message})); }",
        ]
    )
    completed = subprocess.run(
        [node, "-e", script], capture_output=True, text=True, check=True
    )
    return json.loads(completed.stdout)


def test_personal_mode_is_explicit_local_and_non_dismissible() -> None:
    source = _source()
    assert 'id="personal-mode-toggle" type="checkbox"' in source
    assert 'id="personal-mode-banner"' in source
    assert "OWNER_REVIEWED_EXPERIMENTAL" in source
    assert "banner.dismissible !== false" in source
    assert "window.location.hostname === '127.0.0.1'" in source
    assert "window.location.hostname === 'localhost'" in source
    assert "localStorage.setItem('personal" not in source
    assert "sessionStorage" not in source


def test_template_main_javascript_has_valid_syntax() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable for JavaScript syntax test")
    scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", _source(), re.DOTALL)
    completed = subprocess.run(
        [node, "--check", "-"],
        input=scripts[-1],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert completed.returncode == 0, completed.stderr


def test_request_is_same_origin_v2_and_contains_safety_context() -> None:
    source = _source()
    assert "fetch('/v2/recommend'" in source
    assert "credentials:'same-origin'" in source
    assert "operating_mode:'PERSONAL_PHYSICIAN'" in source
    for field in (
        "owner_id",
        "session_token",
        "pregnant",
        "renal_function",
        "hepatic_impairment",
        "allergies",
        "current_meds",
    ):
        assert field in source
    assert "неизвестные значения блокируют запрос" in source


def test_api_failures_are_caught_without_disabling_calculator() -> None:
    source = _source()
    request_fn = _js_function(source, "requestPersonalCandidates")
    assert "try{" in request_fn and "}catch(error){" in request_fn
    assert "автономный калькулятор доступен" in request_fn
    assert "resetDisease(" not in request_fn
    assert "activeDrug = null" not in request_fn


def test_apply_reuses_existing_render_and_calculation_functions() -> None:
    source = _source()
    apply_fn = _js_function(source, "applyPersonalCandidate")
    select_fn = _js_function(source, "selectDrug")
    assert "renderScenarios(resolved.scenario" in apply_fn
    assert "renderForms(preferredRoute);" in select_fn
    assert "renderRegimens(preferredRegimenIdx);" in select_fn
    assert "calculate();" in select_fn
    assert "computeDose(" not in apply_fn
    assert not re.search(r"singleMg\s*=|dailyMg\s*=|concentration_mg_per_ml\s*[*/]", apply_fn)


def test_exact_single_drug_binding_resolves_filtered_regimen_index() -> None:
    result = _run_binding(
        {
            "disease_id": "disease-1",
            "scenario_id": "scenario-1",
            "line_number": 1,
            "drug_ref": "amoxicillin",
            "route": "per_os",
            "regimen_label": "child exact",
        }
    )
    assert result == {"ok": True, "index": 0, "route": "po", "combo": None}


def test_exact_combo_binding_resolves() -> None:
    result = _run_binding(
        {
            "disease_id": "disease-1",
            "scenario_id": "scenario-1",
            "line_number": 1,
            "combo_ref": ["amoxicillin", "clavulanate"],
            "route": "per_os",
            "regimen_index": 0,
        }
    )
    assert result["ok"] is True
    assert result["combo"] == ["amoxicillin", "clavulanate"]


@pytest.mark.parametrize(
    "change",
    [
        {"disease_id": "unknown"},
        {"scenario_id": "unknown"},
        {"line_number": 2},
        {"drug_ref": "unknown"},
        {"route": "iv"},
        {"regimen_label": "unknown"},
    ],
)
def test_unknown_or_mismatched_binding_is_blocked(change: dict) -> None:
    binding = {
        "disease_id": "disease-1",
        "scenario_id": "scenario-1",
        "line_number": 1,
        "drug_ref": "amoxicillin",
        "route": "per_os",
        "regimen_label": "child exact",
    }
    binding.update(change)
    result = _run_binding(binding)
    assert result["ok"] is False


def test_trace_panel_covers_governance_source_and_causal_trace() -> None:
    source = _source()
    trace_fn = _js_function(source, "renderPersonalTrace")
    for term in (
        "Governance",
        "Regimen / guideline",
        "Источник",
        "Рассмотрено / отклонено",
        "Safety filters",
        "Terminology mappings",
        "Engine stages",
        "Request trace",
    ):
        assert term in trace_fn
