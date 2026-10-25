#!/bin/sh
# ============================================================================
# verify_v102.sh — статическая верификация ais_providets_v102.html
# по критериям Волны 0 + выпуска «Рабочая платформа» (фикс Д-10).
# Запуск: sh src11/verify_v102.sh   (из корня репозитория)
# Дом-тесты (поведение): NODE_PATH=... node src10/test_dom_v101.js — см. README.
# ============================================================================
set -e
cd "$(dirname "$0")/.."
F=ais_providets_v102.html
FAIL=0
ok()  { printf '  ok   %s\n' "$1"; }
bad() { printf '  FAIL %s\n' "$1"; FAIL=1; }
cnt() { grep -c -- "$1" "$F" || true; }

[ -f "$F" ] || { echo "Нет файла $F — сначала выполните: python3 src11/patch_v102.py"; exit 1; }
echo "== Верификация $F (Волна 0 + Д-10, критерии 0.1–0.8) =="

# --- 0.1/P3.1 единая константа версии ---------------------------------------
grep -q 'const APP_VERSION=Object.freeze({major:102,minor:0,patch:0,str:"v102.0.0"' "$F" \
  && ok "0.1 константа APP_VERSION определена (v102.0.0)" || bad "0.1 APP_VERSION не найдена"
grep -q 'function ver(){return APP_VERSION.str;}' "$F" \
  && ok "0.1 ver()/verNum() определены" || bad "0.1 ver() не найдена"
N=$(grep -oE 'program:"v10[0-9]\.0\.0"' "$F" | wc -l | tr -d ' ')
[ "$N" = "0" ] && ok "0.1 program:\"v100.0.0\" = 0 (все отчёты через ver())" || bad "0.1 найдено $N хардкодов program"
N=$(grep -oE '_v10[0-9]\.json' "$F" | wc -l | tr -d ' ')
[ "$N" = "0" ] && ok "0.1 имена экспорта _v100.json = 0 (динамический build-суффикс)" || bad "0.1 найдено $N имён _v100.json"
N=$(grep -oE 'version:"v10[0-9]\.0\.0"' "$F" | wc -l | tr -d ' ')
[ "$N" = "0" ] && ok "0.1 SBOM: version через ver()" || bad "0.1 SBOM содержит $N хардкода"
# исторические упоминания v100.0.0: ровно 2 (массив истории + комментарий Этапа 9)
N=$(grep -o 'v100\.0\.0' "$F" | wc -l | tr -d ' ')
[ "$N" = "2" ] && ok "0.1 исторических упоминаний v100.0.0 ровно 2" || bad "0.1 v100.0.0: $N (ожидалось 2)"
N=$(grep -o 'v101\.0\.0' "$F" | wc -l | tr -d ' ')
[ "$N" = "3" ] && ok "0.1 исторических упоминаний v101.0.0 ровно 3 (история+2 комментария)" || bad "0.1 v101.0.0: $N (ожидалось 3)"

# --- 0.2/P3.2 meta-тег -------------------------------------------------------
N=$(grep -o '<meta name="providets-release-version"' "$F" | wc -l | tr -d ' ')
[ "$N" = "1" ] && ok "0.2 ровно один meta providets-release-version" || bad "0.2 meta-тегов: $N"
grep -q '<meta name="providets-release-version" content="v102.0.0">' "$F" \
  && ok "0.2 meta содержит актуальную версию v102.0.0" || bad "0.2 meta устарела"

# --- 0.3/P3.3 тосты -----------------------------------------------------------
grep -q '<div id="toasts" role="status" aria-live="polite"' "$F" \
  && ok "0.3 #toasts: role=status aria-live=polite" || bad "0.3 контейнер тостов без aria"
grep -q 'd.setAttribute("role","alert");d.setAttribute("aria-live","assertive")' "$F" \
  && ok "0.3 ошибочные тосты: alert/assertive" || bad "0.3 нет assertive для ошибок"

# --- 0.4/P3.4 нативные диалоги -------------------------------------------------
N=$(grep -oE 'window\.confirm[[:space:]]*\(' "$F" | wc -l | tr -d ' ')
[ "$N" = "0" ] && ok "0.4 window.confirm( = 0" || bad "0.4 найдено window.confirm(: $N"
N=$(grep -oE 'window\.prompt[[:space:]]*\(' "$F" | wc -l | tr -d ' ')
[ "$N" = "0" ] && ok "0.4 window.prompt( = 0" || bad "0.4 найдено window.prompt(: $N"
grep -q 'function tcDialog(opts)' "$F" && grep -q 'aria-modal' "$F" \
  && ok "0.4 tcDialog: role=dialog, aria-modal, фокус-ловушка" || bad "0.4 tcDialog не найден"
grep -q 'await tcConfirm("Восстановление демонстрационных данных' "$F" \
  && ok "0.4 восстановление снимка через tcConfirm" || bad "0.4 восстановление не через tcConfirm"
grep -q 'await tcPrompt("Двухфакторная аутентификация' "$F" \
  && ok "0.4 MFA-ввод через tcPrompt" || bad "0.4 MFA не через tcPrompt"

# --- 0.5/P3.5 навигация ---------------------------------------------------------
grep -q '<nav id="sidebar" aria-label=' "$F" \
  && ok "0.5 сайдбар — <nav aria-label>" || bad "0.5 сайдбар не <nav>"
grep -qF '" role="button" tabindex="0"' "$F" && grep -qF 'data-page="' "$F" \
  && ok "0.5 nav-item: role=button tabindex=0 data-page" || bad "0.5 nav-item без role/tabindex"
grep -q 'aria-current="page"' "$F" \
  && ok "0.5 активный пункт: aria-current=page" || bad "0.5 нет aria-current"

