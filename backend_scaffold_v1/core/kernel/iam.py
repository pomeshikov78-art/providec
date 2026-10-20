"""IAM: аутентификация (JWT) и авторизация RBAC + ABAC (ТЗ п.3.2, п.9).

Уровни доступа L0–L7 и политики перенесены из прототипа v8.0.0 (функция can()),
где они проверены демонстрационными отказами (событие iam.access_denied).

Вариант А: интеграция с ЕСИА (OAuth 2.0 / SAML), MFA.
Вариант Б: локальные учетные записи, мандатный доступ, СКЗИ ГОСТ.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional

import jwt
from fastapi import Depends, HTTPException, Request

from config import settings

ROLES = {
    "L0": "Внешний пользователь",
    "L1": "Государственные органы",
    "L2": "Отраслевые органы",
    "L3": "Партнеры/инвесторы",
    "L4": "Предприятие (собственный профиль)",
    "L5": "НИОКР/испытания",
    "L6": "Передача прав (делегирование)",
    "L7": "Администратор системы",
}

# Расширенные роли: полный доступ к записывающим операциям (как в прототипе)
FULL_ROLES = {"L1", "L2", "L5", "L6", "L7"}


@dataclass
class AuthUser:
    login: str
    role: str                 # L0..L7
    org_id: Optional[str]     # для L4 — собственное предприятие (атрибут ABAC)

    @property
    def display(self) -> str:
        return f"{self.login} ({self.role} · {ROLES.get(self.role, '?')})"


def issue_token(user: AuthUser) -> str:
    s = settings()
    payload = {"sub": user.login, "role": user.role, "org_id": user.org_id,
               "iat": int(time.time()), "exp": int(time.time()) + s.jwt_ttl_minutes * 60}
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_token(token: str) -> AuthUser:
    s = settings()
    data = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    return AuthUser(login=data["sub"], role=data["role"], org_id=data.get("org_id"))


def can(user: AuthUser, action: str, org_id: Optional[str] = None) -> bool:
    """Политика RBAC+ABAC (перенос 1:1 из прототипа v8).

    action: admin | gate | org.write | org.create | expert.approve | expert.assign
            | ai.run | ai.accept | report.run | view
    ABAC-атрибут: org_id пользователя (для L4 — только собственное предприятие).
    """
    if user.role in FULL_ROLES:
        return True
    if user.role == "L4":
        if action == "admin":
            return False
        if action == "org.write" and org_id is not None:
            return org_id == user.org_id          # ABAC: атрибут «свой объект»
        return False
    return action == "view"                        # L0, L3 — только просмотр


def require_role(min_role: str = "L0", action: str = "view", org_param: str = "orgId"):
    """Зависимость FastAPI: проверка роли и действия политики.

    При отказе публикуется событие iam.access_denied (через шину) и пишется аудит —
    здесь оставлен синхронный каркас; полная цепочка подключается на Фазе 1.
    """
    async def dep(request: Request) -> AuthUser:
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            raise HTTPException(401, "Требуется аутентификация (JWT)")
        user = decode_token(auth.split(" ", 1)[1])
        org_id = request.path_params.get(org_param)
        if not can(user, action, org_id):
            raise PermissionError(
                f"IAM: операция «{action}» запрещена для роли {user.role}"
                + (f" по объекту {org_id} (ABAC)" if org_id else "")
            )
        return user
    return dep
