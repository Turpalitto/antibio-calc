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
// «1 050 000 ЕД» / «1,5 млн ЕД» / «500 мг» → number
const num=t=>{ const mul=/млн/.test(t)?1e6:(/тыс/.test(t)?1e3:1); return parseFloat(String(t).replace(/[\s\u00a0]/g,'').replace(/мг|ЕД|млн|тыс/g,'').replace(',','.'))*mul; };
const type=(el,v)=>{el.value=v; el.dispatchEvent(new w.Event('input',{bubbles:true})); el.dispatchEvent(new w.Event('change',{bubbles:true}));};
const BAD=/NaN|Infinity|undefined|\[object |null мг|null ЕД/;
setTimeout(async()=>{
  const DB=w.eval('DB'); const computable=DB.recommendations.filter(r=>!r.calculation_blocked);
  const childRecs=computable.filter(r=>(r.scenarios||[]).some(sc=>(sc.lines||[]).some(l=>(l.drugs||[]).some(dr=>(dr.regimens||[]).some(reg=>reg.age_group==='child')))));
  // child mg/kg regimens whose daily ceiling is reached below 39 kg (the cap row oracle)
  const cappedRecs=computable.filter(r=>(r.scenarios||[]).some(sc=>(sc.lines||[]).some(l=>(l.drugs||[]).some(dr=>(dr.regimens||[]).some(reg=>reg.age_group==='child'&&reg.dose_mg_kg_day&&reg.max_daily_mg&&reg.max_daily_mg/reg.dose_mg_kg_day<39)))));
  const key=x=>x==='per_os'?'po':x;
  // scenarios where a route picked on drug A is offered by drug B in a NON-first position:
  // the only places where «the picked route follows the physician» is observable
  const pairScenarios=[];
  computable.forEach(r=>(r.scenarios||[]).forEach((sc,scIdx)=>{
    const drugs=[]; (sc.lines||[]).forEach((ln,lineIdx)=>(ln.drugs||[]).forEach((dr,drugIdx)=>drugs.push({lineIdx,drugIdx,routes:(dr.route||[]).map(key)})));
    drugs.forEach(a=>drugs.forEach(b=>{ if(a!==b&&a.routes.length>1) a.routes.forEach(x=>{ if(b.routes.indexOf(x)>0) pairScenarios.push({r,scIdx,a,b,x}); }); }));
  }));
  const findings=[]; const counts={}; const checks={}; const tally=k=>{ checks[k]=(checks[k]||0)+1; };
  const toInjectable=()=>{ if(shown($('res-inj'))) return; const inj=q('#route-tabs button').filter(b=>/^(в\/в|в\/м)$/.test(txt(b))&&!b.classList.contains('active')); if(inj.length) pick(inj).click(); };
  // Tab as a browser would do it: dispatch keydown on the focused element; when the shell
  // did not preventDefault, move to the next / previous focusable element of the document
  // (hidden / inert subtrees skipped)
  const docFocusables=()=>[...d.querySelectorAll('a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')].filter(el=>!el.closest('[hidden], .hidden, [inert]')&&w.getComputedStyle(el).display!=='none'&&w.getComputedStyle(el).visibility!=='hidden');
  const pressTab=(shift)=>{ const from=d.activeElement||d.body; const ev=new w.KeyboardEvent('keydown',{key:'Tab',shiftKey:!!shift,bubbles:true,cancelable:true}); from.dispatchEvent(ev); if(ev.defaultPrevented) return; const items=docFocusables(); const i=items.indexOf(from); const next=items.length?items[((i<0?(shift?0:-1):i)+(shift?-1:1)+items.length)%items.length]:null; if(next) next.focus(); else if(from.blur) from.blur(); };
  // saveToHistory with the state it was called in (blocked / weight missing) recorded for
  // the history invariants
  const saveProbe=()=>{
    const n0=w.eval('historyEntries.length'); const blocked=w.eval('activeDrug ? !!calculationBlockReason(parseFloat($("weight").value)) : true');
    const incomplete=w.eval('activeDrug ? !!doseIncompleteReason(getActiveRegimen(), parseFloat($("weight").value)) : false');
    const expect=w.eval('(activeDrug && getActiveRegimen()) ? JSON.stringify({course: getActiveRegimen().duration_days ? courseText(getActiveRegimen()) : "", drug: getDrugRefs(activeDrug).map(k=>(DB.drugs_reference[k]||{}).inn||k).join(" + "), single: Math.round(computeDose(getActiveRegimen(), parseFloat($("weight").value), doseUnitOf(DB.drugs_reference[getDrugRefs(activeDrug)[0]])).singleMg)}) : null');
    w.saveToHistory(); const n1=w.eval('historyEntries.length'); w.__historyDelta={blocked, incomplete, added:n1-n0, toast:txt($('toast')), expect:expect?JSON.parse(expect):null, last:n1>n0?JSON.parse(w.eval('JSON.stringify(historyEntries[0])')):null};
  };
  const actions={
    weight:()=>type($('weight'),pick(['','3.2','7','12.5','25','39.9','45','70','95','0.5','300','12,5'])),
    name:()=>type($('patient-name'),pick(['','Иванов И.И.','Петрова А.','<b>x</b>'])),
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
    // the injection panel is on screen in ~7 % of the states: open an injectable route tab
    // first when there is one, and prefer a chip that is not the active one (a dead click on
    // the active chip proves nothing)
    vial:()=>{ w.__vialClick=null; toInjectable(); const all=q('#vial-list button'); const c=all.filter(b=>!b.classList.contains('active')); if(c.length||all.length){ const b=pick(c.length?c:all); w.__vialClick=[...b.parentElement.children].indexOf(b); tally('vial_clicked'); b.click(); } },
    injRoute:()=>{ w.__injClick=null; toInjectable(); const all=q('#route-selector button'); const c=all.filter(b=>!b.classList.contains('active')); if(c.length||all.length){ const b=pick(c.length?c:all); w.__injClick=txt(b); tally('inj_route_clicked'); b.click(); } },
    // the quick-weight chips, a unit change alone (same number, other unit), keyboard
    // activation of the cards (Enter / Space) and the keyboard path of the search
    weightChip:()=>{ const c=q('.quick-weight-chip'); if(c.length) pick(c).click(); },
    ageUnit:()=>type($('patient-age-unit'),pick(['years','months','days'])),
    keyCard:()=>{ const c=q('#scenario-list .scenario-card, #drug-list .drug-card, #results-box > div[role=button]'); if(!c.length) return; const el=pick(c); el.focus(); el.dispatchEvent(new w.KeyboardEvent('keydown',{key:pick(['Enter',' ']),bubbles:true,cancelable:true})); },
    searchKeys:()=>{ const el=$('search'); type(el,pick(['пневмония','цистит','J18','сепсис','ин'])); el.focus(); const key=pick(['Enter','ArrowDown','Escape']); el.dispatchEvent(new w.KeyboardEvent('keydown',{key,bubbles:true,cancelable:true})); if(key==='ArrowDown'){ const n=1+Math.floor(rnd()*3); for(let i=0;i<n;i++) (d.activeElement||el).dispatchEvent(new w.KeyboardEvent('keydown',{key:rnd()<0.7?'ArrowDown':'ArrowUp',bubbles:true,cancelable:true})); if(rnd()<0.7&&d.activeElement&&d.activeElement!==el) d.activeElement.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true})); } },
    // the group chosen by chip over a typed age (allowed, flagged): type an age and click
    // the chip of another group — the plain walk resets the age too often to stay there
    chipOverAge:()=>{ type($('patient-age-unit'),pick(['years','months'])); type($('patient-age'),pick(['12','150','20','2'])); const other=[...d.querySelectorAll('#age-group button')].filter(b=>!b.classList.contains('active')); if(other.length) pick(other).click(); actions.copy(); },
    // a child on a solid form: mg/kg doses rarely land on a whole tablet, so the «~N таб
    // = M мг» rounding path (and its arithmetic) is reached on purpose
    childTablet:()=>{ type($('patient-age-unit'),'years'); type($('patient-age'),pick(['4','7','10','14'])); type($('weight'),pick(['14','18','22','25','33','38'])); if(childRecs.length) w.selectDisease(pick(childRecs)); const dc=q('#drug-list .drug-card'); if(dc.length&&rnd()<0.7) pick(dc).click(); const ref=w.eval('activeDrug ? getDrugRefs(activeDrug)[0] : null'); const forms=(ref&&DB.drugs_reference[ref]||{forms:[]}).forms||[]; const solid=q('#form-grid button[data-form-idx]').filter(b=>{ const f=forms[+b.dataset.formIdx]; return f&&(f.form_type==='tablet'||f.form_type==='capsule'); }); if(solid.length) pick(solid).click(); },
    // T77: no weight + an mg/kg regimen («—» on screen) — then every door at once: the
    // exports, the printed form and the history must all refuse and say why
    noWeightExport:()=>{ type($('weight'),''); if(childRecs.length) w.selectDisease(pick(childRecs)); const sc=q('#scenario-list .scenario-card'); if(sc.length&&rnd()<0.5) pick(sc).click(); const dc=q('#drug-list .drug-card'); if(dc.length&&rnd()<0.5) pick(dc).click(); actions.copy(); w.dispatchEvent(new w.Event('beforeprint')); saveProbe(); w.__restored=null; },
    newPatient:()=>$('new-patient').click(),
    // a heavy child on a record whose mg/kg regimen hits its daily ceiling below 39 kg:
    // steers the amber cap row oracle (max_daily_capped), which the plain walk reaches rarely
    capDose:()=>{ type($('patient-age-unit'),'years'); type($('patient-age'),pick(['9','11','13'])); type($('weight'),pick(['34','36','38','39.9'])); if(cappedRecs.length) w.selectDisease(pick(cappedRecs)); const sc=q('#scenario-list .scenario-card'); if(sc.length&&rnd()<0.5) pick(sc).click(); const dc=q('#drug-list .drug-card'); if(dc.length&&rnd()<0.7) pick(dc).click(); },
    // a weight typed for a fresh patient (no explicit age yet) infers the group and shows
    // the inference notice — the plain walk sets an explicit age early and rarely gets here
    freshWeight:()=>{ $('new-patient').click(); type($('weight'),pick(['3.2','25','45','70'])); },
    resetDisease:()=>w.resetDisease(),
    // a quick nosology tag («Отит (H66)»): the tag code is recorded for the group invariant
    quickTag:()=>{ const tags=q('.quick-disease-tag'); if(!tags.length) return; const t=pick(tags); const m=(t.getAttribute('onclick')||'').match(/selectQuickDisease\('([^']+)'\)/); w.__quickTag=m?m[1]:null; t.click(); },
    // the query sometimes stays on screen (no click): the panel state is checked after the step
    search:()=>{ type($('search'),pick(['пневмония','цистит','отит','J18','амоксициллин','сепсис','ин','п','qwertyzzz','пневмания','  ','Н66','В20','J 18','котримоксазол','ангина','таза','грипп'])); if(rnd()<0.6){ const hits=[...d.querySelectorAll('#results-box > div[role=button]')]; if(hits.length) pick(hits).click(); } },
    hash:()=>{ const r=pick(computable); const sc=pick(r.scenarios||[]); w.location.hash='#'+r.id+(sc?'/'+sc.id+(rnd()<0.5?'/L'+pick(sc.lines).line_number:''):''); },
    history:()=>{
      saveProbe(); w.__restored=null;
      const btns=[...d.querySelectorAll('#history-list [data-action="restore"]')];
      if(btns.length&&rnd()<0.7){
        const i=Math.floor(rnd()*btns.length);
        const entry=w.eval('JSON.stringify(historyEntries['+i+'])'); const e=JSON.parse(entry);
        const ok=w.restoreHistoryEntry(e);
        w.__restored={ok, ref:e.ref, weight:e.weight, ageGroup:e.ageGroup, patient:e.patient, toast:txt($('toast'))};
      }
    },
    copy:()=>{ w.__copied=null; w.copyForMIS(); w.__mis=w.__copied; w.__copied=null; w.copyLatinRecipe(); w.__rp=w.__copied; },
    print:()=>w.dispatchEvent(new w.Event('beforeprint')),
    // a dialog session: open the КР modal or the history drawer, press Tab / Shift+Tab a
    // few times (focus must stay inside), close it by Escape / its × / the backdrop — the
    // dialog must be closed afterwards with the focus back on the opener
    dialog:()=>{
      w.__dialog=null;
      const which=rnd()<0.5?'modal':'drawer';
      // through the buttons the physician sees (the КР button lives in the result step)
      if(which==='modal'){ if(!shown($('btn-guideline-modal'))) return; $('btn-guideline-modal').click(); } else { $('btn-history').click(); }
      const box=which==='modal'?$('guideline-modal'):$('history-drawer');
      const open=()=>which==='modal'?!box.classList.contains('hidden'):box.classList.contains('open');
      const r={which, opened:open(), initialInside:box.contains(d.activeElement), escaped:[]};
      const n=1+Math.floor(rnd()*6);
      for(let i=0;i<n;i++){ const shift=rnd()<0.4; pressTab(shift); if(!box.contains(d.activeElement)) r.escaped.push((shift?'S':'')+'Tab#'+i+'→'+(d.activeElement&&(d.activeElement.id||d.activeElement.tagName))); }
      r.tabs=n;
      r.how=pick(['esc','button','backdrop']);
      if(r.how==='esc') (d.activeElement||d).dispatchEvent(new w.KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}));
      else if(r.how==='button'){ const b=which==='modal'?box.querySelector('button[aria-label]'):$('drawer-close'); b.click(); }
      else { if(which==='modal') box.click(); else $('drawer-overlay').click(); }
      r.closed=!open(); r.focusOnOpener=d.activeElement===(which==='modal'?$('btn-guideline-modal'):$('btn-history'));
      w.__dialog=r;
    },
    theme:()=>w.toggleTheme(),
  };
  const getDrugRefsSafe=dr=>{ try{ return w.getDrugRefs(dr).join('+'); }catch(e){ return '?'; } };
  const names=Object.keys(actions);
  const stateStr=()=>w.eval('[activeAge, activeDisease&&activeDisease.id, activeScenario&&activeScenario.id, activeLine&&activeLine.line_number, activeDrug&&getDrugRefs(activeDrug).join("+"), currentRouteGroup, activeFormIdx, activeRegimenIdx].join("|")');
  for(let i=0;i<STEPS;i++){
    const name=pick(names); counts[name]=(counts[name]||0)+1;
    const before=stateStr();
    const beforePicked=w.eval('pickedRouteGroup'), beforeSc=w.eval('activeScenario');
    try{ actions[name](); await new Promise(r=>setTimeout(r,0)); }catch(e){ findings.push({step:i,action:name,kind:'exception',msg:String(e&&e.stack||e).slice(0,300),before}); continue; }
    if(errors.length){ findings.push({step:i,action:name,kind:'console',msg:errors.splice(0).join(' || ').slice(0,300),before}); }
    // invariants
    const S=w.eval('({age:activeAge, dis:activeDisease, sc:activeScenario, ln:activeLine, dr:activeDrug, form:activeFormIdx, reg:activeRegimenIdx, route:currentRouteGroup, blocked: activeDrug ? calculationBlockReason(parseFloat($("weight").value)) : null, regimen: activeDrug ? getActiveRegimen() : null, incomplete: activeDrug ? doseIncompleteReason(getActiveRegimen(), parseFloat($("weight").value)) : ""})');
    const where=`#${i} ${name} | ${before} → ${stateStr()}`;
    const push=(kind,msg)=>findings.push({step:i,action:name,kind,msg:String(msg).slice(0,300),where});
    // FUZZ_DUMP_STEP=<n> prints the patient inputs, the result tiles and the exports of
    // one step to stderr — to replay a finding without re-instrumenting the harness
    if(String(i)===process.env.FUZZ_DUMP_STEP){
      const ids=['weight','patient-age','patient-age-unit','patient-gfr','patient-pregnancy','patient-allergy'];
      process.stderr.write(JSON.stringify({step:i,action:name,inputs:Object.fromEntries(ids.map(id=>[id,$(id).value])),chipAge:(d.querySelector('#age-group button.active')||{}).dataset,state:stateStr(),regimen:S.regimen,blocked:S.blocked,doseBlock:txt($('dose-block')),resPo:shown($('res-po'))&&txt($('res-po')).slice(0,300),resInj:shown($('res-inj'))&&txt($('res-inj')).slice(0,300),mis:w.__mis,rp:w.__rp},null,1)+'\n');
    }
    const chipAge=d.querySelector('#age-group button.active'); if(chipAge&&chipAge.dataset.age!==S.age) push('age_chip_mismatch',`chip ${chipAge.dataset.age} vs ${S.age}`);
    if(S.dis&&w.location.hash&&!w.location.hash.startsWith('#'+S.dis.id)) push('hash_mismatch',`${w.location.hash.slice(0,60)} vs ${S.dis.id}`);
    if(!S.dis&&w.location.hash) push('hash_without_disease',w.location.hash.slice(0,60));
    if(name==='newPatient'){
      // «Новый пациент» resets the whole patient context: a name / weight / age / GFR /
      // pregnancy / allergy left behind would colour the NEXT prescription
      tally('new_patient_reset');
      const left=[['patient-name',''],['weight',''],['patient-age',''],['patient-gfr',''],['patient-pregnancy','unknown'],['patient-allergy','none']].filter(([id,v])=>$(id).value!==v).map(([id])=>`${id}=«${$(id).value}»`);
      if(left.length||S.dis||w.location.hash) push('new_patient_context_left',left.join(', ')+(S.dis?' disease='+S.dis.id:'')+(w.location.hash?' hash='+w.location.hash:''));
    }
    if(name==='newPatient'||name==='resetDisease'){
      // the nosology «✕» / «Новый пациент» leave no result tiles, block text, safety banners
      // or route preference behind inside the hidden steps (they used to stay un-hidden)
      tally('reset_clean');
      const left=['res-po','res-inj','dose-block','patient-safety-banners','dilution-block','combo-block'].filter(id=>!$(id).classList.contains('hidden'));
      if(left.length) push('reset_leaves_result_rows',left.join(', '));
      if(w.eval('pickedRouteGroup')!==null) push('reset_keeps_route_pick',String(w.eval('pickedRouteGroup')));
    }
    if(name==='quickTag'&&w.__quickTag){
      // T84: with an adult / child group set, the tag must not open a record written for
      // the other group while a record for this group covers the code (it used to open the
      // first record in DB order: children's otitis for an adult, adults' pneumonia for a
      // child); several equally fitting records go to the search list instead
      const code=w.__quickTag; w.__quickTag=null; tally('quick_tag');
      const up=code.toUpperCase(); const group=w.eval('activeAge');
      const covers=r=>(r.mkb10||[]).some(m=>String(m).toUpperCase().startsWith(up));
      const fits=r=>(r.scenarios||[]).some(sc=>sc&&(!sc.age_group||sc.age_group==='all'||sc.age_group===group));
      const cands=DB.recommendations.filter(covers); const fitting=cands.filter(fits);
      const pickedId=w.eval('activeDisease ? activeDisease.id : null'); const picked=cands.find(r=>r.id===pickedId);
      if(picked){
        if(fitting.length&&!fits(picked)) push('quick_tag_wrong_group',`${code} as ${group}: opened ${pickedId}, fitting ${fitting.map(r=>r.id).join('/')}`);
        if($('search').value.trim()||visible($('results-box'))) push('quick_tag_search_not_cleared',`${code}: «${$('search').value}» box ${visible($('results-box'))}`);
      } else {
        if(cands.length===1||fitting.length===1) push('quick_tag_not_opened',`${code} as ${group}: ${fitting.map(r=>r.id).join('/')||cands.map(r=>r.id).join('/')}`);
        if(cands.length>1&&(!visible($('results-box'))||q('#results-box > div[role=button]').length<2)) push('quick_tag_no_list',`${code} as ${group}: ${q('#results-box > div[role=button]').length} rows`);
      }
    }
    if(name==='dialog'&&w.__dialog){
      const r=w.__dialog; tally('dialog_'+r.which);
      if(!r.opened) push('dialog_not_opened',r.which);
      else {
        if(!r.initialInside) push('dialog_focus_not_moved_in',`${r.which}: ${d.activeElement&&d.activeElement.id}`);
        if(r.escaped.length) push('dialog_focus_escaped',`${r.which}: ${r.escaped.join(', ')}`);
        if(!r.closed) push('dialog_not_closed',`${r.which} by ${r.how}`);
        if(r.closed&&!r.focusOnOpener) push('dialog_focus_not_returned',`${r.which} by ${r.how} → ${d.activeElement&&(d.activeElement.id||d.activeElement.tagName)}`);
      }
      w.__dialog=null;
    }
    // no dialog stays open after an action, and the closed drawer is inert for assistive tech
    {
      const modalOpen=!$('guideline-modal').classList.contains('hidden'); const drawer=$('history-drawer'); const drawerOpen=drawer.classList.contains('open');
      if(modalOpen||drawerOpen) push('dialog_left_open',`modal ${modalOpen} drawer ${drawerOpen}`);
      if(!drawerOpen&&(!drawer.hasAttribute('inert')||drawer.getAttribute('aria-hidden')!=='true')) push('drawer_not_inert',`inert ${drawer.hasAttribute('inert')} aria-hidden ${drawer.getAttribute('aria-hidden')}`);
    }
    if((name==='history'||name==='noWeightExport')&&w.__historyDelta){
      if(w.__historyDelta.blocked&&w.__historyDelta.added>0) push('history_saved_while_blocked','');
      // T77: an mg/kg regimen with no weight (dose «—») is not saved — the toast names the gap
      if(!w.__historyDelta.blocked&&w.__historyDelta.incomplete){ tally('history_incomplete'); if(w.__historyDelta.added>0) push('history_saved_without_weight',''); if(!/Сохранение заблокировано: введите вес пациента/.test(w.__historyDelta.toast)) push('history_incomplete_toast',w.__historyDelta.toast.slice(0,80)); }
      // T85: the saved entry carries the screen's single dose, the full drug name
      // (combination partners included) and the course worded as the exports word it;
      // the drawer row repeats them
      const hd=w.__historyDelta;
      if(hd.added>0&&hd.last&&hd.expect){
        tally('history_entry_content');
        if(hd.last.singleMg!==hd.expect.single) push('history_dose_differs_from_screen',`${hd.last.singleMg} vs ${hd.expect.single}`);
        if(hd.last.drug!==hd.expect.drug) push('history_drug_name',`«${hd.last.drug}» vs «${hd.expect.drug}»`);
        if((hd.last.course||'')!==hd.expect.course) push('history_course_wording',`«${hd.last.course}» vs «${hd.expect.course}»`);
        w.openHistory(); const row=txt(d.querySelector('#history-list .premium-card')||$('history-list')); w.closeHistory();
        if(hd.expect.course&&!row.includes('курс '+hd.expect.course)) push('history_row_course',`row «${row.slice(0,120)}» lacks «курс ${hd.expect.course}»`);
        if(!row.includes(hd.expect.drug)) push('history_row_drug',`row «${row.slice(0,120)}» lacks «${hd.expect.drug}»`);
      }
      w.__historyDelta=null;
    }
    if(name==='history'&&w.__restored){
      // «Открыть расчёт» must re-open exactly what was saved (same DB, same age group)
      const r=w.__restored, ref=r.ref;
      const now=w.eval('({dis:activeDisease&&activeDisease.id, sc:activeScenario&&activeScenario.id, ln:activeLine&&activeLine.line_number, dr:activeDrug&&getDrugRefs(activeDrug).join("+"), route:currentRouteGroup, form:activeFormIdx, reg:activeRegimenIdx, age:activeAge, gfr:$("patient-gfr").value, preg:$("patient-pregnancy").value, all:$("patient-allergy").value, weight:parseFloat($("weight").value)})');
      const diffs=[];
      if(!r.ok) diffs.push('restore returned false: '+r.toast);
      [['dis','disease'],['sc','scenario'],['ln','line'],['dr','drug'],['route','route'],['form','formIdx'],['reg','regimenIdx'],['gfr','gfr'],['preg','pregnancy'],['all','allergy']].forEach(([k,rk])=>{ if(String(now[k])!==String(ref[rk])) diffs.push(`${rk}: ${ref[rk]} → ${now[k]}`); });
      if(r.ageGroup&&now.age!==r.ageGroup) diffs.push(`ageGroup: ${r.ageGroup} → ${now.age}`);
      if(r.weight>0&&now.weight!==r.weight) diffs.push(`weight: ${r.weight} → ${now.weight}`);
      if(r.ok&&$('patient-name').value!==(r.patient||'')) diffs.push(`patient: «${r.patient}» → «${$('patient-name').value}»`);
      if(diffs.length) push('history_restore_mismatch',diffs.join('; '));
      w.__restored=null;
    }
    if(S.sc&&S.dis&&!(S.dis.scenarios||[]).includes(S.sc)) push('scenario_not_in_disease','');
    // notices mirror the state: the allergy banner only for an active drug whose class is hit,
    // the «scenario from the link» note only while a hash scenario is pending, the
    // route-mismatch note only when the record lists a route without any form
    {
      const bannerVis=shown($('allergy-alert-banner'));
      const expectBanner=!!S.dr&&w.eval('getDrugRefs(activeDrug).some(r=>["contraindicated","caution"].includes(checkAllergyStatus(r,$("patient-allergy").value).status))');
      if(expectBanner) tally('allergy_banner_expected');
      if(bannerVis!==expectBanner) push('allergy_banner_stale',`visible ${bannerVis} expected ${expectBanner} (${$('patient-allergy').value})`);
      const noteVis=shown($('scenario-hash-note')); const pending=!!w.eval('pendingHashScenario');
      if(pending) tally('hash_note_expected');
      if(noteVis!==pending) push('hash_note_stale',`visible ${noteVis} pending ${pending}`);
      if(S.dr){
        const mmVis=shown($('route-mismatch-note'));
        // tabs are the record routes that have forms, or (fallback) every form group — the note
        // must be on screen exactly in the fallback case
        const lblK={po:'per os',im:'в/м',iv:'в/в',topical:'местно'};
        const tabKeysMm=[...d.querySelectorAll('#route-tabs button')].map(b=>Object.keys(lblK).find(k=>lblK[k]===txt(b)));
        const intendedMm=(S.dr.route||[]).map(x=>x==='per_os'?'po':x);
        const expectMm=intendedMm.length>0&&tabKeysMm.length>0&&!tabKeysMm.some(k=>intendedMm.includes(k));
        if(expectMm) tally('route_mismatch_note_expected');
        if(mmVis!==expectMm) push('route_mismatch_note_stale',`visible ${mmVis} expected ${expectMm}`);
      } else if(shown($('route-mismatch-note'))) push('route_mismatch_note_stale','visible without a drug');
    }
    // the block notice under the result shows the CURRENT reason (never a previous one),
    // and the weight notice next to the weight field mirrors weightBlockReason / weightWarnReason
    if(S.dr){
      const blockVisNow=shown($('dose-block'));
      if(S.blocked&&blockVisNow){ tally('dose_block_text'); if(txt($('dose-block'))!==S.blocked.replace(/\s+/g,' ').trim()) push('dose_block_text_stale',`«${txt($('dose-block')).slice(0,60)}» vs «${S.blocked.slice(0,60)}»`); }
      if(!S.blocked&&blockVisNow&&S.regimen) push('dose_block_without_reason',txt($('dose-block')).slice(0,80));
    }
    {
      const ww=$('weight-warn'); const wwVis=shown(ww); const wwText=txt(ww.querySelector('span'));
      const exp=w.eval('(function(){ const wv=parseFloat($("weight").value); return weightBlockReason(wv, activeAge)||weightWarnReason(wv, activeAge)||badInputHint()||""; })()').replace(/\s+/g,' ').trim();
      const situational=/^(Для этого режима нужен вес|Группа «новорождённые» выбрана без указания возраста)/.test(wwText);
      if(exp){ tally('weight_warn_expected'); if(!wwVis||wwText!==exp) push('weight_warn_stale',`visible ${wwVis} «${wwText.slice(0,60)}» vs «${exp.slice(0,60)}»`); }
      if(!exp&&wwVis&&!situational) push('weight_warn_stale',`visible without a reason: «${wwText.slice(0,80)}»`);
    }
    // the explicit-age notice mirrors patientAgeDays / activeAge (its «не соответствует»
    // flag must follow every chip click), the weight-inference notice never outlives a
    // typed age or a chip click
    {
      const el=$('age-explicit-notice'); const vis=shown(el); const days=w.eval('patientAgeDays');
      if(vis!==(days!=null)) push('age_explicit_notice_stale',`visible ${vis} patientAgeDays ${days}`);
      else if(vis){
        tally('age_explicit_notice');
        const t=txt(el); const implausible=w.eval('ageInputBlockReason()||""').replace(/\s+/g,' ').trim();
        if(implausible){ if(t!==implausible) push('age_explicit_notice_text',`«${t.slice(0,60)}» vs «${implausible.slice(0,60)}»`); }
        else {
          const g=w.eval('ageGroupFromDays(patientAgeDays)'); const flagged=/не соответствует/.test(t);
          if(flagged!==(g!==S.age)) push('age_explicit_notice_mismatch_flag',`«${t.slice(0,80)}» group ${g} active ${S.age}`);
          if(!t.includes('«'+w.eval('ageGroupLabel(ageGroupFromDays(patientAgeDays))')+'»')) push('age_explicit_notice_text',`«${t.slice(0,80)}» group ${g}`);
        }
      }
      const inf=$('age-infer-notice');
      if(shown(inf)) tally('age_infer_notice_shown');
      if(shown(inf)&&(days!=null||w.eval('userPickedAge'))) push('age_infer_notice_stale',`«${txt(inf).slice(0,80)}» patientAgeDays ${days} userPickedAge ${w.eval('userPickedAge')}`);
    }
    // the patient-safety banners under the result are exactly collectPatientSafetyFlags()
    // of the drug on screen (level + text) and never outlive the result
    {
      const box=$('patient-safety-banners'); const rows=[...box.querySelectorAll('[data-level]')].map(r=>r.dataset.level+':'+txt(r));
      const resultVis=shown($('res-po'))||shown($('res-inj'));
      if(!resultVis){ if(shown(box)) push('safety_banners_without_result',rows.join(' || ').slice(0,120)); }
      else {
        const exp=w.eval('JSON.stringify(collectPatientSafetyFlags(getDrugRefs(activeDrug)).map(f=>f.level+":"+f.text))');
        const expRows=JSON.parse(exp).map(x=>x.replace(/\s+/g,' ').trim());
        if(expRows.length) tally('safety_banners_expected');
        if(expRows.join('|')!==rows.join('|')) push('safety_banners_mismatch',`${rows.length} rows vs ${expRows.length}: ${expRows.join(' || ').slice(0,100)}`);
        if(shown(box)!==expRows.length>0) push('safety_banners_mismatch',`box visible ${shown(box)} expected ${expRows.length>0}`);
      }
    }
    // the regimen chips are exactly the age-eligible regimens of the drug on screen (count,
    // label, active chip = activeRegimenIdx, index in range — getActiveRegimen() falls back
    // to the first regimen silently when the index is stale), the availability note mirrors
    // the drug reference
    if(S.dr){
      const regsN=w.eval('ageEligibleRegimens(activeDrug).length'); const chips=[...d.querySelectorAll('#regimen-list button')];
      const selVis=shown($('regimen-selector'));
      if(selVis!==(regsN>1)) push('regimen_selector_visibility',`visible ${selVis} regimens ${regsN}`);
      if(regsN>0&&!(S.reg>=0&&S.reg<regsN)) push('regimen_idx_out_of_range',`${S.reg} of ${regsN}`);
      if(regsN>1){
        tally('regimen_chips');
        if(chips.length!==regsN) push('regimen_chips_count',`${chips.length} vs ${regsN}`);
        const act=chips.findIndex(b=>b.classList.contains('active')); if(act!==S.reg) push('regimen_chip_mismatch',`chip ${act} vs ${S.reg}`);
        const labels=JSON.parse(w.eval('JSON.stringify(ageEligibleRegimens(activeDrug).map(r=>regimenSummary(r, doseUnitOf(DB.drugs_reference[getDrugRefs(activeDrug)[0]]))))')).map(x=>x.replace(/\s+/g,' ').trim());
        if(chips.map(txt).join('|')!==labels.join('|')) push('regimen_chip_text',`${chips.map(txt).join(' / ').slice(0,100)} vs ${labels.join(' / ').slice(0,100)}`);
      }
      const availVis=shown($('availability-note')); const availExp=!!w.eval('DB.drugs_reference[getDrugRefs(activeDrug)[0]].availability_note');
      if(availExp) tally('availability_note_expected');
      if(availVis!==availExp) push('availability_note_stale',`visible ${availVis} expected ${availExp}`);
    } else if(shown($('regimen-selector'))) push('regimen_selector_visibility','visible without a drug');
    // the injection panel mirrors activeRouteKey / activeVialIdx: the active dilution chip
    // and the route label name the same route, the vial chips are the solvent options of
    // that route with the active one at activeVialIdx (the MIS text takes the vial from
    // the same index)
    if(name==='vial'&&w.__vialClick!=null){ if(w.eval('activeVialIdx')!==w.__vialClick) push('vial_click_not_recorded',`clicked ${w.__vialClick} activeVialIdx ${w.eval('activeVialIdx')}`); w.__vialClick=null; }
    if(name==='injRoute'&&w.__injClick!=null){ if(w.eval('routeKeyLabel(activeRouteKey)').replace(/\s+/g,' ').trim()!==w.__injClick) push('inj_route_click_not_recorded',`clicked ${w.__injClick} activeRouteKey ${w.eval('activeRouteKey')}`); w.__injClick=null; }
    if(shown($('res-inj'))){
      tally('inj_panel');
      const lbl=w.eval('routeKeyLabel(activeRouteKey)').replace(/\s+/g,' ').trim();
      const act=d.querySelector('#route-selector button.active');
      if(!act||txt(act)!==lbl) push('inj_route_chip_mismatch',`${act?txt(act):'none'} vs ${lbl}`);
      if(txt($('inj-route-label'))!==lbl) push('inj_route_label_mismatch',`${txt($('inj-route-label'))} vs ${lbl}`);
      const rk=w.eval('activeRouteKey');
      if(S.route==='iv'&&!/^iv_/.test(rk)) push('inj_route_group_mismatch',`${rk} under ${S.route}`);
      const vialsN=w.eval('(function(){ const ref=DB.drugs_reference[getDrugRefs(activeDrug)[0]]; const rd=ref&&ref.dilution&&ref.dilution[activeRouteKey]; return rd&&rd.solvent_options?rd.solvent_options.length:0; })()');
      const vialVis=shown($('vial-selector'));
      if(vialVis!==(vialsN>1)) push('vial_selector_visibility',`visible ${vialVis} vials ${vialsN}`);
      if(vialsN>1){
        tally('vial_chips');
        const chips=[...d.querySelectorAll('#vial-list button')]; const vi=w.eval('activeVialIdx');
        if(chips.length!==vialsN) push('vial_chips_count',`${chips.length} vs ${vialsN}`);
        const ai=chips.findIndex(b=>b.classList.contains('active')); if(ai!==vi) push('vial_chip_mismatch',`chip ${ai} vs ${vi}`);
        if(!(vi>=0&&vi<vialsN)) push('vial_idx_out_of_range',`${vi} of ${vialsN}`);
      }
    }
    // the record header names the active record (title / МКБ / source), the empty state
    // shows exactly when there is none; the active scenario / drug cards are the ones in
    // state; the quick-weight chip, the allergy badge and the result sub-blocks mirror
    // their inputs
    {
      const hdrVis=shown($('active-disease')), emptyVis=shown($('empty-state'));
      if(hdrVis!==!!S.dis) push('header_visibility',`header ${hdrVis} disease ${S.dis&&S.dis.id}`);
      if(emptyVis!==!S.dis) push('empty_state_visibility',`empty ${emptyVis} disease ${S.dis&&S.dis.id}`);
      if(S.dis){
        if(txt($('active-title'))!==S.dis.name.replace(/\s+/g,' ').trim()) push('header_title_mismatch',`«${txt($('active-title')).slice(0,60)}» vs «${S.dis.name.slice(0,60)}»`);
        const srcExp=w.eval('diseaseSourceLabel(activeDisease)').replace(/\s+/g,' ').trim(); if(txt($('active-cr'))!==srcExp) push('header_source_mismatch',`«${txt($('active-cr')).slice(0,60)}» vs «${srcExp.slice(0,60)}»`);
        const sel=d.querySelector('#scenario-list .scenario-card.active');
        if(S.sc){ const idx=S.dis.scenarios.indexOf(S.sc); if(sel&&+sel.dataset.idx!==idx) push('active_scenario_card_mismatch',`card ${sel.dataset.idx} vs ${idx}`); }
        else if(sel) push('active_scenario_card_without_state',sel.dataset.idx);
        const selDrug=d.querySelector('#drug-list .drug-card.active');
        if(S.dr&&S.ln&&S.sc){ const li=S.sc.lines.indexOf(S.ln), di=S.ln.drugs.indexOf(S.dr); if(selDrug&&(+selDrug.dataset.lineIdx!==li||+selDrug.dataset.drugIdx!==di)) push('active_drug_card_mismatch',`card ${selDrug.dataset.lineIdx}/${selDrug.dataset.drugIdx} vs ${li}/${di}`); }
        else if(selDrug) push('active_drug_card_without_state',`${selDrug.dataset.lineIdx}/${selDrug.dataset.drugIdx}`);
      }
      const wv=parseFloat($('weight').value); const activeChips=[...d.querySelectorAll('.quick-weight-chip.active')];
      if(activeChips.length>1) push('weight_chip_mismatch',`${activeChips.length} active chips`);
      if(activeChips.length===1&&parseFloat(activeChips[0].dataset.weight)!==wv) push('weight_chip_mismatch',`chip ${activeChips[0].dataset.weight} vs weight ${$('weight').value}`);
      if(!activeChips.length&&[...d.querySelectorAll('.quick-weight-chip')].some(c=>parseFloat(c.dataset.weight)===wv)) push('weight_chip_mismatch',`no active chip for weight ${wv}`);
      const badgeVis=shown($('allergy-badge')); if(badgeVis!==($('patient-allergy').value!=='none')) push('allergy_badge_stale',`visible ${badgeVis} allergy ${$('patient-allergy').value}`);
      const resVisNow=shown($('res-po'))||shown($('res-inj'));
      if(resVisNow){
        if(!shown($('drug-meta'))) push('drug_meta_hidden_with_result','');
        const comboExp=w.eval('getDrugRefs(activeDrug).length>1'); if(shown($('combo-block'))!==comboExp) push('combo_block_mismatch',`visible ${shown($('combo-block'))} expected ${comboExp}`);
        if(shown($('res-po'))&&shown($('res-inj'))) push('both_result_boxes_visible','');
        if(shown($('res-po'))!==(S.route==='po'||S.route==='topical')) push('result_box_route_mismatch',`po box ${shown($('res-po'))} route ${S.route}`);
      } else if(shown($('drug-meta'))||shown($('combo-block'))) push('result_sub_block_without_result',`meta ${shown($('drug-meta'))} combo ${shown($('combo-block'))}`);
    }
    // the search panel mirrors the query: the × only with text, the result list and the
    // status line only for a query of 2+ characters, and «Найдено: N» counts the rows
    {
      const qv=$('search').value.trim(); const clearVis=shown($('search-clear')); const boxVis=shown($('results-box')); const stVis=shown($('search-status'));
      if(clearVis!==(qv.length>0)) push('search_clear_stale',`× ${clearVis} query «${qv.slice(0,30)}»`);
      if(qv.length<2&&(boxVis||stVis)) push('search_panel_without_query',`box ${boxVis} status ${stVis} query «${qv}»`);
      if(qv.length>=2){
        tally('search_panel');
        if(!stVis) push('search_status_missing',`query «${qv.slice(0,30)}»`);
        const m=/^Найдено: (\d+)/.exec(txt($('search-status'))); const rows=d.querySelectorAll('#results-box > div[role=button]').length;
        if(m&&(!boxVis||rows!==+m[1])) push('search_count_mismatch',`status ${m[1]} rows ${rows} box ${boxVis}`);
        if(!m&&(boxVis||rows)) push('search_count_mismatch',`«${txt($('search-status')).slice(0,40)}» rows ${rows} box ${boxVis}`);
        // T86: the «нет схемы для группы «G»» note on a row ⇔ the record has no scenario for
        // the CURRENT group, and only once the physician set the group; the list on screen is
        // re-ranked when the group changes (a stale list would name the previous group)
        if(boxVis&&rows){
          const group=w.eval('activeAge'); const picked=w.eval('userPickedAge'); const label={neonate:'новорождённые',child:'дети',adult:'взрослые'}[group];
          const byName=new Map(DB.recommendations.map(r=>[r.name,r]));
          const fits=r=>(r.scenarios||[]).some(sc=>sc&&(!sc.age_group||sc.age_group==='all'||sc.age_group===group));
          let checked=0, firstFit=-1, firstMiss=-1;
          [...d.querySelectorAll('#results-box > div[role=button]')].forEach((row,i)=>{
            const name=row.querySelector('span')?row.querySelector('span').textContent:''; const rec=byName.get(name); if(!rec) return;
            checked++;
            const note=/нет схемы для группы «([^»]+)»/.exec(txt(row));
            const expectNote=picked&&!fits(rec);
            if(!!note!==expectNote) push('search_group_note_mismatch',`«${name.slice(0,40)}» note ${note?note[1]:'-'} picked ${picked} group ${group} fits ${fits(rec)}`);
            else if(note&&note[1]!==label) push('search_group_note_stale',`«${name.slice(0,40)}» says «${note[1]}», group is «${label}»`);
            if(picked){ if(fits(rec)&&firstFit<0) firstFit=i; if(!fits(rec)&&firstMiss<0) firstMiss=i; }
          });
          if(checked) tally('search_group_note');
          // the top row is for the patient's group whenever any row of the list is (phrase
          // rank ties are broken by the group, token hits rank below phrase hits — so only
          // the first row is asserted, and only when the query is a plain phrase hit)
          if(picked&&firstFit>=0&&firstMiss===0){ const top=byName.get(d.querySelector('#results-box > div[role=button] span').textContent); const qf=qv.toLowerCase().replace(/ё/g,'е'); const fitRows=[...d.querySelectorAll('#results-box > div[role=button]')].map(r=>byName.get(r.querySelector('span').textContent)).filter(r=>r&&fits(r)&&!r.calculation_blocked&&r.name.toLowerCase().replace(/ё/g,'е').split(/[^a-zа-яё0-9]+/).some(wd=>wd.startsWith(qf))); if(top&&!top.calculation_blocked&&top.name.toLowerCase().replace(/ё/g,'е').split(/[^a-zа-яё0-9]+/).some(wd=>wd.startsWith(qf))&&fitRows.length) push('search_group_order',`top «${top.name.slice(0,40)}» does not fit «${label}» while «${fitRows[0].name.slice(0,40)}» does`); }
        }
      }
    }
    // arithmetic oracle at the random weight (the walk checks five fixed weights): the
    // single / daily dose on screen is what the DB regimen gives for this weight, the ml
    // tile is dose / concentration of the suspension or of the selected vial solution
    if(S.dr&&S.regimen&&!S.blocked&&(shown($('res-po'))||shown($('res-inj')))){
      const reg=S.regimen; const kg=parseFloat($('weight').value); const freq=reg.freq_per_day||1;
      let daily=null;
      if(reg.single_dose_mg!=null) daily=reg.single_dose_mg*freq;
      else if(reg.dose_mg_kg_per_dose!=null&&kg>0) daily=kg*reg.dose_mg_kg_per_dose*freq;
      else if(reg.dose_mg_kg_day!=null&&kg>0) daily=kg*reg.dose_mg_kg_day;
      else if(reg.dose_mg_day_fixed!=null) daily=reg.dose_mg_day_fixed;
      const rawDaily=daily; let cappedHere=false;
      if(daily!=null&&reg.max_daily_mg!=null&&daily>reg.max_daily_mg){ daily=reg.max_daily_mg; cappedHere=true; }
      const po=shown($('res-po'));
      // the ceiling is announced exactly when it cuts the dose (the amber «Превышена max
      // суточная доза» row); a silent cap or a stale row from the previous drug both count
      const warnEl=po?$('po-max-warn'):$('inj-max-warn'); const warnText=txt(warnEl);
      const capRow=shown(warnEl)&&/Превышена max суточная доза/.test(warnText);
      if(cappedHere&&rawDaily>reg.max_daily_mg+1){ tally('max_daily_capped'); if(!capRow&&!/несогласованы/.test(warnText)) push('max_cap_silent',`${rawDaily} > max ${reg.max_daily_mg}, row «${warnText.slice(0,60)}»`); }
      else if(capRow&&!cappedHere) push('max_cap_row_stale',`row «${warnText.slice(0,80)}» while daily ${rawDaily} ≤ max ${reg.max_daily_mg}`);
      const shownSingle=po?txt($('po-mg')):txt($('inj-mg')); const shownDay=po?txt($('po-day')):txt($('inj-day'));
      if(daily!=null&&Number.isFinite(num(shownSingle))){
        tally('dose_arithmetic');
        const expectSingle=daily/freq;
        if(Math.abs(num(shownSingle)-expectSingle)>1) push('dose_arithmetic',`screen ${shownSingle} vs ${Math.round(expectSingle)} (${kg} kg, ${JSON.stringify({s:reg.single_dose_mg,kgd:reg.dose_mg_kg_day,kgdose:reg.dose_mg_kg_per_dose,fx:reg.dose_mg_day_fixed,max:reg.max_daily_mg,f:freq})})`);
        if(Number.isFinite(num(shownDay))&&Math.abs(num(shownDay)-daily)>1) push('daily_dose_arithmetic',`screen ${shownDay} vs ${Math.round(daily)}`);
        const formNow=w.eval('(DB.drugs_reference[getDrugRefs(activeDrug)[0]]||{forms:[]}).forms[activeFormIdx]||null');
        if(po&&txt($('po-unit'))==='мл'&&/^\d/.test(txt($('po-ml')))){
          const conc=formNow&&formNow.concentration_mg_per_ml; const ml=parseFloat(txt($('po-ml')).replace(',','.'));
          if(!(conc>0)) push('po_ml_without_concentration',txt($('po-ml')));
          else if(Math.abs(ml-expectSingle/conc)>0.06) push('po_volume_arithmetic',`${ml} мл vs ${Math.round(expectSingle)} / ${conc} = ${(expectSingle/conc).toFixed(2)}`);
          else tally('po_volume');
        } else if(!po&&/^\d/.test(txt($('inj-ml')))){
          const vial=w.eval('(function(){ const ref=DB.drugs_reference[getDrugRefs(activeDrug)[0]]||{}; const rd=(ref.dilution||{})[activeRouteKey]||{}; return (rd.solvent_options||[])[activeVialIdx]||null; })()');
          const conc=vial&&(vial.final_concentration_mg_ml||vial.final_concentration_units_ml); const ml=parseFloat(txt($('inj-ml')).replace(',','.'));
          if(!(conc>0)) push('inj_ml_without_concentration',txt($('inj-ml')));
          else if(Math.abs(ml-expectSingle/conc)>0.006) push('inj_volume_arithmetic',`${ml} мл vs ${Math.round(expectSingle)} / ${conc} = ${(expectSingle/conc).toFixed(3)}`);
          else tally('inj_volume');
        }
      } else if(daily!=null&&!shownSingle.startsWith('—')) push('dose_not_shown',`expected ${Math.round(daily/freq)}, screen «${shownSingle}»`);
      // tablets per dose: «(N таб S мг)» means N × S == the single dose; «(~N таб S мг = M мг …)»
      // means M == N × S and N is the nearest half tablet (whole capsule) to dose / S
      const tabs=po?txt($('po-tabs')):'';
      const tm=/^\((~?)([\d.,]+|½)\s+(таб|капс)\s+([\d.,+\s]+?)\s*мг(?:\s*=\s*([\d\s\u00a0]+)\s*мг)?/.exec(tabs);
      if(tabs&&!tm) push('tablet_text_unreadable',tabs.slice(0,80));
      if(tm&&Number.isFinite(num(shownSingle))){
        tally(tm[1]?'tablet_units_rounded':'tablet_units');
        const n=tm[2]==='½'?0.5:parseFloat(tm[2].replace(',','.')); const single=num(shownSingle);
        const strengths=tm[4].split('+').map(x=>parseFloat(x.trim().replace(',','.'))).filter(x=>x>0);
        const cands=strengths.length>1?[strengths[0],strengths[strengths.length-1]]:strengths;
        const fits=cands.some(S=>{ const exact=single/S; const expectN=tm[3]==='капс'?Math.max(1,Math.round(exact)):Math.round(exact*2)/2; if(Math.abs(expectN-n)>1e-9) return false; if(!tm[1]) return Math.abs(n*S-single)<=1; const m=parseFloat(tm[5].replace(/[\s\u00a0]/g,'')); return Math.abs(n*S-m)<=1; });
        if(!fits) push('tablet_units_arithmetic',`${tabs.slice(0,60)} for single ${shownSingle}`);
      }
    }
    // the four steps are visible exactly when their state exists (a visible step with no
    // state = stale cards; a hidden step with state = a dead end for the physician)
    {
      const gatedNow=!!(S.dis&&S.dis.calculation_blocked);
      const expectSteps={ 'scenario-step':!!S.dis&&!gatedNow, 'drug-step':!!S.sc, 'form-step':!!S.dr, 'result-step':!!S.dr };
      Object.entries(expectSteps).forEach(([id,exp])=>{ if(shown($(id))!==exp) push('step_visibility',`${id} visible ${shown($(id))} expected ${exp}`); });
    }
    // a record under the source gate (calculation_blocked) never gets a scenario / drug / result
    if(S.dis&&S.dis.calculation_blocked&&(S.sc||S.dr)) push('blocked_record_opened',`${S.dis.id} sc=${S.sc&&S.sc.id} dr=${S.dr&&getDrugRefsSafe(S.dr)}`);
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
      if(name==='scenario'&&picked!==null) push('route_pick_survives_scenario_click',`${picked}`);
      const sel=d.querySelector('#scenario-list .scenario-card.active'); if(!sel) push('no_active_scenario_card','');
      const selDrug=d.querySelector('#drug-list .drug-card.active'); if(!selDrug) push('no_active_drug_card','');
      const blockVis=visible($('dose-block')), resVis=visible($('res-po'))||visible($('res-inj'));
      if(S.blocked&&resVis) push('result_visible_while_blocked',S.blocked.slice(0,80));
      if(!S.blocked&&S.regimen&&!resVis&&!blockVis) push('no_result_no_block','');
      if(S.regimen&&S.regimen.age_group&&S.regimen.age_group!=='all'&&S.regimen.age_group!==S.age) push('regimen_age_mismatch',`${S.regimen.age_group} vs ${S.age}`);
      const all=txt($('result-step'))+' '+txt($('dose-block')); if(BAD.test(all)) push('bad_token',all.match(/.{0,30}(NaN|Infinity|undefined|\[object |null мг|null ЕД).{0,30}/)[0]);
      // binary float noise («0.30000000000000004 мл») must never reach the screen or an export
      const NOISE=/\d+[.,]\d{5,}/; if(NOISE.test(all)) push('float_noise',all.match(/.{0,30}\d+[.,]\d{5,}.{0,30}/)[0]);
      if(name==='copy'||name==='chipOverAge'||name==='noWeightExport'){
        if(S.blocked&&(w.__mis||w.__rp)) push('export_while_blocked','');
        // T77: no weight for an mg/kg regimen — nothing is copied, the toast names the gap
        if(!S.blocked&&S.incomplete){ tally('export_incomplete'); if(w.__mis||w.__rp) push('export_without_weight',`mis ${!!w.__mis} rp ${!!w.__rp}: ${S.incomplete.slice(0,60)}`); if(!/заблокировано: введите вес пациента/.test(txt($('toast')))) push('export_incomplete_toast',txt($('toast')).slice(0,80)); }
        if(!S.blocked&&w.__mis){
          // the chart text names the drug on screen (INN) and the diagnosis
          const inn=(DB.drugs_reference[w.eval('getDrugRefs(activeDrug)[0]')]||{}).inn||'';
          if(inn&&!w.__mis.includes(inn)) push('mis_names_other_drug',`${inn} not in «${w.__mis.slice(0,100)}»`);
          if(S.dis&&!w.__mis.includes(S.dis.name)) push('mis_names_other_diagnosis',`${S.dis.name} not in «${w.__mis.slice(0,100)}»`);
        }
        if(!S.blocked&&!S.incomplete&&S.regimen&&resVis&&!(w.__mis&&w.__rp)) push('export_empty_while_computed',`mis ${!!w.__mis} rp ${!!w.__rp} toast ${txt($('toast'))}`);
        // every warning the physician sees travels with the chart text: the safety banners,
        // a «противопоказан» allergy banner, the weight caution and the explicit-age / group
        // mismatch notice must each have a flag line in the MIS text
        if(!S.blocked&&w.__mis){
          const misLines=w.__mis.split('\n').map(l=>l.trim()).filter(l=>/^(ВНИМАНИЕ|Предупреждение): /.test(l)).map(l=>l.replace(/^(ВНИМАНИЕ|Предупреждение): /,'').replace(/\s+/g,' ').trim());
          const expected=JSON.parse(w.eval('JSON.stringify(exportSafetyFlags(getDrugRefs(activeDrug)).map(f=>f.text))')).map(x=>x.replace(/\s+/g,' ').trim());
          expected.forEach(t=>{ if(!misLines.includes(t)) push('export_flag_missing',`«${t.slice(0,80)}»`); });
          [...d.querySelectorAll('#patient-safety-banners [data-level]')].forEach(r=>{ if(shown(r)&&!misLines.includes(txt(r))) push('screen_banner_not_in_mis',txt(r).slice(0,80)); });
          const notice=txt($('age-explicit-notice'));
          if(shown($('age-explicit-notice'))&&/не соответствует/.test(notice)){ tally('group_mismatch_export'); if(!misLines.some(l=>/выбрана вручную/.test(l))) push('group_mismatch_not_in_mis',notice.slice(0,80)); }
          if(shown($('weight-warn'))&&/редк/.test(txt($('weight-warn')))&&!misLines.some(l=>/редк/.test(l))) push('weight_caution_not_in_mis',txt($('weight-warn')).slice(0,80));
        }
        // the chart text repeats the screen: the same single dose («Схема приёма: по X …»),
        // the same daily dose, the ceiling note exactly when the amber cap row is shown,
        // the same weight and age group in the patient line
        if(!S.blocked&&w.__mis&&resVis){
          const po=shown($('res-po')); const single=num(po?txt($('po-mg')):txt($('inj-mg'))); const day=num(po?txt($('po-day')):txt($('inj-day')));
          const DOSE=/(\d[\d\s\u00a0]*(?:[.,]\d+)?)\s*(млн|тыс)?\s*(мг|ЕД)/g;
          const first=line=>{ const m=DOSE.exec(line); DOSE.lastIndex=0; return m?num(m[0]):NaN; };
          const scheme=(/Схема приёма: (.+)/.exec(w.__mis)||[])[1]||''; const dailyLine=(/Суточная доза: (.+)/.exec(w.__mis)||[])[1]||'';
          if(scheme&&!/^наружно/.test(scheme)&&Number.isFinite(single)){ tally('mis_dose'); const got=first(scheme); if(!Number.isFinite(got)||Math.abs(got-single)>1) push('mis_single_dose_mismatch',`screen ${single} vs «${scheme.slice(0,70)}»`); }
          if(dailyLine&&Number.isFinite(day)){ const got=first(dailyLine); if(!Number.isFinite(got)||Math.abs(got-day)>1) push('mis_daily_dose_mismatch',`screen ${day} vs «${dailyLine.slice(0,70)}»`); }
          const capRowNow=shown(po?$('po-max-warn'):$('inj-max-warn'))&&/Превышена max/.test(txt(po?$('po-max-warn'):$('inj-max-warn')));
          if(capRowNow&&dailyLine&&!/ограничена максимумом/.test(dailyLine)) push('mis_cap_missing',dailyLine.slice(0,80));
          if(!capRowNow&&/ограничена максимумом/.test(dailyLine)) push('mis_cap_stale',dailyLine.slice(0,80));
          const pat=(/Пациент: (.+)/.exec(w.__mis)||[])[1]||''; const wv=parseFloat($('weight').value);
          if(wv>0&&!pat.startsWith('вес '+wv+' кг')) push('mis_weight_mismatch',`${wv} vs «${pat.slice(0,60)}»`);
          const groupWord={child:'дети',neonate:'новорожденный',adult:'взрослый'}[S.age]; if(groupWord&&!pat.includes('('+groupWord+')')) push('mis_group_mismatch',`${S.age} vs «${pat.slice(0,60)}»`);
          // the Latin recipe: the same drug (Latin INN), the same single dose in the Signa,
          // the route words of the screen in both exports, D.t.d. N. == the MIS course total
          const rp=w.__rp||''; const signa=(rp.split('\n').find(l=>l.startsWith('S.:'))||'');
          const key=w.eval('getDrugRefs(activeDrug)[0]'); const latin=w.eval('(typeof LATIN_INN !== "undefined" && LATIN_INN['+JSON.stringify(key)+']) || ""'); const inn=(DB.drugs_reference[key]||{}).inn||'';
          if(rp&&!(latin&&rp.includes(latin))&&!(inn&&rp.includes(inn))) push('rp_names_other_drug',`${latin||inn} not in «${rp.slice(0,80)}»`);
          const rpDose=/по (?:\d+(?:[.,]\d+)? мл(?: суспензии)? \()?(\d+(?:[.,]\d+)?(?: (?:млн|тыс))?) (мг|ЕД)/.exec(signa);
          if(rpDose&&Number.isFinite(single)&&S.route!=='topical'){ tally('rp_dose'); if(Math.abs(num(rpDose[1]+' '+rpDose[2])-single)>1) push('rp_single_dose_mismatch',`screen ${single} vs «${signa.slice(0,80)}»`); }
          const ROUTE_WORDS={po:/внутрь/,im:/в\/м|внутримышечно/,iv:/в\/в|внутривенно/,topical:/наружно|местно/}; const want=ROUTE_WORDS[S.route];
          if(want&&/\d/.test(scheme)){
            if(!want.test(scheme)) push('mis_route_missing',`${S.route}: «${scheme.slice(0,80)}»`);
            if(signa&&!want.test(signa)) push('rp_route_missing',`${S.route}: «${signa.slice(0,80)}»`);
            const wrong=Object.entries(ROUTE_WORDS).filter(([g,re])=>g!==S.route&&(g==='po'||S.route==='po')&&re.test(scheme+' '+signa));
            if(wrong.length) push('export_route_contradicts_screen',`${S.route} vs ${wrong.map(x=>x[0])}: «${scheme.slice(0,50)}» / «${signa.slice(0,50)}»`);
          }
          // the frequency printed in both exports is the regimen's freq_per_day (a dose
          // repeated the wrong number of times a day is as wrong as a wrong dose)
          const freq=w.eval('(function(){ const r=getActiveRegimen(); return r&&r.freq_per_day>0?r.freq_per_day:0; })()');
          if(freq&&/\d/.test(scheme)&&!/^наружно/.test(scheme)){
            tally('export_freq');
            const mf=/(\d+) р\/сут/.exec(scheme); if(!mf||+mf[1]!==freq) push('mis_freq_mismatch',`regimen ${freq} р/сут vs «${scheme.slice(0,80)}»`);
            const rf=/(\d+) раза? в день/.exec(signa); if(signa&&(!rf||+rf[1]!==freq)) push('rp_freq_mismatch',`regimen ${freq} р/сут vs «${signa.slice(0,80)}»`);
          }
          const misTotal=/суммарно (\d+) таб/.exec(w.__mis); const rpDtd=/D\.t\.d\. N\. (\d+)/.exec(rp);
          if(misTotal&&rpDtd){ tally('course_units'); if(misTotal[1]!==rpDtd[1]) push('course_units_mis_vs_rp',`MIS ${misTotal[1]} таб vs Rp N. ${rpDtd[1]}`); }
          const courseBad=/(хроническая|по ситуации|не указан[а-я]*|однократно) дн/.exec(w.__mis+'\n'+rp); if(courseBad) push('course_words_plus_days',courseBad[0]);
        }
        if(BAD.test((w.__mis||'')+(w.__rp||''))) push('export_bad_token','');
        if(NOISE.test((w.__mis||'')+(w.__rp||''))) push('export_float_noise',((w.__mis||'')+(w.__rp||'')).match(/.{0,30}\d+[.,]\d{5,}.{0,30}/)[0]);
      }
      if(name==='print'||name==='noWeightExport'){
        const rxd=txt($('rx-drugs')); const trust=txt($('rx-trust-line'));
        if(S.blocked&&rxd) push('print_drugs_while_blocked',rxd.slice(0,60));
        if(!S.blocked&&S.incomplete){ tally('print_incomplete'); if(rxd||txt($('rx-signa-text'))) push('print_without_weight',(rxd+' '+txt($('rx-signa-text'))).slice(0,80)); if(!/^ПЕЧАТЬ НЕВОЗМОЖНА: введите вес пациента/.test(trust)) push('print_incomplete_reason',trust.slice(0,80)); }
        if(!S.blocked&&rxd){
          const key=w.eval('getDrugRefs(activeDrug)[0]'); const inn=(DB.drugs_reference[key]||{}).inn||'';
          const latin=w.eval('(typeof LATIN_INN !== "undefined" && LATIN_INN['+JSON.stringify(key)+']) || ""');
          if(!(latin&&rxd.includes(latin))&&!(inn&&rxd.includes(inn))) push('print_names_other_drug',`${latin||inn} not in «${rxd.slice(0,80)}»`);
          const wv=parseFloat($('weight').value); if(wv>0&&txt($('rx-weight'))!==String(wv)+' кг'&&!txt($('rx-weight')).startsWith(String(wv))) push('print_weight_mismatch',`${wv} vs ${txt($('rx-weight'))}`);
        }
        if(!S.blocked&&!S.incomplete&&S.regimen&&resVis&&!rxd) push('print_empty_while_computed',trust.slice(0,80));
        // the printed safety line carries every export flag (the same set as the MIS text)
        if(!S.blocked&&rxd){
          const printed=($('rx-safety-line').textContent||'').split('\n').map(l=>l.trim()).filter(Boolean).map(l=>l.replace(/^!?\s*(ВНИМАНИЕ|Предупреждение): /,'').replace(/\s+/g,' ').trim());
          const expected=JSON.parse(w.eval('JSON.stringify(exportSafetyFlags(getDrugRefs(activeDrug)).map(f=>f.text))')).map(x=>x.replace(/\s+/g,' ').trim());
          if(expected.length) tally('print_flags');
          expected.forEach(t=>{ if(!printed.includes(t)) push('print_flag_missing',`«${t.slice(0,80)}» not in ${printed.length} printed lines`); });
          if(!expected.length&&!$('rx-safety-line').hidden&&printed.length) push('print_flag_without_reason',printed.join(' | ').slice(0,80));
        }
        if(BAD.test(txt($('prescription-form')))) push('print_bad_token','');
      }
    } else {
      if(name==='print'&&txt($('rx-drugs'))) push('print_drugs_without_drug',txt($('rx-drugs')).slice(0,60));
      if((name==='copy'||name==='chipOverAge')&&(w.__mis||w.__rp)) push('export_without_drug','');
    }
  }
  console.log(JSON.stringify({seed,steps:STEPS,findings:findings.slice(0,40),nFindings:findings.length,kinds:findings.reduce((a,f)=>(a[f.kind]=(a[f.kind]||0)+1,a),{}),counts,checks},null,1));
},300);
