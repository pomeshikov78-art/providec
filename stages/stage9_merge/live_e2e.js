/* E2E Этапа 9: объединённый клиент (v100) ↔ реальный бэкенд (uvicorn :8000).
   Запуск: сначала поднять бэкенд, затем
   cd /tmp && node -e "process.argv[2]='/home/user/ais_providets.html'; require('/home/user/src9/live_e2e.js')" */
const fs = require("fs");
const { JSDOM, VirtualConsole } = require("jsdom");
const FILE = process.argv[2] || "/home/user/ais_providets.html";
const BASE = process.env.TC_E2E_BASE || "http://127.0.0.1:8000";

let pass = 0, fail = 0; const errs = [];
function ok(name, cond, extra) { if (cond) pass++; else { fail++; errs.push(name + (extra ? " [" + extra + "]" : "")); } }
const delay = ms => new Promise(r => setTimeout(r, ms));

const vc = new VirtualConsole();
const jsErrors = [];
vc.on("jsdomError", e => jsErrors.push(String(e.message).slice(0, 160)));
const dom = new JSDOM(fs.readFileSync(FILE, "utf8"), { runScripts: "dangerously", pretendToBeVisual: true, url: "http://localhost/", virtualConsole: vc });
const w = dom.window;
const E = x => w.eval(x);

