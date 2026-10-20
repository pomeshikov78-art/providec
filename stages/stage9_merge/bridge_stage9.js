/* ================= ЭТАП 9 (ОБЪЕДИНЕНИЕ ВЕТОК): МОСТ К СЕРВЕРНЫМ МОДУЛЯМ ЭТАПА 8 =================
   Перенос серверного моста MOD-KPI / MOD-STIM / MOD-DOC / MOD-EXPERT / MOD-AI (Этап 8, ветка
   бэкенда 80 тестов) в закалённую клиентскую ветку v13–v82 (P0.1–P0.59).

   Принципы переноса:
   1. Демо-режим не изменяется: все обёртки при !SRV.connected делегируют исходным функциям.
   2. Все запросы идут через закалённый srvApi() ветки P0 (валидация URL/пути, лимиты размера
      ответа с потоковым чтением, эпоха сессии, таймаут 30 с, credentials:omit, redirect:error).
   3. Защищённые функции (srvTryLogin, doLogin, srvStartPolling, srvApplyBootstrap — их исходный
      текст контролируется встроенными проверками toString) НЕ переопределяются: загрузка
      витринных данных выполняется через хук enterApp и ленивую догрузку в рендерерах.
   4. Серверные операции соответствуют API бэкенда (routers/modules2.py): /api/v1/kpis,
      /api/v1/kpis/recalculate, /api/v1/stims, /api/v1/expert/{id}/assign|conclude,
      /api/v1/documents/{id}/sign|card, /api/v1/ai/run, /api/v1/ai/recommendations[/{rid}/accept]. */
