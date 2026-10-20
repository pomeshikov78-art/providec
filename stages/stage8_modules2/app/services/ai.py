"""MOD-AI: предиктивная аналитика и рекомендации (ИВП-7).

Серверная реализация прогнозного цикла — детерминированная (воспроизводимая),
без внешних ML-зависимостей; модель «v4.0-srv» (регрессионно-правильный движок):

1. Прогноз технологических разрывов (tech-gap): по каждому направлению компетенций
   (ТЗ п.5.2.2) — средний уровень по отрасли и экстраполяция моделью сходимости
   к порогу технологического суверенитета 75% (шаг 12% разрыва за период);
   confidence = полнота паспортных данных отрасли (средний fill, 0.60–0.95).
2. Риск срыва контрольных точек НИОКР: (TRL_target − TRL_cur)×22 + стадия×2 +
   (индекс риска предприятия − 20) + просрочка/15 дней, кламп 4–92%.
   Детерминированный аналог формулы витрины (случайный джиттер заменён фактором
   просрочки календарного плана — воспроизводимость обязательна для аудита).
3. Рекомендации: правильный движок по 6 правилам (консорциум, форсирование этапа,
   «белое пятно» GEO, стимул MRL 9, полнота паспорта, дефицит испытаний);
   публикуется только confidence ≥ 0.7 (критерий ИВП-7), топ-6.

Прогон регистрируется (run_id AIR-YYYYMMDD-HHMMSS), рекомендации персистентны,
принятие оператором — событие ai.recommendation_accepted + WORM-аудит.
"""
from __future__ import annotations

import threading
from datetime import date, datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AiRecommendation, Maturity, Organization, Project
from ..services import maturity as mat

MODEL_VERSION = "v4.0-srv"
SOVEREIGNTY_THRESHOLD = 75.0   # целевой порог локализации технологий, %
PUBLISH_THRESHOLD = 0.70       # ИВП-7: публикации при confidence ≥ 0.7
MAX_RECS = 6

COMPS = {"sci": "Научно-исследовательские", "des": "Конструкторские",
         "prod": "Производственные", "test": "Испытательные",
         "dig": "Цифровые", "mng": "Управленческие"}

_lock = threading.Lock()
_last_run_seq = 0


def _run_id() -> str:
    """Уникальный ID прогона даже в пределах одной секунды (тесты)."""
    global _last_run_seq
    with _lock:
        _last_run_seq += 1
        return f"AIR-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{_last_run_seq:03d}"


# ---------------------------------------------------------------- 1. tech-gap прогноз
def tech_gap_forecast(db: Session, periods: int = 6) -> dict:
    """Сходимость среднего уровня компетенции к порогу суверенитета (75%)."""
    from ..models import OrgCompetency
    rows = list(db.scalars(select(OrgCompetency)))
    orgs = list(db.scalars(select(Organization)))
    avg_fill = 0.0
    if orgs:
        fills = []
        for o in orgs:
            f = mat.section_fill(db, o.id)
            fills.append(sum(f) / len(f) if f else 0)
        avg_fill = sum(fills) / len(fills)
    conf = round(min(0.95, max(0.60, 0.55 + avg_fill / 100 * 0.4)), 2)
    gaps = []
    for key, name in COMPS.items():
        levels = [r.level for r in rows if r.comp == key]
        if not levels:
            continue
        cur = round(sum(levels) / len(levels), 1)
        prog = [cur]
        v = cur
        for _ in range(periods):
            v = v + (SOVEREIGNTY_THRESHOLD - v) * 0.12 if v < SOVEREIGNTY_THRESHOLD \
                else min(99.0, v + 0.4)
            prog.append(round(v, 1))
        gaps.append({"key": key, "n": name, "cur": cur, "prog": prog, "conf": conf,
                     "sovereign_by": next((i for i, x in enumerate(prog) if x >= SOVEREIGNTY_THRESHOLD), None)})
    return {"model": MODEL_VERSION, "threshold": SOVEREIGNTY_THRESHOLD,
            "periods": periods, "gaps": gaps,
            "as_of": date.today().isoformat()}


