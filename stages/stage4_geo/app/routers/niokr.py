"""MOD-NIOKR: жизненный цикл проектов (стадии 0–8), контрольные точки Go/No-Go, EVM, PERT."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from ..db import get_db
from ..kernel import audit
from ..kernel.bus import get_bus
from ..kernel.iam import AuthUser, require
from ..models import EvmSnapshot, Organization, Project, ProjectGate
from ..services import evm as evm_svc

router = APIRouter(prefix="/api/v1/niokr", tags=["niokr"])

STAGES = ["Фундаментальные исследования", "Поисковые НИР", "Прикладные НИР", "ОКР",
          "Доводка и испытания", "Сертификация", "Подготовка производства",
          "Серийное производство", "Коммерциализация"]


def _days_left(p: Project) -> int:
    return (p.deadline - date.today()).days if p.deadline else 0


def _project_dict(db, p: Project) -> dict:
    org = db.get(Organization, p.org_id)
    e = evm_svc.evm(p, org) if org else None
    return {"id": p.id, "name": p.name, "org_id": p.org_id,
            "org": org.short_name if org else "?", "stage": p.lc_stage,
            "stage_name": STAGES[p.lc_stage], "gate": p.gate,
            "deadline": p.deadline.isoformat() if p.deadline else None,
            "budget": p.budget, "trlT": p.trl_target, "trlC": p.trl_current,
            "evm": e, "pert": evm_svc.pert(p, _days_left(p))}


@router.get("/projects")
def projects(q: Optional[str] = None, db=Depends(get_db), user: AuthUser = Depends(require("view"))):
    rows = list(db.scalars(select(Project).order_by(Project.id)))
    if q:
        ql = q.lower()
        rows = [p for p in rows if ql in p.name.lower() or ql in p.id.lower()]
    return {"total": len(rows), "items": [_project_dict(db, p) for p in rows]}


@router.get("/projects/{pid}")
def project(pid: str, db=Depends(get_db), user: AuthUser = Depends(require("view"))):
    p = db.get(Project, pid)
    if p is None:
        raise HTTPException(404, f"Проект {pid} не найден")
    gates = [{"stage": g.stage, "decision": g.decision, "comment": g.comment,
              "by": g.decided_by, "at": g.decided_at.strftime("%Y-%m-%d %H:%M")}
             for g in db.scalars(select(ProjectGate).where(ProjectGate.project_id == pid)
                                 .order_by(ProjectGate.id.desc()).limit(20))]
    snaps = [{"pv": s.pv, "ev": s.ev, "ac": s.ac, "spi": s.spi, "cpi": s.cpi,
              "at": s.calc_at.strftime("%Y-%m-%d %H:%M")}
             for s in db.scalars(select(EvmSnapshot).where(EvmSnapshot.project_id == pid)
                                 .order_by(EvmSnapshot.id.desc()).limit(30))]
    return {**_project_dict(db, p), "gates": gates, "evm_history": snaps}


class GateDecision(BaseModel):
    decision: str              # go | no-go | review
    comment: str = ""


@router.post("/projects/{pid}/gates")
def gate(pid: str, body: GateDecision, db=Depends(get_db),
         user: AuthUser = Depends(require("gate"))):
    """Контрольная точка Go/No-Go (ИВП-3): решение фиксируется append-only,
    go → переход на следующую стадию, no-go → откат стадии."""
    p = db.get(Project, pid)
    if p is None:
        raise HTTPException(404, f"Проект {pid} не найден")
    if body.decision not in ("go", "no-go", "review"):
        raise HTTPException(422, "Допустимые решения: go, no-go, review")
    org = db.get(Organization, p.org_id)
    evs: list[tuple] = []
    if body.decision == "go":
        if p.lc_stage >= 8:
            raise HTTPException(409, "Проект уже на финальной стадии")
        p.lc_stage += 1
        p.gate = "go"
        if org:
            org.lc_stage = p.lc_stage
        evs.append(("niokr.gate_decision", "MOD-NIOKR",
                    f"{pid}: стадия {p.lc_stage - 1}→{p.lc_stage} · GO · {STAGES[p.lc_stage]}", "info"))
    elif body.decision == "no-go":
        prev = max(0, p.lc_stage - 1)
        p.lc_stage = prev
        p.gate = "no-go"
        if org:
            org.lc_stage = prev
        evs.append(("niokr.gate_decision", "MOD-NIOKR",
                    f"{pid}: стадия {p.lc_stage + 1}→{p.lc_stage} · NO-GO · откат на {STAGES[p.lc_stage]}", "alert"))
    else:
        p.gate = "review"
        evs.append(("niokr.gate_decision", "MOD-NIOKR", f"{pid}: решение REVIEW (доработка)", "warn"))
    db.add(ProjectGate(project_id=pid, stage=p.lc_stage, decision=body.decision,
                       comment=body.comment or None, decided_by=user.login))
    # фиксация EVM-снимка на момент решения (основание для ИВП-6)
    if org:
        e = evm_svc.evm(p, org)
        db.add(EvmSnapshot(project_id=pid, pv=e["pv"], ev=e["ev"], ac=e["ac"],
                           spi=e["spi"], cpi=e["cpi"]))
        evs.append(("niokr.evm_snapshot", "MOD-NIOKR",
                    f"{pid}: PV={e['pv']} EV={e['ev']} AC={e['ac']} SPI={e['spi']} CPI={e['cpi']}", "info"))
        evs.append(("profile.updated", "MOD-PROF", f"Пересчет профиля {org.id} (ИВП-2)", "info"))
    db.commit()
    for t, s, pl, sv in evs:
        get_bus().publish(t, s, pl, sv)
    audit.record("Решение контрольной точки", f"{pid} · {body.decision.upper()}" +
                 (f" · {body.comment}" if body.comment else ""), "Успех",
                 user=user.login, role=user.role)
    return _project_dict(db, p)


@router.get("/portfolio/summary")
def portfolio(db=Depends(get_db), user: AuthUser = Depends(require("view"))):
    """Агрегированные показатели портфеля (MOD-PORTF): ΣEV/ΣPV, ΣEV/ΣAC, антирейтинг SPI."""
    pairs = []
    for p in db.scalars(select(Project)):
        o = db.get(Organization, p.org_id)
        if o:
            pairs.append((p, o))
    agg = evm_svc.portfolio_evm(pairs)
    by_stage = [0] * 9
    for p, _ in pairs:
        by_stage[p.lc_stage] += 1
    return {"total_projects": len(pairs), "stage_names": STAGES, "by_stage": by_stage, **agg}