(function stage9ServerModulesBridge(){
  if(window.__TC_STAGE9_BRIDGE)return;
  if(typeof srvApi!=="function"||typeof toast!=="function"||typeof RENDERERS!=="object")return;
  window.__TC_STAGE9_BRIDGE=true;

  /* ---- витринные данные серверных модулей (загружаются после входа/лениво) ----
     Защита от цикла: повторный рендер не перезапускает загрузку, пока не завершён
     предыдущий прогон (_s9LoadInFlight) или данные уже загружены/помечены как
     незагруженные (SRV._s9Stage8Loaded). Ручной повтор — srvLoadStage8(true). */
  let _s9LoadInFlight=false;
  function srvLoadStage8(force){
    if(!SRV.connected)return Promise.resolve(false);
    if(force)SRV._s9Stage8Loaded=false;
    if(SRV._s9Stage8Loaded||_s9LoadInFlight)return Promise.resolve(false);
    _s9LoadInFlight=true;
    const pk=srvApi("/api/v1/kpis").then(r=>{SRV.kpis=r;}).catch(()=>{SRV.kpis=null;});
    const pa=srvApi("/api/v1/ai/recommendations").then(r=>{SRV.ai=r;}).catch(()=>{SRV.ai=null;});
    return Promise.all([pk,pa]).then(()=>{
      _s9LoadInFlight=false;SRV._s9Stage8Loaded=true;
      if(state.page==="kpi"||state.page==="ai")showPage(state.page,true);
      return true;
    },()=>{_s9LoadInFlight=false;SRV._s9Stage8Loaded=true;return false;});
  }
  window.srvLoadStage8=srvLoadStage8;

  /* ---- хук входа: после enterApp в серверном режиме догружаем витрины KPI/AI ---- */
  const _s9OrigEnterApp=enterApp;
  enterApp=function(){
    const r=_s9OrigEnterApp.apply(this,arguments);
    try{if(SRV.connected)srvLoadStage8(true);}catch(e){}
    return r;
  };
  /* ---- хук отключения: очищаем серверные витринные данные ---- */
  const _s9OrigDisconnect=srvDisconnect;
  srvDisconnect=function(reason){SRV.kpis=null;SRV.ai=null;SRV._s9Stage8Loaded=false;return _s9OrigDisconnect(reason);};

  /* ---------------- MOD-KPI: серверный пересчёт из СУБД ---------------- */
  function srvKpiRecalc(){
    if(!SRV.connected){toast("Пересчёт KPI из СУБД доступен в серверном режиме","warn","MOD-KPI");return;}
    if(!can("kpi.recalc")){deny("Регламентный пересчёт KPI");return;}
    srvApi("/api/v1/kpis/recalculate",{method:"POST"}).then(r=>{
      SRV.kpis={period:r.period,items:r.items};
      addAudit("Пересчет KPI (сервер)",r.total+" показателей · отклонений: "+r.breached.length,r.breached.length?"Отклонение от порогов":"Успех");
      if(r.breached.length){
        publish("kpi.threshold_breached","MOD-KPI","Сервер: отклонений "+r.breached.length+" ("+r.breached.map(b=>esc(b.code)).join(", ")+") — MOD-STIM применит эскалацию (Прил. 1.6)","warn");
        toast("Пересчёт KPI: "+r.breached.length+" отклонений от порогов. Опубликованы kpi.threshold_breached; MOD-STIM автоматически применяет меру «Эскалация отраслевым органам».","warn","MOD-KPI");
        srvApi("/api/v1/stims").then(s=>{if(s&&s.items){STIMS.length=0;s.items.forEach(x=>STIMS.push(x));}if(state.page==="stim")showPage("stim",true);}).catch(()=>{});
      } else {
        toast("Пересчёт KPI выполнен на сервере: все показатели в норме (период "+esc(r.period)+").","ok","MOD-KPI");
      }
      showPage("kpi",true);
    }).catch(e=>toast("Сервер отклонил пересчёт KPI: "+(e&&e.message||e),"err","MOD-KPI"));
  }
  window.srvKpiRecalc=srvKpiRecalc;

  const _s9OrigRenderKpi=RENDERERS.kpi;
  RENDERERS.kpi=function(){
    if(SRV.connected&&!SRV.kpis&&!SRV._s9Stage8Loaded){
      srvLoadStage8();
      return pageHead("Показатели эффективности (KPI)",
        'Мониторинг целевых показателей (ТЗ п.2.3) — СЕРВЕРНЫЙ РЕЖИМ: выполняется загрузка показателей из СУБД…',
        'MOD-KPI · источник: СУБД (сервер) · загрузка…','')+
        '<div class="empty-note">Загрузка KPI с сервера… Если данные не появились, проверьте подключение и права (kpi.recalc / view).</div>';
    }
    if(!SRV.connected||!SRV.kpis||!SRV.kpis.items){
      if(SRV.connected)return '<div class="iam-note" style="border-color:rgba(251,191,36,.45);background:rgba(251,191,36,.07)">⚠ Серверный режим: витрина MOD-KPI не загружена (ошибка API, деградация модуля 503 или недостаточно прав). Ниже — демонстрационные данные; они не заменяют серверный пересчёт из СУБД. <button class="btn sm" onclick="srvLoadStage8(true)">⟳ Повторить загрузку</button></div>'+_s9OrigRenderKpi();
      return _s9OrigRenderKpi();
    }
    const items=SRV.kpis.items;
    return pageHead("Показатели эффективности (KPI)",
     'Мониторинг целевых показателей (ТЗ п.2.3) — СЕРВЕРНЫЙ РЕЖИМ: calc-показатели пересчитываются из СУБД (охват реестра, точность верификации, портфель НИОКР, дедупликация через кооперацию), telemetry-показатели — реальные замеры служб MOD-REPORT/MOD-GEO. Отклонение от порога → kpi.threshold_breached → авто-санкция MOD-STIM (Прил. 1.6).',
     'MOD-KPI · период: '+esc(SRV.kpis.period)+' · источник: СУБД (сервер) · отклонений: '+items.filter(k=>!k.met).length,
     '<button class="btn ac" onclick="srvKpiRecalc()">⟳ Регламентный пересчёт</button>')+
    '<div class="cards c2">'+items.map(k=>{
     const pct=k.dir==="up"?Math.min(100,Math.round(k.cur/k.target*100)):Math.min(100,Math.round(k.target/Math.max(k.cur,0.1)*100));
     return '<div class="card kpi"><div class="corner"></div><div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px">'+
      '<div><div class="kv" style="font-size:22px;color:'+(k.met?"var(--green)":"var(--red)")+'">'+String(k.cur).replace(".",",")+" "+esc(k.unit)+'</div><div class="kt">'+esc(k.n)+' <span class="kbd">'+esc(k.code)+' · '+esc(k.source)+'</span></div></div>'+
      sparkSVG(k.hist&&k.hist.length?k.hist:[k.cur],k.met?"#34d399":"#f87171",96,30)+"</div>"+
      '<div class="kgoal">цель: '+esc(k.fmt)+' · <span style="color:'+(k.met?"var(--green)":"var(--red)")+'">'+(k.met?"✓ достигается":"✗ отклонение → kpi.threshold_breached")+'</span></div>'+
      '<div class="bar"><i style="width:'+pct+"%;background:"+(k.met?"var(--green)":"var(--red)")+'"></i></div></div>';}).join("")+"</div>"+
    '<div class="hint" style="margin-top:12px">История — последние 12 замеров · обновлено: '+esc((items[0]&&items[0].updated)||"—")+' · телеметрия KPI-2/4/5/8 накапливается службами сервера и применяется при пересчёте (нормативы ИВП-6).</div>';
  };

  /* ---------------- MOD-EXPERT: назначение и заключения на сервере ---------------- */
  const _s9OrigAssignExpert=assignExpert;
  assignExpert=function(id){
    if(!SRV.connected){return _s9OrigAssignExpert(id);}
    if(!can("expert.assign")){deny("Назначение эксперта");return;}
    srvApi("/api/v1/expert/"+encodeURIComponent(id)+"/assign",{method:"POST"}).then(res=>{
      const v=EXPERT_QUEUE.find(x=>x.id===id);
      if(v){v.expert=res.expert;v.status=res.status;}
      publish("expert.assigned","MOD-EXPERT",esc(id)+" → эксперт "+esc(res.expert)+" (сервер: комиссия ≥ 3 чел., Прил. 3.7)");
      addAudit("Назначение эксперта (сервер)",id+" · "+res.expert,"Успех");
      toast("Эксперт назначен сервером: "+res.expert+". Формируется комиссия (≥ 3 чел.).","ok","MOD-EXPERT");
      showPage("expert",true);
    }).catch(e=>toast("Сервер: назначение отклонено — "+(e&&e.message||e),"err","MOD-EXPERT"));
  };
  const _s9OrigConclude=conclude;
  conclude=function(id){
    if(!SRV.connected){return _s9OrigConclude(id);}
    if(!can("expert.approve")){deny("Выдача экспертного заключения");return;}
    srvApi("/api/v1/expert/"+encodeURIComponent(id)+"/conclude",{method:"POST",body:JSON.stringify({verdict:"Подтверждено"})}).then(res=>{
      const v=EXPERT_QUEUE.find(x=>x.id===id);
      if(v){v.status="done";}
      publish("expert.conclusion_ready","MOD-EXPERT",esc(id)+": заключение подписано ЭЦП ("+esc(res.expert)+") · серверная цепочка ИВП-1");
      addAudit("Выдача экспертного заключения (сервер)",id+" · вердикт: "+res.verdict,"Успех");
      if(res.org_verified){
        const o=orgById(res.org_verified);
        if(o)o.status="verified";
        publish("passport.verified","MOD-PASS",esc(res.org_verified)+" · экспертиза завершена, расхождения устранены (сервер)");
        (res.new_stims||[]).forEach(ns=>{if(!STIMS.find(x=>x.id===ns.id))STIMS.push(ns);});
      }
      toast("Заключение "+id+" готово (ЭЦП)."+(res.org_verified?" Организация "+res.org_verified+" верифицирована; MOD-DOC зарегистрировал заключение, MOD-STIM применил меры — всё через шину событий сервера.":""),"ok","MOD-EXPERT");
      showPage("expert",true);
    }).catch(e=>toast("Сервер: заключение не выдано — "+(e&&e.message||e),"err","MOD-EXPERT"));
  };

  /* ---------------- MOD-DOC: подписание и карточки на сервере ---------------- */
  const _s9OrigSignDoc=signDoc;
  signDoc=function(id){
    if(!SRV.connected){return _s9OrigSignDoc(id);}
    const d=DOCS.find(x=>x.id===id);
    if(d&&d.sign==="Проект"){
      srvApi("/api/v1/documents/"+encodeURIComponent(id)+"/sign",{method:"POST"}).then(res=>{
        d.sign=res.sign;d.version=res.version;
        publish("doc.status_changed","MOD-DOC",esc(id)+": Проект → "+esc(res.sign)+" (неизменяемый поток статусов)");
        addAudit("Подписание документа (сервер)",id+" → "+res.sign,"Успех");
        toast("Документ "+id+" направлен на подписание: статус «"+res.sign+"» (версия "+res.version+"). Поток статусов неизменяем: Проект → На подписании → Подписан (ЭЦП) → Утверждён.","ok","MOD-DOC");
        showPage("doc",true);
      }).catch(e=>toast("Сервер: "+(e&&e.message||e),"err","MOD-DOC"));
    }else{
      srvApi("/api/v1/documents/"+encodeURIComponent(id)+"/card").then(res=>{
        publish("doc.accessed","MOD-DOC",esc(id)+" · просмотр карточки (серверный аудит)");
        addAudit("Просмотр карточки документа (сервер)",id+" · "+res.t,"Успех");
        toast("Карточка "+id+": «"+res.t+"» · статус: "+res.sign+" · версия: "+res.version+(res.signature?" · подпись: "+String(res.signature).slice(0,28)+"…":"")+(res.signed_by?" · подписал: "+res.signed_by:""),"ok","MOD-DOC");
      }).catch(()=>{addAudit("Просмотр карточки документа",id,"Успех");toast("Карточка документа "+id+" (локально): "+(d?d.t:"—"),"ok","MOD-DOC");});
    }
  };

  /* ---------------- MOD-AI: прогнозный цикл ИВП-7 на сервере ---------------- */
  const _s9OrigRunAI=runAI;
  runAI=function(){
    if(!SRV.connected){return _s9OrigRunAI();}
    if(!can("ai.run")){deny("Запуск прогнозного цикла ИИ");return;}
    toast("Прогнозный цикл ИВП-7 выполняется на сервере: tech-gap, риски этапов, рекомендации…","","MOD-AI");
    srvApi("/api/v1/ai/run",{method:"POST"}).then(res=>
      srvApi("/api/v1/ai/recommendations").then(latest=>{
        SRV.ai=latest||{};SRV.ai.run_id=res.run_id;SRV.ai.model=res.model;
        publish("ai.recommendations_ready","MOD-AI","Прогнозный цикл "+esc(res.run_id)+": "+res.tech_gaps.gaps.length+" tech-gap, "+res.fail_risk.length+" рисков этапов, "+res.recommendations.length+" рекомендаций (conf ≥ 0.7) · модель "+esc(res.model));
        addAudit("Запуск ИИ-прогнозирования (сервер)",res.run_id+" · ИВП-7 · модель "+res.model,"Успех");
        toast("Прогнозный цикл "+res.run_id+" выполнен на сервере (модель "+res.model+"). Рекомендаций опубликовано: "+res.recommendations.length+" (confidence ≥ 0.7).","ok","MOD-AI");
        showPage("ai",true);
      })).catch(e=>toast("Сервер: прогнозный цикл отклонён — "+(e&&e.message||e),"err","MOD-AI"));
  };
  const _s9OrigAcceptRec=acceptRec;
  acceptRec=function(btn){
    const box=btn&&btn.closest?btn.closest("[data-rid]"):null;
    const rid=box?box.getAttribute("data-rid"):null;
    if(!SRV.connected||!rid){return _s9OrigAcceptRec(btn);}
    if(!can("ai.accept")){deny("Принятие ИИ-рекомендации");return;}
    srvApi("/api/v1/ai/recommendations/"+encodeURIComponent(rid)+"/accept",{method:"POST"}).then(res=>{
      btn.textContent="✓ Принято";btn.disabled=true;btn.className="btn sm";
      addAudit("Принятие ИИ-рекомендации (сервер)",rid+" · "+String(res.t||"").slice(0,60),"Успех");
      publish("ai.recommendation_accepted","MOD-AI","Рекомендация "+esc(rid)+" принята оператором "+esc(SRV.fio||"")+" (WORM-аудит сервера)");
      toast("Рекомендация принята и зарегистрирована в WORM-аудите сервера.","ok","MOD-AI");
    }).catch(e=>toast("Сервер: "+(e&&e.message||e),"err","MOD-AI"));
  };
  const _s9OrigRenderAi=RENDERERS.ai;
  RENDERERS.ai=function(){
    if(SRV.connected&&!SRV.ai&&!SRV._s9Stage8Loaded){
      srvLoadStage8();
      return pageHead("ИИ-рекомендации и прогнозирование",
        'Предиктивная аналитика (ИВП-7) — СЕРВЕРНЫЙ РЕЖИМ: выполняется загрузка рекомендаций и прогнозов из СУБД…',
        'MOD-AI · источник: сервер · загрузка…','')+
        '<div class="empty-note">Загрузка данных MOD-AI с сервера… Для запуска прогнозного цикла нажмите «Запустить прогнозный цикл» после загрузки.</div>';
    }
    if(!SRV.connected||!SRV.ai){
      if(SRV.connected)return '<div class="iam-note" style="border-color:rgba(251,191,36,.45);background:rgba(251,191,36,.07)">⚠ Серверный режим: данные MOD-AI не загружены (ошибка API, деградация модуля 503 или недостаточно прав). Ниже — демонстрационная витрина; прогнозный цикл доступен после восстановления связи с сервером. <button class="btn sm" onclick="srvLoadStage8(true)">⟳ Повторить загрузку</button></div>'+_s9OrigRenderAi();
      return _s9OrigRenderAi();
    }
    const A=SRV.ai,tg=A.tech_gaps||{gaps:[],threshold:75},gaps=tg.gaps||[];
    const cols=["#f87171","#fbbf24","#34d399","#a78bfa","#38bdf8","#f472b6"];
    const recs=A.recommendations||[];
    return pageHead("ИИ-рекомендации и прогнозирование",
     'Предиктивная аналитика (ИВП-7) — СЕРВЕРНАЯ модель '+esc(A.model||"v4.0-srv")+': прогноз технологических разрывов (сходимость компетенций отрасли к порогу суверенитета '+tg.threshold+'%), детерминированная оценка риска срыва контрольных точек, рекомендации по правилам (публикация при confidence ≥ 0.7). Все расчёты — по реальным данным СУБД (реестр, портфель НИОКР, паспорта, геоаналитика).',
     'MOD-AI · прогон: '+esc(A.run_id||"— (живой пересчёт)")+' · снимок данных DWH от '+today()+' · источник: сервер',
     '<button class="btn ac" onclick="runAI()">▶ Запустить прогнозный цикл</button>')+
    '<div class="cards" style="grid-template-columns:1.2fr 1fr;margin-bottom:14px">'+
     '<div class="card"><h3><span class="hico">◮</span> Прогноз технологических разрывов (6 периодов)</h3>'+
      (gaps.length?lineSVG(gaps.map((g,i)=>({vals:g.prog,col:cols[i%cols.length]})),{h:230,min:20,max:100,xlabel:"— динамика среднего уровня компетенций отрасли, % · целевой порог суверенитета "+tg.threshold+"%"}):'<div class="empty-note">Нет данных компетенций</div>')+
      '<div style="display:flex;gap:14px;flex-wrap:wrap;margin-top:8px">'+gaps.map((g,i)=>'<span style="font-size:11px;color:var(--tx2)"><span style="color:'+cols[i%cols.length]+'">━━</span> '+esc(g.n)+' <b class="mono">'+Math.round(g.conf*100)+'%</b>'+(g.sovereign_by!=null?' · порог: период '+g.sovereign_by:'')+'</span>').join("")+"</div></div>"+
     '<div class="card"><h3><span class="hico">⚠</span> Риск срыва контрольных точек, % (серверная модель)</h3>'+
      (A.fail_risk||[]).map(f=>'<div style="display:flex;gap:8px;align-items:center;font-size:11.5px;margin:5px 0"><span class="mono" style="color:var(--acc2);width:26px">'+esc(f.id)+'</span><span style="flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--tx2)">'+esc(f.name)+' <span class="hint">'+esc(f.org||"")+(f.factors&&f.factors.overdue_days?" · просрочка "+f.factors.overdue_days+" дн":"")+'</span></span><div class="progress-lg" style="width:80px"><i style="width:'+f.risk+"%;background:"+(f.risk>60?"var(--red)":f.risk>35?"var(--gold)":"var(--green)")+'"></i></div><b class="mono" style="width:30px;color:'+(f.risk>60?"var(--red)":f.risk>35?"var(--gold)":"var(--green)")+'">'+f.risk+"%</b></div>").join("")+
      '<div class="hint" style="margin-top:9px">Факторы (детерминированно, воспроизводимо для аудита): отставание TRL ×22 + стадия ×2 + (индекс риска − 20) + просрочка плана /15 дн.</div></div></div>'+
    '<div class="card"><h3><span class="hico">✦</span> Рекомендации системы (публикуются при confidence ≥ 0.7)</h3>'+
     (recs.length?recs.map(r=>'<div data-rid="'+esc(r.rid)+'" style="display:flex;gap:11px;align-items:center;padding:9px 4px;border-bottom:1px dashed var(--line)"><span class="badge b-vio">'+Math.round(r.conf*100)+'%</span><span style="flex:1;font-size:13px">'+esc(r.t)+'</span><span class="kbd">'+esc(r.m)+"</span>"+(r.status==="accepted"?'<span class="badge b-green">✓ Принято'+(r.decided_by?" · "+esc(r.decided_by):"")+"</span>":'<button class="btn sm gr" onclick="acceptRec(this)">Принять</button>')+"</div>").join("")
      :'<div class="empty-note">Прогнозный цикл ещё не выполнялся — нажмите «Запустить прогнозный цикл» (рекомендации появятся после прогона)</div>')+
     '<div class="hint" style="margin-top:9px">Точность прогноза сроков ≥ 80% (критерий ИВП-7). Принятые рекомендации регистрируются в WORM-аудите сервера и рассылаются службой уведомлений ядра.</div></div>';
  };
})();
