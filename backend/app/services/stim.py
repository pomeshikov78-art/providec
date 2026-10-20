"""MOD-STIM: стимулы и санкции (Приложение 1.6 к ТЗ).

Применение мер — автоматически по событиям шины ядра (event-driven, без прямых
межмодульных вызовов — принцип «Ядро + Модули»):
  niokr.gate_decision (NO-GO ×2)  → санкция «Ограничение новых заявок»;
  passport.verified               → стимул «Публикация в отраслевом каталоге компетенций»,
                                     при TRL ≥ 9 дополнительно «Статус технологического лидера»;
  kpi.threshold_breached          → санкция «Эскалация отраслевым органам (L2)».

Каждая мера — запись в БД (append-only реестр), событие ``stim.applied`` и
WORM-аудит. RACI (Приложение 4.4): утверждает субъект с кодом «A» (L2/L6/L7 —
политика ``stim.write``), исполнение — «R», информирование — «I».
"""
from __future__ import annotations

import re
import threading
from datetime import date
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import session_scope
from ..kernel import audit
from ..kernel.bus import get_bus
from ..models import Maturity, Organization, Project, ProjectGate, Stim

STIM_CATALOG = [
    "Приоритетное софинансирование НИОКР (+квота)",
    "Ускоренная верификация паспорта (24 ч)",
    "Статус «Технологический лидер отрасли»",
    "Грант на формирование задела (этап 3)",
    "Публикация в отраслевом каталоге компетенций",
]
SANCTION_CATALOG = [
    "Ограничение новых заявок (после No-Go ×2)",
    "Предупреждение о неполноте паспорта",
    "Повторная верификация данных (арбитраж)",
    "Понижение приоритета в портфеле",
    "Эскалация отраслевым органам (L2)",
]

_RE_PID = re.compile(r"\bP\d{2,4}\b")
_RE_OID = re.compile(r"\bE\d{2,4}\b")


# ---------------------------------------------------------------- реестр мер
def _next_id(db: Session) -> str:
    ids = [s.id for s in db.scalars(select(Stim))]
    mx = max((int(i[1:]) for i in ids if i and i[0] == "S" and i[1:].isdigit()), default=0)
    return f"S{mx + 1:02d}"


def stim_dict(s: Stim) -> dict:
    return {"id": s.id, "ent": s.org_id, "kind": "Стимул" if s.kind == "stim" else "Санкция",
            "t": s.title, "base": s.basis, "st": s.status,
            "date": s.doc_date.isoformat() if s.doc_date else None}


def list_stims(db: Session) -> List[dict]:
    return [stim_dict(s) for s in db.scalars(select(Stim).order_by(Stim.id))]


def exists_with_basis(db: Session, basis: str) -> bool:
    """Идемпотентность: мера с таким основанием уже зарегистрирована."""
    return db.scalar(select(Stim).where(Stim.basis == basis).limit(1)) is not None


def create(db: Session, org_id: Optional[str], kind: str, title: str, basis: str,
           events: Optional[list] = None, author: str = "system") -> Stim:
    """Регистрация меры. kind: stim | sanction. События добавляются в список —
    публикация строго после commit (паттерн ядра против deadlock SQLite)."""
    if kind not in ("stim", "sanction"):
        raise ValueError("kind: stim | sanction")
    s = Stim(id=_next_id(db), org_id=org_id, kind=kind, title=title, basis=basis,
             doc_date=date.today(), status="Действует")
    db.add(s)
    db.flush()
    if events is not None:
        who = org_id or "отрасль"
        events.append(("stim.applied", "MOD-STIM",
                       f"{s.id}: {'Стимул' if kind == 'stim' else 'Санкция'} · {title} · {who} · основание: {basis}",
                       "info" if kind == "stim" else "warn"))
    return s


def set_status(db: Session, stim_id: str, status: str) -> Stim:
    s = db.get(Stim, stim_id)
    if s is None:
        raise KeyError(stim_id)
    if status not in ("Действует", "На контроле", "Снята"):
        raise ValueError("Статусы: Действует | На контроле | Снята")
    s.status = status
    return s


# ---------------------------------------------------------------- автоматические правила (Прил. 1.6)
def apply_auto_rules(db: Session, ev_type: str, payload: str, events: list) -> List[Stim]:
    """Реакция MOD-STIM на события шины. Возвращает созданные меры (для аудита)."""
    created: List[Stim] = []
    if ev_type == "niokr.gate_decision" and "NO-GO" in payload:
        m = _RE_PID.search(payload)
        if m:
            pid = m.group(0)
            p = db.get(Project, pid)
            nogos = len(list(db.scalars(select(ProjectGate).where(
                ProjectGate.project_id == pid, ProjectGate.decision == "no-go"))))
            if p and nogos >= 2:
                basis = f"{pid}: No-Go ×{nogos} (решения контрольных точек)"
                if not exists_with_basis(db, basis):
                    created.append(create(db, p.org_id, "sanction",
                                          SANCTION_CATALOG[0], basis, events))
    elif ev_type == "passport.verified":
        m = _RE_OID.search(payload)
        if m:
            oid = m.group(0)
            org = db.get(Organization, oid)
            if org:
                basis = f"passport.verified · {oid} · верификация завершена"
                if not exists_with_basis(db, basis):
                    created.append(create(db, oid, "stim", STIM_CATALOG[4], basis, events))
                mat = db.get(Maturity, oid)
                if mat and mat.trl >= 9:
                    basis2 = f"passport.verified · {oid} · TRL {mat.trl} ≥ 9"
                    if not exists_with_basis(db, basis2):
                        created.append(create(db, oid, "stim", STIM_CATALOG[2], basis2, events))
    elif ev_type == "kpi.threshold_breached":
        basis = f"kpi.threshold_breached · {payload[:110]}"
        if not exists_with_basis(db, basis):
            created.append(create(db, None, "sanction", SANCTION_CATALOG[4], basis, events))
    return created


# ---------------------------------------------------------------- подписки на шину ядра
_registered = False
_lock = threading.Lock()


def register_stim_subscriptions() -> None:
    """Регистрация обработчиков шины (один раз на процесс ядра)."""
    global _registered
    with _lock:
        if _registered:
            return
        _registered = True

    def _handler(ev: dict) -> None:
        with session_scope() as db:
            evs: list = []
            created = apply_auto_rules(db, ev["type"], ev.get("payload", ""), evs)
            if not created:
                return
            db.commit()   # фиксация ДО публикации (паттерн ядра)
        for t, s, pl, sv in evs:
            get_bus().publish(t, s, pl, sv)
        for c in created:
            audit.record("Автоматическое применение меры (MOD-STIM)",
                         f"{c.id} · {c.title} · {c.org_id or 'отрасль'}", "Успех",
                         user="system", role="CORE:Bus")

    for et in ("niokr.gate_decision", "passport.verified", "kpi.threshold_breached"):
        get_bus().subscribe(et, _handler)
