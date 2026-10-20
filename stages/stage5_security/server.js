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
