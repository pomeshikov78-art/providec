/* ================= ПЛАН РАЗРАБОТКИ (ФАЗЫ 0–6, 36 МЕСЯЦЕВ) ================= */
state.planDone={};
function planProgress(p){
  let d=0;for(let i=0;i<p.tasks.length;i++)if(state.planDone[p.n+"_"+i])d++;
  return Math.round(d/p.tasks.length*100);
}
function planToggle(n,i){
  const k=n+"_"+i;
  state.planDone[k]=!state.planDone[k];
  addAudit((state.planDone[k]?"Отметка выполнения задачи плана":"Снятие отметки"),"Фаза "+n+", задача "+(i+1),state.planDone[k]?"Отмечено":"Снято");
  showPage("plan",true);
}
function planGantt(){
  const W=860,H=46+DEV_PLAN.length*38,padL=210,mm=40;
  const X=m=>padL+(m-1)/mm*(W-padL-24);
  let g='<svg viewBox="0 0 '+W+" "+H+'" width="100%" style="max-width:'+W+'px">';
  [1,6,12,18,24,30,36].forEach(m=>{g+='<line x1="'+X(m)+'" y1="24" x2="'+X(m)+'" y2="'+(H-8)+'" stroke="#1d2e50"/><text x="'+X(m)+'" y="15" fill="#5d719a" font-size="10" text-anchor="middle" font-family="monospace">м'+m+"</text>";});
  const cols=["#64748b","#38bdf8","#34d399","#a78bfa","#fbbf24","#f472b6","#22d3ee"];
  DEV_PLAN.forEach((p,i)=>{
    const y=32+i*38,x1=X(p.m[0]),x2=X(p.m[1]||mm),pr=planProgress(p);
    g+='<text x="'+(padL-10)+'" y="'+(y+14)+'" fill="#8ca0c4" font-size="11" text-anchor="end">Фаза '+p.n+" · "+esc(p.name.length>24?p.name.slice(0,23)+"…":p.name)+"</text>";
    g+='<rect x="'+x1+'" y="'+y+'" width="'+(x2-x1)+'" height="19" rx="6" fill="'+cols[i]+'" opacity="0.22" stroke="'+cols[i]+'" stroke-opacity="0.6"/>';
    if(pr>0)g+='<rect x="'+x1+'" y="'+y+'" width="'+((x2-x1)*pr/100)+'" height="19" rx="6" fill="'+cols[i]+'" opacity="0.85"/>';
    g+='<text x="'+((x1+x2)/2)+'" y="'+(y+13)+'" fill="#dce6f7" font-size="10" text-anchor="middle" font-family="monospace">'+p.m[0]+"–"+(p.m[1]||"…")+" мес · "+p.budget+(pr?"  ·  "+pr+"%":"")+"</text>";});
  g+='<line x1="'+X(0.6)+'" y1="24" x2="'+X(0.6)+'" y2="'+(H-8)+'" stroke="#f87171" stroke-width="1.6" stroke-dasharray="4 3"/><text x="'+(X(0.6)+6)+'" y="'+(H-12)+'" fill="#f87171" font-size="9.5" font-family="monospace">сейчас: прототип v8 · артефакты Фазы 0/1 (backend_scaffold_v1)</text>';
  return g+"</svg>";
}
RENDERERS.plan=function(){
  const totalTasks=DEV_PLAN.reduce((a,p)=>a+p.tasks.length,0);
  const doneTasks=Object.keys(state.planDone).filter(k=>state.planDone[k]).length;
  const totalBudget=DEV_PLAN.slice(0,6).reduce((a,p)=>a+parseInt(p.budget,10),0);
  return pageHead("Поэтапный план разработки (ред. 1.0)",
    'От прототипа к промышленной системе за 36 месяцев: Фазы 0–6 с deliverables и критериями завершения. Стратегия: Agile+Waterfall гибрид (ядро/безопасность — waterfall, модули — agile), MVP-first, dual-track (оба варианта с общей кодовой базы), CI/CD. Чек-листы интерактивны — прогресс фиксируется в журнале аудита сеанса.',
    'Бюджет: '+totalBudget+' млн ₽ (+10 млн ₽/год сопровождение) · срок: 36 мес. · задач в плане: '+totalTasks+" · отмечено: "+doneTasks,
    '<a class="btn ac" href="'+PLAN_DOC+'" target="_blank" rel="noopener" style="text-decoration:none">📄 Полный документ плана ↗</a><button class="btn" onclick="showPage(\'roadmap\')">Статус прототипа →</button>')+
  '<div class="card" style="margin-bottom:14px"><h3><span class="hico">▦</span> Сводный план-график (диаграмма Ганта)</h3>'+planGantt()+
   '<div class="hint" style="margin-top:6px">Заполненная часть полосы — прогресс чек-листа фазы (интерактивно). Красная линия — текущая точка: интерактивный прототип v8.0.0 и стартовые артефакты Фазы 0/1.</div></div>'+
  '<div class="cards c4" style="margin-bottom:14px">'+
   PLAN_STRATEGY.map(x=>'<div class="card"><h3 style="font-size:11.5px"><span class="hico">◆</span> '+esc(x[0])+'</h3><div class="hint" style="font-size:12px;line-height:1.55">'+esc(x[1])+"</div></div>").join("")+"</div>"+
  DEV_PLAN.map(p=>{
    const pr=planProgress(p);
    return '<div class="ivp-card'+(p.n<=1?" open":"")+'" id="plan-ph'+p.n+'"><div class="ivp-head" onclick="accToggleClass(\'plan-ph'+p.n+'\')">'+
     '<span class="ic">ФАЗА '+p.n+'</span><h4>'+esc(p.name)+'</h4>'+
     '<span class="badge b-gray">'+p.m[0]+"–"+(p.m[1]||"…")+" мес.</span>"+
     '<span class="badge b-vio">'+p.budget+" · "+p.share+'%</span>'+
     '<span class="badge '+(pr===100?"b-green":pr>0?"b-blue":"b-gray")+'" style="margin-left:auto">'+pr+'%</span>'+
     '<a href="'+PLAN_DOC+"#ph-"+p.n+'" target="_blank" rel="noopener" class="badge b-gray" style="text-decoration:none" onclick="event.stopPropagation()">п.'+p.n+' док. ↗</a><span class="chev" style="color:var(--tx3)">▶</span></div>'+
     '<div class="ivp-body"><div class="ivp-box" style="margin-bottom:12px"><h5>Цель фазы</h5><div style="font-size:13px;color:var(--tx2);line-height:1.6">'+esc(p.goal)+"</div></div>"+
     '<div class="progress-lg" style="margin-bottom:12px"><i style="width:'+pr+"%;background:"+(pr===100?"var(--green)":"var(--acc)")+'"></i></div>'+
     '<div class="sec-title" style="margin:4px 0 8px">Задачи (чек-лист)</div>'+
     p.tasks.map((t,i)=>{
       const dn=state.planDone[p.n+"_"+i];
       return '<label style="display:flex;gap:9px;align-items:flex-start;padding:5px 7px;border-radius:7px;cursor:pointer;font-size:12.6px;color:'+(dn?"var(--tx3)":"var(--tx2)")+';'+(dn?"text-decoration:line-through":"")+'" onclick="event.preventDefault();planToggle('+p.n+","+i+')">'+
       '<input type="checkbox" '+(dn?"checked":"")+' style="margin-top:3px" onclick="planToggle('+p.n+","+i+')"><span>'+esc(t)+"</span></label>";}).join("")+
     '<div class="ivp-cols" style="margin-top:12px"><div class="ivp-box"><h5>Deliverables</h5><ul>'+p.deliv.map(x=>"<li>"+esc(x)+"</li>").join("")+'</ul></div>'+
     '<div class="ivp-box"><h5>Критерии завершения</h5><ul>'+p.crit.map(x=>"<li>"+esc(x)+"</li>").join("")+"</ul></div></div>"+
     "</div></div>";}).join("")+
  '<div class="cards c2" style="margin-top:16px"><div class="card"><h3><span class="hico">₽</span> Бюджет по фазам (ориентировочно, 300 млн ₽)</h3>'+
   barsSVG(DEV_PLAN.map((p,i)=>({label:"Ф"+p.n,val:p.share,lab:p.share+"%",col:["#64748b","#38bdf8","#34d399","#a78bfa","#fbbf24","#f472b6","#22d3ee"][i]})),{h:190,max:32})+
   '<div class="tbl-wrap" style="margin-top:10px"><table class="tbl"><thead><tr><th>Фаза</th><th>Стоимость</th><th>Доля</th></tr></thead><tbody>'+
   DEV_PLAN.map(p=>"<tr><td>Фаза "+p.n+" · "+esc(p.name)+'</td><td class="mono">'+p.budget+'</td><td class="mono">'+p.share+"%</td></tr>").join("")+
   '<tr><td><b>Итого (без сопровождения)</b></td><td class="mono"><b>'+totalBudget+' млн ₽</b></td><td class="mono"><b>97%</b></td></tr></tbody></table></div></div>'+
  '<div class="card"><h3><span class="hico">⚠</span> Управление рисками плана</h3>'+
   '<div class="tbl-wrap" style="border:none"><table class="tbl"><thead><tr><th>Риск</th><th>Вер.</th><th>Влияние</th><th>Митигация</th></tr></thead><tbody>'+
   PLAN_RISKS.map(r=>'<tr><td>'+esc(r[0])+'</td><td><span class="badge '+(r[1]==="Высокая"?"b-red":r[1]==="Средняя"?"b-gold":"b-green")+'">'+r[1]+'</span></td><td><span class="badge '+(r[2]==="Высокое"?"b-red":r[2]==="Среднее"?"b-gold":"b-green")+'">'+r[2]+"</span></td><td style=\"color:var(--tx2)\">"+esc(r[3])+"</td></tr>").join("")+
   "</tbody></table></div>"+
   '<div class="hint" style="margin-top:9px">Ожидаемые результаты через 36 месяцев: 13 модулей, два варианта поставки, сертификат ФСТЭК (1Б), охват ≥ 95% предприятий, сокращение сроков вывода технологий на 30–40%, снижение дублирующих НИОКР ≥ 50%.</div></div></div>'+
  '<div class="footer-note">План редакции 1.0 · основание: ТЗ v4.0 и прототип · полный текст: '+PLAN_DOC+' · АИС «Техноконтур» | шифр «Провидец»</div>';
};
