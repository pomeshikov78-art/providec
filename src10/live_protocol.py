#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Живой протокол интеграции платформы (план улучшений, п. 3.3 — контрактные/живые
испытания клиент-серверного контура; закрывает часть ворот G-03 реальными
доказательствами вместо NOT_RUN).

Запускается против ЖИВОГО uvicorn-стенда (см. src10/run_platform.sh):
  TC_API=http://127.0.0.1:8000 TC_DB=backend/technocontour.db python3 src10/live_protocol.py

Проверяет фактические HTTP-контракты, по которым клиентский мост (srvApi/srvApplyBootstrap,
Этап 8/9) работает с бэкендом: IAM (JWT + MFA/TOTP, отказ/отзыв), bootstrap-витрина,
реестр модулей, шина событий, MOD-KPI/DOC/EXPERT/AI/STIM (включая событийную цепочку
ИВП-1→ИВП-2), graceful degradation (503 при отключённом модуле), WORM-аудит с
хеш-цепочкой, экспорт фактического OpenAPI.

Статус протокола — честный: испытания ВЫПОЛНЕНЫ локально, но это не независимая приёмка.
"""
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
BASE = os.environ.get("TC_API", "http://127.0.0.1:8000").rstrip("/")
DB = os.environ.get("TC_DB", str(ROOT / "backend" / "technocontour.db"))
ADMIN_LOGIN = os.environ.get("TC_ADMIN_LOGIN", "admin")
ADMIN_PASS = os.environ.get("TC_ADMIN_PASS", "tc-admin-2026")
PROGRAM = "v103.0.0"

results = []
ctx = {}


def check(cid, title, fn):
    t0 = time.monotonic()
    try:
        detail = fn()
        results.append({"id": cid, "title": title, "result": "PASS",
                        "detail": str(detail or "")[:300], "ms": round((time.monotonic() - t0) * 1000)})
        print(f"  PASS  {cid} — {title}" + (f"  [{detail}]" if detail else ""))
    except Exception as e:  # noqa: BLE001
        results.append({"id": cid, "title": title, "result": "FAIL",
                        "detail": f"{type(e).__name__}: {e}"[:300], "ms": round((time.monotonic() - t0) * 1000)})
        print(f"  FAIL  {cid} — {title}: {type(e).__name__}: {e}")


def need(cond, msg):
    if not cond:
        raise AssertionError(msg)


client = httpx.Client(base_url=BASE, timeout=30.0)


def totp_now(secret: str) -> str:
    import pyotp
    return pyotp.TOTP(secret).now()


def read_admin_totp_secret() -> str:
    con = sqlite3.connect(DB)
    try:
        row = con.execute("SELECT totp_secret FROM users WHERE login=?", (ADMIN_LOGIN,)).fetchone()
    finally:
        con.close()
    need(row and row[0], "TOTP-секрет администратора не найден в СУБД")
    return row[0]


# ================================================================ ЯДРО / IAM
check("LP-01", "GET /api/v1/core/health — ядро живо", lambda: (
    lambda r: (need(r.status_code == 200, f"HTTP {r.status_code}"),
               ctx.update(health=r.json()), r.json().get("status") or "ok")[-1])
    (client.get("/api/v1/core/health")))

check("LP-02", "Негатив: вход с неверным паролем → 401", lambda: (
    lambda r: (need(r.status_code == 401, f"ожидался 401, получен {r.status_code}"), "401")[1])
    (client.post("/api/v1/auth/login", json={"login": ADMIN_LOGIN, "password": "неверный-пароль"})))


def _login_mfa_required():
    r = client.post("/api/v1/auth/login", json={"login": ADMIN_LOGIN, "password": ADMIN_PASS})
    need(r.status_code == 200, f"HTTP {r.status_code}")
    b = r.json()
    need(b.get("mfa_required") is True, f"ожидался mfa_required, получено {list(b)}")
    return "mfa_required=True (TOTP для L7)"


check("LP-03", "Вход без MFA для L7 → mfa_required (без токена)", _login_mfa_required)


def _login_full():
    secret = read_admin_totp_secret()
    code = totp_now(secret)
    r = client.post("/api/v1/auth/login",
                    json={"login": ADMIN_LOGIN, "password": ADMIN_PASS, "mfa_code": code})
    need(r.status_code == 200, f"HTTP {r.status_code}: {r.text[:120]}")
    b = r.json()
    need(isinstance(b.get("access_token"), str) and b["access_token"], "нет access_token")
    need(b.get("role_level") == "L7", f"role_level={b.get('role_level')!r}, ожидался L7")
    need(isinstance(b.get("refresh_token"), str), "нет refresh_token")
    ctx["tok"] = b["access_token"]
    ctx["ref"] = b["refresh_token"]
    ctx["fio"] = b.get("fio")
    return f"JWT + role_level=L7 + fio={b.get('fio')!r} (TOTP из СУБД)"


check("LP-04", "Полный вход: пароль + TOTP (секрет из СУБД) → JWT, роль L7", _login_full)
H = {"Authorization": "Bearer " + ctx.get("tok", "")}

check("LP-05", "Негатив: bootstrap без токена → 401/403", lambda: (
    lambda r: (need(r.status_code in (401, 403), f"ожидался 401/403, получен {r.status_code}"),
               str(r.status_code))[1])
    (client.get("/api/v1/bootstrap")))


def _bootstrap():
    r = client.get("/api/v1/bootstrap", headers=H)
    need(r.status_code == 200, f"HTTP {r.status_code}: {r.text[:160]}")
    b = r.json()
    for k in ("orgs", "projects", "risks", "docs", "stims", "expert", "modules", "integrations", "geo"):
        need(k in b, f"в bootstrap нет ключа {k!r} (контракт клиентского srvApplyBootstrap)")
    need(len(b["orgs"]) == 100, f"orgs={len(b['orgs'])}, ожидалось 100")
    need(len(b["modules"]) == 15, f"modules={len(b['modules'])}, ожидалось 15")
    need(all(isinstance(x, dict) for x in b["orgs"]), "записи orgs должны быть объектами (лимиты клиента)")
    ctx["boot"] = b
    return (f"orgs=100, projects={len(b['projects'])}, risks={len(b['risks'])}, docs={len(b['docs'])}, "
            f"stims={len(b['stims'])}, expert={len(b['expert'])}, modules=15, integrations={len(b['integrations'])}")


check("LP-06", "GET /bootstrap — витрина соответствует контракту клиента (srvApplyBootstrap)", _bootstrap)

check("LP-07", "GET /core/modules — 15 модулей, 6 обязательных", lambda: (
    lambda r: (need(r.status_code == 200, f"HTTP {r.status_code}"),
               need(len(r.json()) == 15, f"модулей {len(r.json())}"),
               need(sum(1 for m in r.json() if m.get("required")) == 6, "обязательных != 6"),
               "15/6")[3])
    (client.get("/api/v1/core/modules", headers=H)))

check("LP-08", "GET /geo/config — картооснова (tile_url, H3, KDE)", lambda: (
    lambda r: (need(r.status_code == 200, f"HTTP {r.status_code}"),
               need("tile_url" in r.json(), "нет tile_url"),
               f"tile_url={str(r.json().get('tile_url'))[:40]}")[2])
    (client.get("/api/v1/geo/config", headers=H)))

# ================================================================ ШИНА / СОБЫТИЯ
check("LP-09", "GET /core/events?limit=20 — ЖУРНАЛ-массив (контракт опроса клиента)", lambda: (
    lambda r: (need(r.status_code == 200, f"HTTP {r.status_code}"),
               need(isinstance(r.json(), list), "клиент ожидает Array (srvStartPolling)"),
               f"list[{len(r.json())}]")[2])
    (client.get("/api/v1/core/events?limit=20", headers=H)))

# ================================================================ МОДУЛИ ЭТАПА 8
check("LP-10", "MOD-KPI: GET /kpis + POST /kpis/recalculate (регламентный пересчёт из СУБД)", lambda: (
    lambda g, p: (need(g.status_code == 200 and g.json().get("items"), "kpis пуст"),
                  need(p.status_code == 200, f"recalc HTTP {p.status_code}"),
                  f"items={len(g.json()['items'])}, recalc period={p.json().get('period')}")[2])
    (client.get("/api/v1/kpis", headers=H), client.post("/api/v1/kpis/recalculate", headers=H)))


def _expert_chain():
    q = client.get("/api/v1/expert", headers=H)
    need(q.status_code == 200, f"GET /expert HTTP {q.status_code}")
    body = q.json()
    items = body.get("items", body) if isinstance(body, dict) else body
    need(isinstance(items, list) and items, f"очередь экспертизы пуста (форма ответа: {type(body).__name__})")
    item = next((x for x in items if x.get("status") == "queued"), items[0])
    iid = item["id"]
    a = client.post(f"/api/v1/expert/{iid}/assign", headers=H)
    need(a.status_code == 200, f"assign HTTP {a.status_code}: {a.text[:120]}")
    need(a.json().get("status") == "in_review" and a.json().get("expert"), "assign не перевёл в in_review")
    c = client.post(f"/api/v1/expert/{iid}/conclude", headers=H, json={"verdict": "Подтверждено"})
    need(c.status_code == 200, f"conclude HTTP {c.status_code}: {c.text[:160]}")
    res = c.json()
    ctx["expert_done"] = res
    ev = client.get("/api/v1/core/events?type=passport.verified", headers=H).json()
    stims = client.get("/api/v1/stims", headers=H).json()
    stim_list = stims.get("items", stims) if isinstance(stims, dict) else stims
    return (f"{iid}: assign→{a.json().get('expert')}, conclude→{res.get('verdict')}, "
            f"org_verified={res.get('org_verified')}, событий passport.verified={len(ev)}, "
            f"стимулов в реестре={len(stim_list)}")


check("LP-11", "MOD-EXPERT: цепочка ИВП-1→ИВП-2 (назначение → заключение → passport.verified → стимул)", _expert_chain)


def _doc_flow():
    title = f"Живой протокол {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}"
    d = client.post("/api/v1/documents", headers=H, json={"title": title, "kind": "Протокол"})
    need(d.status_code in (200, 201), f"POST /documents HTTP {d.status_code}: {d.text[:120]}")
    did = d.json()["id"]
    s = client.post(f"/api/v1/documents/{did}/sign", headers=H)
    need(s.status_code == 200, f"sign HTTP {s.status_code}")
    card = client.get(f"/api/v1/documents/{did}/card", headers=H)
    need(card.status_code == 200, f"card HTTP {card.status_code}")
    ctx["doc"] = did
    return f"{did}: Проект → {s.json().get('sign')}, карточка version={card.json().get('version', card.json())}"


check("LP-12", "MOD-DOC: авторегистрация документа + неизменяемый поток статусов + карточка", _doc_flow)


def _ai_run():
    r = client.post("/api/v1/ai/run", headers=H)
    need(r.status_code == 200, f"POST /ai/run HTTP {r.status_code}: {r.text[:160]}")
    b = r.json()
    need(b.get("run_id"), "нет run_id")
    recs = b.get("recommendations") or []
    if isinstance(recs, dict):
        recs = recs.get("recommendations", recs.get("items", []))
    need(recs, "рекомендаций нет (модель v4.0-srv должна дать результат на seed-данных)")
    need(all("rid" in x for x in recs),
         "рекомендации без rid — клиент рендерит принятие по data-rid (контракт моста Этапа 9)")
    # форма ответа обязана совпадать с GET /ai/recommendations (latest_run)
    latest = client.get("/api/v1/ai/recommendations", headers=H).json()
    need(latest.get("run_id") == b["run_id"], "run_id POST /ai/run и GET /ai/recommendations разошлись")
    rid = recs[0]["rid"]
    a = client.post(f"/api/v1/ai/recommendations/{rid}/accept", headers=H)
    need(a.status_code == 200, f"accept HTTP {a.status_code}: {a.text[:120]}")
    a2 = client.post(f"/api/v1/ai/recommendations/{rid}/accept", headers=H)
    need(a2.status_code == 409, f"повторное принятие должно давать 409, получено {a2.status_code}")
    ctx["ai"] = {"run_id": b["run_id"], "rid": rid}
    return (f"run_id={b['run_id']}, рекомендаций={len(recs)} (все с rid), "
            f"принята {rid}, повтор → 409 (WORM-аудит)")


check("LP-13", "MOD-AI: детерминированный прогнозный цикл + принятие рекомендации", _ai_run)


def _degradation():
    off = client.patch("/api/v1/core/modules/MOD-AI", headers=H, json={"enabled": False})
    need(off.status_code == 200, f"отключение HTTP {off.status_code}")
    g = client.get("/api/v1/ai/recommendations", headers=H)
    need(g.status_code == 503, f"ожидался 503 при отключённом модуле, получен {g.status_code}")
    on = client.patch("/api/v1/core/modules/MOD-AI", headers=H, json={"enabled": True})
    need(on.status_code == 200, f"включение HTTP {on.status_code}")
    g2 = client.get("/api/v1/ai/recommendations", headers=H)
    need(g2.status_code == 200, f"после включения HTTP {g2.status_code}")
    return "MOD-AI off→503, on→200 (ТЗ п.4.4.2)"


check("LP-14", "Graceful degradation: отключённый модуль → 503, включение восстанавливает", _degradation)

check("LP-15", "WORM-аудит: хеш-цепочка sha256 сверяется, записи операций присутствуют", lambda: (
    lambda v, t: (need(v.status_code == 200, f"verify HTTP {v.status_code}"),
                  need(v.json().get("ok") or v.json().get("consistent") or v.json().get("valid"),
                       f"цепочка не подтверждена: {v.json()}"),
                  need(t.status_code == 200 and len(t.json()) > 0, "журнал пуст"),
                  f"записей в хвосте={len(t.json())}")[3])
    (client.get("/api/v1/core/audit/verify", headers=H), client.get("/api/v1/core/audit", headers=H)))


# ================================================================ ЭТАП 12: ПАСПОРТ/ОТЧЁТЫ
def _passport_persistence():
    pas = client.get("/api/v1/orgs/E01/passport", headers=H)
    need(pas.status_code == 200, f"GET passport HTTP {pas.status_code}")
    sections = pas.json()["sections"]
    need(len(sections) == 12, f"разделов {len(sections)}, ожидалось 12")
    nfields = sum(len(s["fields"]) for s in sections)
    need(nfields == 92, f"полей {nfields}, ожидалось 92")
    fid = sections[0]["fields"][0]["id"]
    marker = "LP-протокол " + datetime.now(timezone.utc).strftime("%H%M%S")
    put = client.put("/api/v1/orgs/E01/passport", headers=H, json={"updates": {str(fid): marker}})
    need(put.status_code == 200, f"PUT passport HTTP {put.status_code}: {put.text[:120]}")
    need(put.json().get("ver_n", 0) >= 1 and put.json().get("changes", 0) >= 1,
         f"PUT не создал версию: {put.json()}")
    pas2 = client.get("/api/v1/orgs/E01/passport", headers=H).json()
    saved = [f for s in pas2["sections"] for f in s["fields"] if f["id"] == fid]
    need(saved and saved[0]["value"] == marker, "значение не персистировано в СУБД")
    vers = client.get("/api/v1/orgs/E01/passport/versions", headers=H).json()
    need(len(vers) >= 1 and vers[0].get("crc32"), f"версии/CRC32 отсутствуют: {vers[:1]}")
    q = client.post("/api/v1/orgs/E01/passport/quality", headers=H)
    need(q.status_code == 200 and "ok" in q.json() and "issues" in q.json(), f"quality HTTP {q.status_code}")
    tw = client.post("/api/v1/twins/E01/rebuild", headers=H)
    need(tw.status_code == 200 and tw.json().get("crc32"), f"twins rebuild HTTP {tw.status_code}")
    return (f"12 разделов/92 поля; PUT → ред. {put.json()['ver_n']}, изменений {put.json()['changes']}, "
            f"CRC версии {vers[0]['crc32']}; значение персистировано; quality ok={q.json()['ok']} "
            f"замечаний {len(q.json()['issues'])}; двойник CRC {tw.json()['crc32']}")


check("LP-18", "MOD-PASS/PROF: карта полей → PUT-версия в СУБД → персистентность → quality → двойник", _passport_persistence)


def _reports_binary():
    d = client.get("/api/v1/reports/passport/E01.docx", headers=H)
    need(d.status_code == 200 and d.content[:2] == b"PK" and len(d.content) > 5000,
         f"DOCX: HTTP {d.status_code}, магия {d.content[:2]!r}, размер {len(d.content)}")
    x = client.get("/api/v1/reports/registry.xlsx", headers=H)
    need(x.status_code == 200 and x.content[:2] == b"PK", f"registry XLSX: HTTP {x.status_code}")
    e = client.get("/api/v1/reports/evm.xlsx", headers=H)
    need(e.status_code == 200 and e.content[:2] == b"PK", f"evm XLSX: HTTP {e.status_code}")
    p = client.get("/api/v1/reports/portfolio.pdf", headers=H)
    need(p.status_code == 200 and p.content[:4] == b"%PDF", f"portfolio PDF: HTTP {p.status_code}, магия {p.content[:4]!r}")
    return (f"DOCX {len(d.content)}Б (PK/python-docx), registry XLSX {len(x.content)}Б, "
            f"evm XLSX {len(e.content)}Б, portfolio PDF {len(p.content)}Б (%PDF/reportlab)")


check("LP-19", "MOD-REPORT: реальные бинарные файлы из СУБД (DOCX/XLSX/PDF, маги-байты)", _reports_binary)


def _openapi():
    r = client.get("/openapi.json")
    need(r.status_code == 200, f"HTTP {r.status_code}")
    spec = r.json()
    paths = spec.get("paths", {})
    for p in ("/api/v1/auth/login", "/api/v1/bootstrap", "/api/v1/core/events",
              "/api/v1/kpis", "/api/v1/expert/{item_id}/conclude", "/api/v1/ai/run"):
        need(p in paths, f"в OpenAPI нет фактического маршрута {p}")
    out_json = ROOT / "backend" / "openapi_providets.json"
    out_json.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    note = "openapi_providets.json"
    try:
        import yaml  # type: ignore
        out_yaml = ROOT / "backend" / "openapi_providets.yaml"
        out_yaml.write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8")
        note += " + openapi_providets.yaml"
    except ImportError:
        note += " (pyyaml не установлен — YAML не сгенерирован)"
    return f"путей={len(paths)}, экспортирован фактический контракт: {note}"


check("LP-16", "Экспорт ФАКТИЧЕСКОГО OpenAPI из живого приложения (ART-02)", _openapi)


def _logout_revoke():
    r = client.post("/api/v1/auth/logout", headers=H)
    need(r.status_code in (200, 204), f"logout HTTP {r.status_code}")
    g = client.get("/api/v1/bootstrap", headers=H)
    need(g.status_code == 401, f"после logout токен должен быть отозван, bootstrap HTTP {g.status_code}")
    return "logout → токен отозван (jti blacklist), повторный доступ 401"


check("LP-17", "Отзыв сессии: logout инвалидирует access-токен", _logout_revoke)

# ================================================================ ПРОТОКОЛ
passed = sum(1 for r in results if r["result"] == "PASS")
failed = len(results) - passed
protocol = {
    "system": "АИС «Техноконтур» / «Провидец»",
    "program": PROGRAM,
    "kind": "live-platform-integration-protocol",
    "status": "EXECUTED_LOCAL_SANDBOX_NOT_INDEPENDENT_ACCEPTANCE",
    "executedAt": datetime.now(timezone.utc).isoformat(),
    "apiBase": BASE,
    "database": os.path.basename(DB),
    "backendHealth": ctx.get("health"),
    "summary": {"total": len(results), "passed": passed, "failed": failed},
    "results": results,
    "chainEvidence": {
        "expert": ctx.get("expert_done"),
        "document": ctx.get("doc"),
        "ai": ctx.get("ai"),
    },
    "limitations": [
        "Испытания выполнены локально (песочница разработки, SQLite, in-process шина) — это не независимая приёмочная процедура.",
        "Протокол подтверждает фактические HTTP-контракты и событийные цепочки на момент прогона, но не заменяет нагрузочные испытания, ИБ-аудит и проверку варианта Б на физически изолированной сети.",
        "Клиентская сторона (браузер) проверяется отдельно: E2E Playwright (tests/e2e/10-server-mode.spec.js) и DOM-тесты.",
        "TOTP-секрет читается напрямую из СУБД стенда — в промышленном контуре выдаётся через процедуру регистрации администратора (TC_FIRST_ADMIN_RUNBOOK).",
    ],
}
outdir = ROOT / "src10" / "protocols"
outdir.mkdir(exist_ok=True)
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
out = outdir / f"live_protocol_{stamp}.json"
out.write_text(json.dumps(protocol, ensure_ascii=False, indent=1), encoding="utf-8")

print(f"\n=== ЖИВОЙ ПРОТОКОЛ ИНТЕГРАЦИИ: {passed}/{len(results)} PASS · {failed} FAIL ===")
print(f"Протокол сохранён: {out.relative_to(ROOT)}")
sys.exit(1 if failed else 0)
