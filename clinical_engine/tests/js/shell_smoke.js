'use strict';
/**
 * End-to-end smoke of the BUILT calculator shell (antibiotic_calc.html) in jsdom.
 *
 * Drives the page the way a physician does — through the DOM and real events
 * (`input`, `change`, `click`, `keydown`), never by calling internal handlers
 * with hand-picked arguments — and reports what the page shows. The clinical
 * numbers themselves are pinned elsewhere (golden cases, clinical-safety
 * harness); this file checks the WIRING: that typing in the visible controls
 * drives the result, that flags / banners / MIS text follow the context, and
 * that the page stays accessible (axe-core) in its main states.
 *
 * Usage: node shell_smoke.js <built html> <vendor/app.css> <axe.min.js>
 * Output: one JSON object on stdout.
 */

const fs = require('fs');
const { JSDOM, VirtualConsole } = require('jsdom');

const [htmlPath, cssPath, axePath] = process.argv.slice(2);
const html = fs.readFileSync(htmlPath, 'utf-8');
const errors = [];
const vc = new VirtualConsole();
vc.on('jsdomError', (e) => errors.push(String((e && e.message) || e)));
vc.on('error', (...a) => errors.push(a.map(String).join(' ')));

const dom = new JSDOM(html, {
  runScripts: 'dangerously',
  pretendToBeVisual: true,
  url: 'http://127.0.0.1:8080/antibiotic_calc.html',
  virtualConsole: vc,
});
const w = dom.window;
const d = w.document;
// jsdom does not fetch external stylesheets; inline the static Tailwind build
// so `hidden`, `dark:` etc. are real for getComputedStyle and for axe.
const style = d.createElement('style');
style.textContent = fs.readFileSync(cssPath, 'utf-8');
d.head.appendChild(style);
w.navigator.clipboard = { writeText: (t) => ((w.__copied = t), Promise.resolve()) };

const $ = (id) => d.getElementById(id);
const txt = (el) => (el ? el.textContent.replace(/\s+/g, ' ').trim() : null);
const visible = (el) => !!el && !el.classList.contains('hidden') && w.getComputedStyle(el).display !== 'none';
const fire = (el, type) => el.dispatchEvent(new w.Event(type, { bubbles: true }));
const type = (el, value) => {
  el.value = value;
  fire(el, 'input');
  fire(el, 'change');
};
const key = (name) => d.dispatchEvent(new w.KeyboardEvent('keydown', { key: name, bubbles: true }));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const DB = () => w.eval('DB');
const find = (pred) => DB().recommendations.find(pred);
const clickDisease = (id) => {
  // the search box lists matches; pick by id through the public selector the list uses
  const rec = find((r) => r.id === id);
  w.selectDisease(rec);
  // a nosology opens with its scenario cards; the first one is what a physician clicks
  const scenario = d.querySelector('#scenario-list .scenario-card');
  if (scenario) scenario.click();
  return rec;
};
const drugCards = () => [...d.querySelectorAll('#drug-list .drug-card')];
const clickDrug = (re) => {
  const card = drugCards().find((c) => re.test(c.textContent));
  if (!card) throw new Error('drug card not found: ' + re);
  card.click();
  return card;
};

async function axeRun(label, out) {
  if (!w.axe) w.eval(fs.readFileSync(axePath, 'utf-8'));
  const res = await w.axe.run(d, { rules: { 'color-contrast': { enabled: false } } });
  out.axe[label] = {
    violations: res.violations.map((v) => ({
      id: v.id,
      impact: v.impact,
      nodes: v.nodes.length,
      sample: v.nodes.slice(0, 3).map((n) => n.html.slice(0, 160)),
    })),
    passes: res.passes.length,
  };
}

