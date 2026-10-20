"""MOD-PASS: реестр организаций и цифровые паспорта (API)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select

from ..db import get_db
from ..kernel import audit
from ..kernel.bus import get_bus
from ..kernel.iam import AuthUser, require
from ..models import Maturity, Organization, PassportVersion
from ..services import maturity as mat
from ..services import passport as psvc

router = APIRouter(prefix="/api/v1/orgs", tags=["pass"])


def _org_or_404(db, org_id: str) -> Organization:
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(404, f"Организация {org_id} не найдена")
    return org


def _org_card(db, o: Organization) -> dict:
    m = db.get(Maturity, o.id)
    fills = mat.section_fill(db, o.id)
    return {"id": o.id, "name": o.name, "short": o.short_name, "type": o.org_type,
            "city": o.city, "reg": o.region, "lat": o.lat, "lon": o.lon, "inn": o.inn,
            "year": o.founded, "emp": o.employees, "rev": o.revenue,
            "trl": m.trl if m else None, "mrl": m.mrl if m else None, "irl": m.irl if m else None,
            "index_i": mat.maturity_index(m.trl, m.mrl, m.irl) if m else None,
            "status": o.status, "stage": o.lc_stage, "invest": o.invest, "riskIdx": o.risk_idx,
            "links": [x for x in (o.links or "").split(",") if x],
            "fill": fills, "fill_total": mat.fill_total(fills)}


@router.get("")
def list_orgs(q: Optional[str] = None, type: Optional[str] = None, status: Optional[str] = None,
              region: Optional[str] = None, page: int = 1, size: int = Query(200, le=500),
              db=Depends(get_db), user: AuthUser = Depends(require("view"))):
    query = select(Organization)
    if q:
        like = f"%{q}%"
        query = query.where(or_(Organization.name.ilike(like), Organization.short_name.ilike(like),
                                Organization.city.ilike(like), Organization.inn.ilike(like),
                                Organization.id.ilike(like)))
    if type:
        query = query.where(Organization.org_type == type)
    if status:
        query = query.where(Organization.status == status)
    if region:
        query = query.where(Organization.region == region)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = list(db.scalars(query.order_by(Organization.id).offset((page - 1) * size).limit(size)))
    # ABAC: L3/L4 видят только согласованный круг (L4 — своё предприятие)
    if user.role == "L4" and user.org_id:
        rows = [r for r in rows if r.id == user.org_id]
    return {"total": total, "page": page, "size": size,
            "items": [_org_card(db, r) for r in rows]}


@router.get("/{org_id}")
def get_org(org_id: str, db=Depends(get_db), user: AuthUser = Depends(require("view"))):
    return _org_card(db, _org_or_404(db, org_id))


@router.get("/{org_id}/passport")
def get_passport(org_id: str, db=Depends(get_db), user: AuthUser = Depends(require("view"))):
    org = _org_or_404(db, org_id)
    return psvc.passport_dict(db, org)


class FieldUpdate(BaseModel):
    updates: dict[int, str]        # field_id → значение


@router.put("/{org_id}/passport")
def put_passport(org_id: str, body: FieldUpdate, db=Depends(get_db),
                 user: AuthUser = Depends(require("org.write"))):
    """Сохранение полей → новая версия паспорта (журнал изменений + CRC32) → ИВП-2.

    События публикуются ПОСЛЕ commit транзакции запроса (иначе вложенные
    сессии шины конфликтуют с незакрытой транзакцией — SQLite single-writer).
    """
    org = _org_or_404(db, org_id)
    evs: list[tuple] = []
    res = psvc.apply_field_updates(db, org, body.updates, author=user.login, role=user.role, events=evs)
    db.commit()
    for t, s, p, sv in evs:
        get_bus().publish(t, s, p, sv)
    get_bus().publish("geo.data_updated", "MOD-GEO", f"Геоданные {org_id} обновлены (ИВП-GEO-1)")
    audit.record("Сохранение версии паспорта", f"{org_id} · ред. {res['ver_n']} · изменений {res['changes']}",
                 "Успех", user=user.login, role=user.role)
    return res


@router.get("/{org_id}/passport/versions")
def versions(org_id: str, db=Depends(get_db), user: AuthUser = Depends(require("view"))):
    _org_or_404(db, org_id)
    rows = list(db.scalars(select(PassportVersion).where(PassportVersion.org_id == org_id)
                           .order_by(PassportVersion.ver_n.desc()).limit(20)))
    return [{"ver_n": v.ver_n, "date": v.created_at.strftime("%Y-%m-%d %H:%M"),
             "author": v.author, "crc32": v.crc32, "fill_total": v.fill_total,
             "changes": v.changes} for v in rows]


@router.post("/{org_id}/passport/quality")
def quality(org_id: str, db=Depends(get_db), user: AuthUser = Depends(require("view"))):
    org = _org_or_404(db, org_id)
    evs: list[tuple] = []
    res = psvc.quality_check(db, org, events=evs)
    db.commit()
    for t, s, p, sv in evs:
        get_bus().publish(t, s, p, sv)
    audit.record("Контроль качества данных паспорта", org_id,
                 "Успех" if res["ok"] else f"Замечания: {len(res['issues'])}",
                 user=user.login, role=user.role)
    return res


@router.post("/{org_id}/verify")
def verify(org_id: str, submit: bool = False, db=Depends(get_db),
           user: AuthUser = Depends(require("view"))):
    org = _org_or_404(db, org_id)
    from ..kernel.iam import _deny, can
    evs: list[tuple] = []
    if submit:
        # отправка на верификацию — операция владельца паспорта (L4 свой / полномочные роли)
        if not can(user, "org.write", org_id):
            _deny(user, "Отправка паспорта на верификацию", org_id)
        res = psvc.submit_for_verification(db, org, user.login, user.role, events=evs)
    else:
        if not can(user, "expert.approve"):
            _deny(user, "Верификация паспорта", org_id)
        res = psvc.verify(db, org, expert=user.login, events=evs)
    db.commit()
    for t, s, p, sv in evs:
        get_bus().publish(t, s, p, sv)
    audit.record("Верификация паспорта" if not submit else "Отправка на верификацию", org_id,
                 "Успех", user=user.login, role=user.role)
    return res
