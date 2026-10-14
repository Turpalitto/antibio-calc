"""Clinical-safety behaviour tests for the single-file calculator template.

The template is the only shippable artefact for the offline calculator, so the
safety gates are asserted by extracting the JavaScript functions out of
`antibiotic_calc.html.template` and executing them under Node with a minimal
DOM stub — the same technique used by `tests/test_personal_calculator_bridge.py`.

Each test names the defect it locks down; see the module docstrings below.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "antibiotic_calc.html.template"
DB_PATH = ROOT / "db" / "antibio_db.json"

# Minimal DOM stub. Enough for the render/gate helpers under test: textContent,
# classList, dataset, value, querySelector('span') and child appending.
#
# The stub models the one guarantee that matters for the XSS tests: a value put
# through textContent can never become a tag, whereas a value assigned to
# innerHTML is markup verbatim. `escapeHtml` is that guarantee, not decoration.
DOM_STUB = r"""
function escapeHtml(v){
  return String(v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
class El {
  constructor(id){
    this.id = id;
    this._text = '';
    this._raw = undefined;
    this.className = '';
    this.classList = {
      _s: new Set(),
      add: (...c) => c.forEach(x => this.classList._s.add(x)),
      remove: (...c) => c.forEach(x => this.classList._s.delete(x)),
      toggle: (c, on) => on ? this.classList._s.add(c) : this.classList._s.delete(c),
      contains: c => this.classList._s.has(c)
    };
    this.dataset = {};
    this.value = '';
    this.children = [];
    this.attrs = {};
  }
  get textContent(){ return this._text; }
  set textContent(v){ this._text = String(v); this.children = []; }
  appendChild(child){
    this.children.push(child);
    this._text += child instanceof El ? child._text : String(child);
    return child;
  }
  append(...nodes){ nodes.forEach(n => this.appendChild(n)); }
  get innerHTML(){
    // Models the real DOM: an innerHTML assignment seeds the markup and later
    // appendChild() children follow it. A text-node child is escaped, an element
    // child contributes its own serialisation.
    const kids = this.children.length
      ? this.children.map(c => c instanceof El ? c.innerHTML : escapeHtml(c)).join('')
      : '';
    if(this._raw !== undefined) return this._raw + kids;
    return kids || escapeHtml(this._text);
  }
  set innerHTML(v){ this._raw = (v === '' ? undefined : String(v)); this.children = []; }
  querySelector(sel){ return this._child || (this._child = new El(this.id + sel)); }
  onclick = null;
  getAttribute(name){ return this.attrs[name]; }
  setAttribute(name, value){ this.attrs[name] = value; }
  focus(){}
}
const REGISTRY = {};
const el = id => (REGISTRY[id] = REGISTRY[id] || new El(id));
const document = {
  getElementById: el,
  createElement: tag => new El('<' + tag + '>'),
  // Text nodes are modelled as plain strings: the stub's innerHTML getter escapes
  // any non-El child, which is exactly the "cannot become a tag" guarantee.
  createTextNode: text => String(text),
  documentElement: { classList: { add(){}, remove(){}, toggle(){}, contains(){ return false; } } },
  querySelectorAll: () => [],
  body: new El('body')
};
const window = { location: { hostname: '127.0.0.1', protocol: 'http:', hash: '' }, print(){}, printCalled: 0 };
function $(id){ return el(id); }
function toast(msg){ TOASTS.push(String(msg)); }
const TOASTS = [];
"""


def _source() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def _db() -> dict:
    return json.loads(DB_PATH.read_text(encoding="utf-8-sig"))


def _js_block(source: str, marker: str, opener: str, closer: str) -> str:
    """Extract a balanced block starting at `marker`, quote/escape aware."""
    start = source.index(marker)
    index = source.index(opener, start)
    depth = 0
    quote = None
    escaped = False
    while index < len(source):
        char = source[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char in "'\"`":
            quote = char
        elif char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
        index += 1
    raise AssertionError(f"unterminated JavaScript block: {marker}")


def _js_function(source: str, name: str) -> str:
    return _js_block(source, f"function {name}(", "{", "}")


def _node(script: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable for JavaScript behaviour test")
    # The shipped DB does not fit on an argv, so run the script from a file.
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as handle:
        handle.write(script)
        path = handle.name
    try:
        completed = subprocess.run([node, path], capture_output=True, text=True, check=False)
    finally:
        os.unlink(path)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def _js_const(source: str, name: str) -> str:
    """Extract a `const NAME = {...};` literal used by the function under test."""
    return _js_block(source, f"const {name} =", "{", "}") + ";"


def _js_simple_const(source: str, name: str) -> str:
    """Extract a scalar `const NAME = <primitive>;` declaration."""
    start = source.index(f"const {name} =") + len(f"const {name} =")
    index = start
    quote = None
    while index < len(source):
        char = source[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = None
        elif char in "'\"`":
            quote = char
        elif char == ";":
            return source[source.index(f"const {name} ="): index + 1]
        index += 1
    raise AssertionError(f"unterminated const: {name}")


def _run(functions: list[str], globals_js: str, body: str) -> dict:
    return _run_with_consts(functions, [], globals_js, body)


# Helpers the shell calls from calculate()/hideDoseResults()/renderDrugMeta()/
# fillPrescriptionForm() since the patient-context work (age / pregnancy / GFR
# flags, honest source labels, capsule-aware tablet maths). They are extracted
# from the real template and appended to every harness run that did not ask
# for them explicitly, so a test still exercises production code paths.
PATIENT_CONTEXT_SUPPORT = [
    "hidePatientSafetyFlags",
    "renderPatientSafetyFlags",
    "collectPatientSafetyFlags",
    "ageRestrictionFlag",
    "pregnancyFlag",
    "renalFlag",
    "parseAgeRestrictionDays",
    "formatAgeDays",
    "isFederalCrId",
    "diseaseSourceLabel",
    "regimenSummary",
    "solidUnitsPerDose",
    "makeActivatable",
    "allergyExportFlag",
    "exportSafetyFlags",
    "comboComponentLines",
    "componentRegimen",
    "diseaseDrugText",
    "daysWord",
    "timesADay",
    "courseIsNumeric",
    "courseDays",
    "courseText",
    "courseTail",
    "routeWordsRu",
    "isOralLiquid",
    "unitStrengthMg",
    "unitsForCourse",
    "bestSolidFormIndex",
    "roundingDeviationText",
    "formatTablets",
    "ageInputBlockReason",
]
PATIENT_CONTEXT_CONSTS = ["DAYS_PER_MONTH", "DAYS_PER_YEAR", "COMPONENT_REGIMEN_MISSING", "MAX_PLAUSIBLE_AGE_DAYS"]
PATIENT_CONTEXT_GLOBALS = "let patientAgeDays = null;\nlet vialFollowsForm = true;\n"


def _run_with_consts(functions: list[str], consts: list[str], globals_js: str, body: str) -> dict:
    source = _source()
    support = [name for name in PATIENT_CONTEXT_SUPPORT if name not in functions]
    script = "\n".join(
        [DOM_STUB, globals_js, PATIENT_CONTEXT_GLOBALS]
        + [_js_simple_const(source, name) for name in PATIENT_CONTEXT_CONSTS]
        + [_js_const(source, name) for name in consts]
        + [_js_function(source, name) for name in functions + support]
        + [body]
    )
    return _node(script)


def _lit(value) -> str:
    """Embed a Python value as a JavaScript literal."""
    return json.dumps(value, ensure_ascii=False)


def _age_globals(db: dict) -> str:
    return AGE_GLOBALS % _lit(db)


def _fixture_db() -> dict:
    return {
        "meta": {
            "version": "0.5.0-draft",
            "generated_at": "2026-07-08",
            "verification_status": "draft",
            "warning": "ЧЕРНОВИК. Требует верификации.",
        },
        "recommendations": [],
        "drugs_reference": {"vancomycin": {"inn": "Ванкомицин", "forms": [{"form_type": "tablet", "concentration": "500 мг"}]}},
    }


# --------------------------------------------------------------------------
# Bug 1 — silent cross-age dose fallback
# --------------------------------------------------------------------------

AGE_GLOBALS = r"""
let DB = %s;
let activeAge = 'child';
let lastPickedAge = null;
let dbBlockingErrors = [];
let activeDrug = null;
let activeRegimenIdx = 0;
"""

SESSION_STORE_GLOBALS = (
    "const HISTORY_KEY = 'antibio_history';\n"
    "const sessionStore = {data:{}, getItem(k){return Object.prototype.hasOwnProperty.call(this.data,k)?this.data[k]:null;},"
    " setItem(k,v){this.data[k]=String(v);}, removeItem(k){delete this.data[k];}};\n"
    "globalThis.sessionStorage = sessionStore;\n"
)

DOSE_BLOCK_GLOBALS = "const DOSE_BLOCK_CLASS = 'blocked';\n"


def test_get_active_regimen_never_substitutes_another_age_group() -> None:
    """B1: adult-only drug while activeAge='child' must yield null, not the adult regimen."""
    fixture = _fixture_db()
    adult_only = {
        "drug_ref": "vancomycin",
        "regimens": [
            {"age_group": "adult", "freq_per_day": 2, "single_dose_mg": 1000, "duration_days": "7-10"},
            {"age_group": "adult", "freq_per_day": 1, "single_dose_mg": 500, "duration_days": "5"},
        ],
    }
    globals_js = _age_globals(fixture) + f"activeDrug = {json.dumps(adult_only)};\n"
    result = _run(
        ["getDrugRefs", "ageGroupLabel", "ageEligibleRegimens", "getActiveRegimen"],
        globals_js,
        "console.log(JSON.stringify({reg:getActiveRegimen(), eligible:ageEligibleRegimens(activeDrug).length}));",
    )
    assert result == {"reg": None, "eligible": 0}, (
        "calculator silently fell back to another age group's regimen"
    )


def test_get_active_regimen_still_resolves_matching_age_and_all() -> None:
    """B1 regression guard: the legitimate paths must keep working."""
    fixture = _fixture_db()
    mixed = {
        "drug_ref": "vancomycin",
        "regimens": [
            {"age_group": "adult", "freq_per_day": 2, "single_dose_mg": 1000},
            {"age_group": "child", "freq_per_day": 3, "single_dose_mg": 40},
            {"age_group": "all", "freq_per_day": 1, "single_dose_mg": 250},
        ],
    }
    base = _age_globals(fixture) + f"activeDrug = {json.dumps(mixed)};\n"
    script_body = (
        "const out={};"
        "activeRegimenIdx=0;out.childFirst=getActiveRegimen().single_dose_mg;"
        "activeRegimenIdx=1;out.childSecond=getActiveRegimen().single_dose_mg;"
        "activeRegimenIdx=99;out.clamped=getActiveRegimen().single_dose_mg;"
        "activeAge='neonate';out.neonate=getActiveRegimen();"
        "console.log(JSON.stringify(out));"
    )
    result = _run(
        ["getDrugRefs", "ageGroupLabel", "ageEligibleRegimens", "getActiveRegimen"],
        base,
        script_body,
    )
    assert result["childFirst"] == 40
    assert result["childSecond"] == 250
    assert result["clamped"] == 40, "out-of-range index must fall back to the first eligible regimen"
    assert result["neonate"] == {"age_group": "all", "freq_per_day": 1, "single_dose_mg": 250}


def test_age_filter_expression_is_de_duplicated() -> None:
    """B1: the identical age filter existed twice; the template must keep one source of truth."""
    source = _source()
    assert source.count("r.age_group === activeAge || r.age_group === 'all'") == 1
    assert "return (activeDrug.regimens || [])[0];" not in source
    assert "function ageEligibleRegimens(" in source
    assert source.count("function getActiveRegimen(") == 1
    # renderRegimens / resolveCalculatorBinding must both go through the helper.
    assert "ageEligibleRegimens(activeDrug)" in _js_function(source, "renderRegimens")
    assert "ageEligibleRegimens(drug)" in _js_function(source, "resolveCalculatorBinding")


def test_implausible_age_blocks_the_calculation_like_an_implausible_weight() -> None:
    """«150 лет» (a typo for 15, or a birth year) must not silently land in the
    adult group: the calculation is blocked and the notice names the input."""
    fixture = _fixture_db()
    adult = {
        "drug_ref": "vancomycin",
        "regimens": [{"age_group": "adult", "freq_per_day": 2, "single_dose_mg": 1000}],
    }
    globals_js = _age_globals(fixture) + f"activeDrug = {json.dumps(adult)};\nactiveAge='adult';\n"
    funcs = [
        "getDrugRefs",
        "ageGroupLabel",
        "ageEligibleRegimens",
        "ageRegimenBlockReason",
        "weightBlockReason",
        "weightWarnReason",
        "dbBlockReason",
        "calculationBlockReason",
        "parseAgeToDays",
        "readPatientAge",
        "ageGroupFromDays",
        "updateExplicitAgeNotice",
    ]
    body = (
        "const out = {};"
        "const probe = (v, unit) => { $('patient-age').value = v; $('patient-age-unit').value = unit;"
        " patientAgeDays = readPatientAge(); updateExplicitAgeNotice();"
        " return {block: calculationBlockReason(70), notice: $('age-explicit-notice').querySelector('span').textContent,"
        " hidden: $('age-explicit-notice').classList.contains('hidden')}; };"
        "out.y150 = probe('150', 'years'); out.m1500 = probe('1500', 'months'); out.d50000 = probe('50000', 'days');"
        "out.y119 = probe('119', 'years'); out.y120 = probe('120', 'years'); out.y15 = probe('15', 'years');"
        "console.log(JSON.stringify(out));"
    )
    result = _run(funcs, globals_js, body)
    for key, shown in (("y150", "150 лет"), ("m1500", "1500 мес"), ("d50000", "50000 дн.")):
        assert result[key]["block"].startswith("РАСЧЁТ ЗАБЛОКИРОВАН: Возраст " + shown + " — неправдоподобное значение (> 120 лет)"), result[key]
        assert "неправдоподобное" in result[key]["notice"] and result[key]["hidden"] is False, result[key]
    assert result["y119"]["block"] == "" and result["y120"]["block"] == "", result
    assert result["y119"]["notice"] == "Возраст 119 лет → группа «взрослые»."
    # 15 years → child group mismatch notice, not a block
    assert result["y15"]["block"] == "" and "не соответствует введённому возрасту" in result["y15"]["notice"], result["y15"]


def test_age_regimen_block_reason_is_explicit_and_blocks() -> None:
    """B1: the missing-age-group case must produce a blocking, dose-level message."""
    fixture = _fixture_db()
    adult_only = {
        "drug_ref": "vancomycin",
        "regimens": [{"age_group": "adult", "freq_per_day": 2, "single_dose_mg": 1000}],
    }
    globals_js = _age_globals(fixture) + f"activeDrug = {json.dumps(adult_only)};\n"
    funcs = [
        "getDrugRefs",
        "ageGroupLabel",
        "ageEligibleRegimens",
        "ageRegimenBlockReason",
        "weightBlockReason",
        "weightWarnReason",
        "dbBlockReason",
        "calculationBlockReason",
    ]
    body = (
        "const reason = calculationBlockReason(30);"
        "console.log(JSON.stringify({blocked:!!reason, reason:reason,"
        " hasAge:reason.indexOf('возрастной группы')>=0,"
        " hasDrug:reason.indexOf('Ванкомицин')>=0,"
        " notPatientSpecific:reason.indexOf('НЕ является пациент-специфичным')>=0,"
        " listsAdultOnly:reason.indexOf('взрослые')>=0,"
        " mentionsNotPrintable:/распечатан/i.test(reason),"
        " mentionsNotSaved:/не может быть сохранён/i.test(reason)}));"
    )
    result = _run(funcs, globals_js, body)
    assert result["blocked"] is True
    assert result["hasAge"] and result["hasDrug"] and result["notPatientSpecific"]
    assert result["listsAdultOnly"]
    assert result["mentionsNotPrintable"] and result["mentionsNotSaved"]


def test_resolve_calculator_binding_rejects_binding_with_no_age_matching_regimen() -> None:
    """B1: the verified-binding path must fail closed too, not pick a foreign regimen."""
    fixture = {
        "meta": _fixture_db()["meta"],
        "drugs_reference": {
            "amoxicillin": {"inn": "Амоксициллин", "forms": [{"form_type": "tablet", "concentration": "500 мг"}]}
        },
        "recommendations": [
            {
                "id": "d1",
                "name": "x",
                "mkb10": ["J01"],
                "scenarios": [
                    {
                        "id": "s1",
                        "age_group": "all",
                        "lines": [
                            {
                                "line_number": 1,
                                "drugs": [
                                    {
                                        "drug_ref": "amoxicillin",
                                        "route": ["per_os"],
                                        "regimens": [
                                            {"age_group": "adult", "freq_per_day": 3, "single_dose_mg": 500}
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    }
    globals_js = DOSE_BLOCK_GLOBALS + (
        f"const DB = {_lit(fixture)};\nlet activeAge='child';\nlet dbBlockingErrors=[];\n"
    )
    result = _run(
        [
            "getDrugRefs",
            "ageGroupLabel",
            "ageEligibleRegimens",
            "sameStringArray",
            "resolveCalculatorBinding",
        ],
        globals_js,
        (
            "try{ resolveCalculatorBinding({disease_id:'d1',scenario_id:'s1',line_number:1,"
            "drug_ref:'amoxicillin',route:'per_os',regimen_label:'adult',regimen_index:0});"
            "console.log(JSON.stringify({ok:true})); }"
            "catch(e){ console.log(JSON.stringify({ok:false,error:e.message})); }"
        ),
    )
    assert result["ok"] is False
    assert "возрастной группы" in result["error"]


# --------------------------------------------------------------------------
# Bug 4 — max_daily_mg did not clamp the single dose
# --------------------------------------------------------------------------


def test_max_daily_cap_clamps_single_dose_branch() -> None:
    """B4: single_dose_mg x freq above max_daily_mg must clamp the single dose too."""
    reg = {"age_group": "all", "freq_per_day": 3, "single_dose_mg": 1000, "max_daily_mg": 2400}
    result = _run(["computeDose"], "", (
        f"const r=computeDose({_lit(reg)}, 70, 'мг');"
        "console.log(JSON.stringify({singleMg:r.singleMg,dailyMg:r.dailyMg,capped:r.capped}));" 
    ))
    assert result["capped"] is True
    assert result["dailyMg"] == 2400
    assert result["singleMg"] == 800, "single dose must be reduced to max_daily_mg / freq_per_day"
    assert result["singleMg"] * 3 <= 2400


def test_max_daily_cap_clamps_single_dose_without_frequency() -> None:
    """B4: single_dose_mg with no freq_per_day is treated as q.d. and still clamped."""
    reg = {"age_group": "all", "single_dose_mg": 4000, "max_daily_mg": 2000}
    result = _run(["computeDose"], "", (
        f"const r=computeDose({_lit(reg)}, 70, 'мг');"
        "console.log(JSON.stringify({singleMg:r.singleMg,dailyMg:r.dailyMg,capped:r.capped}));" 
    ))
    assert result["capped"] is True
    assert result["singleMg"] == 2000
    assert result["dailyMg"] == 2000


def test_max_daily_cap_preserves_uncapped_doses() -> None:
    """B4 regression guard: doses below the cap are untouched."""
    reg = {"age_group": "all", "freq_per_day": 2, "single_dose_mg": 500, "max_daily_mg": 4000}
    result = _run(["computeDose"], "", (
        f"const r=computeDose({_lit(reg)}, 70, 'мг');"
        "console.log(JSON.stringify({singleMg:r.singleMg,dailyMg:r.dailyMg,capped:r.capped}));" 
    ))
    assert result == {"singleMg": 500, "dailyMg": 1000, "capped": False}


def test_per_kilogram_branch_still_clamps_to_max_daily() -> None:
    """B4 regression guard: the mg/kg path keeps its original clamping behaviour."""
    reg = {"age_group": "child", "dose_mg_kg_day": 100, "freq_per_day": 3, "max_daily_mg": 2000}
    result = _run(["computeDose"], "", (
        f"const r=computeDose({_lit(reg)}, 40, 'мг');"
        "console.log(JSON.stringify({singleMg:r.singleMg,dailyMg:r.dailyMg,capped:r.capped}));" 
    ))
    assert result == {"singleMg": 2000 / 3, "dailyMg": 2000, "capped": True}


# --------------------------------------------------------------------------
# Bug 6 — out-of-range weight was advisory only
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "weight,age",
    [
        (0.5, "neonate"),
        (300, "adult"),
        (45, "child"),
        (45, "neonate"),
    ],
)
def test_out_of_range_or_contradictory_weight_blocks(weight: float, age: str) -> None:
    """B6: implausible weight / weight-vs-age conflict must block, not warn.

    A child-grouped mg/kg regimen evaluated against an adult weight is the real
    overdose vector, so it blocks. The symmetric case (a rare but real
    sub-40 kg adult) does NOT block -- see weightWarnReason below.
    """
    result = _run(["weightBlockReason"], "", (
        f"console.log(JSON.stringify({{r:weightBlockReason({weight}, '{age}')}}));"
    ))
    assert result["r"], f"expected a blocking reason for weight={weight} age={age}"
    assert "Расчёт заблокирован" in result["r"]


@pytest.mark.parametrize(
    "weight,age",
    [(20, "child"), (70, "adult"), (4, "neonate"), (0, "child"), (12.5, "child")],
)
def test_in_range_weight_does_not_block(weight: float, age: str) -> None:
    result = _run(["weightBlockReason"], "", (
        f"console.log(JSON.stringify({{r:weightBlockReason({weight}, '{age}')}}));"
    ))
    assert result["r"] == ""


@pytest.mark.parametrize("weight,age", [(35, "adult"), (20, "adult"), (12, "adult")])
def test_sub_40kg_adult_warns_but_is_not_a_workflow_dead_end(weight, age) -> None:
    """B6 follow-up: a rare-but-real low-weight adult must still be able to be dosed.

    The fixed adult dose does not depend on weight, so an unusual adult weight
    cannot corrupt it. Blocking would leave the physician with no dose at all,
    which is a worse failure than the inconsistency it prevents.
    """
    result = _run(["weightBlockReason", "weightWarnReason"], "", (
        f"console.log(JSON.stringify({{b:weightBlockReason({weight}, '{age}'),"
        f"w:weightWarnReason({weight}, '{age}')}}));"
    ))
    assert result["b"] == "", f"weight={weight} age={age} must not hard-block"
    assert result["w"], f"weight={weight} age={age} must still carry a caution"
    assert "\u0420\u0430\u0441\u0447\u0451\u0442 \u0437\u0430\u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u0430\u043d" not in result["w"]


def test_adult_weight_over_40_never_produces_a_caution() -> None:
    result = _run(["weightBlockReason", "weightWarnReason"], "", (
        "console.log(JSON.stringify({w:weightWarnReason(70, 'adult')}));"
    ))
    assert result["w"] == ""


def test_weight_impossible_for_the_entered_age_blocks_and_rare_combinations_warn() -> None:
    """«25» typed instead of «2.5» for a neonate is a 10× mg/kg dose: the explicit
    age makes the weight checkable, and the notice names both values."""
    body = (
        "const probe = (days, w, age) => ({b: weightBlockReason(w, age), w: weightWarnReason(w, age)});"
        "const out = {};"
        "patientAgeDays = 10; out.neo25 = probe(10, 25, 'neonate'); out.neo7 = probe(10, 7, 'neonate'); out.neo71 = probe(10, 7.1, 'neonate');"
        "patientAgeDays = 6 * DAYS_PER_MONTH; out.inf25 = probe(0, 25, 'child'); out.inf20 = probe(0, 20, 'child'); out.inf7 = probe(0, 7, 'child');"
        "patientAgeDays = 2 * DAYS_PER_YEAR; out.tod28 = probe(0, 28, 'child'); out.tod14 = probe(0, 14, 'child');"
        "patientAgeDays = 5 * DAYS_PER_YEAR; out.five28 = probe(0, 28, 'child');"
        "patientAgeDays = null; out.noAge25 = probe(0, 25, 'neonate');"
        "console.log(JSON.stringify(out));"
    )
    result = _run(["weightBlockReason", "weightWarnReason"], "", body)
    assert result["neo25"]["b"].startswith("Вес 25 кг при возрасте 10 дн. — неправдоподобное сочетание для новорождённого (> 7 кг)"), result["neo25"]
    assert "2.5 кг вместо 25" in result["neo25"]["b"]
    assert result["neo7"] == {"b": "", "w": ""} and result["neo71"]["b"].startswith("Вес 7.1 кг при возрасте 10 дн.")
    assert result["inf25"]["b"].startswith("Вес 25 кг при возрасте 6 мес — неправдоподобное сочетание для ребёнка до года (> 20 кг)"), result["inf25"]
    assert result["inf20"] == {"b": "", "w": ""} and result["inf7"] == {"b": "", "w": ""}
    # 1–3 years: a warning, never a block (obesity exists; the typo risk is lower)
    assert result["tod28"]["b"] == "" and result["tod28"]["w"].startswith("Вес 28 кг при возрасте 2 года — редкое сочетание для ребёнка до 3 лет"), result["tod28"]
    assert result["tod14"] == {"b": "", "w": ""} and result["five28"] == {"b": "", "w": ""}
    # without an explicit age the old group-only rules apply (25 kg neonate → not checkable by age)
    assert result["noAge25"] == {"b": "", "w": ""}, result["noAge25"]


def test_calculate_refuses_to_render_a_dose_for_out_of_range_weight() -> None:
    """B6: the blocking path must hide the dose panels, not just print a message."""
    fixture = _fixture_db()
    drug = {
        "drug_ref": "vancomycin",
        "route": ["per_os"],
        "regimens": [{"age_group": "all", "freq_per_day": 2, "single_dose_mg": 1000, "duration_days": "7-10"}],
    }
    globals_js = DOSE_BLOCK_GLOBALS + (
        f"const DB = {_lit(fixture)};\nlet activeAge='neonate';\nlet userPickedAge=false;\nlet lastPickedAge=null;\n"
        f"let dbBlockingErrors=[];\nlet activeDrug={_lit(drug)};\nlet activeRegimenIdx=0;\n"
        "let activeFormIdx=0;let currentRouteGroup='po';let activeDisease={name:'x'};\n"
        "let activeLine=null;\n$('weight').value='0.5';\n"
    )
    funcs = [
        "getDrugRefs",
        "ageGroupLabel",
        "ageEligibleRegimens",
        "getActiveRegimen",
        "ageRegimenBlockReason",
        "weightBlockReason",
        "weightWarnReason",
        "dbBlockReason",
        "calculationBlockReason",
        "showDoseBlock",
        "hideDoseBlock",
        "hideDoseResults",
        "updateWeightWarn",
        "doseUnitOf",
        "computeDose",
        "calculate",
    ]
    body = (
        "calculate();"
        "console.log(JSON.stringify({"
        "block:$('dose-block').textContent,"
        "blockHidden:$('dose-block').classList.contains('hidden'),"
        "poHidden:$('res-po').classList.contains('hidden'),"
        "injHidden:$('res-inj').classList.contains('hidden'),"
        "warnBlocking:$('weight-warn').dataset.blocking}));"
    )
    result = _run(funcs, globals_js, body)
    assert "РАСЧЁТ ЗАБЛОКИРОВАН" in result["block"]
    assert result["blockHidden"] is False, "the dose-level block must be visible"
    assert result["poHidden"] is True and result["injHidden"] is True
    assert result["warnBlocking"] == "true"


def test_calculate_renders_normally_when_all_gates_pass() -> None:
    """B6/B8 regression guard: a sane 20 kg child must still get a dose."""
    fixture = _fixture_db()
    drug = {
        "drug_ref": "vancomycin",
        "route": ["per_os"],
        "regimens": [{"age_group": "all", "freq_per_day": 2, "single_dose_mg": 20, "duration_days": "7-10"}],
    }
    globals_js = DOSE_BLOCK_GLOBALS + (
        f"const DB = {_lit(fixture)};\nlet activeAge='child';\nlet userPickedAge=false;\nlet lastPickedAge=null;\n"
        f"let dbBlockingErrors=[];\nlet activeDrug={_lit(drug)};\nlet activeRegimenIdx=0;\n"
        "let activeFormIdx=0;let currentRouteGroup='po';let activeDisease={name:'x'};\n"
        "let activeLine=null;\n$('weight').value='20';\n"
    )
    funcs = [
        "getDrugRefs",
        "ageGroupLabel",
        "ageEligibleRegimens",
        "getActiveRegimen",
        "ageRegimenBlockReason",
        "weightBlockReason",
        "weightWarnReason",
        "dbBlockReason",
        "calculationBlockReason",
        "showDoseBlock",
        "hideDoseBlock",
        "hideDoseResults",
        "updateWeightWarn",
        "doseUnitOf",
        "computeDose",
        "formatUnits",
        "formatTablets",
        "getStandardBottleMl",
        "fmtDose",
        "calculateCoursePackages",
        "renderReconstitution",
        "renderDrugMeta",
        "metaRow",
        "renderPO",
        "calculate",
    ]
    result = _run(funcs, globals_js, (
        "calculate();"
        "console.log(JSON.stringify({block:$('dose-block').textContent,"
        "poHidden:$('res-po').classList.contains('hidden'),"
        "mg:$('po-mg').textContent,day:$('po-day').textContent}));"
    ))
    assert result["block"] == ""
    assert result["poHidden"] is False
    assert result["mg"] == "20 мг"
    assert result["day"] == "40 мг"


# --------------------------------------------------------------------------
# Bug 8 — validateDB() was fail-open
# --------------------------------------------------------------------------


def test_shipped_database_passes_the_blocking_validation_checks() -> None:
    """B8: making validateDB() authoritative is only safe if the shipped DB is clean."""
    result = _run(["validateDB"], f"const DB = {_lit(_db())};", (
        "const v=validateDB();"
        "console.log(JSON.stringify({errs:v.errs.length,warns:v.warns.length,first:v.errs.slice(0,3)}));"
    ))
    assert result["errs"] == 0, f"shipped DB has blocking errors: {result['first']}"


def test_validate_db_flags_dangling_drug_reference() -> None:
    broken = {
        "meta": _fixture_db()["meta"],
        "drugs_reference": {"amoxicillin": {"inn": "A", "forms": []}},
        "recommendations": [
            {
                "id": "d1",
                "name": "n",
                "mkb10": ["J01"],
                "scenarios": [
                    {
                        "id": "s1",
                        "age_group": "all",
                        "lines": [
                            {
                                "line_number": 1,
                                "drugs": [
                                    {
                                        "drug_ref": "vancomycin",
                                        "route": ["per_os"],
                                        "regimens": [{"age_group": "all"}],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    }
    result = _run(["validateDB"], f"const DB = {_lit(broken)};", (
        "const v=validateDB();"
        "console.log(JSON.stringify({errs:v.errs,blocking:v.errs.some(e=>e.indexOf('vancomycin')>=0)}));"
    ))
    assert result["blocking"] is True
    assert any("vancomycin" in err for err in result["errs"])


def test_db_block_reason_is_fail_closed() -> None:
    result = _run(["dbBlockReason"], "let dbBlockingErrors = ['drug_ref \"x\" не найден', 'нет freq_per_day'];", (
        "const reason=dbBlockReason();"
        "dbBlockingErrors=[];"
        "console.log(JSON.stringify({reason:reason, empty:dbBlockReason()}));"
    ))
    assert "БД не прошла проверку целостности" in result["reason"]
    assert "2 ошибок" in result["reason"]
    assert result["empty"] == ""


def test_calculation_block_reason_prefers_database_integrity_failure() -> None:
    fixture = _fixture_db()
    drug = {
        "drug_ref": "vancomycin",
        "regimens": [{"age_group": "all", "freq_per_day": 1, "single_dose_mg": 10}],
    }
    globals_js = DOSE_BLOCK_GLOBALS + (
        f"const DB = {_lit(fixture)};\nlet activeAge='child';\nlet dbBlockingErrors=['нет freq_per_day'];\n"
        f"let activeDrug={_lit(drug)};\n"
    )
    result = _run(
        [
            "getDrugRefs",
            "ageGroupLabel",
            "ageEligibleRegimens",
            "ageRegimenBlockReason",
            "weightBlockReason",
        "weightWarnReason",
            "dbBlockReason",
            "calculationBlockReason",
        ],
        globals_js,
        "console.log(JSON.stringify({reason:calculationBlockReason(20)}));",
    )
    assert "БД не прошла проверку целостности" in result["reason"]


def test_init_marks_the_header_as_blocked_when_the_database_is_invalid() -> None:
    source = _source()
    init_fn = _js_function(source, "init")
    assert "dbBlockingErrors = v.errs.slice();" in init_fn
    assert "расчёт заблокирован" in init_fn
    assert "renderTrustBanner();" in init_fn


# --------------------------------------------------------------------------
# Bug 2 — stored DOM XSS
# --------------------------------------------------------------------------

XSS_PAYLOAD = '<img src=x onerror="globalThis.__pwned=1">'


def test_history_rows_are_built_with_text_content_not_inner_html() -> None:
    """B2: a stored patient name must never be parsed as HTML."""
    result = _run(
        ["historySessionAvailable", "readHistoryEntries", "loadHistory"],
        "let historyEntries = " + _lit(
            [
                {
                    # fresh timestamp: readHistoryEntries drops entries older
                    # than the 24h PHI TTL (audit S-3), so a fixed 2023 date
                    # would be filtered out and the row would never render.
                    "ts": int(time.time() * 1000),
                    "patient": XSS_PAYLOAD,
                    "disease": XSS_PAYLOAD,
                    "drug": XSS_PAYLOAD,
                    "singleMg": 500,
                    "freq": 2,
                    "duration": "7-10",
                }
            ]
        ) + ";\n",
        (
            "loadHistory();"
            "const list=$('history-list');"
            "console.log(JSON.stringify({"
            "html:list.innerHTML,"
            "text:list.textContent,"
            "leaked:list.innerHTML.indexOf('<img')>=0}));"
        ),
    )
    assert result["leaked"] is False, "history markup still interpolates raw values"
    assert "&lt;img" in result["html"], "payload must survive as escaped text, not as a tag"
    assert XSS_PAYLOAD in result["text"], "the name must still be shown, just as text"


def test_search_results_are_built_with_text_content_not_inner_html() -> None:
    """B2: DB-sourced name/MKB/CR values in the search list must not be parsed as HTML."""
    fixture = {
        "meta": _fixture_db()["meta"],
        "drugs_reference": {},
        "recommendations": [
            {
                "id": "d1",
                "name": "Отит " + XSS_PAYLOAD,
                "mkb10": ["H66" + XSS_PAYLOAD, "H65.9"],
                "cr_id": XSS_PAYLOAD,
                "synonyms": [],
            }
        ],
    }
    result = _run_with_consts(
        ["handleSearch"],
        ["KEY_MAP_RU_EN", "HOMOGLYPHS_RU_EN"],
        f"const DB = {_lit(fixture)};\nfunction selectDisease(){{}}\n",
        (
            "$('search').value='От';\nhandleSearch();"
            "const box=$('results-box');"
            "console.log(JSON.stringify({leaked:box.innerHTML.indexOf('<img')>=0,"
            " escaped:box.innerHTML.indexOf('&lt;img')>=0,"
            " text:box.textContent}));"
        ),
    )
    assert result["leaked"] is False, "search results still interpolate DB values as HTML"
    assert result["escaped"] is True
    assert "onerror" in result["text"]


def test_known_safe_dom_sinks_remain_text_content() -> None:
    """B2 regression guard: the helpers that were already safe must stay that way."""
    source = _source()
    for name in ("renderExtractedCandidates", "renderPersonalCandidates"):
        body = _js_function(source, name)
        assert "textContent" in body
        assert not re.search(r"innerHTML\s*=\s*[^;]*\$\{", body)


# --------------------------------------------------------------------------
# Bug 3 — PHI in localStorage
# --------------------------------------------------------------------------


def test_patient_identity_never_reaches_local_storage() -> None:
    source = _source()
    assert "localStorage.setItem('antibio_history'" not in source
    assert "localStorage.getItem('antibio_history'" not in source
    for name in ("saveToHistory", "loadHistory", "writeSessionHistory", "readHistoryEntries", "clearHistory"):
        assert "localStorage" not in _js_function(source, name), f"{name} touches localStorage"


def test_history_is_memory_only_unless_the_physician_opts_in() -> None:
    """B3: default state keeps PHI in memory; the checkbox flips on sessionStorage."""
    result = _run_with_consts(
        [
            "historySessionAvailable",
            "historyPersistAllowed",
            "readHistoryEntries",
            "writeSessionHistory",
        ],
        ["HISTORY_MAX"],
        SESSION_STORE_GLOBALS + "let historyEntries = [];\n",
        (
            "$('history-persist').checked=false;"
            "const before=historyPersistAllowed();"
            "writeSessionHistory([{ts:1,patient:'Ann',drug:'x'}]);"
            "const afterDefault=('antibio_history' in sessionStore.data)?sessionStore.data['antibio_history']:null;"
            "$('history-persist').checked=true;"
            "const afterOptIn=historyPersistAllowed();"
            "writeSessionHistory([{ts:2,patient:'Bob',drug:'y'}]);"
            "console.log(JSON.stringify({"
            "defaultAllowed:before, afterOptIn:afterOptIn,"
            "writtenWithoutConsent:afterDefault, writtenWithConsent:('antibio_history' in sessionStore.data)?sessionStore.data['antibio_history']:null"
            " }));"
        ),
    )
    assert result["defaultAllowed"] is False
    assert result["afterOptIn"] is True
    assert result["writtenWithoutConsent"] is None, "PHI written before the physician opted in"
    assert result["writtenWithConsent"] == '[{"ts":2,"patient":"Bob","drug":"y"}]'


def test_history_degrades_honestly_when_session_storage_is_unavailable() -> None:
    result = _run_with_consts(
        [
            "historySessionAvailable",
            "historyPersistAllowed",
            "readHistoryEntries",
            "writeSessionHistory",
            "purgeLegacyHistory",
            "initHistoryStore",
        ],
        ["HISTORY_MAX"],
        "const HISTORY_KEY = 'antibio_history';\nlet historyEntries = [{ts:Date.now(),patient:'Ann',drug:'x'}];\n",
        (
            "const avail=historySessionAvailable();"
            "$('history-persist').checked=true;"
            "const allowed=historyPersistAllowed();"
            "const list=writeSessionHistory([{ts:Date.now(),patient:'Bob'}]);"
            "initHistoryStore();"
            "console.log(JSON.stringify({available:avail,allowed:allowed,"
            " checkboxDisabled:$('history-persist').disabled,"
            " memoryStillUsable:list.length===1&&readHistoryEntries().length===1,"
            " note:$('history-storage-note').textContent}));"
        ),
    )
    assert result["available"] is False
    assert result["allowed"] is False
    assert result["checkboxDisabled"] is True
    assert result["memoryStillUsable"] is True
    assert "недоступно" in result["note"]


def test_legacy_local_storage_history_is_purged_on_start() -> None:
    result = _run_with_consts(
        ["historySessionAvailable", "purgeLegacyHistory"], ["HISTORY_MAX"],
        "const HISTORY_KEY = 'antibio_history';\nlet historyEntries = [];\n"
        "const local = {data:{'antibio_history':'[{\"patient\":\"Old PHI\"}]'},"
        " getItem(k){return Object.prototype.hasOwnProperty.call(this.data,k)?this.data[k]:null;},"
        " removeItem(k){delete this.data[k];}};\n"
        "globalThis.localStorage = local;\n",
        (
            "const before=localStorage.getItem('antibio_history');"
            "purgeLegacyHistory();"
            "console.log(JSON.stringify({beforePresent:before!==null,"
            " after:localStorage.getItem('antibio_history')}));"
        ),
    )
    assert result["beforePresent"] is True
    assert result["after"] is None


def test_history_ui_survives_the_storage_change() -> None:
    source = _source()
    assert 'id="history-persist" type="checkbox"' in source
    assert 'id="history-storage-note"' in source
    assert 'id="history-list"' in source
    assert 'id="history-clear"' in source
    assert "onHistoryPersistChange()" in source
    assert "initHistoryStore();" in _js_function(source, "init")
    clear_fn = _js_function(source, "clearHistory")
    assert "sessionStorage.removeItem(HISTORY_KEY)" in clear_fn
    assert "historyEntries = []" in clear_fn


# --------------------------------------------------------------------------
# Bug 5 — draft status and build identity were invisible
# --------------------------------------------------------------------------


def test_build_identifier_exposes_database_version_and_a_build_fingerprint() -> None:
    result = _run(
        ["dbTrustState", "buildFingerprint", "buildIdentifier"],
        f"const DB = {_lit(_fixture_db())};\n"
        + "$('db-data').textContent='{\"recommendations\":[],\"meta\":{\"version\":\"9.9.9\"}}';\n",
        (
            "const other=buildFingerprint();"
            "$('db-data').textContent='{\"recommendations\":[1],\"meta\":{\"version\":\"9.9.9\"}}';"
            "console.log(JSON.stringify({id:buildIdentifier(),fingerprint:other,"
            " changed:other!==buildFingerprint(),"
            " hasVersion:buildIdentifier().indexOf('0.5.0-draft')>=0,"
            " hasBuild:buildIdentifier().indexOf('сборка')>=0}));"
        ),
    )
    assert result["hasVersion"] is True, "DB.meta.version is not shown"
    assert result["hasBuild"] is True
    assert re.fullmatch(r"[0-9A-F]{8}", result["fingerprint"]), result["fingerprint"]
    assert result["changed"] is True, "build id must change when the DB payload changes"


def test_trust_banner_promotes_draft_status_and_drives_verified_flag() -> None:
    globals_js = f"const DB = {_lit(_fixture_db())};\n$('db-data').textContent='{{}}';\n"
    draft = _run(
        ["dbTrustState", "buildFingerprint", "buildIdentifier", "renderTrustBanner"],
        globals_js,
        (
            "renderTrustBanner();"
            "console.log(JSON.stringify({verified:$('trust-banner').dataset.verified,"
            " text:$('trust-banner').textContent,build:$('build-id').textContent}));"
        ),
    )
    assert draft["verified"] == "false"
    assert "НЕПРОВЕРЕННАЯ" in draft["text"]
    assert "ЧЕРНОВИК" in draft["text"]
    assert "0.5.0-draft" in draft["build"]

    verified_db = _fixture_db()
    verified_db["meta"]["verification_status"] = "verified"
    ok = _run(
        ["dbTrustState", "buildFingerprint", "buildIdentifier", "renderTrustBanner"],
        f"const DB = {_lit(verified_db)};\n$('db-data').textContent='{{}}';\n",
        (
            "renderTrustBanner();"
            "console.log(JSON.stringify({verified:$('trust-banner').dataset.verified,"
            " text:$('trust-banner').textContent}));"
        ),
    )
    assert ok["verified"] == "true"
    assert "ВЕРИФИЦИРОВАННАЯ" in ok["text"]


def test_disease_source_badge_reflects_the_actual_source_status() -> None:
    source = _source()
    fn = _js_function(source, "diseaseSourceStatus")
    assert "calculation_blocked" in fn
    gate = _js_function(source, "applyDiseaseSourceGate")
    assert "block.dataset.sourceStatus = status" in gate
    # A VERIFIED badge must not be reachable for a non-verified status.
    verified_branch = gate.split("status === 'CALCULATOR_BOUND_VERIFIED'")[1].split("} else if")[0]
    assert "VERIFIED" in verified_branch
    assert "block.textContent" in gate.split("if(blocked)")[0] or "РАСЧЁТ ЗАБЛОКИРОВАН" in gate


def test_source_status_helper_reports_blocked_and_unverified() -> None:
    result = _run(
        ["diseaseSourceStatus"],
        "",
        (
            "console.log(JSON.stringify({"
            "blocked:diseaseSourceStatus({calculation_blocked:true,source_verification_status:'CALCULATOR_BOUND_VERIFIED'}),"
            " verified:diseaseSourceStatus({source_verification_status:'CALCULATOR_BOUND_VERIFIED'}),"
            " unverified:diseaseSourceStatus({source_verification_status:'SOURCE_PDF_VERIFIED'}),"
            " missing:diseaseSourceStatus({}),"
            " lower:diseaseSourceStatus({source_verification_status:'source_pdf_verified'}),"
            " injected:diseaseSourceStatus({source_verification_status:'<img src=x onerror=1>'}),"
            " quoted:diseaseSourceStatus({source_verification_status:'A\\'><script>alert(1)</script>'}) }));"
        ),
    )
    assert result["blocked"] == "blocked"
    assert result["verified"] == "CALCULATOR_BOUND_VERIFIED"
    assert result["unverified"] == "SOURCE_PDF_VERIFIED"
    assert result["missing"] == "UNVERIFIED"
    assert result["lower"] == "SOURCE_PDF_VERIFIED", "status must be normalised to upper case"
    assert result["injected"] == "UNVERIFIED", "markup in a DB status must not survive"
    assert result["quoted"] == "UNVERIFIED", "quote-breaking markup must not survive"


def test_draft_banner_and_build_id_reach_the_printed_prescription() -> None:
    source = _source()
    assert 'id="trust-banner"' in source
    assert 'id="build-id"' in source
    assert 'id="rx-trust-line"' in source
    assert 'id="rx-build-line"' in source
    # The print banner lives inside #prescription-form, which is the only
    # element the @media print rule reveals.
    fill = _js_function(source, "fillPrescriptionForm")
    assert "$('rx-trust-line').textContent" in fill
    assert "$('rx-build-line').textContent" in fill
    assert "dbTrustState().verified" in fill
    assert "НЕПРОВЕРЕННАЯ БД" in fill
    form = source.split('id="prescription-form"')[1].split("</div>\n\n<script")[0]
    assert "rx-trust-line" in form and "rx-build-line" in form


def test_print_is_refused_when_the_calculation_is_blocked() -> None:
    source = _source()
    blocked = _js_function(source, "printBlocked")
    assert "calculationBlockReason" in blocked
    assert "showDoseBlock" in blocked
    setup = _js_function(source, "setupButtons")
    assert setup.count("if(printBlocked()) return;") == 2
    assert setup.count("window.print()") == 2


def test_copy_paths_refuse_to_emit_a_dose_when_blocked() -> None:
    source = _source()
    for name in ("copyForMIS", "copyLatinRecipe"):
        body = _js_function(source, name)
        assert "calculationBlockReason" in body
        assert "заблокировано" in body


def test_no_console_log_left_in_the_template() -> None:
    assert not re.search(r"console\.(log|debug)\(", _source())


def test_weight_inference_that_changes_the_group_surfaces_a_notice() -> None:
    """B7: the population may still be inferred, but never silently."""
    result = _run(
        ["ageGroupLabel", "showAgeInferenceNotice", "clearAgeInferenceNotice", "setActiveAge"],
        "let activeAge='adult';\nlet lastPickedAge='adult';\n",
        (
            "setActiveAge('child', {w:20});"
            "const shown=$('age-infer-notice');"
            "const afterDown={visible:!shown.classList.contains('hidden'), text:shown.querySelector('span').textContent};"
            "clearAgeInferenceNotice();"
            "const cleared=shown.classList.contains('hidden');"
            "activeAge='child'; setActiveAge('adult', {w:70});"
            "const afterUp={visible:!shown.classList.contains('hidden'), text:shown.querySelector('span').textContent};"
            "clearAgeInferenceNotice();"
            "activeAge='adult'; setActiveAge('adult', {w:70});"
            "const sameGroupHidden=shown.classList.contains('hidden');"
            "activeAge='adult'; setActiveAge('child');"
            "const noInferenceHidden=shown.classList.contains('hidden');"
            "console.log(JSON.stringify({afterDown:afterDown, cleared:cleared, afterUp:afterUp,"
            " sameGroupHidden:sameGroupHidden, noInferenceHidden:noInferenceHidden}));"
        ),
    )
    assert result["afterDown"]["visible"] is True
    assert "с «взрослые» на «дети»" in result["afterDown"]["text"]
    assert "20 кг" in result["afterDown"]["text"]
    assert "вы ранее выбрали" in result["afterDown"]["text"]
    assert result["cleared"] is True
    assert result["afterUp"]["visible"] is True
    assert "с «дети» на «взрослые»" in result["afterUp"]["text"]
    assert result["sameGroupHidden"] is True, "an unchanged group must not raise a notice"
    assert result["noInferenceHidden"] is True, "an explicit choice must not raise a notice"


def test_age_inference_notice_is_wired_to_the_weight_input() -> None:
    source = _source()
    assert 'id="age-infer-notice"' in source
    assert "setActiveAge('child', {w:w})" in _js_function(source, "onWeightChange")
    assert "setActiveAge('adult', {w:w})" in _js_function(source, "onWeightChange")
    assert "clearAgeInferenceNotice();" in _js_function(source, "init")
    # An explicit click must switch the inference off (pre-existing guard) and
    # clear any pending notice.
    init_fn = _js_function(source, "init")
    assert "userPickedAge = true;" in init_fn
    assert "lastPickedAge = activeAge;" in init_fn


def test_placeholder_marker_is_intact() -> None:
    source = _source()
    assert source.count("__DB_PLACEHOLDER__") == 1
    assert '<script id="db-data" type="application/json">__DB_PLACEHOLDER__</script>' in source


# --------------------------------------------------------------------------
# Bug 9 — the remaining innerHTML sinks (stored DOM XSS in the DB renderers)
# --------------------------------------------------------------------------
#
# The two sinks an earlier pass closed (loadHistory, handleSearch) left every
# other DB-rendered region interpolating strings into innerHTML. Same defect
# class, lower tier of data provenance (extraction pipeline over clinical PDFs
# rather than physician input) but identical blast radius: the origin holds
# `personal-session-token` / `personal-owner-id` in live DOM inputs and can call
# /v2/personal/attest and /v2/personal/build-bundle.
#
# Fix strategy: build those regions with createElement + textContent, matching
# renderExtractedCandidates / renderPersonalCandidates / applyDiseaseSourceGate
# / selectDisease. The lint below is the durable half — it makes the *next* sink
# fail the build instead of waiting for the next audit.

# Trusted-text helpers permitted on the right-hand side of an HTML sink.
#
# A name may only be added here for a helper that provably cannot emit markup
# (an escape-only / allow-list-only function returning a constant-escaped
# string). A helper that concatenates untrusted input does not qualify, however
# carefully it is written. The set is intentionally empty today: every sink in
# the template is a literal or `''`, so no escape helper is needed yet.
ALLOWED_TRUSTED_TEXT_HELPERS: frozenset[str] = frozenset()

# `el.innerHTML = ...`, `el.innerHTML += ...`, `el.insertAdjacentHTML(...)`.
# `.innerHTML ==` / `.innerHTML !=` comparisons and the getter are not sinks.
_SINK_RE = re.compile(r"\.(?:innerHTML\s*(\+?=)|insertAdjacentHTML\s*\()")

# A right-hand side made only of string literals joined by `+` (optionally
# parenthesised) contains no values at all, so nothing can be injected.
_LITERAL_ONLY_RE = re.compile(r"^[\s+()]*$")

# A single call to an allow-listed trusted-text helper.
_ALLOWED_CALL_RE = re.compile(r"^\s*([A-Za-z_$][\w$]*)\s*\(.*\)\s*$", re.S)


def _scan_rhs(source: str, start: int) -> tuple[str, bool, str, int]:
    """Read one right-hand side / argument starting at `start`.

    Returns `(code_residue, has_template_interpolation, stop_char, end)`.
    `code_residue` is the expression with every string-literal body removed, so
    a caller can tell a literal-only concatenation (`++`) from one carrying a
    value (`++name+`). The scan is quote-, escape- and `${}`-aware so it does
    not stop early at a `;` or a `,` inside a literal or a nested call.
    """
    residue: list[str] = []
    interpolated = False
    index = start
    depth = 0
    mode = "code"
    quote = ""
    escaped = False
    in_template: list[bool] = []
    stop = "eof"
    while index < len(source):
        char = source[index]
        if mode == "code":
            if char in "'\"`":
                mode, quote, escaped = "quote", char, False
            elif char in "([{":
                depth += 1
            elif char in ")]}":
                depth -= 1
                if depth < 0:  # the `)` that closed the insertAdjacentHTML call
                    stop = char
                    break
                if depth == 0 and in_template and in_template[-1]:
                    in_template.pop()
                    mode, quote, escaped = "quote", "`", False
            elif depth == 0 and char in ";,":
                stop = char
                break
            else:
                residue.append(char)
        else:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                mode = "code"
            elif quote == "`" and char == "$" and source[index + 1 : index + 2] == "{":
                interpolated = True
                in_template.append(True)
                depth += 1
                mode, quote, escaped = "code", "", False
                index += 1
        index += 1
    return "".join(residue), interpolated, stop, index


def _html_sinks(source: str) -> list[dict]:
    """Enumerate every `.innerHTML =` / `+=` / `insertAdjacentHTML(` sink.

    For `insertAdjacentHTML` every argument is collected, not just the position:
    the position is a literal, the markup is the second argument.
    """
    found = []
    for match in _SINK_RE.finditer(source):
        operator = match.group(1)
        kind = "insertAdjacentHTML" if operator is None else "innerHTML " + operator
        residues: list[str] = []
        interpolated = False
        index = match.end()
        while True:
            residue, saw_interpolation, stop, end = _scan_rhs(source, index)
            residues.append(residue)
            interpolated = interpolated or saw_interpolation
            if stop != ",":
                break
            index = end + 1
        found.append(
            {
                "line": source.count("\n", 0, match.start()) + 1,
                "kind": kind,
                "rhs": " ".join(part for part in residues if part.strip()),
                "interpolated": interpolated,
            }
        )
    return found


def _sink_violations(source: str) -> list[str]:
    """Sinks whose right-hand side can carry a value into the HTML parser."""
    problems = []
    for sink in _html_sinks(source):
        if sink["interpolated"]:
            problems.append(
                "line %(line)d: %(kind)s uses a ${...} template interpolation" % sink
            )
            continue
        if _LITERAL_ONLY_RE.match(sink["rhs"]):
            continue
        allowed = _ALLOWED_CALL_RE.match(sink["rhs"])
        if allowed and allowed.group(1) in ALLOWED_TRUSTED_TEXT_HELPERS:
            continue
        problems.append(
            "line %(line)d: %(kind)s right-hand side is not a literal: %(rhs)s" % sink
        )
    return problems


def test_no_html_sink_in_the_template_receives_an_interpolated_value() -> None:
    """B9 lint: every innerHTML/insertAdjacentHTML sink must be literal-only.

    This is the durable fix. A renderer that reaches for `element.innerHTML =
    '<b>'+dbValue+'</b>'` fails here, with the line number, instead of shipping
    a stored-XSS sink for the next audit to find.
    """
    problems = _sink_violations(_source())
    assert problems == [], "unsafe DOM HTML sinks in the template:\n" + "\n".join(problems)


def test_html_sink_lint_actually_finds_and_classifies_the_sinks() -> None:
    """B9: guard the lint itself — a regex that matches nothing would pass vacuously."""
    source = _source()
    sinks = _html_sinks(source)
    assert len(sinks) >= 15, f"the lint only found {len(sinks)} sinks; the matcher is too narrow"
    assert all(sink["line"] > 0 for sink in sinks)
    assert not any(sink["interpolated"] for sink in sinks)
    # Every remaining sink is either a `= ''` reset or a fixed markup literal.
    assert all(_LITERAL_ONLY_RE.match(sink["rhs"]) for sink in sinks)


def test_html_sink_lint_flags_each_class_of_unsafe_right_hand_side() -> None:
    """B9: the lint must actually fail on the shapes it claims to reject."""
    bad = {
        "concatenation": "card.innerHTML = '<b>'+db.name+'</b>';",
        "template literal": "card.innerHTML = `<b>${db.name}</b>`;",
        "variable": "content.innerHTML = html;",
        "join": "warn.innerHTML = warnings.join('<br>');",
        "append": "content.innerHTML += db.note;",
        "insertAdjacentHTML": "el.insertAdjacentHTML('beforeend', db.note);",
        "call": "el.innerHTML = sanitize(db.note);",
    }
    for label, line in bad.items():
        assert _sink_violations(line) != [], f"the lint failed to flag a {label} sink"
    good = [
        "box.innerHTML = '';",
        "box.innerHTML = '<p class=\"text-xs\">Нет форм для этого пути</p>';",
        "box.innerHTML = '<span>' + '</span>';",
        "el.insertAdjacentHTML('beforeend', '<br>');",
    ]
    for line in good:
        assert _sink_violations(line) == [], f"the lint flagged a literal sink: {line}"


def test_trusted_text_helper_allow_list_is_empty_and_intentional() -> None:
    """B9: the allow-list is a decision, not an accidental leftover."""
    assert ALLOWED_TRUSTED_TEXT_HELPERS == frozenset()


# --------------------------------------------------------------------------
# B9 behaviour: every DB-rendered region must escape DB strings as text
# --------------------------------------------------------------------------
#
# The Node harness models the one guarantee that matters: a value written with
# `textContent` cannot become a tag (the stub escapes it when serialising), while
# a value concatenated into `innerHTML` reaches the HTML parser verbatim. Each
# test therefore asserts three things about the same payload:
#   * no `img` element node was created anywhere under the container,
#   * the serialised markup carries the payload escaped, and
#   * the payload is still *shown* to the physician, as text.

_XSS_INSPECTOR = (
    "function walk(node, out){"
    "  out = out || [];"
    "  (node.children||[]).forEach(function(c){ if(c instanceof El){ out.push(c.id); walk(c, out); } });"
    "  return out;"
    "}"
    "function report(box){"
    "  var nodes = walk(box);"
    "  return {"
    "    html: box.innerHTML,"
    "    text: box.textContent,"
    "    leaked: box.innerHTML.indexOf('<img')>=0,"
    "    escaped: box.innerHTML.indexOf('&lt;img')>=0,"
    "    img_nodes: nodes.filter(function(id){ return id === '<img>'; }),"
    "    br_nodes: nodes.filter(function(id){ return id === '<br>'; }).length"
    "  };"
    "}"
)


def _assert_payload_is_inert(result: dict, where: str) -> None:
    assert result["leaked"] is False, f"{where}: the payload reached the HTML parser verbatim"
    assert result["img_nodes"] == [], f"{where}: a live <img> element node was created"
    assert result["escaped"] is True, f"{where}: the payload must survive as escaped text"
    assert "onerror" in result["text"], f"{where}: the DB value must still reach the physician"


def test_render_scenarios_never_parses_a_scenario_name_as_markup() -> None:
    """B9: s.name comes out of the PDF extraction pipeline and lands on the card.

    The second scenario does not match the active age group, so the
    "Не подходит…" branch is exercised too.
    """
    globals_js = (
        "let activeAge='adult';\n"
        "function selectScenario(){}\n"
        "let activeDisease = " + _lit(
            {
                "scenarios": [
                    {"id": "s1", "name": "Схема " + XSS_PAYLOAD, "age_group": "all"},
                    {"id": "s2", "name": "Детская " + XSS_PAYLOAD, "age_group": "child"},
                ]
            }
        ) + ";\n"
    )
    result = _run(["renderScenarios"], globals_js, _XSS_INSPECTOR + "renderScenarios();console.log(JSON.stringify(report($('scenario-list'))));")
    _assert_payload_is_inert(result, "renderScenarios")
    assert "Не подходит для выбранной возрастной группы" in result["text"]


def test_render_lines_never_parses_inn_or_indication_note_as_markup() -> None:
    """B9: the drug card carries the МНН and the indication note from the DB."""
    globals_js = (
        "let activeAge='adult';\n"
        "function selectDrug(){}\n"
        "const DRUG_CLASSES = " + _lit({}) + ";\n"
        "const DB = " + _lit({"drugs_reference": {"x": {"inn": "МНН " + XSS_PAYLOAD}}}) + ";\n"
        "let activeScenario = " + _lit(
            {
                "lines": [
                    {
                        "line_number": 1,
                        "combo_therapy": True,
                        "drugs": [{"drug_ref": "x", "indication_note": "Показание " + XSS_PAYLOAD}],
                    }
                ]
            }
        ) + ";\n"
    )
    result = _run(
        ["getDrugRefs", "checkAllergyStatus", "allergyBadge", "renderLines"],
        globals_js,
        _XSS_INSPECTOR + "renderLines(0,0);console.log(JSON.stringify(report($('drug-list'))));",
    )
    _assert_payload_is_inert(result, "renderLines")


def test_render_forms_never_parses_a_form_concentration_or_note_as_markup() -> None:
    """B9: the form chip's concentration/notes are DB strings."""
    globals_js = (
        "let activeAge='adult';\n"
        "let currentRouteGroup='po';\n"
        "let activeFormIdx=0;\n"
        "function calculate(){}\n"
        "const DB = " + _lit(
            {
                "drugs_reference": {
                    "x": {
                        "forms": [
                            {
                                "form_type": "suspension",
                                "concentration": "400 мг/5 мл " + XSS_PAYLOAD,
                                "notes": "По инструкции " + XSS_PAYLOAD,
                                "concentration_mg_per_ml": 80,
                            }
                        ],
                        "availability_note": "Форма " + XSS_PAYLOAD,
                    }
                }
            }
        ) + ";\n"
        "let activeDrug = " + _lit({"drug_ref": "x"}) + ";\n"
    )
    result = _run(
        ["getDrugRefs", "renderFormChips", "renderForms"],
        globals_js,
        _XSS_INSPECTOR + "renderForms();console.log(JSON.stringify(report($('form-grid'))));",
    )
    _assert_payload_is_inert(result, "renderForms/renderFormChips")


def test_open_guideline_modal_never_parses_line_label_or_inn_as_markup() -> None:
    """B9: the evidence modal prints МНН, the regimen and the line label."""
    globals_js = (
        "let activeDisease = " + _lit(
            {
                "name": "Отит",
                "cr_id": "123",
                "cr_year": "2024",
                "mkb10": ["H66"],
                "indications": ["Средний отит"],
            }
        ) + ";\n"
        "let activeScenario = " + _lit(
            {
                "lines": [
                    {
                        "line_number": 1,
                        "line_label": "Стартовая " + XSS_PAYLOAD,
                        "drugs": [
                            {
                                "drug_ref": "x",
                                "regimens": [{"dose_mg_kg_day": "30 " + XSS_PAYLOAD, "freq_per_day": 3}],
                            }
                        ],
                    }
                ]
            }
        ) + ";\n"
        "const DB = " + _lit({"drugs_reference": {"x": {"inn": "МНН " + XSS_PAYLOAD}}}) + ";\n"
        "let activeDrug = null;\n"
    )
    result = _run(
        ["getDrugRefs", "doseUnitOf", "fmtDose", "formatUnits", "openGuidelineModal"],
        globals_js,
        _XSS_INSPECTOR + "openGuidelineModal();console.log(JSON.stringify(report($('modal-cr-lines'))));",
    )
    _assert_payload_is_inert(result, "openGuidelineModal")


def test_fill_prescription_form_never_parses_a_drug_name_or_solvent_as_markup() -> None:
    """B9: the printed Rp. block, the Latin injection block and the D.S. signa."""
    fixture = _fixture_db()
    payload = _lit(XSS_PAYLOAD)
    globals_js = (
        f"const DB = {_lit(fixture)};\n"
        "let activeAge='child';\nlet userPickedAge=false;\nlet lastPickedAge=null;\n"
        "let dbBlockingErrors=[];\nlet activeRegimenIdx=0;\n"
        "let activeFormIdx=0;let currentRouteGroup='iv';let activeRouteKey='iv_bolus';let activeVialIdx=0;\n"
        "let activeLine=null;\n"
        # 'x'/'y' are deliberately absent from LATIN_INN so the printed name comes
        # from the DB reference rather than the hard-coded Latin table.
        f"let activeDrug={_lit({'combo_ref': ['x', 'y'], 'regimens': [{'age_group': 'all', 'single_dose_mg': 40, 'freq_per_day': 3, 'duration_days': 7}]})};\n"
        "let activeDisease={name:'x',cr_id:'1',cr_year:'2024',source_verification_status:'UNVERIFIED',mkb10:['H66']};\n"
        "$('weight').value='20';\n"
        f"DB.drugs_reference.x = {{inn:'МНН ' + {payload},"
        f" forms:[{{form_type:'powder_for_injection',concentration:'1000 мг ' + {payload}}}],"
        f" dilution:{{iv_bolus:{{solvent_options:[{{solvent:'Физраствор ' + {payload},solvent_ml:10,"
        f"final_volume_ml:10,final_concentration_mg_ml:100,vial_mg:1000}}],"
        f"steps:['Шаг 1. ' + {payload}],cautions:'Осторожно'}}}}}};\n"
        f"DB.drugs_reference.y = {{inn:'Второй компонент ' + {payload},"
        f" forms:[{{form_type:'solution_iv',concentration:'40 мг/мл ' + {payload}}}]}};\n"
    )
    funcs = [
        "getDrugRefs",
        "ageGroupLabel",
        "ageEligibleRegimens",
        "getActiveRegimen",
        "ageRegimenBlockReason",
        "weightBlockReason",
        "weightWarnReason",
        "dbBlockReason",
        "calculationBlockReason",
        "dbTrustState",
        "buildFingerprint",
        "buildIdentifier",
        "doseUnitOf",
        "computeDose",
        "formatUnits",
        "fmtDose",
        "diseaseSourceStatus",
        "formatTablets",
        "getStandardBottleMl",
        "calculateCoursePackages",
        "formTypeRussian",
        "fillPrescriptionForm",
    ]
    result = _run_with_consts(
        funcs,
        ["LATIN_INN", "LATIN_FORM", "LATIN_ROUTE", "LATIN_FREQ"],
        globals_js,
        _XSS_INSPECTOR + "fillPrescriptionForm();console.log(JSON.stringify({drugs:report($('rx-drugs')),"
        "inj:report($('rx-injection-details')),signa:$('rx-signa-text').textContent}));",
    )
    _assert_payload_is_inert(result["drugs"], "fillPrescriptionForm (Rp. block)")
    _assert_payload_is_inert(result["inj"], "fillPrescriptionForm (Latin injection block)")
    assert "3 раза в день" in result["signa"], "the D.S. signa must still be produced"


def test_render_dilution_block_never_parses_solvent_notes_or_steps_as_markup() -> None:
    """B9: the dilution card, the step list and the <br><br>-joined warnings."""
    globals_js = (
        "let activeAge='child';\n"
        "const ref = " + _lit({"interactions": []}) + ";\n"
        "const routeData = " + _lit(
            {
                "child_solvent_warning": "Осторожно " + XSS_PAYLOAD,
                "contraindications": "Противопоказано " + XSS_PAYLOAD,
                "cautions": "Не смешивать",
                "steps": ["1. Развести " + XSS_PAYLOAD, "2. Ввести"],
            }
        ) + ";\n"
        "const selectedVial = " + _lit(
            {
                "solvent": "Растворитель " + XSS_PAYLOAD,
                "notes": "Примечание " + XSS_PAYLOAD,
                "solvent_ml": 10,
                "final_volume_ml": 10,
                "final_concentration_mg_ml": 100,
                "vial_mg": 1000,
            }
        ) + ";\n"
    )
    result = _run(
        ["formatUnits", "renderDilutionBlock"],
        globals_js,
        _XSS_INSPECTOR + "renderDilutionBlock(ref,'iv_bolus',500,selectedVial,routeData);"
        "console.log(JSON.stringify({solvents:report($('dilution-solvents')),"
        "steps:report($('dilution-steps')),warn:report($('dilution-warn-text'))}));",
    )
    _assert_payload_is_inert(result["solvents"], "renderDilutionBlock (solvent card)")
    _assert_payload_is_inert(result["steps"], "renderDilutionBlock (steps)")
    _assert_payload_is_inert(result["warn"], "renderDilutionBlock (warnings)")
    # The two warnings are still separated by a real <br><br>, not by lost layout.
    assert result["warn"]["br_nodes"] == 2, "the <br><br> warning separator must survive"

def test_render_reconstitution_never_parses_solvent_steps_or_storage_as_markup() -> None:
    """B9: the preparation block for a powder for solution."""
    globals_js = ""
    body = (
        _XSS_INSPECTOR
        + "renderReconstitution({concentration:'1 г ' + "
        + _lit(XSS_PAYLOAD)
        + ", reconstitution:{solvent:'Растворитель ' + "
        + _lit(XSS_PAYLOAD)
        + ", solvent_ml:10, final_volume_ml:10, steps:['Шаг ' + "
        + _lit(XSS_PAYLOAD)
        + "], storage:'Хранить ' + "
        + _lit(XSS_PAYLOAD)
        + "}});"
        "console.log(JSON.stringify(report($('reconstitution-content'))));"
    )
    result = _run(["renderReconstitution"], globals_js, body)
    _assert_payload_is_inert(result, "renderReconstitution")


def test_render_combo_components_never_parses_inn_or_component_note_as_markup() -> None:
    """B9: the combination card and the component's own regimen note."""
    globals_js = (
        "let activeAge='child';\n"
        "const DB = " + _lit({"drugs_reference": {}}) + ";\n"
        "const reg = " + _lit(
            {
                "age_group": "all",
                "single_dose_mg": 2000,
                "freq_per_day": 1,
                "duration_days": 7,
                "component_regimens": {
                    "x": {"single_dose_mg": 40, "freq_per_day": 3, "duration_days": 7, "component_note": "Компонент " + XSS_PAYLOAD},
                },
            }
        ) + ";\n"
    )
    result = _run(
        ["getDrugRefs", "doseUnitOf", "computeDose", "formatUnits", "fmtDose", "renderComboComponents"],
        globals_js,
        _XSS_INSPECTOR + "DB.drugs_reference.x = {inn:'МНН ' + "
        + _lit(XSS_PAYLOAD)
        + ",forms:[{form_type:'tablet',concentration:'500 мг'}]};"
        "renderComboComponents(['x'], reg, 20);"
        "const rep = report($('combo-block'));const text = $('combo-block').textContent;"
        "DB.drugs_reference.y = {inn:'Без режима',forms:[{form_type:'tablet',concentration:'500 мг'}]};"
        "renderComboComponents(['y'], reg, 20);"
        "console.log(JSON.stringify(Object.assign(rep, {partnerText: text, orphan: $('combo-block').textContent,"
        " lines: comboComponentLines(['x', 'y'], reg, 20)})));",
    )
    _assert_payload_is_inert(result, "renderComboComponents")
    # the partner is dosed from ITS regimen (40 mg × 3), never from the main drug's 2000 mg
    assert "40 мг" in result["partnerText"] and "2000 мг" not in result["partnerText"], result["partnerText"]
    # a partner without component_regimens is fail-visible, not dosed with the main drug's numbers
    assert "режим компонента не задан в БД" in result["orphan"] and "2000 мг" not in result["orphan"], result["orphan"]
    assert result["lines"][0].startswith("Компонент комбинации: МНН ") and "по 40 мг 3 р/д" in result["lines"][0]
    assert result["lines"][1] == "Компонент комбинации: Без режима — режим компонента не задан в БД — дозу уточните по КР (расчёт не выполнен)"


def test_render_drug_meta_never_parses_drug_metadata_as_markup() -> None:
    """B9: the drug metadata table is built from nine DB fields."""
    globals_js = (
        "let activeDisease = "
        + _lit(
            {
                "cr_id": "42",
                "cr_year": "2024",
                "source_url": "https://cr.minzdrav.gov.ru/recomend/42",
                "cr_note": "Основание " + XSS_PAYLOAD,
            }
        )
        + ";\n"
    )
    body = (
        _XSS_INSPECTOR
        + "const ref = {inn:'МНН ', renal_adjustment:'Нет ', hepatic_adjustment:'', pregnancy_category:'',"
        " monitoring:'Контроль ', interactions:'Ca', storage_reconstituted:'При ', class:'Пенициллины ' + "
        + _lit(XSS_PAYLOAD)
        + "};"
        "renderDrugMeta(ref, {});"
        "console.log(JSON.stringify(report($('drug-meta'))));"
    )
    result = _run(["renderDrugMeta", "metaRow"], globals_js, body)
    _assert_payload_is_inert(result, "renderDrugMeta")


def test_render_po_instruction_never_parses_a_form_concentration_as_markup() -> None:
    """B9: the oral instruction, the course summary and the fail-closed message."""
    globals_js = (
        "let activeAge='child';\nlet activeDrug=" + _lit({"drug_ref": "vancomycin"}) + ";\n"
        "const DB = " + _lit({"drugs_reference": {}}) + ";\n"
        "const reg = " + _lit({"age_group": "all", "single_dose_mg": 250, "freq_per_day": 3, "duration_days": 7}) + ";\n"
        "const ref = " + _lit({"inn": "Ванкомицин"}) + ";\n"
        "const poisoned = {form_type:'suspension', concentration:'250 мг/5 мл ' + "
        + _lit(XSS_PAYLOAD)
        + ", concentration_mg_per_ml:50};\n"
        "const solidForm = {form_type:'tablet', concentration:'500 мг ' + "
        + _lit(XSS_PAYLOAD)
        + ", concentration_mg_per_ml:0};\n"
        "const unknownForm = {form_type:'suspension', concentration:'', concentration_mg_per_ml:0};\n"
    )
    body = (
        _XSS_INSPECTOR
        + "renderPO(reg, poisoned, ref, 20, 500, 1500, false, false);"
        "const liquid=report($('po-instruction'));const liquidPkg=report($('po-package-text'));"
        "renderPO(reg, solidForm, ref, 70, 500, 1500, false, false);"
        "const solid=report($('po-instruction'));"
        "renderPO(reg, unknownForm, ref, 20, 500, 1500, false, false);"
        "const blocked=report($('po-instruction'));"
        # The pre-existing coursePkg.summary string, tags stripped: the DOM text
        # must still say exactly the same thing to the physician.
        "const expected=calculateCoursePackages(reg, poisoned, 500, 1500, 20).summary.replace(/<[^>]+>/g, '');"
        "console.log(JSON.stringify({liquid,liquidPkg,solid,blocked,expected}));"
    )
    result = _run(
        [
            "getDrugRefs",
            "doseUnitOf",
            "formatUnits",
            "formatTablets",
            "getStandardBottleMl",
            "fmtDose",
            "calculateCoursePackages",
            "renderPO",
        ],
        globals_js,
        body,
    )
    for key, where in (
        ("liquid", "renderPO (suspension)"),
        ("liquidPkg", "renderPO (course summary)"),
        ("solid", "renderPO (tablet)"),
        ("blocked", "renderPO (no concentration)"),
    ):
        assert result[key]["leaked"] is False, f"{where}: payload reached the HTML parser"
        assert result[key]["img_nodes"] == [], f"{where}: a live <img> element node was created"
    for key in ("liquid", "solid"):
        _assert_payload_is_inert(result[key], f"renderPO {key}")
    # The course summary carries only computed numbers, and is now assembled from
    # the numeric coursePkg fields rather than from its ready-made HTML string.
    assert "<b>" not in result["liquidPkg"]["html"]
    assert result["liquidPkg"]["text"] == result["expected"], "the course summary text must be unchanged"
    assert "Объём не рассчитан" in result["blocked"]["text"], "the fail-closed message must still render"


def test_apply_disease_source_gate_banner_carries_no_markup() -> None:
    """B9 regression guard: the source banner is DOM-built on every branch."""
    globals_js = "const DOSE_BLOCK_CLASS = 'blocked';\n"
    body = (
        _XSS_INSPECTOR
        + "applyDiseaseSourceGate({cr_id:'654', cr_year:2021, source_verification_status:'CR_REFERENCE_CALCULATION'});"
        "const reference=report($('source-calculation-block'));"
        "applyDiseaseSourceGate({source_verification_status:'<img src=x onerror=\"globalThis.__pwned=1\">'});"
        "const injected=report($('source-calculation-block'));"
        "console.log(JSON.stringify({reference,injected,status:$('source-calculation-block').dataset.sourceStatus}));"
    )
    result = _run(["diseaseSourceStatus", "applyDiseaseSourceGate"], globals_js, body)
    assert result["status"] == "UNVERIFIED", "markup in a DB status must normalise away"
    assert result["injected"]["leaked"] is False
    assert result["injected"]["img_nodes"] == []
    assert "КР МЗ РФ" in result["reference"]["text"], "the reference banner must still render"


def test_init_failure_does_not_render_the_exception_message() -> None:
    """B9: the init() catch must not put an untrusted exception string in the DOM."""
    body = (
        "globalThis.__logged=[];"
        "const original=console.error;"
        "console.error=function(){ globalThis.__logged.push(String(arguments[0])); };"
        "$('db-data').textContent='{not json';"
        "init();"
        "console.error=original;"
        "const box=$('empty-state');"
        "console.log(JSON.stringify({text:box.textContent,html:box.innerHTML,"
        " logged:globalThis.__logged.length, raw_error:box.innerHTML.indexOf('Unexpected')>=0"
        " || box.textContent.indexOf('JSON')>=0}));"
    )
    result = _run(["init"], "", body)
    assert result["raw_error"] is False, "the raw exception text still reaches the DOM"
    assert result["logged"] == 1, "the failure must still be logged for whoever debugs the build"
    assert "Ошибка загрузки БД" in result["text"]
    assert "консоли" in result["text"]


def test_render_injection_never_parses_the_frequency_or_solvent_as_markup() -> None:
    """B9: the parenteral instruction and the chosen-vial button label."""
    globals_js = (
        "let activeAge='child';\n"
        "let activeRouteKey='iv_bolus';\n"
        "let activeVialIdx=0;\n"
        "let currentRouteGroup='iv';\n"
        "const reg = " + _lit({"age_group": "all", "single_dose_mg": 40, "freq_per_day": "3 " + XSS_PAYLOAD, "duration_days": 7}) + ";\n"
        "const form = " + _lit({"form_type": "powder_for_injection", "concentration": "1000 мг"}) + ";\n"
        "const ref = " + _lit(
            {
                "inn": "Ванкомицин",
                "dilution": {
                    "iv_bolus": {
                        "solvent_options": [
                            {"solvent": "Растворитель " + XSS_PAYLOAD, "solvent_ml": 10, "final_volume_ml": 10, "final_concentration_mg_ml": 100}
                        ]
                    }
                },
            }
        ) + ";\n"
    )
    result = _run(
        ["doseUnitOf", "formatUnits", "fmtDose", "computeInjectableMl", "routeKeyLabel", "renderInjection", "renderDilutionBlock"],
        globals_js,
        _XSS_INSPECTOR
        + "renderInjection(reg, form, ref, 20, 40, 120, false, false);"
        "const instr=report($('inj-instruction'));"
        "const vials=report($('vial-list'));"
        "console.log(JSON.stringify({instr,vials,route:$('inj-route-label').textContent}));",
    )
    _assert_payload_is_inert(result["instr"], "renderInjection (instruction)")
    _assert_payload_is_inert(result["vials"], "renderInjection (vial selector)")
    assert result["route"] == "в/в струйно", "the route label must still be produced"


# --------------------------------------------------------------------------
# Audit 2026-10-14 — patient context, honest source labels, solid-form maths
# --------------------------------------------------------------------------

_RX_FUNCS = [
    "getDrugRefs", "ageGroupLabel", "ageEligibleRegimens", "getActiveRegimen",
    "ageRegimenBlockReason", "weightBlockReason", "weightWarnReason", "dbBlockReason",
    "calculationBlockReason", "dbTrustState", "buildFingerprint", "buildIdentifier",
    "doseUnitOf", "computeDose", "formatUnits", "fmtDose", "diseaseSourceStatus",
    "formatTablets", "getStandardBottleMl", "calculateCoursePackages", "formTypeRussian",
    "fillPrescriptionForm",
]
_RX_CONSTS = ["LATIN_INN", "LATIN_FORM", "LATIN_ROUTE", "LATIN_FREQ"]


def _rx_globals(drug_ref: dict, active_drug: dict, route_group: str, route_key: str, weight: str = "70") -> str:
    fixture = _fixture_db()
    fixture["drugs_reference"]["d"] = drug_ref
    return (
        f"const DB = {_lit(fixture)};\n"
        "let activeAge='adult';\nlet userPickedAge=false;\nlet lastPickedAge=null;\n"
        "let dbBlockingErrors=[];\nlet activeRegimenIdx=0;\n"
        f"let activeFormIdx=0;let currentRouteGroup='{route_group}';let activeRouteKey={_lit(route_key)};let activeVialIdx=0;\n"
        "let activeLine=null;\n"
        f"let activeDrug={_lit(active_drug)};\n"
        "let activeDisease={name:'x',cr_id:'654',cr_year:2021,source_verification_status:'CR_REFERENCE_CALCULATION',mkb10:['J18']};\n"
        f"$('weight').value='{weight}';\n"
    )


def test_apply_disease_source_gate_does_not_accumulate_banners_across_selections() -> None:
    """Regression: the reference branch appended children without clearing them first."""
    body = (
        "applyDiseaseSourceGate({cr_id:'654',cr_year:2021,source_verification_status:'CR_REFERENCE_CALCULATION'});"
        "applyDiseaseSourceGate({cr_id:'—',cr_note:'СКАТ 2018',source_verification_status:'NO_FEDERAL_CR_EXPERT_BASIS'});"
        "const b=$('source-calculation-block');"
        "console.log(JSON.stringify({children:b.children.length,text:b.innerHTML,status:b.dataset.sourceStatus}));"
    )
    result = _run(["diseaseSourceStatus", "applyDiseaseSourceGate"], "", body)
    assert result["children"] == 2, "exactly one caption + one badge after the second selection"
    assert result["text"].count("Справочный расчёт") == 0, "the previous nosology's banner must be gone"
    assert "СКАТ 2018" in result["text"] and "БЕЗ КР" in result["text"]
    assert result["status"] == "NO_FEDERAL_CR_EXPERT_BASIS"


def test_source_banner_wording_per_status() -> None:
    body = (
        "const out={};"
        "for(const d of ["
        " {k:'cr',cr_id:'654',cr_year:2021,source_verification_status:'CR_REFERENCE_CALCULATION'},"
        " {k:'spec',cr_id:'314',source_verification_status:'SOURCE_SPEC_PENDING_CALCULATOR_BINDING'},"
        " {k:'nocr',cr_id:'—',cr_note:'IDSA 2019',source_verification_status:'NO_FEDERAL_CR_EXPERT_BASIS'},"
        " {k:'nocr_nonote',cr_id:'—',source_verification_status:'NO_FEDERAL_CR_EXPERT_BASIS'},"
        " {k:'unknown',source_verification_status:'SOMETHING_ELSE'},"
        " {k:'blocked',calculation_blocked:true,calculation_block_reason:'нет источника'}"
        "]){ const ok=applyDiseaseSourceGate(d); out[d.k]={ok:ok,text:$('source-calculation-block').innerHTML}; }"
        "console.log(JSON.stringify(out));"
    )
    result = _run(["diseaseSourceStatus", "applyDiseaseSourceGate"], "", body)
    assert "№654 (2021)" in result["cr"]["text"] and "не проходила построчную верификацию" in result["cr"]["text"]
    assert "построчная привязка таблиц ещё не подтверждена" in result["spec"]["text"]
    assert "Нет федеральной КР" in result["nocr"]["text"] and "IDSA 2019" in result["nocr"]["text"]
    assert "не документировано" in result["nocr_nonote"]["text"]
    assert "НЕ ВЕРИФИЦИРОВАНО" in result["unknown"]["text"] and "SOMETHING_ELSE" in result["unknown"]["text"]
    assert result["blocked"]["ok"] is False and "РАСЧЁТ ЗАБЛОКИРОВАН" in result["blocked"]["text"]
    assert all(v["ok"] is True for k, v in result.items() if k != "blocked")


def test_disease_source_label_never_invents_a_federal_guideline() -> None:
    body = (
        "console.log(JSON.stringify({"
        "cr:diseaseSourceLabel({cr_id:'654',cr_year:2021}),"
        "cr_noyear:diseaseSourceLabel({cr_id:'313_3'}),"
        "dash:diseaseSourceLabel({cr_id:'—',cr_year:2024,cr_note:'СКАТ 2018'}),"
        "dash_nonote:diseaseSourceLabel({cr_id:'—'}),"
        "none:diseaseSourceLabel({}),"
        "fed:[isFederalCrId('654'),isFederalCrId('313_3'),isFederalCrId('—'),isFederalCrId(''),isFederalCrId(null),isFederalCrId('IDSA')]"
        "}));"
    )
    result = _run([], "", body)
    assert result["cr"] == "КР МЗ РФ #654 (2021)"
    assert result["cr_noyear"] == "КР МЗ РФ #313_3 (год не указан)"
    assert result["dash"] == "без федеральной КР — основание: СКАТ 2018"
    assert "2024" not in result["dash"], "a year must not be attached to a non-existent CR"
    assert result["dash_nonote"] == "без федеральной КР — основание не документировано"
    assert result["none"].startswith("без федеральной КР")
    assert result["fed"] == [True, True, False, False, False, False]


def test_format_tablets_never_splits_a_capsule_and_shows_the_actual_dose() -> None:
    body = (
        "const cap={form_type:'capsule',concentration:'500 мг'};"
        "const tab={form_type:'tablet',concentration:'500 мг'};"
        "console.log(JSON.stringify({"
        "cap_exact:formatTablets(1000,cap), cap_half:formatTablets(750,cap), cap_small:formatTablets(100,cap),"
        "tab_exact:formatTablets(1000,tab), tab_half:formatTablets(750,tab), tab_third:formatTablets(333,tab),"
        "none:formatTablets(0,tab), susp:formatTablets(500,{form_type:'suspension',concentration:'250 мг/5 мл'}),"
        "units_cap:solidUnitsPerDose(750,cap).units, units_tab:solidUnitsPerDose(750,tab).units"
        "}));"
    )
    result = _run(["formatTablets"], "", body)
    assert result["cap_exact"] == "(2 капс 500 мг)"
    assert result["cap_half"] == "(~2 капс 500 мг = 1000 мг, +33 % к расчётной; капсулы не делятся)"
    assert result["cap_small"] == "(~1 капс 500 мг = 500 мг, +400 % к расчётной; капсулы не делятся)"
    assert result["tab_exact"] == "(2 таб 500 мг)"
    assert result["tab_half"] == "(1.5 таб 500 мг)", "a half tablet is exact, not a rounding"
    assert result["tab_third"] == "(~0.5 таб 500 мг = 250 мг, -25 % к расчётной)"
    assert result["none"] == "" and result["susp"] == ""
    assert result["units_cap"] == 2 and result["units_tab"] == 1.5


def test_compute_dose_understands_per_kg_per_dose_regimens() -> None:
    body = (
        "const reg={age_group:'child',dose_mg_kg_per_dose:7,freq_per_day:3,max_daily_mg:2000};"
        "const a=computeDose(reg,20,'мг'); const b=computeDose(reg,0,'мг'); const c=computeDose(reg,120,'мг');"
        "console.log(JSON.stringify({a:a,b:b,c:c}));"
    )
    result = _run(["computeDose"], "", body)
    assert result["a"]["singleMg"] == 140 and result["a"]["dailyMg"] == 420 and result["a"]["needWeight"] is False
    assert result["b"]["needWeight"] is True and result["b"]["dailyMg"] == 0
    # 120 kg × 7 × 3 = 2520 > 2000 → capped, single dose re-derived from the ceiling
    assert result["c"]["capped"] is True and result["c"]["dailyMg"] == 2000 and abs(result["c"]["singleMg"] - 2000 / 3) < 1e-9


def test_regimen_summary_keeps_units_honest() -> None:
    body = (
        "console.log(JSON.stringify(["
        "regimenSummary({dose_mg_kg_day:45,freq_per_day:3,max_daily_mg:3000},'мг'),"
        "regimenSummary({dose_mg_kg_per_dose:7,freq_per_day:3},'мг'),"
        "regimenSummary({single_dose_mg:1000000,freq_per_day:4},'ЕД'),"
        "regimenSummary({dose_mg_day_fixed:1500,freq_per_day:3},'мг'),"
        "regimenSummary({regimen_label:'по схеме',dose_mg_kg_day:45},'мг'),"
        "regimenSummary({duration_note:'однократно'},'мг')"
        "]));"
    )
    result = _run(["fmtDose", "formatUnits"], "", body)
    assert result[0] == "45 мг/кг/сут • 3 р/д • макс 3000 мг/сут"
    assert result[1] == "7 мг/кг на приём • 3 р/д"
    assert result[2].startswith("1") and "ЕД на приём • 4 р/д" in result[2]
    assert result[3] == "1500 мг/сут • 3 р/д"
    assert result[4] == "по схеме"
    assert result[5] == "однократно"


def test_search_typo_tolerance_is_one_edit_on_a_word_prefix() -> None:
    body = (
        "console.log(JSON.stringify({"
        "edits:[withinOneEdit('пневмония','пневмания'),withinOneEdit('тонзилит','тонзиллит'),withinOneEdit('пнвемония','пневмония'),"
        "withinOneEdit('синусит','синусид'),withinOneEdit('отит','отит'),withinOneEdit('ангина','ангиоп'),withinOneEdit('abc','abcde')],"
        "hits:[fuzzyWordHit('внебольничная пневмония у детей','пневмания'),fuzzyWordHit('острый тонзиллит','тонзилит'),"
        "fuzzyWordHit('амоксициллин','амоксицилин'),fuzzyWordHit('острый синусит','синусид'),fuzzyWordHit('отит','отти'),"
        "fuzzyWordHit('менингококковая инфекция','менингит'),fuzzyWordHit('холецистит','холера')]"
        "}));"
    )
    result = _run(["withinOneEdit", "fuzzyWordHit"], "", body)
    assert result["edits"] == [True, True, True, True, True, False, False]
    assert result["hits"] == [True, True, True, True, False, False, False]


def test_times_a_day_declension() -> None:
    """Rp Signa / printed form said «1 раза в день» and «6 раза в день»."""
    result = _run(["timesADay"], "", "console.log(JSON.stringify([1,2,3,4,5,6,8,11,12,21,22,0].map(timesADay)));")
    assert result == [
        "1 раз в день", "2 раза в день", "3 раза в день", "4 раза в день", "5 раз в день",
        "6 раз в день", "8 раз в день", "11 раз в день", "12 раз в день", "21 раз в день",
        "22 раза в день", "0 раз в день",
    ]


def test_format_units_never_drops_the_decimal_point() -> None:
    """1 050 000 ЕД (150 000 ЕД/кг/сут × 7 кг) once read «15 млн ЕД»: the old
    `.replace('.0','')` ate the point. Scale only when two decimals are exact,
    otherwise print the number in full with thousand spaces."""
    body = (
        "console.log(JSON.stringify([1050000,1005000,1030000,2000000,1500000,1000000,1250000,"
        "24000000,175000,625000,20050,1050,1000,999,0].map(formatUnits)));"
    )
    result = _run(["formatUnits"], "", body)
    assert result == [
        "1.05 млн", "1 005 000", "1.03 млн", "2 млн", "1.5 млн", "1 млн", "1.25 млн",
        "24 млн", "175 тыс", "625 тыс", "20.05 тыс", "1.05 тыс", "1 тыс", "999", "0",
    ]
    assert _run(["fmtDose", "formatUnits"], "", "console.log(JSON.stringify(fmtDose(1050000,'ЕД')));") == "1.05 млн ЕД"


def test_age_parsing_and_group_boundaries() -> None:
    body = (
        "console.log(JSON.stringify({"
        "days:[parseAgeToDays('10','days'),parseAgeToDays('6','months'),parseAgeToDays('7','years'),parseAgeToDays('','years'),parseAgeToDays('-1','years'),parseAgeToDays('abc','years')],"
        "groups:[ageGroupFromDays(0),ageGroupFromDays(28),ageGroupFromDays(29),ageGroupFromDays(17*365.25+364),ageGroupFromDays(18*365.25),ageGroupFromDays(null)],"
        "restr:[parseAgeRestrictionDays('6 мес'),parseAgeRestrictionDays('18 лет'),parseAgeRestrictionDays('1 мес'),parseAgeRestrictionDays('28 дней'),parseAgeRestrictionDays('с 3 лет'),parseAgeRestrictionDays('2 нед'),parseAgeRestrictionDays('нет'),parseAgeRestrictionDays(null),parseAgeRestrictionDays('12 г'),parseAgeRestrictionDays('6 м.'),parseAgeRestrictionDays('5 мг')],"
        "fmt:[formatAgeDays(10),formatAgeDays(200),formatAgeDays(365.25*1),formatAgeDays(365.25*3),formatAgeDays(365.25*5),formatAgeDays(365.25*21)]"
        "}));"
    )
    result = _run(["parseAgeToDays", "ageGroupFromDays"], "", body)
    assert result["days"][0] == 10 and abs(result["days"][1] - 6 * 30.4375) < 1e-9 and abs(result["days"][2] - 7 * 365.25) < 1e-9
    assert result["days"][3:] == [None, None, None]
    assert result["groups"] == ["neonate", "neonate", "child", "child", "adult", None]
    assert abs(result["restr"][0] - 6 * 30.4375) < 1e-9 and abs(result["restr"][1] - 18 * 365.25) < 1e-9
    assert abs(result["restr"][2] - 30.4375) < 1e-9 and result["restr"][3] == 28
    assert abs(result["restr"][4] - 3 * 365.25) < 1e-9 and result["restr"][5] == 14
    # JS «\b» is ASCII-only: «12 г» / «6 м.» used to fall through to «проверьте вручную»
    assert result["restr"][6:8] == [None, None] and len(result["restr"]) == 11
    assert abs(result["restr"][8] - 12 * 365.25) < 1e-9 and abs(result["restr"][9] - 6 * 30.4375) < 1e-9
    assert result["restr"][10] is None, "«5 мг» is not an age"
    assert result["fmt"] == ["10 дн.", "7 мес", "12 мес", "3 года", "5 лет", "21 год"]


def test_age_restriction_flag_matrix() -> None:
    body = (
        "const ref={inn:'Доксициклин',age_restriction_min:'8 лет'};"
        "const adultOnly={inn:'Левофлоксацин',age_restriction_min:'18 лет'};"
        "const infant={inn:'Цефиксим',age_restriction_min:'6 мес'};"
        "const odd={inn:'X',age_restriction_min:'по инструкции'};"
        "const out={};"
        "activeAge='child'; patientAgeDays=5*365.25; out.child_5y_vs_8y=ageRestrictionFlag(ref);"
        "patientAgeDays=10*365.25; out.child_10y_vs_8y=ageRestrictionFlag(ref);"
        "patientAgeDays=null; out.child_unknown_vs_18y=ageRestrictionFlag(adultOnly);"
        "out.child_unknown_vs_6m=ageRestrictionFlag(infant);"
        "activeAge='neonate'; out.neonate_unknown_vs_6m=ageRestrictionFlag(infant);"
        "activeAge='adult'; out.adult_unknown_vs_18y=ageRestrictionFlag(adultOnly);"
        "out.adult_odd=ageRestrictionFlag(odd);"
        "out.none=ageRestrictionFlag({inn:'Y'});"
        "console.log(JSON.stringify(out));"
    )
    result = _run(["ageGroupLabel"], "let activeAge='child';\n", body)
    assert result["child_5y_vs_8y"]["level"] == "danger" and "5 лет" in result["child_5y_vs_8y"]["text"]
    assert result["child_10y_vs_8y"] is None
    assert result["child_unknown_vs_18y"]["level"] == "danger", "a child can never satisfy an 18-year minimum"
    assert result["child_unknown_vs_6m"]["level"] == "warn" and "Введите возраст" in result["child_unknown_vs_6m"]["text"]
    assert result["neonate_unknown_vs_6m"]["level"] == "danger"
    assert result["adult_unknown_vs_18y"] is None
    assert result["adult_odd"]["level"] == "warn" and "по инструкции" in result["adult_odd"]["text"]
    assert result["none"] is None


def test_pregnancy_and_renal_flags() -> None:
    body = (
        "const out={};"
        "$('patient-pregnancy').value='yes';"
        "out.contra=pregnancyFlag({inn:'Доксициклин',pregnancy_category:'Противопоказан'});"
        "out.tri=pregnancyFlag({inn:'Ко-тримоксазол',pregnancy_category:'Противопоказан в I и III триместрах'});"
        "out.caution=pregnancyFlag({inn:'Азитромицин',pregnancy_category:'С осторожностью'});"
        "out.ok=pregnancyFlag({inn:'Амоксициллин',pregnancy_category:'Разрешён'});"
        "out.ok_tri=pregnancyFlag({inn:'Нитрофурантоин',pregnancy_category:'Разрешён во II-III триместрах'});"
        "out.nodata=pregnancyFlag({inn:'Тинидазол',pregnancy_category:null});"
        "$('patient-pregnancy').value='no'; out.not_pregnant=pregnancyFlag({inn:'Доксициклин',pregnancy_category:'Противопоказан'});"
        "const cotrim={inn:'Ко-тримоксазол',renal_adjustment:'СКФ<30: коррекция дозы; СКФ<15 — противопоказан'};"
        "$('patient-gfr').value='20'; out.gfr20=renalFlag(cotrim);"
        "$('patient-gfr').value='10'; out.gfr10=renalFlag(cotrim);"
        "$('patient-gfr').value='45'; out.gfr45=renalFlag(cotrim);"
        "out.not_required=renalFlag({inn:'Доксициклин',renal_adjustment:'Не требуется'});"
        "out.generic=renalFlag({inn:'Гентамицин',renal_adjustment:'Коррекция по СКФ, ТЛМ'});"
        "out.nodata=renalFlag({inn:'Клиндамицин',renal_adjustment:null});"
        "$('patient-gfr').value='95'; out.generic_normal=renalFlag({inn:'Гентамицин',renal_adjustment:'Коррекция по СКФ, ТЛМ'});"
        "$('patient-gfr').value=''; out.no_gfr=renalFlag(cotrim);"
        "console.log(JSON.stringify(out));"
    )
    result = _run([], "", body)
    assert result["contra"]["level"] == "danger" and result["tri"]["level"] == "danger"
    assert result["caution"]["level"] == "warn" and result["ok"] is None
    assert result["ok_tri"]["level"] == "warn", "a trimester-restricted 'allowed' still needs a glance"
    assert result["nodata"]["level"] == "warn" and result["not_pregnant"] is None
    assert result["gfr20"]["level"] == "warn" and "СКФ<30" in result["gfr20"]["text"] and "БЕЗ почечной коррекции" in result["gfr20"]["text"]
    assert result["gfr10"]["level"] == "danger" and "противопоказан" in result["gfr10"]["text"]
    assert result["gfr45"] is None
    assert result["not_required"] is None
    assert result["generic"]["level"] == "warn" and result["generic_normal"] is None
    assert result["nodata"]["level"] == "warn" and result["no_gfr"] is None


def test_render_patient_safety_flags_builds_nodes_and_clears() -> None:
    fixture = _fixture_db()
    fixture["drugs_reference"]["doxy"] = {"inn": "Доксициклин " + XSS_PAYLOAD, "age_restriction_min": "8 лет " + XSS_PAYLOAD, "forms": []}
    body = (
        _XSS_INSPECTOR
        + "activeAge='child'; patientAgeDays=3*365.25;"
        "const flags=renderPatientSafetyFlags(['doxy']);"
        "const first=report($('patient-safety-banners'));"
        "const hiddenAfterFlags=$('patient-safety-banners').classList.contains('hidden');"
        "hidePatientSafetyFlags();"
        "const cleared=$('patient-safety-banners').children.length;"
        "const hiddenAfterClear=$('patient-safety-banners').classList.contains('hidden');"
        "const none=renderPatientSafetyFlags(['vancomycin']);"
        "console.log(JSON.stringify({n:flags.length,level:flags[0]&&flags[0].level,first:first,hiddenAfterFlags:hiddenAfterFlags,cleared:cleared,hiddenAfterClear:hiddenAfterClear,none:none.length,noneHidden:$('patient-safety-banners').classList.contains('hidden')}));"
    )
    result = _run(["ageGroupLabel"], f"const DB = {_lit(fixture)};\nlet activeAge='child';\n", body)
    assert result["n"] == 1 and result["level"] == "danger"
    _assert_payload_is_inert(result["first"], "renderPatientSafetyFlags")
    assert result["hiddenAfterFlags"] is False
    assert result["cleared"] == 0 and result["hiddenAfterClear"] is True
    assert result["none"] == 0 and result["noneHidden"] is True


def test_prescription_signa_for_an_injectable_solution_names_the_real_route() -> None:
    """Regression: a solution_im with concentration_mg_per_ml printed 'внутрь'."""
    drug = {"inn": "Гентамицин", "forms": [{"form_type": "solution_im", "concentration": "40 мг/мл", "concentration_mg_per_ml": 40}]}
    active = {"drug_ref": "d", "regimens": [{"age_group": "all", "single_dose_mg": 240, "freq_per_day": 1, "duration_days": 7}]}
    result = _run_with_consts(
        _RX_FUNCS, _RX_CONSTS, _rx_globals(drug, active, "im", "im"),
        "fillPrescriptionForm();console.log(JSON.stringify({signa:$('rx-signa-text').textContent,trust:$('rx-trust-line').textContent}));",
    )
    assert "внутримышечно" in result["signa"] and "внутрь" not in result["signa"]
    assert "6.0 мл" in result["signa"] and "240 мг" in result["signa"]
    assert "КР МЗ РФ #654 (2021)" in result["trust"]


def test_prescription_capsule_count_is_whole_and_shows_actual_dose() -> None:
    drug = {"inn": "Доксициклин", "forms": [{"form_type": "capsule", "concentration": "100 мг"}]}
    active = {"drug_ref": "d", "regimens": [{"age_group": "all", "single_dose_mg": 150, "freq_per_day": 2, "duration_days": 7}]}
    result = _run_with_consts(
        _RX_FUNCS, _RX_CONSTS, _rx_globals(drug, active, "po", None),
        "fillPrescriptionForm();console.log(JSON.stringify({signa:$('rx-signa-text').textContent,drugs:$('rx-drugs').innerHTML}));",
    )
    assert "По 2 " in result["signa"] and "(= 200 мг, +33 % к расчётной)" in result["signa"], result["signa"]
    assert "1.5" not in result["signa"]
    # D.t.d. N is the quantity for the whole course (2 caps × 2/day × 7 days), with the per-dose count beside it
    assert "D.t.d. N 28 in caps." in result["drugs"] and "по 2 на приём, 2 р/д × 7 дн." in result["drugs"], result["drugs"]


def test_unit_strength_handles_combination_strengths_and_dose_basis() -> None:
    """One amoxiclav 875+125 tablet used to be «7 таб 125 мг»; co-trimoxazole 480 mg «6 таб 80 мг»."""
    body = (
        "const amc={form_type:'tablet',concentration:'875+125 мг'};"
        "const amc500={form_type:'tablet',concentration:'500+125 мг'};"
        "const amcIv={form_type:'powder_for_injection',concentration:'1000+200 мг флакон'};"
        "const cot={form_type:'tablet',concentration:'400+80 мг'};"
        "const pen={form_type:'powder_for_injection',concentration:'1.2 млн ЕД флакон'};"
        "const tmp={regimen_label:'10 мг/кг (по TMP) на ночь'};"
        "const tmp2={duration_note:'По триметоприму 15-20 мг/кг/сут в 3-4 введения.'};"
        "const tmp3={regimen_label:'15-20 мг/кг/сут (по ТМП)'};"
        "console.log(JSON.stringify({"
        "amc875:unitStrengthMg(amc,875,null),amc500:unitStrengthMg(amc500,500,null),amcIv:unitStrengthMg(amcIv,1000,null),"
        "cot480:unitStrengthMg(cot,480,null),cot800:unitStrengthMg(cot,800,null),cot960:unitStrengthMg(cot,960,null),"
        "cotTmp:unitStrengthMg(cot,250,tmp),cotTmp2:unitStrengthMg(cot,350,tmp2),cotTmp3:unitStrengthMg(cot,350,tmp3),"
        "pen:unitStrengthMg(pen,2.4e6,null,'ЕД'),plain:unitStrengthMg({concentration:'500 мг'},1000,null),"
        "none:unitStrengthMg({concentration:'крем 2%'},100,null),"
        "amcUnits:solidUnitsPerDose(875,amc,null).units,cotUnits:solidUnitsPerDose(480,cot,null).units,"
        "cotTmpUnits:solidUnitsPerDose(250,cot,tmp).units}));"
    )
    result = _run([], "", body)
    assert result["amc875"] == 875 and result["amc500"] == 500 and result["amcIv"] == 1000
    assert result["cot480"] == 480 and result["cot800"] == 400 and result["cot960"] == 480
    assert result["cotTmp"] == 80 and result["cotTmp2"] == 80, "«по триметоприму» regimens dose the TMP component"
    assert result["cotTmp3"] == 80, "«(по ТМП)» alone must be recognised — JS \\b never matches after Cyrillic"
    assert result["pen"] == 1_200_000 and result["plain"] == 500 and result["none"] is None
    assert result["amcUnits"] == 1 and result["cotUnits"] == 1 and result["cotTmpUnits"] == 3


def test_rounding_deviation_is_named_when_it_reaches_ten_percent() -> None:
    body = (
        "const t500={form_type:'tablet',concentration:'500 мг'};"
        "const c100={form_type:'capsule',concentration:'100 мг'};"
        "console.log(JSON.stringify({"
        "exact:formatTablets(1000,t500,null),"
        "small:formatTablets(1050,t500,null),"   # 2.1 → 2 tabs = 1000 mg, −5 % → no percent
        "plus:formatTablets(875,t500,null),"     # 1.75 → 2 tabs = 1000 mg, +14 %
        "minus:formatTablets(500,{form_type:'tablet',concentration:'750 мг'},null),"  # 0.5 × 750 = 375, −25 %
        "caps:formatTablets(150,c100,null)}));"  # 1.5 → 2 caps = 200 mg, +33 %
    )
    result = _run([], "", body)
    assert result["exact"] == "(2 таб 500 мг)"
    assert result["small"] == "(~2 таб 500 мг = 1000 мг)", result["small"]
    assert result["plus"] == "(~2 таб 500 мг = 1000 мг, +14 % к расчётной)", result["plus"]
    assert result["minus"] == "(~0.5 таб 750 мг = 375 мг, -25 % к расчётной)", result["minus"]
    assert result["caps"] == "(~2 капс 100 мг = 200 мг, +33 % к расчётной; капсулы не делятся)", result["caps"]


def test_course_text_and_units_for_course() -> None:
    body = (
        "const tab={form_type:'tablet',concentration:'500 мг'};"
        "const vial={form_type:'powder_for_injection',concentration:'1000 мг флакон'};"
        "const r=(d,f)=>({duration_days:d,freq_per_day:f});"
        "console.log(JSON.stringify({"
        "w1:daysWord(1),w3:daysWord(3),w7:daysWord(7),w11:daysWord(11),w21:daysWord(21),w22:daysWord(22),"
        "t7:courseText(r(7,1)),t710:courseText(r('7-10',1)),t1:courseText(r(1,1)),t21:courseText(r('14-21',1)),"
        "tChr:courseText(r('хроническая',1)),tNone:courseText(r('',1)),"
        "tail7:courseTail(r('7',1)),tailChr:courseTail(r('по ситуации',1)),"
        "d710:courseDays(r('7-10',1)),dChr:courseDays(r('хроническая',1)),"
        "u:unitsForCourse(r('7-10',3),tab,1000),uVial:unitsForCourse(r(5,2),vial,1500),"
        "uChr:unitsForCourse(r('хроническая',1),tab,500),uHalf:unitsForCourse(r(7,1),tab,250)}));"
    )
    result = _run([], "", body)
    assert (result["w1"], result["w3"], result["w7"], result["w11"], result["w21"], result["w22"]) == ("день", "дня", "дней", "дней", "день", "дня")
    assert result["t7"] == "7 дней" and result["t710"] == "7–10 дней" and result["t1"] == "1 день" and result["t21"] == "14–21 день"
    assert result["tChr"] == "хроническая" and result["tNone"] == "не указан"
    assert result["tail7"] == ", курс 7 дней." and result["tailChr"] == ", длительность: по ситуации."
    assert result["d710"] == 10 and result["dChr"] == 0
    assert result["u"] == {"perDose": 2, "total": 60, "days": 10, "strength": 500}
    assert result["uVial"] == {"perDose": 2, "total": 20, "days": 5, "strength": 1000}, "partial vials are rounded up per dose"
    assert result["uChr"] is None, "a course in words has no dispensable quantity"
    assert result["uHalf"] == {"perDose": 0.5, "total": 4, "days": 7, "strength": 500}


def test_header_stats_distinguish_computable_from_blocked_records() -> None:
    db = {
        "meta": {"version": "t", "verification_status": "draft", "warning": "w"},
        "drugs_reference": {"amoxicillin": {"inn": "A", "forms": []}},
        "recommendations": [
            {"id": "a", "name": "A", "mkb10": ["J18"], "calculation_blocked": False, "scenarios": []},
            {"id": "b", "name": "B", "mkb10": ["J19"], "calculation_blocked": True, "calculation_block_reason": "r", "scenarios": []},
            {"id": "c", "name": "C", "mkb10": ["J20"], "calculation_blocked": True, "calculation_block_reason": "r", "scenarios": []},
        ],
    }
    body = (
        f"$('db-data').textContent={_lit(json.dumps(db, ensure_ascii=False))};"
        "document.querySelectorAll=()=>[];"
        "function setupButtons(){} function setupPersonalMode(){} function setupTheme(){} function initHistoryStore(){} function loadHistory(){}"
        "function registerServiceWorker(){}"
        "const navigator={};"
        "init();"
        "console.log(JSON.stringify({header:$('header-stats').textContent,empty:$('empty-state-stats').textContent}));"
    )
    result = _run(["validateDB", "dbBlockReason", "dbTrustState", "buildFingerprint", "buildIdentifier", "renderTrustBanner", "init"],
                  "let DB=null;let dbBlockingErrors=[];let activeDisease=null;\n", body)
    assert "3 нозологий (1 расчётных, 2 закрыто до верификации)" in result["header"]
    assert result["empty"].startswith("1 расчётных нозологий из 3")


def test_topical_forms_never_get_a_tablet_or_bottle_course_estimate() -> None:
    """Regression (bacterial vaginosis → clindamycin 2 % cream, 2026-10-14):
    the cream carries concentration_mg_per_ml = 20, so the suspension branch
    produced "210 ml → 3 bottles" in the MIS text and "D.t.d. N. 3" in the
    Latin recipe from the ORAL 300 mg regimen. Topical forms return null."""
    globals_js = (
        "let activeDrug={drug_ref:'clindamycin'};\n"
        "function getDrugRefs(d){return [d.drug_ref];}\n"
    )
    body = (
        "const reg={single_dose_mg:300,freq_per_day:2,duration_days:'7'};"
        "const out={"
        " cream: calculateCoursePackages(reg,{form_type:'topical',concentration:'2% крем',concentration_mg_per_ml:20},300,600,70),"
        " drops: calculateCoursePackages(reg,{form_type:'drops',concentration:'0.3%',concentration_mg_per_ml:3},300,600,70),"
        " susp: calculateCoursePackages(reg,{form_type:'suspension',concentration:'250 мг/5 мл',concentration_mg_per_ml:50},300,600,20),"
        " caps: calculateCoursePackages(reg,{form_type:'capsule',concentration:'150 мг'},300,600,70),"
        " none: calculateCoursePackages(reg,null,300,600,70)"
        "};"
        "console.log(JSON.stringify({cream:out.cream,drops:out.drops,none:out.none,susp:out.susp&&out.susp.type,caps:out.caps&&[out.caps.type,out.caps.totalTabs,out.caps.packCount]}));"
    )
    result = _run(["calculateCoursePackages", "getStandardBottleMl"], globals_js, body)
    assert result["cream"] is None and result["drops"] is None and result["none"] is None
    assert result["susp"] == "suspension"
    assert result["caps"] == ["tablet", 28, 2]
