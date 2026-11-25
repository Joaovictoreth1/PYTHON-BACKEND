"""Configuração da aplicação carregada a partir de variáveis de ambiente."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

DEFAULT_DEV_API_KEY = "dev-secret-key-2026"
VERSION = "2.1.0"


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


def _list_env(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    environment: str = "development"
    database_url: str = "sqlite:///./taskflow_v2.db"
    api_secret_key: str = field(default=DEFAULT_DEV_API_KEY, repr=False)
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    rate_limit_max_requests: int = 120
    rate_limit_window_seconds: int = 60
    log_level: str = "INFO"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def validate(self) -> None:
        if self.is_production and self.api_secret_key == DEFAULT_DEV_API_KEY:
            raise ConfigError("Defina API_SECRET_KEY com um valor seguro em produção.")
        if len(self.api_secret_key) < 16:
            raise ConfigError("API_SECRET_KEY deve ter pelo menos 16 caracteres.")

    @classmethod
    def from_env(cls) -> Settings:
        settings = cls(
            environment=os.getenv("ENVIRONMENT", "development").strip().lower(),
            database_url=os.getenv("DATABASE_URL", cls.database_url),
            api_secret_key=os.getenv("API_SECRET_KEY", DEFAULT_DEV_API_KEY),
            cors_origins=_list_env("CORS_ORIGINS", "*"),
            rate_limit_max_requests=_int_env("RATE_LIMIT_MAX_REQUESTS", 120),
            rate_limit_window_seconds=_int_env("RATE_LIMIT_WINDOW_SECONDS", 60),
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
        )
        settings.validate()
        return settings
