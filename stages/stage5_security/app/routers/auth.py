"""Роутер IAM: вход (JWT), refresh, MFA (TOTP), профиль сеанса."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import select

from ..db import session_scope
from ..kernel import audit
from ..kernel.bus import get_bus
from ..kernel.iam import (AuthUser, ROLES, create_tokens, decode_token, get_current_user,
                          mfa_required, verify_password, verify_totp)
from ..models import User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    login: str
    password: str
    mfa_code: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/login")
def login(req: LoginRequest):
    from ..kernel.iam import clear_failures, is_locked, register_failure
    if is_locked(req.login):
        get_bus().publish("iam.login_failed", "CORE:IAM",
                          f"Вход отклонен: учетная запись {req.login} заблокирована (подбор пароля)", sev="warn")
        raise HTTPException(423, "Учетная запись временно заблокирована (5 неудачных попыток, 15 минут)")
    with session_scope() as db:
        user = db.scalars(select(User).where(User.login == req.login)).first()
        if user is None or not user.active or not verify_password(req.password, user.password_hash):
            locked = register_failure(req.login)
            get_bus().publish("iam.login_failed", "CORE:IAM",
                              f"Неуспешный вход: {req.login}" + (" — УЗ заблокирована" if locked else ""),
                              sev="warn" if locked else "info")
            audit.record("Неуспешный вход в систему", req.login +
                         (" · блокировка УЗ (защита от перебора)" if locked else ""),
                         "Отказ", user=req.login, role="—")
            if locked:
                raise HTTPException(423, "Превышено число попыток: учетная запись заблокирована на 15 минут")
            raise HTTPException(401, "Неверные учетные данные")
        clear_failures(req.login)
        if mfa_required(user.role_level):
            if not req.mfa_code:
                return {"mfa_required": True, "detail": f"Для роли {user.role_level} требуется MFA (TOTP)"}
            if not user.totp_secret or not verify_totp(user.totp_secret, req.mfa_code):
                get_bus().publish("iam.login_failed", "CORE:IAM", f"MFA отклонен: {req.login}", sev="warn")
                raise HTTPException(401, "Неверный код MFA")
        tokens = create_tokens(user)
        fio, org = user.fio, user.org_id
        role = user.role_level
    get_bus().publish("iam.login", "CORE:IAM", f"Сеанс установлен: {req.login} ({role})")
    audit.record("Вход в систему (аутентификация)", f"роль {role}" + (f" · org {org}" if org else ""),
                 "Успех", user=req.login, role=role)
    return {**tokens, "fio": fio, "org_id": org, "role_name": ROLES.get(role, "")}


@router.post("/logout")
def logout(user: AuthUser = Depends(get_current_user),
           credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))):
    """Завершение сеанса: jti access-токена отзывается (blacklist до истечения exp)."""
    from ..kernel.iam import revoke_token
    if credentials:
        revoke_token(credentials.credentials)
    get_bus().publish("iam.logout", "CORE:IAM", f"Сеанс завершен: {user.login}")
    audit.record("Выход из системы", user.login, "Успех", user=user.login, role=user.role)
    return {"ok": True}


@router.post("/refresh")
def refresh(req: RefreshRequest):
    data = decode_token(req.refresh_token, typ="refresh")
    with session_scope() as db:
        user = db.scalars(select(User).where(User.login == data["sub"])).first()
        if user is None or not user.active:
            raise HTTPException(401, "Пользователь не найден/заблокирован")
        return create_tokens(user)


@router.get("/me")
def me(user: AuthUser = Depends(get_current_user)):
    return {"login": user.login, "role": user.role, "role_name": ROLES.get(user.role, ""),
            "org_id": user.org_id}


@router.get("/roles")
def roles():
    """Справочник уровней доступа L0–L7 (ТЗ п.3.2) — публичный."""
    return [{"id": k, "name": v} for k, v in ROLES.items()]
