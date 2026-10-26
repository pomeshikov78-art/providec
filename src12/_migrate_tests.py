#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Одноразовая миграция тестовой обвязки v102 → v103 (Этап 12)."""
import glob
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---------- 1. test_dom_v103.js ----------
s = (ROOT / "src11/test_dom_v102.js").read_text(encoding="utf-8")
s = s.replace("DOM-тесты Этапа 11 (jsdom): программа v102.0.0 = v101.0.0 + выпуск «Рабочая платформа» (фикс Д-10).",
              "DOM-тесты Этапа 12 (jsdom): программа v103.0.0 = v102.0.0 + серверная персистентность базовых операций.")
s = s.replace("test_dom_v102.js", "test_dom_v103.js")
s = s.replace("src11/test_dom_v103.js", "src12/test_dom_v103.js")
s = s.replace("ais_providets_v102.html", "ais_providets_v103.html")
s = s.replace("=== DOM-ТЕСТЫ ЭТАПА 11 (v102 · Рабочая платформа): ", "=== DOM-ТЕСТЫ ЭТАПА 12 (v103 · Персистентность): ")
s = s.replace('ok("4.8 история: 81 строка (v102→v1), факт " + rows.length, rows.length === 81);',
              'ok("4.8 история: 82 строки (v103→v1), факт " + rows.length, rows.length === 82);')
s = s.replace('''ok("4.9 порядок: v102 → v101 → v100 → v82 → v49 → v1",
    about.indexOf(">v102.0.0<") < about.indexOf(">v101.0.0<") && about.indexOf(">v101.0.0<") < about.indexOf(">v100.0.0<") && about.indexOf(">v100.0.0<") < about.indexOf(">v82.0.0<") && about.indexOf(">v82.0.0<") < about.indexOf(">v49.0.0<") && about.indexOf(">v49.0.0<") < about.indexOf(">v1.0.0<"));''',
              '''ok("4.9 порядок: v103 → v102 → v101 → v100 → v82 → v49 → v1",
    about.indexOf(">v103.0.0<") < about.indexOf(">v102.0.0<") && about.indexOf(">v102.0.0<") < about.indexOf(">v101.0.0<") && about.indexOf(">v101.0.0<") < about.indexOf(">v100.0.0<") && about.indexOf(">v100.0.0<") < about.indexOf(">v82.0.0<") && about.indexOf(">v82.0.0<") < about.indexOf(">v49.0.0<") && about.indexOf(">v49.0.0<") < about.indexOf(">v1.0.0<"));''')
s = s.replace('ok("4.13 запись v102 описывает дефект Д-10 и живые испытания", about.includes("Д-10") && about.includes("живым протоколом"));',
              'ok("4.13 запись v102 описывает дефект Д-10 и живые испытания", about.includes("Д-10") && about.includes("живым протоколом"));\n  ok("4.14 запись v103 описывает Этап 12 (персистентность)", about.includes("Этап 12") && about.includes("персистентность"));')
s = s.replace("smoke.summary.failed === 0 && smoke.summary.total >= 26);",
              "smoke.summary.failed === 0 && smoke.summary.total >= 30);")
s = s.replace('["REL-VER-02","A11Y-01","NAV-01","DL-01","GEO-SRI-01","SRV-LOGIN-01"]',
              '["REL-VER-02","A11Y-01","NAV-01","DL-01","GEO-SRI-01","SRV-LOGIN-01","SRV-DL-01","SRV-PASS-01","SRV-REPORT-01","SRV-TWIN-01"]')
