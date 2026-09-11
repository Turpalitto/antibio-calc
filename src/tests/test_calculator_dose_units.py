"""Регрессия на единицы действия и на молчаливый ноль вместо дозы.

Два дефекта одного класса — «правдоподобное неверное число»:

1. Поля режима называются ``single_dose_mg`` / ``dose_mg_day_fixed``, но для
   бензилпенициллина хранят **единицы действия**. Метка, собранная с жёстким
   «мг», читалась как «4000000 мг 6 р/д» — четыре килограмма пенициллина.
   В HTML то же самое делали signa рецепта, текст для копирования и история.

2. Режим вообще без дозовых полей (доза есть только в свободном тексте КР)
   давал ``singleMg = 0`` при ``needWeight = false``, то есть экран печатал
   «0 мг» как если бы это была доза.

Тесты исполняют **именно тот JavaScript, который попадает в собранный
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

from db.regimen_semantics import build_label, parse_duration

ROOT = Path(__file__).resolve().parents[2]
BUILT_HTML = ROOT / "antibiotic_calc.html"
DB_PATH = ROOT / "db" / "antibio_db.json"
TEMPLATE = ROOT / "antibiotic_calc.html.template"

node = shutil.which("node")


def _script_and_db() -> tuple[str, dict]:
    html = BUILT_HTML.read_text(encoding="utf-8")
    script = next(
        body
        for _attrs, body in re.findall(r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>", html, re.S)
        if "function computeDose(" in body
    )
    db = json.loads(re.search(r'<script id="db-data" type="application/json">(.*?)</script>', html, re.S).group(1))
    return script, db


def _extract(script: str, name: str) -> str:
    match = re.search(rf"\nfunction {re.escape(name)}\(.*?\n\}}\n", script, re.S)
    assert match, f"function {name}() not found in the built calculator script"
    return match.group(0)


def _run(body: str, helpers: tuple[str, ...] = ("formatUnits", "fmtDose", "doseUnitOf", "computeDose")) -> dict:
    script, db = _script_and_db()
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as handle:
        handle.write(f"const DB = {json.dumps(db, ensure_ascii=False)};\n")
        handle.write("".join(_extract(script, name) for name in helpers))
        handle.write("\nconsole.log(JSON.stringify(")
        handle.write(body)
        handle.write("));\n")
        path = handle.name

    result = subprocess.run([node, path], capture_output=True, text=True, timeout=300, check=True)
    return json.loads(result.stdout.strip().splitlines()[-1])


# ── единицы действия ────────────────────────────────────────────────────────


def test_db_has_unit_dosed_drugs() -> None:
    """Предусловие: если таких препаратов не станет, тест перестанет что-либо ловить."""
    db = json.loads(DB_PATH.read_text(encoding="utf-8-sig"))
    units = {k: v.get("dose_unit") for k, v in (db.get("drugs_reference") or {}).items()
             if isinstance(v, dict) and v.get("dose_unit")}

    assert "benzylpenicillin_na" in units and units["benzylpenicillin_na"] == "ЕД"
    assert "benzathine_benzylpenicillin" in units


@pytest.mark.skipif(node is None, reason="node is required to execute the shipped calculator script")
def test_no_unit_dosed_drug_is_rendered_in_milligrams() -> None:
    """Сплошной проход: ни один препарат в ЕД не рендерится в «мг»."""
    verdict = _run(
        """(() => {
      const bad = []; let checked = 0;
      for (const rec of DB.recommendations)
        for (const sc of (rec.scenarios || []))
          for (const ln of (sc.lines || []))
            for (const d of (ln.drugs || [])) {
              const ref = DB.drugs_reference[d.drug_ref] || {};
              if (ref.dose_unit !== 'ЕД') continue;
              for (const reg of (d.regimens || []))
                for (const w of [3, 20, 70]) {
                  const r = computeDose(reg, w, 'мг');
                  if (r.noDose || r.needWeight) continue;
                  checked++;
                  const text = fmtDose(r.singleMg, doseUnitOf(ref));
                  if (text.includes('мг')) bad.push(rec.id + '/' + d.drug_ref + ' -> ' + text);
                }
            }
      return { checked, bad: bad.slice(0, 5), count: bad.length };
    })()"""
    )

    assert verdict["checked"] > 0, "не проверено ни одного режима препарата в ЕД"
    assert verdict["count"] == 0, f"препарат в ЕД отрендерен в мг: {verdict['bad']}"


@pytest.mark.skipif(node is None, reason="node is required to execute the shipped calculator script")
def test_unit_formatting_is_readable() -> None:
    verdict = _run(
        """(() => ({
      mg:        fmtDose(500, 'мг'),
      units:     fmtDose(4000000, 'ЕД'),
      millionth: fmtDose(1500000, 'ЕД'),
      thousand:  fmtDose(300000, 'ЕД'),
      default:   fmtDose(250, undefined),
    }))()"""
    )

    assert verdict == {
        "mg": "500 мг",
        "units": "4 млн ЕД",
        "millionth": "1.5 млн ЕД",
        "thousand": "300 тыс ЕД",
        "default": "250 мг",
    }


@pytest.mark.parametrize(
    ("regimen", "dose_unit", "expected"),
    [
        ({"single_dose_mg": 4000000, "freq_per_day": 6}, "ЕД", "4000000 ЕД 6 р/д"),
        ({"single_dose_mg": 1500000, "freq_per_day": 4}, "ЕД", "1500000 ЕД 4 р/д"),
        ({"dose_mg_kg_day": 300000, "freq_per_day": 6}, "ЕД", "300000 ЕД/кг/сут 6 р/д"),
        ({"dose_mg_day_fixed": 18000000, "freq_per_day": 6}, "ЕД", "18000000 ЕД/сут 6 р/д"),
        # Без dose_unit остаётся мг — поведение для остальных препаратов не меняется.
        ({"single_dose_mg": 500, "freq_per_day": 3}, None, "500 мг 3 р/д"),
        ({"single_dose_mg": 500, "freq_per_day": 3}, "мг", "500 мг 3 р/д"),
    ],
)
def test_build_label_uses_the_drug_dose_unit(regimen, dose_unit, expected):
    assert build_label(regimen, parse_duration(None), dose_unit) == expected


def test_build_label_never_mixes_units_inside_one_label():
    label = build_label({"single_dose_mg": 2400000, "freq_per_day": 1}, parse_duration("21"), "ЕД")

    assert label == "2400000 ЕД 1 р/д 21 дн"
    assert "мг" not in label


def test_shipped_db_has_no_unit_dosed_label_in_milligrams():
    """Отгруженная БД: все метки препаратов в ЕД используют ЕД."""
    db = json.loads(DB_PATH.read_text(encoding="utf-8-sig"))
    refs = db.get("drugs_reference") or {}

    labels = []
    for rec in db["recommendations"]:
        for scenario in rec.get("scenarios") or []:
            for line in scenario.get("lines") or []:
                for drug in line.get("drugs") or []:
                    unit = (refs.get(drug.get("drug_ref")) or {}).get("dose_unit")
                    if unit != "ЕД":
                        continue
                    for regimen in drug.get("regimens") or []:
                        if regimen.get("regimen_label"):
                            labels.append(regimen["regimen_label"])

    assert len(labels) >= 16, f"ожидалось не менее 16 меток, получено {len(labels)}"
    wrong = [label for label in labels if "мг" in label]
    assert wrong == [], f"метки препаратов в ЕД содержат «мг»: {wrong}"


# ── молчаливый ноль вместо дозы ─────────────────────────────────────────────


@pytest.mark.skipif(node is None, reason="node is required to execute the shipped calculator script")
def test_doseless_regimen_is_flagged_instead_of_returning_zero() -> None:
    verdict = _run(
        """(() => ({
      nothing:  computeDose({freq_per_day: 6, duration_days: '3 дня'}, 70, 'ЕД'),
      onlyFreq: computeDose({age_group: 'adult'}, 70, 'мг'),
      withDose: computeDose({single_dose_mg: 500, freq_per_day: 3}, 70, 'мг'),
    }))()"""
    )

    assert verdict["nothing"]["noDose"] is True
    assert verdict["onlyFreq"]["noDose"] is True
    assert verdict["withDose"]["noDose"] is False
    assert verdict["withDose"]["singleMg"] == 500


@pytest.mark.skipif(node is None, reason="node is required to execute the shipped calculator script")
def test_no_regimen_silently_returns_zero_without_flagging_it() -> None:
    """Ни один режим не должен давать 0 молча: либо доза, либо noDose, либо needWeight."""
    verdict = _run(
        """(() => {
      const silent = []; let checked = 0;
      for (const rec of DB.recommendations)
        for (const sc of (rec.scenarios || []))
          for (const ln of (sc.lines || []))
            for (const d of (ln.drugs || []))
              for (const reg of (d.regimens || []))
                for (const w of [3, 20, 70]) {
                  const r = computeDose(reg, w, 'мг');
                  checked++;
                  if (!r.noDose && !r.needWeight && r.singleMg === 0 && r.dailyMg === 0) {
                    silent.push(rec.id + '/' + (d.drug_ref || d.combo_ref));
                  }
                }
      return { checked, silent: silent.slice(0, 5), count: silent.length };
    })()"""
    )

    assert verdict["checked"] > 1500, verdict
    assert verdict["count"] == 0, f"молчаливый ноль вместо дозы: {verdict['silent']}"


@pytest.mark.skipif(node is None, reason="node is required to execute the shipped calculator script")
def test_doseless_regimens_are_all_inside_blocked_diseases() -> None:
    """Пока расчёт закрыт, noDose недостижим; тест ловит момент, когда это изменится."""
    verdict = _run(
        """(() => {
      let doseless = 0, openDisease = 0; const open = [];
      for (const rec of DB.recommendations)
        for (const sc of (rec.scenarios || []))
          for (const ln of (sc.lines || []))
            for (const d of (ln.drugs || []))
              for (const reg of (d.regimens || [])) {
                if (!computeDose(reg, 70, 'мг').noDose) continue;
                doseless++;
                if (!rec.calculation_blocked) { openDisease++; open.push(rec.id); }
              }
      return { doseless, openDisease, open: open.slice(0, 5) };
    })()"""
    )

    assert verdict["doseless"] == 27, verdict
    assert verdict["openDisease"] == 0, (
        f"режим без дозы в открытой нозологии — расчёт покажет пустоту: {verdict['open']}"
    )


def test_template_explains_the_absence_of_a_numeric_dose() -> None:
    source = TEMPLATE.read_text(encoding="utf-8")

    assert "noDose" in source
    assert "не указана числовая доза" in source
    assert "function showNoCalculation(" in source
