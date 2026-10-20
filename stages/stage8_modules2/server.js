/* ==================================================================
   СЕРВЕРНЫЙ РЕЖИМ v9 — мост к реальному бэкенду АИС «Техноконтур»
   (FastAPI + SQLAlchemy + Postgres Pro/SQLite + JWT IAM + шина событий)
   и картооснова Leaflet + OSM (ТЗ п.5.6: MOD-GEO, реальный движок).
   Принцип: демо-режим (модельные данные в файле) сохраняется полностью;
   серверный режим включается явно и деградирует в демо при недоступности
   бэкенда (graceful degradation — как в ядре системы).
   ================================================================== */
const SRV={
  url:"",token:null,refresh:null,connected:false,role:null,fio:"",boot:null,geo:null,
  lastEventId:0,pollTimer:null,lmap:null,ltiles:null,layers:{}
};
(function srvInit(){
  try{SRV.url=localStorage.getItem("tc_srv_url")||"";}catch(e){}
})();

function srvApi(path,opts){
  opts=opts||{};
  const headers=Object.assign({"Content-Type":"application/json"},opts.headers||{});
  if(SRV.token)headers["Authorization"]="Bearer "+SRV.token;
  return fetch(SRV.url.replace(/\/$/,"")+path,Object.assign({},opts,{headers}))
    .then(r=>{
      if(r.status===401&&SRV.connected){srvDisconnect("Сеанс истек (401)");throw new Error("401");}
      if(!r.ok)return r.json().catch(()=>({})).then(b=>{const e=new Error(b.detail||("HTTP "+r.status));e.status=r.status;throw e;});
      const ct=r.headers.get("content-type")||"";
      return ct.indexOf("json")>=0?r.json():r.text();
    });
}

function srvDisconnect(reason){
  SRV.connected=false;SRV.token=null;
  if(SRV.pollTimer){clearInterval(SRV.pollTimer);SRV.pollTimer=null;}
  const b=document.getElementById("srvBadge");
  if(b){b.textContent="ДЕМО-РЕЖИМ";b.style.cssText="font-size:10px;padding:3px 8px;border-radius:6px;border:1px solid rgba(251,191,36,.5);color:#fbbf24;letter-spacing:1px";}
  if(reason)toast("Серверный режим отключен: "+reason,"warn","API Gateway");
}

/* ---------------- вход через реальный IAM (JWT + MFA) ---------------- */
async function srvTryLogin(){
  const url=(document.getElementById("srvUrl")||{}).value||SRV.url;
  const login=((document.getElementById("srvLogin")||{}).value||"admin").trim();
  const pass=((document.getElementById("srvPass")||{}).value||"");
  if(url){SRV.url=url;try{localStorage.setItem("tc_srv_url",url);}catch(e){}}
  let body={login:login,password:pass};
  let r=await srvApi("/api/v1/auth/login",{method:"POST",body:JSON.stringify(body)});
  if(r&&r.mfa_required){
    const code=window.prompt("MFA (TOTP) для роли "+login.toUpperCase()+": введите 6-значный код");
    if(!code)throw new Error("MFA отменен");
    body.mfa_code=code;
    r=await srvApi("/api/v1/auth/login",{method:"POST",body:JSON.stringify(body)});
  }
  SRV.token=r.access_token;SRV.refresh=r.refresh_token||null;SRV.role=r.role_level;SRV.fio=r.fio||login;
  SRV.connected=true;
  // загрузка реальных данных из СУБД одним запросом
  const b=await srvApi("/api/v1/bootstrap");
  srvApplyBootstrap(b);
  try{SRV.geo=await srvApi("/api/v1/geo/config");}catch(e){SRV.geo=null;}
  // синхронизация клиентской сессии
  if(typeof loginRole!=="undefined"&&r.role_level)loginRole=r.role_level;
  const un=document.getElementById("userName");if(un&&SRV.fio)un.value=SRV.fio;
  const ob=document.getElementById("srvBadge");
  if(ob){ob.textContent="СЕРВЕР ✓ JWT";ob.style.cssText="font-size:10px;padding:3px 8px;border-radius:6px;border:1px solid rgba(52,211,153,.5);color:#34d399;letter-spacing:1px";}
  srvStartPolling();
  return r;
}

function srvApplyBootstrap(b){
  SRV.boot=b;
  if(b.orgs&&b.orgs.length&&typeof ORGS!=="undefined"){ORGS.length=0;b.orgs.forEach(o=>ORGS.push(o));}
  if(b.projects&&typeof PROJECTS!=="undefined"){PROJECTS.length=0;b.projects.forEach(p=>{if(!p.pert)p.pert=[30,50,90];PROJECTS.push(p);});}
  if(b.risks&&typeof RISKS!=="undefined"){RISKS.length=0;b.risks.forEach(r=>RISKS.push(r));}
  if(b.docs&&typeof DOCS!=="undefined"){DOCS.length=0;b.docs.forEach(d=>DOCS.push(d));}
  if(b.stims&&typeof STIMS!=="undefined"){STIMS.length=0;b.stims.forEach(s=>STIMS.push(s));}
  if(b.expert&&typeof EXPERT_QUEUE!=="undefined"){EXPERT_QUEUE.length=0;b.expert.forEach(v=>EXPERT_QUEUE.push(v));}
}

