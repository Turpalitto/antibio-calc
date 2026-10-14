#!/usr/bin/env node
/* Exhaustive DOM walk of the built shell: every computable nosology → every
 * age-matching scenario → every drug card → every route tab → every form chip,
 * for a few patient profiles. Reports anything a physician must never see
 * (NaN / Infinity / undefined / "[object" in the visible result, console
 * errors, an empty result with no block reason).
 *
 * usage: node shell_walk.js <built html> <app.css>  → JSON on stdout
 */
'use strict';
const fs = require('fs');
const path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');

const [htmlPath, cssPath] = process.argv.slice(2);
const consoleErrors = [];
const vc = new VirtualConsole();
vc.on('error', (m) => consoleErrors.push(String(m)));
vc.on('jsdomError', (e) => consoleErrors.push(String(e && e.message)));

const html = fs.readFileSync(htmlPath, 'utf-8');
const dom = new JSDOM(html, {
  runScripts: 'dangerously',
  pretendToBeVisual: true,
  url: 'http://127.0.0.1:8080/' + path.basename(htmlPath),
  virtualConsole: vc,
});
const w = dom.window;
const d = w.document;
const style = d.createElement('style');
style.textContent = fs.readFileSync(cssPath, 'utf-8');
d.head.appendChild(style);
w.scrollTo = () => {};
w.navigator.clipboard = { writeText: (t) => ((w.__copied = t), Promise.resolve()) };
w.print = () => {};

