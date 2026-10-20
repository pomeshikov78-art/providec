"""ORM-модели АИС «Техноконтур» (соответствуют db/schema.sql и контрактам OpenAPI).

Сущности: IAM (users, policies), ядро (module_registry, events_log, audit_log),
MOD-PASS (organizations, passport_*), MOD-PROF (competencies, radar, maturity, twins),
MOD-NIOKR (projects, gates, evm), MOD-RISK/DOC/STIM/EXPERT/INT.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey,
                        Index, Integer, SmallInteger, String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- IAM
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    fio: Mapped[str] = mapped_column(String(200))
    role_level: Mapped[str] = mapped_column(String(2), index=True)          # L0..L7 (ТЗ п.3.2)
    org_id: Mapped[str | None] = mapped_column(String(8), nullable=True)   # ABAC: своё предприятие (L4)
    password_hash: Mapped[str] = mapped_column(String(256))
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)  # MFA (RFC 6238)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class IamPolicy(Base):
    __tablename__ = "iam_policies"
    id: Mapped[int] = mapped_column(primary_key=True)
    subject_role: Mapped[str] = mapped_column(String(2), index=True)       # L0..L7 или '*'
    action: Mapped[str] = mapped_column(String(64), index=True)
    resource: Mapped[str] = mapped_column(String(128), default="*")
    effect: Mapped[str] = mapped_column(String(5), default="deny")         # allow | deny
    condition: Mapped[str | None] = mapped_column(Text, nullable=True)     # JSON: ABAC-условия
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


# ---------------------------------------------------------------- Ядро
class ModuleRegistry(Base):
    __tablename__ = "module_registry"
    code: Mapped[str] = mapped_column(String(16), primary_key=True)        # MOD-PASS ...
    name: Mapped[str] = mapped_column(String(160))
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[str] = mapped_column(String(16))                       # SemVer
    deps: Mapped[str] = mapped_column(Text, default="")                    # CSV кодов
    status: Mapped[str] = mapped_column(String(12), default="active")      # active|disabled|degraded|error
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    @property
    def dep_list(self) -> list[str]:
        return [d for d in self.deps.split(",") if d]


class EventLog(Base):
    __tablename__ = "events_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    type: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(64))
    payload: Mapped[str] = mapped_column(Text, default="")
    sev: Mapped[str] = mapped_column(String(5), default="info")            # info|warn|alert
    trace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    delivered: Mapped[int] = mapped_column(Integer, default=0)             # at-least-once: счетчик доставок
    dlq: Mapped[bool] = mapped_column(Boolean, default=False)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    user_login: Mapped[str] = mapped_column(String(64))
    role_level: Mapped[str | None] = mapped_column(String(2), nullable=True)
    action: Mapped[str] = mapped_column(String(200))
    object: Mapped[str] = mapped_column(String(300), default="—")
    result: Mapped[str] = mapped_column(String(120), default="Успех")
    ip: Mapped[str] = mapped_column(String(45), default="127.0.0.1")
    prev_hash: Mapped[str] = mapped_column(String(64), default="0" * 64)
    hash: Mapped[str] = mapped_column(String(64), index=True)              # WORM: хеш-цепочка


# ---------------------------------------------------------------- MOD-PASS
class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(8), primary_key=True)           # E01..E101
    name: Mapped[str] = mapped_column(String(220))
    short_name: Mapped[str] = mapped_column(String(120))
    org_type: Mapped[str] = mapped_column(String(4))                       # ent|nio|test
    city: Mapped[str] = mapped_column(String(80))
    region: Mapped[str] = mapped_column(String(60), index=True)            # ФО
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    inn: Mapped[str] = mapped_column(String(10))
    ogrn: Mapped[str | None] = mapped_column(String(13), nullable=True)
    founded: Mapped[int] = mapped_column(Integer, default=2000)
    employees: Mapped[int] = mapped_column(Integer, default=100)
    revenue: Mapped[float] = mapped_column(Float, default=1.0)             # млрд ₽
    status: Mapped[str] = mapped_column(String(10), default="draft")       # draft|pending|verified
    lc_stage: Mapped[int] = mapped_column(SmallInteger, default=0)
    invest: Mapped[int] = mapped_column(SmallInteger, default=1)
    risk_idx: Mapped[int] = mapped_column(SmallInteger, default=30)
    links: Mapped[str] = mapped_column(Text, default="")                   # CSV кооперационных связей
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    competencies: Mapped[list["OrgCompetency"]] = relationship(cascade="all, delete-orphan")
    radar: Mapped[list["OrgRadar"]] = relationship(cascade="all, delete-orphan")


class PassportSection(Base):
    __tablename__ = "passport_sections"
    n: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    threshold: Mapped[int] = mapped_column(SmallInteger, default=90)       # порог полноты (Прил. 2.14)


class PassportField(Base):
    __tablename__ = "passport_fields"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    section_n: Mapped[int] = mapped_column(SmallInteger, ForeignKey("passport_sections.n"), index=True)
    ord: Mapped[int] = mapped_column(SmallInteger)
    name: Mapped[str] = mapped_column(String(200))
    ftype: Mapped[str] = mapped_column(String(20))                         # Текст|Число|Список|Файлы|...
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str | None] = mapped_column(String(60), nullable=True)  # ЕГРЮЛ/ГИСП (раздел 1)
    __table_args__ = (UniqueConstraint("section_n", "ord", name="uq_field_sec_ord"),)


class PassportValue(Base):
    __tablename__ = "passport_values"
    org_id: Mapped[str] = mapped_column(String(8), ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    field_id: Mapped[int] = mapped_column(Integer, ForeignKey("passport_fields.id"), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PassportVersion(Base):
    __tablename__ = "passport_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(String(8), ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    ver_n: Mapped[int] = mapped_column(Integer)
    changes: Mapped[str] = mapped_column(Text, default="[]")               # JSON: [{section,field,old,new}]
    crc32: Mapped[str] = mapped_column(String(10))                         # снимок целостности (0x........)
    fill_total: Mapped[int] = mapped_column(SmallInteger, default=0)
    author: Mapped[str] = mapped_column(String(120))
    role_level: Mapped[str | None] = mapped_column(String(2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("org_id", "ver_n", name="uq_org_ver"),)


class OrgCompetency(Base):
    __tablename__ = "org_competencies"
    org_id: Mapped[str] = mapped_column(String(8), ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    comp: Mapped[str] = mapped_column(String(4), primary_key=True)         # sci|des|prod|test|dig|mng
    level: Mapped[int] = mapped_column(SmallInteger, default=0)


class OrgRadar(Base):
    __tablename__ = "org_radar"
    org_id: Mapped[str] = mapped_column(String(8), ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    dim: Mapped[int] = mapped_column(SmallInteger, primary_key=True)       # 1..7
    val: Mapped[int] = mapped_column(SmallInteger, default=0)


class Maturity(Base):
    __tablename__ = "maturity"
    org_id: Mapped[str] = mapped_column(String(8), ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    trl: Mapped[int] = mapped_column(SmallInteger, default=1)
    mrl: Mapped[int] = mapped_column(SmallInteger, default=1)
    irl: Mapped[int] = mapped_column(SmallInteger, default=1)
    calc_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Twin(Base):
    """Цифровой двойник управленческого состояния (ТЗ п.2.1): снимок + производные метрики."""
    __tablename__ = "twins"
    org_id: Mapped[str] = mapped_column(String(8), ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    crc32: Mapped[str] = mapped_column(String(10))
    snapshot: Mapped[str] = mapped_column(Text, default="{}")              # JSON
    index_i: Mapped[float] = mapped_column(Float, default=0.0)
    gaps_count: Mapped[int] = mapped_column(SmallInteger, default=0)
    built_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ---------------------------------------------------------------- MOD-NIOKR / MOD-PORTF
class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(8), primary_key=True)           # P01...
    name: Mapped[str] = mapped_column(String(240))
    org_id: Mapped[str] = mapped_column(String(8), ForeignKey("organizations.id"), index=True)
    lc_stage: Mapped[int] = mapped_column(SmallInteger, default=0)         # 0..8
    gate: Mapped[str] = mapped_column(String(8), default="review")         # go|no-go|review
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    budget: Mapped[float] = mapped_column(Float, default=1.0)
    trl_target: Mapped[int] = mapped_column(SmallInteger, default=6)
    trl_current: Mapped[int] = mapped_column(SmallInteger, default=4)
    pert_o: Mapped[int] = mapped_column(Integer, default=30)               # трёхточечная оценка этапа, дней
    pert_m: Mapped[int] = mapped_column(Integer, default=50)
    pert_p: Mapped[int] = mapped_column(Integer, default=90)


class ProjectGate(Base):
    """Append-only журнал решений контрольных точек (ИВП-3)."""
    __tablename__ = "project_gates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String(8), ForeignKey("projects.id"), index=True)
    stage: Mapped[int] = mapped_column(SmallInteger)
    decision: Mapped[str] = mapped_column(String(8))                       # go|no-go|review
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[str] = mapped_column(String(64))
    decided_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class EvmSnapshot(Base):
    __tablename__ = "evm_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String(8), ForeignKey("projects.id"), index=True)
    pv: Mapped[float] = mapped_column(Float)
    ev: Mapped[float] = mapped_column(Float)
    ac: Mapped[float] = mapped_column(Float)
    spi: Mapped[float] = mapped_column(Float)
    cpi: Mapped[float] = mapped_column(Float)
    calc_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ---------------------------------------------------------------- Прочие модули
class Risk(Base):
    __tablename__ = "risks"
    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(40))
    prob: Mapped[int] = mapped_column(SmallInteger)
    impact: Mapped[int] = mapped_column(SmallInteger)
    owner_module: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="Открыт")
    mitigation: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def score(self) -> int:
        return self.prob * self.impact


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    org_id: Mapped[str | None] = mapped_column(String(8), nullable=True)
    kind: Mapped[str] = mapped_column(String(24))
    sign_status: Mapped[str] = mapped_column(String(30), default="Проект")
    doc_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(200), nullable=True)  # MinIO object key
    version: Mapped[int] = mapped_column(SmallInteger, default=1)         # версия карточки (версионность MOD-DOC)
    signature: Mapped[str | None] = mapped_column(String(80), nullable=True)   # dev: sha256-отпечаток; prod: ЭЦП ГОСТ Р 34.10-2012
    signed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Stim(Base):
    __tablename__ = "stims"
    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    org_id: Mapped[str | None] = mapped_column(String(8), nullable=True)
    kind: Mapped[str] = mapped_column(String(10))                          # stim|sanction
    title: Mapped[str] = mapped_column(String(300))
    basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    doc_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="Действует")


class ExpertItem(Base):
    __tablename__ = "expert_queue"
    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    org_id: Mapped[str | None] = mapped_column(String(8), nullable=True)
    object: Mapped[str] = mapped_column(String(200))
    expert: Mapped[str | None] = mapped_column(String(80), nullable=True)
    since: Mapped[date | None] = mapped_column(Date, nullable=True)
    priority: Mapped[str] = mapped_column(String(12), default="Средний")
    status: Mapped[str] = mapped_column(String(16), default="queued")


class Integration(Base):
    __tablename__ = "integrations"
    code: Mapped[str] = mapped_column(String(24), primary_key=True)        # EGRUL, GISP, ROSPATENT, ESIA, ASSPR...
    name: Mapped[str] = mapped_column(String(160))
    grp: Mapped[str] = mapped_column(String(80))
    protocol: Mapped[str | None] = mapped_column(String(40), nullable=True)
    period: Mapped[str | None] = mapped_column(String(60), nullable=True)
    variant_a: Mapped[bool] = mapped_column(Boolean, default=True)
    variant_b_mode: Mapped[str] = mapped_column(String(16), default="manual")  # manual|exchange|unavailable


class AssprPackage(Base):
    """Пакет «Цифрового паспорта НТП» из внешней системы АССПР (импорт в БД MOD-PASS)."""
    __tablename__ = "asspr_packages"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    org_name: Mapped[str] = mapped_column(String(220))
    target_org_id: Mapped[str | None] = mapped_column(String(8), nullable=True)
    ver: Mapped[str | None] = mapped_column(String(80), nullable=True)
    doc_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    approval: Mapped[str | None] = mapped_column(String(120), nullable=True)
    completeness: Mapped[int] = mapped_column(SmallInteger, default=0)
    issues: Mapped[int] = mapped_column(SmallInteger, default=0)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[str] = mapped_column(Text, default="{}")               # JSON: sections/comps/trl/mrl/irl/newOrg
    imported_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    imported_by: Mapped[str | None] = mapped_column(String(64), nullable=True)


Index("ix_org_region_type", Organization.region, Organization.org_type)


# ---------------------------------------------------------------- Этап 8: MOD-KPI / MOD-AI / MOD-DOC (ЭЦП)
class Kpi(Base):
    """Целевой показатель системы (ТЗ п.2.3). source: calc — пересчёт из БД,
    telemetry — измеряется службами модулей (отчёты, гео, SLA)."""
    __tablename__ = "kpis"
    code: Mapped[str] = mapped_column(String(8), primary_key=True)        # KPI-1..KPI-8
    name: Mapped[str] = mapped_column(String(300))
    current: Mapped[float] = mapped_column(Float, default=0.0)
    target: Mapped[float] = mapped_column(Float, default=0.0)
    unit: Mapped[str] = mapped_column(String(12), default="")
    direction: Mapped[str] = mapped_column(String(4), default="up")       # up | down
    fmt: Mapped[str] = mapped_column(String(80), default="")
    source: Mapped[str] = mapped_column(String(12), default="calc")       # calc | telemetry
    history: Mapped[str] = mapped_column(Text, default="[]")              # JSON: до 12 последних значений
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AiRecommendation(Base):
    """Рекомендация MOD-AI (ИВП-7): публикуется при confidence ≥ 0.7."""
    __tablename__ = "ai_recommendations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(24), index=True)           # AIR-YYYYMMDD-HHMMSS
    text: Mapped[str] = mapped_column(Text)
    module: Mapped[str] = mapped_column(String(16))                       # MOD-COOP, MOD-NIOKR, ...
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(16), default="published")  # published|accepted|dismissed
    decided_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
