"""MOD-PASS: workflow верификации паспорта, версионность (CRC32), контроль качества.

Процессы (ТЗ п.4.5, Задача 1):
  * ИВП-1: регистрация → валидация → обогащение (MOD-INT) → верификация (MOD-EXPERT)
    → статус «Подтверждён» → события passport.* ;
  * версионность: каждое сохранение создает версию с журналом изменений и CRC32-снимком
    (хранение ≥ 10 версий, Задача 1.5);
  * контроль качества: ИНН/ОГРН (ФНС), полнота ≥ 95% (ИВП-1), пороги разделов (Прил. 2.14),
    статус верификации → события pass.quality_ok / pass.quality_issues.
"""
from __future__ import annotations

import json
import zlib
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..kernel.bus import get_bus
from ..models import (Maturity, Organization, PassportField, PassportSection,
                      PassportValue, PassportVersion)
from . import maturity as mat
from .validators import inn_fix, inn_valid, ogrn_valid


def _emit(events, type_: str, source: str, payload: str, sev: str = "info") -> None:
    """Публикация события: отложенно (в транзакции запроса) или немедленно."""
    if events is not None:
        events.append((type_, source, payload, sev))
    else:
        get_bus().publish(type_, source, payload, sev)


# ---------------------------------------------------------------- представление
def passport_dict(db: Session, org: Organization) -> dict:
    sections = list(db.scalars(select(PassportSection).order_by(PassportSection.n)))
    fields = list(db.scalars(select(PassportField).order_by(PassportField.section_n, PassportField.ord)))
    values = {v.field_id: v for v in db.scalars(select(PassportValue).where(PassportValue.org_id == org.id))}
    fills = mat.section_fill(db, org.id)
    out_sections = []
    for s in sections:
        fs = [f for f in fields if f.section_n == s.n]
        out_sections.append({
            "n": s.n, "name": s.name, "threshold": s.threshold, "fill": fills[s.n - 1],
            "fields": [{
                "id": f.id, "name": f.name, "ftype": f.ftype, "required": f.required,
                "source": f.source,
                "value": values[f.id].value if f.id in values else None,
                "filled": bool(f.id in values and values[f.id].value),
            } for f in fs],
        })
    ver = db.scalars(select(PassportVersion).where(PassportVersion.org_id == org.id)
                     .order_by(PassportVersion.ver_n.desc()).limit(1)).first()
    return {"org_id": org.id, "status": org.status, "fill_total": mat.fill_total(fills),
            "version": ({"n": ver.ver_n, "crc32": ver.crc32, "date": ver.created_at.strftime("%Y-%m-%d %H:%M")}
                        if ver else None),
            "sections": out_sections}


# ---------------------------------------------------------------- сохранение версии
def snapshot_crc(db: Session, org_id: str) -> str:
    """CRC32-снимок ключевых атрибутов паспорта (механизм из прототипа v8 / АССПР v2.4)."""
    org = db.get(Organization, org_id)
    fills = mat.section_fill(db, org_id)
    comps = {}
    from ..models import OrgCompetency
    for c in db.scalars(select(OrgCompetency).where(OrgCompetency.org_id == org.id)):
        comps[c.comp] = c.level
    m = db.get(Maturity, org.id)
    blob = json.dumps({"id": org.id, "inn": org.inn, "fill": fills, "comps": comps,
                       "trl": m.trl if m else None, "mrl": m.mrl if m else None,
                       "irl": m.irl if m else None, "status": org.status, "stage": org.lc_stage},
                      ensure_ascii=False, sort_keys=True)
    return "0x%08x" % (zlib.crc32(blob.encode("utf-8")) & 0xFFFFFFFF)


def save_version(db: Session, org: Organization, changes: List[dict], author: str,
                 role: Optional[str] = None, publish_events: bool = True,
                 events: Optional[List[tuple]] = None) -> dict:
    """Фиксирует новую версию паспорта: журнал изменений + CRC32-снимок + события."""
    fills = mat.section_fill(db, org.id)
    crc = snapshot_crc(db, org.id)
    last = db.scalars(select(func.max(PassportVersion.ver_n)).where(PassportVersion.org_id == org.id)).first()
    ver = PassportVersion(org_id=org.id, ver_n=(last or 0) + 1,
                          changes=json.dumps(changes, ensure_ascii=False), crc32=crc,
                          fill_total=mat.fill_total(fills), author=author, role_level=role)
    db.add(ver)
    db.flush()
    if publish_events:
        _emit(events, "passport.updated", "MOD-PASS",
              f'{org.id}: сохранена «ред. {ver.ver_n}» · изменений {len(changes)} · полнота {ver.fill_total}%')
        _emit(events, "profile.updated", "MOD-PROF", f"Пересчет профиля {org.id} (ИВП-2)")
    return {"ver_n": ver.ver_n, "crc32": crc, "fill_total": ver.fill_total, "changes": len(changes)}


