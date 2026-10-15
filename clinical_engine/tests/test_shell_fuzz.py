"""Random-walk (model-based) fuzz of the built shell (``tests/js/shell_fuzz.js``).

A seeded sequence of the actions a physician can take — weight / age / GFR /
pregnancy / allergy inputs, age chips, nosology / scenario / drug / route /
form / regimen / vial clicks (visible elements only), «Новый пациент», the
nosology «✕», search + pick, ``#hash`` navigation, history save / restore,
MIS / Rp copy, Ctrl+P (``beforeprint``), theme — with state invariants checked
after every step: no exception or console error; the active age chip equals
``activeAge``; scenario ∈ disease, line ∈ scenario, drug ∈ line; the form
index is in range and equals the active chip; the route tab equals
``currentRouteGroup``; an active scenario and drug card exist while a drug is
selected; a blocked state shows no result tiles, exports nothing, prints no
lines and never adds a history entry; a computed state shows a result,
non-empty MIS / Rp and printed lines; the regimen used fits ``activeAge``; no
NaN / undefined anywhere; ``location.hash`` names the active nosology.

Found on the first runs: a weight- / age-blocked calculation was still saved
to history with its doses (the block text promises «не может быть сохранён»),
the nosology «✕» left live cards of the previous record in the hidden steps,
and a group change that left no fitting scenario showed a drug list next to
an unmarked scenario list. Two seeds × 800 steps ≈ 25 s in jsdom; skipped when
Node.js or the root devDependencies are absent (CI installs them).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HTML = PROJECT_ROOT / "antibiotic_calc.html"
CSS = PROJECT_ROOT / "vendor" / "app.css"
JSDOM = PROJECT_ROOT / "node_modules" / "jsdom" / "package.json"
HARNESS = Path(__file__).with_name("js") / "shell_fuzz.js"
SEEDS = (11, 23)
STEPS = 800


def _run(seed: int) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable")
    if not JSDOM.is_file():
        pytest.skip("root devDependencies missing — run `npm ci` (jsdom)")
    completed = subprocess.run(
        [node, str(HARNESS), str(HTML), str(CSS), str(seed), str(STEPS)],
        capture_output=True, text=True, check=False, timeout=600, cwd=PROJECT_ROOT,
    )
    assert completed.returncode == 0, completed.stderr[-3000:]
    return json.loads(completed.stdout)


@pytest.fixture(scope="module", params=SEEDS, ids=[f"seed{s}" for s in SEEDS])
def fuzz(request: pytest.FixtureRequest) -> dict:
    return _run(request.param)


def test_random_walk_keeps_every_shell_invariant(fuzz: dict) -> None:
    assert fuzz["steps"] == STEPS
    assert fuzz["findings"] == [], json.dumps(fuzz["findings"][:15], ensure_ascii=False, indent=1)
    assert fuzz["nFindings"] == 0


def test_random_walk_exercises_every_action(fuzz: dict) -> None:
    counts = fuzz["counts"]
    expected = {
        "weight", "age", "ageChip", "gfr", "preg", "allergy", "disease", "scenario", "drug", "route",
        "form", "regimen", "vial", "newPatient", "resetDisease", "search", "hash", "history", "copy",
        "print", "theme",
    }
    assert expected <= set(counts), sorted(expected - set(counts))
    assert all(counts[name] >= 10 for name in expected), counts
