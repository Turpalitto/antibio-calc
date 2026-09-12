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


# ── прочность таблетки: один делитель на все пути вывода ──────────────────────

_TABLET_SWEEP = """(() => {
  let diverged = [];
  let checked = 0;
  for (const [key, ref] of Object.entries(DB.drugs_reference)) {
    if (key === '_note' || !ref || typeof ref !== 'object') continue;
    for (const f of (ref.forms || [])) {
      if (!['tablet', 'capsule'].includes(f.form_type)) continue;
      checked++;
      const viaHelper = tabletStrengthMg(f);
      const viaPrint = parseFloat(f.concentration);
      if (viaHelper !== viaPrint) {
        diverged.push(key + ' "' + f.concentration + '": helper=' + viaHelper + ' print=' + viaPrint);
      }
    }
  }
  const amox = DB.drugs_reference.amoxiclav.forms.find(f => f.concentration === '875+125 мг');
  const cotrim = DB.drugs_reference.cotrimoxazole.forms.find(f => f.concentration === '400+80 мг');
  return {
    diverged: diverged,
    checked: checked,
    amoxiclavStrength: tabletStrengthMg(amox),
    amoxiclavFormatted: formatTablets(875, amox),
    cotrimStrength: tabletStrengthMg(cotrim),
  };
})()"""

_NON_TABLET_PROBE = """(() => {
  const ref = DB.drugs_reference.benzylpenicillin_na;
  const inj = (ref.forms || []).find(f => f.form_type === 'powder_for_injection');
  return {
    strength: tabletStrengthMg(inj),
    formatted: formatTablets(1000000, inj),
    nullStrength: tabletStrengthMg(null),
    nullFormatted: formatTablets(500, null),
  };
})()"""

_TABLET_HELPERS = ("tabletStrengthMg", "formatTablets")


def test_composite_tablet_strength_uses_the_first_component() -> None:
    """«875+125 мг» → 875, а не 125: делим на основной компонент.

    Раньше ``formatTablets`` брал ПОСЛЕДНЕЕ число перед «мг» регуляркой
    ``/(\\d+)\\s*мг/`` — для «875+125 мг» это 125 (клавуланат), и на дозу 875 мг
    печаталось «7 таб 125 мг», тогда как печатная форма на том же экране считала
    одну таблетку. Семикратная передозировка в подсказке.
    """
    probe = _run(_TABLET_SWEEP, helpers=_TABLET_HELPERS)

    assert probe["checked"] >= 50, probe
    assert probe["diverged"] == [], probe
    assert probe["amoxiclavStrength"] == 875, probe
    assert probe["cotrimStrength"] == 400, probe
    # Было «(7 таб 125 мг)».
    assert probe["amoxiclavFormatted"] == "(1 таб 875 мг)", probe


def test_non_tablet_forms_are_never_counted_as_tablets() -> None:
    """Инъекционный флакон и отсутствующая форма не должны давать таблеток."""
    probe = _run(_NON_TABLET_PROBE, helpers=_TABLET_HELPERS)

    assert probe["strength"] is None, probe
    assert probe["formatted"] == "", probe
    assert probe["nullStrength"] is None, probe
    assert probe["nullFormatted"] == "", probe


def test_printed_prescription_uses_the_shared_strength_helper() -> None:
    """Оба места печати таблеток обязаны идти через tabletStrengthMg.

    Расхождение между точками вывода — тот же источник ошибок, что расхождение
    между ветками ``computeDose``. Единственное допустимое вхождение
    ``parseFloat(form.concentration)`` — внутри самого хелпера.
    """
    template = TEMPLATE.read_text(encoding="utf-8")
    offenders = [line.strip() for line in template.splitlines() if "parseFloat(form.concentration)" in line]

    assert len(offenders) == 1, offenders
    assert offenders[0] == "const strength = parseFloat(form.concentration);"
    assert "tabletStrengthMg(form)" in template


# ── концентрация флакона: одно извлечение на три точки вывода ─────────────────

_VIAL_HELPERS = (
    "formatUnits",
    "vialConcentrationPerMl",
    "vialStrengthLabel",
    "vialConcentrationLabel",
    "injectableMlForDose",
    "computeInjectableMl",
)

