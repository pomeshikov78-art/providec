"""Общие фикстуры тестов: изолированная БД (SQLite-файл), TestClient, токены ролей."""
import os
import sys
import tempfile
import uuid

# --- окружение ДО импорта приложения ---
_tmpdb = os.path.join(tempfile.gettempdir(), f"tc_test_{uuid.uuid4().hex[:8]}.db")
os.environ["TC_DATABASE_URL"] = f"sqlite:///{_tmpdb}"
os.environ["TC_BUS_BACKEND"] = "memory"
os.environ["TC_JWT_SECRET"] = "test_secret_0123456789abcdef_0123456789abcdef"
os.environ["TC_RATE_LIMIT_PER_MINUTE"] = "100000"
os.environ["TC_MFA_REQUIRED_ROLES"] = "L7"
os.environ["TC_CONNECTORS_MODE"] = "sandbox"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def client():
    from app.main import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c


def _login(client, login, password, mfa=None):
    body = {"login": login, "password": password}
    if mfa:
        body["mfa_code"] = mfa
    r = client.post("/api/v1/auth/login", json=body)
    return r


@pytest.fixture(scope="session")
def admin_headers(client):
    """L7 с MFA (TOTP): секрет берется из БД seed."""
    import pyotp
    from app.db import session_scope
    from app.models import User
    from sqlalchemy import select
    with session_scope() as db:
        u = db.scalars(select(User).where(User.login == "admin")).first()
        secret = u.totp_secret
    code = pyotp.TOTP(secret).now()
    r = _login(client, "admin", "tc-admin-2026", mfa=code)
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


@pytest.fixture(scope="session")
def l5_headers(client):
    r = _login(client, "analyst", "tc-analyst-2026")
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


@pytest.fixture(scope="session")
def l4_headers(client):
    r = _login(client, "sarmat", "tc-org-2026")
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


@pytest.fixture(scope="session")
def l0_headers(client):
    r = _login(client, "guest", "tc-guest-2026")
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}
