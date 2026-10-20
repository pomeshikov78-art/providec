"""Импорт цифровых паспортов НТП из АССПР v2.4 в БД MOD-PASS (ТЗ п.5.10, Прил. 8).

Пакет АССПР (JSON): {org_name, target_org_id?, ver?, date?, approval?, completeness?,
issues?, note?, fields?: {имя поля → значение}, comps?: {sci..mng: 0-5},
trl/mrl/irl?, newOrg?: {...}}.
Применение: сопоставление организации (или создание при newOrg), обновление
компетенций/зрелости, правка полей паспорта по имени → новая версия (CRC32),
события int.asspr_imported → profile.updated (ИВП-2).
"""
from __future__ import annotations

import json
import time
from datetime import date as ddate

from sqlalchemy import func, select

from ..db import session_scope
from ..models import (AssprPackage, Maturity, OrgCompetency, OrgRadar, Organization,
                      PassportField)
from . import passport as psvc


def import_asspr(pkg: dict, actor: str) -> dict:
    org_name = pkg.get("org_name") or (pkg.get("newOrg") or {}).get("name") or ""
    if not org_name:
        return {"applied": False, "reason": "В пакете отсутствует наименование организации"}
    evs: list[tuple] = []
    with session_scope() as db:
        # 1) сопоставление/создание организации
        org_id = pkg.get("target_org_id")
        org = db.get(Organization, org_id) if org_id else None
        if org is None:
            org = db.scalars(select(Organization).where(Organization.name == org_name)).first()
        if org is None and pkg.get("newOrg"):
            n = db.scalar(select(func.count()).select_from(Organization)) + 1
            o = pkg["newOrg"]
            org = Organization(id=f"E{n:03d}", name=o.get("name", org_name),
                               short_name=o.get("short", org_name[:40]), org_type=o.get("type", "ent"),
                               city=o.get("city", "Москва"), region=o.get("reg", "Центральный ФО"),
                               lat=o.get("lat", 55.75), lon=o.get("lon", 37.62),
                               inn=o.get("inn", "7700000000"), founded=int(o.get("year", 2020)),
                               employees=int(o.get("emp", 100)), revenue=float(o.get("rev", 0.5)),
                               status="draft", links="")
            db.add(org)
            db.flush()
            evs.append(("pass.new_registered", "MOD-PASS", f"Новая организация из АССПР: {org.id} «{org.short_name}»", "info"))
        if org is None:
            return {"applied": False, "reason": f"Организация «{org_name}» не найдена в реестре; "
                                                "укажите target_org_id или передайте newOrg"}
        # 2) регистрация пакета (идемпотентно по id)
        pkg_id = pkg.get("id") or f"ASSPR-{int(time.time())}"
        if db.get(AssprPackage, pkg_id):
            return {"applied": False, "reason": f"Пакет {pkg_id} уже импортирован (идемпотентность)"}
        db.add(AssprPackage(id=pkg_id, org_name=org_name, target_org_id=org.id,
                            ver=pkg.get("ver"), doc_date=_d(pkg.get("date")),
                            approval=pkg.get("approval"), completeness=int(pkg.get("completeness") or 0),
                            issues=int(pkg.get("issues") or 0), note=pkg.get("note"),
                            payload=json.dumps(pkg, ensure_ascii=False),
                            imported_at=ddate.today(), imported_by=actor))
        # 3) компетенции и зрелость
        comps = pkg.get("comps") or {}
        for k, v in comps.items():
            row = db.get(OrgCompetency, (org.id, k))
            if row is None:
                db.add(OrgCompetency(org_id=org.id, comp=k, level=int(v)))
            else:
                row.level = int(v)
        if any(x in pkg for x in ("trl", "mrl", "irl")):
            m = db.get(Maturity, org.id)
            if m is None:
                m = Maturity(org_id=org.id)
                db.add(m)
            m.trl = int(pkg.get("trl", m.trl))
            m.mrl = int(pkg.get("mrl", m.mrl))
            m.irl = int(pkg.get("irl", m.irl))
        db.flush()
        # 4) поля паспорта по имени
        updates = {}
        if pkg.get("fields"):
            fields = list(db.scalars(select(PassportField)))
            by_name = {f.name.lower(): f for f in fields}
            for fname, val in pkg["fields"].items():
                f = by_name.get(str(fname).lower())
                if f:
                    updates[f.id] = str(val)
        res = {"ver_n": None, "fields": len(updates)}
        if updates:
            r = psvc.apply_field_updates(db, org, updates, author=f"АССПР:{actor}",
                                         role="L6", events=evs)
            res = {"ver_n": r.get("ver_n"), "fields": r.get("changes", 0), "crc32": r.get("crc32")}
        evs.append(("int.asspr_imported", "MOD-INT",
                    f"Пакет {pkg_id} → {org.id}: полей {res.get('fields', 0)}, ред. {res.get('ver_n')}", "info"))
        evs.append(("profile.updated", "MOD-PROF", f"Пересчет профиля {org.id} (ИВП-2)", "info"))
        db.commit()
        result = {"applied": True, "package_id": pkg_id, "org_id": org.id,
                  "fields_updated": res.get("fields", 0), "version": res.get("ver_n")}
    from ..kernel.bus import get_bus
    for t, s, p, sv in evs:
        get_bus().publish(t, s, p, sv)
    return result


def _d(v):
    try:
        return ddate.fromisoformat(v) if v else None
    except Exception:
        return None
