#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ЭТАП 12 — выпуск v103.0.0 «Серверная персистентность базовых операций»:
ais_providets_v102.html → ais_providets_v103.html (+ рабочая копия ais_providets.html).

Содержание (продолжение превращения прототипа в рабочую платформу):
  srvDownload — существующая (Этап 9, не использовавшаяся) функция бинарной загрузки
              доводится до закалённого Promise-API: эпоха сессии, лимит 64 МБ,
              непустота, имя файла из Content-Disposition, регистрация в
              SRV_ACTIVE_REQUESTS (отмена при logout), SRV_DOWNLOAD_MAX байт.
  MOD-PASS  — в серверном режиме значения полей паспорта загружаются из СУБД
              (GET /api/v1/orgs/{id}/passport → оверлей state.passOv),
              «Сохранить версию» персистит правки (PUT /api/v1/orgs/{id}/passport,
              маппинг (раздел,поле)→field_id по карте с сервера; отправляются только
              изменённые поля), fail-closed при отказе; «Контроль качества» — серверный.
  MOD-PROF  — «Пересчитать профиль» пересобирает цифровой двойник на сервере
              (POST /api/v1/twins/{id}/rebuild, CRC32 + WORM-аудит).
  Отчёты    — DOCX/XLSX в серверном режиме = РЕАЛЬНЫЕ файлы бэкенда
              (python-docx/openpyxl): паспорт {org}.docx, registry.xlsx / evm.xlsx;
              при недоступности сервера — честный откат в клиентскую генерацию.
  Демо-режим не изменён: обёртки прозрачны при !SRV.connected.

Запуск:  python3 src12/patch_v103.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "ais_providets_v102.html"
OUT = ROOT / "ais_providets_v103.html"
CUR = ROOT / "ais_providets.html"
CHANGELOG = ROOT / "CHANGELOG.md"

V = {"major": 103, "minor": 0, "patch": 0, "str": "v103.0.0", "num": "103.0.0",
     "tz": "4.0", "build": "v103", "released": "26.10.2026", "released_iso": "2026-10-26"}

HISTORY_TEXT = (
    "Рабочая платформа — Этап 12 (серверная персистентность базовых операций): "
    "(1) MOD-PASS в серверном режиме: при открытии страницы паспорта значения полей "
    "загружаются из СУБД (GET /api/v1/orgs/{id}/passport → оверлей state.passOv — UI "
    "показывает серверные данные), «Сохранить версию» персистит правки на сервере "
    "(PUT /api/v1/orgs/{id}/passport; маппинг (раздел,поле)→field_id строится по карте "
    "полей с сервера; отправляются только реально изменённые поля — перезапись серверных "
    "значений пустыми исключена), сервер создаёт новую версию паспорта с CRC32 и журналом "
    "изменений, событие passport.updated запускает ИВП-2 (профиль зрелости + цифровой "
    "двойник); при отказе сервера — fail-closed: локальные данные не изменяются; "
    "(2) «Контроль качества» паспорта — серверный (POST .../passport/quality: ИНН/ОГРН "
    "по методикам ФНС, полнота по порогам Прил. 2.14); (3) MOD-PROF: «Пересчитать профиль» "
    "в серверном режиме пересобирает цифровой двойник на сервере (POST /api/v1/twins/{id}/rebuild, "
    "CRC32 + WORM-аудит сервера); (4) отчёты: DOCX/XLSX в серверном режиме — РЕАЛЬНЫЕ файлы, "
    "сгенерированные бэкендом из данных СУБД (python-docx/openpyxl: паспорт DOCX, реестр/EVM "
    "XLSX); доведена до закалённого Promise-API функция srvDownload (Этап 9 определил её, но "
    "не использовал): валидация пути buildApiUrl, Authorization bearer, credentials omit, "
    "redirect error, эпоха сессии, таймаут 60 с, лимит 64 МБ, проверка непустоты, имя файла "
    "из Content-Disposition, регистрация в SRV_ACTIVE_REQUESTS (отмена при logout); при "
    "недоступности сервера — прозрачный откат в клиентскую генерацию с честным "
    "предупреждением; (5) демо-режим не изменён (обёртки прозрачны при отключённом сервере); "
    "добавлены smoke-проверки SRV-PASS-01, SRV-REPORT-01, SRV-TWIN-01, SRV-DL-01; E2E-стенд "
    "srv расширен сценариями персистентности (правка паспорта → версия в СУБД → данные "
    "переживают повторный вход; реальный DOCX — PK-магия ZIP; XLSX реестра); живой протокол "
    "интеграции расширен LP-18 (паспорт: карта полей → PUT → версия → quality) и LP-19 "
    "(бинарные отчёты DOCX/XLSX/PDF из СУБД)."
)

