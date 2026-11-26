import os
from dataclasses import dataclass, field


def positive_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = 0
    if value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


@dataclass(frozen=True)
class Settings:
    api_secret_key: str = field(repr=False)
    database_url: str = "sqlite:///./taskflow_v2.db"
    cors_allowed_origins: tuple[str, ...] = ()
    rate_limit_max_requests: int = 120
    rate_limit_window_seconds: int = 60

    def __post_init__(self) -> None:
        if (
            len(self.api_secret_key) < 32
            or not self.api_secret_key.isascii()
            or not self.api_secret_key.isprintable()
            or any(char.isspace() for char in self.api_secret_key)
        ):
            raise ValueError(
                "API_SECRET_KEY must contain at least 32 printable ASCII characters without spaces"
            )
        if "*" in self.cors_allowed_origins:
            raise ValueError("CORS_ALLOWED_ORIGINS must list explicit origins")

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            api_secret_key=os.getenv("API_SECRET_KEY", ""),
            database_url=os.getenv("DATABASE_URL", "sqlite:///./taskflow_v2.db"),
            cors_allowed_origins=tuple(
                value.strip()
                for value in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
                if value.strip()
            ),
            rate_limit_max_requests=positive_int("RATE_LIMIT_MAX_REQUESTS", 120),
            rate_limit_window_seconds=positive_int("RATE_LIMIT_WINDOW_SECONDS", 60),
        )
