"""Bootstrap-эндпоинт: единая загрузка набора данных для SPA-клиента.

Клиент (ais_providets_vN.html в серверном режиме) одним запросом получает
реестр, проекты, риски, документы и справочники — далее рендеринг локальный,
а записывающие операции идут через соответствующие API (event-driven цепочки
сохраняются на сервере).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select

from ..config import settings
from ..db import get_db
from ..kernel import registry
from ..kernel.iam import AuthUser, require
from ..models import (Document, ExpertItem, Integration, Maturity, OrgCompetency,
                      OrgRadar, Organization, Project, Risk, Stim)
from ..services import maturity as mat

router = APIRouter(prefix="/api/v1", tags=["bootstrap"])


@router.get("/bootstrap")
def bootstrap(db=Depends(get_db), user: AuthUser = Depends(require("view"))):
    s = settings()
    orgs = []
    for o in db.scalars(select(Organization).order_by(Organization.id)):
        m = db.get(Maturity, o.id)
        comps = {c.comp: c.level for c in db.scalars(select(OrgCompetency).where(OrgCompetency.org_id == o.id))}
        radar = {r.dim: r.val for r in db.scalars(select(OrgRadar).where(OrgRadar.org_id == o.id))}
        orgs.append({"id": o.id, "name": o.name, "short": o.short_name, "type": o.org_type,
                     "city": o.city, "reg": o.region, "lat": o.lat, "lon": o.lon, "inn": o.inn,
                     "year": o.founded, "emp": o.employees, "rev": o.revenue,
                     "trl": m.trl if m else 1, "mrl": m.mrl if m else 1, "irl": m.irl if m else 1,
                     "comps": comps, "radar": [radar.get(i, 0) for i in range(1, 8)],
                     "fill": mat.section_fill(db, o.id), "status": o.status, "stage": o.lc_stage,
                     "invest": o.invest, "riskIdx": o.risk_idx,
                     "links": [x for x in (o.links or "").split(",") if x]})
    projects = [{"id": p.id, "name": p.name, "ent": p.org_id, "stage": p.lc_stage, "gate": p.gate,
                 "deadline": p.deadline.isoformat() if p.deadline else None, "budget": p.budget,
                 "trlT": p.trl_target, "trlC": p.trl_current,
                 "pert": [p.pert_o, p.pert_m, p.pert_p]}
                for p in db.scalars(select(Project).order_by(Project.id))]
    risks = [{"id": r.id, "t": r.title, "cat": r.category, "p": r.prob, "i": r.impact,
              "own": r.owner_module, "st": r.status, "mit": r.mitigation}
             for r in db.scalars(select(Risk).order_by(Risk.id))]
    docs = [{"id": d.id, "t": d.title, "ent": d.org_id, "kind": d.kind, "sign": d.sign_status,
             "date": d.doc_date.isoformat() if d.doc_date else None}
            for d in db.scalars(select(Document).order_by(Document.id))]
    stims = [{"id": x.id, "ent": x.org_id, "kind": "Стимул" if x.kind == "stim" else "Санкция",
              "t": x.title, "base": x.basis, "date": x.doc_date.isoformat() if x.doc_date else None,
              "st": x.status} for x in db.scalars(select(Stim).order_by(Stim.id))]
    expert = [{"id": e.id, "ent": e.org_id, "obj": e.object, "expert": e.expert or "—",
               "since": e.since.isoformat() if e.since else None, "prio": e.priority}
              for e in db.scalars(select(ExpertItem).order_by(ExpertItem.id))]
    ints = [{"code": i.code, "n": i.name, "g": i.grp, "p": i.protocol, "f": i.period,
             "a": i.variant_a, "b": i.variant_b_mode,
             "available": (i.variant_a if s.variant == "network" else i.variant_b_mode != "unavailable")}
            for i in db.scalars(select(Integration).order_by(Integration.code))]
    return {"variant": s.variant, "app_version": s.app_version, "modules": registry.list_modules(),
            "orgs": orgs, "projects": projects, "risks": risks, "docs": docs, "stims": stims,
            "expert": expert, "integrations": ints,
            "geo": {"tile_url": s.tile_url, "h3_resolution": s.geo_h3_resolution,
                    "kde_bandwidth_km": s.geo_kde_bandwidth_km}}