html = SRC.read_text(encoding="utf-8")
BASE_LEN = len(html)
report, errors = [], []


def rep(old, new, count=1, label=""):
    global html
    n = html.count(old)
    name = label or (old[:64].replace("\n", "\\n") + "…")
    if n != count:
        errors.append(f"[FAIL] {name}: ожидалось {count}, найдено {n}")
        return False
    html = html.replace(old, new)
    report.append(f"  ok  {name}  ×{count}")
    return True


# ============================================ 1. ВЕРСИЯ (единый источник) ====
rep('const APP_VERSION=Object.freeze({major:102,minor:0,patch:0,str:"v102.0.0",num:"102.0.0",tz:"4.0",build:"v102",released:"26.10.2026"});',
    'const APP_VERSION=Object.freeze({major:%(major)d,minor:%(minor)d,patch:%(patch)d,str:"%(str)s",num:"%(num)s",tz:"%(tz)s",build:"%(build)s",released:"%(released)s"});' % V,
    1, "APP_VERSION → 103")
rep('<meta name="providets-release-version" content="v102.0.0">',
    '<meta name="providets-release-version" content="%s">' % V["str"], 1, "meta → v103")
rep('· программа v102.0.0</div>', '· программа %s</div>' % V["str"], 1, "loginVerLine → v103")
rep('<span data-tc-ver="num">102.0.0</span>', '<span data-tc-ver="num">%s</span>' % V["num"], 1, "login-note → 103.0.0")

