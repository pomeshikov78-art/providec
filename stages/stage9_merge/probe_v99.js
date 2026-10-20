/* Пробная оценка загруженного v99 (jsdom): рендер «О системе», встроенные smoke-тесты, страницы, версии.
   Запуск: cd /tmp && node /home/user/src9/probe_v99.js [файл] */
const fs = require("fs");
const { JSDOM, VirtualConsole } = require("jsdom");
const FILE = process.argv[2] || "/home/user/uploads/ais_providets_v99.html";
const html = fs.readFileSync(FILE, "utf8");

const vc = new VirtualConsole();
const jsErrors = [];
vc.on("jsdomError", e => jsErrors.push(String(e.message).slice(0, 200)));

const dom = new JSDOM(html, { runScripts: "dangerously", pretendToBeVisual: true, url: "http://localhost/", virtualConsole: vc });
const w = dom.window;

setTimeout(() => {
  const out = [];
  const T = (name, fn) => { try { out.push([name, fn()]); } catch (e) { out.push([name, "EXC: " + String(e.message).slice(0, 160)]); } };

  T("jsErrors при загрузке", () => jsErrors.length ? jsErrors.slice(0, 5).join(" | ") : "нет");
  T("typeof RENDERERS.about", () => w.eval("typeof RENDERERS.about"));
  T("about(): длина", () => w.eval("RENDERERS.about().length"));
  T("about(): начинается с page-head", () => w.eval("/page-head|О системе · АИС/.test(RENDERERS.about().slice(0,300))"));
  T("about(): содержит «История версий»", () => w.eval("RENDERERS.about().includes('История версий')"));
  T("about(): содержит строку v82", () => w.eval("RENDERERS.about().includes('v82.0.0')"));
  T("about(): содержит строку v49", () => w.eval("RENDERERS.about().includes('v49.0.0')"));
  T("about(): содержит строку v1.0.0", () => w.eval("RENDERERS.about().includes('v1.0.0')"));
  T("about(): содержит P0-карточки (SBOM)", () => w.eval("RENDERERS.about().includes('P0.18')"));
  T("about(): содержит архитектуру (Microkernel)", () => w.eval("RENDERERS.about().includes('Microkernel')"));
  T("about(): первые 200 символов", () => w.eval("RENDERERS.about().slice(0,200)"));

  T("smoke: всего/прошло", () => {
    const r = w.eval("runClientRegressionSmokeTests()");
    return r.summary.total + "/" + r.summary.passed + (r.summary.failed ? " FAIL: " + r.tests.filter(t => t.result === "FAIL").map(t => t.id + " — " + t.detail).join("; ") : "");
  });

  T("демо-вход + 22 страницы", () => {
    w.eval("loginRole='L7'; state.userName='Тест'; state.role=ROLES.find(r=>r.id==='L7'); enterApp();");
    const pages = ["dashboard","registry","bus","ivp","audit","db","pass","prof","niokr","geo","comp","coop","risk","report","int","tasks","variants","raci","plan","roadmap","kpi","ai","doc","expert","stim","about"];
    const bad = [];
    pages.forEach(p => { try { w.eval("showPage('" + p + "',true)"); } catch (e) { bad.push(p + ":" + e.message.slice(0, 80)); } });
    return bad.length ? "ОШИБКИ: " + bad.join(" | ") : "все " + pages.length + " OK";
  });

  T("roadmap: панель ворот выпуска", () => w.eval("showPage('roadmap',true); !!document.getElementById('releaseGateDecision') || !!document.getElementById('releaseGates')"));
  T("db: самодиагностика снимков", () => { try { const r = w.eval("dbRunSelfTests(); DB_LAST_SELF_TEST_REPORT ? DB_LAST_SELF_TEST_REPORT.passed + '/' + DB_LAST_SELF_TEST_REPORT.total : 'нет отчёта'"); return r; } catch (e) { return "EXC " + e.message.slice(0, 120); } });
  T("версия login-head", () => (w.document.querySelector(".login-head div div") || {}).textContent || "нет");
  T("версия login-note", () => ((w.document.querySelector(".login-note") || {}).textContent || "").slice(0, 120));
  T("снимки/настройки: функции", () => w.eval("[typeof exportDB, typeof previewDBRestore, typeof dbRunSelfTests, typeof exportLiveStateIntegrityReport, typeof buildP0EvidenceSummary].join(',')"));

  console.log("=== ПРОБА " + FILE + " ===");
  out.forEach(([n, v]) => console.log("· " + n + ": " + v));
  process.exit(0);
}, 1500);