s = s.replace("snap.program).toBe('v102.0.0')", "snap.program).toBe('v103.0.0')") if "snap.program).toBe('v102.0.0')" in s else s
# новая секция [11] перед итогом
s = s.replace('''  /* ---------- итог ---------- */''',
'''  console.log("[11] Этап 12: серверная персистентность (jsdom-срезы)...");
  /* ---------- 11. Этап 12: обёртки и fail-closed ---------- */
  ok("11.1 мост Этапа 12 установлен", E("window.__TC_STAGE12_BRIDGE===true&&savePassVersion.toString().includes('SRV.connected')&&exportReportDocx.toString().includes('srvDownload')&&recalcProfile.toString().includes('/api/v1/twins/')"));
  ok("11.2 srvDownload — закалённый Promise (эпоха, лимит, отмена)", E("srvDownload.toString().includes('LOGIN_ATTEMPT_SUPERSEDED')&&srvDownload.toString().includes('SRV_DOWNLOAD_MAX_BYTES')&&srvDownload.toString().includes('SRV_ACTIVE_REQUESTS')"));
  installMock([]); // все маршруты → 404
  E("SRV.connected=true;SRV.token='t';SRV.sessionEpoch=9;SRV.url='';state.selEnt='E01';state.passEdit['E01']=true;showPage('pass',true);");
  await delay(300);
  E("savePassVersion('E01')");
  await delay(500);
  ok("11.3 отказ сервера при сохранении паспорта — fail-closed (ошибка, оверлей пуст)",
    E("(function(){const t=document.getElementById('toasts').lastElementChild;const ov=state.passOv['E01']||{};const keys=Object.keys(ov).filter(k=>k!=='__s12Synced');return !!t&&/отклонил|недоступен|Не удалось/.test(t.textContent)&&keys.length===0;})()"));
  installMock([]);
  E("SRV.connected=false;SRV.token=null;showPage('pass',true);");
  E("(function(){const i=Array.from(document.querySelectorAll('.pf-in')).find(x=>x.tagName==='INPUT');if(i){i.value='ДЕМО-ПРОВЕРКА-'+Date.now();}})()");
  E("savePassVersion('E01')");
  await delay(200);
  ok("11.4 демо-режим: сохранение паспорта локальное, без обращений к серверу",
    fetchCalls.length === 0 && E("Object.keys(state.passOv['E01']||{}).filter(k=>k!=='__s12Synced').length>0"));

  /* ---------- итог ---------- */''')
(ROOT / "src12/test_dom_v103.js").write_text(s, encoding="utf-8")
print("записан src12/test_dom_v103.js")

# ---------- 2. verify_v103.sh ----------
v = (ROOT / "src11/verify_v102.sh").read_text(encoding="utf-8")
v = v.replace("verify_v102.sh — статическая верификация ais_providets_v102.html",
              "verify_v103.sh — статическая верификация ais_providets_v103.html")
v = v.replace("по критериям Волны 0 + выпуска «Рабочая платформа» (фикс Д-10).",
              "по критериям Волны 0 + выпусков «Рабочая платформа» (Д-10) и «Персистентность» (Этап 12).")
v = v.replace("sh src11/verify_v102.sh", "sh src12/verify_v103.sh")
v = v.replace("F=ais_providets_v102.html", "F=ais_providets_v103.html")
v = v.replace("python3 src11/patch_v102.py", "python3 src12/patch_v103.py")
v = v.replace('const APP_VERSION=Object.freeze({major:102,minor:0,patch:0,str:"v102.0.0"',
              'const APP_VERSION=Object.freeze({major:103,minor:0,patch:0,str:"v103.0.0"')
v = v.replace('ok "0.1 константа APP_VERSION определена (v102.0.0)"', 'ok "0.1 константа APP_VERSION определена (v103.0.0)"')
v = v.replace("""N=$(grep -o 'v101\\.0\\.0' "$F" | wc -l | tr -d ' ')
[ "$N" = "3" ] && ok "0.1 исторических упоминаний v101.0.0 ровно 3 (история+2 комментария)" || bad "0.1 v101.0.0: $N (ожидалось 3)\"""",
              """N=$(grep -o 'v101\\.0\\.0' "$F" | wc -l | tr -d ' ')
[ "$N" = "3" ] && ok "0.1 исторических упоминаний v101.0.0 ровно 3" || bad "0.1 v101.0.0: $N (ожидалось 3)"
N=$(grep -o 'v102\\.0\\.0' "$F" | wc -l | tr -d ' ')
[ "$N" = "1" ] && ok "0.1 исторических упоминаний v102.0.0 ровно 1 (запись истории)" || bad "0.1 v102.0.0: $N (ожидалось 1)\"""")
v = v.replace('content="v102.0.0">"$F"', 'content="v103.0.0">"$F"')
v = v.replace('grep -q \'<meta name="providets-release-version" content="v102.0.0">\' "$F"',
              'grep -q \'<meta name="providets-release-version" content="v103.0.0">\' "$F"')
