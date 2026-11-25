from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

TEST_SECRET_KEY = "test-jwt-secret-key-0123456789abcdef"


def make_settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "database_url": "sqlite://",
        "secret_key": TEST_SECRET_KEY,
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
def register_and_login(client: TestClient) -> Callable[..., tuple[dict[str, Any], dict[str, str]]]:
    def _helper(
        email: str = "alice@example.com",
        password: str = "StrongPass123",
        full_name: str = "Alice Silva",
    ) -> tuple[dict[str, Any], dict[str, str]]:
        reg = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "full_name": full_name},
        )
        assert reg.status_code == 201, reg.text
        login = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        assert login.status_code == 200, login.text
        tokens = login.json()
        return tokens, {"Authorization": f"Bearer {tokens['access_token']}"}

    return _helper


@pytest.fixture
def auth(
    register_and_login: Callable[..., tuple[dict[str, Any], dict[str, str]]],
) -> dict[str, str]:
    _, headers = register_and_login()
    return headers


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
