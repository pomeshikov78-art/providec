# backend_scaffold_v1 — стартовый каркас промышленной разработки
## АИС «Техноконтур» (шифр «Провидец») · Фаза 0–1 поэтапного плана (ред. 1.0)

Каркас серверной части, сгенерированный по итогам этапа 2 (прототип v8.0.0) и в соответствии с
поэтапным планом разработки. Артефакт закрепляет контракты, проверенные на интерактивном прототипе:
каталог событий шины, граф зависимостей 15 модулей, спецификацию 92 полей цифрового паспорта
(Приложение 2 к ТЗ) и политики доступа IAM (L0–L7, RBAC+ABAC).

## Состав

```
backend_scaffold_v1/
├── README.md                  — этот файл
├── docker-compose.yml         — локальный стенд: Postgres+PostGIS, Redis, MinIO, Kafka
├── openapi/openapi.yaml       — контракт API Gateway (OpenAPI 3.0), ~25 операций
├── asyncapi/asyncapi.yaml     — каталог событий шины (AsyncAPI 2.6), 30+ каналов
├── db/schema.sql              — схема Postgres Pro: 20+ таблиц, hash-chain аудит,
│                                seed: 15 модулей, 12 разделов и 92 поля паспорта (Прил. 2),
│                                пороги полноты (Прил. 2.14), политики IAM
├── core/                      — каркас микроядра (Python 3.11+, FastAPI)
│   ├── requirements.txt
│   ├── config.py              — настройки (вариант А/Б, СУБД, Redis, Kafka, JWT)
│   ├── main.py                — фабрика приложения, маршрутизаторы, startup ядра
│   └── kernel/
│       ├── registry.py        — реестр модулей: SemVer, зависимости, enable/disable
│       ├── bus.py             — шина событий: publish/subscribe, at-least-once, DLQ
│       ├── iam.py             — JWT + RBAC/ABAC политики L0–L7 (перенос из прототипа)
│       └── audit.py           — неизменяемый журнал с хеш-цепочкой (WORM-профиль)
└── docs/ADR-001-microkernel.md — архитектурное решение «Ядро + Модули»
```

## Быстрый старт

```bash
cd backend_scaffold_v1
docker compose up -d                     # стенд данных (Postgres/Redis/MinIO/Kafka)
psql "$DATABASE_URL" -f db/schema.sql    # схема + справочные seed-данные
cd core && pip install -r requirements.txt
uvicorn main:app --reload                # API Gateway: http://localhost:8000/docs
```

Переменные окружения — см. `core/config.py` и `docker-compose.yml`.
Для варианта Б (air-gap) заменить образы на сертифицированные: Postgres Pro, Astra Linux SE,
 Redis → отечественный кэш-сервер, Kafka → Redis Streams (профиль `autonomous`).

## Соответствие плану (Фазы 0–1)

| Задача плана | Артефакт каркаса |
|---|---|
| 0.2 Стек: FastAPI + Celery, Kafka/Redis Streams | `core/requirements.txt`, `docker-compose.yml` |
| 0.2 Данные: Postgres Pro + PostGIS, Redis, MinIO | `docker-compose.yml`, `db/schema.sql` |
| 1.1 ADR-001, OpenAPI 3.0, ER-схема | `docs/ADR-001-microkernel.md`, `openapi/`, `db/schema.sql` |
| 1.2 Реестр модулей (SemVer, зависимости) | `core/kernel/registry.py` + таблица `module_registry` |
| 1.3 Шина событий (at-least-once, DLQ) | `core/kernel/bus.py`, `asyncapi/asyncapi.yaml` |
| 1.5 IAM (JWT, RBAC+ABAC, L0–L7) | `core/kernel/iam.py` + таблица `iam_policies` |
| 1.7 Аудит WORM | `core/kernel/audit.py` + триггер hash-chain на `audit_log` |
| 2.1 Паспорт: 12 разделов / 92 поля, пороги 2.14 | таблицы `passport_*` + seed из Приложения 2 |

## Что перенесено из прототипа v8.0.0 (проверено демонстрацией)

- Каталог из 30+ событий шины и их семантика (`asyncapi.yaml` = тикер прототипа).
- Граф зависимостей 15 модулей и правило «обязательные не отключаются» (`registry.py`).
- Спецификация 92 полей паспорта с типами/обязательностью/источниками и порогами полноты
  по разделам (`schema.sql`, seed сгенерирован из данных прототипа).
- Политики доступа L0–L7, включая ABAC-правило «L4 видит только своё предприятие» (`iam.py`).
- Алгоритмы: индекс зрелости I = 0,4·TRL/9 + 0,35·MRL/10 + 0,25·IRL/9; EVM (SPI/CPI);
  PERT te=(o+4m+p)/6; скоринг кооперации 45/20/20/15; контрольные суммы ИНН/ОГРН (ФНС);
  CRC32-снимки цифрового двойника — подлежат серверной реимплементации (Фаза 2).

## Следующие шаги (по плану)

1. Фаза 0: подключить GitLab CI (линтеры, тесты, сборка образов), окружения Dev/Stage/Prod.
2. Фаза 1: реализовать сервисы ядра поверх каркаса (уведомления, планировщик, менеджер состояний),
   нагрузочное тестирование Gateway (1000 RPS), security audit.
3. Фаза 2: перенести бизнес-алгоритмы прототипа в сервисы модулей (MOD-PASS первым —
   схема данных уже готова).