v = v.replace('ok "0.2 meta содержит актуальную версию v102.0.0"', 'ok "0.2 meta содержит актуальную версию v103.0.0"')
v = v.replace("""grep -q '\\["v102.0.0","26.10.2026"' "$F" \\""", """grep -q '\\["v103.0.0","26.10.2026"' "$F" \\""")
v = v.replace('ok "0.8 запись v102 в истории версий «О системе»"', 'ok "0.8 запись v103 в истории версий «О системе»"')
v = v.replace('bad "0.8 нет записи v102 в истории"', 'bad "0.8 нет записи v103 в истории"')
v = v.replace("CHANGELOG: запись v102", "CHANGELOG: запись v103").replace("CHANGELOG без v102", "CHANGELOG без v103")
v = v.replace("grep -q '## \\[102\\.0\\.0\\]' CHANGELOG.md", "grep -q '## \\[103\\.0\\.0\\]' CHANGELOG.md")
v = v.replace("""# --- синтаксис всех <script>-блоков""",
              """# --- Этап 12 (v103): серверная персистентность --------------------------------
grep -q '__TC_STAGE12_BRIDGE=true' "$F" \\
  && ok "Э12 мост установлен (window-флаг)" || bad "Э12 нет маркера моста"
grep -q 'SRV_DOWNLOAD_MAX_BYTES' "$F" \\
  && ok "Э12 srvDownload: лимит размера константой" || bad "Э12 нет лимита загрузки"
grep -q 'savePassVersion=function(id){' "$F" \\
  && ok "Э12 обёртка savePassVersion (PUT /orgs/{id}/passport)" || bad "Э12 нет обёртки savePassVersion"
grep -q "'/api/v1/twins/'" "$F" \\
  && ok "Э12 пересборка двойника на сервере" || bad "Э12 нет моста двойника"
grep -q "/passport/quality" "$F" \\
  && ok "Э12 серверный контроль качества паспорта" || bad "Э12 нет моста качества"
grep -q "check('SRV-DL-01'" "$F" && grep -q "check('SRV-PASS-01'" "$F" && grep -q "check('SRV-REPORT-01'" "$F" && grep -q "check('SRV-TWIN-01'" "$F" \\
  && ok "Э12 smoke-контроль (SRV-DL/PASS/REPORT/TWIN-01)" || bad "Э12 нет smoke-контроля"

# --- синтаксис всех <script>-блоков""")
v = v.replace("== Верификация $F (Волна 0 + Д-10, критерии 0.1–0.8) ==", "== Верификация $F (Волна 0 + Д-10 + Этап 12) ==")
v = v.replace("'ВСЕ КРИТЕРИИ ВЫПОЛНЕНЫ (Волна 0 + Д-10)'", "'ВСЕ КРИТЕРИИ ВЫПОЛНЕНЫ (Волна 0 + Д-10 + Этап 12)'")
(ROOT / "src12/verify_v103.sh").write_text(v, encoding="utf-8")
print("записан src12/verify_v103.sh")

# ---------- 3. E2E + конфиги: v103 ----------
files = glob.glob(str(ROOT / "tests/e2e/*.js")) + [str(ROOT / "tests/playwright.config.js"),
          str(ROOT / "tests/README.md"), str(ROOT / "src10/live_protocol.py")]
