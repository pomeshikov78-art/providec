#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Одноразовая миграция тестовой обвязки v101 → v102 (Этап 11)."""
import glob
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---------- 1. test_dom_v102.js ----------
s = (ROOT / "src10/test_dom_v101.js").read_text(encoding="utf-8")
s = s.replace("DOM-тесты Этапа 10 (jsdom): программа v101.0.0 = v100.0.0 + Волна 0 плана улучшений (P3.1–P3.8).",
              "DOM-тесты Этапа 11 (jsdom): программа v102.0.0 = v101.0.0 + выпуск «Рабочая платформа» (фикс Д-10).")
s = s.replace("test_dom_v101.js", "test_dom_v102.js")
s = s.replace("src10/test_dom_v102.js", "src11/test_dom_v102.js")
s = s.replace("ais_providets_v101.html", "ais_providets_v102.html")
s = s.replace("=== DOM-ТЕСТЫ ЭТАПА 10 (v101 · Волна 0): ", "=== DOM-ТЕСТЫ ЭТАПА 11 (v102 · Рабочая платформа): ")
s = s.replace('ok("4.8 история: 80 строк (v101→v1), факт " + rows.length, rows.length === 80);',
              'ok("4.8 история: 81 строка (v102→v1), факт " + rows.length, rows.length === 81);')
s = s.replace('''ok("4.9 порядок: v101 → v100 → v82 → v49 → v1",
    about.indexOf(">v101.0.0<") < about.indexOf(">v100.0.0<") && about.indexOf(">v100.0.0<") < about.indexOf(">v82.0.0<") && about.indexOf(">v82.0.0<") < about.indexOf(">v49.0.0<") && about.indexOf(">v49.0.0<") < about.indexOf(">v1.0.0<"));''',
              '''ok("4.9 порядок: v102 → v101 → v100 → v82 → v49 → v1",
    about.indexOf(">v102.0.0<") < about.indexOf(">v101.0.0<") && about.indexOf(">v101.0.0<") < about.indexOf(">v100.0.0<") && about.indexOf(">v100.0.0<") < about.indexOf(">v82.0.0<") && about.indexOf(">v82.0.0<") < about.indexOf(">v49.0.0<") && about.indexOf(">v49.0.0<") < about.indexOf(">v1.0.0<"));''')
s = s.replace('ok("4.12 запись v101 описывает Волну 0", about.includes("Волна 0 плана улучшений"));',
              'ok("4.12 запись v101 описывает Волну 0", about.includes("Волна 0 плана улучшений"));\n  ok("4.13 запись v102 описывает Д-10 и живые испытания", about.includes("Д-10") && about.includes("живым протоколом"));')
s = s.replace("smoke.summary.failed === 0 && smoke.summary.total >= 25);",
              "smoke.summary.failed === 0 && smoke.summary.total >= 26);")
s = s.replace('["REL-VER-02","A11Y-01","NAV-01","DL-01","GEO-SRI-01"]',
              '["REL-VER-02","A11Y-01","NAV-01","DL-01","GEO-SRI-01","SRV-LOGIN-01"]')
s = s.replace('''ok("w.22 P3.1: экспорты/отчёты используют ver() (выборка)",''',
              '''ok("w.22 Д-10: обёртка входа передаёт снимок пароля в srvTryLogin(presetPassword)",
    E("doLogin.toString().includes('passSnapshot')&&srvTryLogin.toString().includes('presetPassword')&&srvTryLogin.length===1"));
  ok("w.23 P3.1: экспорты/отчёты используют ver() (выборка)",''')
(ROOT / "src11/test_dom_v102.js").write_text(s, encoding="utf-8")
print("записан src11/test_dom_v102.js")

# ---------- 2. verify_v102.sh ----------
v = (ROOT / "src10/verify_v101.sh").read_text(encoding="utf-8")
v = v.replace("verify_v101.sh — статическая верификация ais_providets_v101.html",
              "verify_v102.sh — статическая верификация ais_providets_v102.html")
v = v.replace("по критериям приёмки Волны 0 плана улучшений (plan_uluchsheniy_v100.md).",
              "по критериям Волны 0 + выпуска «Рабочая платформа» (фикс Д-10).")
