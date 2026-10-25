#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ЭТАП 10 — Волна 0 плана улучшений (работы 0.1–0.8 → идентификаторы P3.1–P3.8).
Преобразование: ais_providets_v100.html → ais_providets_v101.html (+ копия ais_providets.html).

Все замены СТРОГИЕ: каждый якорь обязан встретиться ровно ожидаемое число раз,
иначе скрипт аварийно завершается (никаких «тихих» регрессий).

Соответствие пунктам плана (plan_uluchsheniy_v100.md):
  0.1/P3.1 — единая константа APP_VERSION + ver()/verNum(); замена всех функциональных
             хардкодов версии в отчётах, самопроверках, UI-строках и именах экспортов.
  0.2/P3.2 — один meta providets-release-version (удалены v97/v98/v99) + runtime-синхронизация.
  0.3/P3.3 — #toasts: role="status" aria-live="polite"; ошибочные тосты: role="alert" assertive.
  0.4/P3.4 — tcDialog/tcConfirm/tcPrompt вместо window.confirm (восстановление снимка)
             и window.prompt (MFA-код): role=dialog, aria-modal, фокус-ловушка, Esc, возврат фокуса.
  0.5/P3.5 — навигация: <nav aria-label>, nav-item role=button tabindex=0 aria-current data-page,
             делегированная клавиатурная обработка (Enter/Space) без новых inline-атрибутов.
  0.6/P3.6 — deep-linking: deepLinkSync() в showPage, hashchange/popstate, восстановление после входа.
  0.7/P3.7 — Leaflet 1.9.4 в поставке (vendor/leaflet/), SRI sha256 для CDN-режима.
  0.8/P3.8 — CHANGELOG.md (генерируется из массива истории версий + запись v101),
             секция «Что нового» в справочном центре.

Запуск:  python3 src10/patch_v101.py   (из корня репозитория или из src10/)
"""
import base64
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "ais_providets_v100.html"
OUT = ROOT / "ais_providets_v101.html"
CUR = ROOT / "ais_providets.html"
VENDOR_JS = ROOT / "vendor" / "leaflet" / "leaflet.js"
VENDOR_CSS = ROOT / "vendor" / "leaflet" / "leaflet.css"
CHANGELOG = ROOT / "CHANGELOG.md"

V = {
    "major": 101, "minor": 0, "patch": 0,
    "str": "v101.0.0", "num": "101.0.0", "tz": "4.0",
    "build": "v101", "released": "26.10.2026", "released_iso": "2026-10-26",
}

WAVE0_HISTORY_TEXT = (
    "Волна 0 плана улучшений (P3.1–P3.8, план plan_uluchsheniy_v100.md): "
    "(1) единый источник версии — константа APP_VERSION + ver()/verNum(): устранены хардкоды "
    "литералов текущей версии в отчётах, самодиагностике, UI и именах JSON-экспортов "
    "(16 имён теперь получают суффикс из APP_VERSION.build; исправлен рассинхрон имени "
    "first_admin_runbook); (2) ровно один meta-тег providets-release-version "
    "(устаревшие v97/v98/v99 удалены), синхронизируется из константы; (3) доступность: "
    "тосты — role=status + aria-live=polite (ошибочные — alert/assertive); боковая навигация — "
    "nav с aria-label, пункты role=button, tabindex=0, aria-current=page, data-page, полное "
    "управление с клавиатуры (Tab, Enter/Space) через один делегированный обработчик; "
    "(4) вместо блокирующих window.confirm/window.prompt — немодальный доступный диалог tcDialog "
    "(role=dialog, aria-modal, фокус-ловушка, Esc — отмена, Enter — подтверждение, возврат фокуса): "
    "подтверждение восстановления снимка и ввод MFA-кода; (5) deep-linking: синхронизация страницы "
    "с location.hash, обработка hashchange/popstate, кнопка «назад» браузера работает, после входа "
    "восстанавливается страница из хэша; (6) офлайн-карта: Leaflet 1.9.4 включён в поставку "
    "(vendor/leaflet/ + LICENSE + images/), CDN-режим загружается с SRI sha256 и "
    "crossorigin=anonymous; (7) CHANGELOG.md в корне репозитория и раздел «Что нового» в "
    "справочном центре (F1); (8) новые встроенные smoke-проверки REL-VER-02, A11Y-01, NAV-01, "
    "DL-01, GEO-SRI-01. Совместимость: демо-режим и киоск не изменены; снимки данных v100 "
    "восстанавливаются без ограничений (валидатор схемы не привязан к версии программы)."
)

# ---------------------------------------------------------------- утилиты ----
html = SRC.read_text(encoding="utf-8")
BASE_LEN = len(html)
report = []
errors = []


def rep(old, new, count=1, label=""):
    """Строгая замена: old должен встречаться ровно count раз."""
    global html
    n = html.count(old)
    name = label or (old[:64].replace("\n", "\\n") + "…")
    if n != count:
        errors.append(f"[FAIL] {name}: ожидалось {count} вхождений, найдено {n}")
        return False
    html = html.replace(old, new)
    report.append(f"  ok  {name}  ×{count}")
    return True


def sri_sha256(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).digest()
    return "sha256-" + base64.b64encode(digest).decode("ascii")


def sha256_hex(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


for p in (SRC, VENDOR_JS, VENDOR_CSS):
    if not p.exists():
        sys.exit(f"[FAIL] Не найден обязательный файл: {p}")

JS_SRI = sri_sha256(VENDOR_JS)
CSS_SRI = sri_sha256(VENDOR_CSS)
print(f"[i] SRI leaflet.js  = {JS_SRI}")
print(f"[i] SRI leaflet.css = {CSS_SRI}")

# =========================================== P3.1/P3.2: КОНСТАНТА ВЕРСИИ ====
MAIN_SCRIPT_ANCHOR = """<script>
"use strict";
/* ============================================================
   АИС «Техноконтур» · шифр «Провидец» · v4.0
   ДЕМОНСТРАЦИОННАЯ ПРОГРАММА (прототип по ТЗ)
   Модельные данные. Все совпадения случайны.
   ============================================================ */
