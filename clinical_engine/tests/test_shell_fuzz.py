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
an unmarked scenario list. Later invariants found the source-gate bypass on
re-render (T66 — a «расчёт закрыт» record computed and exported a dose after
the next typed age) and the allergy banner surviving a record with no scenario
for the group (T67); the state ⇔ DOM invariants added later found the regimen
chips of the previous group under the age block (T72) and the history restore
losing the group chosen by chip over a typed age (T74). Two seeds × 800 steps,
run concurrently (≈ 50 s wall time in jsdom); skipped when Node.js or the root
devDependencies are absent (CI installs them).
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


def _run_all(seeds: tuple[int, ...]) -> dict[int, dict]:
    """Run every seed as its own node process, concurrently: the walks are
    independent and each takes ~50 s in jsdom, so the wall time is one walk."""
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable")
    if not JSDOM.is_file():
        pytest.skip("root devDependencies missing — run `npm ci` (jsdom)")
    procs = {
        seed: subprocess.Popen(
            [node, str(HARNESS), str(HTML), str(CSS), str(seed), str(STEPS)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=PROJECT_ROOT,
        )
        for seed in seeds
    }
    results: dict[int, dict] = {}
    for seed, proc in procs.items():
        stdout, stderr = proc.communicate(timeout=600)
        assert proc.returncode == 0, f"seed {seed}: {stderr[-3000:]}"
        results[seed] = json.loads(stdout)
    return results


@pytest.fixture(scope="module")
def _runs() -> dict[int, dict]:
    return _run_all(SEEDS)


@pytest.fixture(scope="module", params=SEEDS, ids=[f"seed{s}" for s in SEEDS])
def fuzz(request: pytest.FixtureRequest, _runs: dict[int, dict]) -> dict:
    return _runs[request.param]


def test_random_walk_keeps_every_shell_invariant(fuzz: dict) -> None:
    assert fuzz["steps"] == STEPS
    assert fuzz["findings"] == [], json.dumps(fuzz["findings"][:15], ensure_ascii=False, indent=1)
    assert fuzz["nFindings"] == 0


def test_random_walk_exercises_every_action(fuzz: dict) -> None:
    counts = fuzz["counts"]
    expected = {
        "weight", "age", "ageChip", "gfr", "preg", "allergy", "disease", "scenario", "drug", "route",
        "form", "regimen", "vial", "newPatient",
        "freshWeight", "injRoute", "dialog", "weightChip", "ageUnit", "keyCard", "searchKeys", "chipOverAge", "childTablet", "noWeightExport", "resetDisease", "search", "hash", "history", "copy",
        "print", "theme", "routeThenDrug", "name", "quickTag", "capDose", "zeroAgeExport", "ageInferenceExport", "injectableRouteExport", "injectableRouteSwitchExport",
    }
    assert expected <= set(counts), sorted(expected - set(counts))
    undercovered = {name: counts[name] for name in expected if counts[name] < 9}
    assert not undercovered, undercovered
    assert counts["injectableRouteExport"] >= 10 and counts["injectableRouteSwitchExport"] >= 10, counts


def test_random_walk_notice_invariants_are_not_vacuous(fuzz: dict) -> None:
    """The «notice mirrors the state» invariants only mean something when the
    walk actually reaches the states they guard: a visible block notice, a
    weight notice with a reason, an allergy banner that must be on screen, a
    pending «scenario from the link» note."""
    checks = fuzz["checks"]
    for key in ("dose_block_text", "weight_warn_expected", "allergy_banner_expected", "hash_note_expected"):
        assert checks.get(key, 0) >= 10, (key, checks)


def test_random_walk_reaches_the_arithmetic_and_export_oracles(fuzz: dict) -> None:
    """The dose arithmetic oracle (screen dose == regimen × the random weight, ml ==
    dose / concentration), the tablets-per-dose oracle (the rounded path is steered by
    childTablet) and the MIS-dose parity must actually fire on computed states — a
    mutant that inflates the mg/kg/day arithmetic by 20 % trips 100+ findings, one that
    rounds to whole tablets instead of halves 18, one that doubles the MIS daily dose 19."""
    checks = fuzz["checks"]
    assert checks.get("dose_arithmetic", 0) >= 100, checks
    assert checks.get("inj_volume", 0) >= 10, checks
    assert checks.get("po_volume", 0) >= 5, checks
    assert checks.get("tablet_units", 0) >= 10, checks
    assert checks.get("tablet_units_rounded", 0) >= 10, checks
    assert checks.get("mis_dose", 0) >= 4, checks
    # T77: the no-weight mg/kg state is steered (noWeightExport) and all four doors are tried
    assert checks.get("export_incomplete", 0) >= 4, checks
    assert checks.get("print_incomplete", 0) >= 5, checks
    assert checks.get("history_incomplete", 0) >= 4, checks


def test_random_walks_together_reach_the_rarer_oracles(_runs: dict[int, dict]) -> None:
    """The daily ceiling (amber cap row == the arithmetic; a mutant with a silent cap trips
    5), the printed safety line parity and the chip-over-age caution in the MIS text are
    reached by the plain walk, but not reliably by every seed — the two seeds are summed."""
    totals: dict[str, int] = {}
    for run in _runs.values():
        for key, value in run["checks"].items():
            totals[key] = totals.get(key, 0) + value
    assert totals.get("max_daily_capped", 0) >= 10, totals  # steered by capDose since T86
    assert totals.get("print_flags", 0) >= 6, totals
    assert totals.get("group_mismatch_export", 0) >= 6, totals
    assert totals.get("course_units", 0) >= 3, totals
    # T84 quick-tag group invariant (old build: 6 findings on seed 11)
    assert totals.get("quick_tag", 0) >= 20, totals
    # T85 history entry == screen (dose, full drug name, course wording; old build: 24 on seed 23)
    assert totals.get("history_entry_content", 0) >= 15, totals
    # T86 «нет схемы для группы» note ⇔ state on the search rows (old build: 27 on seed 23)
    assert totals.get("search_group_note", 0) >= 20, totals
    # the frequency printed in the MIS scheme / the Rp Signa == the regimen's freq_per_day
    # (a mutant printing freq + 1 in the tablet scheme trips 11 on seed 11)
    assert totals.get("export_freq", 0) >= 15, totals
    # T95: the full-strength cotrimoxazole tablet is exactly 400+80 = 480 mg; steered
    # through the random walk so the independent arithmetic oracle checks this path.
    assert totals.get("combo_tablet_steered", 0) >= 1, totals
    # T96: theme toggle writes the current light/dark mode; storage and <html>.dark
    # remain aligned during the rest of the random walk (a no-op writer is a mutant).
    assert totals.get("theme_toggle", 0) >= 15, totals
    # T98: a 0-years neonatal calculation repeats its age-entry caution on screen, MIS, Rp and print.
    assert totals.get("zero_age_export", 0) >= 1, totals
    # T99: weight-inferred changes of dosing group repeat their visible caution across exports.
    assert totals.get("age_inference_export", 0) >= 1, totals
    # T100: source-route preparation steps and cautions reach MIS / Rp / print.
    assert totals.get("injectable_route_export", 0) >= 1, totals
    # T101: the same drug's bolus / infusion / bolus-again switch stays in sync.
    assert totals.get("injectable_route_switch_export", 0) >= 10, totals
    # T103: each random action checks labels, role and aria-pressed parity for every
    # exclusive selection group; the active state must not be visual-only.
    assert totals.get("selection_aria_state", 0) >= 1500, totals
