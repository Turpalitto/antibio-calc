"""Static wiring checks on the shell template (no browser, no Node).

Two real defects motivated these: a duplicate ``id="patient-age"`` that made
``getElementById`` return the wrong input (the typed age was ignored), and a
mobile-nav button calling ``getElementById('btn-copy')`` for an id that no
longer existed (the button did nothing). Both are invisible to unit tests that
call handlers directly, so pin them at the markup level.
"""

from __future__ import annotations

import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = PROJECT_ROOT / "antibiotic_calc.html.template"


def _template() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def _markup_ids(html: str) -> list[str]:
    # ids written in markup (static elements); dynamic `.id = '…'` assignments are separate
    return re.findall(r'<[a-zA-Z][^>]*\sid="([^"]+)"', html)


def test_markup_ids_are_unique() -> None:
    counts = Counter(_markup_ids(_template()))
    duplicates = sorted(i for i, n in counts.items() if n > 1)
    assert duplicates == [], f"duplicate id attributes in the template: {duplicates}"


def test_every_id_the_script_looks_up_exists() -> None:
    html = _template()
    defined = set(_markup_ids(html))
    defined |= set(re.findall(r"""\.id\s*=\s*['"]([^'"]+)['"]""", html))
    looked_up = set(re.findall(r"\$\('([^']+)'\)", html))
    looked_up |= set(re.findall(r"""getElementById\(['"]([^'"]+)['"]\)""", html))
    missing = sorted(i for i in looked_up if i not in defined)
    assert missing == [], f"script references ids that no element defines: {missing}"


def test_labels_and_aria_references_point_at_existing_ids() -> None:
    html = _template()
    defined = set(_markup_ids(html))
    for attr in ("for", "aria-labelledby", "aria-describedby", "aria-controls"):
        targets = re.findall(rf'\s{attr}="([^"]+)"', html)
        for value in targets:
            for target in value.split():
                assert target in defined, f'{attr}="{target}" has no element with that id'


class _InlineScriptParser(HTMLParser):
    """Collect inline script text with HTML's case-insensitive tag parsing rules."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._active = False
        self._parts: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "script":
            self._parts.append([])
            self._active = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script":
            self._active = False

    def handle_data(self, data: str) -> None:
        if self._active and self._parts:
            self._parts[-1].append(data)


def _inline_script_bodies(html: str) -> list[str]:
    parser = _InlineScriptParser()
    parser.feed(html)
    parser.close()
    return ["".join(parts) for parts in parser._parts]


def test_inline_handlers_only_call_functions_the_script_defines() -> None:
    html = _template()
    assert _inline_script_bodies('<SCRIPT TYPE="text/javascript">function smoke() {}</SCRIPT>') == [
        "function smoke() {}"
    ]
    script = "\n".join(_inline_script_bodies(html))
    defined = set(re.findall(r"^\s*(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(", script, flags=re.M))
    defined |= set(re.findall(r"^\s*(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>", script, flags=re.M))
    calls = set()
    for handler in re.findall(r'\son[a-z]+="([^"]+)"', html):
        for name in re.findall(r"\b([A-Za-z_$][\w$]*)\s*\(", handler):
            calls.add(name)
    builtin = {"document", "getElementById", "focus", "click", "reload", "preventDefault", "stopPropagation", "alert",
               "if", "for", "while", "switch", "return"}  # keywords that look like calls
    unknown = sorted(c for c in calls if c not in defined and c not in builtin)
    assert unknown == [], f"inline on*= handlers call undefined functions: {unknown}"


def test_print_stylesheet_shows_only_the_prescription_form() -> None:
    """``@media print`` hides every direct child of <body> and re-shows
    ``#prescription-form`` — that only works while the form stays a direct
    child of <body> (wrapping it in a container would print a blank page)."""
    html = _template()
    print_block = re.search(r"@media print\{(.*?)\n\}", html, re.S)
    assert print_block, "the @media print block is missing"
    rules = print_block.group(1)
    assert "body>*{display:none!important}" in rules
    assert "#prescription-form{display:block!important}" in rules
    # the form is a direct child of <body>: no unclosed <div> between <body> and it
    body = html[html.index("<body") : html.index('<div id="prescription-form"')]
    depth = len(re.findall(r"<div\b", body)) - len(re.findall(r"</div>", body))
    assert depth == 0, f"#prescription-form is nested {depth} level(s) deep — it must be a direct child of <body>"
    # the printed form itself is never shown on screen
    assert 'id="prescription-form" class="print-only" style="display:none"' in html


def test_every_validator_form_type_is_routed_explicitly_by_the_shell() -> None:
    """``renderForms`` sorts forms into per os / в/м / в/в / topical by form_type;
    an unlisted type falls through to per os. Every type the validator accepts
    must therefore be named in that function (``drops`` was not — ear drops
    would have been offered as an oral dose)."""
    html = _template()
    validator = (PROJECT_ROOT / "db" / "validate_db.js").read_text(encoding="utf-8")
    block = re.search(r"const FORM_TYPES = new Set\(\[(.*?)\]\);", validator, re.S)
    assert block, "FORM_TYPES not found in db/validate_db.js"
    form_types = re.findall(r"'([a-z_]+)'", block.group(1))
    assert len(form_types) >= 10
    start = html.index("function renderForms(")
    body = html[start : html.index("\nfunction ", start + 10)]
    missing = [t for t in form_types if f"'{t}'" not in body and t not in ("topical", "drops")]
    assert "isTopicalForm(f)" in body, "topical / drops must go through isTopicalForm"
    assert missing == [], f"form types the shell does not route explicitly: {missing}"
    # and the Latin table knows every type the validator accepts
    latin = re.search(r"const LATIN_FORM = \{(.*?)\};", html, re.S).group(1)
    assert [t for t in form_types if f"{t}:" not in latin] == []


def test_every_shipped_drug_has_a_latin_name_for_the_rp() -> None:
    """`copyLatinRecipe` / the printed form write `LATIN_INN[key] || ref.inn`: a drug
    missing from the table would print a Cyrillic INN on the Latin «Rp.:» line. Every
    `drugs_reference` key must be in the table, and every table key must be a real drug."""
    import json

    db = json.loads((PROJECT_ROOT / "db" / "antibio_db.json").read_text(encoding="utf-8-sig"))
    html = TEMPLATE.read_text(encoding="utf-8")
    block = re.search(r"const LATIN_INN = \{(.*?)\};", html, re.S)
    assert block, "LATIN_INN not found in the template"
    latin = dict(re.findall(r"(\w+):'([^']+)'", block.group(1)))
    drugs = [k for k in db["drugs_reference"] if isinstance(db["drugs_reference"][k], dict)]
    assert [k for k in drugs if k not in latin] == [], "drugs without a Latin name for the Rp line"
    assert [k for k in latin if k not in drugs] == [], "Latin names for drugs the DB does not ship"
    # Latin genitive forms only — no Cyrillic slipped into the table
    assert all(re.fullmatch(r"[A-Za-z\- ]+", name) for name in latin.values()), latin