# --- 0.6/P3.6 deep-linking --------------------------------------------------------
grep -q 'state.page=p;renderNav();deepLinkSync(p);' "$F" \
  && ok "0.6 showPage синхронизирует хэш" || bad "0.6 showPage без deepLinkSync"
grep -q 'showPage(parseHashPage()||"dashboard")' "$F" \
  && ok "0.6 enterApp восстанавливает страницу из хэша" || bad "0.6 enterApp без хэша"
grep -q 'addEventListener("hashchange",onDeepLinkNav)' "$F" && grep -q 'addEventListener("popstate",onDeepLinkNav)' "$F" \
  && ok "0.6 hashchange/popstate обрабатываются" || bad "0.6 нет обработчиков hashchange/popstate"

# --- 0.7/P3.7 Leaflet в поставке ----------------------------------------------------
for f in vendor/leaflet/leaflet.js vendor/leaflet/leaflet.css vendor/leaflet/LICENSE \
         vendor/leaflet/images/marker-icon.png vendor/leaflet/images/marker-icon-2x.png \
         vendor/leaflet/images/marker-shadow.png vendor/leaflet/images/layers.png vendor/leaflet/images/layers-2x.png; do
  [ -f "$f" ] && ok "0.7 поставка: $f" || bad "0.7 отсутствует $f"
done
JS_SRI="sha256-$(openssl dgst -sha256 -binary vendor/leaflet/leaflet.js | openssl base64 -A)"
CSS_SRI="sha256-$(openssl dgst -sha256 -binary vendor/leaflet/leaflet.css | openssl base64 -A)"
grep -q "$JS_SRI" "$F" && ok "0.7 SRI leaflet.js встроен и совпадает с файлом поставки ($JS_SRI)" || bad "0.7 SRI leaflet.js не совпадает"
grep -q "$CSS_SRI" "$F" && ok "0.7 SRI leaflet.css встроен и совпадает с файлом поставки ($CSS_SRI)" || bad "0.7 SRI leaflet.css не совпадает"
# эталонные хеши leafletjs.com для 1.9.4 (unpkg dist)
[ "$JS_SRI" = "sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" ] \
  && ok "0.7 SRI leaflet.js совпадает с эталоном leafletjs.com" || bad "0.7 SRI leaflet.js НЕ совпадает с эталоном"
[ "$CSS_SRI" = "sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" ] \
  && ok "0.7 SRI leaflet.css совпадает с эталоном leafletjs.com" || bad "0.7 SRI leaflet.css НЕ совпадает с эталоном"
grep -q 'css.integrity=TC_LEAFLET_SRI.css' "$F" \
  && ok "0.7 leafletLoad применяет integrity+crossorigin в CDN-режиме" || bad "0.7 leafletLoad без SRI"

# --- 0.8/P3.8 CHANGELOG и «Что нового» -----------------------------------------------
[ -f CHANGELOG.md ] && ok "0.8 CHANGELOG.md в корне" || bad "0.8 нет CHANGELOG.md"
grep -q '## \[102\.0\.0\]' CHANGELOG.md && ok "0.8 CHANGELOG: запись v102" || bad "0.8 CHANGELOG без v102"
grep -q '## \[100\.0\.0\]' CHANGELOG.md && ok "0.8 CHANGELOG: запись v100" || bad "0.8 CHANGELOG без v100"
grep -q 'Что нового · "+ver()' "$F" \
  && ok "0.8 «Что нового» в справочном центре" || bad "0.8 нет секции «Что нового»"
grep -q '\["v102.0.0","26.10.2026"' "$F" \
  && ok "0.8 запись v102 в истории версий «О системе»" || bad "0.8 нет записи v102 в истории"

# --- Д-10 (v102): серверный вход — снимок пароля до очистки полей --------------
grep -q 'const passSnapshot=passEl?String(passEl.value' "$F" \
  && ok "Д-10 passSnapshot снимается до prepareServerLoginAttempt" || bad "Д-10 passSnapshot не найден"
grep -q 'srvTryLogin(passSnapshot)' "$F" \
  && ok "Д-10 обёртка передаёт снимок в srvTryLogin" || bad "Д-10 снимок не передаётся"
grep -q 'async function srvTryLogin(presetPassword){' "$F" \
  && ok "Д-10 srvTryLogin(presetPassword)" || bad "Д-10 srvTryLogin без параметра"
grep -q "check('SRV-LOGIN-01'" "$F" \
  && ok "Д-10 smoke-контроль SRV-LOGIN-01" || bad "Д-10 нет smoke-контроля"

# --- синтаксис всех <script>-блоков ------------------------------------------------------
python3 - "$F" <<'PYEOF' && ok "синтаксис: все <script>-блоки проходят node --check" || bad "синтаксис: есть битый script-блок"
import re, subprocess, sys, tempfile, os
from pathlib import Path
html = Path(sys.argv[1]).read_text(encoding="utf-8")
blocks = re.findall(r"<script>(.*?)</script>", html, re.DOTALL)
bad = 0
for i, b in enumerate(blocks):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(b); p = f.name
    r = subprocess.run(["node", "--check", p], capture_output=True, text=True)
    if r.returncode != 0:
        bad += 1
        print(f"    блок {i}: {r.stderr[:300]}")
    os.unlink(p)
print(f"    блоков: {len(blocks)}, ошибок: {bad}")
sys.exit(1 if bad else 0)
PYEOF

echo "== ИТОГ: $([ $FAIL = 0 ] && echo 'ВСЕ КРИТЕРИИ ВЫПОЛНЕНЫ (Волна 0 + Д-10)' || echo 'ЕСТЬ ПРОВАЛЫ') =="
exit $FAIL
