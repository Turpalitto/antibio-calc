'use strict';
/**
 * ANTIBIO calculator database validator.
 *
 * Blocking errors exit non-zero; `db/build_html.py` refuses to embed a database
 * that fails this check. Warnings are reported but do not fail the build.
 *
 * Usage
 *   node db/validate_db.js               human-readable report (default)
 *   node db/validate_db.js --json        machine-readable report on stdout
 *   node db/validate_db.js --db <path>   validate another database file
 *
 * Exit codes
 *   0  no errors (warnings may be present)
 *   1  one or more blocking errors
 *   2  the database could not be read/parsed, or its top-level shape is wrong
 *
 * The module also exports `validateDatabase(db)` so tests can validate an
 * in-memory object without touching the filesystem.
 *
 * Rule classes (audit 2026-10-14, finding B-3):
 *   structural   — ids, names, mkb10, drug refs, routes, age groups, form types
 *   dose         — every computable regimen has a usable dose, plausible values,
 *                  units consistent with the drug (мг vs ЕД)
 *   frequency    — integer 1..6 per day (a parse defect such as "каждые 8 ч" -> 8
 *                  is the exact bug this rule was written for)
 *   provenance   — cr_id is a federal CR id or the record documents its basis
 *                  (cr_note); the source gate must have set calculation_blocked
 * A record that is calculation_blocked cannot reach the dose engine, so its
 * regimen-level defects are reported as warnings instead of blocking the build.
 */

const fs = require('fs');
const path = require('path');

/** Keys the calculator shell cannot run without. */
const REQUIRED_KEYS = ['meta', 'drugs_reference', 'categories', 'recommendations'];

const AGE_GROUPS = new Set(['neonate', 'child', 'adult', 'all']);
const ROUTES = new Set(['per_os', 'iv', 'im', 'topical', 'inhalation', 'intrathecal']);
const FORM_TYPES = new Set([
  'tablet', 'capsule', 'suspension', 'syrup', 'granules', 'powder_for_suspension',
  'powder_for_injection', 'solution_iv', 'solution_im', 'topical', 'drops',
]);
const KNOWN_STATUSES = new Set([
  'CALCULATOR_BOUND_VERIFIED',
  'SOURCE_SPEC_PENDING_CALCULATOR_BINDING',
  'CR_REFERENCE_CALCULATION',
  'NO_FEDERAL_CR_EXPERT_BASIS',
  'SOURCE_BASIS_MISSING',
  'SOURCE_SPEC_MISSING',
  'CURRENT_WEB_CONFIRMED_PDF_PENDING',
  'EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW',
]);
const DOSE_FIELDS = ['dose_mg_kg_day', 'dose_mg_kg_per_dose', 'dose_mg_day_fixed', 'single_dose_mg'];
/** ICD-10: "J18.9", "A41", ranges "B20-B24" / "B20-24". */
const MKB_RE = /^[A-Z]\d{2}(?:\.\d{1,2})?(?:-[A-Z]?\d{2}(?:\.\d{1,2})?)?$/;
const CR_ID_RE = /^\d+(?:_\d+)?$/;

/** Plausibility ceilings per unit. Anything above is a data defect, not a dose. */
const LIMITS = {
  'мг': { per_kg_day: 400, per_kg_dose: 150, fixed_day: 24000, single: 8000, max_daily: 24000, min_positive: 0.1 },
  'ЕД': { per_kg_day: 1000000, per_kg_dose: 500000, fixed_day: 60000000, single: 30000000, max_daily: 60000000, min_positive: 1000 },
};

function isFiniteNumber(value) {
  return typeof value === 'number' && Number.isFinite(value);
}

function drugUnit(drugsReference, key) {
  const ref = drugsReference[key];
  return ref && ref.dose_unit === 'ЕД' ? 'ЕД' : 'мг';
}

/**
 * Validate an in-memory database object.
 * @returns {{errors: string[], warnings: string[], stats: object}}
 */
