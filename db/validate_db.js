/* Structural + clinical-consistency gate for db/antibio_db.json.
 *
 * Exit 1 on any ERROR (the build must never embed an invalid DB), exit 0 with
 * warnings otherwise. Warnings are real findings — they are printed in full and
 * counted, never swallowed (ARCHITECTURAL_INVARIANTS.md INV-14: no silent
 * failure in value stages).
 *
 * Run: node db/validate_db.js
 */
const fs = require('fs');
const path = require('path');

const dbPath = path.join(__dirname, 'antibio_db.json');
let raw = fs.readFileSync(dbPath, 'utf-8');
if (raw.charCodeAt(0) === 0xFEFF) raw = raw.slice(1); // strip BOM
const db = JSON.parse(raw);

const drugKeys = Object.keys(db.drugs_reference).filter(k => k !== '_note');
const errors = [];
const warnings = [];
const counts = { refs: 0, regimens: 0, scenarios: 0, lines: 0, guidelineLinks: 0, blockedDiseases: 0 };

const ICD10 = /^[A-Z]\d{2}(\.\d{1,3})?$/;
const ROUTES = ['per_os', 'iv', 'im'];
// Declared in source but not calculable by the HTML calculator (it maps only
// per_os/iv/im to a form group). Flagged, not silently ignored.
const NON_CALCULABLE_ROUTES = ['topical'];
const AGE_GROUPS = ['neonate', 'child', 'adult', 'all'];
const LINK_METHODS = ['ICD10_EXACT', 'ICD10_BLOCK', 'TITLE_EXACT'];
const NUMERIC_RANGE = /^\d+(\.\d+)?\s*-\s*\d+(\.\d+)?$/;
const NUMERIC = /^\d+(\.\d+)?$/;
// Mirrors db/regimen_semantics.py — a duration the builder cannot classify must
// be visible, not silently rendered as a number of days.
const DURATION_KINDS = [
  'FIXED', 'RANGE', 'SINGLE_DOSE', 'AT_LEAST', 'AT_MOST', 'DOSE_COUNT',
  'INTERMITTENT', 'INFUSION_CONSTRAINT', 'CONDITION_DEPENDENT', 'LIFELONG',
  'NOT_FIXED', 'NOT_STATED', 'MISSING',
];

function refOf(drug) {
  return drug.drug_ref || (drug.combo_ref || []).join('+') || '<no ref>';
}