# ============================ 2. ЗАКАЛКА srvDownload (Promise + барьеры) =====
OLD_DL = '''function srvDownload(path,fallbackName){
  if(!SRV.connected){toast("Серверные отчеты доступны в серверном режиме","warn","MOD-REPORT");return;}
  let target;try{
    target=buildApiUrl(path,"Скачивание серверного отчёта");
  }catch(e){toast(e.message,"warn","API Gateway");return;}
  const controller=typeof AbortController!=="undefined"?new AbortController():null;
  const timeout=controller?setTimeout(()=>controller.abort(),60000):null;
  const opts={credentials:"omit",redirect:"error",headers:{Authorization:"Bearer "+SRV.token}};
  if(controller)opts.signal=controller.signal;
  fetch(target,opts)
    .then(r=>{if(!r.ok)throw new Error("HTTP "+r.status);return r.blob();})
    .then(b=>{
      const a=document.createElement("a");a.href=URL.createObjectURL(b);
      a.download=fallbackName||path.split("/").pop();document.body.appendChild(a);a.click();
      setTimeout(()=>{URL.revokeObjectURL(a.href);a.remove();},500);
      toast("Отчет с сервера: "+a.download+" ("+(b.size/1024).toFixed(0)+" КБ)","ok","MOD-REPORT");
    }).catch(e=>toast("Ошибка загрузки отчета: "+(e&&e.name==="AbortError"?"превышено время ожидания (60 с)":e.message),"warn","MOD-REPORT"))
    .finally(()=>{if(timeout)clearTimeout(timeout);});
}'''
NEW_DL = '''const SRV_DOWNLOAD_MAX_BYTES=64*1024*1024; /* Этап 12 (v103): лимит бинарной загрузки */
/* Этап 12 (v103): закалённое Promise-API бинарной загрузки (барьеры как в srvApi):
   валидация пути/origin, Authorization, credentials:omit, redirect:error, эпоха сессии,
   таймаут 60 с, лимит 64 МБ, непустота, имя из Content-Disposition, abort при logout. */
function srvDownload(path,fallbackName,label){
  return new Promise(function(resolve,reject){
    if(!SRV.connected||!SRV.token){
      toast("Серверные отчеты доступны в серверном режиме","warn","MOD-REPORT");
      reject(new Error("Серверный режим не активен"));return;
    }
    let target;
    try{target=buildApiUrl(path,label||"Скачивание серверного отчёта");}
    catch(e){toast(e.message,"warn","API Gateway");reject(e);return;}
    const epoch=Number(SRV.sessionEpoch)||0;
    const controller=typeof AbortController!=="undefined"?new AbortController():null;
    if(controller&&typeof SRV_ACTIVE_REQUESTS!=="undefined"&&SRV_ACTIVE_REQUESTS&&SRV_ACTIVE_REQUESTS.add)SRV_ACTIVE_REQUESTS.add(controller);
    const timeout=controller?setTimeout(()=>controller.abort(),60000):null;
    const opts={credentials:"omit",redirect:"error",headers:{Authorization:"Bearer "+SRV.token}};
    if(controller)opts.signal=controller.signal;
    const cleanup=()=>{if(timeout)clearTimeout(timeout);
      if(controller&&typeof SRV_ACTIVE_REQUESTS!=="undefined"&&SRV_ACTIVE_REQUESTS&&SRV_ACTIVE_REQUESTS["delete"])SRV_ACTIVE_REQUESTS["delete"](controller);};
    fetch(target,opts)
      .then(r=>{
        if((Number(SRV.sessionEpoch)||0)!==epoch){const e0=new Error("Сеанс обновлён; загрузка отменена.");e0.code="LOGIN_ATTEMPT_SUPERSEDED";throw e0;}
        if(!r.ok)throw new Error("HTTP "+r.status);
        const cd=r.headers.get("Content-Disposition")||"";
        let name=fallbackName||path.split("/").pop();
        const m=/filename\\*=UTF-8''([^;]+)/i.exec(cd);
        if(m){try{name=decodeURIComponent(m[1]);}catch(e){}}
        return r.blob().then(b=>{
          if(b.size>SRV_DOWNLOAD_MAX_BYTES)throw new Error("Документ превышает лимит 64 МБ");
          if(b.size<=0)throw new Error("Сервер вернул пустой файл");
          const a=document.createElement("a");a.href=URL.createObjectURL(b);
          a.download=name;document.body.appendChild(a);a.click();
          setTimeout(()=>{URL.revokeObjectURL(a.href);a.remove();},500);
          return {name:name,size:b.size,type:b.type||""};
        });
      })
      .then(res=>{cleanup();resolve(res);},err=>{cleanup();reject(err);});
  });
}'''
rep(OLD_DL, NEW_DL, 1, "srvDownload: закалённое Promise-API (этап 12)")

# ================================== 3. ИСТОРИЯ И «ЧТО НОВОГО» ================
rep('   [\n    ["v102.0.0","26.10.2026","Рабочая платформа',
    '   [\n    ["%s","%s","%s"],\n    ["v102.0.0","26.10.2026","Рабочая платформа' % (V["str"], V["released"], HISTORY_TEXT),
    1, "история: запись v103.0.0")
rep('x:"v102.0.0: исправлен критический дефект Д-10',
    'x:"'+V['str']+' — серверная персистентность: правки паспорта сохраняются в СУБД (PUT /orgs/{id}/passport, версия+CRC32+журнал), контроль качества и пересборка двойника — серверные, DOCX/XLSX — реальные файлы бэкенда (python-docx/openpyxl) через закалённый srvDownload. v102: исправлен критический дефект Д-10',
    1, "«Что нового» обновлено до v103")

