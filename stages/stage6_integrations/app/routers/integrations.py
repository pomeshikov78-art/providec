"""MOD-INT: интеграционный шлюз — статусы коннекторов, обогащение данных, импорт АССПР."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from ..config import settings
from ..connectors.base import all_status, get_connector
from ..db import get_db
from ..kernel import audit
from ..kernel.bus import get_bus
from ..kernel.iam import AuthUser, require
from ..models import Organization, PassportField
from ..services import passport as psvc

router = APIRouter(prefix="/api/v1/int", tags=["int"])


@router.get("/connectors")
def connectors(user: AuthUser = Depends(require("view"))):
    return {"variant": settings().variant, "mode": settings().connectors_mode,
            "connectors": all_status()}


@router.post("/egryul/enrich/{org_id}")
def enrich_egryul(org_id: str, db=Depends(get_db), user: AuthUser = Depends(require("view"))):
    """Автообогащение раздела 1 паспорта из ЕГРЮЛ (ИВП-1, шаг «обогащение»)."""
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(404, "Организация не найдена")
    conn = get_connector("EGRUL")
    try:
        data = conn.fetch_by_inn(org.inn)
    except (KeyError, RuntimeError) as e:
        raise HTTPException(502, f"Обмен с ЕГРЮЛ не удался: {e}")
    # маппинг ответов ЕГРЮЛ → поля раздела 1 (по имени)
    mapping = {"full_name": "полное наименование", "short_name": "сокращённое наименование",
               "okved": "оквэд", "address": "юридический адрес", "registered": "дата регистрации"}
    fields = {f.name.lower(): f for f in db.scalars(select(PassportField).where(PassportField.section_n == 1))}
    updates = {}
    applied = []
    for key, label in mapping.items():
        if key in data:
            f = next((f for n, f in fields.items() if label in n), None)
            if f:
                updates[f.id] = str(data[key])
                applied.append(label)
    evs: list[tuple] = []
    res = {"ver_n": None, "fields": 0}
    if updates:
        res = psvc.apply_field_updates(db, org, updates, author=f"ЕГРЮЛ:{user.login}",
                                       role=user.role, events=evs)
        evs.append(("int.egrul_enriched", "MOD-INT",
                    f"{org_id}: обогащено полей {len(updates)} из ЕГРЮЛ (ред. {res['ver_n']})", "info"))
    db.commit()
    for t, s, p, sv in evs:
        get_bus().publish(t, s, p, sv)
    audit.record("Обогащение паспорта из ЕГРЮЛ", f"{org_id} · полей: {len(updates)}", "Успех",
                 user=user.login, role=user.role)
    return {"egryul": data, "applied_fields": applied, "version": res.get("ver_n")}


@router.get("/gisp/{org_id}")
def gisp(org_id: str, user: AuthUser = Depends(require("view"))):
    try:
        return get_connector("GISP").products(org_id)
    except (KeyError, RuntimeError) as e:
        raise HTTPException(502, str(e))


@router.get("/rospatent/{org_id}")
def rospatent(org_id: str, user: AuthUser = Depends(require("view"))):
    try:
        return get_connector("ROSPATENT").patents(org_id)
    except (KeyError, RuntimeError) as e:
        raise HTTPException(502, str(e))


class AssprImport(BaseModel):
    package: dict


@router.post("/asspr/import")
def asspr_import(body: AssprImport, user: AuthUser = Depends(require("admin"))):
    """Импорт пакета «Цифровой паспорт НТП» из АССПР v2.4 (вариант А — API, Б — файл)."""
    res = get_connector("ASSPR").import_package(body.package, actor=user.login)
    if res.get("applied"):
        audit.record("Импорт пакета АССПР", f"{res['package_id']} → {res['org_id']}", "Успех",
                     user=user.login, role=user.role)
    else:
        audit.record("Импорт пакета АССПР", res.get("reason", "")[:120], "Отказ",
                     user=user.login, role=user.role)
    return res