# Старые реализации, продублированные в трёх местах до рефакторинга. Сравнение с
# ними доказывает, что консолидация ничего не изменила в надписях.
_VIAL_OLD_VS_NEW = """(() => {
  function OLD_strength(v, units){
    if(!v) return '';
    if(units) return v.vial_mg ? v.vial_mg+' mg' : (v.vial_units ? formatUnits(v.vial_units)+' ED' : '');
    return v.vial_mg ? v.vial_mg+' мг' : (v.vial_units ? formatUnits(v.vial_units)+' ЕД' : '');
  }
  function OLD_conc(v, units){
    if(units) return v.final_concentration_mg_ml ? v.final_concentration_mg_ml+' mg/ml'
      : (v.final_concentration_units_ml ? formatUnits(v.final_concentration_units_ml)+' ED/ml' : '');
    return v.final_concentration_mg_ml ? v.final_concentration_mg_ml+' мг/мл'
      : (v.final_concentration_units_ml ? formatUnits(v.final_concentration_units_ml)+' ЕД/мл' : '');
  }
  function OLD_ml(singleMg, v, units){
    const c = (v.final_concentration_mg_ml || v.final_concentration_units_ml);
    return c ? (singleMg / c).toFixed(2)+' '+(units ? 'ml' : 'мл') : (units ? '—' : '');
  }
  function OLD_injectable(singleMg, v){
    if(!v) return '—';
    const conc = v.final_concentration_mg_ml || v.final_concentration_units_ml || 0;
    if(conc <= 0) return '—';
    return (singleMg / conc).toFixed(2)+' мл';
  }

  let diffs = [];
  let checked = 0;
  for (const [key, ref] of Object.entries(DB.drugs_reference)) {
    if (key === '_note' || !ref || typeof ref !== 'object') continue;
    for (const [route, data] of Object.entries(ref.dilution || {})) {
      if (!data || typeof data !== 'object') continue;
      for (const v of (data.solvent_options || [])) {
        for (const units of [false, true]) {
          checked++;
          if (vialStrengthLabel(v, units) !== OLD_strength(v, units)) diffs.push('strength ' + key + '/' + route);
          if (vialConcentrationLabel(v, units) !== OLD_conc(v, units)) diffs.push('conc ' + key + '/' + route);
          if (injectableMlForDose(500, v, units) !== OLD_ml(500, v, units)) diffs.push('ml ' + key + '/' + route);
        }
        if (computeInjectableMl(500, v) !== OLD_injectable(500, v)) diffs.push('injectable ' + key + '/' + route);
      }
    }
  }
  return { checked: checked, diffs: diffs };
})()"""


def test_vial_labels_are_unchanged_by_the_consolidation() -> None:
    """Рефакторинг обязан быть сохраняющим поведение: сверка со старым рендером."""
    probe = _run(_VIAL_OLD_VS_NEW, helpers=_VIAL_HELPERS)

    assert probe["checked"] >= 150, probe
    assert probe["diffs"] == [], probe


def test_vial_strength_keeps_milligrams_unabbreviated() -> None:
    """«1000 мг», а не «1 тыс мг»: formatUnits только для единиц действия.

    В БД есть ``vial_mg`` 1000/1500/2000/4000, и ``formatUnits`` превратил бы их
    в «1 тыс мг» / «1.5 тыс мг». Для единиц действия сокращение, наоборот, нужно:
    1000000 → «1 млн ЕД».
    """
    probe = _run(
        """(() => {
          const mg = DB.drugs_reference.amoxiclav.dilution.iv_infusion.solvent_options[0];
          const dilution = DB.drugs_reference.benzylpenicillin_na.dilution;
          const ed = dilution[Object.keys(dilution)[0]].solvent_options[0];
          return {
            mgLabel: vialStrengthLabel(mg, false),
            mgLatin: vialStrengthLabel(mg, true),
            edLabel: vialStrengthLabel(ed, false),
            edConc: vialConcentrationLabel(ed, false),
            mgConc: vialConcentrationLabel(mg, false),
          };
        })()""",
        helpers=_VIAL_HELPERS,
    )

    assert probe["mgLabel"] == "1000 мг", probe
    assert probe["mgLatin"] == "1000 mg", probe
    assert probe["edLabel"].endswith(" ЕД"), probe
    assert "тыс" not in probe["mgLabel"], probe
    assert probe["edConc"].endswith("ЕД/мл"), probe
    assert probe["mgConc"].endswith("мг/мл"), probe