for f in files:
    p = Path(f); t = p.read_text(encoding="utf-8"); orig = t
    t = t.replace("ais_providets_v102.html", "ais_providets_v103.html")
    if f.endswith("live_protocol.py"):
        t = t.replace('PROGRAM = "v102.0.0"', 'PROGRAM = "v103.0.0"')
    if t != orig:
        p.write_text(t, encoding="utf-8"); print("обновлён:", p.relative_to(ROOT))

p = ROOT / "tests/e2e/01-load-login.spec.js"; t = p.read_text(encoding="utf-8")
t = t.replace("'v102.0.0'", "'v103.0.0'").replace("программа v102.0.0", "программа v103.0.0").replace("версии 102.0.0", "версии 103.0.0")
p.write_text(t, encoding="utf-8"); print("01-load-login: версии → v103")

p = ROOT / "tests/e2e/06-db-snapshots.spec.js"; t = p.read_text(encoding="utf-8")
t = t.replace("toBe('v102.0.0')", "toBe('v103.0.0')")
p.write_text(t, encoding="utf-8"); print("06-db-snapshots: версии → v103")

p = ROOT / "tests/e2e/08-geo-evidence.spec.js"; t = p.read_text(encoding="utf-8")
old = """test('8.5 «О системе»: история версий v102 → v101 → v100 → v82', async ({ page }) => {
  await login(page, 'L7');
  await page.evaluate(() => showPage('about', true));
  const html = await page.evaluate(() => document.getElementById('main').innerHTML);
  const i102 = html.indexOf('>v102.0.0<');
  const i101 = html.indexOf('>v101.0.0<');
  const i100 = html.indexOf('>v100.0.0<');
  const i82 = html.indexOf('>v82.0.0<');
  expect(i102).toBeGreaterThan(-1);
  expect(i102).toBeLessThan(i101);
  expect(i101).toBeLessThan(i100);
  expect(i100).toBeLessThan(i82);
  expect(html).toContain('Д-10');
  expect(html).toContain('Волна 0 плана улучшений');
  await expect(page.locator('#main')).toContainText('программа v102.0.0');
});"""
new = """test('8.5 «О системе»: история версий v103 → v102 → v101 → v100 → v82', async ({ page }) => {
  await login(page, 'L7');
  await page.evaluate(() => showPage('about', true));
  const html = await page.evaluate(() => document.getElementById('main').innerHTML);
  const i103 = html.indexOf('>v103.0.0<');
  const i102 = html.indexOf('>v102.0.0<');
  const i101 = html.indexOf('>v101.0.0<');
  const i100 = html.indexOf('>v100.0.0<');
  const i82 = html.indexOf('>v82.0.0<');
  expect(i103).toBeGreaterThan(-1);
  expect(i103).toBeLessThan(i102);
  expect(i102).toBeLessThan(i101);
  expect(i101).toBeLessThan(i100);
  expect(i100).toBeLessThan(i82);
  expect(html).toContain('Этап 12');
  expect(html).toContain('Д-10');
  await expect(page.locator('#main')).toContainText('программа v103.0.0');
});"""
assert old in t, "8.5 anchor"
t = t.replace(old, new)
t = t.replace("expect(rep.summary.total).toBeGreaterThanOrEqual(26);", "expect(rep.summary.total).toBeGreaterThanOrEqual(30);")
t = t.replace("expect(rep.program).toBe('v102.0.0');", "expect(rep.program).toBe('v103.0.0');")
t = t.replace("['REL-VER-01', 'REL-VER-02', 'A11Y-01', 'NAV-01', 'DL-01', 'GEO-SRI-01', 'SRV-LOGIN-01']",
              "['REL-VER-01', 'REL-VER-02', 'A11Y-01', 'NAV-01', 'DL-01', 'GEO-SRI-01', 'SRV-LOGIN-01', 'SRV-DL-01', 'SRV-PASS-01', 'SRV-REPORT-01', 'SRV-TWIN-01']")
p.write_text(t, encoding="utf-8"); print("08-geo-evidence: 8.5/8.6 → v103")
print("МИГРАЦИЯ v103 ЗАВЕРШЕНА")
