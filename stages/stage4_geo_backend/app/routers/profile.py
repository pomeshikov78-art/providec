"""MOD-PROF: цифровой профиль, двойник, бенчмарки (API)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from ..db import get_db
from ..kernel import audit
from ..kernel.iam import AuthUser, require
from ..models import Maturity, OrgCompetency, OrgRadar, Organization
from ..services import maturity as mat
from ..services import twin as tsvc

router = APIRouter(prefix="/api/v1", tags=["prof"])


@router.get("/profiles/benchmarks")
def bench(db=Depends(get_db), user: AuthUser = Depends(require("view"))):
    return mat.benchmarks(db)


@router.get("/profiles/{org_id}")
def profile(org_id: str, db=Depends(get_db), user: AuthUser = Depends(require("view"))):
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(404, "Организация не найдена")
    m = db.get(Maturity, org_id)
    radar = {r.dim: r.val for r in db.scalars(select(OrgRadar).where(OrgRadar.org_id == org_id))}
    comps = {c.comp: c.level for c in db.scalars(select(OrgCompetency).where(OrgCompetency.org_id == org_id))}
    index_i = mat.maturity_index(m.trl, m.mrl, m.irl) if m else None
    return {"org_id": org_id,
            "radar": [radar.get(i, 0) for i in range(1, 8)],
            "radar_dims": mat.RADAR_DIMS,
            "trl": m.trl if m else None, "mrl": m.mrl if m else None, "irl": m.irl if m else None,
            "index_i": index_i, "status_level": mat.maturity_status(index_i or 0),
            "competencies": comps,
            "gaps": mat.org_gaps(db, org, m),
            "fill": mat.section_fill(db, org_id)}


@router.get("/twins/{org_id}")
def twin(org_id: str, user: AuthUser = Depends(require("view"))):
    t = tsvc.get_twin(org_id)
    if t is None:
        t = tsvc.build_twin(org_id, publish=False)   # ленивая сборка при первом запросе
        t = tsvc.get_twin(org_id)
    return t


@router.post("/twins/{org_id}/rebuild")
def rebuild(org_id: str, user: AuthUser = Depends(require("view"))):
    res = tsvc.build_twin(org_id)
    audit.record("Пересборка цифрового двойника", org_id + " · CRC " + res["crc32"], "Успех",
                 user=user.login, role=user.role)
    return res