# ---------------------------------------------------------------- 2. риск срыва этапов
def failure_risk(db: Session, top: int = 6) -> List[dict]:
    today = date.today()
    out = []
    for p in db.scalars(select(Project)):
        org = db.get(Organization, p.org_id)
        if not org:
            continue
        overdue = max(0, (today - p.deadline).days) if p.deadline else 0
        trl_gap = (p.trl_target or 0) - (p.trl_current or 0)
        r = trl_gap * 22 + p.lc_stage * 2 + (org.risk_idx - 20) + overdue // 15
        r = max(4, min(92, round(r)))
        out.append({"id": p.id, "name": p.name, "org": org.short_name, "risk": r,
                    "factors": {"trl_gap": trl_gap, "stage": p.lc_stage,
                                "risk_idx": org.risk_idx, "overdue_days": overdue}})
    out.sort(key=lambda x: (-x["risk"], x["id"]))
    return out[:top]


# ---------------------------------------------------------------- 3. рекомендации (правильный движок)
def _avg(seq: List[float]) -> float:
    return sum(seq) / len(seq) if seq else 0.0


def recommendations(db: Session) -> List[dict]:
    from ..models import OrgCompetency
    recs: List[dict] = []
    orgs = list(db.scalars(select(Organization).order_by(Organization.id)))
    by_id = {o.id: o for o in orgs}

    # R1 · консорциум: две организации с высокой общей компетенцией без связи (MOD-COOP)
    comp_rows = list(db.scalars(select(OrgCompetency)))
    levels = {}
    for r in comp_rows:
        levels.setdefault(r.comp, {})[r.org_id] = r.level
    best = None
    for key, per_org in levels.items():
        ids = sorted(per_org, key=lambda i: -per_org[i])
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = ids[i], ids[j]
                if per_org[a] < 60 or per_org[b] < 60:
                    continue
                oa, ob = by_id.get(a), by_id.get(b)
                if not oa or not ob:
                    continue
                if b in (oa.links or "").split(",") or a in (ob.links or "").split(","):
                    continue
                score = min(per_org[a], per_org[b])
                if best is None or score > best[0]:
                    best = (score, oa, ob, key)
    if best:
        score, oa, ob, key = best
        recs.append({"t": f"Объединить {oa.short_name} и {ob.short_name} в консорциум по "
                          f"направлению «{COMPS[key]}» (устранение дублирования НИОКР)",
                     "m": "MOD-COOP", "conf": round(min(0.95, 0.5 + score / 250), 2)})

    # R2 · форсирование этапа: максимальная просрочка календарного плана (MOD-NIOKR)
    today = date.today()
    worst = None
    for p in db.scalars(select(Project)):
        if not p.deadline:
            continue
        overdue = (today - p.deadline).days
        if overdue > 30 and (worst is None or overdue > worst[1]):
            worst = (p, overdue)
    if worst:
        p, overdue = worst
        recs.append({"t": f"Форсировать этап {p.lc_stage} проекта {p.id}: отставание "
                          f"{overdue} дн. от календарного плана",
                     "m": "MOD-NIOKR", "conf": round(min(0.95, 0.6 + overdue / 500), 2)})

    # R3 · «белое пятно»: ФО с числом организаций ниже медианы (MOD-GEO, ИВП-GEO-3)
    regions: dict = {}
    for o in orgs:
        regions.setdefault(o.region, []).append(o)
    if regions:
        counts = sorted(len(v) for v in regions.values())
        median = counts[len(counts) // 2]
        spots = sorted((r for r, v in regions.items() if len(v) < median),
                       key=lambda r: len(regions[r]))
        if spots:
            recs.append({"t": f"Разместить НИО научно-исследовательского профиля в "
                              f"{spots[0]} («белое пятно» геоаналитики: "
                              f"{len(regions[spots[0]])} орг. при медиане {median})",
                         "m": "MOD-GEO", "conf": 0.76})

    # R4 · стимул: верифицированная организация с MRL ≥ 9 (MOD-STIM, Прил. 1.6)
    for o in orgs:
        m = db.get(Maturity, o.id)
        if m and m.mrl >= 9 and o.status == "verified":
            recs.append({"t": f"Применить стимул к {o.short_name}: опережающее достижение "
                              f"MRL {m.mrl} (технологическая готовность производства)",
                         "m": "MOD-STIM", "conf": 0.90})
            break

    # R5 · полнота паспорта: pending-организация с наименьшей полнотой (MOD-PASS, ИВП-1)
    cands = []
    for o in orgs:
        if o.status != "pending":
            continue
        f = mat.section_fill(db, o.id)
        avg = _avg(f)
        if avg < 95:
            weak = sorted(range(len(f)), key=lambda i: f[i])[:2]
            cands.append((avg, o, [i + 1 for i in weak]))
    if cands:
        cands.sort(key=lambda x: (x[0], x[1].id))
        avg, o, weak = cands[0]
        recs.append({"t": f"Повысить полноту разделов {' и '.join(str(w) for w in weak)} "
                          f"паспорта {o.short_name} ({avg:.0f}% < 95%) до верификации",
                     "m": "MOD-PASS", "conf": 0.95})

    # R6 · дефицит испытательных мощностей (MOD-PORTF, прогноз по компетенции test)
    test_levels = [r.level for r in comp_rows if r.comp == "test"]
    test_orgs = [o for o in orgs if o.org_type == "test"]
    avg_test = _avg(test_levels)
    if avg_test and avg_test < 65 and test_orgs:
        names = "/".join(o.short_name for o in test_orgs[:2])
        recs.append({"t": f"Прогноз: дефицит испытательных мощностей (средний уровень "
                          f"компетенции {avg_test:.0f} < 65) — загрузить {names} на 85%",
                     "m": "MOD-PORTF", "conf": round(min(0.95, max(0.70, 0.6 + (65 - avg_test) / 100)), 2)})

    published = [r for r in recs if r["conf"] >= PUBLISH_THRESHOLD]
    published.sort(key=lambda r: (-r["conf"], r["t"]))
    return published[:MAX_RECS]


# ---------------------------------------------------------------- прогон цикла (ИВП-7)
def run_cycle(db: Session, events: Optional[list] = None, author: str = "scheduler") -> dict:
    """Прогнозный цикл: расчёт → персистентные рекомендации → событие в шину."""
    run_id = _run_id()
    tg = tech_gap_forecast(db)
    risks = failure_risk(db)
    recs = recommendations(db)
    for r in recs:
        db.add(AiRecommendation(run_id=run_id, text=r["t"], module=r["m"],
                                confidence=r["conf"], status="published"))
    db.flush()
    if events is not None:
        events.append(("ai.recommendations_ready", "MOD-AI",
                       f"Прогнозный цикл {run_id} завершен: {len(tg['gaps'])} tech-gap, "
                       f"{len(risks)} рисков этапов, {len(recs)} рекомендаций (conf ≥ {PUBLISH_THRESHOLD})",
                       "info"))
    return {"run_id": run_id, "model": MODEL_VERSION, "author": author,
            "tech_gaps": tg, "fail_risk": risks, "recommendations": recs,
            "as_of": date.today().isoformat()}


def rec_dict(r: AiRecommendation) -> dict:
    return {"rid": r.id, "run_id": r.run_id, "t": r.text, "m": r.module,
            "conf": r.confidence, "status": r.status,
            "decided_by": r.decided_by,
            "decided_at": r.decided_at.strftime("%Y-%m-%d %H:%M:%S") if r.decided_at else None}


def latest_run(db: Session) -> dict:
    """Последний прогон: рекомендации из БД + живой пересчёт прогнозов (детерминирован)."""
    last = db.scalars(select(AiRecommendation).order_by(AiRecommendation.id.desc()).limit(1)).first()
    recs: List[dict] = []
    run_id = None
    if last:
        run_id = last.run_id
        recs = [rec_dict(r) for r in db.scalars(
            select(AiRecommendation).where(AiRecommendation.run_id == run_id)
            .order_by(AiRecommendation.confidence.desc(), AiRecommendation.id))]
    return {"run_id": run_id, "model": MODEL_VERSION, "recommendations": recs,
            "tech_gaps": tech_gap_forecast(db), "fail_risk": failure_risk(db)}


def accept(db: Session, rid: int, user_login: str, events: Optional[list] = None) -> AiRecommendation:
    r = db.get(AiRecommendation, rid)
    if r is None:
        raise KeyError(rid)
    if r.status != "published":
        raise ValueError(f"Рекомендация уже в статусе «{r.status}»")
    r.status = "accepted"
    r.decided_by = user_login
    r.decided_at = datetime.now(timezone.utc)
    db.flush()
    if events is not None:
        events.append(("ai.recommendation_accepted", "MOD-AI",
                       f"Рекомендация {rid} принята оператором {user_login}: {r.text[:80]}", "info"))
    return r
