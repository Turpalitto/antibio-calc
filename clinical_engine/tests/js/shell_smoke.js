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
    out.search = { resultsVisible: visible($('results-box')), results: $('results-box').children.length, first: txt($('results-box').firstElementChild), status: txt($('search-status')), statusVisible: visible($('search-status')) };
    // recall: tokens + Russian endings + ICD + drug names, computable hits first
    out.searchRecall = {};
    for (const q of ['пневмония дети', 'h. pylori', 'амоксициллин', 'J18', 'отит взрослые', 'xyzzy', 'пневмания дети', 'тонзилит', 'амоксицилин', 'цистит', 'бронхит', 'ин', 'х']) {
      type($('search'), q);
      const items = [...$('results-box').children];
      out.searchRecall[q] = {
        n: items.length,
        status: txt($('search-status')), statusVisible: visible($('search-status')), boxVisible: visible($('results-box')),
        first: items.length ? txt(items[0]).slice(0, 60) : null,
        names: items.slice(0, 5).map((i) => txt(i).split('МКБ')[0]),
        blockedBeforeComputable: items.findIndex((i) => /расчёт закрыт/i.test(i.textContent)) >= 0
          && items.findIndex((i) => /расчёт закрыт/i.test(i.textContent)) < items.map((i) => !/расчёт закрыт/i.test(i.textContent)).lastIndexOf(true),
      };
    }
    const chl = clickDisease('chlamydia_urogenital');
    out.disease = { name: chl.name, status: $('source-calculation-block').dataset.sourceStatus, activeCr: txt($('active-cr')), searchStatusVisible: visible($('search-status')) };
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
    w.fillPrescriptionForm();
    out.rxPregGfr = { safetyHidden: $('rx-safety-line').hidden, safety: txt($('rx-safety-line')) };
    // course units + wording: MIS «суммарно N таб.» == Rp «D.t.d. N. N» == printed «D.t.d. N N»,
    // and the course is «N дней», never «<words> дней»
    w.__copied = '';
    w.copyLatinRecipe();
    await sleep(0);
    out.courseUnits = {
      misTotal: ((w.__copied && out.mis.text.match(/суммарно (\d+) таб/)) || [])[1] || null,
      rpDtd: ((w.__copied || '').match(/D\.t\.d\. N\. (\d+)/) || [])[1] || null,
      rxDtd: (txt($('rx-drugs')).match(/D\.t\.d\. N (\d+)/) || [])[1] || null,
      rpSigna: ((w.__copied || '').split('\n').find((l) => l.startsWith('S.:')) || ''),
      misCourse: (out.mis.text.split('\n').find((l) => l.startsWith('Курс лечения:')) || ''),
      rxCourse: txt($('rx-course')),
      screenCourse: txt($('po-dur')),
      perDose: txt($('po-tabs')),
    };
    // printed header: patient (raw input, text only), age, weight
    type($('patient-name'), 'Иванова А.<img src=x onerror=alert(1)>');
    w.fillPrescriptionForm();
    out.rxHeader = { text: txt($('rx-header-row')), html: $('rx-header-row').innerHTML.includes('<img') };
    type($('patient-name'), '');

    // ---- 3b. implausible GFR («1500» = a creatinine?) → patient-level caution on
    // screen and in the MIS text; GFR 0 (anuria) runs the renal rule, not silence
    type($('patient-gfr'), '1500');
    ($('btn-copy-mis') || $('btn-copy')).click();
    await sleep(0);
    out.gfrHigh = { flags: txt($('patient-safety-banners')), mis: (w.__copied || '').split('\n').filter((l) => l.includes('СКФ 1500')) };
    type($('patient-gfr'), '0');
    out.gfrZero = { flags: txt($('patient-safety-banners')) };  // doxycycline: «Не требуется» → nothing

    // ---- 4. reset context → flags disappear ------------------------------------
    $('patient-pregnancy').value = 'unknown';
    fire($('patient-pregnancy'), 'change');
    type($('patient-gfr'), '');
    type($('patient-age'), '');
    out.afterReset = { flagsVisible: visible($('patient-safety-banners')), noticeVisible: visible($('age-explicit-notice')) };

    // ---- 5. allergy: penicillin → amoxicillin card flagged -------------------
    type($('patient-age'), '7');
    clickDisease('aom_child');
    $('patient-allergy').value = 'penicillin_severe';
    fire($('patient-allergy'), 'change');
    const amox = drugCards().find((c) => /Амоксициллин/i.test(c.textContent));
    out.allergy = {
      badgeVisible: visible($('allergy-badge')),
      amoxCardClass: amox ? amox.className : null,
      amoxText: amox ? txt(amox).slice(0, 120) : null,
    };
    // selecting the contraindicated drug anyway: every export must say so
    amox.click();
    type($('weight'), '25');
    out.allergy.bannerVisible = visible($('allergy-alert-banner'));
    out.allergy.bannerTitle = txt($('allergy-alert-title'));
    w.__copied = '';
    w.copyForMIS();
    await sleep(0);
    out.allergy.mis = w.__copied || '';
    w.__copied = '';
    w.copyLatinRecipe();
    await sleep(0);
    out.allergy.rp = w.__copied || '';
    w.fillPrescriptionForm();
    out.allergy.rxSafety = { hidden: $('rx-safety-line').hidden, text: txt($('rx-safety-line')) };
    w.saveToHistory();
    w.loadHistory();
    out.allergy.history = txt($('history-list'));
    $('patient-allergy').value = 'none';
    fire($('patient-allergy'), 'change');
    w.fillPrescriptionForm();
    out.allergy.rxSafetyAfterReset = { hidden: $('rx-safety-line').hidden, text: txt($('rx-safety-line')) };
    out.allergy.toast = txt($('toast'));
    // changing the allergy status must keep the physician's place: the NON-first drug,
    // its non-default form chip and regimen (it used to jump to the first card)
    {
      const cards = [...d.querySelectorAll('#drug-list .drug-card')];
      const second = cards.find((c) => !c.classList.contains('active') && !/Амоксициллин/i.test(c.textContent)) || cards[cards.length - 1];
      second.click();
      const chips = [...d.querySelectorAll('#form-grid button[data-form-idx]')];
      if (chips.length > 1) chips[chips.length - 1].click();
      const state = () => w.eval('[getDrugRefs(activeDrug).join("+"), activeLine.line_number, currentRouteGroup, activeFormIdx, activeRegimenIdx].join("|")');
      const keep = { before: state(), firstCard: txt(cards[0]).slice(0, 30), chips: chips.length };
      type($('patient-allergy'), 'penicillin_severe');
      keep.afterSevere = state();
      keep.flaggedCards = [...d.querySelectorAll('#drug-list .drug-card')].filter((c) => /border-red-300/.test(c.className)).map((c) => txt(c).slice(0, 20));
      keep.activeCard = txt(d.querySelector('#drug-list .drug-card.active')).slice(0, 30);
      type($('patient-allergy'), 'none');
      keep.afterNone = state();
      out.allergy.keepSelection = keep;
    }
    type($('weight'), '');
    type($('patient-age'), '');
    // the explicit age is sticky (clearing it keeps «дети»): go back to adults via the chip
    d.querySelector('[data-age="adult"]').click();
    out.allergy.ageGroupAfterChip = w.eval('activeAge');

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

    // ---- 7a. keyboard: cards are focusable buttons, Enter/Space activate -------
    {
      const key = (el, k) => el.dispatchEvent(new w.KeyboardEvent('keydown', { key: k, bubbles: true, cancelable: true }));
      type($('search'), 'хламид');
      const hits = [...$('results-box').children];
      const hit = hits.find((c) => /Урогенитальный хламидиоз/i.test(c.textContent)) || hits[0];
      out.keyboard = { hits: hits.length, hitRole: hit.getAttribute('role'), hitTabindex: hit.getAttribute('tabindex') };
      key(hit, 'Enter');
      out.keyboard.diseaseAfterEnter = w.eval('activeDisease && activeDisease.id');
      const scCards = [...d.querySelectorAll('#scenario-list .scenario-card')];
      out.keyboard.scenarioRoles = scCards.map((c) => c.getAttribute('role') + '/' + c.getAttribute('tabindex'));
      const target = scCards.find((c) => !c.classList.contains('opacity-50')) || scCards[0];
      key(target, ' ');
      out.keyboard.scenarioAfterSpace = w.eval('activeScenario && activeScenario.id');
      out.keyboard.scenarioCardActive = target.classList.contains('active');
      const drugCard = d.querySelector('#drug-list .drug-card');
      out.keyboard.drugRole = drugCard && drugCard.getAttribute('role');
      key(drugCard, 'Enter');
      out.keyboard.drugAfterEnter = w.eval('activeDrug && (activeDrug.drug_ref || (activeDrug.combo_ref || []).join("+"))');
      out.keyboard.resultVisible = visible($('result-step'));
      // deep link: #disease/scenario restores the scenario, not only the disease
      const hash = w.location.hash;
      out.keyboard.hash = hash;
      w.eval('activeScenario = null; activeDisease = null;');
      w.eval('restoreFromHash()');
      out.keyboard.restoredScenario = w.eval('activeScenario && activeScenario.id');
      // leave the harness in the doxycycline/70 kg state the later steps expect
      clickDisease('chlamydia_urogenital');
      clickDrug(/Доксициклин/i);
      type($('weight'), '70');
    }

    // ---- 7c. switching to a gate-blocked nosology must drop the previous
    //          drug: the always-visible header "Печать" used to print the OLD
    //          regimen under the NEW (blocked) diagnosis ------------------------
    {
      w.print = () => { w.__printed = (w.__printed || 0) + 1; };
      $('rx-drugs').textContent = '';
      $('rx-trust-line').textContent = '';
      out.stale = { drugBefore: w.eval('activeDrug && activeDrug.drug_ref') };
      const blocked = find((r) => r.calculation_blocked && r.id !== 'chlamydia_urogenital');
      w.selectDisease(blocked);
      out.stale.blockedId = blocked.id;
      out.stale.gate = $('source-calculation-block').dataset.sourceStatus;
      out.stale.drugAfter = w.eval('activeDrug && activeDrug.drug_ref');
      out.stale.scenarioAfter = w.eval('activeScenario && activeScenario.id');
      out.stale.hash = w.location.hash;
      out.stale.staleCards = d.querySelectorAll('#scenario-list .scenario-card, #drug-list .drug-card').length;
      $('btn-print').click();
      out.stale.printed = w.__printed || 0;
      out.stale.rxDrugs = txt($('rx-drugs'));
      out.stale.toast = txt($('toast'));
      // back to the working state for the remaining steps
      clickDisease('chlamydia_urogenital');
      clickDrug(/Доксициклин/i);
      type($('weight'), '70');
    }

    // ---- 7d. combination: the partner drug's computed dose reaches the exports --
    {
      w.selectDisease(find((r) => r.id === 'listeriosis'));
      type($('weight'), '70');
      out.combo = { drug: w.eval('JSON.stringify(activeDrug.combo_ref)'), screen: txt($('combo-block')) };
      w.__copied = '';
      w.copyForMIS();
      await sleep(0);
      out.combo.mis = w.__copied || '';
      w.fillPrescriptionForm();
      out.combo.rx = txt($('rx-drugs'));
    }

    // ---- 7e. default form = the strength that fits the single dose -------------
    {
      w.selectDisease(find((r) => r.id === 'cap_adult'));
      type($('weight'), '70');
      const sc = [...d.querySelectorAll('#scenario-list .scenario-card')].find((c) => !c.classList.contains('opacity-50'));
      if (sc) sc.click();
      clickDrug(/^Амоксициллин(?!\s*\+)/i);
      const chips = [...d.querySelectorAll('#form-grid button')];
      out.defaultForm = {
        drug: w.eval('activeDrug && activeDrug.drug_ref'),
        chips: chips.map((c) => txt(c)),
        active: chips.filter((c) => c.classList.contains('active')).map((c) => txt(c)),
        dose: txt($('po-mg')),
        perDose: txt($('po-tabs')),
      };
      // amoxiclav 875 mg → the 875+125 tablet, one per dose
      const amc = [...d.querySelectorAll('#scenario-list .scenario-card')].find((c) => /коморбидный/i.test(c.textContent) && !c.classList.contains('opacity-50'));
      if (amc) { amc.click(); clickDrug(/Амоксициллин\s*\+|клавулан/i); }
      out.defaultForm.amoxiclav = {
        drug: w.eval('activeDrug && activeDrug.drug_ref'),
        active: [...d.querySelectorAll('#form-grid button.active')].map((c) => txt(c)),
        dose: txt($('po-mg')),
        perDose: txt($('po-tabs')),
      };
    }

    // ---- 7f. history «Открыть расчёт» re-opens the saved calculation ------------
    {
      // pick the NON-default 500+125 tablet, save, go somewhere else, restore
      const other = [...d.querySelectorAll('#form-grid button')].find((c) => /^500\+125/.test(txt(c)));
      if (other) other.click();
      const before = w.eval('[activeDisease.id, activeScenario.id, activeLine.line_number, activeDrug.drug_ref, currentRouteGroup, activeFormIdx, activeRegimenIdx].join("|")');
      // the rest of the patient context (GFR / pregnancy / allergy) is saved with the entry
      type($('patient-gfr'), '25');
      type($('patient-pregnancy'), 'no');
      type($('patient-allergy'), 'cephalosporin');
      out.historyRestore = { before, doseBefore: txt($('po-mg')) + ' ' + txt($('po-tabs')), flagsBefore: txt($('patient-safety-banners')) };
      w.saveToHistory();
      type($('patient-gfr'), '');
      type($('patient-pregnancy'), 'unknown');
      type($('patient-allergy'), 'none');
      type($('patient-age'), '6');
      type($('weight'), '20');
      clickDisease('cap_child');
      out.historyRestore.elsewhere = w.eval('activeDisease.id + "|" + activeAge');
      w.openHistory();
      const open = d.querySelector('#history-list button[data-action="restore"]');
      out.historyRestore.button = open ? txt(open) + ' / ' + (open.getAttribute('aria-describedby') || '').split(' ').map((id) => txt($(id))).join(', ') : null;
      if (open) open.click();
      out.historyRestore.after = w.eval('[activeDisease.id, activeScenario.id, activeLine.line_number, activeDrug.drug_ref, currentRouteGroup, activeFormIdx, activeRegimenIdx].join("|")');
      out.historyRestore.doseAfter = txt($('po-mg')) + ' ' + txt($('po-tabs'));
      out.historyRestore.age = $('patient-age').value + '|' + w.eval('activeAge') + '|' + $('weight').value;
      out.historyRestore.drawerOpen = $('history-drawer').classList.contains('open');
      out.historyRestore.toast = txt($('toast'));
      out.historyRestore.context = [$('patient-gfr').value, $('patient-pregnancy').value, $('patient-allergy').value].join('|');
      out.historyRestore.flagsAfter = txt($('patient-safety-banners'));
      out.historyRestore.allergyBadge = visible($('allergy-badge'));
      type($('patient-gfr'), '');
      type($('patient-pregnancy'), 'unknown');
      type($('patient-allergy'), 'none');
      clickDisease('chlamydia_urogenital');
      clickDrug(/Доксициклин/i);
      type($('weight'), '70');
    }

    // ---- 7b. route/form mismatch is fail-visible: doxycycline (tablets only)
    //          asked for iv → tabs fall back to all forms + amber notice ---------
    out.routeMismatch = { noteHiddenBefore: !visible($('route-mismatch-note')) };
    w.eval("activeDrug.route = ['iv']; renderForms();");
    out.routeMismatch.noteVisible = visible($('route-mismatch-note'));
    out.routeMismatch.noteText = txt($('route-mismatch-note'));
    out.routeMismatch.tabs = [...$('route-tabs').querySelectorAll('button')].map((b) => txt(b));
    w.eval("activeDrug.route = ['per_os']; renderForms();");
    out.routeMismatch.noteHiddenAfter = !visible($('route-mismatch-note'));

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

    // ---- 10. a hand-edited hash re-opens that nosology (hashchange) ----------------
    {
      const beforeHash = w.eval('activeDisease && activeDisease.id');
      w.location.hash = '#cap_adult/cap_adult_out_no_risk';
      await sleep(20);
      out.hashchange = { before: beforeHash, after: w.eval('activeDisease && activeDisease.id'), scenario: w.eval('activeScenario && activeScenario.id') };
      // the hash line is restored too, and a scenario that does not fit the current age
      // group waits (note under the list) until the patient data moves into its group
      const hs = () => w.eval('[activeAge, activeScenario && activeScenario.id, activeLine && activeLine.line_number, activeDrug && getDrugRefs(activeDrug)[0]].join("|")');
      w.location.hash = '#salmonellosis/salmonellosis_severe/L2';
      await sleep(20);
      out.hashchange.line = hs();
      type($('patient-age'), '7');
      type($('weight'), '25');
      w.location.hash = '#cap_adult/cap_adult_out_comorbid/L1';
      await sleep(20);
      out.hashchange.pendingState = hs();
      out.hashchange.pendingNote = visible($('scenario-hash-note')) ? txt($('scenario-hash-note')) : '';
      type($('patient-age'), '40');
      type($('weight'), '70');
      out.hashchange.resolvedState = hs();
      out.hashchange.resolvedNote = visible($('scenario-hash-note'));
      // a scenario picked by hand drops the pending link
      type($('patient-age'), '7');
      type($('weight'), '25');
      w.location.hash = '#cap_adult/cap_adult_out_comorbid/L1';
      await sleep(20);
      w.location.hash = '#cap_child/cap_child_out/L1';
      await sleep(20);
      out.hashchange.otherDiseaseClearsNote = !visible($('scenario-hash-note'));
      type($('patient-age'), '35');
      type($('weight'), '70');
    }

    // ---- 11. children open on the suspension whose dose volume is measurable ------
    {
      type($('patient-age-unit'), 'years');
      type($('patient-age'), '7');
      type($('weight'), '25');
      clickDisease('cap_child');
      const sc = [...d.querySelectorAll('#scenario-list .scenario-card')].find((c) => !c.classList.contains('opacity-50'));
      if (sc) sc.click();
      clickDrug(/^Амоксициллин(?!\s*\+)/i);
      const active = () => [...d.querySelectorAll('#form-grid button.active')].map((c) => txt(c));
      out.liquidDefault = { child25: { active: active(), dose: txt($('po-mg')), ml: txt($('po-ml')) + ' ' + txt($('po-unit')) } };
      w.__copied = '';
      w.copyForMIS();
      await sleep(0);
      out.liquidDefault.child25.mis = w.__copied || '';
      w.__copied = '';
      w.copyLatinRecipe();
      await sleep(0);
      out.liquidDefault.child25.rp = w.__copied || '';
      w.fillPrescriptionForm();
      out.liquidDefault.child25.rxDtd = [...d.querySelectorAll('#rx-drugs .rx-dtd')].map((e) => txt(e));
      // the same drug for a 7-kg infant: the low concentration is the measurable one
      type($('patient-age-unit'), 'months');
      type($('patient-age'), '6');
      type($('weight'), '7');
      clickDisease('cap_child');
      const sc2 = [...d.querySelectorAll('#scenario-list .scenario-card')].find((c) => !c.classList.contains('opacity-50'));
      if (sc2) sc2.click();
      clickDrug(/^Амоксициллин(?!\s*\+)/i);
      out.liquidDefault.infant7 = { active: active(), dose: txt($('po-mg')), ml: txt($('po-ml')) + ' ' + txt($('po-unit')) };
      // hand-picked low concentration → the MIS text carries the volume warning
      // (the chips are re-rendered when the weight changes the default — find it afterwards)
      type($('patient-age-unit'), 'years');
      type($('patient-age'), '7');
      type($('weight'), '25');
      const low = [...d.querySelectorAll('#form-grid button')].find((c) => /^125 мг\/5 мл/.test(txt(c)));
      if (low) low.click();
      w.__copied = '';
      w.copyForMIS();
      await sleep(0);
      out.liquidDefault.lowPicked = { active: active(), ml: txt($('po-ml')), mis: w.__copied || '' };
      // a 12-year-old at 39.9 kg: 1500 mg per dose = 30 ml of the strongest suspension →
      // opens on «500 мг» tablets (3 per dose); the 7-year-old above stays on the suspension
      // because no tablet divides 1125 mg into ≤ 3 units
      type($('patient-age'), '12');
      type($('weight'), '39.9');
      clickDisease('cap_child');
      const sc3 = [...d.querySelectorAll('#scenario-list .scenario-card')].find((c) => !c.classList.contains('opacity-50'));
      if (sc3) sc3.click();
      clickDrug(/^Амоксициллин(?!\s*\+)/i);
      out.liquidDefault.teen40 = { active: active(), dose: txt($('po-mg')), tabs: txt($('po-tabs')) };
      type($('patient-age-unit'), 'years');
      type($('patient-age'), '35');
      type($('weight'), '70');
    }
    // 12. weight / age plausibility: the notice appears while typing (drug or not),
    //     a weight impossible for the entered age blocks every output
    {
      const warn = () => ({ text: txt($('weight-warn')), hidden: !visible($('weight-warn')), blocking: $('weight-warn').dataset.blocking });
      type($('patient-age-unit'), 'days');
      type($('patient-age'), '10');
      type($('weight'), '25');
      w.__copied = '';
      w.copyForMIS();
      await sleep(0);
      out.plausibility = { neonate25: Object.assign(warn(), { mis: w.__copied || '', toast: txt($('toast')), block: txt($('dose-block')) }) };
      type($('weight'), '3.2');
      out.plausibility.neonate32 = warn();
      type($('patient-age'), '150');
      type($('patient-age-unit'), 'years');
      type($('weight'), '70');
      out.plausibility.age150 = { notice: txt($('age-explicit-notice')), block: txt($('dose-block')), po: visible($('res-po')) };
      type($('patient-age'), '35');
      out.plausibility.age35 = { notice: txt($('age-explicit-notice')), block: txt($('dose-block')), po: visible($('res-po')) };
      // no drug at all: pick nothing new, just an out-of-range weight on a fresh page state
      type($('weight'), '300');
      out.plausibility.w300 = warn();
      type($('weight'), '70');
    }
    // 13. keyboard search: Enter opens the top result, arrows walk the list, Escape clears
    {
      const key = (el, k) => el.dispatchEvent(new w.KeyboardEvent('keydown', { key: k, bubbles: true, cancelable: true }));
      type($('search'), 'тонзилит');
      const items = [...$('results-box').querySelectorAll('[role="button"]')];
      out.keyboardSearch = { n: items.length, first: items[0] ? txt(items[0]).split('МКБ')[0].trim() : null };
      key($('search'), 'ArrowDown');
      out.keyboardSearch.focusAfterDown = d.activeElement === items[0];
      key(items[0], 'ArrowDown');
      out.keyboardSearch.focusAfterDown2 = d.activeElement === items[1];
      key(items[1], 'ArrowUp');
      key(items[0], 'ArrowUp');
      out.keyboardSearch.backToInput = d.activeElement === $('search');
      key($('search'), 'Escape');
      out.keyboardSearch.clearedValue = $('search').value;
      out.keyboardSearch.boxHiddenAfterEscape = !visible($('results-box'));
      type($('search'), 'тонзилит');
      key($('search'), 'Enter');
      out.keyboardSearch.openedDisease = w.eval('activeDisease && activeDisease.name');
    }
    // 14. a validator-accepted «drops» form belongs with the topical route, never per os
    {
      clickDisease('cap_adult');
      const sc = [...d.querySelectorAll('#scenario-list .scenario-card')].find((c) => !c.classList.contains('opacity-50'));
      if (sc) sc.click();
      clickDrug(/^Амоксициллин(?!\s*\+)/i);
      const before = [...d.querySelectorAll('#route-tabs button')].map((b) => txt(b));
      w.eval("DB.drugs_reference[getDrugRefs(activeDrug)[0]].forms.push({form_type:'drops', concentration:'0.3 % капли ушные', notes:'тест'})");
      w.eval("activeDrug.route = (activeDrug.route || []).concat(['topical'])");
      w.renderForms();
      const tabs = [...d.querySelectorAll('#route-tabs button')];
      const topicalTab = tabs.find((b) => /наружно|местно|топик/i.test(txt(b)));
      if (topicalTab) topicalTab.click();
      out.dropsForm = {
        before,
        tabs: tabs.map((b) => txt(b)),
        topicalForms: [...d.querySelectorAll('#form-grid button')].map((b) => txt(b)),
        poHasDrops: (() => { const po = tabs.find((b) => /per os|внутрь/i.test(txt(b))); if (po) po.click(); return [...d.querySelectorAll('#form-grid button')].some((b) => /капли/.test(txt(b))); })(),
      };
      w.eval("DB.drugs_reference[getDrugRefs(activeDrug)[0]].forms.pop(); activeDrug.route = activeDrug.route.filter(r => r !== 'topical')");
      w.renderForms();
    }
    // 15. «Новый пациент» clears the whole patient context and the calculation in one action
    {
      type($('patient-age-unit'), 'years');
      type($('patient-age'), '78');
      type($('weight'), '58');
      type($('patient-gfr'), '25');
      type($('patient-pregnancy'), 'yes');
      type($('patient-allergy'), 'penicillin_severe');
      const filled = { po: visible($('res-po')) || visible($('res-inj')), allergyBanner: visible($('allergy-alert-banner')), group: w.eval('activeAge') };
      // the nosology «✕» alone used to leave the allergy banner on screen with no drug
      w.resetDisease();
      filled.allergyBannerAfterDiseaseReset = visible($('allergy-alert-banner'));
      clickDisease('cap_adult');
      clickDrug(/^Амоксициллин(?!\s*\+)/i);
      filled.allergyBannerAgain = visible($('allergy-alert-banner'));
      // GFR 0 (anuria) must run the renal rule («СКФ<30» for amoxicillin), not read as «empty»
      type($('patient-gfr'), '0');
      filled.gfrZeroFlags = txt($('patient-safety-banners'));
      $('new-patient').click();
      out.newPatient = {
        filled,
        weight: $('weight').value, age: $('patient-age').value, unit: $('patient-age-unit').value,
        gfr: $('patient-gfr').value, pregnancy: $('patient-pregnancy').value, allergy: $('patient-allergy').value,
        group: w.eval('activeAge'), userPickedAge: w.eval('userPickedAge'), patientAgeDays: w.eval('patientAgeDays'),
        activeChip: [...d.querySelectorAll('#age-group button.active')].map((b) => b.dataset.age),
        resultHidden: !visible($('result-step')), emptyState: visible($('empty-state')), disease: w.eval('activeDisease'),
        allergyBanner: visible($('allergy-alert-banner')), weightWarnHidden: !visible($('weight-warn')), toast: txt($('toast')),
        search: $('search').value,
      };
      type($('patient-age'), '35');
      type($('weight'), '70');
    }
    // 16. an age-group change keeps the physician's scenario / drug when the scenario
    //     fits both groups; a drug without a regimen for the new group shows the explicit
    //     age block instead of silently jumping to the first scenario's first drug
    {
      clickDisease('salmonellosis');
      const state = () => w.eval('[activeScenario && activeScenario.id, activeLine && activeLine.line_number, activeDrug && getDrugRefs(activeDrug).join("+"), currentRouteGroup, activeAge].join("|")');
      clickDrug(/^Ципрофлоксацин/i);
      const keep = { adult: state(), adultBlock: txt($('dose-block')) };
      type($('weight'), '25');
      type($('patient-age'), '7');
      keep.child = state();
      keep.childBlock = txt($('dose-block'));
      keep.childResultHidden = !visible($('res-po')) && !visible($('res-inj'));
      clickDrug(/^Цефтриаксон/i);
      keep.childCeftriaxone = state() + '|' + txt($('inj-mg') || $('po-mg'));
      type($('patient-age'), '40');
      type($('weight'), '70');
      keep.backToAdult = state() + '|' + txt($('inj-mg') || $('po-mg'));
      keep.backBlock = txt($('dose-block'));
      // a scenario that does NOT fit the new group still falls back to the first eligible one
      clickDisease('cap_adult');
      type($('patient-age'), '7');
      type($('weight'), '25');
      keep.adultOnlyScenarioAtChildAge = state() + '|' + txt($('dose-block')).slice(0, 60);
      // weight-inferred group change re-marks the scenario cards as well (sticky explicit
      // age disables inference — start from «Новый пациент»)
      $('new-patient').click();
      clickDisease('aom_child');
      type($('weight'), '25');
      keep.inferredChild = state() + '|' + [...d.querySelectorAll('#scenario-list .scenario-card')].map((c) => (c.classList.contains('opacity-50') ? 'dim' : 'ok')).join(',');
      type($('weight'), '70');
      keep.inferredAdult = state() + '|' + [...d.querySelectorAll('#scenario-list .scenario-card')].map((c) => (c.classList.contains('opacity-50') ? 'dim' : 'ok')).join(',') + '|' + txt($('dose-block')).slice(0, 40);
      out.ageKeepsSelection = keep;
      type($('patient-age'), '35');
      type($('weight'), '70');
    }
    // 17. the default form chip follows the weight (and the age / regimen) until the
    //     physician picks one: a 25-kg child typed AFTER the drug used to stay on
    //     «125 мг/5 мл» = 45 ml per dose, the same child typed first opened on «250 мг/5 мл»
    {
      const formState = () => w.eval('activeFormIdx') + '|' + txt(d.querySelector('#form-grid button.active')).slice(0, 12) + '|' + txt($('po-ml'));
      $('new-patient').click();
      type($('patient-age'), '7');
      clickDisease('cap_child');
      const def = { noWeight: formState() };
      type($('weight'), '25');
      def.weightAfterDrug = formState();
      $('new-patient').click();
      type($('patient-age'), '7');
      type($('weight'), '25');
      clickDisease('cap_child');
      def.weightBeforeDrug = formState();
      // an explicit chip survives weight changes; the next drug card starts from the default again
      d.querySelector('#form-grid button[data-form-idx="4"]').click();
      type($('weight'), '8');
      def.pickedStays = formState() + '|' + w.eval('userPickedForm');
      clickDrug(/^Амоксициллин \+ Клав/i);
      def.nextDrugPicked = w.eval('userPickedForm');
      out.formFollowsWeight = def;
      type($('patient-age'), '35');
      type($('weight'), '70');
    }
    // 18. no navigator.clipboard (plain-http intranet host): the legacy execCommand copy
    //     is used and the physician is always told the outcome (it used to throw silently)
    {
      clickDisease('cap_adult');
      const clip = w.navigator.clipboard;
      w.navigator.clipboard = undefined;
      let legacy = '';
      w.document.execCommand = (cmd) => { legacy = cmd === 'copy' ? (d.activeElement && d.activeElement.value) || '' : ''; return true; };
      w.copyForMIS();
      await sleep(0);
      const viaLegacy = { toast: txt($('toast')), copiedLines: legacy.split('\n').length, startsWith: legacy.slice(0, 20), leftover: d.querySelectorAll('textarea[aria-hidden="true"]').length };
      w.document.execCommand = () => false;
      w.copyLatinRecipe();
      await sleep(0);
      viaLegacy.failToast = txt($('toast'));
      delete w.document.execCommand;
      w.navigator.clipboard = clip;
      out.clipboardFallback = viaLegacy;
    }
    // 19. a browser that denies storage access (blocked site data): a second window where
    //     localStorage / sessionStorage getters throw SecurityError — init() must still
    //     restore the #hash deep link, the theme toggle must work, no uncaught errors
    {
      const errors2 = [];
      const vc2 = new VirtualConsole();
      vc2.on('jsdomError', (e) => errors2.push(String((e && e.message) || e)));
      vc2.on('error', (...a) => errors2.push(a.map(String).join(' ')));
      const dom2 = new JSDOM(html, {
        runScripts: 'dangerously',
        pretendToBeVisual: true,
        url: 'http://10.0.0.5:8080/antibiotic_calc.html#cap_adult/cap_adult_out_comorbid/L1',
        virtualConsole: vc2,
        beforeParse(window) {
          const deny = () => { throw new window.DOMException('Access is denied for this document.', 'SecurityError'); };
          Object.defineProperty(window, 'localStorage', { get: deny, configurable: true });
          Object.defineProperty(window, 'sessionStorage', { get: deny, configurable: true });
        },
      });
      await sleep(400);
      const w2 = dom2.window;
      const d2 = w2.document;
      const denied = { errors: errors2.slice(0, 5), dbLoaded: !!w2.eval('DB'), hashDisease: w2.eval('activeDisease && activeDisease.id'), hashScenario: w2.eval('activeScenario && activeScenario.id') };
      try { w2.toggleTheme(); denied.toggleTheme = d2.documentElement.classList.contains('dark') ? 'dark' : 'light'; } catch (e) { denied.toggleTheme = 'threw: ' + e.message; }
      try { w2.openHistory(); denied.historyOpens = !d2.getElementById('history-drawer').classList.contains('hidden'); } catch (e) { denied.historyOpens = 'threw: ' + e.message; }
      out.storageDenied = denied;
      dom2.window.close();
    }
  } catch (e) {
    out.exception = String((e && e.stack) || e);
  }
  out.consoleErrors = errors.slice(0, 10);
  process.stdout.write(JSON.stringify(out));
}

d.addEventListener('DOMContentLoaded', run);
