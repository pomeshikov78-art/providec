"""Слой данных: SQLAlchemy 2.0 (ТЗ п.4.2).

Dev-профиль: SQLite (файл). Production: Postgres Pro + PostGIS — DATABASE_URL
переключается конфигурацией без изменения кода (требование ТЗ п.4.4.2).
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        s = settings()
        kwargs = {"echo": s.db_echo, "future": True}
        if s.database_url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_engine(s.database_url, **kwargs)
        if s.database_url.startswith("sqlite"):
            @event.listens_for(_engine, "connect")
            def _fk_on(dbapi_conn, _):
                dbapi_conn.execute("PRAGMA foreign_keys=ON")
    return _engine


def get_session_factory() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return _SessionLocal


@contextmanager
def session_scope() -> Iterator[Session]:
    """Транзакционная сессия: commit при успехе, rollback при ошибке."""
    db = get_session_factory()()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db() -> Iterator[Session]:
    """FastAPI-зависимость: сессия на запрос."""
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Создание схемы (dev). В production — миграции Alembic поверх db/schema.sql."""
    from . import models  # noqa: F401 — регистрация мапперов
    Base.metadata.create_all(bind=get_engine())


def reset_engine() -> None:
    """Для тестов: сброс движка (смена DATABASE_URL)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
