"""Реестр модулей ядра (ТЗ п.4.4.1, п.4.7).

Правила, перенесенные из прототипа v8.0.0 (проверены демонстрацией):
  * 15 модулей: 6 обязательных (не отключаются) и 9 опциональных;
  * горячее подключение/отключение без остановки ядра;
  * включение возможно только при активных зависимостях;
  * отключение модуля каскадно переводит зависимые опциональные в «degraded».
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Literal

Status = Literal["active", "disabled", "degraded", "error"]

BUILTIN_MODULES: List[dict] = [
    # code, name, required, version, deps  (ТЗ п.4.7)
    {"code": "MOD-PASS",   "name": "Цифровой паспорт предприятия",      "required": True,  "version": "4.0.3", "deps": []},
    {"code": "MOD-PROF",   "name": "Цифровой профиль и аналитика",      "required": True,  "version": "4.0.2", "deps": ["MOD-PASS", "MOD-COMP"]},
    {"code": "MOD-NIOKR",  "name": "Управление жизненным циклом НИОКР", "required": True,  "version": "4.0.5", "deps": ["MOD-PASS"]},
    {"code": "MOD-COMP",   "name": "Оценка компетенций и зрелости",     "required": True,  "version": "4.0.1", "deps": ["MOD-PASS"]},
    {"code": "MOD-REPORT", "name": "Отчетность и дашборды",             "required": True,  "version": "4.0.4", "deps": ["MOD-PROF", "MOD-KPI"]},
    {"code": "MOD-GEO",    "name": "Геоподдержка и геоаналитика",       "required": True,  "version": "4.0.6", "deps": ["MOD-PASS", "MOD-PROF"]},
    {"code": "MOD-EXPERT", "name": "Экспертная оценка и верификация",   "required": False, "version": "3.9.2", "deps": ["MOD-PASS"]},
    {"code": "MOD-PORTF",  "name": "Портфель проектов и программ",      "required": False, "version": "3.8.7", "deps": ["MOD-NIOKR"]},
    {"code": "MOD-RISK",   "name": "Управление рисками",                "required": False, "version": "3.9.0", "deps": ["MOD-PROF"]},
    {"code": "MOD-COOP",   "name": "Поиск кооперации и матчинг",        "required": False, "version": "3.9.4", "deps": ["MOD-PROF", "MOD-GEO"]},
    {"code": "MOD-INT",    "name": "Интеграционный шлюз",               "required": False, "version": "4.0.0", "deps": []},
    {"code": "MOD-AI",     "name": "ИИ-рекомендации и прогнозирование", "required": False, "version": "3.7.5", "deps": ["MOD-PROF", "MOD-NIOKR"]},
    {"code": "MOD-DOC",    "name": "Электронный документооборот",       "required": False, "version": "3.8.1", "deps": ["MOD-PASS"]},
    {"code": "MOD-STIM",   "name": "Стимулы и санкции",                 "required": False, "version": "3.6.9", "deps": ["MOD-KPI"]},
    {"code": "MOD-KPI",    "name": "Показатели эффективности",          "required": False, "version": "4.0.1", "deps": ["MOD-PROF"]},
]


@dataclass
class Module:
    code: str
    name: str
    required: bool
    version: str
    deps: List[str] = field(default_factory=list)
    status: Status = "active"

    def dict(self) -> dict:
        return asdict(self)


class ModuleRegistry:
    def __init__(self) -> None:
        self._modules: Dict[str, Module] = {}

    def load_builtin_modules(self) -> None:
        for m in BUILTIN_MODULES:
            self._modules[m["code"]] = Module(**m)

    def all(self) -> List[Module]:
        return list(self._modules.values())

    def get(self, code: str) -> Module:
        try:
            return self._modules[code]
        except KeyError:
            raise ValueError(f"Модуль {code} не зарегистрирован в ядре")

    def is_active(self, code: str) -> bool:
        return code in self._modules and self._modules[code].status == "active"

    def disable(self, code: str) -> List[str]:
        m = self.get(code)
        if m.required:
            raise PermissionError(f"Модуль {code} обязателен (ТЗ п.4.7) и не может быть отключен")
        m.status = "disabled"
        degraded: List[str] = []
        for other in self._modules.values():          # каскадная деградация зависимых
            if code in other.deps and other.status == "active" and not other.required:
                other.status = "degraded"
                degraded.append(other.code)
        return degraded

    def enable(self, code: str) -> None:
        m = self.get(code)
        missing = [d for d in m.deps if not self.is_active(d)]
        if missing:
            raise ValueError(f"Зависимости не активны: {', '.join(missing)}")
        m.status = "active"


_registry: ModuleRegistry | None = None


def get_registry() -> ModuleRegistry:
    global _registry
    if _registry is None:
        _registry = ModuleRegistry()
    return _registry
