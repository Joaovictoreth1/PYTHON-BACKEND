from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./taskflow_v2.db"
    api_secret_key: SecretStr | None = None
    cors_origins: list[str] = Field(default_factory=list)
    rate_limit_max_requests: Annotated[int, Field(ge=1, le=10000)] = 120
    rate_limit_window_seconds: Annotated[int, Field(ge=1, le=3600)] = 60
    rate_limit_max_clients: Annotated[int, Field(ge=1, le=65536)] = 4096
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @model_validator(mode="after")
    def validate_deployment(self) -> Self:
        try:
            url = make_url(self.database_url)
        except ArgumentError:
            raise ValueError("DATABASE_URL is not a SQLAlchemy URL") from None
        for origin in self.cors_origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or any((parsed.path, parsed.query, parsed.fragment, "*" in origin))
            ):
                raise ValueError("CORS_ORIGINS must enumerate trusted HTTP(S) origins")
        key = self.api_secret_key.get_secret_value() if self.api_secret_key is not None else ""
        if key and (not key.isascii() or not key.isprintable() or any(c.isspace() for c in key)):
            raise ValueError("API_SECRET_KEY must contain printable ASCII without whitespace")
        if self.environment == "production":
            if len(key) < 32:
                raise ValueError("Set API_SECRET_KEY to a random value of at least 32 characters")
            if url.get_backend_name() == "sqlite" and url.database in (None, "", ":memory:"):
                raise ValueError("Production requires a persistent database")
        return self