"""

VERSION_BLOCK = """
/* ==================================================================
   P3.1–P3.2 (v101.0.0 · Волна 0 плана улучшений): ЕДИНЫЙ ИСТОЧНИК ВЕРСИИ.
   Все отчёты, экспорты, самопроверки и видимые версии читают значение
   только отсюда. Ручная правка литералов версии в коде запрещена.
   ================================================================== */
const APP_VERSION=Object.freeze({major:101,minor:0,patch:0,str:"v101.0.0",num:"101.0.0",tz:"4.0",build:"v101",released:"26.10.2026"});
function ver(){return APP_VERSION.str;}
function verNum(){return APP_VERSION.num;}
/* P3.7 (Волна 0.7): SRI (SHA-256, base64) для Leaflet 1.9.4 в CDN-режиме.
   Значения вычисляются сборщиком из фактических файлов ./vendor/leaflet/,
   которые поставляются в архиве для автономного варианта Б. */
const TC_LEAFLET_SRI=Object.freeze({version:"1.9.4",js:"@@JS_SRI@@",css:"@@CSS_SRI@@",
  localPath:"./vendor/leaflet/",cdnBase:"https://unpkg.com/leaflet@1.9.4/dist/"});

/* ================= P3.4 (v101 · Волна 0.4): ДОСТУПНЫЙ НЕБЛОКИРУЮЩИЙ ДИАЛОГ =================
   Замена window.confirm/window.prompt: role="dialog", aria-modal, фокус-ловушка (Tab),
   Esc — отмена, Enter — подтверждение (с учётом фокуса на «Отмене»), возврат фокуса.
   Возвращает Promise: tcConfirm → true/false; tcPrompt → строка либо null. */
function tcDialog(opts){
  opts=opts||{};
  return new Promise(function(resolve){
    const hasInput=!!opts.input;
    const prevFocus=document.activeElement;
    const old=document.getElementById("tcDialog");if(old)old.remove();
    const overlay=document.createElement("div");overlay.id="tcDialog";
    overlay.style.cssText="position:fixed;inset:0;z-index:10060;background:rgba(2,6,23,.78);display:flex;align-items:center;justify-content:center;padding:16px;";
    overlay.setAttribute("role","dialog");overlay.setAttribute("aria-modal","true");overlay.setAttribute("aria-labelledby","tcDialogTitle");
    overlay.innerHTML='<div style="width:min(560px,100%);max-height:85vh;overflow:auto;background:var(--panel,#101827);color:var(--tx,#e5edf7);border:1px solid var(--bd,#334155);border-radius:14px;padding:18px;box-shadow:0 20px 80px #0008">'+
      '<h2 id="tcDialogTitle" style="margin:0 0 10px;font-size:17px">'+esc(opts.title||"Подтверждение действия")+'</h2>'+
      '<div style="font-size:13px;line-height:1.55;color:var(--tx2,#9ca3af);white-space:pre-wrap">'+esc(opts.message||"")+'</div>'+
      (hasInput?'<label for="tcDlgInp" style="display:block;margin-top:12px;font-size:12.5px;color:var(--tx2,#9ca3af)">'+esc(opts.inputLabel||"Значение")+'</label>'+
        '<input id="tcDlgInp" class="inp" type="text" autocomplete="'+esc(opts.inputAutocomplete||"off")+'"'+(opts.inputNumeric?' inputmode="numeric" pattern="[0-9]*"':"")+(opts.inputMaxlength?' maxlength="'+Number(opts.inputMaxlength)+'"':"")+' style="width:100%;margin-top:6px"'+(opts.inputPlaceholder?' placeholder="'+esc(opts.inputPlaceholder)+'"':"")+'>':"")+
      '<div style="display:flex;justify-content:flex-end;gap:10px;margin-top:16px">'+
      (opts.cancelText===null?"":'<button type="button" class="btn" id="tcDlgCancel">'+esc(opts.cancelText||"Отмена")+'</button>')+
      '<button type="button" class="btn ac" id="tcDlgOk">'+esc(opts.okText||"OK")+'</button></div></div>';
    document.body.appendChild(overlay);
    const inp=hasInput?overlay.querySelector("#tcDlgInp"):null;
    const okBtn=overlay.querySelector("#tcDlgOk");
    const cancelBtn=overlay.querySelector("#tcDlgCancel");
    let closed=false;
    const cancelVal=function(){return hasInput?null:false;};
    const okVal=function(){return hasInput?(inp?inp.value:null):true;};
    const finish=function(val){
      if(closed)return;closed=true;
      document.removeEventListener("keydown",onKey,true);
      overlay.remove();
      if(prevFocus&&prevFocus.focus){try{prevFocus.focus();}catch(e){}}
      resolve(val);
    };
    okBtn.addEventListener("click",function(){finish(okVal());});
    if(cancelBtn)cancelBtn.addEventListener("click",function(){finish(cancelVal());});
    overlay.addEventListener("click",function(e){if(e.target===overlay)finish(cancelVal());});
    function focusables(){
      return Array.prototype.slice.call(overlay.querySelectorAll('button,input,[tabindex]:not([tabindex="-1"])'))
        .filter(function(el){return !el.disabled;});
    }
    function onKey(e){
      if(e.key==="Escape"){e.preventDefault();e.stopPropagation();finish(cancelVal());return;}
      if(e.key==="Enter"){
        /* Enter не должен провоцировать глобальные обработчики (например, doLogin на экране входа) */
        e.preventDefault();e.stopPropagation();
        const ae=document.activeElement;
        finish(ae&&ae.id==="tcDlgCancel"?cancelVal():okVal());
        return;
      }
      if(e.key==="Tab"){
        const f=focusables();if(!f.length)return;
        const first=f[0],last=f[f.length-1];
        if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}
        else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}
      }
    }
    document.addEventListener("keydown",onKey,true);
    setTimeout(function(){try{(inp||okBtn).focus();if(inp&&inp.select)inp.select();}catch(e){}},30);
  });
}
function tcConfirm(title,message,okText){return tcDialog({title:title,message:message,okText:okText||"Продолжить",cancelText:"Отмена"});}
function tcPrompt(title,message,label,opts){
  const o=Object.assign({},opts||{});
  o.title=title;o.message=message;o.input=true;o.inputLabel=label||"Значение";
  return tcDialog(o);
}