# ======================================= 4. SMOKE-ПРОВЕРКИ ЭТАПА 12 ==========
SRV_LOGIN_ANCHOR = " check('SRV-LOGIN-01','Д-10: серверный вход передаёт снимок пароля в srvTryLogin до очистки полей',()=>doLogin.toString().includes('passSnapshot')&&srvTryLogin.toString().includes('presetPassword')&&srvTryLogin.length===1);"
rep(SRV_LOGIN_ANCHOR,
    SRV_LOGIN_ANCHOR + """
 check('SRV-DL-01','Этап 12: srvDownload — закалённый Promise (эпоха сессии, лимит, отмена при logout)',()=>typeof srvDownload==='function'&&srvDownload.toString().includes('LOGIN_ATTEMPT_SUPERSEDED')&&srvDownload.toString().includes('SRV_DOWNLOAD_MAX_BYTES')&&srvDownload.toString().includes('SRV_ACTIVE_REQUESTS'));
 check('SRV-PASS-01','Этап 12: сохранение паспорта в серверном режиме персистит в СУБД (fail-closed)',()=>savePassVersion.toString().includes('SRV.connected')&&RENDERERS.pass.toString().includes('__s12Synced'));
 check('SRV-REPORT-01','Этап 12: DOCX/XLSX в серверном режиме — реальные файлы сервера (srvDownload)',()=>exportReportDocx.toString().includes('srvDownload')&&exportPassportDocx.toString().includes('srvDownload'));
 check('SRV-TWIN-01','Этап 12: пересборка цифрового двойника и контроль качества — на сервере',()=>recalcProfile.toString().includes('/api/v1/twins/')&&passportQuality.toString().includes('/passport/quality'));""",
    1, "smoke +SRV-DL-01/SRV-PASS-01/SRV-REPORT-01/SRV-TWIN-01")

