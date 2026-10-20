"""Этап 1: ядро — реестр модулей, шина событий, IAM (JWT+MFA+RBAC/ABAC), WORM-аудит."""


def test_health_and_registry(client):
    r = client.get("/api/v1/core/health")
    assert r.status_code == 200
    h = r.json()
    assert h["status"] == "ok" and h["modules"]["total"] == 15
    r = client.get("/api/v1/core/modules")
    assert r.status_code == 401  # без токена доступ запрещен


def test_modules_list(client, admin_headers):
    r = client.get("/api/v1/core/modules", headers=admin_headers)
    assert r.status_code == 200
    mods = {m["code"]: m for m in r.json()}
    assert len(mods) == 15
    assert mods["MOD-PASS"]["required"] is True
    assert "MOD-COMP" in mods["MOD-PROF"]["deps"]


def test_login_and_me(client, admin_headers):
    r = client.get("/api/v1/auth/me", headers=admin_headers)
    assert r.status_code == 200 and r.json()["role"] == "L7"


def test_login_wrong_password(client):
    r = client.post("/api/v1/auth/login", json={"login": "admin", "password": "wrong"})
    assert r.status_code == 401


def test_mfa_required_for_l7(client):
    r = client.post("/api/v1/auth/login", json={"login": "admin", "password": "tc-admin-2026"})
    assert r.status_code == 200 and r.json().get("mfa_required") is True


def test_toggle_optional_module(client, admin_headers):
    r = client.patch("/api/v1/core/modules/MOD-AI", json={"enabled": False}, headers=admin_headers)
    assert r.status_code == 200 and r.json()["status"] == "disabled"
    r = client.patch("/api/v1/core/modules/MOD-AI", json={"enabled": True}, headers=admin_headers)
    assert r.status_code == 200 and r.json()["status"] == "active"


def test_required_module_protected(client, admin_headers):
    r = client.patch("/api/v1/core/modules/MOD-PASS", json={"enabled": False}, headers=admin_headers)
    assert r.status_code == 403  # обязательный модуль защищён политикой ядра (ТЗ п.4.7)


def test_cascade_degradation_and_deps(client, admin_headers):
    # MOD-KPI (опц.) ← зависимы MOD-REPORT (обяз., остаётся active) и MOD-STIM (опц. → degraded)
    r = client.patch("/api/v1/core/modules/MOD-KPI", json={"enabled": False}, headers=admin_headers)
    assert r.status_code == 200
    mods = {m["code"]: m["status"] for m in client.get("/api/v1/core/modules", headers=admin_headers).json()}
    assert mods["MOD-STIM"] == "degraded"
    assert mods["MOD-REPORT"] == "active"
    # включение MOD-STIM при неактивной зависимости → 409
    r = client.patch("/api/v1/core/modules/MOD-STIM", json={"enabled": True}, headers=admin_headers)
    assert r.status_code == 409
    # возвращаем MOD-KPI → деградация снимается
    r = client.patch("/api/v1/core/modules/MOD-KPI", json={"enabled": True}, headers=admin_headers)
    assert r.status_code == 200
    mods = {m["code"]: m["status"] for m in client.get("/api/v1/core/modules", headers=admin_headers).json()}
    assert mods["MOD-STIM"] == "active"


def test_rbac_l0_denied_and_events(client, l0_headers):
    r = client.patch("/api/v1/core/modules/MOD-AI", json={"enabled": False}, headers=l0_headers)
    assert r.status_code == 403
    ev = client.get("/api/v1/core/events?type=iam.access_denied", headers=l0_headers).json()
    assert len(ev) >= 1


def test_abac_l4_own_org(client, l4_headers):
    from app.kernel.iam import AuthUser, can
    own = AuthUser("sarmat", "L4", "E14")
    assert can(own, "org.write", "E14") is True
    assert can(own, "org.write", "E01") is False
    assert can(own, "admin") is False
    assert can(AuthUser("guest", "L0"), "view") is True


def test_events_journal_and_dlq(client, admin_headers):
    from app.kernel.bus import get_bus
    bus = get_bus()

    def bad_handler(ev):
        raise RuntimeError("тестовый сбой обработчика")

    bus.subscribe("test.dlq", bad_handler)
    bus.publish("test.dlq", "TEST", "проверка DLQ")
    r = client.get("/api/v1/core/events/dlq", headers=admin_headers)
    assert r.status_code == 200
    assert any(e["type"] == "test.dlq" for e in r.json())


def test_bus_priority_and_journal(client, admin_headers):
    from app.kernel.bus import get_bus
    bus = get_bus()
    got = []
    bus.subscribe("demo.*", lambda ev: got.append(ev["type"]))
    bus.publish("demo.one", "TEST", "1")
    bus.publish("demo.two", "TEST", "2", sev="alert")
    assert got == ["demo.one", "demo.two"]
    r = client.get("/api/v1/core/events?type=demo.two", headers=admin_headers)
    assert r.json()[0]["sev"] == "alert"


def test_audit_worm_chain(client, admin_headers):
    r = client.get("/api/v1/core/audit/verify", headers=admin_headers)
    assert r.status_code == 200
    v = r.json()
    assert v["enabled"] is True and v["ok"] is True and v["checked"] > 5


def test_rate_limiter_unit():
    from app.kernel.security import RateLimiter
    from app.config import settings
    rl = RateLimiter()
    limit = settings().rate_limit_per_minute
    assert all(rl.allow("u1") for _ in range(limit))
    assert rl.allow("u1") is False
    assert rl.allow("u2") is True


def test_security_headers(client):
    r = client.get("/api/v1/core/health")
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "DENY"
