"""MOD-REPORT: API генерации отчётов (реальные файлы DOCX/XLSX/PDF)."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select

from ..config import settings
from ..db import get_db
from ..kernel import audit
from ..kernel.bus import get_bus
from ..kernel.iam import AuthUser, require
from ..models import Maturity, Organization, Project, Risk
from ..services import maturity as mat
from ..services import passport as psvc
from ..services import reports as rsvc
from .niokr import _project_dict, portfolio

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

XLSX_MT = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX_MT = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _timed(fn, name: str, user: AuthUser, obj: str):
    t0 = time.monotonic()
    data = fn()
    dt = round(time.monotonic() - t0, 2)
    limit = settings().report_max_sec
    if dt > limit:
        get_bus().publish("report.failed", "MOD-REPORT",
                          f"Нарушен норматив времени: {name} — {dt} c > {limit} c", sev="alert")
        raise HTTPException(500, f"Нарушен норматив ТЗ: генерация {dt} c > {limit} c")
    get_bus().publish("report.generated", "MOD-REPORT", f"{name}: сформирован за {dt} с (норматив ≤ {limit} с)")
    try:   # телеметрия KPI-4 (Этап 8): время отклика при формировании отчета
        from ..services import kpi as kpi_svc
        kpi_svc.record_telemetry("KPI-4", dt)
    except Exception:
        pass
    audit.record("Формирование отчета", f"{obj} · {dt} c", "Успех", user=user.login, role=user.role)
    return data, dt


def _dl(data: bytes, filename: str, mt: str) -> Response:
    from urllib.parse import quote
    return Response(content=data, media_type=mt,
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})


@router.get("/registry.xlsx")
def registry_xlsx(db=Depends(get_db), user: AuthUser = Depends(require("report.run"))):
    def gen():
        rows = []
        for o in db.scalars(select(Organization).order_by(Organization.id)):
            m = db.get(Maturity, o.id)
            fills = mat.section_fill(db, o.id)
            rows.append({"id": o.id, "name": o.name, "type": o.org_type, "city": o.city, "reg": o.region,
                         "inn": o.inn, "trl": m.trl if m else None, "mrl": m.mrl if m else None,
                         "irl": m.irl if m else None,
                         "index_i": mat.maturity_index(m.trl, m.mrl, m.irl) if m else None,
                         "fill_total": mat.fill_total(fills), "status": o.status,
                         "stage": o.lc_stage, "rev": o.revenue})
        return rsvc.build_orgs_xlsx(rows)
    data, dt = _timed(gen, "Реестр организаций (XLSX)", user, "registry.xlsx")
    return _dl(data, "technocontour_registry.xlsx", XLSX_MT)


@router.get("/evm.xlsx")
def evm_xlsx(db=Depends(get_db), user: AuthUser = Depends(require("report.run"))):
    def gen():
        projects = [_project_dict(db, p) for p in db.scalars(select(Project).order_by(Project.id))]
        pairs = [(p, db.get(Organization, p.org_id)) for p in db.scalars(select(Project))
                 if db.get(Organization, p.org_id)]
        from ..services import evm as evm_svc
        agg = evm_svc.portfolio_evm(pairs)
        return rsvc.build_evm_xlsx(projects, agg)
    data, dt = _timed(gen, "EVM портфеля (XLSX)", user, "evm.xlsx")
    return _dl(data, "technocontour_evm.xlsx", XLSX_MT)


@router.get("/passport/{org_id}.docx")
def passport_docx(org_id: str, db=Depends(get_db), user: AuthUser = Depends(require("view"))):
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(404, "Организация не найдена")
    def gen():
        pas = psvc.passport_dict(db, org)
        card = {"id": org.id, "name": org.name}
        return rsvc.build_passport_docx(card, pas)
    data, dt = _timed(gen, f"Паспорт {org_id} (DOCX)", user, f"passport_{org_id}.docx")
    return _dl(data, f"passport_{org_id}.docx", DOCX_MT)


@router.get("/portfolio.pdf")
def portfolio_pdf(db=Depends(get_db), user: AuthUser = Depends(require("report.run"))):
    def gen():
        projects = [_project_dict(db, p) for p in db.scalars(select(Project).order_by(Project.id))]
        pairs = [(p, db.get(Organization, p.org_id)) for p in db.scalars(select(Project))
                 if db.get(Organization, p.org_id)]
        from ..services import evm as evm_svc
        agg = {"total_projects": len(pairs), **evm_svc.portfolio_evm(pairs)}
        risks = [{"id": r.id, "cat": r.category, "t": r.title, "p": r.prob, "i": r.impact, "st": r.status}
                 for r in db.scalars(select(Risk))]
        return rsvc.build_portfolio_pdf(agg, projects, risks)
    data, dt = _timed(gen, "Портфель НИОКР (PDF)", user, "portfolio.pdf")
    return _dl(data, "technocontour_portfolio.pdf", "application/pdf")
