"""Начальное наполнение БД (seed): ядро, справочники, демо-пользователи.

Данные предметной области (100 организаций, 92 поля паспорта, проекты, риски)
загружаются из app/data/seed_data.json — экспорт из прототипа v8.0.0
(Единый источник: интерактивный макет, согласованный с Заказчиком).
"""
from __future__ import annotations

import json
import os
from datetime import date

from sqlalchemy import func, select

from .config import settings
from .db import session_scope
from .kernel import audit, registry
from .kernel.iam import generate_totp_secret, hash_password
from .models import (AssprPackage, Document, ExpertItem, IamPolicy, Integration,
                     Kpi, Maturity, OrgCompetency, OrgRadar, Organization, PassportField,
                     PassportSection, PassportValue, Project, Risk, Stim, Twin, User)

DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "seed_data.json")

POLICIES = [
    ("*", "view", "*", "allow", None, "L0–L7: просмотр согласно роли"),
    ("L7", "admin", "*", "allow", None, "Управление конфигурацией, модулями, импортом, хранилищем"),
    ("L6", "admin", "*", "allow", None, "Делегированные полномочия"),
    ("L1", "gate", "*", "allow", None, "Госорганы: решения контрольных точек"),
    ("L2", "gate", "*", "allow", None, "Отраслевые органы"),
    ("L5", "gate", "*", "allow", None, "НИОКР/испытания"),
    ("L5", "expert.approve", "*", "allow", None, "Экспертиза и верификация"),
    ("L7", "expert.approve", "*", "allow", None, None),
    ("L2", "report.run", "*", "allow", None, None),
    ("L5", "report.run", "*", "allow", None, None),
    ("L7", "report.run", "*", "allow", None, None),
    ("L2", "expert.assign", "*", "allow", None, "Формирование экспертных групп (≥ 3 чел.)"),
    ("L5", "expert.assign", "*", "allow", None, None),
    ("L7", "expert.assign", "*", "allow", None, None),
    ("L2", "ai.run", "*", "allow", None, "Запуск прогнозного цикла ИВП-7"),
    ("L5", "ai.run", "*", "allow", None, None),
    ("L7", "ai.run", "*", "allow", None, None),
    ("L1", "ai.accept", "*", "allow", None, "Принятие ИИ-рекомендаций"),
    ("L2", "ai.accept", "*", "allow", None, None),
    ("L5", "ai.accept", "*", "allow", None, None),
    ("L7", "ai.accept", "*", "allow", None, None),
    ("L1", "doc.sign", "*", "allow", None, "Подписание/регистрация документов MOD-DOC"),
    ("L2", "doc.sign", "*", "allow", None, None),
    ("L5", "doc.sign", "*", "allow", None, None),
    ("L7", "doc.sign", "*", "allow", None, None),
    ("L2", "stim.write", "*", "allow", None, "Утверждение мер (RACI: код «A»)"),
    ("L6", "stim.write", "*", "allow", None, None),
    ("L7", "stim.write", "*", "allow", None, None),
    ("L2", "kpi.recalc", "*", "allow", None, "Регламентный пересчет KPI"),
    ("L6", "kpi.recalc", "*", "allow", None, None),
    ("L7", "kpi.recalc", "*", "allow", None, None),
    ("L4", "org.write", "*", "allow", '{"org_eq_subject": true}', "ABAC: только собственное предприятие"),
    ("L4", "admin", "*", "deny", None, "Предприятие не управляет конфигурацией"),
    ("L0", "org.write", "*", "deny", None, "Внешний пользователь — только просмотр"),
    ("L3", "org.write", "*", "deny", None, "Партнеры/инвесторы — только просмотр"),
]

DEMO_USERS = [
    # login, fio, role, org_id, password
    ("admin", "Крылов И. А. (администратор)", "L7", None, "tc-admin-2026"),
    ("analyst", "Соколова Д. Н. (аналитик)", "L5", None, "tc-analyst-2026"),
    ("regulator", "Отраслевой орган (оператор)", "L2", None, "tc-reg-2026"),
    ("sarmat", "Предприятие E14 «Сармат-Электроника»", "L4", "E14", "tc-org-2026"),
    ("guest", "Внешний пользователь", "L0", None, "tc-guest-2026"),
]

