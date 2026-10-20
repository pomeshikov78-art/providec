"""Шина событий ядра (ТЗ п.4.4.1 Event Bus, Приложение 9).

Свойства (согласно ТЗ и ADR-001):
  * event-driven: модули публикуют/подписываются, прямое взаимодействие запрещено;
  * at-least-once: обработчик получает событие минимум один раз (повтор до подтверждения);
  * приоритеты: alert > warn > info — обработчики приоритетных подписок вызываются первыми;
  * DLQ: ошибка обработчика → событие помечается dlq=True и кладётся в очередь мёртвых писем;
  * журнал: каждое событие персистентно (events_log) — источник для монитора шины и аудита;
  * транспорт: in-process (dev/тесты) или Redis Streams (вариант Б); Kafka-адаптер — Фаза 1 prod.
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from collections import defaultdict
from typing import Callable, Dict, List

from sqlalchemy import select

from ..config import settings
from ..db import session_scope
from ..models import EventLog

log = logging.getLogger("kernel.bus")

Handler = Callable[[dict], None]

SEV_PRIORITY = {"alert": 0, "warn": 1, "info": 2}


class EventBus:
    def __init__(self) -> None:
        self._subs: Dict[str, List[Handler]] = defaultdict(list)
        self._lock = threading.RLock()
        self._redis = None
        s = settings()
        if s.bus_backend == "redis":
            try:
                import redis  # локальный импорт: не обязателен в dev-профиле
                self._redis = redis.Redis.from_url(s.redis_url, decode_responses=True)
                self._redis.ping()
                log.info("EventBus: транспорт Redis Streams (%s)", s.bus_stream)
            except Exception as exc:  # деградация в in-process без остановки ядра
                log.warning("EventBus: Redis недоступен (%s) — деградация в in-process", exc)
                self._redis = None

    # ------------------------------------------------------------- подписки
    def subscribe(self, event_type: str, handler: Handler) -> None:
        """Подписка модуля/сервиса. Шаблоны: 'niokr.*', '*'."""
        with self._lock:
            self._subs[event_type].append(handler)

    def handlers_for(self, event_type: str) -> List[Handler]:
        with self._lock:
            exact = list(self._subs.get(event_type, []))
            templ = [h for pat, hs in self._subs.items() if pat.endswith("*") and event_type.startswith(pat[:-1]) for h in hs]
        return exact + templ

    # ------------------------------------------------------------- публикация
    def publish(self, type_: str, source: str, payload: str = "", sev: str = "info",
                trace_id: str | None = None) -> dict:
        ev = {
            "id": None,
            "ts": None,
            "type": type_,
            "source": source,
            "payload": payload,
            "sev": sev if sev in SEV_PRIORITY else "info",
            "trace_id": trace_id or str(uuid.uuid4()),
        }
        # 1) персистентный журнал (неизменяемая последовательность)
        with session_scope() as db:
            row = EventLog(type=type_, source=source, payload=payload, sev=ev["sev"], trace_id=ev["trace_id"])
            db.add(row)
            db.flush()
            ev["id"] = row.id
            ev["ts"] = row.ts.isoformat(sep=" ", timespec="seconds")
        # 2) дублирование в транспорт варианта Б (Redis Streams) — fire-and-forget
        if self._redis is not None:
            try:
                self._redis.xadd(settings().bus_stream, {"event": json.dumps(ev, ensure_ascii=False)}, maxlen=100000)
            except Exception as exc:
                log.warning("EventBus: XADD failed: %s", exc)
        # 3) доставка подписчикам (at-least-once + DLQ)
        self._deliver(ev)
        return ev

    def _deliver(self, ev: dict) -> None:
        delivered = 0
        for h in self.handlers_for(ev["type"]):
            try:
                h(ev)
                delivered += 1
            except Exception as exc:
                log.error("EventBus: обработчик %s упал на %s: %s → DLQ", getattr(h, "__name__", h), ev["type"], exc)
                with session_scope() as db:
                    row = db.get(EventLog, ev["id"])
                    if row:
                        row.dlq = True
                        row.payload = (row.payload or "") + f" || DLQ: {exc}"
                if self._redis is not None:
                    try:
                        self._redis.xadd(settings().bus_dlq, {"event": json.dumps(ev, ensure_ascii=False), "error": str(exc)})
                    except Exception:
                        pass
        with session_scope() as db:
            row = db.get(EventLog, ev["id"])
            if row:
                row.delivered = delivered
        # приоритетная эскалация: alert-события дополнительно логируются
        if ev["sev"] == "alert":
            log.warning("ALERT %s ← %s: %s", ev["type"], ev["source"], ev["payload"])

    # ------------------------------------------------------------- чтение журнала
    def journal(self, limit: int = 100, type_: str | None = None, source: str | None = None) -> List[dict]:
        with session_scope() as db:
            q = select(EventLog).order_by(EventLog.id.desc()).limit(min(limit, 500))
            if type_:
                q = q.where(EventLog.type == type_)
            if source:
                q = q.where(EventLog.source == source)
            rows = list(db.scalars(q))
        return [{"id": r.id, "ts": r.ts.strftime("%Y-%m-%d %H:%M:%S"), "type": r.type,
                 "source": r.source, "payload": r.payload, "sev": r.sev,
                 "dlq": r.dlq, "delivered": r.delivered} for r in rows]

    def dlq(self, limit: int = 50) -> List[dict]:
        with session_scope() as db:
            rows = list(db.scalars(select(EventLog).where(EventLog.dlq.is_(True))
                                   .order_by(EventLog.id.desc()).limit(limit)))
        return [{"id": r.id, "type": r.type, "source": r.source, "payload": r.payload} for r in rows]


_bus: EventBus | None = None
_bus_lock = threading.Lock()


def get_bus() -> EventBus:
    global _bus
    with _bus_lock:
        if _bus is None:
            _bus = EventBus()
        return _bus


def reset_bus() -> None:
    """Для тестов."""
    global _bus
    with _bus_lock:
        _bus = None
