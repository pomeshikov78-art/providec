"""IAM: аутентификация и авторизация RBAC + ABAC (ТЗ п.3.2, п.9; Задача 5.6).

Состав:
  * пароли: PBKDF2-HMAC-SHA256 (100k итераций, соль) — в prod варианта Б заменяется
    на СКЗИ-профиль через kernel/crypto.py (ГОСТ Р 34.12-2015);
  * сессии: JWT access/refresh (в prod варианта А — интеграция с ЕСИА через Keycloak OIDC);
  * MFA: TOTP (RFC 6238) для ролей из settings().mfa_required_roles;
  * авторизация: PolicyEngine читает iam_policies (RBAC) + условия JSON (ABAC:
    org_eq_subject — «L4 видит только своё предприятие»), дефолт — deny;
  * отказ: событие iam.access_denied в шину + запись в аудит (как в прототипе v8).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from ..config import settings
from ..db import session_scope
from ..models import IamPolicy, User

ROLES = {
    "L0": "Внешний пользователь", "L1": "Государственные органы", "L2": "Отраслевые органы",
    "L3": "Партнеры/инвесторы", "L4": "Предприятие (собственный профиль)", "L5": "НИОКР/испытания",
    "L6": "Передача прав (делегирование)", "L7": "Администратор системы",
}
FULL_ROLES = {"L1", "L2", "L5", "L6", "L7"}   # расширенные роли (как в прототипе)

_pbearer = HTTPBearer(auto_error=False)

# ---------------------------------------------------------------- пароли
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return "pbkdf2$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        _, b64salt, b64dk = stored.split("$")
        salt = base64.b64decode(b64salt)
        dk = base64.b64decode(b64dk)
    except Exception:
        return False
    cand = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return hmac.compare_digest(cand, dk)

# ---------------------------------------------------------------- JWT
def create_tokens(user: User) -> dict:
    s = settings()
    now = int(time.time())
    access = jwt.encode({"sub": user.login, "role": user.role_level, "org_id": user.org_id,
                         "typ": "access", "iat": now, "exp": now + s.jwt_ttl_minutes * 60},
                        s.jwt_secret, algorithm=s.jwt_algorithm)
    refresh = jwt.encode({"sub": user.login, "typ": "refresh", "iat": now,
                          "exp": now + s.jwt_refresh_ttl_hours * 3600},
                         s.jwt_secret, algorithm=s.jwt_algorithm)
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer",
            "role_level": user.role_level}


def decode_token(token: str, typ: str = "access") -> dict:
    s = settings()
    try:
        data = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Токен истек")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Недействительный токен")
    if data.get("typ") != typ:
        raise HTTPException(401, f"Ожидался токен типа {typ}")
    return data

# ---------------------------------------------------------------- MFA (TOTP)
def mfa_required(role: str) -> bool:
    return role in {r.strip() for r in settings().mfa_required_roles.split(",") if r.strip()}


def generate_totp_secret() -> str:
    import pyotp
    return pyotp.random_base32()


def verify_totp(secret: str, code: str) -> bool:
    import pyotp
    return pyotp.TOTP(secret).verify(code, valid_window=1)

# ---------------------------------------------------------------- субъект
@dataclass
class AuthUser:
    login: str
    role: str
    org_id: Optional[str] = None

    @property
    def display(self) -> str:
        return f"{self.login} ({self.role} · {ROLES.get(self.role, '?')})"


# ---------------------------------------------------------------- политики (RBAC+ABAC)
def evaluate_policies(role: str, action: str, org_id: Optional[str], subject_org: Optional[str]) -> Optional[bool]:
    """Возвращает True/False по таблицам политик; None — если правил нет (→ дефолт deny).

    Приоритет: deny-правила важнее allow; ABAC-условие org_eq_subject сверяет
    ресурсный org_id с атрибутом субъекта (ТЗ: L4 — только своё предприятие).
    """
    verdict: Optional[bool] = None
    with session_scope() as db:
        rows = list(db.scalars(select(IamPolicy).where(IamPolicy.subject_role.in_([role, "*"]))))
    for p in rows:
        if p.action not in (action, "*"):
            continue
        if p.condition:
            try:
                cond = json.loads(p.condition)
            except Exception:
                continue
            if cond.get("org_eq_subject") and org_id is not None and org_id != subject_org:
                continue    # условие ABAC не выполнено — правило не применяется
        if p.effect == "deny":
            return False    # явный deny побеждает
        verdict = True
    return verdict


# Встроенный дефолт (строже демо-прототипа: согласован с RACI Прил. 4 —
# управление конфигурацией только L6/L7; таблицы политик БД имеют приоритет)
BUILTIN_ALLOW = {
    "admin": {"L6", "L7"},
    "gate": {"L1", "L2", "L5", "L6", "L7"},
    "expert.approve": {"L5", "L6", "L7"},
    "report.run": {"L1", "L2", "L5", "L6", "L7"},
    "org.write": {"L1", "L2", "L5", "L6", "L7"},
}


def can(user: AuthUser, action: str, org_id: Optional[str] = None) -> bool:
    """Итоговое решение: политики из БД (приоритет), иначе встроенный дефолт."""
    if action == "view":
        return True
    verdict = evaluate_policies(user.role, action, org_id, user.org_id)
    if verdict is not None:
        return verdict
    if action in BUILTIN_ALLOW and user.role in BUILTIN_ALLOW[action]:
        return True
    if user.role == "L4":
        if action == "admin":
            return False
        if action == "org.write" and org_id is not None:
            return org_id == user.org_id    # ABAC: только своё предприятие
        return False
    return False


# ---------------------------------------------------------------- зависимости FastAPI
def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(_pbearer)) -> AuthUser:
    if credentials is None:
        raise HTTPException(401, "Требуется аутентификация (Bearer JWT)")
    data = decode_token(credentials.credentials)
    return AuthUser(login=data["sub"], role=data["role"], org_id=data.get("org_id"))


def require(action: str = "view"):
    """Зависимость: проверка действия политики; отказ → iam.access_denied + аудит."""
    def dep(request: Request, user: AuthUser = Depends(get_current_user)) -> AuthUser:
        org_id = request.path_params.get("org_id") or request.path_params.get("orgId")
        if not can(user, action, org_id):
            _deny(user, action, org_id)
        return user
    return dep


def _deny(user: AuthUser, action: str, org_id: Optional[str]) -> None:
    from . import audit
    from .bus import get_bus
    detail = f"IAM: операция «{action}» запрещена для роли {user.role}" + (f" по объекту {org_id} (ABAC)" if org_id else "")
    get_bus().publish("iam.access_denied", "CORE:IAM", f"{action} · {user.login} ({user.role})", sev="warn")
    audit.record("Отказ в доступе (IAM/ABAC)", f"{action}" + (f" · {org_id}" if org_id else ""),
                 "Запрещено", user=user.login, role=user.role)
    raise HTTPException(403, detail)
