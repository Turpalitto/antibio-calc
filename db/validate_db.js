'use strict';
/**
 * ANTIBIO calculator database validator.
 *
 * Blocking errors exit non-zero; `db/build_html.py` refuses to embed a database
 * that fails this check. Warnings are reported but do not fail the build.
 *
 * Usage
 *   node db/validate_db.js          human-readable report (default)
 *   node db/validate_db.js --json   machine-readable report on stdout
 *
 * Exit codes
 *   0  no errors (warnings may be present)
 *   1  one or more blocking errors
 *   2  the database could not be read/parsed, or its top-level shape is wrong
 */

const fs = require('fs');
const path = require('path');

const dbPath = path.join(__dirname, 'antibio_db.json');
const asJson = process.argv.includes('--json');

/** Keys the calculator shell cannot run without. */
const REQUIRED_KEYS = ['meta', 'drugs_reference', 'categories', 'recommendations'];

function fail(message, code = 2) {
  if (asJson) {
    process.stdout.write(JSON.stringify({ ok: false, fatal: message }, null, 2) + '\n');
  } else {
    console.error(`\n❌ ${message}`);
  }
  process.exit(code);
}

if (!fs.existsSync(dbPath)) {
  fail(`database not found: ${dbPath}`);
}

let raw = fs.readFileSync(dbPath, 'utf-8');
if (raw.charCodeAt(0) === 0xfeff) raw = raw.slice(1); // strip BOM
raw = raw.trim();

let db;
try {
  db = JSON.parse(raw);
} catch (error) {
  fail(`${dbPath} is not valid JSON: ${error.message}`);
}
if (db === null || typeof db !== 'object' || Array.isArray(db)) {
  fail(`${dbPath} must contain a JSON object`);
}
const missingKeys = REQUIRED_KEYS.filter((key) => !(key in db));
if (missingKeys.length > 0) {
  fail(`${dbPath} is missing required top-level key(s): ${missingKeys.join(', ')}`);
}
if (!Array.isArray(db.recommendations)) {
  fail(`${dbPath}: "recommendations" must be an array`);
}
if (db.drugs_reference === null || typeof db.drugs_reference !== 'object') {
  fail(`${dbPath}: "drugs_reference" must be an object`);
}

const drugKeys = Object.keys(db.drugs_reference).filter((k) => k !== '_note');
const drugKeySet = new Set(drugKeys);
const errors = [];
const warnings = [];
let checkedRefs = 0;
let checkedRegimens = 0;
let checkedScenarios = 0;

// 1. Every drug_ref / combo_ref must resolve in drugs_reference, and every
//    regimen must carry the dosing fields the calculator reads.
db.recommendations.forEach((rec, ri) => {
  (rec.scenarios || []).forEach((sc, si) => {
    checkedScenarios++;
    (sc.lines || []).forEach((ln, li) => {
      (ln.drugs || []).forEach((drug, di) => {
        checkedRefs++;
        if (drug.drug_ref && !drugKeySet.has(drug.drug_ref)) {
          errors.push(
            `rec[${ri}] ${rec.id} > scenario[${si}] ${sc.id} > line[${li}] > drug[${di}]: drug_ref "${drug.drug_ref}" NOT FOUND in drugs_reference`
          );
        }
        if (drug.combo_ref) {
          drug.combo_ref.forEach((cr, cdi) => {
            if (!drugKeySet.has(cr)) {
              errors.push(
                `rec[${ri}] ${rec.id} > scenario[${si}] ${sc.id} > line[${li}] > drug[${di}] > combo_ref[${cdi}]: "${cr}" NOT FOUND in drugs_reference`
              );
            }
          });
        }
        (drug.regimens || []).forEach((reg, regi) => {
          checkedRegimens++;
          const where = `rec[${ri}] ${rec.id} > scenario[${si}] ${sc.id} > drug ${drug.drug_ref || drug.combo_ref} > regimen[${regi}]`;
          if (reg.duration_days == null) {
            warnings.push(`${where}: missing duration_days`);
          }
          if (reg.freq_per_day == null) {
            errors.push(`${where}: missing freq_per_day`);
          }
          if (reg.age_group && sc.age_group && reg.age_group !== 'all' && reg.age_group !== sc.age_group) {
            // 'all' covers every age group, so a specific regimen age_group must
            // still be compatible with the scenario it is filed under.
            const scGroups = sc.age_group === 'all' ? ['neonate', 'child', 'adult'] : [sc.age_group];
            if (!scGroups.includes(reg.age_group)) {
              warnings.push(
                `rec[${ri}] ${rec.id} > scenario[${si}] ${sc.id}: regimen age_group "${reg.age_group}" outside scenario age_group "${sc.age_group}"`
              );
            }
          }
        });
      });
    });
  });
});

const summary = {
  database: path.relative(path.join(__dirname, '..'), dbPath),
  drugs_in_reference: drugKeys.length,
  recommendations: db.recommendations.length,
  scenarios_checked: checkedScenarios,
  drug_references_checked: checkedRefs,
  regimens_checked: checkedRegimens,
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
console.log(`Recommendations: ${summary.recommendations}`);
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
