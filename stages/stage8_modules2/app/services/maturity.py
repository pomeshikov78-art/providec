"""MOD-PROF: расчет зрелости (TRL/MRL/IRL), индекса ИТЗ, разрывов и бенчмарков отрасли.

Алгоритмы перенесены из прототипа v8.0.0 (валидированы на демо-данных):
  * I = (0,4·TRL/9 + 0,35·MRL/10 + 0,25·IRL/9)×100   (Приложение 3.5 к ТЗ);
  * разрывы: слабые измерения радара, отставание MRL/IRL от TRL, разделы ниже порога, ИНН;
  * бенчмарки: средние по отрасли и по типу организации.
"""
from __future__ import annotations

from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Maturity, OrgRadar, Organization, PassportValue, PassportField

RADAR_DIMS = ["Наука", "Технологии", "НИОКР", "Производство", "Испытания", "Кадры", "Цифровизация"]


def maturity_index(trl: int, mrl: int, irl: int) -> float:
    """Интегральный индекс зрелости (Прил. 3.5). Эталон ТЗ: (6,5,4) → 55.3."""
    return round((0.4 * trl / 9.0 + 0.35 * mrl / 10.0 + 0.25 * irl / 9.0) * 100, 1)


def maturity_status(index_i: float) -> str:
    if index_i >= 80:
        return "Лидер"
    if index_i >= 60:
        return "Высокий"
    if index_i >= 40:
        return "Средний"
    return "Начальный"


def section_fill(db: Session, org_id: str) -> List[int]:
    """Полнота 12 разделов паспорта, % (по факту заполненных значений полей)."""
    counts: Dict[int, List[int]] = {}
    fields = list(db.scalars(select(PassportField)))
    values = {v.field_id: v.value for v in db.scalars(
        select(PassportValue).where(PassportValue.org_id == org_id))}
    for f in fields:
        tot, filled = counts.get(f.section_n, [0, 0])
        tot += 1
        if values.get(f.id):
            filled += 1
        counts[f.section_n] = [tot, filled]
    return [round(counts.get(n, [1, 0])[1] / max(counts.get(n, [1, 0])[0], 1) * 100) for n in range(1, 13)]


def fill_total(fills: List[int]) -> int:
    return round(sum(fills) / len(fills)) if fills else 0


def org_gaps(db: Session, org: Organization, mat: Maturity | None) -> List[str]:
    gaps: List[str] = []
    radar = {r.dim: r.val for r in db.scalars(select(OrgRadar).where(OrgRadar.org_id == org.id))}
    dims = [radar.get(i, 0) for i in range(1, 8)]
    if dims:
        ordered = sorted(zip(RADAR_DIMS, dims), key=lambda x: x[1])
        if ordered[0][1] < 55:
            gaps.append(f'Критический разрыв: «{ordered[0][0]}» = {ordered[0][1]}/100 (бенчмарк ≥ 55)')
        if len(ordered) > 1 and ordered[1][1] < 65:
            gaps.append(f'Разрыв: «{ordered[1][0]}» = {ordered[1][1]}/100 (бенчмарк ≥ 65)')
    if mat:
        if mat.mrl < mat.trl:
            gaps.append(f"MRL ({mat.mrl}) отстает от TRL ({mat.trl}): риск неготовности производства к серии")
        if mat.irl < mat.trl - 1:
            gaps.append(f"IRL ({mat.irl}) отстает от TRL ({mat.trl}): слабая промышленная интеграция")
    fills = section_fill(db, org.id)
    from ..models import PassportSection
    th = {s.n: s.threshold for s in db.scalars(select(PassportSection))}
    for i, fv in enumerate(fills, start=1):
        if fv < th.get(i, 90):
            gaps.append(f"Паспорт: раздел {i} — полнота {fv}% ниже порога {th.get(i, 90)}% (Прил. 2.14)")
    from .validators import inn_valid
    if not inn_valid(org.inn):
        gaps.append(f"ИНН {org.inn}: контрольная сумма не сходится (расхождение с ЕГРЮЛ)")
    if not gaps:
        gaps.append("Критических разрывов не выявлено — профиль соответствует бенчмаркам отрасли")
    return gaps


def benchmarks(db: Session) -> dict:
    """Бенчмарки отрасли: средние радаров, зрелости и полноты (по всем и по типам)."""
    orgs = list(db.scalars(select(Organization)))
    radars = {(r.org_id, r.dim): r.val for r in db.scalars(select(OrgRadar))}
    radar_sum = [0] * 7
    radar_cnt = [0] * 7
    for (oid, dim), val in radars.items():
        if 1 <= dim <= 7:
            radar_sum[dim - 1] += val
            radar_cnt[dim - 1] += 1
    dims = [round(radar_sum[i] / radar_cnt[i]) if radar_cnt[i] else 0 for i in range(7)]
    mats = {m.org_id: m for m in db.scalars(select(Maturity))}
    def avg(pred):
        sel = [o for o in orgs if pred(o)]
        k = max(len(sel), 1)
        return {
            "trl": round(sum(mats[o.id].trl for o in sel if o.id in mats) / k, 1),
            "mrl": round(sum(mats[o.id].mrl for o in sel if o.id in mats) / k, 1),
            "irl": round(sum(mats[o.id].irl for o in sel if o.id in mats) / k, 1),
        }
    return {"dims": dims, "orgs_total": len(orgs), "all": avg(lambda o: True),
            "by_type": {t: avg(lambda o, t=t: o.org_type == t) for t in ("ent", "nio", "test")}}
