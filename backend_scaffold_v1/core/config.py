"""Конфигурация АИС «Техноконтур» (шифр «Провидец»).

Варианты поставки (ТЗ п.6):
  network    — вариант А «Техноконтур-Сеть»: Kafka, внешние интеграции, ЕСИА;
  autonomous — вариант Б «Техноконтур-Контур»: Redis Streams, ручной импорт, air-gap.
Код ядра и модулей не меняется при смене варианта (требование ТЗ п.4.4.2).
"""
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TC_", env_file=".env", extra="ignore")

    app_name: str = "АИС «Техноконтур»"
    app_cipher: str = "Провидец"
    app_version: str = "1.0.0"
    variant: Literal["network", "autonomous"] = "network"

    database_url: str = "postgresql+asyncpg://tc:tc_dev_password@localhost:5432/technocontour"
    redis_url: str = "redis://localhost:6379/0"
    kafka_bootstrap: str = "localhost:9092"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "tc-admin"
    minio_secret_key: str = "tc_dev_password"

    jwt_secret: str = "dev_secret_change_me"
    jwt_algorithm: str = "HS256"          # в production варианта Б — ГОСТ Р 34.10-2012 через СКЗИ
    jwt_ttl_minutes: int = 60

    bus_backend: Literal["kafka", "redis"] = "kafka"   # вариант Б: redis (Streams)
    bus_dlq_topic: str = "tc.events.dlq"
    audit_hash_chain: bool = True          # WORM: хеш-цепочка записей аудита

    # Нормативы ТЗ (контролируются тестами):
    core_boot_max_sec: int = 30            # п.4.4.2 время запуска ядра
    report_max_sec: int = 5                # Задача 8.5
    geo_update_max_sec: int = 2            # ИВП-GEO-1
    heatmap_max_sec: int = 3               # ИВП-GEO-2
    passport_fill_min: int = 95            # ИВП-1 / Задача 1.5


@lru_cache
def settings() -> Settings:
    s = Settings()
    if s.variant == "autonomous":
        s.bus_backend = "redis"            # шина варианта Б — Redis Streams
    return s
