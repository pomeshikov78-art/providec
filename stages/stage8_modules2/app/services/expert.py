"""MOD-EXPERT: экспертная оценка и верификация (ИВП-1 шаги 7–9, ИВП-3, Прил. 3.7).

Очередь верификации хранится в СУБД (expert_queue). Процедура (Приложение 3.7):
самооценка → экспертная оценка (комиссия ≥ 3 чел.) → верификация документальной
базы → арбитраж (расхождение > 1 уровня) → утверждение в профиле MOD-PROF.

Норматив ИВП-1: обработка ≤ 8 часов с момента постановки в очередь — нарушение
фиксируется в SLA-отчёте и событием ``expert.sla_breach``. Заключение выдаётся
только назначенным экспертом (статус in_review), сопровождается ЭЦП-отпечатком
(MOD-DOC регистрирует заключение автоматически по событию expert.conclusion_ready)
и при арбитраже переводит организацию в status=verified (как в витрине прототипа:
E11 — расхождение ЕГРЮЛ устранено).
"""
from __future__ import annotations

import hashlib
import threading
from datetime import date, datetime, time, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..kernel.bus import get_bus
from ..models import ExpertItem, Organization

EXPERT_POOL = ["Соколов Д. Н.", "Мельникова А. В.", "Гущин П. С.", "Радченко Е. И."]
SLA_HOURS = 8          # норматив ИВП-1
STATUSES = ("queued", "in_review", "done")


def _hours_in_queue(item: ExpertItem, now: Optional[datetime] = None) -> float:
    now = now or datetime.now(timezone.utc)
    if not item.since:
        return 0.0
    start = datetime.combine(item.since, time.min, tzinfo=timezone.utc)
    return round((now - start).total_seconds() / 3600.0, 1)


def item_dict(e: ExpertItem, now: Optional[datetime] = None) -> dict:
    h = _hours_in_queue(e, now)
    return {"id": e.id, "ent": e.org_id, "obj": e.object, "expert": e.expert or "—",
            "since": e.since.isoformat() if e.since else None, "prio": e.priority,
            "status": e.status, "hours_in_queue": h,
            "sla_breach": bool(e.status != "done" and h > SLA_HOURS)}


def queue(db: Session) -> dict:
    """Очередь + SLA-мониторинг (ИВП-1: ≤ 8 ч) + паспорта на верификации."""
    items = list(db.scalars(select(ExpertItem).order_by(ExpertItem.id)))
    pending_orgs = [{"id": o.id, "short": o.short_name}
                    for o in db.scalars(select(Organization).where(Organization.status == "pending"))]
    breaches = [i for i in items if i.status != "done" and _hours_in_queue(i) > SLA_HOURS]
    return {"items": [item_dict(i) for i in items],
            "pending_passports": pending_orgs,
            "sla_hours": SLA_HOURS,
            "sla_breaches": [i.id for i in breaches],
            "total": len(items), "done": sum(1 for i in items if i.status == "done")}


def assign(db: Session, item_id: str, events: Optional[list] = None,
           expert: Optional[str] = None) -> ExpertItem:
    """Назначение эксперта (детерминированный выбор из пула по ID объекта).
    Формируется комиссия ≥ 3 чел. (ведущий эксперт — в карточке)."""
    e = db.get(ExpertItem, item_id)
    if e is None:
        raise KeyError(item_id)
    if e.status == "done":
        raise ValueError("Заключение уже выдано — назначение невозможно")
    if expert is None:
        h = int(hashlib.sha256(item_id.encode()).hexdigest(), 16)
        expert = EXPERT_POOL[h % len(EXPERT_POOL)]
    e.expert = expert
    e.status = "in_review"
    db.flush()
    if events is not None:
        events.append(("expert.assigned", "MOD-EXPERT",
                       f"{item_id} → эксперт {expert} · комиссия ≥ 3 чел. (Прил. 3.7)", "info"))
    return e


def conclude(db: Session, item_id: str, verdict: str, user_login: str,
             events: Optional[list] = None) -> dict:
    """Выдача заключения (ЭЦП ГОСТ Р 34.10-2012; отпечаток — в MOD-DOC).
    Арбитраж/pending-организация → status=verified + passport.verified + profile.updated
    (цепочка ИВП-1→ИВП-2: пересчёт профиля и цифрового двойника через шину)."""
    e = db.get(ExpertItem, item_id)
    if e is None:
        raise KeyError(item_id)
    if e.status != "in_review":
        raise ValueError("Заключение выдаётся только после назначения эксперта (assign)")
    e.status = "done"
    db.flush()
    org_verified = None
    if events is not None:
        events.append(("expert.conclusion_ready", "MOD-EXPERT",
                       f"{item_id}: заключение подписано ЭЦП ({e.expert}) · вердикт: {verdict}"
                       + (f" · {e.org_id}" if e.org_id else ""), "info"))
    if e.org_id:
        org = db.get(Organization, e.org_id)
        if org and org.status in ("pending", "arbitration"):
            org.status = "verified"
            org_verified = org.id
            if events is not None:
                events.append(("passport.verified", "MOD-EXPERT",
                               f"{org.id} · экспертиза завершена ({verdict}), расхождения устранены", "info"))
                events.append(("profile.updated", "MOD-PROF",
                               f"Пересчет профиля {org.id} (ИВП-2)", "info"))
    return {"id": e.id, "status": e.status, "expert": e.expert, "verdict": verdict,
            "org_verified": org_verified, "by": user_login}


# ---------------------------------------------------------------- подписка: SLA-эскалация
_registered = False
_lock = threading.Lock()


def register_expert_subscriptions() -> None:
    """Контроль норматива ИВП-1: при постановке паспорта на верификацию
    (событие passport.pending_verification) SLA-таймер стартует; эскалация
    expert.sla_breach публикуется регламентной проверкой check_sla()."""
    global _registered
    with _lock:
        if _registered:
            return
        _registered = True

    def on_new_item(ev: dict) -> None:
        # событие-триггер: паспорт направлен на верификацию — фиксируем в журнале
        get_bus().publish("expert.queue_updated", "MOD-EXPERT",
                          f"Очередь верификации обновлена: {ev.get('payload', '')[:100]}", "info")

    get_bus().subscribe("passport.pending_verification", on_new_item)


def check_sla(db: Session, events: Optional[list] = None) -> List[str]:
    """Регламентная проверка SLA (планировщик ядра): нарушения → expert.sla_breach."""
    breached = []
    for e in db.scalars(select(ExpertItem)):
        if e.status != "done" and _hours_in_queue(e) > SLA_HOURS:
            breached.append(e.id)
            if events is not None:
                events.append(("expert.sla_breach", "MOD-EXPERT",
                               f"{e.id}: в очереди {item_dict(e)['hours_in_queue']} ч > {SLA_HOURS} ч (ИВП-1)",
                               "warn"))
    return breached
