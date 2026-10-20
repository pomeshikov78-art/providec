"""MOD-COOP и MOD-RISK: подбор партнёров, матрица рисков (API)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from ..db import get_db
from ..kernel import audit
from ..kernel.iam import AuthUser, require
from ..models import Organization, Risk
from ..services import coop as coop_svc

router = APIRouter(prefix="/api/v1", tags=["coop-risk"])


@router.get("/coop/{org_id}/partners")
def partners(org_id: str, top: int = 5, db=Depends(get_db), user: AuthUser = Depends(require("view"))):
    try:
        return {"target": org_id, "weights": {"comp": 0.45, "geo": 0.20, "stage": 0.20, "inv": 0.15},
                "items": coop_svc.find_partners(db, org_id, top=top)}
    except KeyError:
        raise HTTPException(404, f"Организация {org_id} не найдена")


@router.get("/risks")
def risks(db=Depends(get_db), user: AuthUser = Depends(require("view"))):
    rows = [{"id": r.id, "t": r.title, "cat": r.category, "p": r.prob, "i": r.impact,
             "score": r.score, "own": r.owner_module, "st": r.status, "mit": r.mitigation}
            for r in db.scalars(select(Risk).order_by(Risk.id))]
    matrix = [[0] * 5 for _ in range(5)]
    for r in rows:
        matrix[min(r["i"] - 1, 4)][min(r["p"] - 1, 4)] += 1
    return {"total": len(rows), "items": rows, "matrix5x5": matrix,
            "top3": sorted(rows, key=lambda x: -x["score"])[:3]}
