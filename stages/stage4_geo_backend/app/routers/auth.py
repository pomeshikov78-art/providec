"""Роутер IAM: вход (JWT), refresh, MFA (TOTP), профиль сеанса."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
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
    with session_scope() as db:
        user = db.scalars(select(User).where(User.login == req.login)).first()
        if user is None or not user.active or not verify_password(req.password, user.password_hash):
            get_bus().publish("iam.login_failed", "CORE:IAM", f"Неуспешный вход: {req.login}", sev="warn")
            audit.record("Неуспешный вход в систему", req.login, "Отказ", user=req.login, role="—")
            raise HTTPException(401, "Неверные учетные данные")
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
