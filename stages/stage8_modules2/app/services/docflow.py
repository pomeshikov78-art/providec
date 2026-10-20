"""MOD-DOC: юридически значимый электронный документооборот.

Реестровые номера «D-YYYY-NNNN», версионность карточек, неизменяемый поток
статусов подписи (движение только вперёд):
    Проект → На подписании → Подписан (ЭЦП) → Утверждён.

ЭЦП: в dev-профиле — sha256-отпечаток карточки (CryptoProvider.digest);
в production (вариант Б) — ГОСТ Р 34.10-2012 через сертифицированное СКЗИ
(КриптоПро/КриптОН): CryptoProvider.sign(). Документы регистрируются в реестре
ядра; отчёты MOD-REPORT и заключения MOD-EXPERT попадают сюда АВТОМАТИЧЕСКИ
по событиям шины (report.generated, expert.conclusion_ready).
"""
from __future__ import annotations

import re
import threading
from datetime import date, datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import session_scope
from ..kernel import audit
from ..kernel.bus import get_bus
from ..kernel.security import CryptoProvider
from ..models import Document

# неизменяемый поток статусов (только вперёд)
FLOW = {"Проект": "На подписании",
        "На подписании": "Подписан (ЭЦП)",
        "Подписан (ЭЦП)": "Утверждён"}
TERMINAL = "Утверждён"
VALID_KINDS = {"Акт", "Отчет", "Заключение", "Договор", "Приказ", "Справка", "Паспорт"}

_RE_REG = re.compile(r"^D-(\d{4})-(\d{4})$")


def _next_registry_id(db: Session) -> str:
    year = datetime.now(timezone.utc).year
    mx = 0
    for d in db.scalars(select(Document)):
        m = _RE_REG.match(d.id or "")
        if m and int(m.group(1)) == year:
            mx = max(mx, int(m.group(2)))
    return f"D-{year}-{mx + 1:04d}"


def doc_dict(d: Document) -> dict:
    return {"id": d.id, "t": d.title, "ent": d.org_id, "kind": d.kind, "sign": d.sign_status,
            "date": d.doc_date.isoformat() if d.doc_date else None,
            "version": d.version, "signature": d.signature,
            "signed_by": d.signed_by,
            "signed_at": d.signed_at.strftime("%Y-%m-%d %H:%M:%S") if d.signed_at else None}


def list_docs(db: Session) -> List[dict]:
    return [doc_dict(d) for d in db.scalars(select(Document).order_by(Document.id))]


def register(db: Session, title: str, org_id: Optional[str], kind: str,
             events: Optional[list] = None, sign_status: str = "Проект",
             doc_date: Optional[date] = None, storage_key: Optional[str] = None) -> Document:
    """Регистрация документа в реестре ядра (номер — следующий по году)."""
    if sign_status not in FLOW and sign_status != TERMINAL:
        raise ValueError(f"Недопустимый стартовый статус: {sign_status}")
    d = Document(id=_next_registry_id(db), title=title, org_id=org_id, kind=kind,
                 sign_status=sign_status, doc_date=doc_date or date.today(),
                 storage_key=storage_key, version=1)
    db.add(d)
    db.flush()
    if events is not None:
        events.append(("doc.registered", "MOD-DOC",
                       f"{d.id}: «{title}» · вид: {kind} · статус: {sign_status}", "info"))
    return d


def _compute_signature(d: Document, signer: str) -> str:
    """Отпечаток подписи. Dev: sha256(CryptoProvider.digest); prod вариант Б:
    ЭЦП ГОСТ Р 34.10-2012 (CryptoProvider.sign через СКЗИ) — до подключения СКЗИ
    деградирует в dev-режим с явной отметкой (graceful degradation, ТЗ п.4.4.2)."""
    data = f"{d.id}|{d.title}|{d.kind}|{d.doc_date}|{d.version}|{signer}".encode("utf-8")
    prov = CryptoProvider()
    try:
        sig = prov.sign(data)
        return "ГОСТ34.10:" + sig.hex()[:48]
    except NotImplementedError:
        return "dev-sha256:" + prov.digest(data).hex()[:32]