/* ---------------- живая шина: опрос журнала событий сервера ---------------- */
function srvStartPolling(){
  if(SRV.pollTimer)clearInterval(SRV.pollTimer);
  SRV.pollTimer=setInterval(()=>{
    if(!SRV.connected)return;
    srvApi("/api/v1/core/events?limit=20").then(list=>{
      if(!Array.isArray(list))return;
      list.reverse().forEach(e=>{
        if(e.id<=SRV.lastEventId)return;
        SRV.lastEventId=e.id;
        const ev={id:++state.evSeq,ts:(e.ts||"").slice(11)||now(),type:e.type,source:"SRV:"+e.source,payload:e.payload,sev:e.sev||"info"};
        state.events.unshift(ev);if(state.events.length>400)state.events.pop();
        try{tickerPush(ev);busFeedPush(ev);}catch(err){}
        if(ev.sev==="alert"||ev.sev==="warn"){try{addNotif(ev);}catch(err){}}
      });
      if(state.page==="bus"){try{showPage("bus",true);}catch(err){}}
    }).catch(()=>{});
  },6000);
}

/* ---------------- обёртка входа: серверный режим → демо-фолбэк ---------------- */
const _origDoLogin=doLogin;
doLogin=function(){
  const chk=document.getElementById("srvEnabled");
  if(!(chk&&chk.checked)){_origDoLogin();return;}
  const btn=document.getElementById("loginBtn");btn.disabled=true;
  toast("Подключение к бэкенду: "+SRV.url+" …","","API Gateway");
  srvTryLogin().then(r=>{
    toast("Серверный режим: JWT выдан, роль "+SRV.role+", данные загружены из СУБД ("+(SRV.boot&&SRV.boot.orgs?SRV.boot.orgs.length:0)+" организаций)","ok","IAM");
    _origDoLogin();
  }).catch(err=>{
    toast("Бэкенд недоступен ("+(err&&err.message||err)+") — вход в демо-режиме","warn","Graceful degradation");
    srvDisconnect(null);_origDoLogin();
  });
};

/* ---------------- сквозная запись операций на сервер ---------------- */
const _origSetModule=setModule;
setModule=function(code,on,silent){
  const r=_origSetModule(code,on,silent);
  if(SRV.connected){srvApi("/api/v1/core/modules/"+code,{method:"PATCH",body:JSON.stringify({enabled:!!on})})
    .catch(e=>{if(e.status===403||e.status===409)toast("Сервер отклонил: "+(e.message||""),"warn","CORE:ModuleRegistry");});}
  return r;
};
const _origGateDecision=gateDecision;
gateDecision=function(id,d){
  _origGateDecision(id,d);
  if(SRV.connected){srvApi("/api/v1/niokr/projects/"+id+"/gates",{method:"POST",body:JSON.stringify({decision:d,comment:""})})
    .then(res=>{const p=PROJECTS.find(x=>x.id===id);if(p&&res&&typeof res.stage==="number"){p.stage=res.stage;p.gate=res.gate;}})
    .catch(e=>toast("Сервер: решение не зафиксировано ("+(e.message||"")+")","warn","MOD-NIOKR"));}
};
const _origSendVerify=sendVerify;
sendVerify=function(id){
  _origSendVerify(id);
  if(SRV.connected){srvApi("/api/v1/orgs/"+id+"/verify",{method:"POST"})
    .catch(e=>{ if(e.status===403){ return srvApi("/api/v1/orgs/"+id+"/verify?submit=true",{method:"POST"}); } throw e; })
    .catch(()=>{});}
};

/* ---------------- серверные отчёты (реальные DOCX/XLSX/PDF) ---------------- */
function srvDownload(path,fallbackName){
  if(!SRV.connected){toast("Серверные отчеты доступны в серверном режиме","warn","MOD-REPORT");return;}
  fetch(SRV.url.replace(/\/$/,"")+path,{headers:{Authorization:"Bearer "+SRV.token}})
    .then(r=>{if(!r.ok)throw new Error("HTTP "+r.status);return r.blob();})
    .then(b=>{
      const a=document.createElement("a");a.href=URL.createObjectURL(b);
      a.download=fallbackName||path.split("/").pop();document.body.appendChild(a);a.click();
      setTimeout(()=>{URL.revokeObjectURL(a.href);a.remove();},500);
      toast("Отчет с сервера: "+a.download+" ("+(b.size/1024).toFixed(0)+" КБ)","ok","MOD-REPORT");
    }).catch(e=>toast("Ошибка загрузки отчета: "+e.message,"warn","MOD-REPORT"));
}

/* ================= КАРТООСНОВА LEAFLET + OSM (MOD-GEO) ================= */
function leafletLoad(cb){
  if(window.L){cb(true);return;}
  if(SRV._lLoading){SRV._lQueue=(SRV._lQueue||[]);SRV._lQueue.push(cb);return;}
  SRV._lLoading=true;
  const css=document.createElement("link");css.rel="stylesheet";
  css.href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";document.head.appendChild(css);
  const js=document.createElement("script");
  js.src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
  const done=ok=>{SRV._lLoading=false;(SRV._lQueue||[]).forEach(f=>{try{f(ok);}catch(e){}});SRV._lQueue=[];cb(ok);};
  js.onload=()=>done(true);
  js.onerror=()=>done(false);
  setTimeout(()=>{if(SRV._lLoading)done(!!window.L);},6000);
  document.head.appendChild(js);
}

