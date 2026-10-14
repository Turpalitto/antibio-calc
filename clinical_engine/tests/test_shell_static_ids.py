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


def test_inline_handlers_only_call_functions_the_script_defines() -> None:
    html = _template()
    script = "\n".join(re.findall(r"<script[^>]*>(.*?)</script>", html, flags=re.S))
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