function validateDatabase(db) {
  const errors = [];
  const warnings = [];
  const stats = { drugs_in_reference: 0, recommendations: 0, scenarios_checked: 0, drug_references_checked: 0, regimens_checked: 0, blocked_recommendations: 0 };

  if (db === null || typeof db !== 'object' || Array.isArray(db)) {
    errors.push('database must be a JSON object');
    return { errors, warnings, stats };
  }
  const missingKeys = REQUIRED_KEYS.filter((key) => !(key in db));
  if (missingKeys.length > 0) {
    errors.push(`missing required top-level key(s): ${missingKeys.join(', ')}`);
    return { errors, warnings, stats };
  }
  if (!Array.isArray(db.recommendations)) {
    errors.push('"recommendations" must be an array');
    return { errors, warnings, stats };
  }
  if (db.drugs_reference === null || typeof db.drugs_reference !== 'object' || Array.isArray(db.drugs_reference)) {
    errors.push('"drugs_reference" must be an object');
    return { errors, warnings, stats };
  }

  const drugsReference = db.drugs_reference;
  const drugKeys = Object.keys(drugsReference).filter((k) => k !== '_note');
  const drugKeySet = new Set(drugKeys);
  stats.drugs_in_reference = drugKeys.length;
  stats.recommendations = db.recommendations.length;

  // 0. drugs_reference shape: inn + forms with known form types.
  drugKeys.forEach((key) => {
    const ref = drugsReference[key];
    if (!ref || typeof ref !== 'object') {
      errors.push(`drugs_reference.${key}: must be an object`);
      return;
    }
    if (!ref.inn) errors.push(`drugs_reference.${key}: missing inn`);
    if (!Array.isArray(ref.forms)) {
      errors.push(`drugs_reference.${key}: forms must be an array`);
    } else {
      ref.forms.forEach((form, fi) => {
        if (!form || !form.form_type) errors.push(`drugs_reference.${key}.forms[${fi}]: missing form_type`);
        else if (!FORM_TYPES.has(form.form_type)) errors.push(`drugs_reference.${key}.forms[${fi}]: unknown form_type "${form.form_type}"`);
        if (form && form.concentration_mg_per_ml != null && !(isFiniteNumber(form.concentration_mg_per_ml) && form.concentration_mg_per_ml > 0)) {
          errors.push(`drugs_reference.${key}.forms[${fi}]: concentration_mg_per_ml must be a positive number`);
        }
      });
      if (ref.forms.length === 0) warnings.push(`drugs_reference.${key}: no dosage forms`);
    }
    if (ref.dose_unit != null && ref.dose_unit !== 'мг' && ref.dose_unit !== 'ЕД') {
      errors.push(`drugs_reference.${key}: dose_unit must be "мг" or "ЕД" (got "${ref.dose_unit}")`);
    }
  });

  const seenIds = new Set();
  db.recommendations.forEach((rec, ri) => {
    const recId = rec && rec.id ? rec.id : `#${ri}`;
    const where0 = `rec[${ri}] ${recId}`;
    if (!rec || typeof rec !== 'object') {
      errors.push(`${where0}: must be an object`);
      return;
    }
    // --- structural
    if (!rec.id) errors.push(`${where0}: missing id`);
    else if (seenIds.has(rec.id)) errors.push(`${where0}: duplicate id`);
    seenIds.add(rec.id);
    if (!rec.name) errors.push(`${where0}: missing name`);
    if (!Array.isArray(rec.mkb10) || rec.mkb10.length === 0) {
      errors.push(`${where0}: mkb10 must be a non-empty array`);
    } else {
      rec.mkb10.forEach((code) => {
        if (typeof code !== 'string' || !MKB_RE.test(code.trim())) {
          errors.push(`${where0}: mkb10 code "${code}" is not a single ICD-10 code/range (comma-joined strings must be split)`);
        }
      });
    }
    if (!Array.isArray(rec.scenarios) || rec.scenarios.length === 0) {
      errors.push(`${where0}: scenarios must be a non-empty array`);
    }

    // --- provenance / gate
    const blocked = rec.calculation_blocked === true;
    if (blocked) stats.blocked_recommendations++;
    if (typeof rec.calculation_blocked !== 'boolean') {
      errors.push(`${where0}: calculation_blocked must be an explicit boolean (run the source gate)`);
    }
    if (blocked && !rec.calculation_block_reason) {
      errors.push(`${where0}: calculation_blocked without calculation_block_reason`);
    }
    const status = rec.source_verification_status;
    if (status == null) {
      errors.push(`${where0}: missing source_verification_status (run the source gate)`);
    } else if (!KNOWN_STATUSES.has(status)) {
      errors.push(`${where0}: unknown source_verification_status "${status}"`);
    }
    const crId = rec.cr_id == null ? '' : String(rec.cr_id).trim();
    const hasFederalCr = CR_ID_RE.test(crId);
    const hasBasis = typeof rec.cr_note === 'string' && rec.cr_note.trim().length > 0;
    if (!hasFederalCr && !hasBasis && !blocked) {
      errors.push(`${where0}: computable record has neither a federal cr_id nor a documented basis (cr_note)`);
    }
    if (!hasFederalCr && status === 'CR_REFERENCE_CALCULATION') {
      errors.push(`${where0}: cr_id "${crId || '—'}" is not a federal CR id but status says CR_REFERENCE_CALCULATION`);
    }
    if (hasFederalCr && rec.cr_year == null) warnings.push(`${where0}: missing cr_year`);
    if (rec.cr_year != null && !(Number.isInteger(rec.cr_year) && rec.cr_year >= 1990 && rec.cr_year <= 2100)) {
      errors.push(`${where0}: cr_year "${rec.cr_year}" is not a plausible year`);
    }

    // Regimen-level defects of a blocked record are warnings: it cannot compute.
    const regimenIssues = blocked ? warnings : errors;
    const tag = blocked ? ' [blocked record]' : '';

    (rec.scenarios || []).forEach((sc, si) => {
      stats.scenarios_checked++;
      const scId = sc && sc.id ? sc.id : `#${si}`;
      const whereSc = `${where0} > scenario[${si}] ${scId}`;
      if (!sc || typeof sc !== 'object') { errors.push(`${whereSc}: must be an object`); return; }
      if (!sc.id) errors.push(`${whereSc}: missing id`);
      if (!sc.name) errors.push(`${whereSc}: missing name`);
      if (!AGE_GROUPS.has(sc.age_group)) errors.push(`${whereSc}: age_group "${sc.age_group}" must be one of ${[...AGE_GROUPS].join('/')}`);
      if (!Array.isArray(sc.lines) || sc.lines.length === 0) errors.push(`${whereSc}: lines must be a non-empty array`);

      (sc.lines || []).forEach((ln, li) => {
        const whereLn = `${whereSc} > line[${li}]`;
        if (!ln || typeof ln !== 'object') { errors.push(`${whereLn}: must be an object`); return; }
        if (ln.line_number == null) errors.push(`${whereLn}: missing line_number`);
        if (!Array.isArray(ln.drugs) || ln.drugs.length === 0) errors.push(`${whereLn}: drugs must be a non-empty array`);

        (ln.drugs || []).forEach((drug, di) => {
          stats.drug_references_checked++;
          const refs = drug.combo_ref ? drug.combo_ref : [drug.drug_ref];
          const label = drug.drug_ref || (drug.combo_ref ? drug.combo_ref.join('+') : '?');
          const whereDrug = `${whereLn} > drug[${di}] ${label}`;
          if (!drug.drug_ref && !drug.combo_ref) errors.push(`${whereDrug}: neither drug_ref nor combo_ref`);
          if (drug.drug_ref && !drugKeySet.has(drug.drug_ref)) {
            errors.push(`${whereDrug}: drug_ref "${drug.drug_ref}" NOT FOUND in drugs_reference`);
          }
          if (drug.combo_ref) {
            if (!Array.isArray(drug.combo_ref) || drug.combo_ref.length < 2) errors.push(`${whereDrug}: combo_ref must list at least two drugs`);
            (drug.combo_ref || []).forEach((cr, cdi) => {
              if (!drugKeySet.has(cr)) errors.push(`${whereDrug} > combo_ref[${cdi}]: "${cr}" NOT FOUND in drugs_reference`);
            });
          }
          // route: the shell derives its route tabs from this list; empty means
          // the regimen can never be selected (and injectable vs oral is unknown).
          if (!Array.isArray(drug.route) || drug.route.length === 0) {
            regimenIssues.push(`${whereDrug}: route is empty${tag}`);
          } else {
            drug.route.forEach((rt) => { if (!ROUTES.has(rt)) errors.push(`${whereDrug}: unknown route "${rt}"`); });
          }
          if (!Array.isArray(drug.regimens) || drug.regimens.length === 0) {
            regimenIssues.push(`${whereDrug}: no regimens${tag}`);
          }
          const unit = drugUnit(drugsReference, refs[0]);
          const limits = LIMITS[unit];
          const isTopical = Array.isArray(drug.route) && drug.route.length > 0 && drug.route.every((rt) => rt === 'topical');

          (drug.regimens || []).forEach((reg, regi) => {
            stats.regimens_checked++;
            const where = `${whereDrug} > regimen[${regi}]`;
            if (!reg || typeof reg !== 'object') { errors.push(`${where}: must be an object`); return; }
            if (reg.age_group != null && !AGE_GROUPS.has(reg.age_group)) {
              errors.push(`${where}: age_group "${reg.age_group}" must be one of ${[...AGE_GROUPS].join('/')}`);
            }
            if (reg.age_group && sc.age_group && reg.age_group !== 'all' && reg.age_group !== sc.age_group) {
              const scGroups = sc.age_group === 'all' ? ['neonate', 'child', 'adult'] : [sc.age_group];
              if (!scGroups.includes(reg.age_group)) {
                warnings.push(`${where}: regimen age_group "${reg.age_group}" outside scenario age_group "${sc.age_group}"`);
              }
            }
            // --- frequency
            if (reg.freq_per_day == null) {
              regimenIssues.push(`${where}: missing freq_per_day${tag}`);
            } else if (!Number.isInteger(reg.freq_per_day) || reg.freq_per_day < 1 || reg.freq_per_day > 6) {
              regimenIssues.push(`${where}: freq_per_day=${JSON.stringify(reg.freq_per_day)} is outside 1..6 per day (a "каждые N ч" parse defect?)${tag}`);
            }
            if (reg.duration_days == null) warnings.push(`${where}: missing duration_days`);
            if (reg.duration_days != null && !(isFiniteNumber(reg.duration_days) || /^\d+(-\d+)?$/.test(String(reg.duration_days).trim()))) {
              warnings.push(`${where}: duration_days "${reg.duration_days}" is not a number or "a-b" range`);
            }
            // --- dose presence / plausibility
            const present = DOSE_FIELDS.filter((f) => reg[f] != null);
            DOSE_FIELDS.concat(['max_daily_mg']).forEach((f) => {
              if (reg[f] != null && !(isFiniteNumber(reg[f]) && reg[f] > 0)) {
                regimenIssues.push(`${where}: ${f}=${JSON.stringify(reg[f])} must be a positive number${tag}`);
              }
            });
            if (present.length === 0 && !isTopical) {
              regimenIssues.push(`${where}: no dose field (${DOSE_FIELDS.join('/')}) — the shell would show a dose-less scheme${tag}`);
            }
            const checkLimit = (field, limit, name) => {
              const v = reg[field];
              if (!isFiniteNumber(v)) return;
              if (v > limit) regimenIssues.push(`${where}: ${field}=${v} exceeds the plausibility ceiling ${limit} ${unit} (${name})${tag}`);
              if (v > 0 && v < limits.min_positive) regimenIssues.push(`${where}: ${field}=${v} ${unit} is implausibly small for a ${unit}-dosed drug (unit mix-up?)${tag}`);
            };
            checkLimit('dose_mg_kg_day', limits.per_kg_day, 'per kg per day');
            checkLimit('dose_mg_kg_per_dose', limits.per_kg_dose, 'per kg per dose');
            checkLimit('dose_mg_day_fixed', limits.fixed_day, 'fixed per day');
            checkLimit('single_dose_mg', limits.single, 'single dose');
            checkLimit('max_daily_mg', limits.max_daily, 'daily ceiling');
            if (isFiniteNumber(reg.single_dose_mg) && isFiniteNumber(reg.max_daily_mg) && Number.isInteger(reg.freq_per_day)
                && reg.single_dose_mg * reg.freq_per_day > reg.max_daily_mg * 1.5) {
              warnings.push(`${where}: single_dose_mg × freq_per_day (${reg.single_dose_mg * reg.freq_per_day}) is far above max_daily_mg (${reg.max_daily_mg}) — the shell will cap it`);
            }
            if (isFiniteNumber(reg.dose_mg_kg_day) && reg.max_daily_mg == null && !blocked
                && (reg.age_group === 'child' || reg.age_group === 'all' || sc.age_group === 'all')) {
              warnings.push(`${where}: mg/kg regimen for children without max_daily_mg — no ceiling for heavy children (owner review)`);
            }
            if (Array.isArray(reg.dose_range_mg_kg_day)) {
              const [lo, hi] = reg.dose_range_mg_kg_day;
              if (reg.dose_range_mg_kg_day.length !== 2 || !(isFiniteNumber(lo) && isFiniteNumber(hi) && lo > 0 && hi >= lo)) {
                regimenIssues.push(`${where}: dose_range_mg_kg_day must be [low, high] positive numbers${tag}`);
              }
            }
          });
        });
      });
    });
  });

  return { errors, warnings, stats };
}