function geoEngineToggle(){
  state.geo.engine=state.geo.engine==="leaflet"?"svg":"leaflet";
  if(state.geo.engine==="leaflet"){
    leafletLoad(ok=>{
      if(!ok){state.geo.engine="svg";toast("Leaflet/OSM недоступны (офлайн) — картооснова «схема». В варианте Б укажите локальный тайл-сервер.","warn","MOD-GEO");showPage("geo",true);return;}
      renderLeafletMap();
      toast("Картооснова: Leaflet + тайлы OSM (реальный картодвижок, ТЗ п.5.6)","ok","MOD-GEO");
    });
  } else { try{if(SRV.lmap){SRV.lmap.remove();SRV.lmap=null;}}catch(e){} showPage("geo",true); }
}

function _lFilteredOrgs(){
  const f=state.geo.filters;
  return ORGS.filter(o=>
    (f.type==="all"||o.type===f.type)&&
    (f.trl==="all"||(f.trl==="low"&&o.trl<=3)||(f.trl==="mid"&&o.trl>=4&&o.trl<=6)||(f.trl==="high"&&o.trl>=7))&&
    (f.reg==="all"||o.reg===f.reg));
}

function renderLeafletMap(){
  const svg=document.getElementById("mapsvg");if(!svg||!window.L)return;
  let box=document.getElementById("leafletMap");
  if(!box){
    box=document.createElement("div");box.id="leafletMap";
    box.style.cssText="position:absolute;inset:0;z-index:5;background:#0a1223;border-radius:10px";
    svg.parentElement.style.position="relative";
    svg.parentElement.appendChild(box);
  }
  svg.style.display="none";box.style.display="block";
  if(!SRV.lmap){
    SRV.lmap=L.map(box,{worldCopyJump:true}).setView([58,62],3);
    const tile=(SRV.geo&&SRV.geo.tile_url)||"https://tile.openstreetmap.org/{z}/{x}/{y}.png";
    SRV.ltiles=L.tileLayer(tile,{maxZoom:18,attribution:(SRV.geo&&SRV.geo.attribution)||"© OpenStreetMap contributors"}).addTo(SRV.lmap);
    SRV.lmap.on("click",e=>{
      if(!state.geo.measureOn)return;
      state.geo.measure.push([e.latlng.lat,e.latlng.lng]);
      if(state.geo.measure.length===2){
        const a=state.geo.measure[0],b=state.geo.measure[1];
        const show=(d)=>{L.polyline([a,b],{color:"#38bdf8",weight:2,dashArray:"6 4"}).addTo(SRV.lmap)
            .bindPopup("Расстояние: "+d.toFixed(1)+" км (WGS84)").openPopup();
          toast("Измерение: "+d.toFixed(1)+" км","ok","MOD-GEO · ИВП-GEO-4");};
        if(SRV.connected){srvApi("/api/v1/geo/measure?lat1="+a[0]+"&lon1="+a[1]+"&lat2="+b[0]+"&lon2="+b[1])
            .then(r=>show(r.distance_km)).catch(()=>show(_hav(a,b)));}
        else show(_hav(a,b));
        state.geo.measure=[];
      }
    });
  }
  setTimeout(()=>{try{SRV.lmap.invalidateSize();}catch(e){}},60);
  // слои
  Object.keys(SRV.layers).forEach(k=>{try{SRV.lmap.removeLayer(SRV.layers[k]);}catch(e){} delete SRV.layers[k];});
  const L0=state.geo.layers;
  if(L0.markers){
    const g=L.layerGroup();
    const col={ent:"#3B82F6",nio:"#10B981",test:"#F59E0B"};
    _lFilteredOrgs().forEach(o=>{
      const m=L.circleMarker([o.lat,o.lon],{radius:4+Math.min(6,o.emp/2000),color:col[o.type]||"#94a3b8",
        fillColor:col[o.type]||"#94a3b8",fillOpacity:.85,weight:1});
      m.bindTooltip("<b>"+esc(o.short)+"</b> ("+o.id+")<br>"+esc(o.city)+" · "+esc(o.reg)+"<br>TRL/MRL/IRL: "+o.trl+"/"+o.mrl+"/"+o.irl+"<br>Сотрудников: "+o.emp,{sticky:true});
      m.on("click",()=>{try{state.selEnt=o.id;showPage("pass",true);toast("Паспорт "+o.id+" — данные из "+(SRV.connected?"СУБД (серверный режим)":"демо-набора"),"","MOD-PASS");}catch(e){}});
      g.addLayer(m);
    });
    g.addTo(SRV.lmap);SRV.layers.markers=g;
  }
  if(L0.heat){
    const g=L.layerGroup();
    const draw=pts=>{pts.forEach(p=>{L.circleMarker([p[0],p[1]],{radius:8+p[2]*26,color:"transparent",
        fillColor:"#f87171",fillOpacity:.10+p[2]*.35,interactive:false}).addTo(g);});
      g.addTo(SRV.lmap);SRV.layers.heat=g;};
    if(SRV.connected){srvApi("/api/v1/geo/heatmap?weight=emp").then(r=>draw(r.points)).catch(()=>draw(_kdeLocal()));}
    else draw(_kdeLocal());
  }
  if(L0.clusters){
    const g=L.layerGroup();
    const draw=items=>{items.forEach(c=>{
        L.circleMarker([c.lat,c.lon],{radius:10+Math.min(14,c.count),color:"#38bdf8",weight:2,fillColor:"#0ea5e9",fillOpacity:.25})
         .bindTooltip("Кластер H3: "+c.count+" орг.<br>"+(c.regions||[]).join(", ")+"<br>Средний TRL: "+(c.avg_trl||"—"),{sticky:true}).addTo(g);});
      g.addTo(SRV.lmap);SRV.layers.clusters=g;};
    if(SRV.connected){srvApi("/api/v1/geo/clusters").then(r=>draw(r.items)).catch(()=>draw(_gridClusters()));}
    else draw(_gridClusters());
  }
  if(L0.links){
    const g=L.layerGroup();
    ORGS.forEach(o=>(o.links||[]).forEach(id=>{const t=orgById(id);if(!t)return;
      L.polyline([[o.lat,o.lon],[t.lat,t.lon]],{color:"#818cf8",weight:1,opacity:.45}).addTo(g);}));
    g.addTo(SRV.lmap);SRV.layers.links=g;
  }
  const st=document.getElementById("mapStatus");
  if(st)st.innerHTML="Картооснова: <b>Leaflet 1.9 + OSM</b>"+(SRV.connected?" · данные СУБД (сервер)":" · демо-данные")+" · объектов: "+_lFilteredOrgs().length+" · H3/KDE: "+(SRV.connected?"серверные алгоритмы":"локальные");
}
function _hav(a,b){const R=6371,dLat=(b[0]-a[0])*Math.PI/180,dLon=(b[1]-a[1])*Math.PI/180;
  const s=Math.sin(dLat/2)**2+Math.cos(a[0]*Math.PI/180)*Math.cos(b[0]*Math.PI/180)*Math.sin(dLon/2)**2;
  return 2*R*Math.asin(Math.sqrt(s));}
