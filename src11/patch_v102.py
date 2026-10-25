#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ЭТАП 11 — выпуск v102.0.0 «Рабочая платформа»: ais_providets_v101.html → ais_providets_v102.html.

Главное содержание выпуска:
  Д-10 (критический дефект серверного режима, обнаружен браузерными E2E на живом бэкенде):
      обёртка doLogin вызывала prepareServerLoginAttempt(), который через
      clearAuthSensitiveFields() очищал #srvPass ДО того, как srvTryLogin() читал пароль.
      Серверный вход через UI был невозможен («Укажите пароль…»). Дефект присутствовал
      с Этапа 9 (v100). Исправление: снимок пароля передаётся аргументом
      srvTryLogin(presetPassword) — обратимо совместимо (вызов без аргумента читает поле).

  Прочее: bump APP_VERSION 102 (единый источник — все отчёты/экспорты/UI обновляются
  автоматически), запись истории, «Что нового», smoke-проверка SRV-LOGIN-01, CHANGELOG.

Запуск:  python3 src11/patch_v102.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "ais_providets_v101.html"
OUT = ROOT / "ais_providets_v102.html"
CUR = ROOT / "ais_providets.html"
CHANGELOG = ROOT / "CHANGELOG.md"

V = {"major": 102, "minor": 0, "patch": 0, "str": "v102.0.0", "num": "102.0.0",
     "tz": "4.0", "build": "v102", "released": "26.10.2026", "released_iso": "2026-10-26"}