/* ================= P3.6 (v101 · Волна 0.6): DEEP-LINKING (location.hash ↔ страница) =========
   showPage() синхронизирует хэш (pushState, на file:// — fallback location.hash);
   hashchange/popstate возвращают приложение на страницу из хэша; в киоск-режиме
   хэш обновляется без накопления истории (replaceState). */
const DL_LOCK={v:false};
function parseHashPage(h){
  const raw=String(h==null?location.hash:(h||"")).replace(/^#/,"");
  if(!raw)return null;
  const id=raw.split("?")[0].split("/")[0].toLowerCase();
  if(!/^[a-z0-9_-]{1,32}$/.test(id))return null;
  return (typeof RENDERERS!=="undefined"&&RENDERERS&&typeof RENDERERS[id]==="function")?id:null;
}
function deepLinkSync(p){
  try{
    if(!p)return;
    const want="#"+p;
    if(location.hash===want)return;
    const replaceMode=DL_LOCK.v||(typeof kiosk!=="undefined"&&kiosk&&kiosk.on);
    if(window.history&&history.pushState){
      try{
        if(replaceMode)history.replaceState({tcPage:p},"",want);
        else history.pushState({tcPage:p},"",want);
        return;
      }catch(e){/* file://: pushState/replaceState могут быть запрещены — fallback ниже */}
    }
    DL_LOCK.v=true;location.hash=p;setTimeout(function(){DL_LOCK.v=false;},0);
  }catch(e){DL_LOCK.v=false;}
}
"""

VERSION_BLOCK = VERSION_BLOCK.replace("@major@@", str(V["major"])).replace("@@JS_SRI@@", JS_SRI).replace("@@CSS_SRI@@", CSS_SRI)
# версия внутри Object.freeze формируется из V (единый источник сборки):
VERSION_BLOCK = VERSION_BLOCK.replace(
    'const APP_VERSION=Object.freeze({major:101,minor:0,patch:0,str:"v101.0.0",num:"101.0.0",tz:"4.0",build:"v101",released:"26.10.2026"});',
    'const APP_VERSION=Object.freeze({major:%(major)d,minor:%(minor)d,patch:%(patch)d,str:"%(str)s",num:"%(num)s",tz:"%(tz)s",build:"%(build)s",released:"%(released)s"});' % V,
)

rep(MAIN_SCRIPT_ANCHOR, MAIN_SCRIPT_ANCHOR + VERSION_BLOCK, 1, "P3.1/3.2/3.4/3.6/3.7: блок константы версии, tcDialog, deep-linking в начале главного скрипта")

# ================================================== P3.2: META-ТЕГ (0.2) ====
rep(
    '<meta name="providets-release-version" content="v97">\n'
    '<meta name="providets-release-version" content="v98">\n'
    '<meta name="providets-release-version" content="v99">\n',
    '<meta name="providets-release-version" content="%s">\n' % V["str"],
    1, "P3.2: три мусорных meta → одна (v101)",
)

# ========================================= статические версии в разметке ====
rep(
    '<div style="font-size:11.5px;color:var(--tx3);letter-spacing:2.6px;text-transform:uppercase;margin-top:3px">Шифр темы «Провидец» · ТЗ 4.0 · программа v100.0.0</div>',
    '<div id="loginVerLine" style="font-size:11.5px;color:var(--tx3);letter-spacing:2.6px;text-transform:uppercase;margin-top:3px">Шифр темы «Провидец» · ТЗ %(tz)s · программа %(str)s</div>' % V,
    1, "P3.1: строка версии на экране входа (loginVerLine)",
)
rep(
    'программа версии 100.0.0 по ТЗ версии 4.0.',
    'программа версии <span data-tc-ver="num">%(num)s</span> по ТЗ версии <span data-tc-ver="tz">%(tz)s</span>.' % V,
    1, "P3.1: login-note — версия через data-tc-ver",
)
rep(
    'внешняя загрузка Leaflet из CDN запрещена; для карты нужны локальные файлы ./vendor/leaflet/leaflet.js и leaflet.css и локальный тайл-сервер.',
    'внешняя загрузка Leaflet из CDN запрещена; для карты используются локальные файлы ./vendor/leaflet/leaflet.js и leaflet.css (включены в поставку, начиная с %(build)s) и локальный тайл-сервер.' % V,
    1, "P3.7: примечание о локальных файлах Leaflet",
)

# ==================================================== P3.3: ТОСТЫ (0.3) ====
rep(
    '<div id="toasts"></div>',
    '<div id="toasts" role="status" aria-live="polite" aria-relevant="additions text"></div>',
    1, "P3.3: #toasts — role=status aria-live=polite",
)
rep(
    '''function toast(msg,type,src){
  const w=$("#toasts");const d=document.createElement("div");d.className="toast "+(type||"");''',
    '''function toast(msg,type,src){
  const w=$("#toasts");const d=document.createElement("div");d.className="toast "+(type||"");
  /* P3.3 (v101): ошибочные тосты объявляются скринридером немедленно */
  if(type==="err"||type==="error"){d.setAttribute("role","alert");d.setAttribute("aria-live","assertive");}''',
    1, "P3.3: toast() — assertive для ошибок",
)

# ================================================ P3.5: НАВИГАЦИЯ (0.5) ====
rep(
    '<div id="sidebar"><div id="nav"></div></div>',
    '<nav id="sidebar" aria-label="Основная навигация по страницам и модулям"><div id="nav"></div></nav>',
    1, "P3.5: sidebar — <nav aria-label>",
)
rep(
    r'''      h.push('<div class="nav-item'+(state.page===it.p?" active":"")+(off?" offmod":"")+'" onclick="showPage(\''+it.p+'\')" title="'+esc(it.t)+'">'+''',
    r'''      h.push('<div class="nav-item'+(state.page===it.p?" active":"")+(off?" offmod":"")+'" data-page="'+it.p+'" role="button" tabindex="0"'+(state.page===it.p?' aria-current="page"':"")+' onclick="showPage(\''+it.p+'\')" title="'+esc(it.t)+'">'+''',
    1, "P3.5: nav-item — role/tabindex/aria-current/data-page",
)

# ============================================= P3.6: DEEP-LINKING (0.6) ====
rep(
    '''function showPage(p,silent){
  const mod=PAGE_MOD[p];
  state.page=p;renderNav();''',
    '''function showPage(p,silent){
  const mod=PAGE_MOD[p];
  state.page=p;renderNav();deepLinkSync(p);''',
    1, "P3.6: showPage — синхронизация хэша",
)
rep(
    '  showPage("dashboard");',
    '  showPage(parseHashPage()||"dashboard"); /* P3.6: deep-link при входе */',
    1, "P3.6: enterApp — восстановление страницы из хэша",
)

# =================================== P3.1: ВЕРСИИ В ОТЧЁТАХ И ЭКСПОРТАХ ====
rep(
    'program:"v100.0.0",tz:"ред. 4.0"',
    'program:ver(),tz:"ред. "+APP_VERSION.tz',
    1, "P3.1: dbSnapshotPayload — program/tz из константы",
)
rep('program:"v100.0.0"', "program:ver()", 17, "P3.1: program:ver() во всех отчётах")
rep('version:"v100.0.0"', "version:ver()", 2, "P3.1: SBOM CycloneDX — версии инструмента и компонента из константы")
rep('program!=="v100.0.0"', "program!==ver()", 6, "P3.1: самопроверки program!==ver()")
rep(
    'const expected="v100.0.0";',
    "const expected=ver();",
    1, "P3.1: selftest expected=ver()",
)
rep(
    'if(!RENDERERS.about.toString().includes("программа v100.0.0"))throw new Error("Заголовок раздела «О системе» содержит устаревшую версию");',
    'if(!RENDERERS.about().includes("программа "+ver()))throw new Error("Заголовок раздела «О системе» содержит устаревую версию");',
    1, "P3.1: selftest — проверка фактического рендера «О системе»",
)
rep(
    "'Прототип v100.0.0 · компонент в оценке: '",
    "'Прототип '+ver()+' · компонент в оценке: '",
    1, "P3.1: roadmap mchip",
)
rep(
    'шифр «Провидец» | прототип v100.0.0</div>\';',
    'шифр «Провидец» | прототип \'+ver()+\'</div>\';',
    1, "P3.1: roadmap footer-note",
)
rep(
    'текущая точка: интерактивный прототип v100.0.0, серверный режим',
    "текущая точка: интерактивный прототип '+ver()+', серверный режим",
    1, "P3.1: roadmap hint фаз",
)
rep(
    "'ТЗ версия 4.0 · программа v100.0.0 · 13 задач · 15 модулей · 10 ИВП · 92 поля паспорта · 10 приложений к ТЗ')+",
    "'ТЗ версия '+APP_VERSION.tz+' · программа '+ver()+' · 13 задач · 15 модулей · 10 ИВП · 92 поля паспорта · 10 приложений к ТЗ')+",
    1, "P3.1: about pageHead",
)
rep(
    'шифр темы «Провидец» | программа v100.0.0 | \'+today()+',
    'шифр темы «Провидец» | программа \'+ver()+\' | \'+today()+',
    1, "P3.1: about footer",
)
rep(
    'Шифр темы «Провидец». Программа v100.0.0 по ТЗ версии 4.0. Архитектура',
    'Шифр темы «Провидец». Программа "+ver()+" по ТЗ версии "+APP_VERSION.tz+". Архитектура',
    1, "P3.1: гид-тур, шаг 1",
)
rep(
    'return !!h&&h.textContent.includes(\'v100.0.0\')&&!!n&&n.textContent.includes(\'100.0.0\')&&',
    "return !!h&&h.textContent.includes(ver())&&!!n&&n.textContent.includes(verNum())&&",
    1, "P3.1: smoke REL-VER-01 — через ver()/verNum()",
)

# имена JSON-экспортов: _v100.json → суффикс из APP_VERSION.build
def regex_rep(pattern, repl, count, label):
    global html
    html_new, n = re.subn(pattern, repl, html)
    if n != count:
        errors.append(f"[FAIL] regex {label}: ожидалось {count}, найдено {n}")
        return False
    html = html_new
    report.append(f"  ok  {label}  ×{n}")
    return True


regex_rep(r'"providets_([a-z0-9_]+)_v100\.json"',
          lambda m: '"providets_' + m.group(1) + '"+APP_VERSION.build+".json"', 10,
          "P3.1: 10 имён экспорта _v100.json → APP_VERSION.build (двойные кавычки)")
regex_rep(r"'providets_([a-z0-9_]+)_v100\.json'",
          lambda m: "'providets_" + m.group(1) + "'+APP_VERSION.build+'.json'", 6,
          "P3.1: 6 имён экспорта _v100.json → APP_VERSION.build (одинарные кавычки)")
rep(
    '"providets_first_admin_runbook_v82.json"',
    '"providets_first_admin_runbook_"+APP_VERSION.build+".json"',
    1, "P3.1: исправлен рассинхрон first_admin_runbook (_v82 → build)",
)

# ================================================ P3.4: ДИАЛОГИ (0.4) ======
rep(
    '  if(!window.confirm(summary)){toast("Восстановление отменено; данные не изменены.","","CORE");return;}',
    '''  /* P3.4 (v101): блокирующий нативный диалог заменён доступным tcDialog (не модальный для браузера) */
  const restoreConfirmed=await tcConfirm("Восстановление демонстрационных данных из снимка",summary,"Заменить данные");
  if(!restoreConfirmed){toast("Восстановление отменено; данные не изменены.","","CORE");return;}''',
    1, "P3.4: восстановление снимка — tcConfirm вместо window.confirm",
)
rep(
    '    const code=window.prompt("MFA (TOTP) для роли "+login.toUpperCase()+": введите 6-значный код");',
    '''    /* P3.4 (v101): блокирующий нативный ввод заменён доступным диалогом tcPrompt */
    const code=await tcPrompt("Двухфакторная аутентификация (MFA)","MFA (TOTP) для роли "+login.toUpperCase()+": введите 6-значный код из приложения-аутентификатора.","Код MFA · 6 цифр",{okText:"Подтвердить",cancelText:"Отмена",inputNumeric:true,inputMaxlength:8,inputAutocomplete:"one-time-code",inputPlaceholder:"000000"});''',
    1, "P3.4: MFA — tcPrompt вместо window.prompt",
)

# ================================================== P3.7: LEAFLET SRI ======
rep(
    '''  js.src=localOnly?"./vendor/leaflet/leaflet.js":"https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
  const done=ok=>{''',
    '''  js.src=localOnly?"./vendor/leaflet/leaflet.js":"https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
  /* P3.7 (v101): CDN-режим — контроль целостности SRI (SHA-256); локальный режим — файлы из поставки */
  if(!localOnly){css.integrity=TC_LEAFLET_SRI.css;css.crossOrigin="anonymous";js.integrity=TC_LEAFLET_SRI.js;js.crossOrigin="anonymous";}
  const done=ok=>{''',
    1, "P3.7: leafletLoad — SRI integrity + crossorigin для CDN",
)

# =============================== P3.8: ИСТОРИЯ, СПРАВКА, SMOKE-ПРОВЕРКИ =====
HISTORY_ANCHOR = '   [\n    ["v100.0.0","18.10.2026","Этап 9 — объединение двух веток разработки'
rep(
    HISTORY_ANCHOR,
    '   [\n    ["%s","%s","%s"],\n    ["v100.0.0","18.10.2026","Этап 9 — объединение двух веток разработки'
    % (V["str"], V["released"], WAVE0_HISTORY_TEXT),
    1, "P3.8: запись v101.0.0 в историю версий «О системе»",
)

rep(
    '''  idx.push({c:"Паспорт (Приложение 2)",t:"92 поля 12 разделов паспорта",x:"Спецификация полей: тип, обязательность, источник; пороги полноты по разделам (2.14); редактирование и журнал версий",go:"showPage('pass')"});
  return idx;''',
    '''  idx.push({c:"Паспорт (Приложение 2)",t:"92 поля 12 разделов паспорта",x:"Спецификация полей: тип, обязательность, источник; пороги полноты по разделам (2.14); редактирование и журнал версий",go:"showPage('pass')"});
  /* P3.8 (v101): раздел «Что нового» в справочном центре */
  idx.push({c:"Что нового · "+ver(),t:ver()+" — волна 0 плана улучшений: версия, доступность, deep-linking, офлайн-карта",x:"Единая константа APP_VERSION; тосты и навигация доступны скринридеру и клавиатуре; диалоги tcDialog вместо window.confirm/prompt (MFA, восстановление снимка); глубокие ссылки #страница и кнопка «назад»; Leaflet 1.9.4 в поставке (vendor/) c SRI для CDN; CHANGELOG.md",go:"showPage('about')"});
  return idx;''',
    1, "P3.8: «Что нового» в индексе справочного центра",
)
rep(
    'if(["kpi","variants","geo","niokr"].includes(m[1]))showPage(m[1]);return;}',
    'if(["kpi","variants","geo","niokr","about"].includes(m[1]))showPage(m[1]);return;}',
    1, "P3.8: runHelpAction — переход на «О системе» разрешён",
)

SMOKE_ANCHOR = "check('CSP-01','Генератор профиля CSP определён',()=>typeof buildCspDeploymentProfile==='function');"
rep(
    SMOKE_ANCHOR,
    SMOKE_ANCHOR + """
 /* P3.x (v101 · Волна 0): проверки новых инженерных механизмов */
 check('REL-VER-02','Единая константа версии: meta, снимок и сводка P0 согласованы с APP_VERSION',()=>{const metas=document.querySelectorAll('meta[name="providets-release-version"]');return metas.length===1&&metas[0].getAttribute('content')===ver()&&ver()==='v'+APP_VERSION.major+'.'+APP_VERSION.minor+'.'+APP_VERSION.patch&&dbSnapshotPayload().program===ver()&&buildP0EvidenceSummary().program===ver();});
 check('A11Y-01','Тосты объявляются скринридеру; блокирующие нативные диалоги не используются',()=>{const t=document.getElementById('toasts');return !!t&&t.getAttribute('aria-live')==='polite'&&typeof tcDialog==='function'&&typeof tcConfirm==='function'&&typeof tcPrompt==='function'&&!previewDBRestoreImpl.toString().includes('window.confirm')&&!srvTryLogin.toString().includes('window.prompt');});
 check('NAV-01','Элементы навигации доступны с клавиатуры (role/tabindex/data-page)',()=>{if(!state||!state.role)return false;renderNav();const items=document.querySelectorAll('#nav .nav-item');return items.length>0&&Array.prototype.every.call(items,x=>x.getAttribute('role')==='button'&&x.getAttribute('tabindex')==='0'&&!!x.getAttribute('data-page'));});
 check('DL-01','Deep-linking: парсер хэша валидирует страницы по реестру RENDERERS',()=>typeof parseHashPage==='function'&&typeof deepLinkSync==='function'&&parseHashPage('#about')==='about'&&parseHashPage('#geo?layer=heat')==='geo'&&parseHashPage('#not-a-page')===null&&parseHashPage('')===null);
 check('GEO-SRI-01','CDN-режим Leaflet использует SRI; офлайн-режим — локальные файлы поставки',()=>typeof TC_LEAFLET_SRI==='object'&&/^sha256-[A-Za-z0-9+/]{43}=$/.test(TC_LEAFLET_SRI.js)&&/^sha256-[A-Za-z0-9+/]{43}=$/.test(TC_LEAFLET_SRI.css)&&TC_LEAFLET_SRI.version==='1.9.4'&&leafletLoad.toString().includes('integrity'));""",
    1, "P3.x: +5 новых smoke-проверок (REL-VER-02, A11Y-01, NAV-01, DL-01, GEO-SRI-01)",
)

# ================================================ ХВОСТОВОЙ СКРИПТ v101 ====
TAIL_ANCHOR = "</script>\n</body>\n</html>"
TAIL_BLOCK = """</script>

<script>
/* ==================================================================
   ЭТАП 10 / %(str)s — ВОЛНА 0 ПЛАНА УЛУЧШЕНИЙ: рантайм-активация P3.
   P3.2: meta и видимые версии синхронизируются из APP_VERSION (единый источник).
   P3.5: клавиатурная навигация сайдбара — один делегированный обработчик
         (Enter/Space на .nav-item[data-page]); новых inline-атрибутов нет.
   P3.6: deep-linking — hashchange/popstate → showPage; до входа хэш не
         применяется (страница восстановится после входа через enterApp).
   Вспомогательные функции (tcDialog, parseHashPage, deepLinkSync, ver)
   определены в главном скрипте.
   ================================================================== */
(function(){
 "use strict";
 function syncVersionMeta(){
   try{
     var m=document.querySelector('meta[name="providets-release-version"]');
     if(!m){m=document.createElement("meta");m.setAttribute("name","providets-release-version");document.head.appendChild(m);}
     m.setAttribute("content",ver());
     var head=document.getElementById("loginVerLine");
     if(head)head.textContent="Шифр темы «Провидец» · ТЗ "+APP_VERSION.tz+" · программа "+ver();
     var els=document.querySelectorAll("[data-tc-ver]");
     for(var i=0;i<els.length;i++){
       var k=els[i].getAttribute("data-tc-ver");
       if(k==="num")els[i].textContent=verNum();
       else if(k==="tz")els[i].textContent=APP_VERSION.tz;
       else if(k==="str")els[i].textContent=ver();
     }
   }catch(e){/* синхронизация версии не должна ломать запуск */}
 }
 function onDeepLinkNav(){
   if(DL_LOCK.v)return;
   var app=document.getElementById("app");
   if(!app||app.style.display!=="grid")return; /* до входа хэш игнорируется */
   var hp=parseHashPage();
   if(hp&&hp!==state.page){DL_LOCK.v=true;try{showPage(hp);}finally{DL_LOCK.v=false;}}
 }
 window.addEventListener("hashchange",onDeepLinkNav);
 window.addEventListener("popstate",onDeepLinkNav);
 document.addEventListener("keydown",function(e){
   if(e.key!=="Enter"&&e.key!==" "&&e.key!=="Spacebar")return;
   var t=e.target&&e.target.closest?e.target.closest(".nav-item[data-page]"):null;
   if(!t)return;
   e.preventDefault();
   var p=t.getAttribute("data-page");
   if(p)showPage(p);
 },true);
 if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",syncVersionMeta);
 else syncVersionMeta();
})();
</script>
</body>
</html>""" % V
rep(TAIL_ANCHOR, TAIL_BLOCK, 1, "P3.2/3.5/3.6: хвостовой скрипт v101 (синхронизация версий, hash-роутинг, клавиатура)")

# ======================================================= ВАЛИДАЦИЯ ВЫХОДА ===
def expect(cond, msg):
    if cond:
        report.append("  ok  VALIDATE: " + msg)
    else:
        errors.append("[FAIL] VALIDATE: " + msg)


expect(html.count('program:"v100.0.0"') == 0, 'не осталось program:"v100.0.0"')
expect(html.count('program!=="v100.0.0"') == 0, 'не осталось program!=="v100.0.0"')
expect(html.count("_v100.json") == 0, "не осталось имён экспорта _v100.json")
expect(html.count("_v82.json") == 0, "не осталось _v82.json")
expect(len(re.findall(r"window\.confirm\s*\(", html)) == 0, "window.confirm( = 0")
expect(len(re.findall(r"window\.prompt\s*\(", html)) == 0, "window.prompt( = 0")
expect(html.count('<meta name="providets-release-version"') == 1, "ровно один meta providets-release-version")
expect(html.count("ver()") >= 40, "ver() используется не менее 40 раз (факт: %d)" % html.count("ver()"))

# Оставшиеся упоминания v100.0.0 — только исторические (массив истории + комментарий Этапа 9)
rem = [(i + 1, ln.strip()[:110]) for i, ln in enumerate(html.split("\n")) if "v100.0.0" in ln]
expect(len(rem) == 2, "осталось ровно 2 исторических упоминания v100.0.0 (история + комментарий), факт: %d" % len(rem))
for no, txt in rem:
    print(f"    [историческое] стр.{no}: {txt}")

# Оставшиеся 101.0.0 — только build-time инъекции единого источника + история
rem101 = [(i + 1, ln.strip()[:110]) for i, ln in enumerate(html.split("\n")) if V["num"] in ln]
allowed_markers = ("const APP_VERSION=Object.freeze", 'content="%s"' % V["str"], "loginVerLine",
                   'data-tc-ver="num"', '["v101.0.0","26.10.2026"',
                   "P3.1–P3.2 (v101.0.0", "ЭТАП 10 / v101.0.0")
for no, txt in rem101:
    line_text = html.split("\n")[no - 1]
    if not any(mk in line_text for mk in allowed_markers):
        errors.append(f"[FAIL] незапланированный хардкод {V['num']} на стр.{no}: {txt}")
report.append("  ok  VALIDATE: все вхождения %s — из единого источника сборки/истории (%d строк)" % (V["num"], len(rem101)))

expect("tcDialog" in html and "tcConfirm" in html and "tcPrompt" in html, "диалоги tcDialog/tcConfirm/tcPrompt определены")
expect("deepLinkSync(p)" in html and "parseHashPage()||" in html, "deep-linking подключён к showPage/enterApp")
expect('data-page="\'+it.p+\'"' in html and 'aria-current="page"' in html, "навигация: data-page + aria-current")
expect('id="toasts" role="status" aria-live="polite"' in html, "тосты: role/aria-live на контейнере")
expect("integrity=TC_LEAFLET_SRI" in html, "Leaflet CDN: SRI integrity")
expect(JS_SRI in html and CSS_SRI in html, "SRI-хеши встроены из фактических файлов vendor/")

if errors:
    print("\n".join(errors))
    sys.exit(1)

# ============================================================= ЗАПИСЬ =======
OUT.write_text(html, encoding="utf-8")
CUR.write_text(html, encoding="utf-8")
print(f"[i] {OUT.name}: {BASE_LEN} → {len(html)} байт (+{len(html) - BASE_LEN})")
print(f"[i] {CUR.name} обновлён (копия {OUT.name})")

# ================================================ CHANGELOG.md (0.8/P3.8) ===
def js_unescape(s: str) -> str:
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t", '"': '"', "'": "'", "\\": "\\"}.get(m.group(1), m.group(1)), s)


entries = re.findall(r'\["(v\d+\.\d+\.\d+)","(\d{2}\.\d{2}\.\d{4})","((?:[^"\\]|\\.)*)"\]',
                     SRC.read_text(encoding="utf-8"))
print(f"[i] извлечено записей истории из v100: {len(entries)}")
if len(entries) < 70:
    sys.exit("[FAIL] массив истории распознан не полностью — CHANGELOG не генерируется")

V101_SECTION = f"""## [{V['num']}] — {V['released_iso']}

Волна 0 плана улучшений (`plan_uluchsheniy_v100.md`, работы 0.1–0.8 → P3.1–P3.8).
Артефакт: `ais_providets_v101.html` (единый HTML; `ais_providets.html` — рабочая копия).
Сборка: `python3 src10/patch_v101.py` (детерминированная, из `ais_providets_v100.html`).

### Добавлено
- **Единый источник версии (0.1/P3.1):** константа `APP_VERSION` + `ver()`/`verNum()`;
  все отчёты, самопроверки, UI-строки и имена JSON-экспортов читают версию только из неё
  (устранено ~40 хардкодов; 16 имён экспорта получают суффикс из `APP_VERSION.build`).
- **Доступный диалог `tcDialog()` (0.4/P3.4):** `role="dialog"`, `aria-modal`, фокус-ловушка,
  Esc — отмена, Enter — подтверждение, возврат фокуса; обёртки `tcConfirm()`/`tcPrompt()`.
- **Deep-linking (0.6/P3.6):** синхронизация страницы с `location.hash` (`#risk`, `#geo`, …),
  обработка `hashchange`/`popstate`, кнопка «назад» браузера работает; после входа
  восстанавливается страница из хэша; в киоск-режиме история не накапливается.
- **Leaflet 1.9.4 в поставке (0.7/P3.7):** `vendor/leaflet/` (leaflet.js, leaflet.css,
  images/, LICENSE) для автономного варианта Б; CDN-режим — загрузка с SRI (SHA-256)
  и `crossorigin="anonymous"`. Хеши:
  - `leaflet.js` — sha256 (hex): `{sha256_hex(VENDOR_JS)}` · SRI: `{JS_SRI}`
  - `leaflet.css` — sha256 (hex): `{sha256_hex(VENDOR_CSS)}` · SRI: `{CSS_SRI}`
- **Новые встроенные smoke-проверки:** REL-VER-02 (единая meta + согласованность версии),
  A11Y-01 (тосты/диалоги), NAV-01 (клавиатурная навигация), DL-01 (hash-роутинг),
  GEO-SRI-01 (SRI Leaflet).
- **Справочный центр (F1):** категория «Что нового · {V['str']}»; страница «О системе»:
  запись {V['str']} в истории версий.
- **`CHANGELOG.md`** в корне репозитория (0.8/P3.8) — генерируется из массива истории
  версий приложения (единый источник) + структурированная запись {V['str']}.
- **`src10/`**: сценарий сборки `patch_v101.py`, DOM-тесты `test_dom_v101.js` (jsdom),
  статическая верификация `verify_v101.sh`.

### Изменено
- **Тосты (0.3/P3.3):** контейнер `#toasts` — `role="status"` + `aria-live="polite"`;
  ошибочные тосты — `role="alert"` + `aria-live="assertive"`.
- **Навигация (0.5/P3.5):** сайдбар — `<nav aria-label>`; пункты — `role="button"`,
  `tabindex="0"`, `aria-current="page"`, `data-page`; Enter/Space работают через один
  делегированный обработчик (новые inline-обработчики НЕ добавлялись — курс на волну 2.2).
- Подтверждение восстановления снимка и ввод MFA-кода переведены с блокирующих
  `window.confirm`/`window.prompt` на `tcDialog` (киоск-режим и скринридеры не ломаются).
- Самопроверка версии «О системе» (dbSnapshotSelfTest) проверяет фактически
  отрисованный HTML, а не исходный код рендерера через `toString()`.

### Исправлено
- **Мусорные meta-теги (0.2/P3.2):** удалены три устаревших `providets-release-version`
  (v97/v98/v99); остался ровно один, синхронизируемый из `APP_VERSION` при загрузке.
- Рассинхрон версии в имени экспорта `providets_first_admin_runbook_v82.json` →
  суффикс из `APP_VERSION.build`.

### Совместимость
- Демо-режим, киоск-сценарий и вариант Б не изменены поведением.
- Снимки данных v100 восстанавливаются в v101 без ограничений
  (`dbValidateSnapshot` проверяет `schemaVersion`, а не версию программы).
"""

lines = [
    "# CHANGELOG — АИС «Техноконтур» · шифр «Провидец»",
    "",
    "Все значимые изменения клиентского приложения (единый HTML-артефакт `ais_providets_vXXX.html`).",
    "Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/), версионирование — [SemVer](https://semver.org/lang/ru/).",
    "",
    "> Примечание: записи ниже (кроме v101) сгенерированы из массива «История версий программы»",
    "> страницы «О системе» (`RENDERERS.about`) — единого источника истории внутри артефакта.",
    "> v14–v81, v83–v99 — промежуточные итерации закалки клиентской ветки B (работы P0.1–P0.59),",
    "> в публичный массив истории артефакта не включались (см. `src9/README.md`).",
    "",
    V101_SECTION,
]
for v, d, text in entries:
    num = v.lstrip("v")
    dd, mm, yyyy = d.split(".")
    lines.append(f"## [{num}] — {yyyy}-{mm}-{dd}")
    lines.append("")
    lines.append("### Изменено")
    lines.append(f"- {js_unescape(text)}")
    lines.append("")

CHANGELOG.write_text("\n".join(lines), encoding="utf-8")
print(f"[i] CHANGELOG.md записан: 1 запись {V['str']} + {len(entries)} записей истории")

print("\n".join(report))
print(f"\n[OK] {OUT.name} собран: замен — {len(report)}, ошибок — 0.")
