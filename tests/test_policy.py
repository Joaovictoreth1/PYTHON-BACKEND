from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from taskflow.config import Settings
from taskflow.database import as_utc, make_engine
from taskflow.main import create_app
from taskflow.middleware import RateLimiter


def test_production_configuration() -> None:
    with pytest.raises(ValidationError, match="random value"):
        Settings(_env_file=None, environment="production", api_secret_key=None)
    with pytest.raises(ValidationError, match="persistent database"):
        Settings(
            _env_file=None,
            environment="production",
            database_url="sqlite:///:memory:",
            api_secret_key=SecretStr("test-generated-production-key-example"),
        )
    with pytest.raises(ValidationError, match="printable ASCII") as exc:
        Settings(_env_file=None, api_secret_key=SecretStr("valor inválido"))
    assert "valor inválido" not in str(exc.value)
    with pytest.raises(ValidationError, match="trusted HTTP"):
        Settings(_env_file=None, cors_origins=["*"])
    with pytest.raises(ValidationError, match="SQLAlchemy URL"):
        Settings(_env_file=None, database_url="invalid")
    with pytest.raises(ValidationError, match="greater than or equal to 1"):
        Settings(_env_file=None, rate_limit_window_seconds=0)


def test_limiter_does_not_evict_active_clients() -> None:
    limiter = RateLimiter(limit=2, window=10, max_clients=2)
    assert limiter.retry_after("a", 0) == 0
    assert limiter.retry_after("b", 1) == 0
    assert limiter.retry_after("a", 2) == 0
    assert limiter.retry_after("a", 3.1) == 7
    assert limiter.retry_after("c", 4) == 7
    assert len(limiter.clients) == 2
    assert limiter.retry_after("c", 11) == 0
    assert limiter.retry_after("a", 11) == 0
    assert limiter.retry_after("c", 12) == 0
    assert len(limiter.clients) == 2


def test_naive_timestamps_and_memory_fk() -> None:
    assert as_utc(datetime(2024, 1, 1)) == datetime(2024, 1, 1, tzinfo=UTC)
    engine = make_engine("sqlite:///:memory:")
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("PRAGMA foreign_keys")) == 1
    finally:
        engine.dispose()


@pytest.mark.anyio
async def test_missing_configuration_denies_api_access(settings: Settings) -> None:
    app = create_app(settings.model_copy(update={"api_secret_key": None, "log_level": "ERROR"}))
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app, client=None),
            base_url="http://test",
            headers={"X-API-Key": "arbitrary-test-key"},
        ) as client,
    ):
        assert (await client.get("/api/v1/tasks")).status_code == 401


@pytest.mark.anyio
async def test_integrity_error_has_no_storage_details(app: FastAPI) -> None:
    @app.get("/constraint-conflict")
    def conflict() -> None:
        raise IntegrityError("private SQL statement", {}, RuntimeError("private storage details"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/constraint-conflict")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"
    assert "private" not in response.text