// 1. Database-level identity
const seenDiseaseIds = new Set();
(db.recommendations || []).forEach((rec, ri) => {
  const where = `rec[${ri}] ${rec.id || '<no id>'}`;

  if (!rec.id) errors.push(`${where}: missing id`);
  else if (seenDiseaseIds.has(rec.id)) errors.push(`${where}: duplicate disease id`);
  else seenDiseaseIds.add(rec.id);

  if (!rec.name) errors.push(`${where}: missing name`);

  // МКБ-10: every element must be ONE well-formed code. A comma-joined string
  // ("C83.5, C91.0") silently breaks every downstream ICD-10 join.
  if (!Array.isArray(rec.mkb10) || rec.mkb10.length === 0) {
    errors.push(`${where}: mkb10 must be a non-empty array`);
  } else {
    rec.mkb10.forEach(code => {
      if (typeof code !== 'string' || !ICD10.test(code.trim())) {
        errors.push(`${where}: mkb10 code "${code}" is not a single well-formed ICD-10 code`);
      }
    });
  }

  if (rec.calculation_blocked === true) counts.blockedDiseases++;
  if (rec.calculation_blocked !== undefined && typeof rec.calculation_blocked !== 'boolean') {
    errors.push(`${where}: calculation_blocked must be boolean when present`);
  }
  if (rec.calculation_blocked === true && !rec.calculation_block_reason) {
    warnings.push(`${where}: calculation_blocked without calculation_block_reason`);
  }
  if (rec.calculation_blocked === false && !rec.source_verification_status) {
    warnings.push(`${where}: calculation unblocked without source_verification_status`);
  }

  // 2. КР corpus crosswalk (navigation layer written by db/build_db.py)
  if (rec.guideline_links !== undefined) {
    if (!Array.isArray(rec.guideline_links)) {
      errors.push(`${where}: guideline_links must be an array`);
    } else {
      rec.guideline_links.forEach((link, li) => {
        counts.guidelineLinks++;
        const at = `${where} > guideline_link[${li}]`;
        if (!link.guideline_id) errors.push(`${at}: missing guideline_id`);
        if (!link.title) errors.push(`${at}: missing title`);
        if (!LINK_METHODS.includes(link.method)) errors.push(`${at}: unknown method "${link.method}"`);
        if (!Array.isArray(link.codes) || link.codes.length === 0) {
          warnings.push(`${at}: no matched ICD-10 codes (title-only link)`);
        } else {
          link.codes.forEach(code => {
            if (!ICD10.test(String(code).trim())) errors.push(`${at}: matched code "${code}" is malformed`);
          });
        }
      });
    }
  }

  // 3. Scenarios / lines / drugs / regimens
  const seenScenarioIds = new Set();
  (rec.scenarios || []).forEach((sc, si) => {
    counts.scenarios++;
    const scWhere = `${where} > scenario[${si}] ${sc.id || '<no id>'}`;
    if (!sc.id) errors.push(`${scWhere}: missing id`);
    else if (seenScenarioIds.has(sc.id)) errors.push(`${scWhere}: duplicate scenario id inside disease`);
    else seenScenarioIds.add(sc.id);
    if (!sc.name) errors.push(`${scWhere}: missing name`);
    if (sc.age_group && !AGE_GROUPS.includes(sc.age_group)) {
      errors.push(`${scWhere}: unknown age_group "${sc.age_group}"`);
    }

    (sc.lines || []).forEach((ln, li) => {
      counts.lines++;
      const lnWhere = `${scWhere} > line[${li}]`;
      if (ln.line_number == null) errors.push(`${lnWhere}: missing line_number`);
      else if (typeof ln.line_number !== 'number') errors.push(`${lnWhere}: line_number must be a number`);

      (ln.drugs || []).forEach((drug, di) => {
        counts.refs++;
        const dWhere = `${lnWhere} > drug[${di}] ${refOf(drug)}`;
        if (drug.drug_ref && !drugKeys.includes(drug.drug_ref)) {
          errors.push(`${dWhere}: drug_ref "${drug.drug_ref}" NOT FOUND in drugs_reference`);
        }
        if (drug.combo_ref) {
          if (!Array.isArray(drug.combo_ref) || drug.combo_ref.length < 2) {
            errors.push(`${dWhere}: combo_ref must list at least two components`);
          }
          (drug.combo_ref || []).forEach((cr, cdi) => {
            if (!drugKeys.includes(cr)) {
              errors.push(`${dWhere} > combo_ref[${cdi}]: "${cr}" NOT FOUND in drugs_reference`);
            }
          });
        }
        if (!drug.drug_ref && !drug.combo_ref) errors.push(`${dWhere}: needs drug_ref or combo_ref`);

        if (!Array.isArray(drug.route) || drug.route.length === 0) {
          warnings.push(`${dWhere}: no route declared`);
        } else {
          drug.route.forEach(route => {
            if (ROUTES.includes(route)) return;
            if (NON_CALCULABLE_ROUTES.includes(route)) {
              warnings.push(`${dWhere}: route "${route}" is declared but the calculator cannot render it`);
            } else {
              errors.push(`${dWhere}: unknown route "${route}"`);
            }
          });
        }

        if (!Array.isArray(drug.regimens) || drug.regimens.length === 0) {
          errors.push(`${dWhere}: no regimens`);
        }

        // The calculator filters regimens by the active age, and a scenario with
        // age_group "all" is reachable at every age. A drug that is offered in
        // such a scenario but has no regimen for one of those ages renders as
        // "no dose available" — a data gap the owner must close, not something
        // the UI should paper over with another age group's dose.
        const reachableAges = sc.age_group === 'all' ? AGE_GROUPS.filter(a => a !== 'all') : [sc.age_group];
        reachableAges.forEach(age => {
          if (!age) return;
          const eligible = (drug.regimens || []).filter(
            reg => reg.age_group === age || reg.age_group === 'all'
          );
          if ((drug.regimens || []).length > 0 && eligible.length === 0) {
            const msg = `${dWhere}: no regimen for age_group "${age}" reachable in this scenario`;
            if (rec.calculation_blocked === true) warnings.push(`${msg} — disease is calculation_blocked`);
            else errors.push(msg);
          }
        });

        const labelSeen = new Map();
        (drug.regimens || []).forEach((reg, regi) => {
          counts.regimens++;
          const rWhere = `${dWhere} > regimen[${regi}]`;

          if (reg.freq_per_day == null) errors.push(`${rWhere}: missing freq_per_day`);
          else if (typeof reg.freq_per_day !== 'number' || reg.freq_per_day <= 0) {
            errors.push(`${rWhere}: freq_per_day must be a positive number`);
          }

          if (reg.dose_mg_kg_day == null && reg.dose_mg_day_fixed == null && reg.single_dose_mg == null) {
            // An uncalculable regimen is only tolerable while the whole nozology
            // is closed by the source gate. Shipping one on an open disease
            // would render a blank/zero dose — the "silent underdose" class.
            const msg = `${rWhere}: no dose at all (dose_mg_kg_day / dose_mg_day_fixed / single_dose_mg)`;
            if (rec.calculation_blocked === true) warnings.push(`${msg} — disease is calculation_blocked`);
            else errors.push(msg);
          }

          // An empty string is a missing duration, not "free text" — it used to
          // fall through the null check and drown the real free-text signal.
          const rawDuration = typeof reg.duration_days === 'string' ? reg.duration_days.trim() : reg.duration_days;
          if (rawDuration == null || rawDuration === '') {
            warnings.push(`${rWhere}: missing duration_days`);
          } else if (typeof reg.duration_days === 'string') {
            // "Free text" only matters when db/regimen_semantics.py could not
            // classify it either. A string like «7-10 дней» is free text by
            // shape yet fully machine-readable, so warning on it is noise.
            const kind = (reg.duration_parsed || {}).kind;
            if (!NUMERIC.test(rawDuration) && !NUMERIC_RANGE.test(rawDuration)
                && (kind == null || kind === 'NOT_FIXED')) {
              warnings.push(`${rWhere}: duration_days "${rawDuration.slice(0, 48)}" is unclassifiable free text`);
            }
          } else if (typeof reg.duration_days !== 'number') {
            errors.push(`${rWhere}: duration_days must be a number or a numeric range string`);
          }

          // duration_parsed is derived at build time by db/regimen_semantics.py
          // and is what lets the UI tell a course length from an infusion rate.
          if (reg.duration_parsed == null) {
            warnings.push(`${rWhere}: no duration_parsed (run db/build_db.py without --skip-semantics)`);
          } else if (!DURATION_KINDS.includes(reg.duration_parsed.kind)) {
            errors.push(`${rWhere}: duration_parsed.kind "${reg.duration_parsed.kind}" is not a known duration kind`);
          }

          // regimen_label is the human-facing key of calculator_binding
          // (resolve_binding selects a regimen by it), so a missing label means
          // the regimen cannot be pinned, and a duplicate one means the pin is
          // ambiguous. Both are hard errors on an open disease.
          const label = reg.regimen_label;
          if (typeof label === 'string' && label.trim()) {
            labelSeen.set(label, (labelSeen.get(label) || 0) + 1);
          } else {
            const msg = `${rWhere}: no regimen_label (calculator_binding cannot pin this regimen)`;
            if (rec.calculation_blocked === true) warnings.push(`${msg} — disease is calculation_blocked`);
            else errors.push(msg);
          }

          if (reg.age_group && !AGE_GROUPS.includes(reg.age_group)) {
            errors.push(`${rWhere}: unknown age_group "${reg.age_group}"`);
          } else if (reg.age_group && sc.age_group && reg.age_group !== 'all' && sc.age_group !== 'all'
                     && reg.age_group !== sc.age_group) {
            warnings.push(`${where} > scenario[${si}] ${sc.id}: regimen age_group "${reg.age_group}" outside scenario age_group "${sc.age_group}"`);
          }

          // Dose self-consistency. The calculator computes single × freq as the
          // source of truth, so a stored daily total that disagrees by >5%
          // means one of the two was mis-transcribed (the "silent underdose"
          // class fixed in the July 2026 clinical audit).
          if (typeof reg.single_dose_mg === 'number' && typeof reg.freq_per_day === 'number') {
            const computed = reg.single_dose_mg * reg.freq_per_day;
            if (typeof reg.max_daily_mg === 'number' && computed > reg.max_daily_mg * 1.0001) {
              warnings.push(`${rWhere}: single_dose_mg × freq_per_day = ${computed} exceeds max_daily_mg ${reg.max_daily_mg} (calculator will cap)`);
            }
            if (typeof reg.dose_mg_day_fixed === 'number' && reg.dose_mg_day_fixed > 0
                && Math.abs(computed - reg.dose_mg_day_fixed) > 0.05 * reg.dose_mg_day_fixed + 1) {
              warnings.push(`${rWhere}: single×freq = ${computed} mg/day disagrees with dose_mg_day_fixed ${reg.dose_mg_day_fixed}`);
            }
          }
        });

        // resolve_binding() selects a regimen by regimen_label, so within one
        // drug entry the label must be unique — otherwise the pin is ambiguous.
        labelSeen.forEach((count, label) => {
          if (count > 1) {
            errors.push(`${dWhere}: regimen_label "${label}" repeats ${count}× — calculator_binding cannot disambiguate`);
          }
        });
      });
    });
  });
});

