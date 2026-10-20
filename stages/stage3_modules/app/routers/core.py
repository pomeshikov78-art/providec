"""Роутеры ядра: реестр модулей, шина событий, хранилище (ТЗ п.4.4)."""
from __future__ import annotations

import zlib

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from ..config import settings
from ..db import session_scope
from ..kernel import audit, registry
from ..kernel.bus import get_bus
from ..kernel.iam import AuthUser, get_current_user, require
from ..models import EventLog, Organization

router = APIRouter(prefix="/api/v1/core", tags=["core"])


class ToggleRequest(BaseModel):
    enabled: bool


class EventIn(BaseModel):
    type: str
    source: str = "external"
    payload: str = ""
    sev: str = "info"


@router.get("/health")
def health():
    """Healthcheck ядра (Менеджер состояний, ТЗ п.4.4.1)."""
    return {"status": "ok", "app": settings().app_name, "cipher": settings().app_cipher,
            "version": settings().app_version, "variant": settings().variant,
            "modules": registry.healthcheck()}


@router.get("/modules")
def modules(user: AuthUser = Depends(require("view"))):
    return registry.list_modules()


@router.get("/modules/{code}")
def module(code: str, user: AuthUser = Depends(require("view"))):
    try:
        return registry.get_module(code)
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.patch("/modules/{code}")
def toggle_module(code: str, req: ToggleRequest, user: AuthUser = Depends(require("admin"))):
    try:
        result = registry.set_module(code, req.enabled, actor=user.login)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))
    except KeyError as e:
        raise HTTPException(404, str(e))
    audit.record(("Включение" if req.enabled else "Отключение") + " модуля", code,
                 "Успех", user=user.login, role=user.role)
    return result


@router.get("/events")
def events(limit: int = 100, type: str | None = None, source: str | None = None,
           user: AuthUser = Depends(require("view"))):
    return get_bus().journal(limit=limit, type_=type, source=source)


@router.post("/events", status_code=202)
def publish_event(ev: EventIn, user: AuthUser = Depends(require("view"))):
    """Публикация события через API Gateway (модули/внешние клиенты)."""
    return get_bus().publish(ev.type, ev.source or user.login, ev.payload, ev.sev)


@router.get("/events/dlq")
def dlq(user: AuthUser = Depends(require("view"))):
    return get_bus().dlq()


@router.get("/audit")
def audit_tail(limit: int = 100, user: AuthUser = Depends(require("view"))):
    return audit.tail(limit=limit)


@router.get("/audit/verify")
def audit_verify(user: AuthUser = Depends(require("view"))):
    """Сверка целостности WORM-журнала (хеш-цепочка)."""
    return audit.verify_chain()


@router.get("/storage")
def storage(user: AuthUser = Depends(require("view"))):
    """Хранилище данных: коллекции и CRC32-контроль целостности (как в прототипе v8)."""
    from ..models import AuditLog, Document, PassportVersion, Project, Risk, Twin
    from ..db import get_session_factory
    db = get_session_factory()()
    try:
        cols = {}
        for model in (Organization, Project, Risk, Document, PassportVersion, Twin, EventLog, AuditLog):
            cols[model.__tablename__] = db.scalar(select(model).limit(1)) is not None
        counts = {}
        for model in (Organization, Project, Risk, Document, PassportVersion, Twin, EventLog, AuditLog):
            from sqlalchemy import func
            counts[model.__tablename__] = db.scalar(select(func.count()).select_from(model))
        crcs = {}
        for name in ("organizations", "projects", "risks"):
            blob = repr(sorted(counts.items())) + name
            crcs[name] = "0x%08x" % (zlib.crc32(blob.encode()) & 0xFFFFFFFF)
        return {"collections": counts, "crc32_sample": crcs}
    finally:
        db.close()
