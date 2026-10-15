"""Exhaustive DOM walk of the built shell (``tests/js/shell_walk.js``).

Every computable nosology → every age-matching scenario → every drug card →
every route tab → every form chip, for five patient profiles (adult, child,
infant, neonate, and an adult with GFR 25 + pregnancy + anaphylactic penicillin
allergy). For each state the visible result, the MIS text and the
prescription form must be free of NaN / Infinity / undefined / "[object" and
must either show a dose or an explicit block reason. Oracles per computed
state: regimen age group, dose arithmetic re-derived from the DB regimen ×
profile weight (single and daily tiles — «15 млн ЕД» for 1 050 000 was found
this way), ml on screen = dose / concentration (suspension or selected vial),
printed «D.t.d. N» = per dose × р/д × days, MIS / Rp dose vs screen (mg and
ЕД), combination-partner dose = component_regimens × weight, route words in
every export, course units (MIS = Rp = printed form), course wording,
number-word grammar («1 раза в день» shipped once), screen/MIS large-volume
warning parity. ~30 s in jsdom; skipped when
Node.js or the root devDependencies are absent (CI installs them).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HTML = PROJECT_ROOT / "antibiotic_calc.html"
CSS = PROJECT_ROOT / "vendor" / "app.css"
JSDOM = PROJECT_ROOT / "node_modules" / "jsdom" / "package.json"
HARNESS = Path(__file__).with_name("js") / "shell_walk.js"


SHARDS = 2


@pytest.fixture(scope="module")
def walk() -> dict:
    """The five profiles are independent: run them as SHARDS concurrent node
    processes (``SHELL_WALK_SHARD=i/n``) and merge the outputs."""
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable")
    if not JSDOM.is_file():
        pytest.skip("root devDependencies missing — run `npm ci` (jsdom)")
    procs = [
        subprocess.Popen(
            [node, str(HARNESS), str(HTML), str(CSS)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=PROJECT_ROOT,
            env={**os.environ, "SHELL_WALK_SHARD": f"{i}/{SHARDS}"},
        )
        for i in range(SHARDS)
    ]
    merged: dict = {"profiles": {}, "consoleErrors": [], "findings": []}
    for i, proc in enumerate(procs):
        stdout, stderr = proc.communicate(timeout=600)
        assert proc.returncode == 0, f"shard {i}: {stderr[-3000:]}"
        part = json.loads(stdout)
        merged["profiles"].update(part["profiles"])
        merged["consoleErrors"].extend(part["consoleErrors"])
        merged["findings"].extend(part["findings"])
        for key, value in part.items():
            if key not in ("profiles", "consoleErrors", "findings"):
                assert merged.setdefault(key, value) == value, (key, merged[key], value)
    return merged


def test_walk_covers_every_computable_nosology_for_every_profile(walk: dict) -> None:
    assert walk["computable"] == 65
    for name, stats in walk["profiles"].items():
        assert stats["diseases"] == walk["computable"], name
        assert stats["empty"] == 0, (name, stats)
        assert stats["blocked"] + stats["computed"] == stats["forms"], (name, stats)
        assert stats["exports"] == stats["computed"], (name, stats)
    adult = walk["profiles"]["adult_70"]
    assert adult["scenarios"] >= 80 and adult["drugs"] >= 180 and adult["computed"] >= 500, adult
    # the arithmetic oracle must actually run on (almost) every computed state
    for name, stats in walk["profiles"].items():
        assert stats["arithmeticOracle"] >= stats["computed"] - 1, (name, stats)
    # ml (suspension / reconstituted vial) and the printed course breakdown are re-multiplied too
    assert adult["volumeOracle"] >= 300 and adult["courseArithmeticOracle"] >= 350, adult
    # MIS / Rp dose vs screen now covers ЕД drugs as well; combination partners are re-derived
    for name, stats in walk["profiles"].items():
        assert stats["doseOracle"] >= stats["computed"] - 1 and stats["rpDoseOracle"] >= stats["computed"] - 1, (name, stats)
    assert adult["partnerOracle"] >= 30, adult
    # T83: every partner the screen lists is named (INN) in the MIS text AND the Latin Rp
    assert adult["partnerExportOracle"] >= adult["partnerOracle"], adult
    # number-word grammar («1 раз / 2 раза / 5 раз в день», «2 дня / 5 дней») on every export,
    # and the large-volume warning shown on screen is also in the chart text (child profile)
    assert all(stats["grammarOracle"] == stats["computed"] for stats in walk["profiles"].values()), walk["profiles"]
    assert walk["profiles"]["child_7y_25kg"]["volumeWarnOracle"] >= 10, walk["profiles"]["child_7y_25kg"]
    # neonates are mostly blocked (no neonatal scheme) — that is the safety design, not a gap
    neonate = walk["profiles"]["neonate_10d_3kg"]
    assert neonate["blocked"] > neonate["computed"], neonate
    # patient-context profile (GFR 25, pregnancy, anaphylactic penicillin allergy): almost every
    # state carries flags and the flags-parity oracle (MIS = Rp = printed form) ran on all of them
    ctx = walk["profiles"]["adult_60_gfr25_pregnant_pen_allergy"]
    assert ctx["computed"] == adult["computed"] and ctx["blocked"] == adult["blocked"], ctx
    assert ctx["flagsOracle"] >= ctx["computed"] - 10 and ctx["dangerFlags"] >= 350, ctx
    # default-route oracle (T63): every drug card with a route list opens on the first route
    # of its scenario entry that has forms, tabs in record order (every profile, every drug)
    for name, stats in walk["profiles"].items():
        assert stats["defaultRouteOracle"] >= stats["drugs"] - 5, (name, stats)
    # picked-route oracle: the last tab clicked follows the physician to the next drug card
    assert adult["pickedRouteOracle"] >= 10, adult
    # source-gate oracle (T66): every calculation_blocked record stays closed through the
    # re-renders (age chip, allergy, typed age) for every profile
    blocked_records = walk["blocked"]
    assert blocked_records >= 40
    for name, stats in walk["profiles"].items():
        assert stats["gatedOracle"] == blocked_records, (name, stats)


def test_no_state_shows_nan_undefined_or_an_empty_result(walk: dict) -> None:
    assert walk["consoleErrors"] == [], walk["consoleErrors"][:5]
    assert walk["findings"] == [], json.dumps(walk["findings"][:20], ensure_ascii=False, indent=1)
