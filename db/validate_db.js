const fs = require('fs');
const path = require('path');

const dbPath = path.join(__dirname, 'antibio_db.json');
let raw = fs.readFileSync(dbPath, 'utf-8');
if (raw.charCodeAt(0) === 0xFEFF) raw = raw.slice(1); // strip BOM
const db = JSON.parse(raw);

const drugKeys = Object.keys(db.drugs_reference).filter(k => k !== '_note');
const errors = [];
const warnings = [];
let checkedRefs = 0;
let checkedRegimens = 0;

// 1. Check all drug_ref/combo_ref exist in drugs_reference
db.recommendations.forEach((rec, ri) => {
  (rec.scenarios || []).forEach((sc, si) => {
    (sc.lines || []).forEach((ln, li) => {
      (ln.drugs || []).forEach((drug, di) => {
        checkedRefs++;
        if (drug.drug_ref && !drugKeys.includes(drug.drug_ref)) {
          errors.push(`rec[${ri}] ${rec.id} > scenario[${si}] ${sc.id} > line[${li}] > drug[${di}]: drug_ref "${drug.drug_ref}" NOT FOUND in drugs_reference`);
        }
        if (drug.combo_ref) {
          drug.combo_ref.forEach((cr, cdi) => {
            if (!drugKeys.includes(cr)) {
              errors.push(`rec[${ri}] ${rec.id} > scenario[${si}] ${sc.id} > line[${li}] > drug[${di}] > combo_ref[${cdi}]: "${cr}" NOT FOUND in drugs_reference`);
            }
          });
        }
        // Check regimens
        (drug.regimens || []).forEach((reg, regi) => {
          checkedRegimens++;
          if (reg.duration_days == null) {
            warnings.push(`rec[${ri}] ${rec.id} > scenario[${si}] ${sc.id} > drug ${drug.drug_ref||drug.combo_ref} > regimen[${regi}]: missing duration_days`);
          }
          if (reg.freq_per_day == null) {
            errors.push(`rec[${ri}] ${rec.id} > scenario[${si}] ${sc.id} > drug ${drug.drug_ref||drug.combo_ref} > regimen[${regi}]: missing freq_per_day`);
          }
          // Check age_group consistency
          if (reg.age_group && sc.age_group && reg.age_group !== 'all' && reg.age_group !== sc.age_group) {
            // regimen age_group should be subset of scenario age_group
            // 'all' means all ages, so any regimen is fine
            // For specific groups, regimen should match scenario or be more specific
            const scGroups = sc.age_group === 'all' ? ['neonate','child','adult'] : [sc.age_group];
            if (!scGroups.includes(reg.age_group)) {
              warnings.push(`rec[${ri}] ${rec.id} > scenario[${si}] ${sc.id}: regimen age_group "${reg.age_group}" outside scenario age_group "${sc.age_group}"`);
            }
          }
        });
      });
    });
  });
});

console.log(`\n=== DB Validation Results ===`);
console.log(`Drugs in reference: ${drugKeys.length}`);
console.log(`Recommendations: ${db.recommendations.length}`);
console.log(`Drug references checked: ${checkedRefs}`);
console.log(`Regimens checked: ${checkedRegimens}`);

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
