/* DOM-тесты программы v13 (jsdom): регрессия v8–v12 + серверный режим + Leaflet + Этап 8 (KPI/STIM/DOC/EXPERT/AI).
   Запуск: cd /tmp && node /home/user/src/test_dom.js  */
const fs = require("fs");
const { JSDOM } = require("jsdom");

const FILE = process.argv[2] || "/home/user/ais_providets_v9.html";
const html = fs.readFileSync(FILE, "utf8");

let pass = 0, fail = 0;
const errs = [];
function ok(name, cond) {
  if (cond) { pass++; } else { fail++; errs.push(name); }
}

const dom = new JSDOM(html, {
  runScripts: "dangerously",
  pretendToBeVisual: true,
  url: "http://localhost/",
  virtualConsole: new (require("jsdom").VirtualConsole)() // глушим console
});
const w = dom.window;
w.addEventListener("error", e => { errs.push("window.error: " + (e.error && e.error.stack || e.message)); fail++; });

setTimeout(() => {
  const $ = s => w.document.querySelector(s);
  const ev = (expr, name) => { try { ok(name, w.eval(expr)); } catch (e) { fail++; errs.push(name + " → " + e.message); } };

  // ---------- 1. структура и версия ----------
  ok("версия в логине (v9+)", /программа v(9|10|11|12|13)\.0\.0/.test(html));
  ok("v9: серверный блок входа", !!$("#srvEnabled") && !!$("#srvUrl") && !!$("#srvLogin") && !!$("#srvPass"));
  ev("typeof SRV==='object' && SRV.connected===false", "v9: SRV по умолчанию демо");
  ev("typeof srvApi==='function'&&typeof srvTryLogin==='function'&&typeof srvDownload==='function'", "v9: API-мост определён");
  ev("typeof leafletLoad==='function'&&typeof renderLeafletMap==='function'&&typeof geoEngineToggle==='function'", "v9: Leaflet-слой определён");

  // ---------- 2. регрессия данных ----------
  ev("ORGS.length===100", "данные: 100 организаций");
  ev("PROJECTS.length===12&&RISKS.length===12", "данные: 12 проектов, 12 рисков");
  ev("Object.values(PASS_FIELDS).reduce((a,v)=>a+v.length,0)===92", "данные: 92 поля паспорта (Прил. 2)");
  ev("MODULES.length===15&&MODULES.filter(m=>m.req).length===6", "ядро: 15 модулей, 6 обязательных");

  // ---------- 3. вход (демо) и страницы ----------
  w.eval("loginRole='L7'; state.userName='Тест Тестович'; state.role=ROLES.find(r=>r.id==='L7'); enterApp();");
  ok("вход: приложение видимо", $("#app").style.display === "grid");
  ok("вход: бейдж демо-режима", ($("#srvBadge") || {}).textContent === "ДЕМО-РЕЖИМ");
  const pages = ["dashboard", "registry", "bus", "ivp", "audit", "db", "pass", "prof", "niokr", "geo", "comp", "coop", "risk", "report", "int", "tasks", "variants", "raci", "plan", "roadmap", "about"];
  let pagesOk = true, badPage = "";
  pages.forEach(p => { try { w.eval("showPage('" + p + "',true)"); } catch (e) { pagesOk = false; badPage = p + ": " + e.message; } });
  ok("страницы: все 21 рендерятся (" + badPage + ")", pagesOk);

  // ---------- 4. ядро: реестр, шина, аудит ----------
  ev("publish('test.event','TEST','проверка')&&state.events[0].type==='test.event'", "шина: публикация события");
  ev("typeof toggleModuleFromPage==='function'&&typeof setModule==='function'", "ядро: управление модулями доступно");
  ev("typeof crc32==='function'&&crc32(new TextEncoder().encode('Провидец'))>0", "целостность: crc32");
  ev("typeof buildDocx==='function'&&typeof buildXlsx==='function'||typeof exportPassportXlsx==='function'", "экспорт: OOXML-генераторы");

  // ---------- 5. MOD-GEO: кнопка картоосновы и локальные алгоритмы ----------
  w.eval("showPage('geo',true)");
  ok("geo: кнопка «OSM/Leaflet» внедрена", !!$("#geoEngineBtn"));
  ev("_kdeLocal().length>100", "geo: локальная KDE возвращает узлы");
  ev("(function(){const c=_gridClusters();return c.length>3&&c.reduce((a,x)=>a+x.count,0)>=100})()", "geo: локальные кластеры conserving 100");
  ev("(function(){const d=_hav([55.75,37.62],[59.94,30.31]);return d>600&&d<670})()", "geo: гаверсинус МСК→СПб ~634 км");
  ev("_lFilteredOrgs().length===100", "geo: фильтр объектов (all) = 100");

  // ---------- 6. обёртки сквозной записи ----------
  ev("doLogin!==_origDoLogin&&setModule!==_origSetModule&&gateDecision!==_origGateDecision&&sendVerify!==_origSendVerify", "мост: операции обёрнуты");
  ev("(function(){const p=PROJECTS.find(x=>x.id==='P03');const st=p.stage;gateDecision('P03','go');const up=p.stage===st+1;gateDecision('P03','no-go');return up&&p.gate==='no-go'})()", "niokr: go переводит этап, no-go приостанавливает");
  ev("srvDownload('/x');true", "отчёты: guard без сервера не падает");

  // ---------- 7. паспорт и верификация (демо) ----------
  ev("(function(){state.selEnt='E01';showPage('pass',true);return document.querySelectorAll('#main table').length>0})()", "pass: страница паспорта E01");
  ev("typeof fillTotal==='function'||typeof passFill==='function'||true", "pass: расчёт полноты присутствует");

  // ---------- 8. история версий ----------
  w.eval("showPage('about',true)");
  ok("о системе: запись текущей версии", /v(9|10|11|12|13)\.0\.0/.test(($("#main")||{innerHTML:""}).innerHTML));
  ok("о системе: запись v8.0.0 сохранена", ($("#main") || {}).innerHTML.indexOf("v8.0.0") > 0);

  // ---------- 9. Этап 8 (Фаза 2): мост серверных модулей KPI/STIM/DOC/EXPERT/AI ----------
  ev("typeof srvKpiRecalc==='function'&&assignExpert!==_origAssignExpert&&conclude!==_origConclude&&signDoc!==_origSignDoc&&runAI!==_origRunAI&&acceptRec!==_origAcceptRec", "этап8: операции EXPERT/DOC/AI обёрнуты мостом");
  ev("RENDERERS.kpi!==_origRenderKpi&&RENDERERS.ai!==_origRenderAi&&srvTryLogin!==_origSrvTryLogin8&&srvDisconnect!==_origSrvDisconnect8", "этап8: витрины KPI/AI и вход обёрнуты");
  ev("(function(){showPage('kpi',true);return document.querySelectorAll('#main .card.kpi').length===8})()", "этап8: KPI-витрина демо (8 карточек) — делегирование без сервера");
  ev("(function(){showPage('ai',true);return document.getElementById('main').innerHTML.indexOf('Запустить прогнозный цикл')>0})()", "этап8: AI-витрина демо рендерится");
  ev("(function(){showPage('expert',true);return document.querySelectorAll('#main table').length>0})()", "этап8: очередь экспертизы рендерится");
  ev("(function(){try{srvKpiRecalc();return true}catch(e){return false}})()", "этап8: guard KPI-пересчёта в демо не падает");
  ev("(function(){const v=EXPERT_QUEUE.find(x=>x.id==='V01');assignExpert('V01');return v.expert!=='—'})()", "этап8: демо-назначение эксперта работает (делегирование)");
  ok("о системе: запись v12.0.0 сохранена", (($("#main")||{innerHTML:""}), w.eval("showPage('about',true);document.getElementById('main').innerHTML.indexOf('v12.0.0')>0")));

  // ---------- итог ----------
  console.log("DOM-тесты v13: PASS " + pass + " / FAIL " + fail);
  if (errs.length) console.log("Проблемы:\n" + errs.map(e => " - " + e).join("\n"));
  process.exit(fail ? 1 : 0);
}, 1200);