INTEGRATIONS = [
    ("EGRUL", "ЕГРЮЛ (ФНС России)", "Государственные ИС", "API/Файл", "По запросу", True, "manual"),
    ("GISP", "ГИСП (Минпромторг)", "Государственные ИС", "API", "1 раз в сутки", True, "manual"),
    ("FNS", "ФНС открытые данные", "Государственные ИС", "API", "1 раз в квартал", True, "manual"),
    ("ROSPATENT", "Роспатент (ФИПС)", "Государственные ИС", "API", "1 раз в неделю", True, "manual"),
    ("REPO", "Реестр российского ПО", "Государственные ИС", "API", "1 раз в месяц", True, "manual"),
    ("REP", "Реестр РЭП", "Государственные ИС", "API", "1 раз в месяц", True, "manual"),
    ("EIS", "ЕИС Закупки", "Государственные ИС", "API", "1 раз в сутки", True, "manual"),
    ("OPP", "Реестр ОПП", "Государственные ИС", "API", "1 раз в месяц", True, "manual"),
    ("NIOKR_CIV", "Реестр НИОКР (гражданский)", "Отраслевые и научные", "API/Файл", "1 раз в месяц", True, "manual"),
    ("NIOKR_OPK", "Реестр НИОКР (ОПК)", "Отраслевые и научные", "Защищённый канал", "По регламенту", True, "exchange"),
    ("RINC", "РИНЦ", "Отраслевые и научные", "API", "1 раз в месяц", True, "manual"),
    ("ROSACC", "Росаккредитация (лаборатории)", "Отраслевые и научные", "API", "1 раз в квартал", True, "manual"),
    ("CERTS", "Реестр сертификатов", "Отраслевые и научные", "API", "1 раз в квартал", True, "manual"),
    ("GOST", "База стандартов ГОСТ", "Отраслевые и научные", "API/Файл", "1 раз в месяц", True, "manual"),
    ("WIPO", "WIPO PATENTSCOPE", "Международные (вариант А)", "API", "1 раз в неделю", True, "unavailable"),
    ("EPO", "Espacenet (EPO)", "Международные (вариант А)", "API", "1 раз в неделю", True, "unavailable"),
    ("USPTO", "USPTO", "Международные (вариант А)", "API", "1 раз в неделю", True, "unavailable"),
    ("SCOPUS", "Scopus / Web of Science", "Международные (вариант А)", "API", "1 раз в месяц", True, "unavailable"),
    ("IEEE", "IEEE Xplore", "Международные (вариант А)", "API", "1 раз в месяц", True, "unavailable"),
    ("GARTNER", "Gartner / IDC", "Международные (вариант А)", "API (платно)", "По подписке", True, "unavailable"),
    ("YAMAPS", "Яндекс.Карты API", "Геоинформационные", "REST API", "Реальное время", True, "unavailable"),
    ("GIS2", "2ГИС API", "Геоинформационные", "REST API", "Реальное время", True, "unavailable"),
    ("KOSMOS", "Космоснимки", "Геоинформационные", "WMS/WMTS", "По запросу", True, "unavailable"),
    ("OSM", "OpenStreetMap (локальные тайлы)", "Геоинформационные", "OSM API", "Ежеквартально", True, "exchange"),
    ("EGRN", "Росреестр (ЕГРН)", "Геоинформационные", "API", "1 раз в месяц", True, "manual"),
    ("ESIA", "ЕСИА (Госуслуги)", "Идентификация и безопасность", "OAuth 2.0 / SAML", "Реальное время", True, "unavailable"),
    ("EBS", "ЕБС", "Идентификация и безопасность", "API", "Реальное время", True, "unavailable"),
    ("UC", "УЦ / инфраструктура ЭП", "Идентификация и безопасность", "Крипто-API", "Реальное время", True, "exchange"),
    ("ASSPR", "АССПР v2.4 «Цифровой паспорт НТП»", "Внешние паспорта предприятий", "API/Файл", "По мере поступления", True, "manual"),
]


def seed_kernel() -> None:
    """Ядро: модули, политики, пользователи, аудит запуска."""
    registry.bootstrap_registry()
    with session_scope() as db:
        if db.scalar(select(func.count()).select_from(IamPolicy)) == 0:
            for role, action, res, effect, cond, note in POLICIES:
                db.add(IamPolicy(subject_role=role, action=action, resource=res,
                                 effect=effect, condition=cond, note=note))
        if db.scalar(select(func.count()).select_from(User)) == 0:
            for login, fio, role, org, pwd in DEMO_USERS:
                u = User(login=login, fio=fio, role_level=role, org_id=org,
                         password_hash=hash_password(pwd))
                if role in {r.strip() for r in settings().mfa_required_roles.split(",")}:
                    u.totp_secret = generate_totp_secret()   # MFA для администраторов
                db.add(u)
    audit.record("Инициализация ядра (seed)", "модули: 15 · политики · демо-пользователи", "Успех",
                 user="system", role="—")


