"""MOD-GEO: API геоаналитики (H3-кластеры, KDE-теплокарта, измерения, экспорт)."""
from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select

from ..config import settings
from ..db import get_db
from ..kernel import audit
from ..kernel.bus import get_bus
from ..kernel.iam import AuthUser, require
from ..models import Organization
from ..services import geo as gsvc

router = APIRouter(prefix="/api/v1/geo", tags=["geo"])


@router.get("/config")
def config(user: AuthUser = Depends(require("view"))):
    return gsvc.geo_config()


@router.get("/objects.geojson")
def objects(type: Optional[str] = None, region: Optional[str] = None, q: Optional[str] = None,
            db=Depends(get_db), user: AuthUser = Depends(require("view"))):
    t0 = time.monotonic()
    fc = gsvc.objects_geojson(db, type, region, q)
    dt = round(time.monotonic() - t0, 3)
    # норматив ИВП-GEO-1: отклик ≤ 2 с
    if dt > settings().geo_update_max_sec:
        get_bus().publish("geo.update_error", "MOD-GEO", f"Нарушен норматив: {dt} c", sev="alert")
    fc["elapsed_sec"] = dt
    return fc


@router.get("/clusters")
def clusters(resolution: Optional[int] = None, db=Depends(get_db),
             user: AuthUser = Depends(require("view"))):
    if resolution is not None and not (0 <= resolution <= 15):
        raise HTTPException(422, "Разрешение H3: 0–15")
    return gsvc.clusters_h3(db, resolution)


@router.get("/heatmap")
def heatmap(bandwidth_km: Optional[float] = None, weight: str = "emp",
            db=Depends(get_db), user: AuthUser = Depends(require("view"))):
    t0 = time.monotonic()
    if weight not in ("emp", "trl"):
        raise HTTPException(422, "weight: emp | trl")
    res = gsvc.heatmap_kde(db, bandwidth_km, weight=weight)
    dt = round(time.monotonic() - t0, 3)
    res["elapsed_sec"] = dt
    # норматив ИВП-GEO-2: построение ≤ 3 с
    if dt > settings().heatmap_max_sec:
        get_bus().publish("geo.render_error", "MOD-GEO", f"Теплокарта: {dt} c > норматива", sev="alert")
    return res


@router.get("/measure")
def measure(org1: Optional[str] = None, org2: Optional[str] = None,
            lat1: Optional[float] = None, lon1: Optional[float] = None,
            lat2: Optional[float] = None, lon2: Optional[float] = None,
            db=Depends(get_db), user: AuthUser = Depends(require("view"))):
    if org1 and org2:
        try:
            return gsvc.measure_by_org(db, org1, org2)
        except KeyError as e:
            raise HTTPException(404, str(e))
    if None not in (lat1, lon1, lat2, lon2):
        return gsvc.measure(lat1, lon1, lat2, lon2)
    raise HTTPException(422, "Укажите пару org1/org2 либо координаты lat1/lon1/lat2/lon2")


@router.get("/export.kml")
def export_kml(type: Optional[str] = None, db=Depends(get_db),
               user: AuthUser = Depends(require("view"))):
    kml = gsvc.kml_export(db, type)
    audit.record("Экспорт геоданных (KML)", f"объектов: {kml.count('<Placemark>')}", "Успех",
                 user=user.login, role=user.role)
    return Response(content=kml, media_type="application/vnd.google-earth.kml+xml",
                    headers={"Content-Disposition": "attachment; filename=technocontour_geo.kml"})


@router.get("/white-spots")
def white_spots(db=Depends(get_db), user: AuthUser = Depends(require("view"))):
    """Регионы с числом объектов ниже медианы по ФО — «белые пятна» (ИВП-GEO-3)."""
    regions = {}
    for o in db.scalars(select(Organization)):
        regions.setdefault(o.region, []).append(o.id)
    counts = sorted(len(v) for v in regions.values())
    median = counts[len(counts) // 2] if counts else 0
    return {"median_per_region": median,
            "spots": [{"region": r, "count": len(ids), "ids": ids}
                      for r, ids in sorted(regions.items()) if len(ids) < median]}