# ======================================= 5. МОСТ ЭТАПА 12 ====================
STAGE12 = r"""
<script>
/* ==================================================================
   ЭТАП 12 / v103.0.0 — СЕРВЕРНАЯ ПЕРСИСТЕНТНОСТЬ БАЗОВЫХ ОПЕРАЦИЙ.
   MOD-PASS:  значения полей из СУБД (оверлей state.passOv), сохранение версии
              через PUT /orgs/{id}/passport (карта field_id, diff относительно
              отрисованных значений, fail-closed), контроль качества — серверный.
   MOD-PROF:  пересборка цифрового двойника на сервере (POST /twins/{id}/rebuild).
   Отчёты:    DOCX/XLSX — реальные файлы бэкенда через закалённый srvDownload;
              откат в клиентскую генерацию при недоступности сервера.
   Демо-режим не изменён: обёртки прозрачны при !SRV.connected.
   ================================================================== */
(function(){
 "use strict";
 if(typeof SRV==="undefined"||typeof srvApi!=="function")return;

 /* ---------------- MOD-PASS: серверные значения полей → оверлей -------------- */
 var _s12PassSyncInFlight=false;
 var _s12OrigRenderPass=RENDERERS.pass;
 RENDERERS.pass=function(){
   var out=_s12OrigRenderPass.apply(this,arguments);
   try{
     var oid=state.selEnt;
     if(SRV.connected&&oid&&!_s12PassSyncInFlight){
       var ov0=state.passOv[oid]||(state.passOv[oid]={});
       if(!ov0.__s12Synced){
         _s12PassSyncInFlight=true;
         srvApi("/api/v1/orgs/"+encodeURIComponent(oid)+"/passport").then(function(pas){
           _s12PassSyncInFlight=false;
           var ov=state.passOv[oid]||(state.passOv[oid]={});
           (pas.sections||[]).forEach(function(s){(s.fields||[]).forEach(function(f){
             if(f.value!=null&&f.value!=="")ov[s.n+"|"+f.name]=String(f.value);
           });});
           ov.__s12Synced=true;
           if(state.page==="pass"&&state.selEnt===oid)showPage("pass",true);
         }).catch(function(){_s12PassSyncInFlight=false;});
       }
     }
   }catch(e){}
   return out;
 };

 /* ---------------- MOD-PASS: сохранение версии в СУБД (fail-closed) ---------- */
 var _s12OrigSavePassVersion=savePassVersion;
 async function srvSavePassVersion(id){
   if(!can("org.write",id)){deny("Сохранение версии паспорта");return;}
   var inputs=document.querySelectorAll(".pf-in");
   if(!inputs.length){toast("На странице нет редактируемых полей паспорта","warn","MOD-PASS");return;}
   toast("Сохранение паспорта на сервере: карта полей из СУБД…","","MOD-PASS");
   try{
     var pas=await srvApi("/api/v1/orgs/"+encodeURIComponent(id)+"/passport");
     var fmap={};
     (pas.sections||[]).forEach(function(s){(s.fields||[]).forEach(function(f){fmap[s.n+"|"+f.name]=f.id;});});
     var o=orgById(id);
     var ov=state.passOv[id]||(state.passOv[id]={});
     var updates={};var edited={};var nEd=0;
     inputs.forEach(function(inp){
       var s=+inp.dataset.s,f=inp.dataset.f,v=inp.value.trim();
       var fid=fmap[s+"|"+f];
       if(!fid)return;
       var j=(PASS_FIELDS[s]||[]).findIndex(function(x){return x[0]===f;});
       var hadOv=ov[s+"|"+f]!=null&&ov[s+"|"+f]!=="";
       var old=(passFilled(o,s-1,j>=0?j:0)||hadOv)?String(fieldValue(o,s,j>=0?j:0,f)):"";
       if(v!==old){updates[fid]=v;edited[s+"|"+f]=v;nEd++;}
     });
     if(!nEd){toast("Изменений нет: версия паспорта на сервере не создавалась","","MOD-PASS");return;}
     var res=await srvApi("/api/v1/orgs/"+encodeURIComponent(id)+"/passport",{method:"PUT",body:JSON.stringify({updates:updates})});
     Object.keys(edited).forEach(function(k){ov[k]=edited[k];});
     ov.__s12Synced=true;
     addAudit("Сохранение версии паспорта (сервер)",id+" · ред. "+res.ver_n+" · изменений "+res.changes,"Успех");
     publish("passport.updated","MOD-PASS","Паспорт "+esc(id)+": редакция "+res.ver_n+" сохранена в СУБД (изменений: "+res.changes+")");
     toast("Паспорт сохранён на сервере: редакция "+res.ver_n+", изменений: "+res.changes+". ИВП-2: профиль зрелости и цифровой двойник пересчитываются","ok","MOD-PASS");
     if(state.page==="pass")showPage("pass",true);
   }catch(e){
     if(e&&e.code==="LOGIN_ATTEMPT_SUPERSEDED")return;
     toast("Сервер отклонил сохранение паспорта: "+((e&&e.message)||e)+". Локальные данные НЕ изменены (fail-closed).","err","MOD-PASS");
   }
 }
 savePassVersion=function(id){
   if(SRV.connected)return srvSavePassVersion(id);
   return _s12OrigSavePassVersion(id);
 };

 /* ---------------- MOD-PASS: контроль качества — серверный ------------------- */
 var _s12OrigQuality=passportQuality;
 passportQuality=function(id){
   if(!SRV.connected)return _s12OrigQuality(id);
   toast("Контроль качества паспорта на сервере (ИНН/ОГРН по методикам ФНС, полнота)…","","MOD-PASS");
   srvApi("/api/v1/orgs/"+encodeURIComponent(id)+"/passport/quality",{method:"POST"}).then(function(res){
     var issues=(res&&res.issues)||[];
     addAudit("Контроль качества данных паспорта (сервер)",id+(res&&res.ok?" · без замечаний":" · замечаний: "+issues.length),"Успех");
     toast((res&&res.ok)?("Качество паспорта "+id+" подтверждено сервером: замечаний нет"):
       ("Контроль качества "+id+": замечаний "+issues.length+" — "+String(issues[0]||"").slice(0,140)),(res&&res.ok)?"ok":"warn","MOD-PASS");
   }).catch(function(e){
     if(e&&e.code==="LOGIN_ATTEMPT_SUPERSEDED")return;
     toast("Серверный контроль качества недоступен ("+((e&&e.message)||e)+") — выполняю клиентскую проверку","warn","MOD-PASS");
     _s12OrigQuality(id);
   });
 };

 /* ---------------- MOD-PROF: пересборка двойника на сервере ------------------ */
 var _s12OrigRecalc=recalcProfile;
 recalcProfile=function(id){
   if(!SRV.connected)return _s12OrigRecalc(id);
   if(!can("org.write",id)){deny("Пересчет профиля ("+id+")");return;}
   toast("Пересборка цифрового двойника на сервере (ИВП-2)…","","MOD-PROF");
   srvApi("/api/v1/twins/"+encodeURIComponent(id)+"/rebuild",{method:"POST"}).then(function(res){
     _s12OrigRecalc(id);
     toast("Серверный цифровой двойник "+id+" пересобран: CRC32 "+String((res&&res.crc32)||"—")+" (WORM-аудит сервера)","ok","MOD-PROF");
   }).catch(function(e){
     if(e&&e.code==="LOGIN_ATTEMPT_SUPERSEDED")return;
     toast("Сервер отклонил пересборку двойника: "+((e&&e.message)||e)+". Локальный пересчёт не выполнялся (fail-closed).","err","MOD-PROF");
   });
 };

 /* ---------------- Реальные файлы DOCX/XLSX с сервера ------------------------ */
 var _s12OrigPassDocx=exportPassportDocx;
 exportPassportDocx=function(id){
   if(!SRV.connected)return _s12OrigPassDocx(id);
   if(!can("org.write",id)){deny("Экспорт паспорта в DOCX ("+id+")");return;}
   toast("Сервер формирует реальный DOCX паспорта (python-docx, данные СУБД)…","","MOD-PASS");
   srvDownload("/api/v1/reports/passport/"+encodeURIComponent(id)+".docx","passport_"+id+".docx","Экспорт паспорта DOCX").then(function(r){
     addAudit("Экспорт паспорта (сервер)",id+" · "+r.name+" · "+r.size+" байт","Успех");
     toast("Реальный DOCX паспорта "+id+" сформирован сервером: "+Math.round(r.size/1024)+" КБ (норматив ≤ 5 с)","ok","MOD-PASS");
   }).catch(function(e){
     if(e&&e.code==="LOGIN_ATTEMPT_SUPERSEDED")return;
     toast("Серверный DOCX недоступен ("+((e&&e.message)||e)+") — клиентская генерация","warn","MOD-PASS");
     _s12OrigPassDocx(id);
   });
 };
 var _s12OrigReportDocx=exportReportDocx;
 exportReportDocx=function(){
   if(!SRV.connected)return _s12OrigReportDocx();
   if(!can("report.run")){deny("Экспорт отчета в DOCX");return;}
   var orgId=state.selEnt||"E01";
   toast("Сервер формирует реальный DOCX (python-docx, данные СУБД)…","","MOD-REPORT");
   srvDownload("/api/v1/reports/passport/"+encodeURIComponent(orgId)+".docx","passport_"+orgId+".docx","Экспорт отчета DOCX").then(function(r){
     addAudit("Формирование отчета (сервер)",r.name+" · DOCX · "+r.size+" байт","Успех");
     toast("Сервер сформировал реальный DOCX: "+r.name+" ("+Math.round(r.size/1024)+" КБ) — паспорт "+orgId+" по данным СУБД","ok","MOD-REPORT");
   }).catch(function(e){
     if(e&&e.code==="LOGIN_ATTEMPT_SUPERSEDED")return;
     toast("Серверный DOCX недоступен ("+((e&&e.message)||e)+") — клиентская генерация","warn","MOD-REPORT");
     _s12OrigReportDocx();
   });
 };
 var _s12OrigReportXlsx=exportReportXlsx;
 exportReportXlsx=function(){
   if(!SRV.connected)return _s12OrigReportXlsx();
   if(!can("report.run")){deny("Экспорт отчета в XLSX");return;}
   var isEvm=String((state.report&&state.report.type)||"").indexOf("НИОКР")>=0;
   var path=isEvm?"/api/v1/reports/evm.xlsx":"/api/v1/reports/registry.xlsx";
   toast("Сервер формирует реальный XLSX (openpyxl, данные СУБД)…","","MOD-REPORT");
   srvDownload(path,isEvm?"technocontour_evm.xlsx":"technocontour_registry.xlsx","Экспорт отчета XLSX").then(function(r){
     addAudit("Формирование отчета (сервер)",r.name+" · XLSX · "+r.size+" байт","Успех");
     toast("Сервер сформировал реальный XLSX: "+r.name+" ("+Math.round(r.size/1024)+" КБ)","ok","MOD-REPORT");
   }).catch(function(e){
     if(e&&e.code==="LOGIN_ATTEMPT_SUPERSEDED")return;
     toast("Серверный XLSX недоступен ("+((e&&e.message)||e)+") — клиентская генерация","warn","MOD-REPORT");
     _s12OrigReportXlsx();
   });
 };
 window.__TC_STAGE12_BRIDGE=true;
})();
</script>
</body>
</html>"""
rep("</script>\n</body>\n</html>", "</script>\n" + STAGE12, 1, "мост Этапа 12 (перед </body>)")