function _kdeLocal(){
  const h=150,pts=[],orgs=ORGS;
  for(let lat=42;lat<=80;lat+=2)for(let lon=20;lon<=190;lon+=3){
    let d=0;orgs.forEach(o=>{const dd=Math.hypot((lat-o.lat)*111,(lon-o.lon)*70);
      if(dd<=3*h)d+=o.emp*Math.exp(-(dd*dd)/(2*h*h));});
    if(d>0)pts.push([lat,lon,d]);}
  const mx=Math.max.apply(null,pts.map(p=>p[2]))||1;
  return pts.map(p=>[p[0],p[1],p[2]/mx]).sort((a,b)=>b[2]-a[2]).slice(0,400);
}
function _gridClusters(){
  const g={};ORGS.forEach(o=>{const k=Math.round(o.lat/4)+"_"+Math.round(o.lon/4);
    (g[k]=g[k]||{lat:0,lon:0,count:0,regions:[],_n:0});const c=g[k];
    c.lat=(c.lat*c._n+o.lat)/(c._n+1);c.lon=(c.lon*c._n+o.lon)/(c._n+1);c._n++;c.count++;
    if(c.regions.indexOf(o.reg)<0)c.regions.push(o.reg);});
  return Object.keys(g).map(k=>({lat:g[k].lat,lon:g[k].lon,count:g[k].count,regions:g[k].regions,avg_trl:null})).sort((a,b)=>b.count-a.count);
}

/* кнопка переключения картоосновы в тулбаре MOD-GEO */
const _origPostGeo=POST.geo;
POST.geo=function(){
  _origPostGeo();
  try{
    const svg=document.getElementById("mapsvg");if(!svg)return;
    const bar=svg.parentElement.querySelector(".mtbtn")?svg.parentElement.querySelector(".mtbtn").parentElement:svg.parentElement;
    if(document.getElementById("geoEngineBtn"))return;
    const b=document.createElement("button");b.id="geoEngineBtn";b.className="mtbtn";
    b.textContent="🌐 OSM/Leaflet";b.title="Реальный картографический движок (Leaflet + тайлы OSM; вариант Б — локальный тайл-сервер). Повторный клик — возврат к схеме.";
    b.onclick=geoEngineToggle;
    bar.insertBefore(b,bar.firstChild);
    if(state.geo.engine==="leaflet")leafletLoad(ok=>{if(ok)renderLeafletMap();});
  }catch(e){}
};