HISTORY_TEXT = (
    "Рабочая платформа (Этап 10c/11): (1) исправлен КРИТИЧЕСКИЙ дефект Д-10 серверного режима — "
    "обёртка doLogin вызывала prepareServerLoginAttempt(), очищающий поле пароля ДО его чтения "
    "функцией srvTryLogin, из-за чего серверный вход через UI (JWT + MFA/TOTP) был невозможен "
    "(«Укажите пароль»); пароль теперь передаётся снимком-аргументом srvTryLogin(presetPassword); "
    "дефект существовал с Этапа 9 (v100), не обнаруживался jsdom-тестами и выявлен браузерными "
    "E2E-испытаниями Playwright на живом бэкенде FastAPI (стенд srv, 10 сценариев); "
    "(2) платформа подтверждена живым протоколом интеграции (src10/live_protocol.py, 17/17 PASS "
    "против реального API): IAM (пароль → mfa_required → TOTP из СУБД → JWT L7), bootstrap из СУБД "
    "(100 организаций, 12 проектов, 15 модулей, 29 интеграций), событийная цепочка ИВП-1→ИВП-2 "
    "(назначение эксперта → заключение → passport.verified → стимул MOD-STIM), неизменяемый поток "
    "статусов MOD-DOC, прогнозный цикл MOD-AI с rid и идемпотентностью принятия (повтор → 409), "
    "graceful degradation (модуль off → 503), WORM-аудит с хеш-цепочкой sha256, отзыв токена при "
    "logout (jti blacklist); (3) фактический OpenAPI-контракт (64 пути) экспортирован из живого "
    "приложения в backend/openapi_providets.json/.yaml (артефакт ART-02) — заменяет черновик; "
    "(4) бэкенд: POST /api/v1/ai/run возвращает сохранённые рекомендации с rid — форма ответа "
    "совпадает с GET /api/v1/ai/recommendations (контракт клиентского моста Этапа 9); "
    "(5) добавлена smoke-проверка SRV-LOGIN-01 (контроль дефекта Д-10); E2E-каркас расширен стендом "
    "srv (клиент против живого FastAPI: вход L7 через MFA-диалог, шина, KPI/AI/EXPERT-цепочки, "
    "негатив-кейсы пароля и MFA, деградация полного стека, отзыв токена, серверный RBAC 403). "
    "Демо-режим и киоск не изменены."
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
rep('const APP_VERSION=Object.freeze({major:101,minor:0,patch:0,str:"v101.0.0",num:"101.0.0",tz:"4.0",build:"v101",released:"26.10.2026"});',
    'const APP_VERSION=Object.freeze({major:%(major)d,minor:%(minor)d,patch:%(patch)d,str:"%(str)s",num:"%(num)s",tz:"%(tz)s",build:"%(build)s",released:"%(released)s"});' % V,
    1, "APP_VERSION → 102")
rep('<meta name="providets-release-version" content="v101.0.0">',
    '<meta name="providets-release-version" content="%s">' % V["str"], 1, "meta → v102")
rep('· программа v101.0.0</div>', '· программа %s</div>' % V["str"], 1, "loginVerLine → v102")
rep('<span data-tc-ver="num">101.0.0</span>', '<span data-tc-ver="num">%s</span>' % V["num"], 1, "login-note → 102.0.0")

# ================================================= 2. ДЕФЕКТ Д-10 (ЯДРО) ====
rep('''  const passEl=document.getElementById("srvPass");
  try{toast("Выполняется серверная аутентификация. При отказе вход в демо не выполняется.","","API Gateway");}
  catch(e){}
  prepareServerLoginAttempt();
  srvTryLogin().then(r=>{''',
    '''  const passEl=document.getElementById("srvPass");
  /* Д-10 (v102): prepareServerLoginAttempt() очищает чувствительные поля ДО чтения —
     снимок пароля берётся заранее и передаётся в srvTryLogin аргументом. */
  const passSnapshot=passEl?String(passEl.value||""):"";
  try{toast("Выполняется серверная аутентификация. При отказе вход в демо не выполняется.","","API Gateway");}
  catch(e){}
  prepareServerLoginAttempt();
  srvTryLogin(passSnapshot).then(r=>{''',
    1, "Д-10: снимок пароля до prepareServerLoginAttempt")
rep('async function srvTryLogin(){',
    'async function srvTryLogin(presetPassword){',
    1, "Д-10: srvTryLogin(presetPassword)")
rep('  const pass=String((document.getElementById("srvPass")||{}).value||"");',
    '''  /* Д-10 (v102): пароль может быть передан снимком (обёрткой входа) до очистки полей */
  const pass=String((typeof presetPassword==="string"&&presetPassword!=="")?presetPassword:((document.getElementById("srvPass")||{}).value||""));''',
    1, "Д-10: чтение пароля из снимка или поля")

# ===================================== 3. SMOKE-ПРОВЕРКА КОНТРОЛЯ Д-10 ======
rep("check('GEO-SRI-01','CDN-режим Leaflet использует SRI; офлайн-режим — локальные файлы поставки',()=>typeof TC_LEAFLET_SRI==='object'&&/^sha256-[A-Za-z0-9+/]{43}=$/.test(TC_LEAFLET_SRI.js)&&/^sha256-[A-Za-z0-9+/]{43}=$/.test(TC_LEAFLET_SRI.css)&&TC_LEAFLET_SRI.version==='1.9.4'&&leafletLoad.toString().includes('integrity'));",
    "check('GEO-SRI-01','CDN-режим Leaflet использует SRI; офлайн-режим — локальные файлы поставки',()=>typeof TC_LEAFLET_SRI==='object'&&/^sha256-[A-Za-z0-9+/]{43}=$/.test(TC_LEAFLET_SRI.js)&&/^sha256-[A-Za-z0-9+/]{43}=$/.test(TC_LEAFLET_SRI.css)&&TC_LEAFLET_SRI.version==='1.9.4'&&leafletLoad.toString().includes('integrity'));\n"
    " check('SRV-LOGIN-01','Д-10: серверный вход передаёт снимок пароля в srvTryLogin до очистки полей',()=>doLogin.toString().includes('passSnapshot')&&srvTryLogin.toString().includes('presetPassword')&&srvTryLogin.length===1);",
    1, "smoke +SRV-LOGIN-01")

# ============================================ 4. ИСТОРИЯ И «ЧТО НОВОГО» =====
rep('   [\n    ["v101.0.0","26.10.2026","Волна 0 плана улучшений',
    '   [\n    ["%s","%s","%s"],\n    ["v101.0.0","26.10.2026","Волна 0 плана улучшений' % (V["str"], V["released"], HISTORY_TEXT),
    1, "история: запись v102.0.0")
rep('x:"Единая константа APP_VERSION; тосты и навигация доступны скринридеру и клавиатуре; диалоги tcDialog вместо window.confirm/prompt (MFA, восстановление снимка); глубокие ссылки #страница и кнопка «назад»; Leaflet 1.9.4 в поставке (vendor/) c SRI для CDN; CHANGELOG.md"',
    'x:"'+V['str']+': исправлен критический дефект Д-10 — серверный вход через UI (JWT+MFA) снова работает; платформа подтверждена живыми испытаниями (протокол 17/17 + E2E-стенд srv против FastAPI); фактический OpenAPI (64 пути) в backend/. v101: единая константа APP_VERSION; тосты и навигация доступны скринридеру и клавиатуре; диалоги tcDialog вместо window.confirm/prompt (MFA, восстановление снимка); глубокие ссылки #страница и кнопка «назад»; Leaflet 1.9.4 в поставке (vendor/) c SRI для CDN; CHANGELOG.md"',
    1, "«Что нового» обновлено до v102")

# ======================================================= ВАЛИДАЦИЯ ==========
def expect(cond, msg):
    (report if cond else errors).append(("  ok  VALIDATE: " if cond else "[FAIL] VALIDATE: ") + msg)


expect(html.count('passSnapshot') >= 2, "passSnapshot в обёртке входа")
expect(html.count('presetPassword') >= 2, "presetPassword в srvTryLogin")
expect(html.count('srvTryLogin(passSnapshot)') == 1, "обёртка передаёт снимок")
expect(html.count("SRV-LOGIN-01") == 2, "SRV-LOGIN-01: smoke-проверка + упоминание в истории (ожидалось 2)")
rem101 = [i + 1 for i, ln in enumerate(html.split("\n")) if "v101.0.0" in ln]
expect(len(rem101) == 3, "осталось ровно 3 исторических упоминания v101.0.0 (история+2 комментария), факт %d" % len(rem101))
rem102 = [(i + 1, ln) for i, ln in enumerate(html.split("\n")) if V["num"] in ln]
allowed = ("const APP_VERSION=Object.freeze", 'content="%s"' % V["str"], "loginVerLine",
           'data-tc-ver="num"', '["v102.0.0","26.10.2026"', "Что нового")
for no, ln in rem102:
    if not any(mk in ln for mk in allowed):
        errors.append(f"[FAIL] незапланированный хардкод {V['num']} на стр.{no}")
expect(True, "все вхождения %s — из единого источника (%d строк)" % (V["num"], len(rem102)))
expect(html.count('program:"v101.0.0"') == 0 and html.count('program:"v102.0.0"') == 0,
       "отчёты по-прежнему через ver() (хардкодов program нет)")

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
print(f"[i] записей истории в v102: {len(entries)}")
if len(entries) < 80:
    sys.exit("[FAIL] массив истории распознан не полностью")

V102_SECTION = f"""## [{V['num']}] — {V['released_iso']}

Выпуск «Рабочая платформа»: клиент v101 + ЖИВОЙ бэкенд FastAPI, подтверждённые
совместными испытаниями. Артефакт: `ais_providets_v102.html` (единый HTML).
Сборка: `python3 src11/patch_v102.py` (детерминированная, из `ais_providets_v101.html`).

### Исправлено
- **Д-10 (критический, серверный режим):** обёртка `doLogin` вызывала
  `prepareServerLoginAttempt()`, который очищал `#srvPass` ДО чтения пароля функцией
  `srvTryLogin` — серверный вход через UI (JWT + MFA/TOTP) был невозможен
  («Укажите пароль…»). Дефект присутствовал с Этапа 9 (v100), не обнаруживался
  jsdom-тестами; выявлен браузерными E2E на живом бэкенде. Исправление: снимок пароля
  передаётся аргументом `srvTryLogin(presetPassword)` (вызов без аргумента совместим).
- **Бэкенд `POST /api/v1/ai/run`:** возвращает СОХРАНЁННЫЕ рекомендации с `rid`
  (ранее — сырые результаты расчёта без `rid`); форма ответа совпадает с
  `GET /api/v1/ai/recommendations` — контракт клиентского моста Этапа 9.

### Добавлено
- **Живой протокол интеграции** `src10/live_protocol.py` — **17/17 PASS** против
  реального API: IAM (пароль → mfa_required → TOTP из СУБД → JWT L7), bootstrap из СУБД
  (100 организаций, 12 проектов, 15 модулей, 29 интеграций), цепочка ИВП-1→ИВП-2
  (assign → conclude → `passport.verified` → стимул MOD-STIM), поток статусов MOD-DOC,
  MOD-AI (run → accept → повтор 409), graceful degradation (off → 503), WORM-аудит
  (хеш-цепочка sha256 сверяется), отзыв токена (logout → 401). Протоколы — в
  `src10/protocols/` (статус: EXECUTED_LOCAL_SANDBOX_NOT_INDEPENDENT_ACCEPTANCE).
- **E2E-стенд `srv`** (Playwright): 10 сценариев «клиент против живого FastAPI» —
  серверный вход через UI с MFA-диалогом, доставка событий шины опросом, KPI-пересчёт,
  AI-цикл с принятием рекомендации, EXPERT-цепочка + WORM-запись, негативы
  (неверный пароль/MFA — fail closed, демо не открывается), деградация полного стека,
  отзыв токена, серверный RBAC (L0 → 403).
- **Фактический OpenAPI** (64 пути) экспортирован из живого приложения:
  `backend/openapi_providets.json` / `.yaml` — артефакт ART-02 манифеста релиза.
- **Smoke-проверка SRV-LOGIN-01** — постоянный контроль дефекта Д-10.

### Изменено
- Версия {V['str']} во всех отчётах/экспортах/UI — автоматически из `APP_VERSION`
  (результат работы 0.1/P3.1: ручных замен версии не потребовалось).
- «Что нового» в справочном центре обновлено до {V['str']}.

### Совместимость
- Демо-режим, киоск, вариант Б — без изменений (регрессия: 87 jsdom + 63×2 E2E).
- Снимки данных v100/v101 восстанавливаются в v102 (schemaVersion=1).
"""

lines = [
    "# CHANGELOG — АИС «Техноконтур» · шифр «Провидец»",
    "",
    "Все значимые изменения клиентского приложения (единый HTML-артефакт `ais_providets_vXXX.html`).",
    "Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/), версионирование — [SemVer](https://semver.org/lang/ru/).",
    "",
    "> Примечание: записи ниже (кроме v102) сгенерированы из массива «История версий программы»",
    "> страницы «О системе» (`RENDERERS.about`) — единого источника истории внутри артефакта.",
    "> v14–v81, v83–v99 — промежуточные итерации закалки клиентской ветки B (работы P0.1–P0.59),",
    "> в публичный массив истории артефакта не включались (см. `src9/README.md`).",
    "",
    V102_SECTION,
]
for v, d, text in entries:
    if v == V["str"]:
        continue  # v102 — структурированная запись выше
    num = v.lstrip("v")
    dd, mm, yyyy = d.split(".")
    lines += [f"## [{num}] — {yyyy}-{mm}-{dd}", "", "### Изменено", f"- {js_unescape(text)}", ""]

CHANGELOG.write_text("\n".join(lines), encoding="utf-8")
print(f"[i] CHANGELOG.md перезаписан: v102 + {len(entries) - 1} записей истории")
print("\n".join(report))
print(f"\n[OK] {OUT.name} собран: замен — {len(report)}, ошибок — 0.")