def test_vial_helpers_degrade_instead_of_printing_nan() -> None:
    """Отсутствующий флакон или доза — пустая строка / прочерк, но не NaN."""
    probe = _run(
        """(() => {
          const am = DB.drugs_reference.amoxiclav.dilution.iv_infusion.solvent_options[0];
          return {
            nullVial: computeInjectableMl(500, null),
            zeroDose: computeInjectableMl(0, am),
            zeroDoseRu: injectableMlForDose(0, am, false),
            zeroDoseLatin: injectableMlForDose(0, am, true),
            nullStrength: vialStrengthLabel(null, false),
            emptyConc: vialConcentrationLabel({}, false),
            emptyMl: injectableMlForDose(500, {}, false),
          };
        })()""",
        helpers=_VIAL_HELPERS,
    )

    assert probe["nullVial"] == "—", probe
    assert probe["zeroDose"] == "—", probe
    assert probe["zeroDoseRu"] == "", probe
    assert probe["zeroDoseLatin"] == "—", probe
    assert probe["nullStrength"] == "", probe
    assert probe["emptyConc"] == "", probe
    assert probe["emptyMl"] == "", probe
    assert "NaN" not in json.dumps(probe, ensure_ascii=False), probe


def test_no_duplicated_concentration_fallback_remains() -> None:
    """`||`-фолбэк по двум полям концентрации больше не встречается нигде.

    Именно он был продублирован в трёх местах (подсказка «на дозу», блок
    разведения, латинская форма). Хелпер выбирает поле явными проверками ``> 0``,
    поэтому фолбэка в шаблоне не остаётся вовсе — и разойтись больше нечему.
    """
    template = TEMPLATE.read_text(encoding="utf-8")
    offenders = [
        line.strip()
        for line in template.splitlines()
        if ("final_concentration_mg_ml ||" in line or "final_concentration_mg_ml||" in line)
    ]

    assert offenders == [], offenders
    assert "function vialConcentrationPerMl" in template
    # Все три точки вывода обязаны идти через хелперы.
    for helper in ("vialStrengthLabel", "vialConcentrationLabel", "injectableMlForDose"):
        assert template.count(helper + "(") >= 3, f"{helper} используется реже, чем в трёх точках"


# ── единица в точках вывода, которые раньше писали «мг/кг» по месту ───────────

_DOM_STUB_UNITS = """
class ClassList{
  constructor(){ this.set=new Set(); }
  add(...c){ c.forEach(x=>this.set.add(x)); }
  remove(...c){ c.forEach(x=>this.set.delete(x)); }
  toggle(c,f){ const on=f===undefined?!this.set.has(c):!!f; on?this.set.add(c):this.set.delete(c); return on; }
  contains(c){ return this.set.has(c); }
}
class El{
  constructor(t){ this.tag=t; this.children=[]; this.classList=new ClassList();
                  this._text=''; this.className=''; this._html=''; this._span=null; }
  append(...n){ n.forEach(x=>this.children.push(x)); }
  appendChild(n){ this.children.push(n); return n; }
  querySelector(sel){ if(!this._span) this._span=new El('span'); return this._span; }
  querySelectorAll(){ return []; }
  set innerHTML(v){ this._html=String(v); this.children=[]; }
  get innerHTML(){ return this._html||''; }
  set textContent(v){ this._text=String(v); }
  get textContent(){ return this._text; }
}
const _warn=new El('div'), _regList=new El('div'), _regSel=new El('div');
const _weight=new El('input'); _weight.value='';
const document={createElement:t=>new El(t), getElementById:id=>new El('div'), querySelectorAll:()=>[]};
function $(id){
  if(id==='weight-warn') return _warn;
  if(id==='weight') return _weight;
  if(id==='regimen-list') return _regList;
  if(id==='regimen-selector') return _regSel;
  return new El('div');
}
let activeAge='neonate', activeDrug=null, activeRegimenIdx=0;
function calculate(){}
"""


