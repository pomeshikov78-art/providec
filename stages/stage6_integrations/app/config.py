"""Конфигурация АИС «Техноконтур» (шифр «Провидец»).

Варианты поставки (ТЗ п.6):
  network    — вариант А «Техноконтур-Сеть»  (Kafka/Redis, внешние интеграции, ЕСИА, онлайн-карты);
  autonomous — вариант Б «Техноконтур-Контур» (Redis Streams, ручной импорт, air-gap, локальный тайл-сервер).
Код ядра и модулей не меняется при смене варианта (ТЗ п.4.4.2) — различия только в конфигурации.
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

    # --- Данные (ТЗ п.4.2: Postgres Pro + PostGIS; dev-профиль — SQLite) ---
    database_url: str = "sqlite:///./technocontour.db"
    db_echo: bool = False

    # --- Шина событий ---
    bus_backend: Literal["memory", "redis"] = "memory"   # вариант Б: redis (Streams); вариант А (prod): kafka-адаптер
    redis_url: str = "redis://localhost:6379/0"
    bus_stream: str = "tc:events"
    bus_dlq: str = "tc:events:dlq"
    bus_delivery: str = "at-least-once"

    # --- IAM ---
    jwt_secret: str = "dev_secret_change_me"
    jwt_algorithm: str = "HS256"          # prod вариант Б: ГОСТ Р 34.10-2012 через СКЗИ (kernel/crypto.py)
    jwt_ttl_minutes: int = 60
    jwt_refresh_ttl_hours: int = 12
    mfa_required_roles: str = "L7"        # роли с обязательной MFA (TOTP)
    keycloak_url: str = ""                # опционально: внешний IdP (вариант А, ЕСИА через Keycloak OIDC)
    keycloak_realm: str = "technocontour"

    # --- Безопасность ---
    rate_limit_per_minute: int = 240      # API Gateway rate limiting (ТЗ п.4.4.1)
    audit_hash_chain: bool = True         # WORM-журнал с хеш-цепочкой
    security_headers: bool = True

    # --- Хранилища / интеграции ---
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "tc-admin"
    minio_secret_key: str = "tc_dev_password"
    connectors_mode: Literal["sandbox", "live"] = "sandbox"  # sandbox — детерминированные стенды внешних систем

    # --- MOD-GEO (ТЗ п.5.6) ---
    geo_tile_url: str = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"   # вариант А
    geo_tile_url_autonomous: str = "http://tiles.contour.internal/{z}/{x}/{y}.png"  # вариант Б: локальный TileServer GL
    geo_h3_resolution: int = 5            # базовое разрешение кластеризации H3
    geo_kde_bandwidth_km: float = 120.0   # полоса ядерной оценки плотности

    # --- Нормативы ТЗ (контролируются тестами) ---
    core_boot_max_sec: int = 30           # п.4.4.2
    report_max_sec: int = 5               # Задача 8.5
    geo_update_max_sec: int = 2           # ИВП-GEO-1
    heatmap_max_sec: int = 3              # ИВП-GEO-2
    passport_fill_min: int = 95           # ИВП-1 / Задача 1.5

    @property
    def tile_url(self) -> str:
        return self.geo_tile_url if self.variant == "network" else self.geo_tile_url_autonomous


@lru_cache
def settings() -> Settings:
    return Settings()
