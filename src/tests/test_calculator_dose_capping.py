"""Регрессия на усечение дозы по `max_daily_mg` в калькуляторе.

`computeDose()` усекала **суточную** дозу по `max_daily_mg`, но разовая dose,
взятая из `single_dose_mg`, оставалась неусечённой. Рецепт при этом печатал
«1500 мг 4 р/д» при заявленном потолке 4000 мг/сут — то есть инструкцию,
которая на 50% превышает максимум. В текущей БД такого сочетания нет
(0 из 638 режимов), поэтому баг был латентным: он сработал бы при первом же
режиме, где разовая доза и частота расходятся с потолком.

Тест исполняет **именно тот JavaScript, который попадает в собранный
``antibiotic_calc.html``**, на реальной БД из этого же файла.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BUILT_HTML = ROOT / "antibiotic_calc.html"
TEMPLATE = ROOT / "antibiotic_calc.html.template"

node = shutil.which("node")
pytestmark = pytest.mark.skipif(node is None, reason="node is required to execute the shipped calculator script")


def _script_and_db() -> tuple[str, dict]:
    html = BUILT_HTML.read_text(encoding="utf-8")
    script = next(
        body
        for _attrs, body in re.findall(r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>", html, re.S)
        if "function computeDose(" in body
    )
    db = json.loads(re.search(r'<script id="db-data" type="application/json">(.*?)</script>', html, re.S).group(1))
    return script, db


def _compute_dose_source() -> str:
    script, _db = _script_and_db()
    match = re.search(r"\nfunction computeDose\(.*?\n\}\n", script, re.S)
    assert match, "function computeDose() not found in the built calculator script"
    return match.group(0)


def _run(body: str) -> dict:
    """Execute the shipped computeDose in node and return its JSON verdict."""
    script, db = _script_and_db()
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as handle:
        handle.write(f"const DB = {json.dumps(db, ensure_ascii=False)};\n")
        handle.write(_compute_dose_source())
        handle.write("\nconsole.log(JSON.stringify(")
        handle.write(body)
        handle.write("));\n")
        path = handle.name

    result = subprocess.run([node, path], capture_output=True, text=True, timeout=300, check=True)
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_capped_single_dose_is_recalculated_with_the_daily_cap() -> None:
    """Разовая доза обязана пересчитываться вместе с суточной."""
    verdict = _run(
        """(() => {
      const cases = {
        singleOverCap:  computeDose({single_dose_mg: 1500, freq_per_day: 4, max_daily_mg: 4000}, 80, 'мг'),
        perKgOverCap:   computeDose({dose_mg_kg_day: 100, freq_per_day: 4, max_daily_mg: 4000}, 80, 'мг'),
        fixedOverCap:   computeDose({dose_mg_day_fixed: 6000, freq_per_day: 4, max_daily_mg: 4000}, 80, 'мг'),
        withinCap:      computeDose({single_dose_mg: 500, freq_per_day: 4, max_daily_mg: 4000}, 80, 'мг'),
        singleNoFreq:   computeDose({single_dose_mg: 2000, max_daily_mg: 1000}, 80, 'мг'),
      };
      const out = {};
      for (const [name, r] of Object.entries(cases)) {
        out[name] = { single: r.singleMg, daily: r.dailyMg, capped: r.capped };
      }
      return out;
    })()"""
    )

    # Усечённые случаи: разовая × частота не должна превышать потолок.
    assert verdict["singleOverCap"] == {"single": 1000, "daily": 4000, "capped": True}
    assert verdict["perKgOverCap"] == {"single": 1000, "daily": 4000, "capped": True}
    assert verdict["fixedOverCap"] == {"single": 1000, "daily": 4000, "capped": True}
    assert verdict["singleNoFreq"] == {"single": 1000, "daily": 1000, "capped": True}

    # Неусечённый случай не должен меняться — иначе фикс ломает нормальный расчёт.
    assert verdict["withinCap"] == {"single": 500, "daily": 2000, "capped": False}


def test_no_regimen_in_the_real_db_can_exceed_its_daily_cap() -> None:
    """Сплошной проход: 638 режимов × 6 весов, ни одного превышения."""
    verdict = _run(
        """(() => {
      const weights = [3, 10, 25, 50, 80, 120];
      let computed = 0; const violations = [];
      for (const rec of DB.recommendations)
        for (const sc of (rec.scenarios || []))
          for (const ln of (sc.lines || []))
            for (const d of (ln.drugs || []))
              for (const reg of (d.regimens || []))
                for (const w of weights) {
                  const r = computeDose(reg, w, 'мг');
                  const product = r.singleMg * (reg.freq_per_day || 1);
                  computed++;
                  if (reg.max_daily_mg != null && product > reg.max_daily_mg * 1.0001) {
                    violations.push(rec.id + '/' + (d.drug_ref || d.combo_ref) + '@' + w
                                    + ': ' + product + ' > ' + reg.max_daily_mg);
                  }
                }
      return { computed, violations: violations.slice(0, 5), count: violations.length };
    })()"""
    )

    assert verdict["computed"] > 3000, verdict
    assert verdict["count"] == 0, f"dose exceeds max_daily_mg: {verdict['violations']}"


def test_daily_dose_itself_never_exceeds_the_cap() -> None:
    """Суточная доза тоже обязана соблюдать потолок — проверяем обе величины."""
    verdict = _run(
        """(() => {
      const weights = [3, 10, 25, 50, 80, 120];
      let bad = 0;
      for (const rec of DB.recommendations)
        for (const sc of (rec.scenarios || []))
          for (const ln of (sc.lines || []))
            for (const d of (ln.drugs || []))
              for (const reg of (d.regimens || []))
                for (const w of weights) {
                  const r = computeDose(reg, w, 'мг');
                  if (reg.max_daily_mg != null && r.dailyMg > reg.max_daily_mg * 1.0001) bad++;
                }
      return { bad };
    })()"""
    )

    assert verdict["bad"] == 0


def test_uncapped_regimens_are_untouched_by_the_fix() -> None:
    """Режимы без `max_daily_mg` считаются ровно как раньше."""
    verdict = _run(
        """(() => ({
      perKg:  computeDose({dose_mg_kg_day: 45, freq_per_day: 3}, 20, 'мг'),
      fixed:  computeDose({dose_mg_day_fixed: 1500, freq_per_day: 3}, 70, 'мг'),
      single: computeDose({single_dose_mg: 875, freq_per_day: 2}, 70, 'мг'),
    }))()"""
    )

    assert verdict["perKg"] == {"singleMg": 300, "dailyMg": 900, "capped": False,
                                "needWeight": False, "inconsistent": False, "noDose": False,
                                "unit": "мг"}
    assert verdict["fixed"]["singleMg"] == 500 and verdict["fixed"]["dailyMg"] == 1500
    assert verdict["single"]["singleMg"] == 875 and verdict["single"]["dailyMg"] == 1750
    assert all(not v["capped"] for v in verdict.values())


def test_inconsistency_between_single_and_stored_daily_is_still_reported() -> None:
    """Фикс не должен глушить кросс-проверку single×freq против stored daily."""
    verdict = _run(
        """(() => ({
      agree:    computeDose({single_dose_mg: 500, freq_per_day: 3, dose_mg_day_fixed: 1500}, 70, 'мг'),
      disagree: computeDose({single_dose_mg: 500, freq_per_day: 3, dose_mg_day_fixed: 2500}, 70, 'мг'),
    }))()"""
    )

    assert verdict["agree"]["inconsistent"] is False
    assert verdict["disagree"]["inconsistent"] is True


def test_template_documents_why_the_single_dose_is_recalculated() -> None:
    source = TEMPLATE.read_text(encoding="utf-8")

    assert "singleMg = dailyMg / (reg.freq_per_day || 1);" in source
    assert "превышает заявленный потолок" in source
