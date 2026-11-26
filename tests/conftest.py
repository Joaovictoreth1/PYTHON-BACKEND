from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.orm import Session, sessionmaker

from taskflow.config import Settings
from taskflow.main import create_app
from taskflow.migrate import migrate

TEST_KEY = "isolated-test-fixture-key"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'api.db'}",
        api_secret_key=SecretStr(TEST_KEY),
        cors_origins=["https://app.example.test"],
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    migrate(settings)
    return create_app(settings)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": TEST_KEY},
        ) as session,
    ):
        yield session


@pytest.fixture
def sessions(app: FastAPI) -> sessionmaker[Session]:
    return app.state.session_factory
