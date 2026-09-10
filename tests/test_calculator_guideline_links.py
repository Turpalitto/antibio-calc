"""HTML-calculator tests for the КР corpus navigation panel.

The calculator is a single self-contained HTML file, so these tests exercise the
real JavaScript extracted from ``antibiotic_calc.html.template`` and run it under
Node against a minimal DOM stub — the same technique used by
``tests/test_personal_calculator_bridge.py``. Nothing here re-implements the
function under test.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "antibiotic_calc.html.template"
BUILT_HTML = ROOT / "antibiotic_calc.html"
DB_PATH = ROOT / "db" / "antibio_db.json"


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


# A tiny DOM good enough for the panel renderer: it records structure and text
# so assertions can inspect what the physician would actually see.
_DOM_STUB = """
class ClassList {
  constructor(el){ this.el = el; this.set = new Set(); }
  add(...c){ c.forEach(x=>this.set.add(x)); }
  remove(...c){ c.forEach(x=>this.set.delete(x)); }
  toggle(c, force){ const on = force === undefined ? !this.set.has(c) : !!force; if(on) this.set.add(c); else this.set.delete(c); return on; }
  contains(c){ return this.set.has(c); }
}
class El {
  constructor(tag){ this.tag = tag; this.children = []; this.classList = new ClassList(this); this._text = ''; this.className = ''; }
  append(...nodes){ nodes.forEach(n=>this.children.push(n)); }
  appendChild(n){ this.children.push(n); return n; }
  querySelector(){ return new El('div'); }
  set textContent(v){ this._text = String(v); this.children = []; }
  get textContent(){ return this.children.length ? this.children.map(c=>c.textContent).join('|') : this._text; }
  set innerHTML(v){ this._html = String(v); this.children = []; }
  get innerHTML(){ return this._html || ''; }
  toJSON(){ return {tag:this.tag, cls:this.className, text:this._text, children:this.children.map(c=>c.toJSON())}; }
}
const document = {
  _els: {},
  createElement: (tag)=>new El(tag),
  getElementById: (id)=>{ if(!document._els[id]) document._els[id] = new El('div'); return document._els[id]; },
  querySelectorAll: ()=>[],
};
function $(id){ return document.getElementById(id); }
"""


def _run(script_body: str) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable for JavaScript behaviour test")
    source = _source()
    script = "\n".join(
        [
            _DOM_STUB,
            "const GUIDELINE_METHOD_LABELS = "
            + json.dumps(
                {
                    "ICD10_EXACT": {"label": "МКБ-10: точное совпадение", "cls": "x"},
                    "ICD10_BLOCK": {"label": "МКБ-10: совпадение по блоку", "cls": "y"},
                    "TITLE_EXACT": {"label": "совпадение названия", "cls": "z"},
                },
                ensure_ascii=False,
            )
            + ";",
            _js_function(source, "crCaption"),
            _js_function(source, "renderGuidelineLinks"),
            script_body,
        ]
    )
    completed = subprocess.run([node, "-e", script], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


# ── static contract ─────────────────────────────────────────────────────────


def test_template_declares_the_panel_and_never_claims_approval() -> None:
    source = _source()
    assert 'id="guideline-links"' in source
    assert "function renderGuidelineLinks(d){" in source
    assert "не одобрение схем и не влияет на расчёт" in source
    # The panel must be hidden until a disease with links is selected.
    assert 'id="guideline-links" class="hidden' in source


def test_panel_is_reset_when_the_disease_is_cleared() -> None:
    source = _source()
    reset_fn = _js_function(source, "resetDisease")
    assert "$('guideline-links').classList.add('hidden');" in reset_fn
    assert "$('guideline-links').innerHTML = '';" in reset_fn


def test_both_entry_points_render_the_panel() -> None:
    source = _source()
    assert "renderGuidelineLinks(d);" in _js_function(source, "selectDisease")
    assert "renderGuidelineLinks(activeDisease);" in _js_function(source, "applyPersonalCandidate")


def test_missing_cr_id_is_labelled_honestly() -> None:
    assert _run("console.log(JSON.stringify(crCaption({cr_id:'—', cr_year:2024})));") == "КР: номер не подтверждён"
    assert _run("console.log(JSON.stringify(crCaption({cr_id:'', cr_year:null})));") == "КР: номер не подтверждён"
    assert _run("console.log(JSON.stringify(crCaption({cr_id:'858_1', cr_year:2024})));") == "КР #858_1 · 2024"
    assert _run("console.log(JSON.stringify(crCaption({cr_id:'858_1', cr_year:null})));") == "КР #858_1"


# ── rendered behaviour ──────────────────────────────────────────────────────


def test_links_are_rendered_with_method_and_codes() -> None:
    result = _run(
        """
        const disease = {guideline_links: [
          {guideline_id:'1759', title:'Воспалительные заболевания молочных желез', years:[2024], method:'ICD10_EXACT', codes:['N61','O91.0']},
          {guideline_id:'1464', title:'Туберкулез у взрослых', years:[], method:'ICD10_BLOCK', codes:['A18']}
        ]};
        renderGuidelineLinks(disease);
        const box = $('guideline-links');
        console.log(JSON.stringify({
          hidden: box.classList.contains('hidden'),
          rows: box.children.length - 2,
          header: box.children[0].children[0].textContent,
          firstTitle: box.children[2].children[0].textContent,
          firstTags: box.children[2].children[1].children.map(c=>c.textContent),
          secondTags: box.children[3].children[1].children.map(c=>c.textContent)
        }));
        """
    )
    assert result["hidden"] is False
    assert result["rows"] == 2
    assert result["header"] == "Клинические рекомендации корпуса · 2"
    assert result["firstTitle"] == "Воспалительные заболевания молочных желез (2024)"
    assert result["firstTags"] == ["МКБ-10: точное совпадение", "N61", "O91.0", "corpus #1759"]
    assert result["secondTags"] == ["МКБ-10: совпадение по блоку", "A18", "corpus #1464"]


def test_panel_hides_for_a_disease_without_corpus_links() -> None:
    for body in (
        "renderGuidelineLinks({id:'orphan'});",
        "renderGuidelineLinks({guideline_links:[]});",
        "renderGuidelineLinks(null);",
    ):
        result = _run(
            body
            + "const box=$('guideline-links'); console.log(JSON.stringify({hidden:box.classList.contains('hidden'), html:box.innerHTML, kids:box.children.length}));"
        )
        assert result == {"hidden": True, "html": "", "kids": 0}


def test_unknown_method_falls_back_to_the_raw_label() -> None:
    result = _run(
        """
        renderGuidelineLinks({guideline_links:[{guideline_id:'1', title:'T', years:[], method:'SOMETHING_NEW', codes:[]}]});
        console.log(JSON.stringify($('guideline-links').children[2].children[1].children[0].textContent));
        """
    )
    assert result == "SOMETHING_NEW"


# ── build reproducibility ───────────────────────────────────────────────────


def test_built_html_matches_template_plus_database() -> None:
    if not BUILT_HTML.is_file():
        pytest.skip("antibiotic_calc.html is not built in this checkout")
    template = _source().strip()
    db = DB_PATH.read_text(encoding="utf-8-sig").strip()
    assert BUILT_HTML.read_text(encoding="utf-8") == template.replace("__DB_PLACEHOLDER__", db)


def test_database_embeds_crosswalk_links_and_navigation_only_summary() -> None:
    db = json.loads(DB_PATH.read_text(encoding="utf-8-sig"))
    summary = db["meta"].get("guideline_crosswalk")
    assert summary, "meta.guideline_crosswalk missing — rebuild with `python db/build_db.py`"
    assert summary["purpose"] == "NAVIGATION_ONLY"
    assert summary["content_sha256"].startswith("sha256:")

    linked = [rec for rec in db["recommendations"] if rec.get("guideline_links")]
    assert len(linked) == summary["linked_diseases"]
    total_links = sum(len(rec["guideline_links"]) for rec in db["recommendations"])
    assert total_links == summary["links"]

    valid_methods = set(summary["links_by_method"])
    for rec in linked:
        for link in rec["guideline_links"]:
            assert set(link) == {"guideline_id", "title", "years", "method", "codes"}
            assert link["method"] in valid_methods


def test_calculator_validates_mkb10_and_guideline_links() -> None:
    """The in-browser validateDB() must catch the same defects as validate_db.js."""
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable for JavaScript behaviour test")
    source = _source()
    script = "\n".join(
        [
            "const DB = "
            + json.dumps(
                {
                    "recommendations": [
                        {"id": "a", "name": "A", "mkb10": ["C83.5, C91.0"], "cr_id": "1_1", "cr_year": 2024},
                        {"id": "a", "name": "A dup", "mkb10": ["A00"], "cr_id": "2_2", "cr_year": 2024},
                        {
                            "id": "b",
                            "name": "B",
                            "mkb10": ["A01"],
                            "cr_id": "3_3",
                            "cr_year": 2024,
                            "guideline_links": [{"guideline_id": "", "title": "x", "method": "BOGUS", "codes": []}],
                        },
                    ],
                    "drugs_reference": {"_note": "n", "amoxicillin": {"inn": "x", "forms": []}},
                },
                ensure_ascii=False,
            )
            + ";",
            _js_function(source, "validateDB"),
            "const r = validateDB(); console.log(JSON.stringify(r));",
        ]
    )
    completed = subprocess.run([node, "-e", script], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    joined = "\n".join(result["errs"])
    assert "некорректный код МКБ-10" in joined
    assert "дубль id нозологии" in joined
    assert "неизвестный метод" in joined
    assert "нет guideline_id/title" in joined


def test_template_main_javascript_still_parses() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable for JavaScript syntax test")
    scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", _source(), re.DOTALL)
    completed = subprocess.run(
        [node, "--check", "-"], input=scripts[-1], capture_output=True, text=True, encoding="utf-8"
    )
    assert completed.returncode == 0, completed.stderr
