# Инфраструктура и DevOps (Этап 7 детального плана разработки)

## Состав каталога `deploy/`
| Файл | Назначение |
|---|---|
| `docker-compose.yml` | Полный стенд: Postgres+PostGIS, Redis (шина/кэш), MinIO (S3-хранилище документов), backend (FastAPI), frontend (nginx). Профили: `monitoring` (Prometheus+Grafana+Alertmanager), `kafka` (шина варианта А), `keycloak` (ЕСИА/OIDC), `elk` (Filebeat→Logstash→Elasticsearch) |
| `k8s/technocontour.yaml` | Namespace, ConfigMap, Secret, StatefulSet Postgres+PVC, Redis, Deployment backend (3 реплики, probes, resources), HPA (3→12 по CPU 70%), frontend, Ingress (TLS 1.2/1.3, rate limit), NetworkPolicy (БД доступна только бэкенду) |
| `gitlab-ci.yml` | Пайплайн: lint (ruff, валидация YAML/OpenAPI, node --check) → test (pytest + junit-отчёт, jsdom DOM-тесты клиента) → SAST (bandit) → build (образы backend/frontend в registry) → deploy (dev — авто по main, production — вручную по тегу) |
| `monitoring/prometheus.yml` | Scrape-конфигурация: backend `/metrics`, redis/postgres/node exporters |
| `monitoring/alerts.yml` | Алерты: CoreDown (SLA), каскадная деградация модулей, остановка шины, **нарушение хеш-цепочки WORM-аудита**, превышение норматива генерации отчётов (5 с) |
| `monitoring/grafana-dashboard.json` | Дашборд: uptime, модули активно/деградировано, реестр, скорость шины, аудит |
| `logging/filebeat.yml`, `logging/logstash.conf` | ELK: сбор JSON-логов контейнеров, парсинг полей приложения (`ts/lvl/src/msg`), отдельный индекс для ALERT-событий шины |
| `.env.example` | Шаблон переменных окружения (все секреты — CHANGE_ME) |

## Контуры развёртывания
**Вариант А «Техноконтур-Сеть»:** защищённое облако (ЦОД РФ) → Kubernetes (3+ узла), Postgres Pro (Patroni, RPO ≤ 1 ч, RTO ≤ 4 ч), Kafka (шина), Keycloak+ЕСИА (IdP), Яндекс.Карты/2ГИС (тайлы), live-коннекторы ФНС/ГИСП/Роспатент, TLS 1.3, SLA 99,5 %.

**Вариант Б «Техноконтур-Контур» (air-gap):** локальный кластер внутри контура → тот же compose/K8s, но: Redis Streams вместо Kafka, локальный TileServer GL (OSM-тайлы), внешний IdP отключён (501), коннекторы — ручной импорт через защищённый носитель, СКЗИ ГОСТ (CryptoProvider), аттестация по профилю ФСТЭК 1Б (чек-лист: `backend/docs/SECURITY.md`), SLA 99,0 %. Код приложения идентичен — различие только в конфигурации (ТЗ п.4.4.2).

## Быстрый старт (dev)
```bash
make install                      # зависимости бэкенда
make test                         # 65+ тестов (ядро, данные, модули, гео, безопасность, интеграции)
make dev                          # uvicorn :8000 (SQLite + in-process шина, seed 100 организаций)
# открыть ais_providets.html → «Серверный режим»: http://localhost:8000, admin / tc-admin-2026 + TOTP
make up                           # docker compose: Postgres+PostGIS, Redis, MinIO, backend, frontend, мониторинг
make metrics                      # Prometheus-метрики ядра
```

## Метрики приложения (`GET /metrics`, без аутентификации — для Prometheus)
`tc_uptime_seconds`, `tc_events_total`, `tc_audit_records_total`, `tc_organizations_total`, `tc_modules_active`, `tc_modules_degraded`.

## Контроль качества поставки
* Юнит- и интеграционные тесты бэкенда: `backend/tests/` (pytest, TestClient, изолированная БД на прогон);
* DOM-тесты клиента: `src/test_dom.js` (jsdom, 28 проверок: данные, страницы 21, ядро, гео-алгоритмы, мост серверного режима);
* Статический анализ: ruff + bandit (CI);
* Валидация спецификаций: OpenAPI/AsyncAPI/compose/K8s — шаг `openapi-validate` в CI;
* Нормативы ТЗ контролируются тестами: запуск ядра ≤ 30 с, отчёты ≤ 5 с, ИВП-GEO-1 ≤ 2 с, ИВП-GEO-2 ≤ 3 с, полнота паспорта ≥ 95 %.
