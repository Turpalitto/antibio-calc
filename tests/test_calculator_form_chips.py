"""Tests for renderFormChips() — the dosage-form picker in the calculator.

A one-character defect shipped here: the syringe-icon branch read ``form.form_type``
instead of the loop variable ``f.form_type``. ``form`` is not declared anywhere in
``renderFormChips`` or globally, so reading it throws ``ReferenceError``.

JavaScript's ``||`` short-circuits left to right, which hid the defect for one type and
exposed it for three:

* ``solution_im`` — the left operand is true, so the right one is never evaluated;
* ``powder_for_injection`` — the exact type the branch was written for, and it throws;
* ``granules`` and ``topical`` — also throw.

Because the throwing branch sits ABOVE the ``granules`` branch, that branch was dead code:
the granules icon could never render. ``granules`` reaches the per-os group and
``powder_for_injection`` reaches both injectable groups, so this was reachable in normal
use — selecting such a drug broke the form picker.

The tests execute the JavaScript that ships in the built ``antibiotic_calc.html``.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BUILT_HTML = ROOT / "antibiotic_calc.html"
TEMPLATE = ROOT / "antibiotic_calc.html.template"

node = shutil.which("node")
pytestmark = pytest.mark.skipif(node is None, reason="node is required to execute the shipped calculator script")

# Присваивание innerHTML в настоящем DOM убирает потомков — без этого заглушка
# накапливала бы чипы между вызовами и тест читал бы первый, а не последний.
_DOM_STUB = """
class ClassList {
  constructor(){ this.set = new Set(); }
  add(...c){ c.forEach(x=>this.set.add(x)); }
  remove(...c){ c.forEach(x=>this.set.delete(x)); }
  toggle(c, f){ const on = f===undefined ? !this.set.has(c) : !!f; on?this.set.add(c):this.set.delete(c); return on; }
  contains(c){ return this.set.has(c); }
}
class El {
  constructor(t){ this.tag=t; this.children=[]; this.classList=new ClassList(); this._text=''; this.className=''; this._html=''; }
  append(...n){ n.forEach(x=>this.children.push(x)); }
  appendChild(n){ this.children.push(n); return n; }
  querySelectorAll(){ return []; }
  set innerHTML(v){ this._html = String(v); this.children = []; }
  get innerHTML(){ return this._html || ''; }
  set textContent(v){ this._text = String(v); }
  get textContent(){ return this._text; }
}
const _grid = new El('div');
const document = {
  createElement: (t)=>new El(t),
  getElementById: (id)=> id==='form-grid' ? _grid : new El('div'),
  querySelectorAll: ()=>[],
};
function $(id){ return document.getElementById(id); }
let activeAge = 'adult', activeFormIdx = 0;
function calculate(){}
"""

EXPECTED_ICONS = {
    "tablet": "fa-pills",
    "capsule": "fa-pills",
    "granules": "fa-prescription-bottle",
    "suspension": "fa-flask",
    "syrup": "fa-flask",
    "powder_for_suspension": "fa-flask",
    "solution_iv": "fa-drip",
    "solution_im": "fa-syringe",
    "powder_for_injection": "fa-syringe",
}


def _script_and_db() -> tuple[str, dict]:
    html = BUILT_HTML.read_text(encoding="utf-8")
    script = next(
        body
        for _attrs, body in re.findall(r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>", html, re.S)
        if "function renderFormChips(" in body
    )
    db = json.loads(re.search(r'<script id="db-data" type="application/json">(.*?)</script>', html, re.S).group(1))
    return script, db


def _extract_fn(script: str, name: str) -> str:
    match = re.search(r"function " + re.escape(name) + r"\(", script)
    assert match, f"function {name}() not found in the built calculator script"
    i = match.start()
    depth = 0
    started = False
    while i < len(script):
        if script[i] == "{":
            depth += 1
            started = True
        elif script[i] == "}":
            depth -= 1
            if started and depth == 0:
                return script[match.start():i + 1]
        i += 1
    raise AssertionError(f"unbalanced braces while extracting {name}()")


def _run(body: str) -> dict:
    script, db = _script_and_db()
    parts = [
        f"const DB = {json.dumps(db, ensure_ascii=False)};",
        _DOM_STUB,
        _extract_fn(script, "renderFormChips"),
        "console.log(JSON.stringify(" + body + "));",
    ]
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as handle:
        handle.write("\n".join(parts) + "\n")
        path = handle.name
    result = subprocess.run([node, path], capture_output=True, text=True, timeout=300, check=True)
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_every_form_type_in_the_database_renders_without_throwing() -> None:
    """Ни один тип формы из справочника не должен ронять отрисовку чипов."""
    verdict = _run(
        """(() => {
      const types = new Set();
      for (const [ref, e] of Object.entries(DB.drugs_reference || {}))
        if (ref !== '_note' && e && typeof e === 'object')
          for (const f of e.forms || []) types.add(f.form_type);
      const failures = [];
      for (const t of types) {
        try {
          renderFormChips([{f: {form_type: t, concentration: 'X', concentration_mg_per_ml: 10}, idx: 0}]);
        } catch (err) { failures.push(t + ': ' + err.constructor.name + ': ' + err.message); }
      }
      return { types: Array.from(types).sort(), failures: failures };
    })()"""
    )
    assert not verdict["failures"], f"отрисовка чипов падает: {verdict['failures']}"
    assert verdict["types"], "в справочнике должны быть лекарственные формы"


def test_each_form_type_gets_its_own_icon() -> None:
    """Иконка соответствует типу формы; ветка granules достижима."""
    verdict = _run(
        """(() => {
      const out = {};
      for (const t of %s) {
        renderFormChips([{f: {form_type: t, concentration: 'X', concentration_mg_per_ml: 10}, idx: 0}]);
        const kids = document.getElementById('form-grid').children;
        out[t] = (kids[kids.length - 1].innerHTML.match(/fa-[a-z-]+/) || ['(none)'])[0];
      }
      return out;
    })()"""
        % json.dumps(list(EXPECTED_ICONS))
    )
    assert verdict == EXPECTED_ICONS, verdict


def test_the_granules_branch_is_not_shadowed_by_the_branch_above() -> None:
    """Раньше ветка выше бросала исключение, и иконка гранул не рисовалась никогда."""
    verdict = _run(
        """(() => {
      renderFormChips([{f: {form_type: 'granules', concentration: '500 мг', concentration_mg_per_ml: null}, idx: 0}]);
      const kids = document.getElementById('form-grid').children;
      return { icon: (kids[0].innerHTML.match(/fa-[a-z-]+/) || ['(none)'])[0] };
    })()"""
    )
    assert verdict["icon"] == "fa-prescription-bottle", verdict


def test_the_icon_branches_reference_the_loop_variable_only() -> None:
    """Опечатка ``form.form_type`` вместо ``f.form_type`` не должна вернуться.

    Переменная ``form`` в ``renderFormChips`` не объявлена, поэтому любое её чтение
    бросает ``ReferenceError``. Проверка статическая: внутри тела функции не должно быть
    обращений к ``form.``, кроме ``f.form_type`` и полей самой записи формы.
    """
    script, _db = _script_and_db()
    body = _extract_fn(script, "renderFormChips")
    bare = [
        m.group(0)
        for m in re.finditer(r"(?<![.\w])form\.[A-Za-z_]+", body)
    ]
    assert not bare, f"обращение к необъявленной переменной form в renderFormChips: {bare}"


def test_template_and_build_agree_on_the_fix() -> None:
    """Правка обязана быть и в шаблоне, и в собранном HTML."""
    needle = "f.form_type === 'solution_im' || f.form_type === 'powder_for_injection'"
    assert needle in TEMPLATE.read_text(encoding="utf-8")
    assert needle in BUILT_HTML.read_text(encoding="utf-8")
    assert "form.form_type === 'powder_for_injection'" not in TEMPLATE.read_text(encoding="utf-8")


def test_the_grid_is_cleared_before_chips_are_added() -> None:
    """Повторная отрисовка не должна накапливать чипы."""
    verdict = _run(
        """(() => {
      const g = [{f: {form_type: 'tablet', concentration: '500 мг'}, idx: 0}];
      renderFormChips(g);
      const first = document.getElementById('form-grid').children.length;
      renderFormChips(g);
      renderFormChips(g);
      return { first: first, after: document.getElementById('form-grid').children.length };
    })()"""
    )
    assert verdict == {"first": 1, "after": 1}, verdict