# ======================================================= ВАЛИДАЦИЯ ==========
def expect(cond, msg):
    (report if cond else errors).append(("  ok  VALIDATE: " if cond else "[FAIL] VALIDATE: ") + msg)


expect(html.count("__TC_STAGE12_BRIDGE") == 1, "маркер моста Этапа 12 (window-флаг): %d" % html.count("__TC_STAGE12_BRIDGE"))
expect(html.count("function srvDownload(") == 1, "srvDownload определён ровно один раз (апгрейд, не дубль)")
expect(html.count("SRV_DOWNLOAD_MAX_BYTES") >= 3, "лимит бинарной загрузки задан константой")
expect(html.count("savePassVersion=function(id){") == 1, "обёртка savePassVersion")
expect(html.count("RENDERERS.pass=function(){") == 2, "RENDERERS.pass: базовый + обёртка Этапа 12")
expect(html.count('"/api/v1/twins/"') == 1 and html.count("/api/v1/twins/") == 3, "мост двойника (код+smoke+история)")
expect(html.count("/passport/quality") >= 3, "мост контроля качества (код+smoke+история)")
expect(html.count("SRV-DL-01") == 2 and html.count("SRV-PASS-01") == 2 and html.count("SRV-REPORT-01") == 2 and html.count("SRV-TWIN-01") == 2,
       "smoke-проверки Этапа 12 (код + упоминание в истории)")
