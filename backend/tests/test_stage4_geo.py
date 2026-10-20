"""Этап 4: MOD-GEO — H3-кластеризация, KDE-теплокарта, геодезия, GeoJSON/KML."""
import json
import time
import xml.etree.ElementTree as ET


def test_geojson(client, admin_headers):
    t0 = time.monotonic()
    fc = client.get("/api/v1/geo/objects.geojson", headers=admin_headers).json()
    assert fc["type"] == "FeatureCollection" and fc["count"] == 100
    f0 = fc["features"][0]
    assert f0["geometry"]["type"] == "Point" and len(f0["geometry"]["coordinates"]) == 2
    assert time.monotonic() - t0 <= 2.0          # норматив ИВП-GEO-1


def test_geojson_filter(client, admin_headers):
    fc = client.get("/api/v1/geo/objects.geojson?type=test", headers=admin_headers).json()
    assert fc["count"] >= 4
    assert all(f["properties"]["type"] == "test" for f in fc["features"])


def test_h3_clusters(client, admin_headers):
    d = client.get("/api/v1/geo/clusters", headers=admin_headers).json()
    assert d["objects"] == 100                    # conservation: все объекты по кластерам
    assert sum(c["count"] for c in d["items"]) == 100
    assert all(len(c["h3"]) == 15 for c in d["items"])   # H3 res5 — 15 символов
    assert d["items"][0]["count"] >= d["items"][-1]["count"]
    # более высокое разрешение → больше кластеров
    d6 = client.get("/api/v1/geo/clusters?resolution=6", headers=admin_headers).json()
    assert d6["clusters"] >= d["clusters"]


def test_kde_heatmap(client, admin_headers):
    t0 = time.monotonic()
    d = client.get("/api/v1/geo/heatmap", headers=admin_headers).json()
    assert time.monotonic() - t0 <= 3.0           # норматив ИВП-GEO-2
    assert d["nodes"] > 50 and d["max_density"] > 0
    top = d["points"][0]
    assert len(top) == 3 and 0 <= top[2] <= 1.0
    # максимум плотности — в районе Москвы (наибольшая концентрация объектов)
    assert 50 < top[0] < 62 and 30 < top[1] < 50
    d2 = client.get("/api/v1/geo/heatmap?weight=trl&bandwidth_km=200", headers=admin_headers).json()
    assert d2["weight"] == "trl" and d2["bandwidth_km"] == 200


def test_measure_geodesic(client, admin_headers):
    # Москва (55.75,37.62) → СПб (59.94,30.31): ~634 км по геодезии
    d = client.get("/api/v1/geo/measure?lat1=55.75&lon1=37.62&lat2=59.94&lon2=30.31",
                   headers=admin_headers).json()
    assert 630 < d["distance_km"] < 640
    assert 300 < d["azimuth_fwd"] < 330           # на северо-запад
    # по организациям
    d2 = client.get("/api/v1/geo/measure?org1=E01&org2=E14", headers=admin_headers).json()
    assert d2["distance_km"] > 0 and "from_org" in d2
    r = client.get("/api/v1/geo/measure?org1=E01&org2=NOPE", headers=admin_headers)
    assert r.status_code == 404


def test_kml_export(client, admin_headers):
    r = client.get("/api/v1/geo/export.kml", headers=admin_headers)
    assert r.status_code == 200
    assert "kml" in r.headers["content-type"]
    root = ET.fromstring(r.content)               # валидный XML
    ns = {"k": "http://www.opengis.net/kml/2.2"}
    placemarks = root.findall(".//k:Placemark", ns)
    assert len(placemarks) == 100


def test_geo_config_variants(client, admin_headers):
    d = client.get("/api/v1/geo/config", headers=admin_headers).json()
    assert d["variant"] == "network"
    assert "openstreetmap" in d["tile_url"]
    from app.config import Settings
    b = Settings(variant="autonomous")
    assert "contour.internal" in b.tile_url       # вариант Б — локальный тайл-сервер


def test_white_spots(client, admin_headers):
    d = client.get("/api/v1/geo/white-spots", headers=admin_headers).json()
    assert d["median_per_region"] > 0
    assert all(s["count"] < d["median_per_region"] for s in d["spots"])
