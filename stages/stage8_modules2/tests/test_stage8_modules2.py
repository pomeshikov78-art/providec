"""Этап 8 (Фаза 2): серверные сервисы MOD-KPI / MOD-STIM / MOD-DOC / MOD-EXPERT / MOD-AI.

Проверяются: реестры и пересчёт KPI из БД, телеметрия, авто-применение мер по
событиям шины (Прил. 1.6), неизменяемый поток статусов документов и ЭЦП-отпечаток,
авторегистрация заключений/отчётов в MOD-DOC, полный цикл экспертизы (assign →
conclude → verified + событийная цепочка ИВП-1→ИВП-2), SLA ≤ 8 ч, детерминированный
прогнозный цикл ИВП-7 (confidence ≥ 0.7), RBAC для новых действий IAM.
"""
import re

import pytest


# ================================================================ MOD-KPI
def test_kpi_list_all_roles(client, l0_headers):
    r = client.get("/api/v1/kpis", headers=l0_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 8
    k1 = body["items"][0]
    assert k1["code"] == "KPI-1" and k1["source"] == "calc"
    assert len(k1["hist"]) == 12          # история 12 месяцев из сида
    assert "квартал" in body["period"]


def test_kpi_recalculate_rbac(client, l0_headers, l5_headers, admin_headers):
    assert client.post("/api/v1/kpis/recalculate", headers=l0_headers).status_code == 403
    assert client.post("/api/v1/kpis/recalculate", headers=l5_headers).status_code == 403
    # L2 (regulator) — разрешено политикой kpi.recalc
    from tests.conftest import _login
    reg = _login(client, "regulator", "tc-reg-2026").json()
    h2 = {"Authorization": "Bearer " + reg["access_token"]}
    r = client.post("/api/v1/kpis/recalculate", headers=h2)
    assert r.status_code == 200
    body = r.json()
    codes = {i["code"]: i for i in body["items"]}
    # KPI-1 вычислен из БД: организации с профилем зрелости / всего (независимо от порядка тестов)
    from sqlalchemy import func, select
    from app.db import session_scope
    from app.models import Maturity, Organization
    with session_scope() as db:
        total = db.scalar(select(func.count()).select_from(Organization))
        withm = db.scalar(select(func.count()).select_from(Maturity))
    assert codes["KPI-1"]["cur"] == round(withm / total * 100, 1)
    assert codes["KPI-1"]["cur"] >= 95 and codes["KPI-1"]["met"] is True
    # calc-показатель пересчитан из БД: KPI-7 = охват кооперационными связями
    assert 0 < codes["KPI-7"]["cur"] <= 100
    # отклонения фиксируются событием kpi.threshold_breached (KPI-3: 67% верифицированных < 90)
    if body["breached"]:
        ev = client.get("/api/v1/core/events?type=kpi.threshold_breached&limit=5", headers=admin_headers)
        assert ev.status_code == 200 and isinstance(ev.json(), list)


def test_kpi_telemetry_flow(client, admin_headers):
    from tests.conftest import _login
    from app.services import kpi as kpi_svc
    kpi_svc.reset_telemetry("KPI-4")               # изоляция от замеров других этапов
    reg = _login(client, "regulator", "tc-reg-2026").json()
    h2 = {"Authorization": "Bearer " + reg["access_token"]}
    # calc-показатель телеметрией не обновляется
    assert client.post("/api/v1/kpis/KPI-1/telemetry", json={"value": 5},
                       headers=admin_headers).status_code == 409
    assert client.post("/api/v1/kpis/KPI-9/telemetry", json={"value": 5},
                       headers=admin_headers).status_code == 404
    r = client.post("/api/v1/kpis/KPI-4/telemetry", json={"value": 2.5}, headers=admin_headers)
    assert r.status_code == 200
    client.post("/api/v1/kpis/KPI-4/telemetry", json={"value": 3.5}, headers=admin_headers)
    r2 = client.post("/api/v1/kpis/recalculate", headers=h2).json()
    k4 = [i for i in r2["items"] if i["code"] == "KPI-4"][0]
    assert k4["cur"] == 3.0                        # среднее замеров (2.5 + 3.5)/2
    assert k4["met"] is True                       # ≤ 5 с (норматив ИВП-6)


# ================================================================ MOD-STIM
def test_stims_list_and_catalog(client, l0_headers):
    r = client.get("/api/v1/stims", headers=l0_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 6
    assert len(body["catalog"]["stim"]) == 5 and len(body["catalog"]["sanction"]) == 5


def test_stims_manual_create_rbac(client, l5_headers, l0_headers):
    from tests.conftest import _login
    assert client.post("/api/v1/stims", headers=l0_headers,
                       json={"kind": "stim", "title": "X"}).status_code == 403
    assert client.post("/api/v1/stims", headers=l5_headers,
                       json={"kind": "stim", "title": "X"}).status_code == 403
    reg = _login(client, "regulator", "tc-reg-2026").json()
    h2 = {"Authorization": "Bearer " + reg["access_token"]}
    r = client.post("/api/v1/stims", headers=h2,
                    json={"org_id": "E01", "kind": "stim",
                          "title": "Грант на формирование задела (этап 3)",
                          "basis": "Решение отраслевого органа (тест этапа 8)"})
    assert r.status_code == 200
    s = r.json()
    assert re.match(r"^S\d{2,}$", s["id"]) and s["kind"] == "Стимул" and s["st"] == "Действует"
    # смена статуса + невалидное значение
    r2 = client.patch(f"/api/v1/stims/{s['id']}", headers=h2, json={"status": "На контроле"})
    assert r2.status_code == 200 and r2.json()["st"] == "На контроле"
    assert client.patch(f"/api/v1/stims/{s['id']}", headers=h2, json={"status": "???"}).status_code == 422
    assert client.patch("/api/v1/stims/S99", headers=h2, json={"status": "Снята"}).status_code == 404


def test_stim_auto_on_no_go(client, l5_headers):
    """Прил. 1.6: No-Go ×2 → автоматическая санкция «Ограничение новых заявок»."""
    pid = "P09"
    for _ in range(2):
        r = client.post(f"/api/v1/niokr/projects/{pid}/gates", headers=l5_headers,
                        json={"decision": "no-go", "comment": "тест этапа 8"})
        assert r.status_code == 200
    stims = client.get("/api/v1/stims", headers=l5_headers).json()["items"]
    sank = [s for s in stims if s["kind"] == "Санкция" and f"{pid}: No-Go ×2" in (s["base"] or "")]
    assert sank, "автоматическая санкция не создана по событию niokr.gate_decision"
    # идемпотентность: повторный пересчёт не дублирует меру с тем же основанием
    n_before = len(stims)
    client.post(f"/api/v1/niokr/projects/{pid}/gates", headers=l5_headers,
                json={"decision": "no-go", "comment": "третий"})
    stims2 = client.get("/api/v1/stims", headers=l5_headers).json()["items"]
    same = [s for s in stims2 if f"{pid}: No-Go ×2 " in (s["base"] or "") + " "]
    assert len([s for s in stims2 if s["base"] == sank[0]["base"]]) == 1
    assert len(stims2) >= n_before


# ================================================================ MOD-EXPERT + цепочка ИВП
def test_expert_queue_and_sla(client, l0_headers, admin_headers):
    r = client.get("/api/v1/expert", headers=l0_headers)
    assert r.status_code == 200
    q = r.json()
    assert q["total"] == 5
    v04 = [i for i in q["items"] if i["id"] == "V04"][0]
    assert v04["status"] == "in_review" and v04["expert"] != "—"
    # SLA ИВП-1: объекты в очереди с 05–12.10 → норматив 8 ч нарушен
    assert q["sla_breaches"]
    r2 = client.get("/api/v1/expert/sla", headers=admin_headers)
    assert r2.status_code == 200 and r2.json()["breached"]
    # L4 (предприятие) не назначает экспертов
    from tests.conftest import _login
    s4 = _login(client, "sarmat", "tc-org-2026").json()
    h4 = {"Authorization": "Bearer " + s4["access_token"]}
    assert client.post("/api/v1/expert/V02/assign", headers=h4).status_code == 403


def test_expert_full_cycle_and_event_chain(client, l5_headers, l0_headers, admin_headers):
    """assign → conclude → E11 verified; цепочка: заключение в MOD-DOC + стимул MOD-STIM."""
    # назначение: детерминированный выбор эксперта из пула
    r = client.post("/api/v1/expert/V01/assign", headers=l5_headers)
    assert r.status_code == 200
    e1 = r.json()
    assert e1["status"] == "in_review"
    assert e1["expert"] in ("Соколов Д. Н.", "Мельникова А. В.", "Гущин П. С.", "Радченко Е. И.")
    r_again = client.post("/api/v1/expert/V01/assign", headers=l5_headers).json()
    assert r_again["expert"] == e1["expert"]            # детерминизм (аудит-воспроизводимость)
    # заключение без назначения → 409
    assert client.post("/api/v1/expert/V02/conclude", headers=l5_headers,
                       json={"verdict": "X"}).status_code == 409
    # арбитраж E11: назначить + выдать заключение
    client.post("/api/v1/expert/V03/assign", headers=l5_headers)
    r3 = client.post("/api/v1/expert/V03/conclude", headers=l5_headers,
                     json={"verdict": "Расхождение ЕГРЮЛ устранено, данные подтверждены"})
    assert r3.status_code == 200
    res = r3.json()
    assert res["status"] == "done" and res["org_verified"] == "E11"
    # организация верифицирована (событие passport.verified → БД)
    org = client.get("/api/v1/orgs/E11", headers=l0_headers).json()
    assert org["status"] == "verified"
    # MOD-DOC: заключение зарегистрировано автоматически (по событию шины)
    docs = client.get("/api/v1/documents", headers=l0_headers).json()["items"]
    concl = [d for d in docs if "V03" in d["t"]]
    assert concl and concl[0]["kind"] == "Заключение"
    assert concl[0]["sign"] == "Подписан (ЭЦП)" and concl[0]["signature"]
    # MOD-STIM: стимул «Публикация в отраслевом каталоге компетенций» применён автоматически
    stims = client.get("/api/v1/stims", headers=l0_headers).json()["items"]
    auto = [s for s in stims if "passport.verified · E11" in (s["base"] or "")]
    assert auto and auto[0]["kind"] == "Стимул"
    # повторное заключение → 409 (статус done)
    assert client.post("/api/v1/expert/V03/conclude", headers=l5_headers,
                       json={}).status_code == 409
    # цифровой двойник пересобран (profile.updated → twin.rebuilt)
    ev = client.get("/api/v1/core/events?type=twin.rebuilt&limit=20", headers=admin_headers).json()
    assert any("E11" in e["payload"] for e in (ev if isinstance(ev, list) else ev.get("items", [])))


def test_expert_rbac(client, l0_headers, l4_headers):
    assert client.post("/api/v1/expert/V02/assign", headers=l0_headers).status_code == 403
    assert client.post("/api/v1/expert/V02/assign", headers=l4_headers).status_code == 403
    assert client.post("/api/v1/expert/V99/assign", headers=l0_headers).status_code == 403


# ================================================================ MOD-DOC
def test_doc_registry_and_sign_flow(client, l0_headers):
    from tests.conftest import _login
    reg = _login(client, "regulator", "tc-reg-2026").json()
    h2 = {"Authorization": "Bearer " + reg["access_token"]}
    r = client.post("/api/v1/documents", headers=h2,
                    json={"title": "Справка о технологическом заделе (тест этапа 8)",
                          "org_id": "E14", "kind": "Справка"})
    assert r.status_code == 200
    d = r.json()
    assert re.match(r"^D-\d{4}-\d{4}$", d["id"]) and d["sign"] == "Проект" and d["version"] == 1
    # неизменяемый поток: Проект → На подписании → Подписан (ЭЦП) → Утверждён
    r1 = client.post(f"/api/v1/documents/{d['id']}/sign", headers=h2).json()
    assert r1["sign"] == "На подписании" and r1["version"] == 2 and not r1["signature"]
    r2 = client.post(f"/api/v1/documents/{d['id']}/sign", headers=h2).json()
    assert r2["sign"] == "Подписан (ЭЦП)" and r2["signature"].startswith("dev-sha256:")
    assert r2["signed_by"]
    r3 = client.post(f"/api/v1/documents/{d['id']}/sign", headers=h2).json()
    assert r3["sign"] == "Утверждён"
    # терминальный статус — подписание запрещено (неизменяемость реестра)
    assert client.post(f"/api/v1/documents/{d['id']}/sign", headers=h2).status_code == 409
    # карточка + аудит просмотра; 404
    card = client.get(f"/api/v1/documents/{d['id']}/card", headers=l0_headers)
    assert card.status_code == 200 and card.json()["t"] == d["t"]
    assert client.get("/api/v1/documents/D-2026-9999/card", headers=l0_headers).status_code == 404
    # RBAC: guest не регистрирует и не подписывает
    assert client.post("/api/v1/documents", headers=l0_headers,
                       json={"title": "X"}).status_code == 403


def test_doc_auto_registration_of_reports(client, admin_headers):
    """Отчёт MOD-REPORT → report.generated → авторегистрация в реестре MOD-DOC."""
    r = client.get("/api/v1/reports/registry.xlsx", headers=admin_headers)
    assert r.status_code == 200
    docs = client.get("/api/v1/documents", headers=admin_headers).json()["items"]
    rep = [d for d in docs if d["kind"] == "Отчет" and d["t"].startswith("Отчет:")]
    assert rep, "отчёт не зарегистрирован в реестре MOD-DOC"


# ================================================================ MOD-AI
def test_ai_forecast_deterministic(client, l0_headers):
    r = client.get("/api/v1/ai/forecast", headers=l0_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["model"] == "v4.0-srv"
    gaps = body["tech_gaps"]["gaps"]
    assert len(gaps) == 6                                   # 6 типов компетенций (ТЗ п.5.2.2)
    for g in gaps:
        assert len(g["prog"]) == 7 and 0.6 <= g["conf"] <= 0.95
        assert all(x <= y + 1e-9 for x, y in zip(g["prog"], g["prog"][1:]))  # монотонный рост
    assert 1 <= len(body["fail_risk"]) <= 6
    top = body["fail_risk"][0]
    assert 4 <= top["risk"] <= 92 and top["factors"]["overdue_days"] >= 0
    # детерминизм: повторный запрос идентичен
    assert client.get("/api/v1/ai/forecast", headers=l0_headers).json() == body


def test_ai_run_and_accept(client, l0_headers, l4_headers, admin_headers):
    from tests.conftest import _login
    assert client.post("/api/v1/ai/run", headers=l0_headers).status_code == 403
    assert client.post("/api/v1/ai/run", headers=l4_headers).status_code == 403
    reg = _login(client, "regulator", "tc-reg-2026").json()
    h2 = {"Authorization": "Bearer " + reg["access_token"]}
    r = client.post("/api/v1/ai/run", headers=h2)
    assert r.status_code == 200
    run = r.json()
    assert run["run_id"].startswith("AIR-")
    recs = run["recommendations"]
    assert 1 <= len(recs) <= 6
    assert all(x["conf"] >= 0.7 for x in recs)              # критерий публикации ИВП-7
    mods = {x["m"] for x in recs}
    assert mods & {"MOD-COOP", "MOD-NIOKR", "MOD-GEO", "MOD-STIM", "MOD-PASS", "MOD-PORTF"}
    # детерминизм модели: второй прогон — те же тексты рекомендаций
    run2 = client.post("/api/v1/ai/run", headers=h2).json()
    assert [x["t"] for x in run2["recommendations"]] == [x["t"] for x in recs]
    # событие ai.recommendations_ready в журнале шины
    ev = client.get("/api/v1/core/events?type=ai.recommendations_ready&limit=5",
                    headers=admin_headers).json()
    items = ev if isinstance(ev, list) else ev.get("items", [])
    assert items
    # принятие рекомендации (ai.accept): L2 → accepted; повторно → 409
    latest = client.get("/api/v1/ai/recommendations", headers=l0_headers).json()
    rid = latest["recommendations"][0]["rid"]
    ra = client.post(f"/api/v1/ai/recommendations/{rid}/accept", headers=h2)
    assert ra.status_code == 200 and ra.json()["status"] == "accepted"
    assert client.post(f"/api/v1/ai/recommendations/{rid}/accept", headers=h2).status_code == 409
    assert client.post("/api/v1/ai/recommendations/999999/accept", headers=h2).status_code == 404
    # L0 принять не может
    rid2 = [x for x in latest["recommendations"] if x["status"] == "published"]
    if rid2:
        assert client.post(f"/api/v1/ai/recommendations/{rid2[0]['rid']}/accept",
                           headers=l0_headers).status_code == 403


# ================================================================ ядро: аудит и деградация
def test_audit_chain_intact_after_stage8(client, admin_headers):
    r = client.get("/api/v1/core/audit/verify", headers=admin_headers)
    assert r.status_code == 200 and r.json()["ok"] is True


def test_module_off_degrades_endpoints(client, admin_headers):
    """Отключение MOD-AI (необязательный модуль) → 503 graceful degradation,
    остальные модули продолжают работу; включение восстанавливает функцию."""
    r = client.patch("/api/v1/core/modules/MOD-AI", headers=admin_headers,
                     json={"enabled": False})
    assert r.status_code == 200                       # MOD-AI не обязателен (ТЗ п.4.7)
    r2 = client.get("/api/v1/ai/forecast", headers=admin_headers)
    assert r2.status_code == 503 and "деградирован" in r2.json()["detail"]
    # каскад: зависимые от MOD-AI отсутствуют; остальные модули работают
    assert client.get("/api/v1/kpis", headers=admin_headers).status_code == 200
    assert client.get("/api/v1/stims", headers=admin_headers).status_code == 200
    client.patch("/api/v1/core/modules/MOD-AI", headers=admin_headers, json={"enabled": True})
    assert client.get("/api/v1/ai/forecast", headers=admin_headers).status_code == 200
