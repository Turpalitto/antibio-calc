#!/usr/bin/env node
/* Random-walk (model-based) fuzz of the built shell: a seeded sequence of the
 * actions a physician can take — weight / age / GFR / pregnancy / allergy inputs,
 * age chips, nosology / scenario / drug / route / form / regimen / vial clicks
 * (visible elements only), «Новый пациент», nosology «✕», search + pick, #hash
 * navigation, history save / restore, MIS / Rp copy, Ctrl+P (beforeprint), theme —
 * with state invariants checked after every step:
 *   no exception / console error; the active age chip = activeAge; scenario ∈
 *   disease, line ∈ scenario, drug ∈ line; form index in range and = the active
 *   chip; route tab = currentRouteGroup; an active scenario and drug card exist
 *   while a drug is selected; blocked ⇒ no result tiles, no export, no printed
 *   lines; computed ⇒ a result, non-empty MIS / Rp, printed lines; the regimen
 *   used fits activeAge; no NaN / undefined anywhere; location.hash names the
 *   active nosology; a blocked state never adds a history entry.
 *
 * usage: node shell_fuzz.js <built html> <app.css> [seed] [steps]  → JSON on stdout
 */
'use strict';
const fs = require('fs');
const { JSDOM, VirtualConsole } = require('jsdom');
const [htmlPath, cssPath, seedArg, stepsArg] = process.argv.slice(2);
const html = fs.readFileSync(htmlPath, 'utf8');
const css = fs.readFileSync(cssPath, 'utf8');
const seed = parseInt(seedArg || '1', 10), STEPS = parseInt(stepsArg || '800', 10);
let rs=seed||1; const rnd=()=>{ rs^=rs<<13; rs^=rs>>>17; rs^=rs<<5; return ((rs>>>0)%1e6)/1e6; };
const pick=a=>a[Math.floor(rnd()*a.length)];
const errors=[]; const vc=new VirtualConsole(); vc.on('jsdomError',e=>errors.push(String(e&&e.message||e).slice(0,200))); vc.on('error',(...a)=>errors.push(a.map(String).join(' ').slice(0,200)));
const dom=new JSDOM(html,{runScripts:'dangerously',url:'http://127.0.0.1:8080/antibiotic_calc.html',pretendToBeVisual:true,virtualConsole:vc});
const w=dom.window,d=w.document,$=id=>d.getElementById(id);
const st=d.createElement('style'); st.textContent=css; d.head.appendChild(st);
w.navigator.clipboard={writeText:t=>((w.__copied=t),Promise.resolve())};
w.print=()=>{};
const txt=el=>el?el.textContent.replace(/\s+/g,' ').trim():'';
const visible=el=>!!el&&!el.classList.contains('hidden')&&w.getComputedStyle(el).display!=='none';
const shown=el=>{ for(let n=el;n&&n.nodeType===1;n=n.parentElement){ if(n.classList.contains('hidden')||n.hidden||n.style.display==='none'||w.getComputedStyle(n).display==='none') return false; } return true; };
const q=sel=>[...d.querySelectorAll(sel)].filter(shown);
const type=(el,v)=>{el.value=v; el.dispatchEvent(new w.Event('input',{bubbles:true})); el.dispatchEvent(new w.Event('change',{bubbles:true}));};
const BAD=/NaN|Infinity|undefined|\[object |null мг|null ЕД/;
setTimeout(async()=>{
  const DB=w.eval('DB'); const computable=DB.recommendations.filter(r=>!r.calculation_blocked);
  const key=x=>x==='per_os'?'po':x;
  // scenarios where a route picked on drug A is offered by drug B in a NON-first position:
  // the only places where «the picked route follows the physician» is observable
  const pairScenarios=[];
  computable.forEach(r=>(r.scenarios||[]).forEach((sc,scIdx)=>{
    const drugs=[]; (sc.lines||[]).forEach((ln,lineIdx)=>(ln.drugs||[]).forEach((dr,drugIdx)=>drugs.push({lineIdx,drugIdx,routes:(dr.route||[]).map(key)})));
    drugs.forEach(a=>drugs.forEach(b=>{ if(a!==b&&a.routes.length>1) a.routes.forEach(x=>{ if(b.routes.indexOf(x)>0) pairScenarios.push({r,scIdx,a,b,x}); }); }));
  }));
  const findings=[]; const counts={};
  const actions={
    weight:()=>type($('weight'),pick(['','3.2','7','12.5','25','39.9','45','70','95','0.5','300','12,5'])),
    age:()=>{ type($('patient-age-unit'),pick(['years','months','days'])); type($('patient-age'),pick(['','0','5','10','18','3','7','12','35','70','150'])); },
    ageChip:()=>pick([...d.querySelectorAll('#age-group button')]).click(),
    gfr:()=>type($('patient-gfr'),pick(['','0','15','25','45','90','1500','-5'])),
    preg:()=>type($('patient-pregnancy'),pick(['unknown','no','yes'])),
    allergy:()=>type($('patient-allergy'),pick(['none','penicillin_mild','penicillin_severe','cephalosporin'])),
    disease:()=>w.selectDisease(pick(rnd()<0.85?computable:DB.recommendations)),
    scenario:()=>{ const c=q('#scenario-list .scenario-card'); if(c.length) pick(c).click(); },
    drug:()=>{ const c=q('#drug-list .drug-card'); if(c.length) pick(c).click(); },
    route:()=>{ const c=q('#route-tabs button'); if(c.length) pick(c).click(); },
    // sharper probe for the route preference: pick a tab that is NOT the first one, then
    // switch to another drug card of the scenario (a plain random walk hits this ~1/6000)
    routeThenDrug:()=>{
      w.__pk=undefined;
      const cardOf=(lineIdx,drugIdx)=>q('#drug-list .drug-card').find(c=>+c.dataset.lineIdx===lineIdx&&+c.dataset.drugIdx===drugIdx);
      const lbl={po:'per os',im:'в/м',iv:'в/в',topical:'местно'};
      if(pairScenarios.length&&rnd()<0.6){
        // steer to a scenario where the preference is observable, pick the route on A, open B
        const pr=pick(pairScenarios); w.selectDisease(pr.r); const cards=q('#scenario-list .scenario-card'); if(cards[pr.scIdx]) cards[pr.scIdx].click();
        const a=cardOf(pr.a.lineIdx,pr.a.drugIdx); if(a) a.click();
        const tab=q('#route-tabs button').find(b=>txt(b)===lbl[pr.x]); if(tab) tab.click();
        w.__pk=w.eval('pickedRouteGroup');
        const b=cardOf(pr.b.lineIdx,pr.b.drugIdx); if(b) b.click();
        return;
      }
      const t=q('#route-tabs button'); if(t.length>1) pick(t.slice(1)).click();
      w.__pk=w.eval('pickedRouteGroup');
      const c=q('#drug-list .drug-card').filter(x=>!x.classList.contains('active')); if(c.length) pick(c).click();
    },
    form:()=>{ const c=q('#form-grid button[data-form-idx]'); if(c.length) pick(c).click(); },
    regimen:()=>{ const c=q('#regimen-list button'); if(c.length) pick(c).click(); },
    vial:()=>{ const c=q('#vial-list button'); if(c.length) pick(c).click(); },
    newPatient:()=>$('new-patient').click(),
    resetDisease:()=>w.resetDisease(),
    search:()=>{ type($('search'),pick(['пневмония','цистит','отит','J18','амоксициллин','сепсис','ин'])); const hits=[...d.querySelectorAll('#results-box > div[role=button]')]; if(hits.length) pick(hits).click(); },
    hash:()=>{ const r=pick(computable); const sc=pick(r.scenarios||[]); w.location.hash='#'+r.id+(sc?'/'+sc.id+(rnd()<0.5?'/L'+pick(sc.lines).line_number:''):''); },
    history:()=>{
      const n0=w.eval('historyEntries.length'); const blocked=w.eval('activeDrug ? !!calculationBlockReason(parseFloat($("weight").value)) : true');
      w.saveToHistory(); const n1=w.eval('historyEntries.length'); w.__historyDelta={blocked, added:n1-n0}; w.__restored=null;
      const btns=[...d.querySelectorAll('#history-list [data-action="restore"]')];
      if(btns.length&&rnd()<0.7){
        const i=Math.floor(rnd()*btns.length);
        const entry=w.eval('JSON.stringify(historyEntries['+i+'])'); const e=JSON.parse(entry);
        const ok=w.restoreHistoryEntry(e);
        w.__restored={ok, ref:e.ref, weight:e.weight, ageGroup:e.ageGroup, toast:txt($('toast'))};
      }
    },
    copy:()=>{ w.__copied=null; w.copyForMIS(); w.__mis=w.__copied; w.__copied=null; w.copyLatinRecipe(); w.__rp=w.__copied; },
    print:()=>w.dispatchEvent(new w.Event('beforeprint')),
    theme:()=>w.toggleTheme(),
  };
  const names=Object.keys(actions);
  const stateStr=()=>w.eval('[activeAge, activeDisease&&activeDisease.id, activeScenario&&activeScenario.id, activeLine&&activeLine.line_number, activeDrug&&getDrugRefs(activeDrug).join("+"), currentRouteGroup, activeFormIdx, activeRegimenIdx].join("|")');
  for(let i=0;i<STEPS;i++){
    const name=pick(names); counts[name]=(counts[name]||0)+1;
    const before=stateStr();
    const beforePicked=w.eval('pickedRouteGroup'), beforeSc=w.eval('activeScenario');
    try{ actions[name](); await new Promise(r=>setTimeout(r,0)); }catch(e){ findings.push({step:i,action:name,kind:'exception',msg:String(e&&e.stack||e).slice(0,300),before}); continue; }
    if(errors.length){ findings.push({step:i,action:name,kind:'console',msg:errors.splice(0).join(' || ').slice(0,300),before}); }
    // invariants
    const S=w.eval('({age:activeAge, dis:activeDisease, sc:activeScenario, ln:activeLine, dr:activeDrug, form:activeFormIdx, reg:activeRegimenIdx, route:currentRouteGroup, blocked: activeDrug ? calculationBlockReason(parseFloat($("weight").value)) : null, regimen: activeDrug ? getActiveRegimen() : null})');
    const where=`#${i} ${name} | ${before} → ${stateStr()}`;
    const push=(kind,msg)=>findings.push({step:i,action:name,kind,msg:String(msg).slice(0,300),where});
    const chipAge=d.querySelector('#age-group button.active'); if(chipAge&&chipAge.dataset.age!==S.age) push('age_chip_mismatch',`chip ${chipAge.dataset.age} vs ${S.age}`);
    if(S.dis&&w.location.hash&&!w.location.hash.startsWith('#'+S.dis.id)) push('hash_mismatch',`${w.location.hash.slice(0,60)} vs ${S.dis.id}`);
    if(!S.dis&&w.location.hash) push('hash_without_disease',w.location.hash.slice(0,60));
    if(name==='history'&&w.__historyDelta){ if(w.__historyDelta.blocked&&w.__historyDelta.added>0) push('history_saved_while_blocked',''); w.__historyDelta=null; }
    if(name==='history'&&w.__restored){
      // «Открыть расчёт» must re-open exactly what was saved (same DB, same age group)
      const r=w.__restored, ref=r.ref;
      const now=w.eval('({dis:activeDisease&&activeDisease.id, sc:activeScenario&&activeScenario.id, ln:activeLine&&activeLine.line_number, dr:activeDrug&&getDrugRefs(activeDrug).join("+"), route:currentRouteGroup, form:activeFormIdx, reg:activeRegimenIdx, age:activeAge, gfr:$("patient-gfr").value, preg:$("patient-pregnancy").value, all:$("patient-allergy").value, weight:parseFloat($("weight").value)})');
      const diffs=[];
      if(!r.ok) diffs.push('restore returned false: '+r.toast);
      [['dis','disease'],['sc','scenario'],['ln','line'],['dr','drug'],['route','route'],['form','formIdx'],['reg','regimenIdx'],['gfr','gfr'],['preg','pregnancy'],['all','allergy']].forEach(([k,rk])=>{ if(String(now[k])!==String(ref[rk])) diffs.push(`${rk}: ${ref[rk]} → ${now[k]}`); });
      if(r.ageGroup&&now.age!==r.ageGroup) diffs.push(`ageGroup: ${r.ageGroup} → ${now.age}`);
      if(r.weight>0&&now.weight!==r.weight) diffs.push(`weight: ${r.weight} → ${now.weight}`);
      if(diffs.length) push('history_restore_mismatch',diffs.join('; '));
      w.__restored=null;
    }
    if(S.sc&&S.dis&&!(S.dis.scenarios||[]).includes(S.sc)) push('scenario_not_in_disease','');
    if(S.ln&&S.sc&&!(S.sc.lines||[]).includes(S.ln)) push('line_not_in_scenario','');
    if(S.dr&&S.ln&&!(S.ln.drugs||[]).includes(S.dr)) push('drug_not_in_line','');
    if(S.dr&&!S.sc) push('drug_without_scenario','');
    if(S.dr){
      const mainRef=DB.drugs_reference[w.eval('getDrugRefs(activeDrug)[0]')];
      if(!(mainRef&&mainRef.forms&&S.form>=0&&S.form<mainRef.forms.length)) push('form_idx_out_of_range',`${S.form}`);
      const activeChip=d.querySelector('#form-grid button.active'); if(activeChip&&parseInt(activeChip.dataset.formIdx)!==S.form) push('form_chip_mismatch',`chip ${activeChip.dataset.formIdx} vs ${S.form}`);
      const activeTab=d.querySelector('#route-tabs button.active'); const lbl={po:'per os',im:'в/м',iv:'в/в',topical:'местно'}; if(activeTab&&txt(activeTab)!==lbl[S.route]) push('route_tab_mismatch',`${txt(activeTab)} vs ${S.route}`);
      // route tabs keep the order of the scenario route list; a drug card opens on the
      // route the physician picked when it offers it, otherwise on its first route
      const tabKeys=[...d.querySelectorAll('#route-tabs button')].map(b=>Object.keys(lbl).find(k=>lbl[k]===txt(b)));
      const intended=(S.dr.route||[]).map(x=>x==='per_os'?'po':x).filter(k=>tabKeys.includes(k));
      if(intended.length&&tabKeys.slice(0,intended.length).join()!==intended.join()) push('route_tab_order',`${tabKeys} vs ${intended}`);
      const picked=w.eval('pickedRouteGroup');
      if(name==='route'&&picked!==S.route) push('route_pick_not_recorded',`${picked} vs ${S.route}`);
      if((name==='drug'||name==='routeThenDrug')&&S.sc===beforeSc&&tabKeys.length){ const pk=name==='routeThenDrug'?w.__pk:beforePicked; const exp=(pk&&tabKeys.includes(pk))?pk:tabKeys[0]; if(S.route!==exp) push('route_default_mismatch',`${S.route} vs ${exp} (picked ${pk})`); }
      if(name==='scenario'&&S.sc!==beforeSc&&picked!==null) push('route_pick_survives_scenario_change',`${picked}`);
      const sel=d.querySelector('#scenario-list .scenario-card.active'); if(!sel) push('no_active_scenario_card','');
      const selDrug=d.querySelector('#drug-list .drug-card.active'); if(!selDrug) push('no_active_drug_card','');
      const blockVis=visible($('dose-block')), resVis=visible($('res-po'))||visible($('res-inj'));
      if(S.blocked&&resVis) push('result_visible_while_blocked',S.blocked.slice(0,80));
      if(!S.blocked&&S.regimen&&!resVis&&!blockVis) push('no_result_no_block','');
      if(S.regimen&&S.regimen.age_group&&S.regimen.age_group!=='all'&&S.regimen.age_group!==S.age) push('regimen_age_mismatch',`${S.regimen.age_group} vs ${S.age}`);
      const all=txt($('result-step'))+' '+txt($('dose-block')); if(BAD.test(all)) push('bad_token',all.match(/.{0,30}(NaN|Infinity|undefined|\[object |null мг|null ЕД).{0,30}/)[0]);
      if(name==='copy'){
        if(S.blocked&&(w.__mis||w.__rp)) push('export_while_blocked','');
        if(!S.blocked&&w.__mis){
          // the chart text names the drug on screen (INN) and the diagnosis
          const inn=(DB.drugs_reference[w.eval('getDrugRefs(activeDrug)[0]')]||{}).inn||'';
          if(inn&&!w.__mis.includes(inn)) push('mis_names_other_drug',`${inn} not in «${w.__mis.slice(0,100)}»`);
          if(S.dis&&!w.__mis.includes(S.dis.name)) push('mis_names_other_diagnosis',`${S.dis.name} not in «${w.__mis.slice(0,100)}»`);
        }
        if(!S.blocked&&S.regimen&&resVis&&!(w.__mis&&w.__rp)) push('export_empty_while_computed',`mis ${!!w.__mis} rp ${!!w.__rp} toast ${txt($('toast'))}`);
        if(BAD.test((w.__mis||'')+(w.__rp||''))) push('export_bad_token','');
      }
      if(name==='print'){
        const rxd=txt($('rx-drugs')); const trust=txt($('rx-trust-line'));
        if(S.blocked&&rxd) push('print_drugs_while_blocked',rxd.slice(0,60));
        if(!S.blocked&&rxd){
          const key=w.eval('getDrugRefs(activeDrug)[0]'); const inn=(DB.drugs_reference[key]||{}).inn||'';
          const latin=w.eval('(typeof LATIN_INN !== "undefined" && LATIN_INN['+JSON.stringify(key)+']) || ""');
          if(!(latin&&rxd.includes(latin))&&!(inn&&rxd.includes(inn))) push('print_names_other_drug',`${latin||inn} not in «${rxd.slice(0,80)}»`);
          const wv=parseFloat($('weight').value); if(wv>0&&txt($('rx-weight'))!==String(wv)+' кг'&&!txt($('rx-weight')).startsWith(String(wv))) push('print_weight_mismatch',`${wv} vs ${txt($('rx-weight'))}`);
        }
        if(!S.blocked&&S.regimen&&resVis&&!rxd) push('print_empty_while_computed',trust.slice(0,80));
        if(BAD.test(txt($('prescription-form')))) push('print_bad_token','');
      }
    } else {
      if(name==='print'&&txt($('rx-drugs'))) push('print_drugs_without_drug',txt($('rx-drugs')).slice(0,60));
      if(name==='copy'&&(w.__mis||w.__rp)) push('export_without_drug','');
    }
  }
  console.log(JSON.stringify({seed,steps:STEPS,findings:findings.slice(0,40),nFindings:findings.length,kinds:findings.reduce((a,f)=>(a[f.kind]=(a[f.kind]||0)+1,a),{}),counts},null,1));
},300);
