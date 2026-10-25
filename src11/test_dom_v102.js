/* DOM-тесты Этапа 11 (jsdom): программа v102.0.0 = v101.0.0 + выпуск «Рабочая платформа» (фикс Д-10).
   База: src9/test_dom_v100.js (регрессия, 60 проверок) + новая секция [5w] Wave-0 (диалоги,
   deep-linking, клавиатурная навигация, тосты a11y, единая версия, SRI Leaflet).
   Запуск:
   cd /tmp && NODE_PATH=/home/user/testenv/node_modules node -e \
     "process.argv[2]='/home/user/providec/ais_providets_v102.html'; require('/home/user/providec/src11/test_dom_v102.js')" */
const fs = require("fs");
const { JSDOM, VirtualConsole } = require("jsdom");
const FILE = process.argv[2] || "/home/user/providec/ais_providets_v102.html";
const html = fs.readFileSync(FILE, "utf8");

let pass = 0, fail = 0; const errs = [];
function ok(name, cond) { if (cond) pass++; else { fail++; errs.push(name); } }
const delay = ms => new Promise(r => setTimeout(r, ms));

const vc = new VirtualConsole();
const jsErrors = [];
vc.on("jsdomError", e => jsErrors.push(String(e.message).slice(0, 200)));
const dom = new JSDOM(html, { runScripts: "dangerously", pretendToBeVisual: true, url: "http://localhost/", virtualConsole: vc });
const w = dom.window;
const E = (expr) => w.eval(expr);

/* ---- mock fetch для серверного режима ---- */
let fetchCalls = [];
function mkResp(r) {
  const body = JSON.stringify(r.json);
  return { ok: r.status >= 200 && r.status < 300, status: r.status,
    headers: { get: h => String(h).toLowerCase() === "content-type" ? "application/json" : null },
    text: async () => body, body: null };
}
function installMock(routes) {
  fetchCalls = [];
  w.fetch = async (url, opts) => {
    const u = String(url); fetchCalls.push({ u, m: (opts && opts.method) || "GET" });
    for (const [pat, resp] of routes) if (u.includes(pat)) return mkResp(resp);
    return mkResp({ status: 404, json: { detail: "не замокировано: " + u } });
  };
}

const KPI_ITEMS = [
  { code: "KPI-1", n: "Охват реестра паспортами", cur: 87, unit: "%", target: 85, dir: "up", met: true, fmt: "≥ 85 %", source: "calc", hist: [80, 83, 87], updated: "2026-10-18" },
  { code: "KPI-3", n: "Портфель НИОКР", cur: 10, unit: "ед", target: 12, dir: "up", met: false, fmt: "≥ 12", source: "calc", hist: [9, 10], updated: "2026-10-18" }];
const AI_DATA = { model: "v4.0-srv",
  tech_gaps: { threshold: 75, gaps: [{ n: "Аддитивные технологии", prog: [54, 61, 66, 70, 73, 75], conf: 0.86, sovereign_by: 6 }] },
  fail_risk: [{ id: "P03", name: "Проект 3", org: "E14", risk: 57, factors: { overdue_days: 12 } }],
  recommendations: [{ rid: "R-9", t: "Ускорить НИОКР по аддитивным технологиям", conf: 0.78, m: "MOD-NIOKR", status: "open" }] };

