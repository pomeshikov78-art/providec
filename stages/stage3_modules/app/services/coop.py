"""MOD-COOP: скоринг кооперационного соответствия (апробирован в прототипе v8).

Весовая формула: компетентностное соответствие 45% + географическая близость 20%
+ совместимость стадии ЖЦ 20% + инвестиционная привлекательность 15%.
"""
from __future__ import annotations

import math
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Maturity, OrgCompetency, Organization


def _geo_score(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Близость: 100 при ≤300 км, 50 при ≤1200 км, 25 при ≤2500 км, иначе 10."""
    d = math.hypot((lat1 - lat2) * 111.0, (lon1 - lon2) * 70.0)
    if d <= 300:
        return 100
    if d <= 1200:
        return 50
    if d <= 2500:
        return 25
    return 10


def _stage_score(s1: int, s2: int) -> float:
    return max(0, 100 - abs(s1 - s2) * 20)


def score_pair(a: Organization, b: Organization, comps_a: Dict[str, int],
               comps_b: Dict[str, int]) -> dict:
    comp_keys = ("sci", "des", "prod", "test", "dig", "mng")
    comp_match = 100 - sum(abs(comps_a.get(k, 0) - comps_b.get(k, 0)) for k in comp_keys) * 100 / 30
    geo = _geo_score(a.lat, a.lon, b.lat, b.lon)
    stage = _stage_score(a.lc_stage, b.lc_stage)
    inv = (b.invest - 1) / 4.0 * 100
    total = round(comp_match * 0.45 + geo * 0.20 + stage * 0.20 + inv * 0.15)
    return {"comp": round(comp_match), "geo": round(geo), "stage": round(stage),
            "inv": round(inv), "total": total}


def find_partners(db: Session, target_id: str, top: int = 5) -> List[dict]:
    org = db.get(Organization, target_id)
    if org is None:
        raise KeyError(target_id)
    all_orgs = [o for o in db.scalars(select(Organization)) if o.id != target_id]
    comps = {}
    for c in db.scalars(select(OrgCompetency)):
        comps.setdefault(c.org_id, {})[c.comp] = c.level
    scored = []
    for o in all_orgs:
        sc = score_pair(org, o, comps.get(target_id, {}), comps.get(o.id, {}))
        scored.append({"id": o.id, "short": o.short_name, "city": o.city, "reg": o.region,
                       "type": o.org_type, **sc})
    scored.sort(key=lambda x: -x["total"])
    return scored[:top]
