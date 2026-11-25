"""Configuração da aplicação carregada a partir de variáveis de ambiente."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

DEFAULT_DEV_SECRET_KEY = "dev-jwt-secret-key-change-in-production-2026"
VERSION = "3.0.0"
VALID_LOG_FORMATS = {"text", "json"}


class ConfigError(RuntimeError):
    """Configuração inválida ou insegura."""


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} deve ser um número inteiro.") from exc
    if value <= 0:
        raise ConfigError(f"{name} deve ser maior que zero.")
    return value


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{name} deve ser um booleano (true/false).")


def _list_env(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    environment: str = "development"
    database_url: str = "sqlite:///./taskflow_v2.db"
    secret_key: str = field(default=DEFAULT_DEV_SECRET_KEY, repr=False)
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    rate_limit_max_requests: int = 120
    rate_limit_window_seconds: int = 60
    redis_url: str | None = field(default=None, repr=False)
    log_level: str = "INFO"
    log_format: str = "text"
    trust_proxy_headers: bool = False
    auto_create_tables: bool = True

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def validate(self) -> None:
        if self.is_production and self.secret_key == DEFAULT_DEV_SECRET_KEY:
            raise ConfigError("Defina SECRET_KEY com um valor seguro em produção.")
        if len(self.secret_key) < 32:
            raise ConfigError("SECRET_KEY deve ter pelo menos 32 caracteres.")
        if self.access_token_expire_minutes <= 0:
            raise ConfigError("ACCESS_TOKEN_EXPIRE_MINUTES deve ser maior que zero.")
        if self.refresh_token_expire_days <= 0:
            raise ConfigError("REFRESH_TOKEN_EXPIRE_DAYS deve ser maior que zero.")
        if self.log_format not in VALID_LOG_FORMATS:
            allowed = ", ".join(sorted(VALID_LOG_FORMATS))
            raise ConfigError(f"LOG_FORMAT inválido: '{self.log_format}'. Use: {allowed}.")

    @classmethod
    def from_env(cls) -> Settings:
        raw_redis = os.getenv("REDIS_URL", "").strip()
        settings = cls(
            environment=os.getenv("ENVIRONMENT", "development").strip().lower(),
            database_url=os.getenv("DATABASE_URL", cls.database_url),
            secret_key=os.getenv("SECRET_KEY", DEFAULT_DEV_SECRET_KEY),
            access_token_expire_minutes=_int_env("ACCESS_TOKEN_EXPIRE_MINUTES", 15),
            refresh_token_expire_days=_int_env("REFRESH_TOKEN_EXPIRE_DAYS", 7),
            cors_origins=_list_env("CORS_ORIGINS", "*"),
            rate_limit_max_requests=_int_env("RATE_LIMIT_MAX_REQUESTS", 120),
            rate_limit_window_seconds=_int_env("RATE_LIMIT_WINDOW_SECONDS", 60),
            redis_url=raw_redis or None,
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
            log_format=os.getenv("LOG_FORMAT", "text").strip().lower(),
            trust_proxy_headers=_bool_env("TRUST_PROXY_HEADERS", False),
            auto_create_tables=_bool_env("AUTO_CREATE_TABLES", True),
        )
        settings.validate()
        return settings
