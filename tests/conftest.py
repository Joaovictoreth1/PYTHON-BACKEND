from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

API_KEY = "test-secret-key-0123456789"


def make_settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "database_url": "sqlite://",
        "api_secret_key": API_KEY,
        "rate_limit_max_requests": 10_000,
        "log_level": "WARNING",
    }
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(make_settings()), raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def auth() -> dict[str, str]:
    return {"X-API-Key": API_KEY}


@pytest.fixture
def create_project(client: TestClient, auth: dict[str, str]) -> Callable[..., dict[str, Any]]:
    def _create(name: str = "Projeto Alpha", **extra: Any) -> dict[str, Any]:
        res = client.post("/api/v1/projects", json={"name": name, **extra}, headers=auth)
        assert res.status_code == 201, res.text
        return res.json()

    return _create


@pytest.fixture
def create_task(client: TestClient, auth: dict[str, str]) -> Callable[..., dict[str, Any]]:
    def _create(title: str = "Tarefa X", **extra: Any) -> dict[str, Any]:
        res = client.post("/api/v1/tasks", json={"title": title, **extra}, headers=auth)
        assert res.status_code == 201, res.text
        return res.json()

    return _create