function readDatabase(dbPath) {
  if (!fs.existsSync(dbPath)) throw new Error(`database not found: ${dbPath}`);
  let raw = fs.readFileSync(dbPath, 'utf-8');
  if (raw.charCodeAt(0) === 0xfeff) raw = raw.slice(1); // strip BOM
  raw = raw.trim();
  let db;
  try {
    db = JSON.parse(raw);
  } catch (error) {
    throw new Error(`${dbPath} is not valid JSON: ${error.message}`);
  }
  return db;
}

function main(argv) {
  const asJson = argv.includes('--json');
  const dbArgIndex = argv.indexOf('--db');
  const dbPath = dbArgIndex >= 0 && argv[dbArgIndex + 1]
    ? path.resolve(argv[dbArgIndex + 1])
    : path.join(__dirname, 'antibio_db.json');

  const fail = (message, code = 2) => {
    if (asJson) {
      process.stdout.write(JSON.stringify({ ok: false, fatal: message }, null, 2) + '\n');
    } else {
      console.error(`\n❌ ${message}`);
    }
    process.exit(code);
  };

  let db;
  try {
    db = readDatabase(dbPath);
  } catch (error) {
    fail(error.message);
  }
  if (db === null || typeof db !== 'object' || Array.isArray(db)) {
    fail(`${dbPath} must contain a JSON object`);
  }
  const missingKeys = REQUIRED_KEYS.filter((key) => !(key in db));
  if (missingKeys.length > 0) {
    fail(`${dbPath} is missing required top-level key(s): ${missingKeys.join(', ')}`);
  }
  if (!Array.isArray(db.recommendations)) fail(`${dbPath}: "recommendations" must be an array`);
  if (db.drugs_reference === null || typeof db.drugs_reference !== 'object') fail(`${dbPath}: "drugs_reference" must be an object`);

  const { errors, warnings, stats } = validateDatabase(db);
  const summary = {
    database: path.relative(path.join(__dirname, '..'), dbPath),
    ...stats,
    errors: errors.length,
    warnings: warnings.length,
    ok: errors.length === 0,
    error_details: errors,
    warning_details: warnings,
  };

  if (asJson) {
    process.stdout.write(JSON.stringify(summary, null, 2) + '\n');
    process.exit(errors.length > 0 ? 1 : 0);
  }

  console.log('\n=== DB Validation Results ===');
  console.log(`Database: ${summary.database}`);
  console.log(`Drugs in reference: ${summary.drugs_in_reference}`);
  console.log(`Recommendations: ${summary.recommendations} (blocked: ${summary.blocked_recommendations})`);
  console.log(`Scenarios checked: ${summary.scenarios_checked}`);
  console.log(`Drug references checked: ${summary.drug_references_checked}`);
  console.log(`Regimens checked: ${summary.regimens_checked}`);

  if (errors.length === 0 && warnings.length === 0) {
    console.log('\n✅ ALL CHECKS PASSED');
    process.exit(0);
  }
  if (errors.length > 0) {
    console.log(`\n❌ ${errors.length} ERROR(S) (blocking):`);
    errors.forEach((e) => console.log(`  ERROR: ${e}`));
  }
  if (warnings.length > 0) {
    console.log(`\n⚠️  ${warnings.length} WARNING(S) (non-blocking):`);
    warnings.forEach((w) => console.log(`  WARN: ${w}`));
  }
  process.exit(errors.length > 0 ? 1 : 0);
}

module.exports = { validateDatabase, readDatabase, REQUIRED_KEYS, LIMITS };

if (require.main === module) {
  main(process.argv.slice(2));
}