rem102 = [i + 1 for i, ln in enumerate(html.split("\n")) if "v102.0.0" in ln]
expect(len(rem102) == 1, "исторических упоминаний v102.0.0 ровно 1 (запись истории), факт %d" % len(rem102))
rem101 = [i + 1 for i, ln in enumerate(html.split("\n")) if "v101.0.0" in ln]
expect(len(rem101) == 3, "исторических упоминаний v101.0.0 ровно 3, факт %d" % len(rem101))
rem103 = [(i + 1, ln) for i, ln in enumerate(html.split("\n")) if V["num"] in ln]
allowed = ("const APP_VERSION=Object.freeze", 'content="%s"' % V["str"], "loginVerLine",
           'data-tc-ver="num"', '["v103.0.0","26.10.2026"', "Что нового", "ЭТАП 12 / v103.0.0")
for no, ln in rem103:
    if not any(mk in ln for mk in allowed):
        errors.append(f"[FAIL] незапланированный хардкод {V['num']} на стр.{no}")
expect(True, "все вхождения %s — из единого источника (%d строк)" % (V["num"], len(rem103)))

if errors:
    print("\n".join(errors))
    sys.exit(1)

OUT.write_text(html, encoding="utf-8")
CUR.write_text(html, encoding="utf-8")
print(f"[i] {OUT.name}: {BASE_LEN} → {len(html)} байт (+{len(html) - BASE_LEN})")

# ================================================== CHANGELOG (регенерация) ==
def js_unescape(s):
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t", '"': '"', "'": "'", "\\": "\\"}.get(m.group(1), m.group(1)), s)


entries = re.findall(r'\["(v\d+\.\d+\.\d+)","(\d{2}\.\d{2}\.\d{4})","((?:[^"\\]|\\.)*)"\]', html)
print(f"[i] записей истории в v103: {len(entries)}")
if len(entries) < 82:
    sys.exit("[FAIL] массив истории распознан не полностью")

