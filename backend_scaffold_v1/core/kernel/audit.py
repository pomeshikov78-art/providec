"""Служба журналирования и аудита (ТЗ п.4.4.1, п.9; WORM-профиль).

Неизменяемый журнал с хеш-цепочкой: каждая запись содержит hash(prev_hash + payload),
что делает подлог/удаление обнаружимым. В production (вариант Б) — хранение в
журнале с однократной записью + периодическая сверка цепочки регламентным заданием.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import deque
from typing import Deque, Dict, List, Optional

GENESIS = "0" * 64


class AuditLog:
    _lock = threading.Lock()
    _records: Deque[dict] = deque(maxlen=100000)
    _last_hash: str = GENESIS

    @classmethod
    def record(cls, user, action: str, obj: str = "—", result: str = "Успех",
               ip: str = "127.0.0.1") -> dict:
        with cls._lock:
            body = {
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "user": getattr(user, "login", str(user)),
                "role": getattr(user, "role", "—"),
                "action": action, "object": obj, "result": result, "ip": ip,
            }
            payload = json.dumps(body, ensure_ascii=False, sort_keys=True)
            body["prev_hash"] = cls._last_hash[:16]
            body["hash"] = hashlib.sha256((cls._last_hash + payload).encode()).hexdigest()[:16]
            cls._last_hash = body["hash"]
            cls._records.appendleft(body)
            return body

    @classmethod
    def tail(cls, limit: int = 100) -> List[dict]:
        return list(cls._records)[:limit]

    @classmethod
    def verify_chain(cls) -> bool:
        """Сверка целостности хеш-цепочки (регламентное задание планировщика)."""
        prev = GENESIS
        for rec in reversed(list(cls._records)):
            body = {k: v for k, v in rec.items() if k not in ("prev_hash", "hash")}
            payload = json.dumps(body, ensure_ascii=False, sort_keys=True)
            expect = hashlib.sha256((prev + payload).encode()).hexdigest()[:16]
            if rec["hash"] != expect or rec["prev_hash"] != prev[:16]:
                return False
            prev = rec["hash"]
        return True
