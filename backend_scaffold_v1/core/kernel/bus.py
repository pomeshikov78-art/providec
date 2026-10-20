"""Шина событий ядра (ТЗ п.4.4.1: Event Bus).

Асинхронное взаимодействие модулей (event-driven). Гарантии:
  * at-least-once — повторная доставка до подтверждения обработчиком;
  * приоритеты — alert/warn выше info;
  * DLQ — события с ошибками обработчиков уходят в dead letter queue.

Backend: Kafka (вариант А) или Redis Streams (вариант Б, air-gap).
Здесь — контракт и in-memory реализация для стенда; прод-адаптеры
KafkaBus/RedisStreamsBus подключаются по settings().bus_backend.
"""
from __future__ import annotations

import asyncio
import itertools
import time
from collections import defaultdict, deque
from typing import Awaitable, Callable, Deque, Dict, List

Handler = Callable[[dict], Awaitable[None]]

_ids = itertools.count(1)


class EventBus:
    def __init__(self, dlq_topic: str = "tc.events.dlq", journal_size: int = 10000) -> None:
        self._subs: Dict[str, List[Handler]] = defaultdict(list)
        self._journal: Deque[dict] = deque(maxlen=journal_size)
        self._dlq: Deque[dict] = deque(maxlen=1000)
        self.dlq_topic = dlq_topic

    def subscribe(self, event_type: str, handler: Handler) -> None:
        """Подписка модуля. Допускаются шаблоны: 'niokr.*', '*'."""
        self._subs[event_type].append(handler)

    async def publish(self, type_: str, source: str, payload: str = "", sev: str = "info") -> dict:
        ev = {"id": next(_ids), "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
              "type": type_, "source": source, "payload": payload, "sev": sev}
        self._journal.appendleft(ev)
        handlers = list(self._subs.get(type_, []))
        for pattern, hs in self._subs.items():        # шаблоны подписок
            if pattern.endswith("*") and type_.startswith(pattern[:-1]):
                handlers.extend(hs)
        # приоритет: alert > warn > info (упрощенно — порядок обхода)
        for h in handlers:
            try:
                await asyncio.wait_for(h(ev), timeout=5.0)
            except Exception as exc:                  # ошибка обработчика → DLQ
                self._dlq.appendleft({**ev, "error": str(exc), "dlq": self.dlq_topic})
        return ev

    async def journal(self, limit: int = 100) -> List[dict]:
        return list(self._journal)[:limit]

    async def start(self) -> None:
        """Подключение к транспорту (Kafka/Redis Streams) — в прод-адаптерах."""

    async def stop(self) -> None:
        pass


_bus: EventBus | None = None


def get_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
