"""Реестр модулей ядра (ТЗ п.4.4.1, п.4.7) — DB-backed.

Правила (перенесены 1:1 из прототипа v8, согласованы демонстрацией):
  * 15 модулей: 6 обязательных (отключение запрещено политикой ядра), 9 опциональных;
  * горячее подключение/отключение без остановки ядра;
  * включение только при активных зависимостях;
  * отключение → каскадная деградация зависимых опциональных модулей.
"""
from __future__ import annotations

from typing import List

from sqlalchemy import select

from ..db import session_scope
from ..models import ModuleRegistry
from .bus import get_bus

BUILTIN = [
    # code, name, required, version, deps
    ("MOD-PASS",   "Цифровой паспорт предприятия",      True,  "4.0.3", ""),
    ("MOD-PROF",   "Цифровой профиль и аналитика",      True,  "4.0.2", "MOD-PASS,MOD-COMP"),
    ("MOD-NIOKR",  "Управление жизненным циклом НИОКР", True,  "4.0.5", "MOD-PASS"),
    ("MOD-COMP",   "Оценка компетенций и зрелости",     True,  "4.0.1", "MOD-PASS"),
    ("MOD-REPORT", "Отчетность и дашборды",             True,  "4.0.4", "MOD-PROF,MOD-KPI"),
    ("MOD-GEO",    "Геоподдержка и геоаналитика",       True,  "4.0.6", "MOD-PASS,MOD-PROF"),
    ("MOD-EXPERT", "Экспертная оценка и верификация",   False, "3.9.2", "MOD-PASS"),
    ("MOD-PORTF",  "Портфель проектов и программ",      False, "3.8.7", "MOD-NIOKR"),
    ("MOD-RISK",   "Управление рисками",                False, "3.9.0", "MOD-PROF"),
    ("MOD-COOP",   "Поиск кооперации и матчинг",        False, "3.9.4", "MOD-PROF,MOD-GEO"),
    ("MOD-INT",    "Интеграционный шлюз",               False, "4.0.0", ""),
    ("MOD-AI",     "ИИ-рекомендации и прогнозирование", False, "3.7.5", "MOD-PROF,MOD-NIOKR"),
    ("MOD-DOC",    "Электронный документооборот",       False, "3.8.1", "MOD-PASS"),
    ("MOD-STIM",   "Стимулы и санкции",                 False, "3.6.9", "MOD-KPI"),
    ("MOD-KPI",    "Показатели эффективности",          False, "4.0.1", "MOD-PROF"),
]


def bootstrap_registry() -> None:
    """Регистрация встроенных модулей при запуске ядра (идемпотентно)."""
    with session_scope() as db:
        for code, name, req, ver, deps in BUILTIN:
            row = db.get(ModuleRegistry, code)
            if row is None:
                db.add(ModuleRegistry(code=code, name=name, required=req, version=ver, deps=deps, status="active"))


def _mod_dict(m: ModuleRegistry) -> dict:
    return {"code": m.code, "name": m.name, "required": m.required, "version": m.version,
            "deps": m.dep_list, "status": m.status,
            "updated_at": m.updated_at.strftime("%Y-%m-%d %H:%M:%S")}


def list_modules() -> List[dict]:
    with session_scope() as db:
        return [_mod_dict(m) for m in db.scalars(select(ModuleRegistry).order_by(ModuleRegistry.code))]


def get_module(code: str) -> dict:
    with session_scope() as db:
        m = db.get(ModuleRegistry, code)
        if m is None:
            raise KeyError(f"Модуль {code} не зарегистрирован в ядре")
        return _mod_dict(m)


def is_active(code: str) -> bool:
    with session_scope() as db:
        m = db.get(ModuleRegistry, code)
        return bool(m and m.status == "active")


def set_module(code: str, enabled: bool, actor: str = "system") -> dict:
    """Горячее включение/отключение. Возвращает обновленное состояние модуля."""
    bus = get_bus()
    with session_scope() as db:
        m = db.get(ModuleRegistry, code)
        if m is None:
            raise KeyError(f"Модуль {code} не зарегистрирован в ядре")
        if not enabled and m.required:
            raise PermissionError(f"Модуль {code} обязателен (ТЗ п.4.7) и не может быть отключен")
        if enabled:
            missing = [d for d in m.dep_list
                       if not (db.get(ModuleRegistry, d) and db.get(ModuleRegistry, d).status == "active")]
            if missing:
                raise ValueError(f"Зависимости не активны: {', '.join(missing)}")
            m.status = "active"
            # восстановление деградированных зависимых (если их зависимости вновь активны)
            for other in db.scalars(select(ModuleRegistry)):
                if other.status == "degraded" and all(
                        (db.get(ModuleRegistry, d) and db.get(ModuleRegistry, d).status == "active")
                        for d in other.dep_list):
                    other.status = "active"
        else:
            m.status = "disabled"
            for other in db.scalars(select(ModuleRegistry)):
                if code in other.dep_list and other.status == "active" and not other.required:
                    other.status = "degraded"
        m.updated_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        result = _mod_dict(m)
    bus.publish("module.enabled" if enabled else "module.disabled", "CORE:ModuleRegistry",
                f"{code} · v{result['version']} · оператор {actor}"
                + ("" if enabled else " · graceful degradation"),
                sev="info" if enabled else "warn")
    return result


def healthcheck() -> dict:
    mods = list_modules()
    active = [m for m in mods if m["status"] == "active"]
    return {"total": len(mods), "active": len(active),
            "degraded": [m["code"] for m in mods if m["status"] == "degraded"],
            "disabled": [m["code"] for m in mods if m["status"] == "disabled"]}