/* ---------------- серверный MOD-INT: живые коннекторы на странице интеграций ---------------- */
POST.int=function(){
  if(!SRV.connected)return;
  try{
    const main=document.getElementById("main");
    if(!main||document.getElementById("srvIntCard"))return;
    const card=document.createElement("div");card.id="srvIntCard";card.className="card";
    card.innerHTML='<h3><span class="hico">⇄</span> Серверный MOD-INT: коннекторы бэкенда (реальный обмен)</h3><div id="srvIntBody" class="hint">загрузка статусов…</div>';
    main.insertBefore(card,main.firstChild);
    srvApi("/api/v1/int/connectors").then(d=>{
      const rows=(d.connectors||[]).map(c=>'<tr><td class="mono">'+c.code+'</td><td>'+esc(c.name||"ЕСИА")+'</td><td>'+esc(c.mode||"oidc")+'</td><td>'+(c.calls!==undefined?(c.calls+" ("+c.ok+" ok)"):"—")+'</td><td>'+(c.circuit?("breaker: "+c.circuit):(c.enabled!==undefined?(c.enabled?"включен":"выключен"):"—"))+'</td></tr>').join("");
      const body=document.getElementById("srvIntBody");
      if(body)body.innerHTML='<table class="tbl"><thead><tr><th>Код</th><th>Коннектор</th><th>Режим</th><th>Вызовы</th><th>Статус</th></tr></thead><tbody>'+rows+'</tbody></table>'+
        '<div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap">'+
        '<button class="btn ac" onclick="srvEnrichEgrul()">⚡ Обогастить '+esc(state.selEnt)+' из ЕГРЮЛ (ИВП-1)</button>'+
        '<button class="btn" onclick="srvAssprStatus()">📦 Импорт АССПР через API</button></div>'+
        '<div class="hint" style="margin-top:7px">Режим стенда: '+esc(d.mode)+' · вариант: '+esc(d.variant)+'. В live-режиме — реальные HTTPS-вызовы ФНС/ГИСП/ФИПС по сервисным сертификатам (Фаза 4 плана).</div>';
    }).catch(e=>{const b=document.getElementById("srvIntBody");if(b)b.textContent="Серверный MOD-INT недоступен: "+e.message;});
  }catch(e){}
};
function srvEnrichEgrul(){
  if(!SRV.connected){toast("Обогащение из ЕГРЮЛ доступно в серверном режиме","warn","MOD-INT");return;}
  srvApi("/api/v1/int/egryul/enrich/"+state.selEnt,{method:"POST"}).then(r=>{
    toast("ЕГРЮЛ → паспорт "+state.selEnt+": обогащено полей "+r.applied_fields.length+" (ред. "+r.version+")","ok","MOD-INT");
    publish("int.egrul_enriched","SRV:MOD-INT",state.selEnt+": обогащение из ЕГРЮЛ — "+r.applied_fields.join(", "));
  }).catch(e=>toast("Обогащение не удалось: "+(e&&e.message||e),"warn","MOD-INT"));
}
function srvAssprStatus(){
  toast("Импорт пакетов АССПР v2.4 — API: POST /api/v1/int/asspr/import (роли L6/L7, идемпотентность по ID пакета). Локальный демо-мастер — ниже на странице.","","MOD-INT");
}

/* ---------------- верхняя панель: бейдж режима ---------------- */
const _origEnterApp=enterApp;
enterApp=function(){
  _origEnterApp();
  try{
    const vb=document.getElementById("variantBadge");
    if(vb&&!document.getElementById("srvBadge")){
      const s=document.createElement("span");s.id="srvBadge";
      s.textContent=SRV.connected?"СЕРВЕР ✓ JWT":"ДЕМО-РЕЖИМ";
      s.style.cssText="font-size:10px;padding:3px 8px;border-radius:6px;margin-left:8px;letter-spacing:1px;border:1px solid "+
        (SRV.connected?"rgba(52,211,153,.5);color:#34d399":"rgba(251,191,36,.5);color:#fbbf24");
      vb.parentElement.insertBefore(s,vb.nextSibling);
    }
  }catch(e){}
};
const _origLogout=logout;
logout=function(){
  if(SRV.connected&&SRV.token){
    try{fetch(SRV.url.replace(/\/$/,"")+"/api/v1/auth/logout",{method:"POST",headers:{Authorization:"Bearer "+SRV.token},keepalive:true});}catch(e){}
  }
  srvDisconnect(null);_origLogout();
};

/* серверный режим в демо-интерфейсе: справка на странице «О системе» */
(function(){
  const hint=document.getElementById("srvHint");
  if(hint&&SRV.url){const u=document.getElementById("srvUrl");if(u)u.value=SRV.url;}
})();

/* ================= ЭТАП 8 (ФАЗА 2): МОСТ К СЕРВЕРНЫМ МОДУЛЯМ =================
   MOD-KPI, MOD-STIM, MOD-DOC, MOD-EXPERT, MOD-AI — бизнес-логика на сервере
   (FastAPI-сервисы + СУБД + шина событий). В демо-режиме сохраняется поведение
   витрины v12; в серверном режиме данные и операции идут из/в бэкенд.       */

/* ---- догрузка серверных витринных данных при входе ---- */
const _origSrvTryLogin8=srvTryLogin;
srvTryLogin=async function(){
  const r=await _origSrvTryLogin8.apply(this,arguments);
  try{SRV.kpis=await srvApi("/api/v1/kpis");}catch(e){SRV.kpis=null;}
  try{SRV.ai=await srvApi("/api/v1/ai/recommendations");}catch(e){SRV.ai=null;}
  return r;
};
const _origSrvDisconnect8=srvDisconnect;
srvDisconnect=function(reason){SRV.kpis=null;SRV.ai=null;_origSrvDisconnect8(reason);};

