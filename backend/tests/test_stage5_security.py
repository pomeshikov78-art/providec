"""Этап 5: безопасность — блокировка перебора, logout/blacklist, OIDC, парольная политика, СКЗИ-абстракция."""


def test_password_policy(client):
    from app.kernel.iam import check_password_policy
    assert check_password_policy("короткий1") is not None
    assert check_password_policy("bezцифровokok") is not None
    assert check_password_policy("123456789012") is not None
    assert check_password_policy("НадежныйПароль2026") is None


def test_bruteforce_lockout(client):
    login = "guest"
    from app.kernel.iam import clear_failures
    clear_failures(login)
    for i in range(4):
        r = client.post("/api/v1/auth/login", json={"login": login, "password": "неверный"})
        assert r.status_code == 401
    r = client.post("/api/v1/auth/login", json={"login": login, "password": "неверный"})
    assert r.status_code == 423          # 5-я попытка → блокировка
    # даже верный пароль во время блокировки отклоняется
    r = client.post("/api/v1/auth/login", json={"login": login, "password": "tc-guest-2026"})
    assert r.status_code == 423
    clear_failures(login)                # откат для остальных тестов
    r = client.post("/api/v1/auth/login", json={"login": login, "password": "tc-guest-2026"})
    assert r.status_code == 200


def test_logout_blacklist(client, l5_headers):
    # вход отдельной сессией
    r = client.post("/api/v1/auth/login", json={"login": "regulator", "password": "tc-reg-2026"})
    tok = r.json()["access_token"]
    h = {"Authorization": "Bearer " + tok}
    assert client.get("/api/v1/auth/me", headers=h).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=h).status_code == 200
    r = client.get("/api/v1/auth/me", headers=h)
    assert r.status_code == 401          # токен отозван
    assert "отозван" in r.json()["detail"]


def test_oidc_disabled_in_autonomous(client):
    from app.config import Settings
    assert Settings(keycloak_url="").variant is not None
    r = client.get("/api/v1/auth/oidc/login")
    assert r.status_code == 501          # внешний IdP не сконфигурирован


def test_oidc_enabled_redirect(client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings(), "keycloak_url", "https://idp.contour.internal/auth")
    r = client.get("/api/v1/auth/oidc/login", follow_redirects=False)
    assert r.status_code == 307
    assert "protocol/openid-connect/auth" in r.headers["location"]
    assert "client_id=technocontour-spa" in r.headers["location"]
    monkeypatch.setattr(settings(), "keycloak_url", "")


def test_role_claim_mapping(client):
    from app.kernel.oidc import ROLE_CLAIM_MAP
    assert ROLE_CLAIM_MAP["tc-admin"] == "L7"
    assert ROLE_CLAIM_MAP["tc-enterprise"] == "L4"
    assert ROLE_CLAIM_MAP["tc-public"] == "L0"
    assert len(ROLE_CLAIM_MAP) == 8      # L0–L7


def test_crypto_provider_gost_extension_points(client):
    from app.kernel.security import crypto
    assert crypto.digest("Провидец".encode("utf-8")).hex()[:8]
    for op in ("sign", "verify", "encrypt", "decrypt"):
        try:
            if op == "sign":
                crypto.sign(b"x")
            elif op == "verify":
                crypto.verify(b"x", b"y")
            elif op == "encrypt":
                crypto.encrypt(b"x")
            else:
                crypto.decrypt(b"x")
            assert False, "ожидался NotImplemented до подключения СКЗИ"
        except NotImplementedError:
            pass


def test_jwt_contains_jti(client, l5_headers):
    from app.kernel.iam import decode_token
    tok = l5_headers["Authorization"].split(" ")[1]
    data = decode_token(tok)
    assert "jti" in data and data["typ"] == "access"
    assert data["role"] == "L5"


def test_lockout_events_and_audit(client, admin_headers):
    ev = client.get("/api/v1/core/events?type=iam.login_failed", headers=admin_headers).json()
    assert len(ev) >= 1
    a = client.get("/api/v1/core/audit", headers=admin_headers).json()
    assert any("Неуспешный вход" in x["action"] for x in a)