def apply_field_updates(db: Session, org: Organization, updates: Dict[int, str], author: str,
                        role: Optional[str] = None, events: Optional[List[tuple]] = None) -> dict:
    """Применяет правки полей (field_id → value) и сохраняет новую версию паспорта."""
    changes: List[dict] = []
    fields = {f.id: f for f in db.scalars(select(PassportField))}
    values = {v.field_id: v for v in db.scalars(select(PassportValue).where(PassportValue.org_id == org.id))}
    for fid, new_val in updates.items():
        f = fields.get(fid)
        if f is None:
            continue
        old = values[fid].value if fid in values else None
        new_val = (new_val or "").strip()
        if new_val == (old or ""):
            continue
        if fid in values:
            values[fid].value = new_val or None
            values[fid].updated_by = author
            values[fid].updated_at = datetime.now(timezone.utc)
        else:
            pv = PassportValue(org_id=org.id, field_id=fid, value=new_val or None, updated_by=author)
            db.add(pv)
        changes.append({"section": f.section_n, "field": f.name, "old": old, "new": new_val})
    return save_version(db, org, changes, author, role, events=events)


# ---------------------------------------------------------------- workflow верификации (ИВП-1)
def submit_for_verification(db: Session, org: Organization, author: str, role: str,
                            events: Optional[List[tuple]] = None) -> dict:
    fills = mat.section_fill(db, org.id)
    total = mat.fill_total(fills)
    if org.status == "verified":
        return {"status": org.status, "detail": "Паспорт уже подтверждён"}
    org.status = "pending"
    db.flush()
    _emit(events, "passport.pending_verification", "MOD-PASS",
          f"{org.id} → очередь MOD-EXPERT (полнота {total}%)")
    return {"status": "pending", "fill_total": total,
            "criteria_met": total >= settings().passport_fill_min}


def verify(db: Session, org: Organization, expert: str, conclusion: str = "соответствует",
           events: Optional[List[tuple]] = None) -> dict:
    if conclusion.startswith("соответствует"):
        org.status = "verified"
        db.flush()
        _emit(events, "expert.conclusion_ready", "MOD-EXPERT", f"{org.id}: {conclusion} (ЭЦП)")
        _emit(events, "passport.verified", "MOD-PASS", f"{org.id} · ЭЦП верификатора подтверждена")
        _emit(events, "profile.updated", "MOD-PROF", f"Пересчет профиля {org.id} (ИВП-2)")
    else:
        org.status = "draft"
        db.flush()
        _emit(events, "expert.conclusion_ready", "MOD-EXPERT",
              f"{org.id}: {conclusion} — возвращён на доработку", "warn")
    return {"status": org.status}


# ---------------------------------------------------------------- контроль качества
def quality_check(db: Session, org: Organization, events: Optional[List[tuple]] = None) -> dict:
    """Контроль качества данных (критерии ИВП-1 + пороги Прил. 2.14 + ФНС-валидация)."""
    issues: List[str] = []
    if not inn_valid(org.inn):
        issues.append(f"ИНН {org.inn}: контрольная сумма не сходится (методика ФНС) — расхождение с ЕГРЮЛ; "
                      f"нормализация: {inn_fix(org.inn)}")
    if org.ogrn and not ogrn_valid(org.ogrn):
        issues.append(f"ОГРН {org.ogrn}: контрольное число не сходится — требуется сверка")
    fills = mat.section_fill(db, org.id)
    total = mat.fill_total(fills)
    if total < settings().passport_fill_min:
        issues.append(f"Полнота паспорта {total}% < {settings().passport_fill_min}% (критерий ИВП-1)")
    th = {s.n: s.threshold for s in db.scalars(select(PassportSection))}
    low = [f"Р{n}: {fills[n-1]}% < {th.get(n, 90)}%" for n in range(1, 13) if fills[n - 1] < th.get(n, 90)]
    if low:
        issues.append("Полнота ниже порога по разделам (Прил. 2.14): " + "; ".join(low))
    if org.status != "verified":
        issues.append("Паспорт не верифицирован (статус: " + ("на верификации" if org.status == "pending" else "черновик") + ")")
    ok = not issues
    _emit(events, "pass.quality_ok" if ok else "pass.quality_issues", "MOD-PASS",
          f'{org.id} «{org.short_name}»: ' + ("замечаний нет" if ok else f"{len(issues)} замечаний"),
          "info" if ok else "warn")
    return {"org_id": org.id, "ok": ok, "fill_total": total, "issues": issues}