const $ = (id) => d.getElementById(id);
const txt = (el) => (el ? el.textContent.replace(/\s+/g, ' ').trim() : '');
const visible = (el) => !!el && !el.classList.contains('hidden') && w.getComputedStyle(el).display !== 'none';
const fire = (el, type) => el.dispatchEvent(new w.Event(type, { bubbles: true }));
const type = (el, value) => { el.value = value; fire(el, 'input'); fire(el, 'change'); };
const BAD = /\bNaN\b|Infinity|undefined|\[object |null мг|null ЕД/;
// «1000 мг» / «1.5 млн ЕД» / «625 тыс» / «1 005 000» (formatUnits for ЕД) → a number
const num = (shown) => {
  const mul = /млн/.test(shown) ? 1e6 : (/тыс/.test(shown) ? 1e3 : 1);
  return parseFloat(String(shown).replace(/[\s\u00a0]/g, '').replace(/мг|ЕД|млн|тыс/g, '').replace(',', '.')) * mul;
};
// the dose token of an export line: «по 175 тыс ЕД», «по 22.5 мл (1125 мг)», «по 500 мг»
const exportDose = (line, mlWord) => {
  const m = line.match(new RegExp('по (?:\\d+(?:[.,]\\d+)? мл' + (mlWord ? '(?: ' + mlWord + ')?' : '') + ' \\()?(\\d+(?:[.,]\\d+)?(?: (?:млн|тыс))?) (мг|ЕД)'));
  return m ? { value: num(m[1] + (m[2] === 'ЕД' ? ' ЕД' : ' мг')), unit: m[2] } : null;
};

// Override for ad-hoc sweeps: SHELL_WALK_PROFILES='[{"name":"child_14.3","age":"3","unit":"years","weight":"14.3"}]'
const PROFILES = process.env.SHELL_WALK_PROFILES ? JSON.parse(process.env.SHELL_WALK_PROFILES) : [
  { name: 'adult_70', age: '35', unit: 'years', weight: '70' },
  { name: 'child_7y_25kg', age: '7', unit: 'years', weight: '25' },
  { name: 'infant_6m_7kg', age: '6', unit: 'months', weight: '7' },
  { name: 'neonate_10d_3kg', age: '10', unit: 'days', weight: '3.2' },
];

function resultSnapshot() {
  const block = visible($('dose-block')) ? txt($('dose-block')) : '';
  const parts = ['res-po', 'res-inj', 'dilution-block', 'reconstitution-block', 'combo-block', 'res-note', 'drug-meta', 'regimen-selector']
    .filter((id) => visible($(id))).map((id) => txt($(id)));
  return { block, text: parts.join(' | ') };
}

setTimeout(() => {
  const out = { profiles: {}, consoleErrors, findings: [] };
  if (!w.eval('DB')) w.eval('init()');
  const DB = w.eval('DB');
  const computable = DB.recommendations.filter((r) => !r.calculation_blocked);
  out.computable = computable.length;
  for (const profile of PROFILES) {
    const stats = { diseases: 0, scenarios: 0, drugs: 0, forms: 0, blocked: 0, computed: 0, empty: 0, exports: 0 };
    type($('patient-age-unit'), profile.unit);
    type($('patient-age'), profile.age);
    type($('weight'), profile.weight);
    for (const rec of computable) {
      w.selectDisease(rec);
      stats.diseases++;
      const scenarioCards = [...d.querySelectorAll('#scenario-list .scenario-card')].filter((c) => !c.classList.contains('opacity-50'));
      for (const sc of scenarioCards) {
        sc.click();
        stats.scenarios++;
        const drugCards = [...d.querySelectorAll('#drug-list .drug-card')];
        for (const dc of drugCards) {
          dc.click();
          stats.drugs++;
          const tabs = [...d.querySelectorAll('#route-tabs button')];
          const tabLoops = tabs.length ? tabs : [null];
          for (const tab of tabLoops) {
            if (tab) tab.click();
            const chips = [...d.querySelectorAll('#form-grid button')];
            const chipLoops = chips.length ? chips : [null];
            for (const chip of chipLoops) {
              if (chip) chip.click();
              stats.forms++;
              const snap = resultSnapshot();
              const where = `${profile.name} › ${rec.id} › ${w.eval('activeScenario && activeScenario.id')} › ${txt(dc).slice(0, 40)} › ${tab ? txt(tab) : '-'} › ${chip ? txt(chip).slice(0, 30) : '-'}`;
              if (snap.block) stats.blocked++;
              else if (snap.text) stats.computed++;
              else { stats.empty++; out.findings.push({ kind: 'empty_result', where }); }
              const all = snap.block + ' ' + snap.text;
              if (BAD.test(all)) out.findings.push({ kind: 'bad_token', where, sample: all.match(/.{0,40}(NaN|Infinity|undefined|\[object |null мг|null ЕД).{0,40}/)[0] });
              if (visible($('res-po')) && /^0 мг|^0 ЕД| 0 мг | 0 таб/.test(txt($('po-mg')) + ' ' + txt($('po-tabs')))) {
                out.findings.push({ kind: 'zero_dose', where, sample: txt($('po-mg')) + ' / ' + txt($('po-tabs')) });
              }
              if (!snap.block) {
                // the regimen actually used must fit the patient's age group
                const reg = w.eval('getActiveRegimen()');
                const activeAge = w.eval('activeAge');
                if (!reg) out.findings.push({ kind: 'no_regimen_but_computed', where });
                else if (reg.age_group && reg.age_group !== 'all' && reg.age_group !== activeAge) {
                  out.findings.push({ kind: 'age_group_mismatch', where, sample: `regimen ${reg.age_group} for ${activeAge}` });
                }
                // arithmetic oracle: the single dose on screen must be what the DB regimen
                // gives for this weight — re-derived here independently of computeDose
                // (single_dose_mg × freq, else mg/kg/day × weight, else fixed daily; the
                // daily ceiling max_daily_mg cuts the single dose too).
                if (reg) {
                  const kg = parseFloat(profile.weight);
                  const freq = reg.freq_per_day || 1;
                  let daily = null;
                  if (reg.single_dose_mg != null) daily = reg.single_dose_mg * freq;
                  else if (reg.dose_mg_kg_per_dose != null) daily = kg * reg.dose_mg_kg_per_dose * freq;
                  else if (reg.dose_mg_kg_day != null) daily = kg * reg.dose_mg_kg_day;
                  else if (reg.dose_mg_day_fixed != null) daily = reg.dose_mg_day_fixed;
                  if (daily != null && reg.max_daily_mg != null && daily > reg.max_daily_mg) daily = reg.max_daily_mg;
                  const expectSingle = daily != null ? daily / freq : null;
                  const po = visible($('res-po'));
                  const shown = po ? txt($('po-mg')) : (visible($('res-inj')) ? txt($('inj-mg')) : '');
                  const shownDay = po ? txt($('po-day')) : (visible($('res-inj')) ? txt($('inj-day')) : '');
                  const regStr = JSON.stringify({ s: reg.single_dose_mg, kg: reg.dose_mg_kg_day, fx: reg.dose_mg_day_fixed, max: reg.max_daily_mg, f: reg.freq_per_day });
                  if (expectSingle != null && Number.isFinite(num(shown))) {
                    if (Math.abs(num(shown) - expectSingle) > 1) out.findings.push({ kind: 'dose_arithmetic', where, sample: `screen ${shown} vs regimen ${regStr} × ${kg} kg → ${Math.round(expectSingle)}` });
                    // the daily tile must be the same arithmetic (1 050 000 ЕД once read «15 млн ЕД»)
                    if (Number.isFinite(num(shownDay)) && Math.abs(num(shownDay) - daily) > 1) out.findings.push({ kind: 'daily_dose_arithmetic', where, sample: `screen daily ${shownDay} vs regimen ${regStr} × ${kg} kg → ${Math.round(daily)}` });
                    stats.arithmeticOracle = (stats.arithmeticOracle || 0) + 1;
                    // volume oracle: ml on screen = single dose / concentration of the
                    // suspension (po) or of the selected vial's final solution (im/iv)
                    const formNow = w.eval('(DB.drugs_reference[getDrugRefs(activeDrug)[0]] || {forms:[]}).forms[activeFormIdx] || null');
                    if (po && txt($('po-unit')) === 'мл' && /^\d/.test(txt($('po-ml')))) {
                      const conc = formNow && formNow.concentration_mg_per_ml;
                      const ml = parseFloat(txt($('po-ml')).replace(',', '.'));
                      if (!(conc > 0)) out.findings.push({ kind: 'po_ml_without_concentration', where, sample: txt($('po-ml')) });
                      else if (Math.abs(ml - expectSingle / conc) > 0.06) out.findings.push({ kind: 'po_volume_arithmetic', where, sample: `screen ${ml} мл vs ${Math.round(expectSingle)} / ${conc} мг/мл = ${(expectSingle / conc).toFixed(2)}` });
                      else stats.volumeOracle = (stats.volumeOracle || 0) + 1;
                    } else if (!po && /^\d/.test(txt($('inj-ml')))) {
                      const vial = w.eval('(function(){ const ref = DB.drugs_reference[getDrugRefs(activeDrug)[0]] || {}; const rd = (ref.dilution || {})[activeRouteKey] || {}; return (rd.solvent_options || [])[activeVialIdx] || null; })()');
                      const conc = vial && (vial.final_concentration_mg_ml || vial.final_concentration_units_ml);
                      const ml = parseFloat(txt($('inj-ml')).replace(',', '.'));
                      if (!(conc > 0)) out.findings.push({ kind: 'inj_ml_without_concentration', where, sample: txt($('inj-ml')) });
                      else if (Math.abs(ml - expectSingle / conc) > 0.006) out.findings.push({ kind: 'inj_volume_arithmetic', where, sample: `screen ${ml} мл vs ${Math.round(expectSingle)} / ${conc} per ml = ${(expectSingle / conc).toFixed(3)}` });
                      else stats.volumeOracle = (stats.volumeOracle || 0) + 1;
                    }
                  } else if (expectSingle != null && !shown.startsWith('—')) {
                    out.findings.push({ kind: 'dose_not_shown', where, sample: `expected ${Math.round(expectSingle)}, screen «${shown}»` });
                  }
                  // combination partners: each card «По N мг k р/д» = component_regimens × weight
                  const partners = w.eval('getDrugRefs(activeDrug).slice(1)');
                  if (partners.length && visible($('combo-block'))) {
                    const cards = [...d.querySelectorAll('#combo-block .premium-card')];
                    partners.forEach((key, pi) => {
                      const pr = (reg.component_regimens || {})[key];
                      const card = cards[pi];
                      if (!pr || !card) { out.findings.push({ kind: 'combo_partner_missing', where, sample: `${key}: regimen ${!!pr}, card ${!!card}` }); return; }
                      const pf = pr.freq_per_day || 1;
                      let pd = null;
                      if (pr.single_dose_mg != null) pd = pr.single_dose_mg * pf;
                      else if (pr.dose_mg_kg_per_dose != null) pd = kg * pr.dose_mg_kg_per_dose * pf;
                      else if (pr.dose_mg_kg_day != null) pd = kg * pr.dose_mg_kg_day;
                      else if (pr.dose_mg_day_fixed != null) pd = pr.dose_mg_day_fixed;
                      if (pd != null && pr.max_daily_mg != null && pd > pr.max_daily_mg) pd = pr.max_daily_mg;
                      const cardDose = txt(card).match(/По (\d+(?:[.,]\d+)?(?: (?:млн|тыс))? (?:мг|ЕД))/);
                      if (pd == null || !cardDose) return;
                      if (Math.abs(num(cardDose[1]) - pd / pf) > 1) out.findings.push({ kind: 'combo_partner_arithmetic', where, sample: `${key}: card «${cardDose[1]}» vs ${JSON.stringify(pr)} × ${kg} kg → ${Math.round(pd / pf)}` });
                      else stats.partnerOracle = (stats.partnerOracle || 0) + 1;
                    });
                  }
                }
                // the two physician-facing exports must be as clean as the screen
                w.__copied = '';
                w.copyForMIS();
                const mis = w.__copied || '';
                if (!mis) out.findings.push({ kind: 'mis_empty', where, sample: txt($('toast')) });
                else if (BAD.test(mis)) out.findings.push({ kind: 'mis_bad_token', where, sample: mis.match(/.{0,40}(NaN|Infinity|undefined|\[object |null мг|null ЕД).{0,40}/)[0] });
                else {
                  // oracle: the single dose on screen (po-mg / inj-mg, plain mg only)
                  // must be the one the MIS line «Схема приёма: по N мг …» carries
                  const screenEl = visible($('res-po')) ? $('po-mg') : (visible($('res-inj')) ? $('inj-mg') : null);
                  const screenUnit = visible($('res-po')) ? (txt($('po-mg')).endsWith('ЕД') ? 'ЕД' : '') : txt($('inj-unit'));
                  const screenMg = screenEl ? txt(screenEl).replace(/\s*мг$/, '') : '';
                  const screenVal = screenEl ? num(txt(screenEl)) : NaN;
                  const misLine = (mis.split('\n').find((l) => l.startsWith('Схема приёма:')) || '');
                  const misDose = exportDose(misLine, null);
                  if (Number.isFinite(screenVal) && misDose && !/топик|местно/.test(misLine)) {
                    if (misDose.unit !== (screenUnit === 'ЕД' ? 'ЕД' : 'мг') || Math.abs(misDose.value - screenVal) > 1) {
                      out.findings.push({ kind: 'mis_dose_differs_from_screen', where, sample: `screen ${txt(screenEl)} ${screenUnit} vs MIS «${misLine.slice(0, 80)}»` });
                    }
                    stats.doseOracle = (stats.doseOracle || 0) + 1;
                  }
                  // route oracle: the route the physician picked on screen must be the
                  // one every export names (fosfomycin granules were exported «в/в»)
                  const group = w.eval('currentRouteGroup');
                  const ROUTE_WORDS = { po: /внутрь/, im: /в\/м|внутримышечно/, iv: /в\/в|внутривенно/, topical: /наружно|местно/ };
                  const want = ROUTE_WORDS[group];
                  const misText = w.__copied;
                  w.__copied = '';
                  w.copyLatinRecipe();
                  const rp = w.__copied || '';
                  w.__rp = rp; w.__copied = misText;
                  const rpSigna = (rp.split('\n').find((l) => l.startsWith('S.:')) || '');
                  if (!rp) out.findings.push({ kind: 'rp_empty', where, sample: txt($('toast')) });
                  else if (BAD.test(rp)) out.findings.push({ kind: 'rp_bad_token', where, sample: rp.match(/.{0,40}(NaN|Infinity|undefined|\[object |null мг|null ЕД).{0,40}/)[0] });
                  if (want && /\d/.test(misLine)) {
                    const wrong = Object.entries(ROUTE_WORDS).filter(([g, re]) => g !== group && (g === 'po' || group === 'po') && re.test(misLine + ' ' + rpSigna));
                    if (!want.test(misLine)) out.findings.push({ kind: 'mis_route_missing', where, sample: `${group}: «${misLine.slice(0, 90)}»` });
                    if (rpSigna && !want.test(rpSigna)) out.findings.push({ kind: 'rp_route_missing', where, sample: `${group}: «${rpSigna.slice(0, 90)}»` });
                    if (wrong.length) out.findings.push({ kind: 'export_route_contradicts_screen', where, sample: `${group} vs ${wrong.map((x) => x[0]).join(',')}: «${misLine.slice(0, 60)}» / «${rpSigna.slice(0, 60)}»` });
                    stats.routeOracle = (stats.routeOracle || 0) + 1;
                  }
                  // Rp dose oracle (mg and ЕД, same rule as the MIS oracle)
                  const rpDose = exportDose(rpSigna, 'суспензии');
                  if (Number.isFinite(screenVal) && rpDose && group !== 'topical') {
                    if (rpDose.unit !== (screenUnit === 'ЕД' ? 'ЕД' : 'мг') || Math.abs(rpDose.value - screenVal) > 1) {
                      out.findings.push({ kind: 'rp_dose_differs_from_screen', where, sample: `screen ${txt(screenEl)} ${screenUnit} vs Rp «${rpSigna.slice(0, 80)}»` });
                    }
                    stats.rpDoseOracle = (stats.rpDoseOracle || 0) + 1;
                  }
                  // course units: MIS «суммарно N таб.», Rp «D.t.d. N. N» and the printed
                  // form «D.t.d. N N» must agree (they used to be packs / per-dose units)
                  const misTotal = mis.match(/суммарно (\d+) таб/);
                  const rpDtd = rp.match(/D\.t\.d\. N\. (\d+)/);
                  if (misTotal && rpDtd && misTotal[1] !== rpDtd[1]) out.findings.push({ kind: 'course_units_mis_vs_rp', where, sample: `MIS ${misTotal[1]} таб vs Rp N. ${rpDtd[1]}` });
                  if (rpDtd) w.__rpDtd = rpDtd[1]; else w.__rpDtd = null;
                  stats.unitsOracle = (stats.unitsOracle || 0) + (misTotal && rpDtd ? 1 : 0);
                  // course wording: a course given in words must never become «… дней»
                  const courseBad = (mis + '\n' + rp).match(/(хроническая|по ситуации|не указан[а-я]*|однократно) дн/);
                  if (courseBad) out.findings.push({ kind: 'course_words_plus_days', where, sample: courseBad[0] });
                }
                w.fillPrescriptionForm();
                const rx = txt($('prescription-form'));
                if (BAD.test(rx)) out.findings.push({ kind: 'rx_bad_token', where, sample: rx.match(/.{0,40}(NaN|Infinity|undefined|\[object |null мг|null ЕД).{0,40}/)[0] });
                if (!txt($('rx-drugs'))) out.findings.push({ kind: 'rx_empty', where, sample: txt($('rx-trust-line')).slice(0, 80) });
                if (/(хроническая|по ситуации|не указан[а-я]*) дн/.test(txt($('rx-course')))) out.findings.push({ kind: 'rx_course_words_plus_days', where, sample: txt($('rx-course')).slice(0, 80) });
                {
                  const rxDtd = txt($('rx-drugs')).match(/D\.t\.d\. N (\d+)/);
                  if (rxDtd && w.__rpDtd && rxDtd[1] !== w.__rpDtd) out.findings.push({ kind: 'course_units_rx_vs_rp', where, sample: `printed N ${rxDtd[1]} vs Rp N. ${w.__rpDtd}` });
                  // the printed breakdown must multiply out: N = per dose × р/д × days
                  const br = txt($('rx-drugs')).match(/D\.t\.d\. N (\d+) [^()]*\(по (\d+(?:[.,]\d+)?) на приём, (\d+) р\/д × (\d+) дн\.\)/);
                  if (br) {
                    const want = Math.ceil(parseFloat(br[2].replace(',', '.')) * parseInt(br[3]) * parseInt(br[4]) - 1e-9);
                    if (parseInt(br[1]) !== want) out.findings.push({ kind: 'course_quantity_arithmetic', where, sample: br[0] });
                    else stats.courseArithmeticOracle = (stats.courseArithmeticOracle || 0) + 1;
                  }
                }
                {
                  const group = w.eval('currentRouteGroup');
                  const ROUTE_WORDS = { po: /внутрь/, im: /в\/м|внутримышечно/, iv: /в\/в|внутривенно/, topical: /наружно|местно/ };
                  const signa = txt($('rx-signa-text'));
                  if (ROUTE_WORDS[group] && /\d/.test(signa) && !ROUTE_WORDS[group].test(signa)) out.findings.push({ kind: 'rx_route_missing', where, sample: `${group}: «${signa.slice(0, 90)}»` });
                  // grammar oracle: «1 раз / 2 раза / 5 раз в день», «1 день / 2 дня / 5 дней»
                  // across every text the physician can paste or print («1 раза в день» shipped once)
                  const everything = [w.__copied || '', w.__rp || '', signa, txt($('rx-drugs')), txt($('res-po')), txt($('res-inj'))].join('\n');
                  // (JS `\b` is ASCII-only — Cyrillic word ends need an explicit lookahead)
                  const END = '(?![а-яё])';
                  const GRAMMAR = [
                    // («не чаще 1 раза в 10 дней» is correct — only the daily-frequency phrase is checked)
                    [new RegExp('(^|[^\\d.,])(?:1|21|31)\\s+раза\\s+в\\s+(?:день|сутки)', 'u'), 'N раза (1/21)'],
                    [new RegExp('(^|[^\\d.,])(?:[5-9]|1\\d|20|2[5-9]|30)\\s+раза\\s+в\\s+(?:день|сутки)', 'u'), 'N раза (5–20)'],
                    [new RegExp('(^|[^\\d.,])(?:[2-4]|2[2-4])\\s+раз\\s+в\\s+день', 'u'), 'N раз в день (2–4)'],
                    [new RegExp('(^|[^\\d.,–-])(?:[2-4]|2[2-4])\\s+дней' + END, 'u'), 'N дней (2–4)'],
                    [new RegExp('(^|[^\\d.,–-])(?:[5-9]|1\\d|20)\\s+дня' + END, 'u'), 'N дня (5–20)'],
                    [new RegExp('(^|[^\\d.,–-])(?:1|21)\\s+(?:дня|дней)' + END, 'u'), 'N дня/дней (1/21)'],
                  ];
                  GRAMMAR.forEach(([re, label]) => {
                    const m = everything.match(re);
                    if (m) out.findings.push({ kind: 'grammar_number_word', where, sample: `${label}: «${everything.slice(Math.max(0, m.index - 30), m.index + 40).replace(/\n/g, ' ⏎ ')}»` });
                  });
                  stats.grammarOracle = (stats.grammarOracle || 0) + 1;
                  // large-volume warning parity: the screen and the chart text agree
                  const screenWarn = /Разовый объём велик/.test(txt($('res-po')));
                  const misWarn = /Предупреждение: разовый объём/.test(w.__copied || '');
                  if (screenWarn !== misWarn) out.findings.push({ kind: 'volume_warning_parity', where, sample: `screen ${screenWarn} vs MIS ${misWarn}` });
                  if (screenWarn) stats.volumeWarnOracle = (stats.volumeWarnOracle || 0) + 1;
                }
                stats.exports++;
              }
            }
          }
        }
      }
    }
    out.profiles[profile.name] = stats;
  }
  process.stdout.write(JSON.stringify(out));
}, 50);
