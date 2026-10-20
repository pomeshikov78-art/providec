"""АИС «Техноконтур» (шифр «Провидец») — точка входа API Gateway / ядра.

Запуск:  uvicorn app.main:app --host 0.0.0.0 --port 8000
Dev-профиль: SQLite + in-process шина; Production (вариант А): Postgres Pro + Kafka/Redis;
вариант Б (air-gap): Postgres Pro + Redis Streams + локальные коннекторы.
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import init_db
from .kernel import audit, registry
from .kernel.bus import get_bus
from .kernel.security import RateLimitMiddleware, SecurityHeadersMiddleware
from .routers import auth as auth_router
from .routers import core as core_router

log = logging.getLogger("technocontour")
logging.basicConfig(level=logging.INFO,
                    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","src":"%(name)s","msg":"%(message)s"}')


@asynccontextmanager
async def lifespan(app: FastAPI):
    t0 = time.monotonic()
    s = settings()
    init_db()
    from .seed import seed_domain, seed_kernel
    seed_kernel()
    dom = seed_domain()
    bus = get_bus()
    from .services.twin import register_twin_subscriptions
    register_twin_subscriptions()   # ИВП-2 → twin.rebuilt (event-driven)
    from .services.stim import register_stim_subscriptions
    from .services.docflow import register_doc_subscriptions
    from .services.expert import register_expert_subscriptions
    register_stim_subscriptions()   # Прил. 1.6: меры по событиям шины (Этап 8)
    register_doc_subscriptions()    # MOD-DOC: авторегистрация отчётов и заключений
    register_expert_subscriptions() # MOD-EXPERT: SLA-контроль очереди ИВП-1
    boot = round(time.monotonic() - t0, 2)
    # Требование ТЗ п.4.4.2: время запуска ядра ≤ 30 с (контролируется тестом)
    assert boot <= s.core_boot_max_sec, f"Нарушен норматив запуска ядра: {boot} c > {s.core_boot_max_sec} c"
    bus.publish("core.started", "CORE:HealthManager",
                f"Ядро запущено за {boot} с (норматив ≤ {s.core_boot_max_sec} с) · вариант {s.variant} · "
                f"модулей: {registry.healthcheck()['total']} · seed: {dom}")
    audit.record("Запуск ядра", f"boot {boot} с · variant {s.variant}", "Успех", user="system")
    log.info("Ядро запущено за %.2f с (вариант %s)", boot, s.variant)
    yield
    bus.publish("core.stopped", "CORE:HealthManager", "Остановка ядра")


def create_app() -> FastAPI:
    s = settings()
    app = FastAPI(title=f"{s.app_name} — API Gateway", version=s.app_version,
                  description="Шифр темы «Провидец» · ТЗ ред. 4.0 · контракт: openapi.yaml",
                  lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    if s.security_headers:
        app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware)

    app.include_router(core_router.router)
    app.include_router(auth_router.router)
    from .kernel.oidc import router as oidc_router
    app.include_router(oidc_router)

    _t0 = time.monotonic()

    @app.get("/metrics", include_in_schema=False)
    def metrics():
        """Prometheus-метрики (Этап 7: мониторинг)."""
        from fastapi.responses import PlainTextResponse
        from sqlalchemy import func as sfunc
        from sqlalchemy import select as sselect
        from .db import get_session_factory
        from .models import AuditLog, EventLog, Organization
        lines = ["# HELP tc_uptime_seconds Время работы процесса ядра",
                 "# TYPE tc_uptime_seconds gauge",
                 f"tc_uptime_seconds {time.monotonic() - _t0:.1f}"]
        try:
            db = get_session_factory()()
            ev = db.scalar(sselect(sfunc.count()).select_from(EventLog)) or 0
            au = db.scalar(sselect(sfunc.count()).select_from(AuditLog)) or 0
            orgs = db.scalar(sselect(sfunc.count()).select_from(Organization)) or 0
            db.close()
        except Exception:
            ev = au = orgs = 0
        lines += ["# HELP tc_events_total Всего событий в шине", "# TYPE tc_events_total counter",
                  f"tc_events_total {ev}",
                  "# HELP tc_audit_records_total Записей WORM-аудита", "# TYPE tc_audit_records_total counter",
                  f"tc_audit_records_total {au}",
                  "# HELP tc_organizations_total Организаций в реестре", "# TYPE tc_organizations_total gauge",
                  f"tc_organizations_total {orgs}"]
        h = registry.healthcheck()
        lines += ["# HELP tc_modules_active Активных модулей ядра", "# TYPE tc_modules_active gauge",
                  f"tc_modules_active {h['active']}",
                  "# HELP tc_modules_degraded Деградированных модулей", "# TYPE tc_modules_degraded gauge",
                  f"tc_modules_degraded {len(h['degraded'])}"]
        return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")

    # Модульные роутеры подключаются по мере реализации (Фазы 2–3 плана):
    # отсутствие файла роутера на ранней стадии не препятствует запуску ядра.
    import importlib
    for mod_name in ("orgs", "profile", "niokr", "geo", "reports", "coop", "integrations",
                     "modules2", "bootstrap"):
        try:
            r = importlib.import_module(f".routers.{mod_name}", package=__package__)
            app.include_router(r.router)
        except ImportError:
            log.info("Роутер %s еще не реализован — пропущен (поэтапная сборка)", mod_name)
    return app


app = create_app()
