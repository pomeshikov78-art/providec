"""Базовый коннектор: retry с экспоненциальной задержкой, circuit breaker,
идемпотентность, журнал вызовов и события шины (ТЗ п.5.10: надёжность обмена).

Режимы (settings().connectors_mode):
  sandbox — детерминированные стенды внешних систем (разработка/демо/приёмка);
  live    — реальные HTTPS-вызовы (учётные данные из конфигурации; включаются
            на этапе ОПЭ после получения доступов — Фаза 4 плана).
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ..config import settings
from ..kernel.bus import get_bus


@dataclass
class CircuitState:
    failures: int = 0
    opened_at: float = 0.0
    THRESHOLD: int = 3
    RECOVERY_SEC: float = 30.0

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.THRESHOLD:
            self.opened_at = time.monotonic()

    def record_success(self) -> None:
        self.failures = 0
        self.opened_at = 0.0

    def allow(self) -> bool:
        if self.failures < self.THRESHOLD:
            return True
        return (time.monotonic() - self.opened_at) > self.RECOVERY_SEC   # half-open


@dataclass
class CallRecord:
    ts: float
    op: str
    ok: bool
    ms: int
    idem: str = ""


class BaseConnector:
    code = "BASE"
    name = "Базовый коннектор"

    def __init__(self) -> None:
        self.circuit = CircuitState()
        self.calls: List[CallRecord] = []
        self._idem_seen: Dict[str, Any] = {}

    # ------------------------------------------------------------ инфраструктура
    def _with_retry(self, op: str, fn: Callable[[], Any], idem_key: str = "") -> Any:
        if idem_key and idem_key in self._idem_seen:      # идемпотентность: повтор → кэш
            return self._idem_seen[idem_key]
        if not self.circuit.allow():
            get_bus().publish("int.connector_error", f"MOD-INT:{self.code}",
                              f"Circuit breaker OPEN: {op} отклонён до восстановления канала", sev="warn")
            raise RuntimeError(f"{self.code}: circuit breaker open")
        attempt, last_exc, t0 = 0, None, time.monotonic()
        while attempt < 3:
            attempt += 1
            try:
                res = fn()
                self.circuit.record_success()
                self.calls.append(CallRecord(time.time(), op, True, int((time.monotonic() - t0) * 1000), idem_key))
                if idem_key:
                    self._idem_seen[idem_key] = res
                return res
            except Exception as exc:                       # noqa: BLE001 — retry на любую ошибку транспорта
                last_exc = exc
                self.circuit.record_failure()
                time.sleep(min(0.05 * (2 ** (attempt - 1)) + random.random() * 0.01, 0.2))
        self.calls.append(CallRecord(time.time(), op, False, int((time.monotonic() - t0) * 1000), idem_key))
        get_bus().publish("int.connector_error", f"MOD-INT:{self.code}",
                          f"{op}: {attempt} попыток исчерпано ({last_exc})", sev="alert")
        raise RuntimeError(f"{self.code}: {op} — обмен не удался после {attempt} попыток") from last_exc

    def status(self) -> dict:
        ok = sum(1 for c in self.calls if c.ok)
        return {"code": self.code, "name": self.name,
                "mode": settings().connectors_mode,
                "calls": len(self.calls), "ok": ok, "failed": len(self.calls) - ok,
                "circuit": "open" if not self.circuit.allow() else "closed",
                "last": [{"op": c.op, "ok": c.ok, "ms": c.ms} for c in self.calls[-5:]]}


# ---------------------------------------------------------------- реестр коннекторов
class EgrulConnector(BaseConnector):
    """ЕГРЮЛ (ФНС России): сведения о юридическом лице по ИНН. Вариант Б — ручной импорт."""
    code, name = "EGRUL", "ЕГРЮЛ (ФНС России)"

    def fetch_by_inn(self, inn: str) -> dict:
        def op():
            if settings().connectors_mode == "live":
                return self._live(inn)
            return self._sandbox(inn)
        return self._with_retry(f"Запрос сведений ИНН {inn}", op, idem_key=f"inn:{inn}")

    def _live(self, inn: str) -> dict:
        import httpx
        # Реальный доступ: API ФНС (dadata-совместимый профиль) по сервисному сертификату.
        # Учётные данные — из защищённой конфигурации (вариант Б — СКЗИ-канал).
        raise NotImplementedError("live-режим включается после выдачи доступов ФНС (Фаза 4 плана)")

    def _sandbox(self, inn: str) -> dict:
        from ..db import session_scope
        from ..models import Organization
        from sqlalchemy import select
        with session_scope() as db:
            o = db.scalars(select(Organization).where(Organization.inn == inn)).first()
            if o is None:
                raise KeyError(f"ИНН {inn} не найден в ЕГРЮЛ (стенд)")
            return {"inn": o.inn, "ogrn": o.ogrn or "1" + o.inn + "0",
                    "full_name": o.name, "short_name": o.short_name,
                    "address": f"г. {o.city}, {o.region}", "status": "Действующее",
                    "okved": "26.30, 62.01, 72.19", "registered": str(o.founded),
                    "source": "ЕГРЮЛ (стенд)", "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S")}


class GispConnector(BaseConnector):
    """ГИСП (Минпромторг): реестр промышленной продукции и статусы ОПП."""
    code, name = "GISP", "ГИСП (Минпромторг)"

    def products(self, org_id: str) -> dict:
        def op():
            from ..db import session_scope
            from ..models import Organization
            with session_scope() as db:
                o = db.get(Organization, org_id)
                if o is None:
                    raise KeyError(org_id)
                n = 3 + (o.employees % 7)
                return {"org_id": org_id, "in_registry_opp": o.status == "verified",
                        "products": [{"code": f"РП-{org_id}-{i+1:02d}",
                                      "name": f"Изделие «{o.short_name.split('«')[-1].split('»')[0] if '«' in o.short_name else o.short_name}» мод. {i+1}",
                                      "status": "В реестре" if i % 3 else "На экспертизе"}
                                     for i in range(n)],
                        "source": "ГИСП (стенд)"}
        return self._with_retry(f"Реестр продукции {org_id}", op, idem_key=f"gisp:{org_id}")


class RospatentConnector(BaseConnector):
    """Роспатент (ФИПС): патенты и заявки организации."""
    code, name = "ROSPATENT", "Роспатент (ФИПС)"

    def patents(self, org_id: str) -> dict:
        def op():
            from ..db import session_scope
            from ..models import Organization
            with session_scope() as db:
                o = db.get(Organization, org_id)
                if o is None:
                    raise KeyError(org_id)
                base = (o.employees % 9) + 2
                return {"org_id": org_id,
                        "patents": [{"number": f"RU {2700000 + (hash(org_id) % 90000) + i}",
                                     "title": f"Способ {['формирования','обработки','контроля','передачи'][i % 4]} "
                                              f"{['сигналов','данных','изображений','метрологических характеристик'][(i+1) % 4]}",
                                     "status": "Действует" if i % 4 else "Заявка",
                                     "date": f"{2021 + (i % 5)}-0{1 + i % 9}-1{ i % 9}"}
                                    for i in range(base)],
                        "source": "ФИПС (стенд)"}
        return self._with_retry(f"Патенты {org_id}", op, idem_key=f"pat:{org_id}")


class EsiaConnector(BaseConnector):
    """ЕСИА: подтвержденная учетная запись (через Keycloak OIDC — kernel/oidc.py)."""
    code, name = "ESIA", "ЕСИА (Госуслуги)"

    def available(self) -> dict:
        return {"code": self.code, "mode": "oidc",
                "enabled": bool(settings().keycloak_url),
                "note": "Аутентификация — kernel/oidc.py (Authorization Code + PKCE); в варианте Б недоступна"}


class AssprConnector(BaseConnector):
    """АССПР v2.4: приём цифровых паспортов НТП (ручной импорт — вариант Б, API — вариант А)."""
    code, name = "ASSPR", "АССПР v2.4 «Цифровой паспорт НТП»"

    def import_package(self, pkg: dict, actor: str) -> dict:
        """Импорт пакета: валидация → сопоставление организации → применение полей раздела 1–12."""
        def op():
            from ..services.asspr_import import import_asspr
            return import_asspr(pkg, actor)
        return self._with_retry("Импорт пакета АССПР", op)


CONNECTORS: Dict[str, BaseConnector] = {}


def get_connector(code: str) -> BaseConnector:
    if not CONNECTORS:
        for cls in (EgrulConnector, GispConnector, RospatentConnector, EsiaConnector, AssprConnector):
            c = cls()
            CONNECTORS[c.code] = c
    if code not in CONNECTORS:
        raise KeyError(f"Коннектор {code} не зарегистрирован")
    return CONNECTORS[code]


def all_status() -> List[dict]:
    get_connector("EGRUL")
    return [c.status() if not isinstance(c, EsiaConnector) else c.available() for c in CONNECTORS.values()]
