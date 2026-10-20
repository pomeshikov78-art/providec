"""API Gateway / точка входа ядра АИС «Техноконтур».

Принцип Microkernel (ADR-001): ядро содержит только инфраструктурные сервисы
(реестр модулей, шина событий, IAM, аудит, планировщик, уведомления, health).
Бизнес-логика предметной области — в подключаемых модулях (MOD-*), которые
регистрируются здесь и взаимодействуют ИСКЛЮЧИТЕЛЬНО через шину событий.
"""
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from config import settings
from kernel.audit import AuditLog
from kernel.bus import get_bus
from kernel.iam import AuthUser, require_role
from kernel.registry import get_registry


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = settings()
    registry = get_registry()
    registry.load_builtin_modules()          # 15 модулей ТЗ п.4.7
    bus = get_bus()
    await bus.start()
    await bus.publish("core.started", "CORE:HealthManager",
                      f"Ядро запущено · вариант {s.variant} · модулей в реестре: {len(registry.all())}")
    yield
    await bus.stop()


app = FastAPI(
    title="АИС «Техноконтур» — API Gateway",
    version=settings().app_version,
    description="Шифр темы «Провидец» · ТЗ ред. 4.0 · контракт: openapi/openapi.yaml",
    lifespan=lifespan,
)

core = APIRouter(prefix="/api/v1/core", tags=["core"])


@core.get("/health")
async def health():
    reg = get_registry()
    return {"status": "ok", "variant": settings().variant,
            "modules": {m.code: m.status for m in reg.all()}}


@core.get("/modules")
async def list_modules(user: AuthUser = Depends(require_role("L1"))):
    return [m.dict() for m in get_registry().all()]


@core.patch("/modules/{code}")
async def toggle_module(code: str, request: Request, user: AuthUser = Depends(require_role("L7"))):
    body = await request.json()
    reg = get_registry()
    try:
        if body.get("enabled"):
            reg.enable(code)
        else:
            reg.disable(code)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))
    bus = get_bus()
    await bus.publish("module.enabled" if body.get("enabled") else "module.disabled",
                      "CORE:ModuleRegistry", f"{code} · пользователь {user.login} ({user.role})")
    AuditLog.record(user, ("Включение" if body.get("enabled") else "Отключение") + " модуля", code, "Успех")
    return reg.get(code).dict()


@core.post("/events")
async def publish_event(request: Request, user: AuthUser = Depends(require_role("L5"))):
    body = await request.json()
    ev = await get_bus().publish(body["type"], body.get("source", "external"),
                                 body.get("payload", ""), body.get("sev", "info"))
    return JSONResponse(ev, status_code=202)


@core.get("/events")
async def list_events(user: AuthUser = Depends(require_role("L1")), limit: int = 100):
    return await get_bus().journal(limit=min(limit, 500))


@core.get("/audit")
async def audit(user: AuthUser = Depends(require_role("L2"))):
    return AuditLog.tail(200)


# Маршрутизация модулей: каждый модуль монтирует свой router через Plugin API (ADR-001).
# Пример подключения (Фаза 2): from modules.pass_.router import router as pass_router
# app.include_router(pass_router, prefix="/api/v1", tags=["pass"])

app.include_router(core)


@app.exception_handler(PermissionError)
async def permission_handler(_: Request, exc: PermissionError):
    """Единый формат отказа IAM: событие iam.access_denied публикуется в kernel.iam."""
    return JSONResponse({"detail": str(exc)}, status_code=403)