def _gen_value(o: dict, sec: int, field) -> str:
    """Детерминированное значение поля паспорта (соответствует генератору прототипа v8)."""
    if sec == 1:
        n = field.name.lower()
        if "наименование" in n:
            return o["name"]
        if "инн" in n:
            return o["inn"] + " / 1" + o["inn"][1:]
        if "координат" in n:
            return f'{o["lat"]:.4f}, {o["lon"]:.4f} (WGS84)'
        if "оквэд" in n:
            return f'26.3{(h := (o["emp"] % 9))}, 62.0{(h + 1) % 9}'
        if "адрес" in n:
            return f'г. {o["city"]}, ул. Промышленная, {1 + o["emp"] % 40}'
        if "статус" in n:
            return "Включено в реестр ОПП"
        if "дата" in n:
            return str(o["year"])
        if "устав" in n:
            return f'Устав ред. {2 + o["emp"] % 4}, подписан ЭЦП'
    ft = field.ftype
    if ft == "Число":
        return str(10 + (field.ord * 7 + sec * 13 + o["emp"]) % 400)
    if ft == "Список":
        return f'{2 + (field.ord + sec) % 6} позиции (в реестре)'
    if ft == "Файлы":
        return f'загружено {1 + (field.ord + sec) % 5} файл(ов), подпись ЭЦП'
    if ft == "Справочник":
        return f'код {100 + (field.ord * 13 + sec * 17) % 800} по классификатору'
    if ft == "Матрица":
        return "6 направлений × уровни 0–5"
    if ft == "Ссылки":
        return f'{1 + (field.ord + sec) % 4} связи в реестре'
    if ft == "Журнал":
        return f'{3 + (field.ord * 3 + sec) % 12} записей'
    return "по документу-основанию"