def _run_dom(body: str, fns: tuple[str, ...]) -> dict:
    """Исполняет собранный JS с DOM-заглушкой — для функций, трогающих документ."""
    script, db = _script_and_db()
    parts = [f"const DB = {json.dumps(db, ensure_ascii=False)};", _DOM_STUB_UNITS]
    parts += [_extract(script, name) for name in fns]
    parts.append("console.log(JSON.stringify(" + body + "));")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as handle:
        handle.write("\n".join(parts) + "\n")
        path = handle.name
    result = subprocess.run([node, path], capture_output=True, text=True, timeout=300, check=True)
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_weight_warning_names_the_actual_dose_unit() -> None:
    """Предупреждение о весе называет ту единицу, в которой задана доза.

    У бензилпенициллина доза в ЕД/кг, и в БД 5 таких режимов. Раньше сообщение
    жёстко говорило «рассчитывается по мг/кг».
    """
    verdict = _run_dom(
        """(() => {
      const out = {};
      updateWeightWarn(true, 'ЕД');      out.units = _warn.querySelector('span').textContent;
      updateWeightWarn(true, 'мг');      out.mg = _warn.querySelector('span').textContent;
      updateWeightWarn(true, undefined); out.fallback = _warn.querySelector('span').textContent;
      return out;
    })()""",
        ("updateWeightWarn",),
    )
    assert "ЕД/кг" in verdict["units"], verdict
    assert "мг/кг" not in verdict["units"], verdict
    assert "мг/кг" in verdict["mg"], verdict
    assert "мг/кг" in verdict["fallback"], verdict


def test_calculate_passes_the_unit_into_the_weight_warning() -> None:
    """Единица должна доходить от справочника до предупреждения."""
    script, _db = _script_and_db()
    calc = _extract(script, "calculate")
    assert "updateWeightWarn(needWeight, unit)" in calc, (
        "calculate() обязан передавать единицу в updateWeightWarn"
    )


def test_regimen_label_uses_the_reference_unit_not_a_hardcoded_one() -> None:
    """Метка режима берёт единицу из справочника."""
    db = json.loads(DB_PATH.read_text(encoding="utf-8-sig"))
    units_drug = next(
        ref
        for ref, entry in (db.get("drugs_reference") or {}).items()
        if isinstance(entry, dict) and entry.get("dose_unit") == "ЕД"
    )
    verdict = _run_dom(
        """(() => {
      activeDrug = {drug_ref: %s, regimens: [
        {age_group:'neonate', dose_mg_kg_day: 100000, freq_per_day: 4},
        {age_group:'neonate', dose_mg_kg_day: 50000,  freq_per_day: 2},
      ]};
      activeAge = 'neonate';
      renderRegimens(0);
      return { label: _regList.children[0].textContent, drug: %s };
    })()"""
        % (json.dumps(units_drug), json.dumps(units_drug)),
        ("renderRegimens", "getDrugRefs", "doseUnitOf"),
    )
    assert verdict["drug"] == units_drug
    assert "ЕД/кг" in verdict["label"], verdict
    assert "мг/кг" not in verdict["label"], verdict


def test_no_dead_local_variables_anywhere_in_the_shipped_script() -> None:
    """Ни одна локальная переменная shipped-JS не вычисляется впустую.

    Так были найдены ``freqStr`` и ``routeLat`` в печати рецепта (обе держали
    недостижимыми карты ``LATIN_FREQ`` и ``LATIN_ROUTE``) и ``mainRef`` в
    ``renderRegimens``. Проверка перебирает все функции верхнего уровня.
    """
    script, _db = _script_and_db()
    functions = []
    for match in re.finditer(r"\nfunction ([A-Za-z_][A-Za-z0-9_]*)\(", script):
        i, depth, started = match.start(), 0, False
        while i < len(script):
            if script[i] == "{":
                depth += 1
                started = True
            elif script[i] == "}":
                depth -= 1
                if started and depth == 0:
                    i += 1
                    break
            i += 1
        functions.append((match.group(1), script[match.start():i]))

    assert len(functions) >= 70, f"ожидалось не менее 70 функций, найдено {len(functions)}"

    dead = [
        (name, decl)
        for name, body in functions
        for decl in set(re.findall(r"^\s*(?:const|let)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=", body, re.M))
        if len(re.findall(r"(?<![.\w])" + re.escape(decl) + r"(?![\w])", body)) <= 1
    ]
    assert dead == [], f"переменные вычисляются и не используются: {dead}"


def test_no_hardcoded_per_kg_unit_remains_in_display_code() -> None:
    """«мг/кг» не пишется по месту ни в одной точке вывода."""
    template = TEMPLATE.read_text(encoding="utf-8")
    offenders = [
        line.strip()
        for line in template.splitlines()
        if "мг/кг" in line
        and not line.strip().startswith("//")
        and "id=\"db-data\"" not in line
        # документированный фолбэк, когда у кандидата нет unit
        and "candidate.dose.unit || 'мг/кг'" not in line
    ]
    assert offenders == [], offenders