def sign(db: Session, doc_id: str, signer: str, events: Optional[list] = None) -> Document:
    """Переход статуса строго вперёд по FLOW; на шаге «Подписан (ЭЦП)» фиксируется
    отпечаток подписи. Обратные переходы запрещены (неизменяемость реестра)."""
    d = db.get(Document, doc_id)
    if d is None:
        raise KeyError(doc_id)
    if d.sign_status not in FLOW:
        raise ValueError(f"Документ в статусе «{d.sign_status}» — подписание завершено (неизменяемо)")
    prev = d.sign_status
    d.sign_status = FLOW[prev]
    d.version += 1
    if d.sign_status == "Подписан (ЭЦП)":
        d.signature = _compute_signature(d, signer)
        d.signed_by = signer
        d.signed_at = datetime.now(timezone.utc)
    if events is not None:
        events.append(("doc.status_changed", "MOD-DOC",
                       f"{d.id}: {prev} → {d.sign_status}" +
                       (f" · подпись {d.signature[:24]}…" if d.signature and d.sign_status == "Подписан (ЭЦП)" else ""),
                       "info"))
    return d


def card(db: Session, doc_id: str, events: Optional[list] = None) -> dict:
    """Карточка документа (просмотр регистрируется — doc.accessed)."""
    d = db.get(Document, doc_id)
    if d is None:
        raise KeyError(doc_id)
    if events is not None:
        events.append(("doc.accessed", "MOD-DOC", f"{doc_id} · просмотр карточки", "info"))
    return doc_dict(d)


# ---------------------------------------------------------------- авторегистрация по событиям шины
_registered = False
_lock = threading.Lock()


def _already_registered(db: Session, title: str) -> bool:
    return db.scalar(select(Document).where(Document.title == title).limit(1)) is not None


def register_doc_subscriptions() -> None:
    """Отчёты MOD-REPORT и заключения MOD-EXPERT → реестр MOD-DOC автоматически."""
    global _registered
    with _lock:
        if _registered:
            return
        _registered = True

    def on_report(ev: dict) -> None:
        payload = ev.get("payload", "")
        title = f"Отчет: {payload.split(':')[0].strip()}"[:300]
        with session_scope() as db:
            if _already_registered(db, title):
                return
            evs: list = []
            register(db, title, None, "Отчет", evs, sign_status="Проект")
            db.commit()
        for t, s, pl, sv in evs:
            get_bus().publish(t, s, pl, sv)

    def on_conclusion(ev: dict) -> None:
        payload = ev.get("payload", "")
        m_vid = re.search(r"\bV\d{2,4}\b", payload)
        m_oid = re.search(r"\bE\d{2,4}\b", payload)
        ref = m_vid.group(0) if m_vid else (m_oid.group(0) if m_oid else payload[:40])
        title = f"Экспертное заключение {ref} (ЭЦП)"
        with session_scope() as db:
            if _already_registered(db, title):
                return
            evs: list = []
            register(db, title, m_oid.group(0) if m_oid else None, "Заключение", evs,
                     sign_status="Подписан (ЭЦП)")
            # заключение выдаётся подписанным: фиксируем отпечаток сразу
            d = db.scalars(select(Document).where(Document.title == title)).first()
            if d and not d.signature:
                d.signature = _compute_signature(d, ev.get("source", "MOD-EXPERT"))
                d.signed_by = "Экспертная комиссия"
                d.signed_at = datetime.now(timezone.utc)
            db.commit()
        for t, s, pl, sv in evs:
            get_bus().publish(t, s, pl, sv)

    get_bus().subscribe("report.generated", on_report)
    get_bus().subscribe("expert.conclusion_ready", on_conclusion)
