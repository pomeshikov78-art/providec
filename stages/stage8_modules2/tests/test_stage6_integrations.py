"""Этап 6: внешние интеграции — коннекторы (retry/circuit breaker/идемпотентность), обогащение ЕГРЮЛ, импорт АССПР."""


def test_connectors_status(client, admin_headers):
    d = client.get("/api/v1/int/connectors", headers=admin_headers).json()
    assert d["mode"] == "sandbox"
    codes = {c["code"] for c in d["connectors"]}
    assert {"EGRUL", "GISP", "ROSPATENT", "ESIA", "ASSPR"} <= codes


def test_egryul_enrich(client, admin_headers):
    r = client.post("/api/v1/int/egryul/enrich/E14", headers=admin_headers)
    assert r.status_code == 200
    d = r.json()
    assert d["egryul"]["source"] == "ЕГРЮЛ (стенд)"
    assert "Сармат" in d["egryul"]["full_name"]
    assert len(d["applied_fields"]) >= 2
    assert d["version"] is not None        # обогащение создало версию паспорта
    ev = client.get("/api/v1/core/events?type=int.egrul_enriched", headers=admin_headers).json()
    assert any("E14" in e["payload"] for e in ev)


def test_egryul_unknown_inn(client, admin_headers):
    r = client.post("/api/v1/int/egryul/enrich/E01", headers=admin_headers)
    # ИНН E01 присутствует в стенде → успех; проверяем именно отказ при несуществующей орг.
    assert r.status_code in (200, 502)
    r = client.post("/api/v1/int/egryul/enrich/NOPE", headers=admin_headers)
    assert r.status_code == 404


def test_gisp_and_rospatent(client, admin_headers):
    g = client.get("/api/v1/int/gisp/E14", headers=admin_headers).json()
    assert g["org_id"] == "E14" and len(g["products"]) >= 3
    p = client.get("/api/v1/int/rospatent/E01", headers=admin_headers).json()
    assert len(p["patents"]) >= 2 and p["patents"][0]["number"].startswith("RU ")


def test_idempotency(client, admin_headers):
    conn_pkg = {"id": "ASSPR-IDEM-1", "org_name": "Сармат-Электроника", "target_org_id": "E14",
                "fields": {"Полное наименование": "АО «Сармат-Электроника»"}}
    r1 = client.post("/api/v1/int/asspr/import", json={"package": conn_pkg}, headers=admin_headers)
    assert r1.status_code == 200 and r1.json()["applied"] is True
    r2 = client.post("/api/v1/int/asspr/import", json={"package": conn_pkg}, headers=admin_headers)
    assert r2.json()["applied"] is False          # повтор отклонён (идемпотентность)
    assert "уже импортирован" in r2.json()["reason"]


def test_asspr_import_updates_org(client, admin_headers):
    pkg = {"id": "ASSPR-T6-1", "org_name": "АО «Сармат-Электроника»", "target_org_id": "E14",
           "comps": {"prod": 5}, "trl": 7, "mrl": 7, "irl": 6,
           "fields": {"Полное наименование": "Акционерное общество «Сармат-Электроника» (ред. АССПР)"}}
    r = client.post("/api/v1/int/asspr/import", json={"package": pkg}, headers=admin_headers).json()
    assert r["applied"] and r["fields_updated"] >= 1
    prof = client.get("/api/v1/profiles/E14", headers=admin_headers).json()
    assert prof["trl"] == 7 and prof["competencies"]["prod"] == 5


def test_asspr_new_org(client, admin_headers):
    pkg = {"id": "ASSPR-NEW-1",
           "newOrg": {"name": "ООО «Фотоника-Плюс»", "short": "Фотоника-Плюс", "type": "ent",
                      "city": "Казань", "reg": "Приволжский ФО", "lat": 55.79, "lon": 49.11,
                      "inn": "1655000000", "year": 2019, "emp": 120, "rev": 0.4},
           "fields": {"Полное наименование": "ООО «Фотоника-Плюс»"}}
    r = client.post("/api/v1/int/asspr/import", json={"package": pkg}, headers=admin_headers).json()
    assert r["applied"] and r["org_id"].startswith("E1")
    ev = client.get("/api/v1/core/events?type=pass.new_registered", headers=admin_headers).json()
    assert any("Фотоника" in e["payload"] for e in ev)


def test_asspr_rbac(client, l5_headers):
    r = client.post("/api/v1/int/asspr/import", json={"package": {"org_name": "X"}}, headers=l5_headers)
    assert r.status_code == 403            # импорт — операция L6/L7 (admin)


def test_retry_and_circuit_breaker_unit():
    from app.connectors.base import BaseConnector

    class Flaky(BaseConnector):
        code, name = "FLAKY", "Тестовый"

    c = Flaky()
    calls = {"n": 0}

    def fail_always():
        calls["n"] += 1
        raise IOError("канал недоступен")

    import pytest
    with pytest.raises(RuntimeError):
        c._with_retry("тест", fail_always)
    assert calls["n"] == 3                       # 3 попытки
    assert not c.circuit.allow()                 # breaker открыт
    import pytest as pt
    with pt.raises(RuntimeError):
        c._with_retry("тест2", fail_always)      # отклонён breaker'ом без вызова
    assert calls["n"] == 3

    ok = Flaky()
    assert ok._with_retry("успех", lambda: {"ok": 1}) == {"ok": 1}
    assert ok.circuit.allow()
    # идемпотентность
    assert ok._with_retry("успех", lambda: {"ok": 2}, idem_key="k1") == {"ok": 2}
    assert ok._with_retry("успех", lambda: {"ok": 3}, idem_key="k1") == {"ok": 2}
