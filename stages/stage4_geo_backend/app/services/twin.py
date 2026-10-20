"""Цифровой двойник управленческого состояния предприятия (ТЗ п.2.1).

Двойник = снимок верифицированного паспорта (CRC32) + производные метрики профиля.
Пересборка — по событию profile.updated (подписка регистрируется в startup ядра).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select

from ..db import session_scope
from ..kernel.bus import get_bus
from ..models import Maturity, OrgCompetency, Organization, Twin
from . import maturity as mat
from .passport import snapshot_crc


def build_twin(org_id: str, publish: bool = True, author: str = "system") -> dict:
    with session_scope() as db:
        org = db.get(Organization, org_id)
        if org is None:
            raise KeyError(f"Организация {org_id} не найдена")
        crc = snapshot_crc(db, org.id)
        m = db.get(Maturity, org_id)
        gaps = mat.org_gaps(db, org, m)
        real_gaps = 0 if (len(gaps) == 1 and "не выявлено" in gaps[0]) else len(gaps)
        index_i = mat.maturity_index(m.trl, m.mrl, m.irl) if m else 0.0
        comps = {c.comp: c.level for c in db.scalars(select(OrgCompetency).where(OrgCompetency.org_id == org_id))}
        fills = mat.section_fill(db, org_id)
        snap = {"id": org.id, "inn": org.inn, "fill": fills, "comps": comps,
                "trl": m.trl if m else None, "mrl": m.mrl if m else None, "irl": m.irl if m else None,
                "status": org.status, "stage": org.lc_stage}
        tw = db.get(Twin, org_id)
        if tw is None:
            tw = Twin(org_id=org_id)
            db.add(tw)
        tw.crc32 = crc
        tw.snapshot = json.dumps(snap, ensure_ascii=False, sort_keys=True)
        tw.index_i = index_i
        tw.gaps_count = real_gaps
        tw.built_at = datetime.now(timezone.utc)
        db.flush()
        out = {"org_id": org_id, "crc32": crc, "index_i": index_i, "gaps": real_gaps,
               "built_at": tw.built_at.strftime("%Y-%m-%d %H:%M:%S")}
    if publish:
        get_bus().publish("twin.rebuilt", "MOD-PROF",
                          f"Цифровой двойник {org_id}: I={index_i}, снимок {crc}, разрывов: {real_gaps}")
    return out


def get_twin(org_id: str) -> dict | None:
    with session_scope() as db:
        tw = db.get(Twin, org_id)
        if tw is None:
            return None
        return {"org_id": tw.org_id, "crc32": tw.crc32, "index_i": tw.index_i,
                "gaps": tw.gaps_count, "snapshot": json.loads(tw.snapshot),
                "built_at": tw.built_at.strftime("%Y-%m-%d %H:%M:%S")}


def register_twin_subscriptions() -> None:
    """Подписка двойника на profile.updated (event-driven, через шину ядра)."""
    def on_profile_updated(ev: dict) -> None:
        # payload вида "Пересчет профиля E01 ..." — извлекаем ID организации
        import re
        m = re.search(r"\bE\d{2,4}\b", ev.get("payload", ""))
        if m:
            try:
                build_twin(m.group(0), publish=True)
            except KeyError:
                pass
    get_bus().subscribe("profile.updated", on_profile_updated)
