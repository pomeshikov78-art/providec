# АИС «Техноконтур» — бэкенд (FastAPI + SQLAlchemy)

Реальная серверная реализация по ТЗ ред. 4.0 (шифр «Провидец»), создана поэтапно
по «Подробному поэтапному плану разработки» ред. 1.0 (Фазы 0–1+, Этапы 1–7).

## Архитектура
```
app/
  config.py            конфигурация (вариант А/Б, СУБД, шина, IAM, гео, нормативы ТЗ)
  db.py                SQLAlchemy 2.0: dev — SQLite, prod — Postgres Pro + PostGIS
  models.py            ORM: IAM, ядро, 12 разделов паспорта (92 поля), НИОКР, двойники, риски…
  seed.py              начальное наполнение (15 модулей, политики, L0–L7, данные прототипа v8)
  kernel/
    bus.py             шина событий: at-least-once, DLQ, приоритеты, журнал, Redis Streams (опц.)
    registry.py        реестр модулей в СУБД: зависимости, обязательность, каскадная деградация
    iam.py             PBKDF2 + JWT (access/refresh, jti, blacklist) + MFA TOTP + RBAC/ABAC-политики
    audit.py           WORM-журнал с хеш-цепочкой sha256, сверка целостности
    oidc.py            Keycloak/ЕСИА (Authorization Code + PKCE), маппер ролей → L0–L7
    security.py        заголовки, rate limiting, CryptoProvider (ГОСТ — точка расширения СКЗИ)
  services/
    maturity.py        TRL/MRL/IRL, индекс ИТЗ (0,4/0,35/0,25), разрывы, бенчмарки отрасли
    passport.py        workflow верификации (ИВП-1), версии + CRC32, контроль качества (ИНН/ОГРН ФНС)
    evm.py             EVM: PV/EV/AC/SPI/CPI, PERT (te, σ, P), агрегаты портфеля
    twin.py            цифровой двойник (подписка на profile.updated)
    geo.py             H3-кластеризация, KDE-теплокарта, геодезия (geographiclib), GeoJSON/KML
    coop.py            скоринг кооперации 45/20/20/15
    reports.py         реальные DOCX (python-docx), XLSX (openpyxl), PDF (reportlab, кириллица)
    asspr_import.py    импорт «Цифрового паспорта НТП» из АССПР v2.4
    validators.py      ИНН/ОГРН по методикам ФНС
  connectors/base.py   ЕГРЮЛ/ГИСП/Роспатент/ЕСИА/АССПР: retry, circuit breaker, идемпотентность
  routers/             API Gateway: auth, core, orgs, profile, niokr, geo, reports, coop, int, bootstrap
tests/                 65+ тестов: ядро, данные, алгоритмы, гео, безопасность, интеграции, отчёты
```

## Запуск
```bash
pip install -r requirements.txt
# dev (SQLite, seed из app/data/seed_data.json):
TC_DATABASE_URL=sqlite:///./technocontour.db TC_BUS_BACKEND=memory \
  uvicorn app.main:app --port 8000
# тесты:
python -m pytest tests/ -q
```
Демо-учётные записи: `admin/tc-admin-2026` (L7, MFA TOTP), `analyst/tc-analyst-2026` (L5),
`sarmat/tc-org-2026` (L4, предприятие E14), `guest/tc-guest-2026` (L0).

Клиент (`ais_providets.html`, v12): экран входа → блок «Серверный режим» → URL `http://localhost:8000`.

## Нормативы ТЗ под тестовым контролем
запуск ядра ≤ 30 с · отчёты ≤ 5 с · ИВП-GEO-1 ≤ 2 с · ИВП-GEO-2 ≤ 3 с · полнота паспорта ≥ 95 %.

Инфраструктура (Docker/K8s/CI/мониторинг/ELK) — см. `../deploy/INFRASTRUCTURE.md`.
Безопасность и чек-лист ФСТЭК 1Б — см. `docs/SECURITY.md`.