(async function main() {
  await delay(1500);
  const $ = s => w.document.querySelector(s);
  const V = E("ver()");           // "v101.0.0" — из единой константы артефакта
  const VN = E("verNum()");       // "101.0.0"

  console.log("[1] загрузка...");
  /* ---------- 1. загрузка и защита ---------- */
  ok("1.1 нет ошибок JS при загрузке", jsErrors.length === 0);
  ok("1.2 fetch-guard: установлен либо нативный fetch отсутствует (jsdom)",
    E("window.__tcFetchGuardInstalled===true || typeof window.fetch!=='function'"));
  ok("1.3 egress-guards установлены", E("window.__tcEgressGuardsInstalled===true"));
  ok("1.4 мост Этапа 9 установлен", E("window.__TC_STAGE9_BRIDGE===true"));

  console.log("[2] данные/страницы...");
  /* ---------- 2. данные и страницы (регрессия) ---------- */
  ok("2.1 100 организаций", E("ORGS.length===100"));
  ok("2.2 92 поля паспорта", E("Object.values(PASS_FIELDS).reduce((a,v)=>a+v.length,0)===92"));
  ok("2.3 15 модулей / 6 обязательных", E("MODULES.length===15&&MODULES.filter(m=>m.req).length===6"));
  E("loginRole='L7'; state.userName='Тест'; state.role=ROLES.find(r=>r.id==='L7'); enterApp();");
  ok("2.4 демо-вход: приложение видимо", $("#app").style.display === "grid");
  const pages = ["dashboard","registry","bus","ivp","audit","db","pass","prof","niokr","geo","comp","coop","risk","report","int","tasks","variants","raci","plan","roadmap","kpi","ai","doc","expert","stim","about"];
  let bad = [];
  pages.forEach(p => { try { E("showPage('" + p + "',true)"); } catch (e) { bad.push(p + ":" + e.message.slice(0, 60)); } });
  ok("2.5 все " + pages.length + " страницы рендерятся (" + bad.join("|") + ")", bad.length === 0);
  ok("2.6 roadmap: панель ворот выпуска", E("showPage('roadmap',true); !!(document.getElementById('releaseGates')||document.getElementById('releaseGateDecision'))"));

  console.log("[3] встроенные самопроверки...");
  /* ---------- 3. встроенные самопроверки ---------- */
  console.log("  [3a] smoke...");
  const smoke = E("runClientRegressionSmokeTests()");
  ok("3.1 встроенные smoke-тесты " + smoke.summary.passed + "/" + smoke.summary.total,
    smoke.summary.failed === 0 && smoke.summary.total >= 26);
  ok("3.1b новые проверки Волны 0 присутствуют в smoke",
    ["REL-VER-02","A11Y-01","NAV-01","DL-01","GEO-SRI-01","SRV-LOGIN-01"].every(id => smoke.tests.some(t => t.id === id && t.result === "PASS")));
  console.log("  [3b] net...");
  const net = E("runNetworkPolicySelfTest()");
  ok("3.2 самотест сетевой политики " + net.passed + "/" + net.total, net.failed === 0);
  console.log("  [3c] db...");
  E("dbRunSelfTests()");
  const dbRep = E("DB_LAST_SELF_TEST_REPORT");
  ok("3.3 самодиагностика снимков " + dbRep.summary.passed + "/" + dbRep.summary.total,
    dbRep && dbRep.summary.failed === 0 && dbRep.program === V);
  ok("3.4 D-1: sanitizer скрывает секреты JSON-ключей",
    E("const s=sanitizeDiagnosticText('{\\\"api_key\\\":\\\"key-secret\\\",\\\"session_id\\\":\\\"sid-secret\\\"}'); s.indexOf('key-secret')<0&&s.indexOf('sid-secret')<0&&s.includes('[REDACTED]')"));
  ok("3.5 D-3: buildP0EvidenceBundleCore синхронный и с метаданными текущей версии",
    E("(function(){const b=buildP0EvidenceBundleCore();return b.program===ver()&&b.status==='PROTOTYPE_EVIDENCE_BUNDLE_NOT_ACCEPTANCE'&&!!b.artifacts.p0Summary&&!!b.artifacts.airGapPlan;})()"));
  ok("3.6 D-4: стартовый цифровой двойник E03 присутствует",
    E("!!state.twin['E03']&&state.twin['E03'].orgId==='E03'&&/^0x[0-9a-f]{8}$/.test(state.twin['E03'].crc)"));

  console.log("[4] О системе...");
  /* ---------- 4. «О системе» ---------- */
  const about = E("RENDERERS.about()");
  ok("4.1 about не начинается с <tr> (defect исправлен)", !about.startsWith("<tr>"));
  ok("4.2 about содержит шапку страницы", about.includes("О системе · АИС «Техноконтур»"));
  ok("4.3 about содержит «История версий»", about.includes("История версий"));
  ok("4.4 about содержит Microkernel/архитектуру", about.includes("Microkernel"));
  ok("4.5 about содержит P0-карточки (P0.18)", about.includes("P0.18"));
  ok("4.6 about содержит «Заимствованные решения»", about.includes("Заимствованные решения"));
  ok("4.7 about содержит контракт безопасности", about.includes("Аутентификация"));
  const rows = about.match(/<td class="mono" style="color:var\(--acc2\);font-weight:700">v\d+\.\d+\.\d+<\/td>/g) || [];
  ok("4.8 история: 81 строка (v102→v1), факт " + rows.length, rows.length === 81);
  ok("4.9 порядок: v102 → v101 → v100 → v82 → v49 → v1",
    about.indexOf(">v102.0.0<") < about.indexOf(">v101.0.0<") && about.indexOf(">v101.0.0<") < about.indexOf(">v100.0.0<") && about.indexOf(">v100.0.0<") < about.indexOf(">v82.0.0<") && about.indexOf(">v82.0.0<") < about.indexOf(">v49.0.0<") && about.indexOf(">v49.0.0<") < about.indexOf(">v1.0.0<"));
  ok("4.10 запись v100 описывает Этап 9", about.includes("Этап 9 — объединение двух веток"));
  ok("4.11 запись v82 (P0.56) сохранена", about.includes("P0.56"));
  ok("4.12 запись v101 описывает Волну 0", about.includes("Волна 0 плана улучшений"));
  ok("4.13 запись v102 описывает Д-10 и живые испытания", about.includes("Д-10") && about.includes("живым протоколом"));

  console.log("[5] версии...");
  /* ---------- 5. версионные метаданные (единый источник) ---------- */
  ok("5.1 login-head: " + V, ($(".login-head div div") || {}).textContent.includes(V));
  ok("5.2 login-note: версии " + VN, ($(".login-note") || {}).textContent.includes("версии " + VN));
  ok("5.3 about-подзаголовок: программа " + V, about.includes("программа " + V));
  ok("5.4 about-футер: программа " + V, about.includes("footer-note") && new RegExp("footer-note[^]*программа " + V.replace(/\./g, "\\.")).test(about));
  ok("5.5 тур: Программа " + V + " (runtime)", E("TOUR[0].x.includes('Программа '+ver()+' по ТЗ версии '+APP_VERSION.tz)"));
  ok("5.6 план/roadmap: прототип " + V + " (runtime)",
    E("RENDERERS.roadmap().includes('Прототип '+ver())&&RENDERERS.roadmap().includes('прототип '+ver())&&RENDERERS.plan().includes('прототип '+ver())"));
  ok("5.7 нет старых литералов v82/v49/74/37/12/7, _v81, _v100.json, _v82.json",
    !html.includes("программа v82") && !html.includes("программа v49") && !html.includes("версии 74.0.0") &&
    !html.includes("прототип v37.0.0") && !html.includes("Программа v12.0.0") && !html.includes("рототип v7.0.0") &&
    !html.includes("_v81.json") && !html.includes("_v100.json") && !html.includes("_v82.json"));
  ok("5.8 имена экспорта динамические (APP_VERSION.build), ≥17",
    ((html.match(/"\+APP_VERSION\.build\+"\.json/g) || []).length + (html.match(/'\+APP_VERSION\.build\+'\.json/g) || []).length) >= 17);

  console.log("[5w] Волна 0 (P3)...");
  /* ---------- 5w. Волна 0 плана улучшений ---------- */
  ok("w.1 APP_VERSION: заморожена и самосогласована",
    E("Object.isFrozen(APP_VERSION)&&ver()==='v'+APP_VERSION.major+'.'+APP_VERSION.minor+'.'+APP_VERSION.patch&&verNum()===APP_VERSION.major+'.'+APP_VERSION.minor+'.'+APP_VERSION.patch"));
  ok("w.2 P3.2: ровно одна meta providets-release-version, синхронизирована",
    E("document.querySelectorAll('meta[name=\"providets-release-version\"]').length===1") &&
    E("document.querySelector('meta[name=\"providets-release-version\"]').getAttribute('content')===ver()"));
  ok("w.3 P3.3: #toasts — role=status aria-live=polite",
    E("(function(){const t=document.getElementById('toasts');return t.getAttribute('role')==='status'&&t.getAttribute('aria-live')==='polite';})()"));
  ok("w.3b P3.3: ошибочный тост — role=alert aria-live=assertive",
    E("(function(){toast('тест ошибки','err','TEST');const d=document.getElementById('toasts').lastElementChild;const r=!!d&&d.getAttribute('role')==='alert'&&d.getAttribute('aria-live')==='assertive';if(d)d.remove();return r;})()"));
  ok("w.4 P3.4: нативные блокирующие диалоги отсутствуют в коде",
    !html.includes("window.confirm(") && !html.includes("window.prompt("));
  /* tcConfirm: OK → true */
  E("(function(){window.__dlg1='pending';tcConfirm('Тест подтверждения','Сообщение').then(v=>{window.__dlg1=v;});})()");
  await delay(80);
  ok("w.5 P3.4: tcDialog открыт (role=dialog, aria-modal, заголовок)",
    !!$("#tcDialog") && $("#tcDialog").getAttribute("role") === "dialog" && $("#tcDialog").getAttribute("aria-modal") === "true" && ($("#tcDialog").textContent || "").includes("Тест подтверждения"));
  E("document.getElementById('tcDlgOk').click()");
  await delay(40);
  ok("w.5b P3.4: OK → resolve(true), диалог закрыт", E("window.__dlg1===true") && !$("#tcDialog"));
  /* tcPrompt: ввод + Enter → значение; Esc → null */
  E("(function(){window.__dlg2='pending';tcPrompt('MFA','Введите код','Код',{inputNumeric:true}).then(v=>{window.__dlg2=v;});})()");
  await delay(80);
  ok("w.6 P3.4: tcPrompt — поле ввода c inputmode=numeric", !!$("#tcDlgInp") && $("#tcDlgInp").getAttribute("inputmode") === "numeric");
  E("(function(){const i=document.getElementById('tcDlgInp');i.value='123456';i.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));})()");
  await delay(40);
  ok("w.6b P3.4: Enter в поле → resolve('123456')", E("window.__dlg2==='123456'") && !$("#tcDialog"));
  E("(function(){window.__dlg3='pending';tcConfirm('Тест Esc','').then(v=>{window.__dlg3=v;});})()");
  await delay(60);
  E("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))");
  await delay(40);
  ok("w.7 P3.4: Esc → отмена (false), диалог закрыт", E("window.__dlg3===false") && !$("#tcDialog"));
  ok("w.8 P3.4: восстановление снимка использует tcConfirm (не confirm)",
    E("previewDBRestoreImpl.toString().includes('tcConfirm')&&!previewDBRestoreImpl.toString().includes('window.confirm')"));
  ok("w.9 P3.4: MFA-ввод использует tcPrompt (не prompt)",
    E("srvTryLogin.toString().includes('tcPrompt')&&!srvTryLogin.toString().includes('window.prompt')"));
  ok("w.10 P3.5: все nav-item — role=button tabindex=0 data-page",
    E("(function(){renderNav();const it=document.querySelectorAll('#nav .nav-item');return it.length>0&&Array.prototype.every.call(it,x=>x.getAttribute('role')==='button'&&x.getAttribute('tabindex')==='0'&&!!x.getAttribute('data-page'));})()"));
  ok("w.11 P3.5: активный пункт — aria-current=page; сайдбар — <nav aria-label>",
    E("(function(){showPage('bus',true);const a=document.querySelector('#nav .nav-item[aria-current=\"page\"]');return !!a&&a.getAttribute('data-page')==='bus'&&document.getElementById('sidebar').tagName==='NAV'&&!!document.getElementById('sidebar').getAttribute('aria-label');})()"));
  E("showPage('registry',true)");
  await delay(20);
  const navItem = w.document.querySelector("#nav .nav-item[data-page='ivp']");
  navItem.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  await delay(40);
  ok("w.12 P3.5: Enter на nav-item переключает страницу", E("state.page==='ivp'"));
  const navItem2 = w.document.querySelector("#nav .nav-item[data-page='audit']");
  navItem2.dispatchEvent(new w.KeyboardEvent("keydown", { key: " ", bubbles: true }));
  await delay(40);
  ok("w.13 P3.5: Space на nav-item переключает страницу", E("state.page==='audit'"));
  ok("w.14 P3.6: showPage синхронизирует location.hash", E("showPage('risk',true);location.hash==='#risk'"));
  ok("w.15 P3.6: parseHashPage валидирует по RENDERERS", E("parseHashPage('#geo?layer=heat')==='geo'&&parseHashPage('#about')==='about'&&parseHashPage('#no-such')===null&&parseHashPage('javascript:alert(1)')===null"));
  E("location.hash='#comp'");
  await delay(120);
  ok("w.16 P3.6: hashchange → showPage (кнопка «назад»/прямая ссылка)", E("state.page==='comp'"));
  E("logout(); loginRole='L7'; state.userName='Тест'; state.role=ROLES.find(r=>r.id==='L7'); location.hash='#niokr'; enterApp();");
  await delay(60);
  ok("w.17 P3.6: после входа восстанавливается страница из хэша", E("state.page==='niokr'") && $("#app").style.display === "grid");
  ok("w.18 P3.7: SRI Leaflet 1.9.4 задан и подключается в CDN-режиме",
    E("TC_LEAFLET_SRI.version==='1.9.4'&&/^sha256-[A-Za-z0-9+/]{43}=$/.test(TC_LEAFLET_SRI.js)&&/^sha256-[A-Za-z0-9+/]{43}=$/.test(TC_LEAFLET_SRI.css)&&leafletLoad.toString().includes('integrity')&&leafletLoad.toString().includes('crossOrigin')"));
  ok("w.19 P3.7: SRI leaflet.js совпадает с эталоном leafletjs.com",
    E("TC_LEAFLET_SRI.js") === "sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" &&
    E("TC_LEAFLET_SRI.css") === "sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=");
  ok("w.20 P3.8: «Что нового» в справочном центре",
    E("buildHelpIndex().some(x=>String(x.c).indexOf('Что нового')===0&&String(x.go).indexOf('about')>0)"));
  ok("w.21 P3.8: runHelpAction разрешает переход на about",
    E("runHelpAction.toString().includes('\"about\"')||runHelpAction.toString().includes(\"'about'\")"));
  ok("w.22 Д-10: обёртка входа передаёт снимок пароля в srvTryLogin(presetPassword)",
    E("doLogin.toString().includes('passSnapshot')&&srvTryLogin.toString().includes('presetPassword')&&srvTryLogin.length===1"));
  ok("w.23 P3.1: экспорты/отчёты используют ver() (выборка)",
    E("dbSnapshotPayload().program===ver()&&buildImportAcceptanceMatrix().program===ver()&&buildAirGapAcceptancePlan().program===ver()&&buildP0EvidenceSummary().program===ver()&&buildSoftwareComponentRegister().metadata.component.version===ver()"));

  console.log("[6] мост...");
  /* ---------- 6. мост Этапа 8 ---------- */
  ok("6.1 srvKpiRecalc/srvLoadStage8 определены", E("typeof srvKpiRecalc==='function'&&typeof srvLoadStage8==='function'"));
  ok("6.2 обёртки операций содержат серверные endpoint'ы",
    E("assignExpert.toString().includes('/api/v1/expert/')&&conclude.toString().includes('/conclude')&&signDoc.toString().includes('/api/v1/documents/')&&runAI.toString().includes('/api/v1/ai/run')&&acceptRec.toString().includes('/accept')"));
  ok("6.3 enterApp/srvDisconnect захуканы", E("enterApp.toString().includes('srvLoadStage8')&&srvDisconnect.toString().includes('SRV.kpis=null')"));
  ok("6.4 защищённые функции НЕ переопределены мостом",
    E("srvTryLogin.toString().includes('loginAttemptEpoch')&&doLogin.toString().includes('LOGIN_ATTEMPT_SUPERSEDED')&&srvStartPolling.toString().includes('pollEpoch')&&srvApplyBootstrap.toString().includes('const staged={}')"));
  ok("6.5 демо-режим: KPI без «СЕРВЕРНЫЙ РЕЖИМ»", E("SRV.connected=false; !RENDERERS.kpi().includes('СЕРВЕРНЫЙ РЕЖИМ')"));
  ok("6.6 демо-режим: AI без серверной модели", E("!RENDERERS.ai().includes('v4.0-srv')"));
  ok("6.7 демо: srvKpiRecalc → предупреждение, без fetch", (() => {
    installMock([]); E("SRV.connected=false; srvKpiRecalc();"); return fetchCalls.length === 0; })());

  console.log("[7] серверная загрузка...");
  /* ---------- 7. серверный режим ---------- */
  installMock([["/api/v1/kpis", { status: 200, json: { period: "2026-Q4", items: KPI_ITEMS } }],
               ["/api/v1/ai/recommendations", { status: 200, json: AI_DATA }]]);
  E("SRV.connected=true;SRV.token='test-jwt';SRV.sessionEpoch=7;SRV.url='';SRV.kpis=null;SRV.ai=null;state.role=ROLES.find(r=>r.id==='L7');showPage('kpi',true)");
  ok("7.1 ленивая загрузка начата (запрос /kpis)", fetchCalls.some(c => c.u.includes("/api/v1/kpis")));
  await delay(120);
  ok("7.2 витрины загружены", E("SRV.kpis&&SRV.kpis.period==='2026-Q4'&&SRV.ai&&SRV.ai.model==='v4.0-srv'"));
  ok("7.3 страница KPI перерисована в серверном режиме", $("#main").innerHTML.includes("СЕРВЕРНЫЙ РЕЖИМ") && $("#main").innerHTML.includes("Регламентный пересчёт"));
  const aiHtml = E("showPage('ai',true); document.getElementById('main').innerHTML");
  ok("7.4 AI-страница: серверная модель и рекомендации", aiHtml.includes("v4.0-srv") && aiHtml.includes('data-rid="R-9"') && aiHtml.includes("Запустить прогнозный цикл"));

  console.log("[8] операции...");
  /* ---------- 8. серверные операции (mock API) ---------- */
  installMock([
    ["/api/v1/kpis/recalculate", { status: 200, json: { period: "2026-Q4", total: 8, breached: [{ code: "KPI-3" }], items: KPI_ITEMS } }],
    ["/api/v1/stims", { status: 200, json: { items: [{ id: "S-88", t: "Эскалация отраслевым органам", m: "MOD-STIM", status: "auto" }] } }],
    ["/expert/E-01/assign", { status: 200, json: { expert: "Иванов И.И.", status: "in_review" } }],
    ["/expert/E-01/conclude", { status: 200, json: { expert: "Иванов И.И.", verdict: "Подтверждено", org_verified: "E14", new_stims: [{ id: "S-77", t: "Стимул верификации", m: "MOD-STIM" }] } }],
    ["/sign", { status: 200, json: { sign: "На подписании", version: 3 } }],
    ["/api/v1/ai/run", { status: 200, json: Object.assign({ run_id: "AI-R-9" }, AI_DATA) }],
    ["/accept", { status: 200, json: { t: AI_DATA.recommendations[0].t } }],
    ["/api/v1/ai/recommendations", { status: 200, json: AI_DATA }]]);
  E("SRV.sessionEpoch=7");

  E("srvKpiRecalc()"); await delay(150);
  ok("8.1 KPI: регламентный пересчёт POST + аудит + STIMS обновлён",
    fetchCalls.some(c => c.u.includes("/kpis/recalculate") && c.m === "POST") &&
    E("state.audit.some(a=>a.action==='Пересчет KPI (сервер)')") && E("STIMS.some(s=>s.id==='S-88')"));
  ok("8.2 KPI: событие kpi.threshold_breached опубликовано", E("state.events.some(e=>e.type==='kpi.threshold_breached')"));

  E("EXPERT_QUEUE[0].id='E-01';EXPERT_QUEUE[0].expert='—';EXPERT_QUEUE[0].status='queued';assignExpert('E-01')"); await delay(120);
  ok("8.3 EXPERT: назначение через сервер", E("EXPERT_QUEUE[0].expert==='Иванов И.И.'&&EXPERT_QUEUE[0].status==='in_review'") && E("state.events.some(e=>e.type==='expert.assigned')"));

  E("conclude('E-01')"); await delay(150);
  ok("8.4 EXPERT: заключение → цепочка verified/стимул", E("EXPERT_QUEUE[0].status==='done'") && E("state.events.some(e=>e.type==='passport.verified')") && E("STIMS.some(s=>s.id==='S-77')"));

  const docId = E("DOCS[0].id"); E("DOCS[0].sign='Проект';signDoc(DOCS[0].id)"); await delay(120);
  ok("8.5 DOC: подписание через сервер (" + docId + ")", E("DOCS[0].sign==='На подписании'&&DOCS[0].version===3") && E("state.events.some(e=>e.type==='doc.status_changed')"));

  E("runAI()"); await delay(200);
  ok("8.6 AI: прогнозный цикл через сервер", E("SRV.ai&&SRV.ai.run_id==='AI-R-9'") && E("state.events.some(e=>e.type==='ai.recommendations_ready')"));

  E("showPage('ai',true)");
  const btnOk = E("(function(){const b=document.querySelector('[data-rid=\\\"R-9\\\"] button');if(!b)return false;acceptRec(b);return true;})()");
  await delay(120);
  ok("8.7 AI: принятие рекомендации + WORM-аудит", btnOk && fetchCalls.some(c => c.u.includes("/accept") && c.m === "POST") && E("state.audit.some(a=>a.action==='Принятие ИИ-рекомендации (сервер)')"));

  console.log("[9] RBAC...");
  /* ---------- 9. RBAC ---------- */
  const before = fetchCalls.length;
  E("state.role=ROLES.find(r=>r.id==='L0');srvKpiRecalc();assignExpert('E-01');runAI()");
  await delay(80);
  ok("9.1 L0: серверные операции отклонены IAM без fetch", fetchCalls.length === before);
  E("state.role=ROLES.find(r=>r.id==='L7')");

  console.log("[10] fallback...");
  /* ---------- 10. сбой сервера ---------- */
  installMock([]);
  E("SRV.connected=true;SRV.token='t';SRV.sessionEpoch=7;SRV.kpis=null;SRV.ai=null;SRV._s9Stage8Loaded=false;showPage('kpi',true)");
  await delay(150);
  const callsAfterFail = fetchCalls.length;
  ok("10.1 при сбое выполнена одна попытка загрузки (" + callsAfterFail + " запросов)", callsAfterFail === 2);
  await delay(250);
  ok("10.2 нет цикла повторных загрузок (было " + callsAfterFail + ", стало " + fetchCalls.length + ")", fetchCalls.length === callsAfterFail);
  ok("10.3 fallback: предупреждение + кнопка повтора, без серверной витрины",
    $("#main").innerHTML.includes("Повторить загрузку") && !$("#main").innerHTML.includes("источник: СУБД (сервер)"));
  E("showPage('ai',true)");
  ok("10.4 fallback MOD-AI аналогичен", $("#main").innerHTML.includes("Повторить загрузку") && !$("#main").innerHTML.includes("СЕРВЕРНАЯ модель"));
  E("srvDisconnect('тест')");
  ok("10.5 srvDisconnect очищает витрины и флаг загрузки",
    E("SRV.connected===false&&SRV.kpis===null&&SRV.ai===null&&SRV._s9Stage8Loaded===false"));
  ok("10.6 после disconnect — чистый демо-рендер",
    E("!RENDERERS.kpi().includes('СЕРВЕРНЫЙ РЕЖИМ')&&!RENDERERS.ai().includes('v4.0-srv')&&!RENDERERS.kpi().includes('Повторить загрузку')"));

  /* ---------- итог ---------- */
  console.log("=== DOM-ТЕСТЫ ЭТАПА 11 (v102 · Рабочая платформа): " + FILE + " ===");
  console.log("PASS: " + pass + " · FAIL: " + fail);
  if (jsErrors.length) console.log("jsErrors: " + jsErrors.slice(0, 3).join(" | "));
  if (errs.length) console.log("Провалено:\n - " + errs.join("\n - "));
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error("КРИТИЧЕСКАЯ ОШИБКА ТЕСТА:", e); process.exit(2); });
