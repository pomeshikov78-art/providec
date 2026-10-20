"""MOD-GEO: реальная геоаналитика (ТЗ п.5.6, Задача 6).

  * кластеризация — H3 (Uber hexagonal hierarchical, разрешение из конфигурации);
  * тепловая карта — ядерная оценка плотности KDE (гауссово ядро, полоса в км);
  * измерения — геодезическая линия Винсенти/Карни (geographiclib), точность 10 м;
  * экспорт — GeoJSON (RFC 7946) и KML 2.2;
  * картооснова — вариант А: OSM/Яндекс тайлы; вариант Б: локальный TileServer GL
    (конфигурация geo_tile_url_autonomous); сервер отдаёт URL тайлов в /geo/config.
В production (Postgres Pro) пространственные запросы исполняются PostGIS;
в dev-профиле (SQLite) — эквивалентная выборка с фильтрацией на стороне приложения.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional
from xml.sax.saxutils import escape as xesc

import h3
from geographiclib.geodesic import Geodesic
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Maturity, Organization

TYPE_COLORS = {"ent": "#3B82F6", "nio": "#10B981", "test": "#F59E0B"}
TYPE_NAMES = {"ent": "Предприятие", "nio": "НИИ/КБ", "test": "Испытательный центр"}


# ---------------------------------------------------------------- GeoJSON
def objects_geojson(db: Session, type_: Optional[str] = None, region: Optional[str] = None,
                    q: Optional[str] = None) -> dict:
    rows = list(db.scalars(select(Organization).order_by(Organization.id)))
    if type_:
        rows = [o for o in rows if o.org_type == type_]
    if region:
        rows = [o for o in rows if o.region == region]
    if q:
        ql = q.lower()
        rows = [o for o in rows if ql in o.name.lower() or ql in o.city.lower()]
    feats = []
    for o in rows:
        m = db.get(Maturity, o.id)
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(o.lon, 4), round(o.lat, 4)]},
            "properties": {"id": o.id, "name": o.name, "short": o.short_name, "type": o.org_type,
                           "city": o.city, "region": o.region, "emp": o.employees,
                           "trl": m.trl if m else None, "mrl": m.mrl if m else None,
                           "irl": m.irl if m else None, "status": o.status, "stage": o.lc_stage,
                           "risk_idx": o.risk_idx, "invest": o.invest},
        })
    return {"type": "FeatureCollection", "count": len(feats), "features": feats}


# ---------------------------------------------------------------- H3-кластеризация
def clusters_h3(db: Session, resolution: Optional[int] = None) -> dict:
    """Кластеризация объектов по гексагональной сетке H3 (ИВП-GEO-3)."""
    res = resolution or settings().geo_h3_resolution
    groups: Dict[str, List[Organization]] = {}
    for o in db.scalars(select(Organization)):
        cell = h3.latlng_to_cell(o.lat, o.lon, res)
        groups.setdefault(cell, []).append(o)
    clusters = []
    for cell, orgs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        lat, lon = h3.cell_to_latlng(cell)
        mats = [db.get(Maturity, o.id) for o in orgs]
        trls = [m.trl for m in mats if m]
        clusters.append({
            "h3": cell, "resolution": res, "lat": round(lat, 4), "lon": round(lon, 4),
            "count": len(orgs), "ids": [o.id for o in orgs],
            "regions": sorted({o.region for o in orgs}),
            "avg_trl": round(sum(trls) / len(trls), 1) if trls else None,
            "total_emp": sum(o.employees for o in orgs),
        })
    return {"resolution": res, "clusters": len(clusters), "objects": sum(c["count"] for c in clusters),
            "items": clusters}


# ---------------------------------------------------------------- KDE-теплокарта
def heatmap_kde(db: Session, bandwidth_km: Optional[float] = None, step_deg: float = 1.0,
                weight: str = "emp") -> dict:
    """Тепловая карта ядерной оценки плотности (ИВП-GEO-2).

    Узлы регулярной сетки получают интенсивность Σ w_i·exp(−d²/2h²);
    результат — точки [lat, lon, intensity 0..1] для слоёв Leaflet.heat / SVG-радара.
    """
    h_km = bandwidth_km or settings().geo_kde_bandwidth_km
    orgs = [(o.lat, o.lon,
             float(o.employees if weight == "emp" else (db.get(Maturity, o.id).trl if db.get(Maturity, o.id) else 1)))
            for o in db.scalars(select(Organization))]
    lats = [x[0] for x in orgs]
    lons = [x[1] for x in orgs]
    lat0, lat1 = math.floor(min(lats) - 2), math.ceil(max(lats) + 2)
    lon0, lon1 = math.floor(min(lons) - 4), math.ceil(max(lons) + 4)
    pts: List[List[float]] = []
    max_dens = 0.0
    grid = []
    lat = lat0
    while lat <= lat1:
        lon = lon0
        while lon <= lon1:
            dens = 0.0
            for olat, olon, w in orgs:
                d = math.hypot((lat - olat) * 111.0, (lon - olon) * 111.0 * math.cos(math.radians(lat)))
                if d <= 3 * h_km:
                    dens += w * math.exp(-(d * d) / (2 * h_km * h_km))
            if dens > 0:
                grid.append([round(lat, 2), round(lon, 2), dens])
                max_dens = max(max_dens, dens)
            lon += step_deg
        lat += step_deg
    for g in grid:
        pts.append([g[0], g[1], round(g[2] / max_dens, 4) if max_dens else 0.0])
    pts.sort(key=lambda p: -p[2])
    return {"bandwidth_km": h_km, "weight": weight, "nodes": len(pts), "max_density": round(max_dens, 2),
            "points": pts}


# ---------------------------------------------------------------- измерения (геодезия)
def measure(lat1: float, lon1: float, lat2: float, lon2: float) -> dict:
    """Геодезическое расстояние и азимут (Karney, точность ~10 м) — ИВП-GEO-4."""
    g = Geodesic.WGS84.Inverse(lat1, lon1, lat2, lon2)
    return {"from": [lat1, lon1], "to": [lat2, lon2],
            "distance_km": round(g["s12"] / 1000.0, 3),
            "azimuth_fwd": round(g["azi1"] % 360.0, 2), "azimuth_back": round(g["azi2"] % 360.0, 2)}


def measure_by_org(db: Session, org1: str, org2: str) -> dict:
    a = db.get(Organization, org1)
    b = db.get(Organization, org2)
    if a is None or b is None:
        raise KeyError(f"Организация не найдена: {org1 if a is None else org2}")
    res = measure(a.lat, a.lon, b.lat, b.lon)
    res["from_org"] = f"{a.id} {a.short_name}"
    res["to_org"] = f"{b.id} {b.short_name}"
    return res


# ---------------------------------------------------------------- экспорт KML
def kml_export(db: Session, type_: Optional[str] = None) -> str:
    rows = list(db.scalars(select(Organization).order_by(Organization.id)))
    if type_:
        rows = [o for o in rows if o.org_type == type_]
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
             '<name>АИС «Техноконтур» — реестр организаций</name>']
    for t, color in TYPE_COLORS.items():   # стили по типам (abgr для KML)
        bgr = color[5:7] + color[3:5] + color[1:3]
        parts.append(f'<Style id="{t}"><IconStyle><color>ff{bgr}</color>'
                     f'<Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon>'
                     f'</IconStyle></Style>')
    for o in rows:
        m = db.get(Maturity, o.id)
        desc = (f"Тип: {TYPE_NAMES[o.org_type]}<br/>Город: {o.city} ({o.region})<br/>"
                f"Сотрудников: {o.employees}<br/>TRL/MRL/IRL: {m.trl if m else '?'}/"
                f"{m.mrl if m else '?'}/{m.irl if m else '?'}<br/>Статус паспорта: {o.status}")
        parts.append(f'<Placemark><name>{xesc(o.short_name)} ({o.id})</name>'
                     f'<description>{xesc(desc)}</description><styleUrl>#{o.org_type}</styleUrl>'
                     f'<Point><coordinates>{o.lon},{o.lat},0</coordinates></Point></Placemark>')
    parts.append("</Document></kml>")
    return "".join(parts)


def geo_config() -> dict:
    s = settings()
    return {"variant": s.variant, "tile_url": s.tile_url,
            "attribution": "© OpenStreetMap contributors" if "openstreetmap" in s.tile_url else "Локальный тайл-сервер (контур)",
            "h3_resolution": s.geo_h3_resolution, "kde_bandwidth_km": s.geo_kde_bandwidth_km,
            "engine": "Leaflet 1.9 + H3 v4 + KDE (сервер) / SVG-схема (офлайн-фолбэк)"}
