"""MOD-KPI: мониторинг целевых показателей системы (ТЗ п.2.3, ИВП-6).

Классы показателей:
- ``calc`` — вычисляются из реальных данных СУБД при пересчёте:
    KPI-1 Охват        = организации с профилем зрелости / всего организаций × 100;
    KPI-3 Точность     = верифицированные организации / организации с профилем × 100;
    KPI-6 Подтв. проекты = проекты верифицированных организаций / всего проектов × 100;
    KPI-7 Дедупликация = организации с кооперационными связями / всего × 100
            (снижение дублирующих НИОКР через консорциумы, ИВП-4).
- ``telemetry`` — измеряются службами модулей в процессе работы и накапливаются
  в памяти процесса (MOD-REPORT → KPI-4 время отчёта, MOD-GEO → KPI-8 отклик
  геоаналитики); применяются при следующем пересчёте (среднее последних замеров).
  Такой приём исключает конкурирующие записи в SQLite из обработчиков запросов.

Отклонение от порога → событие ``kpi.threshold_breached`` (публикуется роутером
после commit), которое запускает автоматические правила MOD-STIM (эскалация).
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Kpi, Maturity, Organization, Project, utcnow

HISTORY_CAP = 12   # глубокая история — 12 месяцев (как в витрине прототипа)

# ------------------------------------------------------------- телеметрия (in-process)
_TELEMETRY: Dict[str, List[float]] = defaultdict(list)


def record_telemetry(code: str, value: float) -> None:
    """Замер от служб модулей (KPI-4 отчёты, KPI-8 гео). Потокобезопасно enough: GIL + append."""
    seq = _TELEMETRY[code]
    seq.append(round(float(value), 2))
    if len(seq) > 20:
        del seq[:-20]


def pending_telemetry(code: str) -> Optional[float]:
    seq = _TELEMETRY.get(code)
    return round(sum(seq) / len(seq), 2) if seq else None


def reset_telemetry(code: Optional[str] = None) -> None:
    """Сброс накопленных замеров (регламентное задание / изоляция тестов)."""
    if code is None:
        _TELEMETRY.clear()
    else:
        _TELEMETRY.pop(code, None)


# ------------------------------------------------------------- формулы calc-показателей
def _pct(part: int, total: int) -> float:
    return round(part / total * 100, 1) if total else 0.0


def calc_coverage(db: Session) -> float:
    """KPI-1: охват предприятий отрасли системой (есть профиль зрелости)."""
    total = db.scalar(select(func.count()).select_from(Organization)) or 0
    withm = db.scalar(select(func.count()).select_from(Maturity)) or 0
    return _pct(withm, total)


def calc_accuracy(db: Session) -> float:
    """KPI-3: точность оценки TRL/MRL/IRL — доля верифицированных профилей
    (верификация = подтверждение оценки экспертной документальной базой, ИВП-1)."""
    total = db.scalar(select(func.count()).select_from(Maturity)) or 0
    ver = db.scalar(select(func.count()).select_from(Organization)
                    .where(Organization.status == "verified")) or 0
    return _pct(ver, total)


def calc_verified_projects(db: Session) -> float:
    """KPI-6: проекты с подтвержденной зрелостью (организация-исполнитель верифицирована)."""
    projects = list(db.scalars(select(Project)))
    if not projects:
        return 0.0
    ok = 0
    for p in projects:
        o = db.get(Organization, p.org_id)
        if o and o.status == "verified":
            ok += 1
    return _pct(ok, len(projects))


def calc_dedup(db: Session) -> float:
    """KPI-7: снижение дублирующих НИОКР — охват кооперационными связями
    (организация участвует ≥ 1 консорциумом ребре графа MOD-COOP/MOD-GEO)."""
    orgs = list(db.scalars(select(Organization)))
    if not orgs:
        return 0.0
    linked = sum(1 for o in orgs if (o.links or "").strip())
    return _pct(linked, len(orgs))


CALC: Dict[str, Callable[[Session], float]] = {
    "KPI-1": calc_coverage,
    "KPI-3": calc_accuracy,
    "KPI-6": calc_verified_projects,
    "KPI-7": calc_dedup,
}


# ------------------------------------------------------------- сериализация / проверки
def is_met(k: Kpi) -> bool:
    return k.current >= k.target if k.direction == "up" else k.current <= k.target


def _hist(k: Kpi) -> List[float]:
    try:
        return json.loads(k.history or "[]")
    except json.JSONDecodeError:
        return []


def kpi_dict(k: Kpi) -> dict:
    return {"code": k.code, "n": k.name, "cur": k.current, "target": k.target,
            "unit": k.unit, "dir": k.direction, "fmt": k.fmt, "source": k.source,
            "met": is_met(k), "hist": _hist(k),
            "updated": k.updated_at.strftime("%Y-%m-%d %H:%M:%S") if k.updated_at else None}


def list_kpis(db: Session) -> List[dict]:
    return [kpi_dict(k) for k in db.scalars(select(Kpi).order_by(Kpi.code))]


def period_label(now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f'{"I II III IV".split()[(now.month - 1) // 3]} квартал {now.year}'


# ------------------------------------------------------------- пересчёт
def recalculate(db: Session, events: Optional[list] = None) -> dict:
    """Регламентный пересчёт (планировщик ядра / оператор). Обновляет calc-показатели
    из БД, применяет накопленную телеметрию, двигает историю, выявляет отклонения.

    События НЕ публикуются здесь (паттерн ядра: сначала commit, затем шина) —
    роутер добавляет их в список ``events`` и публикует после фиксации транзакции.
    """
    items: List[Kpi] = list(db.scalars(select(Kpi).order_by(Kpi.code)))
    breached: List[dict] = []
    for k in items:
        new_val: Optional[float] = None
        if k.source == "calc" and k.code in CALC:
            new_val = CALC[k.code](db)
        elif k.source == "telemetry":
            new_val = pending_telemetry(k.code)
        if new_val is not None:
            k.current = new_val
        hist = _hist(k)
        hist.append(k.current)
        if len(hist) > HISTORY_CAP:
            hist = hist[-HISTORY_CAP:]
        k.history = json.dumps(hist, ensure_ascii=False)
        k.updated_at = utcnow()
        if not is_met(k):
            breached.append({"code": k.code, "n": k.name, "cur": k.current,
                             "target": k.target, "dir": k.direction, "fmt": k.fmt})
    if events is not None:
        for b in breached:
            events.append(("kpi.threshold_breached", "MOD-KPI",
                           f"Внимание: {b['code']} «{b['n']}» = {b['cur']} "
                           f"(цель {b['fmt']}) — контроль динамики", "warn"))
    return {"period": period_label(), "total": len(items), "breached": breached,
            "items": [kpi_dict(k) for k in items]}