// 4. Crosswalk summary must be present once links are embedded
const xw = (db.meta || {}).guideline_crosswalk;
const anyLinks = (db.recommendations || []).some(r => Array.isArray(r.guideline_links));
if (anyLinks && !xw) warnings.push('meta.guideline_crosswalk missing while guideline_links are embedded');
if (xw && xw.purpose !== 'NAVIGATION_ONLY') {
  errors.push(`meta.guideline_crosswalk.purpose must be NAVIGATION_ONLY, got "${xw.purpose}"`);
}

console.log('\n=== DB Validation Results ===');
console.log(`Drugs in reference: ${drugKeys.length}`);
console.log(`Recommendations: ${(db.recommendations || []).length} (${counts.blockedDiseases} calculation-blocked)`);
console.log(`Scenarios / lines / drug refs / regimens: ${counts.scenarios} / ${counts.lines} / ${counts.refs} / ${counts.regimens}`);
console.log(`КР corpus links embedded: ${counts.guidelineLinks}${xw ? ` (content ${String(xw.content_sha256 || '').slice(0, 19)}…)` : ''}`);

if (errors.length === 0 && warnings.length === 0) {
  console.log('\n✅ ALL CHECKS PASSED');
  process.exit(0);
}

if (errors.length > 0) {
  console.log(`\n❌ ${errors.length} ERROR(S):`);
  errors.forEach(e => console.log(`  ERROR: ${e}`));
}
if (warnings.length > 0) {
  console.log(`\n⚠️  ${warnings.length} WARNING(S):`);
  warnings.forEach(w => console.log(`  WARN: ${w}`));
}

process.exit(errors.length > 0 ? 1 : 0);