v = v.replace("sh src10/verify_v101.sh", "sh src11/verify_v102.sh")
v = v.replace("F=ais_providets_v101.html", "F=ais_providets_v102.html")
v = v.replace("python3 src10/patch_v101.py", "python3 src11/patch_v102.py")
v = v.replace('const APP_VERSION=Object.freeze({major:101,minor:0,patch:0,str:"v101.0.0"',
              'const APP_VERSION=Object.freeze({major:102,minor:0,patch:0,str:"v102.0.0"')
v = v.replace('ok "0.1 константа APP_VERSION определена (v101.0.0)"', 'ok "0.1 константа APP_VERSION определена (v102.0.0)"')
v = v.replace("""N=$(grep -o 'program:"v100\\.0\\.0"' "$F" | wc -l | tr -d ' ')""",
              """N=$(grep -oE 'program:"v10[0-9]\\.0\\.0"' "$F" | wc -l | tr -d ' ')""")
v = v.replace("""N=$(grep -o '_v100\\.json' "$F" | wc -l | tr -d ' ')""",
              """N=$(grep -oE '_v10[0-9]\\.json' "$F" | wc -l | tr -d ' ')""")
v = v.replace("""N=$(grep -o 'version:"v100\\.0\\.0"' "$F" | wc -l | tr -d ' ')""",
              """N=$(grep -oE 'version:"v10[0-9]\\.0\\.0"' "$F" | wc -l | tr -d ' ')""")
v = v.replace("""N=$(grep -o 'v100\\.0\\.0' "$F" | wc -l | tr -d ' ')
[ "$N" = "2" ] && ok "0.1 исторических упоминаний v100.0.0 ровно 2 (история+комментарий)" || bad "0.1 неожиданных упоминаний v100.0.0: $N (ожидалось 2)\"""",
              """N=$(grep -o 'v100\\.0\\.0' "$F" | wc -l | tr -d ' ')
[ "$N" = "2" ] && ok "0.1 исторических упоминаний v100.0.0 ровно 2" || bad "0.1 v100.0.0: $N (ожидалось 2)"
N=$(grep -o 'v101\\.0\\.0' "$F" | wc -l | tr -d ' ')
[ "$N" = "3" ] && ok "0.1 исторических упоминаний v101.0.0 ровно 3 (история+2 комментария)" || bad "0.1 v101.0.0: $N (ожидалось 3)\"""")
v = v.replace('content="v101.0.0">"$F"', 'content="v102.0.0">"$F"')
v = v.replace('grep -q \'<meta name="providets-release-version" content="v101.0.0">\' "$F"',
              'grep -q \'<meta name="providets-release-version" content="v102.0.0">\' "$F"')
v = v.replace("ok \"0.2 meta содержит актуальную версию v101.0.0\"", "ok \"0.2 meta содержит актуальную версию v102.0.0\"")
v = v.replace("""grep -q '\\["v101.0.0","26.10.2026"' "$F" \\""", """grep -q '\\["v102.0.0","26.10.2026"' "$F" \\""")
v = v.replace('ok "0.8 запись v101 в истории версий «О системе»"', 'ok "0.8 запись v102 в истории версий «О системе»"')
v = v.replace('bad "0.8 нет записи v101 в истории"', 'bad "0.8 нет записи v102 в истории"')
v = v.replace("CHANGELOG: запись v101", "CHANGELOG: запись v102").replace("CHANGELOG без v101", "CHANGELOG без v102")
v = v.replace("grep -q '## \\[101\\.0\\.0\\]' CHANGELOG.md", "grep -q '## \\[102\\.0\\.0\\]' CHANGELOG.md")
v = v.replace("""# --- синтаксис всех <script>-блоков""",
              """# --- Д-10 (v102): серверный вход — снимок пароля до очистки полей --------------
grep -q 'const passSnapshot=passEl?String(passEl.value' "$F" \\
  && ok "Д-10 passSnapshot снимается до prepareServerLoginAttempt" || bad "Д-10 passSnapshot не найден"
grep -q 'srvTryLogin(passSnapshot)' "$F" \\
  && ok "Д-10 обёртка передаёт снимок в srvTryLogin" || bad "Д-10 снимок не передаётся"
grep -q 'async function srvTryLogin(presetPassword){' "$F" \\
  && ok "Д-10 srvTryLogin(presetPassword)" || bad "Д-10 srvTryLogin без параметра"
grep -q "check('SRV-LOGIN-01'" "$F" \\
  && ok "Д-10 smoke-контроль SRV-LOGIN-01" || bad "Д-10 нет smoke-контроля"

# --- синтаксис всех <script>-блоков""")
v = v.replace("== Верификация $F (Волна 0, критерии 0.1–0.8) ==", "== Верификация $F (Волна 0 + Д-10, критерии 0.1–0.8) ==")
v = v.replace("'ВСЕ КРИТЕРИИ ВОЛНЫ 0 ВЫПОЛНЕНЫ'", "'ВСЕ КРИТЕРИИ ВЫПОЛНЕНЫ (Волна 0 + Д-10)'")
(ROOT / "src11/verify_v102.sh").write_text(v, encoding="utf-8")
print("записан src11/verify_v102.sh")

