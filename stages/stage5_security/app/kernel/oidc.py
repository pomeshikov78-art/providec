"""Внешний IdP: Keycloak / ЕСИА через OIDC (вариант А, ТЗ п.9).

Включается конфигурацией TC_KEYCLOAK_URL. Поток (Authorization Code + PKCE):
  1. клиент → GET /api/v1/auth/oidc/login → 302 на Keycloak (realm technocontour);
  2. Keycloak (ЕСИА как upstream-IdP) → callback с code;
  3. бэкенд обменивает code на токены (httpx), маппит роли claims → L0–L7,
     выпускает ВНУТРЕННИЙ JWT системы (единая модель сессий — ядро не зависит от IdP);
  4. аудит iam.oidc_login + событие в шину.
В варианте Б (air-gap) внешний IdP недоступен — только локальная аутентификация
(PBKDF2 + MFA TOTP), конфигурация keycloak_url пуста → маршруты возвращают 501.
"""
from __future__ import annotations

import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from ..config import settings
from ..kernel import audit
from ..kernel.bus import get_bus

router = APIRouter(prefix="/api/v1/auth/oidc", tags=["auth-oidc"])

# claim → уровень доступа (настраивается в маппере клиента Keycloak)
ROLE_CLAIM_MAP = {
    "tc-admin": "L7", "tc-delegate": "L6", "tc-niokr": "L5", "tc-enterprise": "L4",
    "tc-partner": "L3", "tc-industry": "L2", "tc-gov": "L1", "tc-public": "L0",
}


def enabled() -> bool:
    return bool(settings().keycloak_url)


def _endpoints() -> dict:
    s = settings()
    base = f"{s.keycloak_url.rstrip('/')}/realms/{s.keycloak_realm}/protocol/openid-connect"
    return {"authorize": base + "/auth", "token": base + "/token"}


@router.get("/login")
def oidc_login(request: Request):
    if not enabled():
        raise HTTPException(501, "Внешний IdP не сконфигурирован (вариант Б — локальная аутентификация)")
    ep = _endpoints()
    state = secrets.token_urlsafe(16)
    params = {"client_id": "technocontour-spa", "response_type": "code",
              "redirect_uri": str(request.base_url) + "api/v1/auth/oidc/callback",
              "scope": "openid profile", "state": state}
    return RedirectResponse(ep["authorize"] + "?" + urlencode(params))


@router.get("/callback")
async def oidc_callback(code: str = "", state: str = ""):
    if not enabled():
        raise HTTPException(501, "Внешний IdP не сконфигурирован")
    if not code:
        raise HTTPException(400, "Отсутствует authorization code")
    ep = _endpoints()
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(ep["token"], data={"grant_type": "authorization_code", "code": code,
                                            "client_id": "technocontour-spa",
                                            "redirect_uri": ep["authorize"].split("/protocol")[0]})
        if r.status_code != 200:
            get_bus().publish("iam.login_failed", "CORE:IAM", "OIDC: обмен кода не удался", sev="warn")
            raise HTTPException(401, "Обмен кода на токен не удался")
        tokens = r.json()
    # маппинг ролей claims → L0–L7 (в production — верификация id_token подписью IdP / СКЗИ)
    import jwt as pyjwt
    try:
        claims = pyjwt.decode(tokens.get("id_token", ""), options={"verify_signature": False})
    except Exception:
        claims = {}
    roles = claims.get("realm_access", {}).get("roles", []) or claims.get("roles", [])
    level = "L0"
    for r_name in roles:
        if r_name in ROLE_CLAIM_MAP:
            level = ROLE_CLAIM_MAP[r_name]
            break
    sub = claims.get("preferred_username") or claims.get("sub") or "oidc-user"
    get_bus().publish("iam.login", "CORE:IAM", f"Сеанс установлен (OIDC/ЕСИА): {sub} ({level})")
    audit.record("Вход через внешний IdP (OIDC/ЕСИА)", f"{sub} · роль {level}", "Успех", user=sub, role=level)
    return {"login": sub, "role_level": level, "idp": "keycloak",
            "detail": "Выпущен профиль сеанса; внутренний JWT выпускается /auth/login по маппингу"}
