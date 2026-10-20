"""Этап 8 (Фаза 2): серверные API перенесённых модулей витрины —
MOD-KPI, MOD-STIM, MOD-DOC, MOD-EXPERT, MOD-AI.

Паттерн ядра (против deadlock SQLite): сервисы собирают события в список →
роутер фиксирует транзакцию (db.commit) → публикует события в шину → WORM-аудит.
Прямые межмодульные вызовы запрещены: цепочки (экспертиза → верификация паспорта
→ стимул → двойник) идут только через шину событий ядра.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select

from ..db import get_db
from ..kernel import audit, registry
from ..kernel.bus import get_bus
from ..kernel.iam import AuthUser, require
from ..models import AiRecommendation, Document, ExpertItem, Kpi, Stim
from ..services import ai as ai_svc
from ..services import docflow as doc_svc
from ..services import expert as exp_svc
from ..services import kpi as kpi_svc
from ..services import stim as stim_svc

router = APIRouter(prefix="/api/v1", tags=["modules2"])


def _publish(evs: list) -> None:
    for t, s, pl, sv in evs:
        get_bus().publish(t, s, pl, sv)


def mod_guard(code: str):
    """Graceful degradation (ТЗ п.4.4.2): функции отключённого/деградированного
    модуля недоступны (503), остальные модули продолжают работу."""
    def dep() -> None:
        if not registry.is_active(code):
            raise HTTPException(503, f"Модуль {code} отключен или деградирован — "
                                     f"функция недоступна (каскадная деградация ядра)")
    return Depends(dep)


# ================================================================ MOD-KPI
@router.get("/kpis", dependencies=[mod_guard("MOD-KPI")])
def kpis(db=Depends(get_db), user: AuthUser = Depends(require("view"))):
    """Целевые показатели системы (ТЗ п.2.3) с историей за 12 месяцев."""
    return {"period": kpi_svc.period_label(), "items": kpi_svc.list_kpis(db)}


@router.post("/kpis/recalculate", dependencies=[mod_guard("MOD-KPI")])
def kpis_recalculate(db=Depends(get_db), user: AuthUser = Depends(require("kpi.recalc"))):
    """Регламентный пересчёт: calc-показатели из БД + накопленная телеметрия.
    Отклонение от порога → kpi.threshold_breached → авто-санкция MOD-STIM (эскалация)."""
    evs: list = []
    res = kpi_svc.recalculate(db, events=evs)
    db.commit()
    _publish(evs)
    audit.record("Пересчет KPI (регламент)", f"{res['total']} показателей · отклонений: {len(res['breached'])}",
                 "Успех" if not res["breached"] else "Отклонение от порогов",
                 user=user.login, role=user.role)
    return res


class TelemetryIn(BaseModel):
    value: float


@router.post("/kpis/{code}/telemetry", dependencies=[mod_guard("MOD-KPI")])
def kpi_telemetry(code: str, body: TelemetryIn, db=Depends(get_db),
                  user: AuthUser = Depends(require("admin"))):
    """Замер телеметрии службами модулей (KPI-4 отчёты, KPI-8 гео, KPI-5 SLA)."""
    k = db.get(Kpi, code)
    if k is None:
        raise HTTPException(404, f"Показатель {code} не найден")
    if k.source != "telemetry":
        raise HTTPException(409, f"{code}: calc-показатель — обновляется пересчётом из БД")
    kpi_svc.record_telemetry(code, body.value)
    return {"code": code, "accepted": body.value,
            "note": "значение будет применено при следующем пересчёте (среднее замеров)"}


# ================================================================ MOD-STIM
@router.get("/stims", dependencies=[mod_guard("MOD-STIM")])
def stims(db=Depends(get_db), user: AuthUser = Depends(require("view"))):
    return {"total": db.scalar(select(func.count()).select_from(Stim)) or 0,
            "active": len([s for s in stim_svc.list_stims(db) if s["st"] == "Действует"]),
            "items": stim_svc.list_stims(db),
            "catalog": {"stim": stim_svc.STIM_CATALOG, "sanction": stim_svc.SANCTION_CATALOG}}


class StimCreate(BaseModel):
    org_id: Optional[str] = None
    kind: str                      # stim | sanction
    title: str
    basis: str = ""


@router.post("/stims", dependencies=[mod_guard("MOD-STIM")])
def stim_create(body: StimCreate, db=Depends(get_db),
                user: AuthUser = Depends(require("stim.write"))):
    """Ручная регистрация меры. RACI (Прил. 4.4): утверждает субъект с кодом «A»."""
    evs: list = []
    try:
        s = stim_svc.create(db, body.org_id, body.kind, body.title,
                            body.basis or f"Решение {user.role} {user.login}", evs)
    except ValueError as e:
        raise HTTPException(422, str(e))
    db.commit()
    _publish(evs)
    audit.record("Регистрация меры стимулирования/санкции", f"{s.id} · {s.title}", "Успех",
                 user=user.login, role=user.role)
    return stim_svc.stim_dict(s)


class StimStatus(BaseModel):
    status: str


@router.patch("/stims/{stim_id}", dependencies=[mod_guard("MOD-STIM")])
def stim_status(stim_id: str, body: StimStatus, db=Depends(get_db),
                user: AuthUser = Depends(require("stim.write"))):
    try:
        s = stim_svc.set_status(db, stim_id, body.status)
    except KeyError:
        raise HTTPException(404, f"Мера {stim_id} не найденa")
    except ValueError as e:
        raise HTTPException(422, str(e))
    db.commit()
    get_bus().publish("stim.status_changed", "MOD-STIM", f"{stim_id}: статус → {s.status}", "info")
    audit.record("Изменение статуса меры", f"{stim_id} → {s.status}", "Успех",
                 user=user.login, role=user.role)
    return stim_svc.stim_dict(s)


# ================================================================ MOD-DOC
@router.get("/documents", dependencies=[mod_guard("MOD-DOC")])
def documents(db=Depends(get_db), user: AuthUser = Depends(require("view"))):
    items = doc_svc.list_docs(db)
    return {"total": len(items), "items": items, "flow": doc_svc.FLOW}


class DocCreate(BaseModel):
    title: str
    org_id: Optional[str] = None
    kind: str = "Справка"


@router.post("/documents", dependencies=[mod_guard("MOD-DOC")])
def document_create(body: DocCreate, db=Depends(get_db),
                    user: AuthUser = Depends(require("doc.sign"))):
    evs: list = []
    d = doc_svc.register(db, body.title, body.org_id, body.kind, evs)
    db.commit()
    _publish(evs)
    audit.record("Регистрация документа", f"{d.id} · {d.title}", "Успех",
                 user=user.login, role=user.role)
    return doc_svc.doc_dict(d)


@router.get("/documents/{doc_id}/card", dependencies=[mod_guard("MOD-DOC")])
def document_card(doc_id: str, db=Depends(get_db), user: AuthUser = Depends(require("view"))):
    evs: list = []
    try:
        c = doc_svc.card(db, doc_id, evs)
    except KeyError:
        raise HTTPException(404, f"Документ {doc_id} не найден")
    db.commit()
    _publish(evs)
    audit.record("Просмотр карточки документа", f"{doc_id} · {c['t']}", "Успех",
                 user=user.login, role=user.role)
    return c


@router.post("/documents/{doc_id}/sign", dependencies=[mod_guard("MOD-DOC")])
def document_sign(doc_id: str, db=Depends(get_db),
                  user: AuthUser = Depends(require("doc.sign"))):
    """Переход статуса строго вперёд: Проект → На подписании → Подписан (ЭЦП) → Утверждён."""
    evs: list = []
    try:
        d = doc_svc.sign(db, doc_id, user.login, evs)
    except KeyError:
        raise HTTPException(404, f"Документ {doc_id} не найден")
    except ValueError as e:
        raise HTTPException(409, str(e))
    db.commit()
    _publish(evs)
    audit.record("Подписание документа", f"{doc_id} → {d.sign_status}", "Успех",
                 user=user.login, role=user.role)
    return doc_svc.doc_dict(d)


# ================================================================ MOD-EXPERT
@router.get("/expert", dependencies=[mod_guard("MOD-EXPERT")])
def expert_queue(db=Depends(get_db), user: AuthUser = Depends(require("view"))):
    """Очередь верификации + SLA-мониторинг (ИВП-1: ≤ 8 ч)."""
    return exp_svc.queue(db)


@router.post("/expert/{item_id}/assign", dependencies=[mod_guard("MOD-EXPERT")])
def expert_assign(item_id: str, db=Depends(get_db),
                  user: AuthUser = Depends(require("expert.assign"))):
    """Назначение эксперта (детерминированный выбор из пула, комиссия ≥ 3 чел.)."""
    evs: list = []
    try:
        e = exp_svc.assign(db, item_id, evs)
    except KeyError:
        raise HTTPException(404, f"Объект экспертизы {item_id} не найден")
    except ValueError as ex:
        raise HTTPException(409, str(ex))
    db.commit()
    _publish(evs)
    audit.record("Назначение эксперта", f"{item_id} · {e.expert}", "Успех",
                 user=user.login, role=user.role)
    return exp_svc.item_dict(e)


class ConcludeIn(BaseModel):
    verdict: str = "Подтверждено"


@router.post("/expert/{item_id}/conclude", dependencies=[mod_guard("MOD-EXPERT")])
def expert_conclude(item_id: str, body: ConcludeIn, db=Depends(get_db),
                    user: AuthUser = Depends(require("expert.approve"))):
    """Выдача заключения (ЭЦП). Цепочка ИВП-1→ИВП-2 через шину:
    expert.conclusion_ready → MOD-DOC (авторегистрация заключения) →
    passport.verified → MOD-STIM (стимул) + profile.updated → цифровой двойник."""
    evs: list = []
    try:
        res = exp_svc.conclude(db, item_id, body.verdict, user.login, evs)
    except KeyError:
        raise HTTPException(404, f"Объект экспертизы {item_id} не найден")
    except ValueError as ex:
        raise HTTPException(409, str(ex))
    db.commit()
    _publish(evs)   # публикация ПОСЛЕ commit — обработчики (DOC/STIM/TWIN) откроют свои сессии
    audit.record("Выдача экспертного заключения", f"{item_id} · {body.verdict}" +
                 (f" · организация {res['org_verified']} верифицирована" if res.get("org_verified") else ""),
                 "Успех", user=user.login, role=user.role)
    # информируем клиента о побочных результатах событийной цепочки
    res["new_stims"] = [stim_svc.stim_dict(s) for s in db.scalars(
        select(Stim).where(Stim.basis.like(f"%{res.get('org_verified') or item_id}%")))] if res.get("org_verified") else []
    return res


@router.get("/expert/sla", dependencies=[mod_guard("MOD-EXPERT")])
def expert_sla(db=Depends(get_db), user: AuthUser = Depends(require("view"))):
    """Регламентная проверка SLA (планировщик ядра / оператор)."""
    evs: list = []
    breached = exp_svc.check_sla(db, evs)
    db.commit()
    _publish(evs)
    return {"sla_hours": exp_svc.SLA_HOURS, "breached": breached,
            "note": ("Нарушения зафиксированы событием expert.sla_breach" if breached
                     else "Норматив ИВП-1 (≤ 8 ч) соблюдается по всем незакрытым объектам")}


# ================================================================ MOD-AI
@router.get("/ai/forecast", dependencies=[mod_guard("MOD-AI")])
def ai_forecast(db=Depends(get_db), user: AuthUser = Depends(require("view"))):
    """Живой пересчёт прогноза (детерминированная модель v4.0-srv)."""
    return {"tech_gaps": ai_svc.tech_gap_forecast(db), "fail_risk": ai_svc.failure_risk(db),
            "model": ai_svc.MODEL_VERSION}


@router.post("/ai/run", dependencies=[mod_guard("MOD-AI")])
def ai_run(db=Depends(get_db), user: AuthUser = Depends(require("ai.run"))):
    """Прогнозный цикл ИВП-7: tech-gap + риски этапов + рекомендации (conf ≥ 0.7)."""
    evs: list = []
    res = ai_svc.run_cycle(db, evs, author=user.login)
    db.commit()
    _publish(evs)
    audit.record("Запуск ИИ-прогнозирования", f"{res['run_id']} · ИВП-7 · модель {res['model']}",
                 "Успех", user=user.login, role=user.role)
    return res


@router.get("/ai/recommendations", dependencies=[mod_guard("MOD-AI")])
def ai_recommendations(db=Depends(get_db), user: AuthUser = Depends(require("view"))):
    return ai_svc.latest_run(db)


@router.post("/ai/recommendations/{rid}/accept", dependencies=[mod_guard("MOD-AI")])
def ai_accept(rid: int, db=Depends(get_db), user: AuthUser = Depends(require("ai.accept"))):
    evs: list = []
    try:
        r = ai_svc.accept(db, rid, user.login, evs)
    except KeyError:
        raise HTTPException(404, f"Рекомендация {rid} не найдена")
    except ValueError as ex:
        raise HTTPException(409, str(ex))
    db.commit()
    _publish(evs)
    audit.record("Принятие ИИ-рекомендации", f"{rid} · {r.text[:80]}", "Успех",
                 user=user.login, role=user.role)
    return ai_svc.rec_dict(r)