def seed_domain() -> dict:
    """Предметная область: справочники и данные из прототипа v8 (seed_data.json)."""
    if not os.path.exists(DATA_PATH):
        return {"loaded": False, "reason": "seed_data.json отсутствует — выполните экспорт из прототипа"}
    data = json.load(open(DATA_PATH, encoding="utf-8"))
    stats: dict = {}
    with session_scope() as db:
        # справочник разделов и полей паспорта (Приложение 2)
        if db.scalar(select(func.count()).select_from(PassportSection)) == 0:
            for s in data["sections"]:
                db.add(PassportSection(n=s["n"], name=s["name"], threshold=s["threshold"]))
            db.flush()
        if db.scalar(select(func.count()).select_from(PassportField)) == 0:
            for sec, fields in data["fields"].items():
                for i, f in enumerate(fields, start=1):
                    db.add(PassportField(section_n=int(sec), ord=i, name=f[0], ftype=f[1],
                                         required=(f[2] == "Обязательно"), source=f[3] or None))
            db.flush()
        # интеграции
        if db.scalar(select(func.count()).select_from(Integration)) == 0:
            for code, name, grp, proto, period, va, vbm in INTEGRATIONS:
                db.add(Integration(code=code, name=name, grp=grp, protocol=proto,
                                   period=period, variant_a=va, variant_b_mode=vbm))
        # организации (идемпотентно): сначала родители, flush, затем дочерние записи
        if db.scalar(select(func.count()).select_from(Organization)) == 0:
            for o in data["orgs"]:
                db.add(Organization(id=o["id"], name=o["name"], short_name=o["short"], org_type=o["type"],
                                    city=o["city"], region=o["reg"], lat=o["lat"], lon=o["lon"], inn=o["inn"],
                                    ogrn=o.get("ogrn"), founded=o["year"], employees=o["emp"], revenue=o["rev"],
                                    status=o["status"], lc_stage=o["stage"], invest=o["invest"],
                                    risk_idx=o["riskIdx"], links=",".join(o.get("links", []))))
            db.flush()
            fields = list(db.scalars(select(PassportField)))
            fid = {(f.section_n, f.ord): f.id for f in fields}
            for o in data["orgs"]:
                for k, v in o["comps"].items():
                    db.add(OrgCompetency(org_id=o["id"], comp=k, level=v))
                for dim, v in enumerate(o["radar"], start=1):
                    db.add(OrgRadar(org_id=o["id"], dim=dim, val=v))
                db.add(Maturity(org_id=o["id"], trl=o["trl"], mrl=o["mrl"], irl=o["irl"]))
                # значения полей паспорта: ровно round(fill%·N) полей раздела (детерминированно)
                for si, fv in enumerate(o["fill"], start=1):
                    fl = data["fields"].get(str(si), [])
                    C = len(fl)
                    nfill = int(round(fv * C / 100))
                    order = sorted(range(C), key=lambda j: ((si - 1) * 7 + j * 13) % 100)
                    for j in order[:nfill]:
                        f_id = fid.get((si, j + 1))
                        if f_id:
                            fobj = next(f for f in fields if f.id == f_id)
                            db.add(PassportValue(org_id=o["id"], field_id=f_id,
                                                 value=_gen_value(o, si, fobj), updated_by="seed"))
            db.flush()
            stats["orgs"] = len(data["orgs"])
        # проекты
        if db.scalar(select(func.count()).select_from(Project)) == 0:
            for p in data["projects"]:
                db.add(Project(id=p["id"], name=p["name"], org_id=p["ent"], lc_stage=p["stage"],
                               gate=p["gate"], deadline=date.fromisoformat(p["deadline"]),
                               budget=p["budget"], trl_target=p["trlT"], trl_current=p["trlC"]))
            stats["projects"] = len(data["projects"])
        # риски, документы, стимулы, экспертиза, пакеты АССПР
        if db.scalar(select(func.count()).select_from(Risk)) == 0:
            for r in data["risks"]:
                db.add(Risk(id=r["id"], title=r["t"], category=r["cat"], prob=r["p"], impact=r["i"],
                            owner_module=r["own"], status=r["st"], mitigation=r["mit"]))
            stats["risks"] = len(data["risks"])
        if db.scalar(select(func.count()).select_from(Document)) == 0:
            for d in data["docs"]:
                db.add(Document(id=d["id"], title=d["t"], org_id=d["ent"], kind=d["kind"],
                                sign_status=d["sign"], doc_date=date.fromisoformat(d["date"])))
        if db.scalar(select(func.count()).select_from(Stim)) == 0:
            for s in data["stims"]:
                db.add(Stim(id=s["id"], org_id=s["ent"], kind="stim" if s["kind"] == "Стимул" else "sanction",
                            title=s["t"], basis=s["base"], doc_date=date.fromisoformat(s["date"]), status=s["st"]))
        if db.scalar(select(func.count()).select_from(ExpertItem)) == 0:
            for v in data["expert"]:
                exp = v.get("expert") or None
                if exp in ("—", "-", ""):
                    exp = None          # «—» в витрине = эксперт не назначен
                db.add(ExpertItem(id=v["id"], org_id=v["ent"], object=v["obj"], expert=exp,
                                  since=date.fromisoformat(v["since"]), priority=v["prio"],
                                  status="in_review" if exp else "queued"))
        # KPI (Этап 8): целевые показатели с историей за 12 месяцев (из прототипа v12)
        if db.scalar(select(func.count()).select_from(Kpi)) == 0:
            for k in data["kpis"]:
                db.add(Kpi(code=k["code"], name=k["n"], current=k["cur"], target=k["target"],
                           unit=k["unit"], direction=k["dir"], fmt=k["fmt"],
                           source=k.get("source", "calc"),
                           history=json.dumps(k.get("hist", []), ensure_ascii=False)))
            stats["kpis"] = len(data["kpis"])
        if db.scalar(select(func.count()).select_from(AssprPackage)) == 0:
            for a in data["asspr"]:
                db.add(AssprPackage(id=a["id"], org_name=a["org"], target_org_id=a["target"], ver=a["ver"],
                                    doc_date=date.fromisoformat(a["date"]), approval=a["approve"],
                                    completeness=a["complete"], issues=a["issues"], note=a.get("note") or None,
                                    payload=json.dumps({k: a[k] for k in
                                                ("sections", "comps", "trl", "mrl", "irl", "kpiIndex")
                                                if k in a} | ({"newOrg": a["newOrg"]} if a.get("newOrg") else {}),
                                                ensure_ascii=False)))
    stats["loaded"] = True
    return stats