/* ---------------- MOD-KPI: серверный пересчёт из СУБД ---------------- */
function srvKpiRecalc(){
  if(!SRV.connected){toast("Пересчёт KPI из СУБД доступен в серверном режиме","warn","MOD-KPI");return;}
  srvApi("/api/v1/kpis/recalculate",{method:"POST"}).then(r=>{
    SRV.kpis={period:r.period,items:r.items};
    addAudit("Пересчет KPI (сервер)",r.total+" показателей · отклонений: "+r.breached.length,r.breached.length?"Отклонение от порогов":"Успех");
    if(r.breached.length){
      publish("kpi.threshold_breached","MOD-KPI","Сервер: отклонений "+r.breached.length+" ("+r.breached.map(b=>b.code).join(", ")+") — MOD-STIM применит эскалацию (Прил. 1.6)","warn");
      toast("Пересчёт KPI: "+r.breached.length+" отклонений от порогов. Опубликованы kpi.threshold_breached; MOD-STIM автоматически применяет санкцию «Эскалация отраслевым органам».","warn","MOD-KPI");
      // подтягиваем автоматически созданные меры в витрину
      srvApi("/api/v1/stims").then(s=>{STIMS.length=0;s.items.forEach(x=>STIMS.push(x));}).catch(()=>{});
    } else {
      toast("Пересчёт KPI выполнен на сервере: все показатели в норме (период "+r.period+").","ok","MOD-KPI");
    }
    showPage("kpi",true);
  }).catch(e=>toast("Сервер отклонил пересчёт KPI: "+(e.message||e),"err","MOD-KPI"));
}
const _origRenderKpi=RENDERERS.kpi;
RENDERERS.kpi=function(){
  if(!SRV.connected||!SRV.kpis||!SRV.kpis.items)return _origRenderKpi();
  const items=SRV.kpis.items;
  return pageHead("Показатели эффективности (KPI)",
   'Мониторинг целевых показателей (ТЗ п.2.3) — СЕРВЕРНЫЙ РЕЖИМ: calc-показатели пересчитываются из СУБД (охват реестра, точность верификации, портфель НИОКР, дедупликация через кооперацию), telemetry-показатели — реальные замеры служб MOD-REPORT/MOD-GEO. Отклонение от порога → kpi.threshold_breached → авто-санкция MOD-STIM (Прил. 1.6).',
   'MOD-KPI · период: '+SRV.kpis.period+' · источник: СУБД (сервер) · отклонений: '+items.filter(k=>!k.met).length,
   '<button class="btn ac" onclick="srvKpiRecalc()">⟳ Регламентный пересчёт</button>')+
  '<div class="cards c2">'+items.map(k=>{
   const pct=k.dir==="up"?Math.min(100,Math.round(k.cur/k.target*100)):Math.min(100,Math.round(k.target/Math.max(k.cur,0.1)*100));
   return '<div class="card kpi"><div class="corner"></div><div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px">'+
    '<div><div class="kv" style="font-size:22px;color:'+(k.met?"var(--green)":"var(--red)")+'">'+String(k.cur).replace(".",",")+" "+k.unit+'</div><div class="kt">'+esc(k.n)+' <span class="kbd">'+k.code+' · '+k.source+'</span></div></div>'+
    sparkSVG(k.hist&&k.hist.length?k.hist:[k.cur],k.met?"#34d399":"#f87171",96,30)+"</div>"+
    '<div class="kgoal">цель: '+esc(k.fmt)+' · <span style="color:'+(k.met?"var(--green)":"var(--red)")+'">'+(k.met?"✓ достигается":"✗ отклонение → kpi.threshold_breached")+'</span></div>'+
    '<div class="bar"><i style="width:'+pct+"%;background:"+(k.met?"var(--green)":"var(--red)")+'"></i></div></div>';}).join("")+"</div>"+
  '<div class="hint" style="margin-top:12px">История — последние 12 замеров · обновлено: '+((items[0]&&items[0].updated)||"—")+' · телеметрия KPI-4/KPI-8 накапливается службами сервера и применяется при пересчёте (нормативы ИВП-6).</div>';
};