# ---------- 3. E2E + конфиги: v102 ----------
files = glob.glob(str(ROOT / "tests/e2e/*.js")) + [str(ROOT / "tests/playwright.config.js"),
          str(ROOT / "tests/README.md"), str(ROOT / "src10/live_protocol.py")]
for f in files:
    p = Path(f); t = p.read_text(encoding="utf-8"); orig = t
    t = t.replace("ais_providets_v101.html", "ais_providets_v102.html")
    if f.endswith("live_protocol.py"):
        t = t.replace('PROGRAM = "v101.0.0"', 'PROGRAM = "v102.0.0"')
    if t != orig:
        p.write_text(t, encoding="utf-8"); print("обновлён:", p.relative_to(ROOT))

p = ROOT / "tests/e2e/01-load-login.spec.js"; t = p.read_text(encoding="utf-8")
t = t.replace("toHaveAttribute('content', 'v101.0.0')", "toHaveAttribute('content', 'v102.0.0')")
t = t.replace("toContainText('программа v101.0.0')", "toContainText('программа v102.0.0')")
t = t.replace("toContainText('версии 101.0.0')", "toContainText('версии 102.0.0')")
t = t.replace("ver())).toBe('v101.0.0')", "ver())).toBe('v102.0.0')")
t = t.replace("APP_VERSION.str)).toBe('v101.0.0')", "APP_VERSION.str)).toBe('v102.0.0')")
p.write_text(t, encoding="utf-8"); print("обновлён: 01-load-login (версии)")

p = ROOT / "tests/e2e/06-db-snapshots.spec.js"; t = p.read_text(encoding="utf-8")
t = t.replace("snap.program).toBe('v101.0.0')", "snap.program).toBe('v102.0.0')")
t = t.replace("rep.program).toBe('v101.0.0')", "rep.program).toBe('v102.0.0')")
p.write_text(t, encoding="utf-8"); print("обновлён: 06-db-snapshots (версии)")

p = ROOT / "tests/e2e/08-geo-evidence.spec.js"; t = p.read_text(encoding="utf-8")
old85 = """test('8.5 «О системе»: история версий v101 → v100 → v82, запись v101 описывает Волну 0', async ({ page }) => {
  await login(page, 'L7');
  await page.evaluate(() => showPage('about', true));
  const html = await page.evaluate(() => document.getElementById('main').innerHTML);
  const i101 = html.indexOf('>v101.0.0<');
  const i100 = html.indexOf('>v100.0.0<');
  const i82 = html.indexOf('>v82.0.0<');
  expect(i101).toBeGreaterThan(-1);
  expect(i101).toBeLessThan(i100);
  expect(i100).toBeLessThan(i82);
  expect(html).toContain('Волна 0 плана улучшений');
  await expect(page.locator('#main')).toContainText('программа v101.0.0');
});"""
new85 = """test('8.5 «О системе»: история версий v102 → v101 → v100 → v82', async ({ page }) => {
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
assert old85 in t, "8.5 anchor not found"
t = t.replace(old85, new85)
t = t.replace("expect(rep.summary.total).toBeGreaterThanOrEqual(25);", "expect(rep.summary.total).toBeGreaterThanOrEqual(26);")
t = t.replace("expect(rep.program).toBe('v101.0.0');", "expect(rep.program).toBe('v102.0.0');")
t = t.replace("['REL-VER-01', 'REL-VER-02', 'A11Y-01', 'NAV-01', 'DL-01', 'GEO-SRI-01']",
              "['REL-VER-01', 'REL-VER-02', 'A11Y-01', 'NAV-01', 'DL-01', 'GEO-SRI-01', 'SRV-LOGIN-01']")
p.write_text(t, encoding="utf-8"); print("обновлён: 08-geo-evidence (8.5 + smoke)")
print("МИГРАЦИЯ ЗАВЕРШЕНА")