(async function main() {
  await delay(1500);
  // реальный fetch Node 20 → в окно jsdom
  w.fetch = (u, o) => globalThis.fetch(u, o);

  /* ---- 1. серверный вход (regulator, L2 — по live_stage8 обладает kpi.recalc/ai.run/expert.*) ---- */
  w.document.getElementById("srvUrl").value = BASE;
  w.document.getElementById("srvLogin").value = "regulator";
  w.document.getElementById("srvPass").value = "tc-reg-2026";
  let loginErr = null;
  try { await E("srvTryLogin()"); } catch (e) { loginErr = String(e && e.message || e); }
  ok("1 вход regulator на реальный бэкенд", E("SRV.connected===true") && loginErr === null, loginErr || "");
  ok("2 роль L2 и ФИО от IAM", E("SRV.role==='L2'"), E("SRV.role"));

  /* ---- 2. enterApp → ленивая загрузка витрин KPI/AI с сервера ---- */
  E("loginRole=SRV.role; state.userName=SRV.fio||'Регулятор'; state.role=ROLES.find(r=>r.id===SRV.role)||state.role; enterApp();");
  await delay(1200);
  ok("3 SRV.kpis загружен с сервера (8 показателей)", E("!!SRV.kpis&&SRV.kpis.items&&SRV.kpis.items.length===8"), E("SRV.kpis?SRV.kpis.items.length:'null'"));
  ok("4 SRV.ai загружен", E("SRV.ai!==null&&typeof SRV.ai==='object'"));
  E("showPage('kpi',true)");
  const kpiHtml = w.document.getElementById("main").innerHTML;
  ok("5 витрина KPI в серверном режиме", kpiHtml.includes("СЕРВЕРНЫЙ РЕЖИМ") && kpiHtml.includes("Регламентный пересчёт"));

  /* ---- 3. регламентный пересчёт KPI через UI-функцию ---- */
  E("srvKpiRecalc()"); await delay(1200);
  ok("6 пересчёт KPI: аудит + событие при отклонении", E("state.audit.some(a=>a.action==='Пересчет KPI (сервер)')"));
  ok("7 KPI-3 отклонение → kpi.threshold_breached (live_stage8 шаг 2)", E("state.events.some(e=>e.type==='kpi.threshold_breached')"));
  ok("8 MOD-STIM: авто-санкция подтянута в STIMS", E("STIMS.some(s=>(s.t||'').includes('Эскалация'))"));

  /* ---- 4. AI: прогнозный цикл ---- */
  E("runAI()"); await delay(1500);
  ok("9 AI-прогон: run_id AIR-* и модель v4.0-srv", E("!!SRV.ai&&/^AIR-/.test(SRV.ai.run_id||'')&&SRV.ai.model==='v4.0-srv'"), E("SRV.ai&&SRV.ai.run_id"));
  ok("10 AI: рекомендации опубликованы (conf ≥ 0.7)", E("(SRV.ai.recommendations||[]).length>0"));

  /* ---- 5. RBAC-негатив: регулятор (L2) не имеет expert.approve ---- */
  const queue = await E("srvApi('/api/v1/expert')");
  const queued = (queue.items || []).find(x => x.status === "queued");
  const qid = queued ? queued.id : null;
  ok("11 очередь экспертизы получена с сервера (" + (queue.items || []).length + " пункт.)", !!qid, qid || "нет queued-пункта");
  if (qid) {
    E("assignExpert('" + qid + "')"); await delay(900);
    ok("12 L2: назначение эксперта разрешено (expert.assign)", E("state.events.some(e=>e.type==='expert.assigned')"));
    E("conclude('" + qid + "')"); await delay(1000);
    const qMid = await E("srvApi('/api/v1/expert')");
    const itMid = (qMid.items || []).find(x => x.id === qid);
    ok("13 RBAC: заключение L2 отклонено сервером 403 (события по " + qid + " нет, пункт in_review)",
      E("!state.events.some(e=>e.type==='expert.conclusion_ready'&&(e.payload||'').includes('" + qid + "'))") && itMid && itMid.status === "in_review", itMid && itMid.status);

    /* ---- 6. сессия 2: аналитик (L5) — expert.approve разрешён ---- */
    E("srvDisconnect('смена роли для E2E')");
    w.document.getElementById("srvLogin").value = "analyst";
    w.document.getElementById("srvPass").value = "tc-analyst-2026";
    let loginErr2 = null;
    try { await E("srvTryLogin()"); } catch (e) { loginErr2 = String(e && e.message || e); }
    ok("14 вход analyst (L5)", E("SRV.connected===true&&SRV.role==='L5'"), loginErr2 || "");
    E("loginRole=SRV.role; state.userName=SRV.fio||'Аналитик'; state.role=ROLES.find(r=>r.id===SRV.role)||state.role; enterApp();");
    await delay(1200);
    ok("15 витрины KPI/AI перезагружены в сессии L5", E("!!SRV.kpis&&!!SRV.kpis.items"));
    E("conclude('" + qid + "')"); await delay(1300);
    ok("16 заключение L5: событие expert.conclusion_ready по " + qid, E("state.events.some(e=>e.type==='expert.conclusion_ready'&&(e.payload||'').includes('" + qid + "'))"));
    const q2 = await E("srvApi('/api/v1/expert')");
    const it2 = (q2.items || []).find(x => x.id === qid);
    ok("17 сервер: пункт " + qid + " в статусе done", it2 && it2.status === "done", it2 && it2.status);
  } else { fail += 7; errs.push("12–17 пропущены — нет queued-пункта"); }

  /* ---- 7. DOC: реестр документов с сервера ---- */
  const docs = await E("srvApi('/api/v1/documents')");
  const d0 = (docs.items || [])[0];
  ok("18 реестр документов с сервера (D-2026-*)", !!d0 && /^D-2026-/.test(d0.id), d0 && d0.id);

  /* ---- 8. выход: очистка сессии ---- */
  E("srvDisconnect('E2E завершён')");
  ok("19 srvDisconnect: сессия и витрины очищены", E("SRV.connected===false&&SRV.kpis===null&&SRV.ai===null"));

  console.log("=== E2E КЛИЕНТ↔БЭКЕНД (Этап 9): " + BASE + " ===");
  console.log("PASS: " + pass + " · FAIL: " + fail);
  if (jsErrors.length) console.log("jsErrors: " + jsErrors.slice(0, 3).join(" | "));
  if (errs.length) console.log("Провалено:\n - " + errs.join("\n - "));
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error("КРИТИЧЕСКАЯ ОШИБКА E2E:", e); process.exit(2); });