/* ---------------- MOD-EXPERT: назначение и заключения на сервере ---------------- */
const _origAssignExpert=assignExpert;
assignExpert=function(id){
  if(!SRV.connected){_origAssignExpert(id);return;}
  if(!can("expert.assign")){deny("Назначение эксперта");return;}
  srvApi("/api/v1/expert/"+id+"/assign",{method:"POST"}).then(res=>{
    const v=EXPERT_QUEUE.find(x=>x.id===id);
    if(v){v.expert=res.expert;v.status=res.status;}
    publish("expert.assigned","MOD-EXPERT",id+" → эксперт "+res.expert+" (сервер: комиссия ≥ 3 чел., Прил. 3.7)");
    addAudit("Назначение эксперта (сервер)",id+" · "+res.expert,"Успех");
    toast("Эксперт назначен сервером: "+res.expert+". Формируется комиссия (≥ 3 чел.).","ok","MOD-EXPERT");
    showPage("expert",true);
  }).catch(e=>toast("Сервер: назначение отклонено — "+(e.message||e),"err","MOD-EXPERT"));
};
const _origConclude=conclude;
conclude=function(id){
  if(!SRV.connected){_origConclude(id);return;}
  if(!can("expert.approve")){deny("Выдача экспертного заключения");return;}
  srvApi("/api/v1/expert/"+id+"/conclude",{method:"POST",body:JSON.stringify({verdict:"Подтверждено"})}).then(res=>{
    const v=EXPERT_QUEUE.find(x=>x.id===id);
    if(v){v.status="done";}
    publish("expert.conclusion_ready","MOD-EXPERT",id+": заключение подписано ЭЦП ("+res.expert+") · серверная цепочка ИВП-1");
    addAudit("Выдача экспертного заключения (сервер)",id+" · вердикт: "+res.verdict,"Успех");
    if(res.org_verified){
      const o=orgById(res.org_verified);
      if(o)o.status="verified";
      publish("passport.verified","MOD-PASS",res.org_verified+" · экспертиза завершена, расхождения устранены (сервер)");
      (res.new_stims||[]).forEach(ns=>{if(!STIMS.find(x=>x.id===ns.id))STIMS.push(ns);});
    }
    toast("Заключение "+id+" готово (ЭЦП)."+(res.org_verified?" Организация "+res.org_verified+" верифицирована; MOD-DOC зарегистрировал заключение, MOD-STIM применил меры — всё через шину событий сервера.":""),"ok","MOD-EXPERT");
    showPage("expert",true);
  }).catch(e=>toast("Сервер: заключение не выдано — "+(e.message||e),"err","MOD-EXPERT"));
};

/* ---------------- MOD-DOC: подписание и карточки на сервере ---------------- */
const _origSignDoc=signDoc;
signDoc=function(id){
  if(!SRV.connected){_origSignDoc(id);return;}
  const d=DOCS.find(x=>x.id===id);
  if(d&&d.sign==="Проект"){
    srvApi("/api/v1/documents/"+id+"/sign",{method:"POST"}).then(res=>{
      d.sign=res.sign;d.version=res.version;
      publish("doc.status_changed","MOD-DOC",id+": Проект → "+res.sign+" (неизменяемый поток статусов)");
      addAudit("Подписание документа (сервер)",id+" → "+res.sign,"Успех");
      toast("Документ "+id+" направлен на подписание: статус «"+res.sign+"» (версия "+res.version+"). Поток статусов неизменяем: Проект → На подписании → Подписан (ЭЦП) → Утверждён.","ok","MOD-DOC");
      showPage("doc",true);
    }).catch(e=>toast("Сервер: "+(e.message||e),"err","MOD-DOC"));
  }else{
    srvApi("/api/v1/documents/"+id+"/card").then(res=>{
      publish("doc.accessed","MOD-DOC",id+" · просмотр карточки (серверный аудит)");
      addAudit("Просмотр карточки документа (сервер)",id+" · "+res.t,"Успех");
      toast("Карточка "+id+": «"+res.t+"» · статус: "+res.sign+" · версия: "+res.version+(res.signature?" · подпись: "+res.signature.slice(0,28)+"…":"")+(res.signed_by?" · подписал: "+res.signed_by:""),"ok","MOD-DOC");
    }).catch(e=>{addAudit("Просмотр карточки документа",id,"Успех");toast("Карточка документа "+id+" (локально): "+(d?d.t:"—"),"ok","MOD-DOC");});
  }
};

