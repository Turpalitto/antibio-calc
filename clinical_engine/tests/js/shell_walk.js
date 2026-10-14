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

const PROFILES = [
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
                // the two physician-facing exports must be as clean as the screen
                w.__copied = '';
                w.copyForMIS();
                const mis = w.__copied || '';
                if (!mis) out.findings.push({ kind: 'mis_empty', where, sample: txt($('toast')) });
                else if (BAD.test(mis)) out.findings.push({ kind: 'mis_bad_token', where, sample: mis.match(/.{0,40}(NaN|Infinity|undefined|\[object |null мг|null ЕД).{0,40}/)[0] });
                w.fillPrescriptionForm();
                const rx = txt($('prescription-form'));
                if (BAD.test(rx)) out.findings.push({ kind: 'rx_bad_token', where, sample: rx.match(/.{0,40}(NaN|Infinity|undefined|\[object |null мг|null ЕД).{0,40}/)[0] });
                if (!txt($('rx-drugs'))) out.findings.push({ kind: 'rx_empty', where, sample: txt($('rx-trust-line')).slice(0, 80) });
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