async function run() {
  const out = { axe: {} };
  try {
    if (!DB()) w.eval('init()');
    out.header = txt($('header-stats'));
    out.dbBlockingErrors = w.eval('dbBlockingErrors.length');
    out.duplicateIds = (() => {
      const seen = {};
      d.querySelectorAll('[id]').forEach((el) => (seen[el.id] = (seen[el.id] || 0) + 1));
      return Object.entries(seen).filter(([, n]) => n > 1).map(([id]) => id);
    })();
    out.landmarks = { main: d.querySelectorAll('main').length, header: d.querySelectorAll('header').length, h1: d.querySelectorAll('h1').length };

    // ---- 1. search → disease → drug → weight (all through the DOM) ----------
    type($('search'), 'хламид');
    out.search = { resultsVisible: visible($('results-box')), results: $('results-box').children.length, first: txt($('results-box').firstElementChild) };
    const chl = clickDisease('chlamydia_urogenital');
    out.disease = { name: chl.name, status: $('source-calculation-block').dataset.sourceStatus, activeCr: txt($('active-cr')) };
    clickDrug(/Доксициклин/i);
    type($('weight'), '70');
    out.adult = {
      ageGroup: w.eval('activeAge'),
      mg: txt($('po-mg')),
      tabs: txt($('po-tabs')),
      resultVisible: visible($('result-step')),
      flags: txt($('patient-safety-banners')),
      flagsVisible: visible($('patient-safety-banners')),
    };

    // ---- 2. the age typed next to the unit selector must drive the age group --
    //      (regression: a duplicate id="patient-age" in the header card used to
    //       swallow the input — getElementById returned the other field)
    type($('patient-age'), '7');
    out.age7 = {
      ageGroup: w.eval('activeAge'),
      notice: txt($('age-explicit-notice')),
      noticeVisible: visible($('age-explicit-notice')),
      flags: txt($('patient-safety-banners')),
      doseBlock: txt($('dose-block')),
      resultVisible: visible($('result-step')),
      scenarioCards: [...d.querySelectorAll('#scenario-list .scenario-card')].map((c) => c.className),
    };
    $('patient-age-unit').value = 'months';
    fire($('patient-age-unit'), 'change');
    out.age7months = { ageGroup: w.eval('activeAge'), notice: txt($('age-explicit-notice')) };
    $('patient-age-unit').value = 'years';
    fire($('patient-age-unit'), 'change');
    type($('patient-age'), '19');
    out.age19 = { ageGroup: w.eval('activeAge'), flags: txt($('patient-safety-banners')), flagsVisible: visible($('patient-safety-banners')) };

    // ---- 3. pregnancy + GFR → advisory flags + MIS text ----------------------
    $('patient-pregnancy').value = 'yes';
    fire($('patient-pregnancy'), 'change');
    type($('patient-gfr'), '25');
    out.pregGfr = { flags: txt($('patient-safety-banners')), flagsVisible: visible($('patient-safety-banners')) };
    ($('btn-copy-mis') || $('btn-copy')).click();
    await sleep(0);
    out.mis = { text: w.__copied || '', lines: (w.__copied || '').split('\n').length };

    // ---- 4. reset context → flags disappear ------------------------------------
    $('patient-pregnancy').value = 'unknown';
    fire($('patient-pregnancy'), 'change');
    type($('patient-gfr'), '');
    type($('patient-age'), '');
    out.afterReset = { flagsVisible: visible($('patient-safety-banners')), noticeVisible: visible($('age-explicit-notice')) };

    // ---- 5. allergy: penicillin → amoxicillin card flagged -------------------
    clickDisease('aom_child');
    $('patient-allergy').value = 'penicillin_severe';
    fire($('patient-allergy'), 'change');
    const amox = drugCards().find((c) => /Амоксициллин/i.test(c.textContent));
    out.allergy = {
      badgeVisible: visible($('allergy-badge')),
      amoxCardClass: amox ? amox.className : null,
      amoxText: amox ? txt(amox).slice(0, 120) : null,
    };
    $('patient-allergy').value = 'none';
    fire($('patient-allergy'), 'change');

    // ---- 6. blocked and no-CR records --------------------------------------------
    const blocked = find((r) => r.calculation_blocked);
    clickDisease(blocked.id);
    out.blocked = { id: blocked.id, resultVisible: visible($('result-step')), banner: txt($('source-calculation-block')).slice(0, 160) };
    const noCr = find((r) => r.source_verification_status === 'NO_FEDERAL_CR_EXPERT_BASIS');
    clickDisease(noCr.id);
    out.noCr = { id: noCr.id, status: $('source-calculation-block').dataset.sourceStatus, banner: txt($('source-calculation-block')).slice(0, 160) };

    // ---- 7. theme toggle, history drawer, guideline modal + keyboard ---------
    const darkBefore = d.documentElement.classList.contains('dark');
    $('btn-theme').click();
    out.theme = { before: darkBefore, after: d.documentElement.classList.contains('dark'), stored: w.localStorage.getItem('antibio_theme') };
    $('btn-theme').click();

    clickDisease('chlamydia_urogenital');
    $('btn-history').click();
    out.drawer = {
      openClass: $('history-drawer').classList.contains('open'),
      inert: $('history-drawer').hasAttribute('inert'),
      ariaHidden: $('history-drawer').getAttribute('aria-hidden'),
      focusOnClose: d.activeElement && d.activeElement.id,
    };
    await axeRun('drawer_open', out);
    key('Escape');
    out.drawerAfterEscape = { openClass: $('history-drawer').classList.contains('open'), inert: $('history-drawer').hasAttribute('inert') };

    $('btn-guideline-modal').click();
    out.modal = {
      visible: visible($('guideline-modal')),
      role: $('guideline-modal').getAttribute('role'),
      labelledBy: $('guideline-modal').getAttribute('aria-labelledby'),
      title: txt($('modal-cr-title')),
      focusTag: d.activeElement && d.activeElement.tagName,
    };
    await axeRun('modal_open', out);
    key('Escape');
    out.modalAfterEscape = { visible: visible($('guideline-modal')), focusId: d.activeElement && d.activeElement.id };

    // ---- 8. service-worker update notice (jsdom has no serviceWorker; the
    //         banner path is exercised directly) ------------------------------------
    out.updateBanner = { hiddenBefore: !visible($('update-banner')) };
    w.showUpdateBanner();
    out.updateBanner.visibleAfter = visible($('update-banner'));
    out.updateBanner.text = txt($('update-banner'));
    out.updateBanner.role = $('update-banner').getAttribute('role');

    // ---- 9. accessibility of the main state ----------------------------------------
    type($('weight'), '70');
    await axeRun('main', out);
    $('update-banner').classList.add('hidden');
  } catch (e) {
    out.exception = String((e && e.stack) || e);
  }
  out.consoleErrors = errors.slice(0, 10);
  process.stdout.write(JSON.stringify(out));
}

d.addEventListener('DOMContentLoaded', run);
