"""Этап 2: реальная СУБД — seed из прототипа, паспорта (92 поля), версии, качество, профили, bootstrap."""


def test_seed_loaded(client, admin_headers):
    r = client.get("/api/v1/orgs?size=1", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["total"] == 100        # 100 организаций из прототипа v8


def test_orgs_filters(client, admin_headers):
    r = client.get("/api/v1/orgs?type=test", headers=admin_headers).json()
    assert r["total"] >= 4 and all(o["type"] == "test" for o in r["items"])
    r = client.get("/api/v1/orgs?q=Сармат", headers=admin_headers).json()
    assert r["total"] == 1 and r["items"][0]["id"] == "E14"
    r = client.get("/api/v1/orgs?region=Приволжский ФО", headers=admin_headers).json()
    assert r["total"] > 5


def test_passport_92_fields(client, admin_headers):
    p = client.get("/api/v1/orgs/E01/passport", headers=admin_headers).json()
    total = sum(len(s["fields"]) for s in p["sections"])
    assert len(p["sections"]) == 12
    assert total == 92
    s1 = p["sections"][0]
    assert s1["threshold"] == 95                     # порог Прил. 2.14
    assert any(f["source"] == "ЕГРЮЛ" for f in s1["fields"])
    filled = sum(1 for s in p["sections"] for f in s["fields"] if f["filled"])
    assert filled > 60                               # E01 — лидер: высокая полнота
    assert p["fill_total"] >= 95


def test_passport_save_creates_version(client, admin_headers):
    p = client.get("/api/v1/orgs/E02/passport", headers=admin_headers).json()
    # найдём незаполненное поле раздела 8 (испытательный потенциал)
    target = None
    for s in p["sections"]:
        for f in s["fields"]:
            if not f["filled"]:
                target = f
                break
        if target:
            break
    assert target is not None, "ожидались незаполненные поля у E02"
    r = client.put("/api/v1/orgs/E02/passport", json={"updates": {str(target["id"]): "Значение из теста Этапа 2"}},
                   headers=admin_headers)
    assert r.status_code == 200
    res = r.json()
    assert res["ver_n"] >= 1 and res["crc32"].startswith("0x")
    vers = client.get("/api/v1/orgs/E02/passport/versions", headers=admin_headers).json()
    assert vers[0]["ver_n"] == res["ver_n"]
    assert target["name"] in vers[0]["changes"]
    # событие в шине
    ev = client.get("/api/v1/core/events?type=passport.updated", headers=admin_headers).json()
    assert any("E02" in e["payload"] for e in ev)
    # двойник пересобран подпиской на profile.updated
    tw = client.get("/api/v1/twins/E02", headers=admin_headers).json()
    assert tw["crc32"].startswith("0x")


def test_passport_quality(client, admin_headers):
    r = client.post("/api/v1/orgs/E01/passport/quality", headers=admin_headers).json()
    assert r["ok"] is True and r["fill_total"] >= 95
    r = client.post("/api/v1/orgs/E11/passport/quality", headers=admin_headers).json()
    assert r["ok"] is False
    assert any("ИНН" in i for i in r["issues"])      # E11 — намеренное расхождение (арбитраж)


def test_verify_workflow(client, admin_headers):
    # E15 — черновик: отправка на верификацию → верификация экспертом
    r = client.post("/api/v1/orgs/E15/verify?submit=true", headers=admin_headers)
    assert r.status_code == 200
    org = client.get("/api/v1/orgs/E15", headers=admin_headers).json()
    assert org["status"] == "pending"
    r = client.post("/api/v1/orgs/E15/verify", headers=admin_headers)
    assert r.status_code == 200
    org = client.get("/api/v1/orgs/E15", headers=admin_headers).json()
    assert org["status"] == "verified"
    ev = client.get("/api/v1/core/events?type=passport.verified", headers=admin_headers).json()
    assert any("E15" in e["payload"] for e in ev)


def test_profile_and_benchmarks(client, admin_headers):
    p = client.get("/api/v1/profiles/E01", headers=admin_headers).json()
    assert len(p["radar"]) == 7 and p["trl"] == 8
    assert p["index_i"] is not None and p["status_level"] in ("Лидер", "Высокий", "Средний", "Начальный")
    b = client.get("/api/v1/profiles/benchmarks", headers=admin_headers).json()
    assert b["orgs_total"] == 100 and len(b["dims"]) == 7
    assert "ent" in b["by_type"]


def test_maturity_index_formula(client):
    """Эталон ТЗ (Прил. 3.5): TRL=6, MRL=5, IRL=4 → 55.3."""
    from app.services.maturity import maturity_index
    assert maturity_index(6, 5, 4) == 55.3


def test_validators(client):
    from app.services.validators import inn_fix, inn_valid, ogrn_valid
    assert inn_valid(inn_fix("770123456")) is True
    assert inn_valid("0000000001") is False
    assert ogrn_valid("1027700123456") is False      # случайное число — как правило невалидно
    fixed = inn_fix("770123456")
    assert len(fixed) == 10 and inn_valid(fixed)


def test_twin_rebuild(client, admin_headers):
    r = client.post("/api/v1/twins/E14/rebuild", headers=admin_headers)
    assert r.status_code == 200
    t = r.json()
    assert t["crc32"].startswith("0x") and t["index_i"] > 0


def test_bootstrap(client, admin_headers):
    b = client.get("/api/v1/bootstrap", headers=admin_headers).json()
    assert len(b["orgs"]) == 100 and len(b["projects"]) == 12 and len(b["risks"]) == 12
    assert len(b["modules"]) == 15
    assert b["geo"]["tile_url"].startswith("http")
    assert len(b["integrations"]) >= 28


def test_abac_l4_sees_only_own_org(client, l4_headers):
    r = client.get("/api/v1/orgs", headers=l4_headers).json()
    assert r["total"] == 100            # total — агрегат (публичный)
    assert all(o["id"] == "E14" for o in r["items"])   # но список — только своё предприятие
    r = client.put("/api/v1/orgs/E01/passport", json={"updates": {}}, headers=l4_headers)
    assert r.status_code == 403         # чужой паспорт — запрет ABAC
    r = client.put("/api/v1/orgs/E14/passport", json={"updates": {}}, headers=l4_headers)
    assert r.status_code == 200         # свой — разрешено