/* ---------------- MOD-AI: прогнозный цикл ИВП-7 на сервере ---------------- */
const _origRunAI=runAI;
runAI=function(){
  if(!SRV.connected){_origRunAI();return;}
  if(!can("ai.run")){deny("Запуск прогнозного цикла ИИ");return;}
  toast("Прогнозный цикл ИВП-7 выполняется на сервере: tech-gap, риски этапов, рекомендации…","","MOD-AI");
  srvApi("/api/v1/ai/run",{method:"POST"}).then(res=>
    srvApi("/api/v1/ai/recommendations").then(latest=>{
      SRV.ai=latest;SRV.ai.run_id=res.run_id;SRV.ai.model=res.model;
      publish("ai.recommendations_ready","MOD-AI","Прогнозный цикл "+res.run_id+": "+res.tech_gaps.gaps.length+" tech-gap, "+res.fail_risk.length+" рисков этапов, "+res.recommendations.length+" рекомендаций (conf ≥ 0.7) · модель "+res.model);
      addAudit("Запуск ИИ-прогнозирования (сервер)",res.run_id+" · ИВП-7 · модель "+res.model,"Успех");
      toast("Прогнозный цикл "+res.run_id+" выполнен на сервере (модель "+res.model+"). Рекомендаций опубликовано: "+res.recommendations.length+" (confidence ≥ 0.7).","ok","MOD-AI");
      showPage("ai",true);
    })).catch(e=>toast("Сервер: прогнозный цикл отклонён — "+(e.message||e),"err","MOD-AI"));
};
const _origAcceptRec=acceptRec;
acceptRec=function(btn){
  const box=btn.closest?btn.closest("[data-rid]"):null;
  const rid=box?box.getAttribute("data-rid"):null;
  if(!SRV.connected||!rid){_origAcceptRec(btn);return;}
  if(!can("ai.accept")){deny("Принятие ИИ-рекомендации");return;}
  srvApi("/api/v1/ai/recommendations/"+rid+"/accept",{method:"POST"}).then(res=>{
    btn.textContent="✓ Принято";btn.disabled=true;btn.className="btn sm";
    addAudit("Принятие ИИ-рекомендации (сервер)",rid+" · "+res.t.slice(0,60),"Успех");
    publish("ai.recommendation_accepted","MOD-AI","Рекомендация "+rid+" принята оператором "+(SRV.fio||"")+" (WORM-аудит сервера)");
    toast("Рекомендация принята и зарегистрирована в WORM-аудите сервера.","ok","MOD-AI");
  }).catch(e=>toast("Сервер: "+(e.message||e),"err","MOD-AI"));
};
const _origRenderAi=RENDERERS.ai;
RENDERERS.ai=function(){
  if(!SRV.connected||!SRV.ai)return _origRenderAi();
  const A=SRV.ai,tg=A.tech_gaps||{gaps:[],threshold:75},gaps=tg.gaps||[];
  const cols=["#f87171","#fbbf24","#34d399","#a78bfa","#38bdf8","#f472b6"];
  const recs=A.recommendations||[];
  return pageHead("ИИ-рекомендации и прогнозирование",
   'Предиктивная аналитика (ИВП-7) — СЕРВЕРНАЯ модель '+A.model+': прогноз технологических разрывов (сходимость компетенций отрасли к порогу суверенитета '+tg.threshold+'%), детерминированная оценка риска срыва контрольных точек, рекомендации по правилам (публикация при confidence ≥ 0.7). Все расчёты — по реальным данным СУБД (реестр, портфель НИОКР, паспорта, геоаналитика).',
   'MOD-AI · прогон: '+(A.run_id||"— (живой пересчёт)")+' · снимок данных DWH от '+today()+' · источник: сервер',
   '<button class="btn ac" onclick="runAI()">▶ Запустить прогнозный цикл</button>')+
  '<div class="cards" style="grid-template-columns:1.2fr 1fr;margin-bottom:14px">'+
   '<div class="card"><h3><span class="hico">◮</span> Прогноз технологических разрывов (6 периодов)</h3>'+
    (gaps.length?lineSVG(gaps.map((g,i)=>({vals:g.prog,col:cols[i%cols.length]})),{h:230,min:20,max:100,xlabel:"— динамика среднего уровня компетенций отрасли, % · целевой порог суверенитета "+tg.threshold+"%"}):'<div class="empty-note">Нет данных компетенций</div>')+
    '<div style="display:flex;gap:14px;flex-wrap:wrap;margin-top:8px">'+gaps.map((g,i)=>'<span style="font-size:11px;color:var(--tx2)"><span style="color:'+cols[i%cols.length]+'">━━</span> '+esc(g.n)+' <b class="mono">'+Math.round(g.conf*100)+'%</b>'+(g.sovereign_by!=null?' · порог: период '+g.sovereign_by:'')+'</span>').join("")+"</div></div>"+
   '<div class="card"><h3><span class="hico">⚠</span> Риск срыва контрольных точек, % (серверная модель)</h3>'+
    (A.fail_risk||[]).map(f=>'<div style="display:flex;gap:8px;align-items:center;font-size:11.5px;margin:5px 0"><span class="mono" style="color:var(--acc2);width:26px">'+f.id+'</span><span style="flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--tx2)">'+esc(f.name)+' <span class="hint">'+esc(f.org||"")+(f.factors&&f.factors.overdue_days?" · просрочка "+f.factors.overdue_days+" дн":"")+'</span></span><div class="progress-lg" style="width:80px"><i style="width:'+f.risk+"%;background:"+(f.risk>60?"var(--red)":f.risk>35?"var(--gold)":"var(--green)")+'"></i></div><b class="mono" style="width:30px;color:'+(f.risk>60?"var(--red)":f.risk>35?"var(--gold)":"var(--green)")+'">'+f.risk+"%</b></div>").join("")+
    '<div class="hint" style="margin-top:9px">Факторы (детерминированно, воспроизводимо для аудита): отставание TRL ×22 + стадия ×2 + (индекс риска − 20) + просрочка плана /15 дн.</div></div></div>'+
  '<div class="card"><h3><span class="hico">✦</span> Рекомендации системы (публикуются при confidence ≥ 0.7)</h3>'+
   (recs.length?recs.map(r=>'<div data-rid="'+r.rid+'" style="display:flex;gap:11px;align-items:center;padding:9px 4px;border-bottom:1px dashed var(--line)"><span class="badge b-vio">'+Math.round(r.conf*100)+'%</span><span style="flex:1;font-size:13px">'+esc(r.t)+'</span><span class="kbd">'+r.m+"</span>"+(r.status==="accepted"?'<span class="badge b-green">✓ Принято'+(r.decided_by?" · "+esc(r.decided_by):"")+"</span>":'<button class="btn sm gr" onclick="acceptRec(this)">Принять</button>')+"</div>").join("")
    :'<div class="empty-note">Прогнозный цикл ещё не выполнялся — нажмите «Запустить прогнозный цикл» (рекомендации появятся после прогона)</div>')+
   '<div class="hint" style="margin-top:9px">Точность прогноза сроков ≥ 80% (критерий ИВП-7). Принятые рекомендации регистрируются в WORM-аудите сервера и рассылаются службой уведомлений ядра.</div></div>';
};