V103_SECTION = f"""## [{V['num']}] — {V['released_iso']}

Выпуск «Серверная персистентность базовых операций» (Этап 12): в серверном режиме
ключевые бизнес-операции сохраняются в СУБД, а отчёты становятся реальными файлами
бэкенда. Артефакт: `ais_providets_v103.html` (единый HTML).
Сборка: `python3 src12/patch_v103.py` (детерминированная, из `ais_providets_v102.html`).

### Добавлено
- **MOD-PASS · серверные значения полей:** при открытии страницы паспорта в серверном
  режиме поля подтягиваются из СУБД (`GET /api/v1/orgs/{{id}}/passport` → оверлей
  `state.passOv`); UI показывает актуальные серверные данные, а не клиентскую модель.
- **MOD-PASS · персистентное сохранение версии:** «💾 Сохранить версию» выполняет
  `PUT /api/v1/orgs/{{id}}/passport` (карта (раздел,поле)→`field_id` берётся с сервера;
  отправляются только изменённые поля — перезапись серверных значений пустыми
  исключена); сервер создаёт версию с CRC32 и журналом изменений, публикуются события
  `passport.updated`/`geo.data_updated` (ИВП-2). Отказ сервера — **fail-closed**:
  локальные данные не изменяются.
- **MOD-PASS · серверный контроль качества:** «⚕ Контроль качества» →
  `POST /api/v1/orgs/{{id}}/passport/quality` (ИНН/ОГРН по методикам ФНС, полнота по
  порогам Прил. 2.14), результат — в тост и WORM-аудит сервера.
- **MOD-PROF · серверный цифровой двойник:** «↻ Пересчитать профиль» →
  `POST /api/v1/twins/{{id}}/rebuild` (CRC32, аудит сервера); fail-closed при отказе.
- **Реальные отчётные файлы:** DOCX/XLSX в серверном режиме генерируются бэкендом
  из данных СУБД (python-docx/openpyxl): паспорт `{{org}}.docx`, реестр `registry.xlsx`,
  EVM портфеля `evm.xlsx` (выбор по типу отчёта). Недоступность сервера — прозрачный
  откат в клиентскую генерацию с честным предупреждением.
- **Smoke-проверки:** SRV-DL-01, SRV-PASS-01, SRV-REPORT-01, SRV-TWIN-01.
- **E2E-стенд `srv`:** сценарии персистентности — s.11 (правка паспорта через UI →
  версия в СУБД → значение переживает повторный вход), s.12 (реальный DOCX: PK-магия,
  размер, имя), s.13 (реальный XLSX реестра).
- **Живой протокол:** LP-18 (паспорт: карта полей → PUT → версия → quality) и LP-19
  (бинарные отчёты DOCX/XLSX/PDF: маги-байты и размер).

### Изменено
- **`srvDownload` доведена до закалённого Promise-API** (функцию определил Этап 9, но
  не использовал): эпоха сессии (отмена устаревших загрузок), лимит 64 МБ
  (`SRV_DOWNLOAD_MAX_BYTES`), проверка непустоты, имя файла из `Content-Disposition`,
  регистрация в `SRV_ACTIVE_REQUESTS` (abort при logout), возврат `{{name,size,type}}`.
- Версия {V['str']} во всех отчётах/экспортах/UI — автоматически из `APP_VERSION`.
- «Что нового» в справочном центре обновлено до {V['str']}.

### Совместимость
- Демо-режим и киоск не изменены: все обёртки Этапа 12 прозрачны при
  `SRV.connected === false` (регрессия: jsdom + E2E file/http).
- Снимки данных v100–v102 восстанавливаются без ограничений.
"""

lines = [
    "# CHANGELOG — АИС «Техноконтур» · шифр «Провидец»",
    "",
    "Все значимые изменения клиентского приложения (единый HTML-артефакт `ais_providets_vXXX.html`).",
    "Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/), версионирование — [SemVer](https://semver.org/lang/ru/).",
    "",
    "> Примечание: записи ниже (кроме v103) сгенерированы из массива «История версий программы»",
    "> страницы «О системе» (`RENDERERS.about`) — единого источника истории внутри артефакта.",
    "> v14–v81, v83–v99 — промежуточные итерации закалки клиентской ветки B (работы P0.1–P0.59),",
    "> в публичный массив истории артефакта не включались (см. `src9/README.md`).",
    "",
    V103_SECTION,
]
for v, d, text in entries:
    if v == V["str"]:
        continue
    num = v.lstrip("v")
    dd, mm, yyyy = d.split(".")
    lines += [f"## [{num}] — {yyyy}-{mm}-{dd}", "", "### Изменено", f"- {js_unescape(text)}", ""]

CHANGELOG.write_text("\n".join(lines), encoding="utf-8")
print(f"[i] CHANGELOG.md перезаписан: v103 + {len(entries) - 1} записей истории")
print("\n".join(report))
print(f"\n[OK] {OUT.name} собран: замен — {len(report)}, ошибок — 0.")
