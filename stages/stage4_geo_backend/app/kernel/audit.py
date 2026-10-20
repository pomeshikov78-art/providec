"""Служба журналирования и аудита (ТЗ п.4.4.1; WORM + хеш-цепочка sha256).

Каждая запись содержит hash(prev_hash + payload): удаление/подлог записи
обнаруживается сверкой цепочки (verify_chain — регламентное задание планировщика).
"""
from __future__ import annotations

import hashlib
import json
from typing import List, Optional

from sqlalchemy import select

from ..config import settings
from ..db import session_scope
from ..models import AuditLog

GENESIS = "0" * 64


def _digest(prev_hash: str, body: dict) -> str:
    payload = json.dumps(body, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256((prev_hash + payload).encode("utf-8")).hexdigest()


def record(action: str, obj: str = "—", result: str = "Успех",
           user: str = "system", role: str = "—", ip: str = "127.0.0.1") -> dict:
    from datetime import datetime, timezone
    with session_scope() as db:
        last = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(1)).first()
        prev = last.hash if last else GENESIS
        ts = datetime.now(timezone.utc).replace(tzinfo=None)   # naive UTC: стабильно для SQLite/Postgres
        row = AuditLog(ts=ts, user_login=user, role_level=role, action=action, object=obj,
                       result=result, ip=ip, prev_hash=prev)
        body = {"ts": ts.isoformat(sep=" "), "user_login": user, "role_level": role, "action": action,
                "object": obj, "result": result, "ip": ip}
        row.hash = _digest(prev, body)
        db.add(row)
        db.flush()
        return {"id": row.id, "ts": row.ts.strftime("%Y-%m-%d %H:%M:%S"), "user": user,
                "role": role, "action": action, "object": obj, "result": result,
                "ip": ip, "hash": row.hash[:16]}


def tail(limit: int = 100, user: Optional[str] = None, action_like: Optional[str] = None) -> List[dict]:
    with session_scope() as db:
        q = select(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 1000))
        if user:
            q = q.where(AuditLog.user_login == user)
        if action_like:
            q = q.where(AuditLog.action.contains(action_like))
        rows = list(db.scalars(q))
    return [{"id": r.id, "ts": r.ts.strftime("%Y-%m-%d %H:%M:%S"), "user": r.user_login,
             "role": r.role_level, "action": r.action, "object": r.object, "result": r.result,
             "ip": r.ip, "hash": r.hash[:16], "prev": (r.prev_hash or "")[:16]} for r in rows]


def verify_chain() -> dict:
    """Сверка целостности хеш-цепочки (п.9 ТЗ, Приложение 7 — профиль варианта Б)."""
    if not settings().audit_hash_chain:
        return {"enabled": False, "ok": True, "checked": 0}
    prev = GENESIS
    checked = 0
    with session_scope() as db:
        for r in db.scalars(select(AuditLog).order_by(AuditLog.id.asc())):
            body = {"ts": r.ts.isoformat(sep=" ") if r.ts else None, "user_login": r.user_login,
                    "role_level": r.role_level, "action": r.action,
                    "object": r.object, "result": r.result, "ip": r.ip}
            expect = _digest(prev, body)
            if r.prev_hash != prev or r.hash != expect:
                return {"enabled": True, "ok": False, "checked": checked, "broken_at": r.id}
            prev = r.hash
            checked += 1
    return {"enabled": True, "ok": True, "checked": checked}
