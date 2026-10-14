"""Exhaustive DOM walk of the built shell (``tests/js/shell_walk.js``).

Every computable nosology → every age-matching scenario → every drug card →
every route tab → every form chip, for four patient profiles (adult, child,
infant, neonate). For each state the visible result, the MIS text and the
prescription form must be free of NaN / Infinity / undefined / "[object" and
must either show a dose or an explicit block reason. Oracles per computed
state: regimen age group, dose arithmetic re-derived from the DB regimen ×
profile weight (single and daily tiles — «15 млн ЕД» for 1 050 000 was found
this way), ml on screen = dose / concentration (suspension or selected vial),
printed «D.t.d. N» = per dose × р/д × days, MIS / Rp dose vs screen, route
words in every export, course units (MIS = Rp = printed form), course wording. ~30 s in jsdom; skipped when
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
HARNESS = Path(__file__).with_name("js") / "shell_walk.js"


@pytest.fixture(scope="module")
def walk() -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable")
    if not JSDOM.is_file():
        pytest.skip("root devDependencies missing — run `npm ci` (jsdom)")
    completed = subprocess.run(
        [node, str(HARNESS), str(HTML), str(CSS)],
        capture_output=True, text=True, check=False, timeout=600, cwd=PROJECT_ROOT,
    )
    assert completed.returncode == 0, completed.stderr[-3000:]
    return json.loads(completed.stdout)


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
    # neonates are mostly blocked (no neonatal scheme) — that is the safety design, not a gap
    neonate = walk["profiles"]["neonate_10d_3kg"]
    assert neonate["blocked"] > neonate["computed"], neonate


def test_no_state_shows_nan_undefined_or_an_empty_result(walk: dict) -> None:
    assert walk["consoleErrors"] == [], walk["consoleErrors"][:5]
    assert walk["findings"] == [], json.dumps(walk["findings"][:20], ensure_ascii=False, indent=1)
