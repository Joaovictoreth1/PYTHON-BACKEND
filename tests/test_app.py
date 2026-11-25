from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from app.core.config import DEFAULT_DEV_API_KEY, ConfigError, Settings
from app.core.middleware import RateLimiter
from app.main import create_app
from tests.conftest import make_settings


def test_health_has_timing_header(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "online"
    assert "X-Process-Time-Ms" in res.headers


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "chave-errada"}, {"X-API-Key": ""}])
def test_protected_routes_require_api_key(client, headers):
    for path in ("/api/v1/tasks", "/api/v1/projects", "/api/v1/stats"):
        res = client.get(path, headers=headers)
        assert res.status_code == 401, path
        assert res.headers["WWW-Authenticate"] == "ApiKey"


def test_rate_limit_returns_429():
    app = create_app(make_settings(rate_limit_max_requests=2))
    with TestClient(app) as c:
        assert c.get("/health").status_code == 200
        assert c.get("/health").status_code == 200
        res = c.get("/health")
    assert res.status_code == 429
    assert res.headers["Retry-After"] == "60"


def test_rate_limiter_window_slides():
    limiter = RateLimiter(max_requests=1, window_seconds=10)
    assert limiter.allow("ip", now=0)
    assert not limiter.allow("ip", now=5)
    assert limiter.allow("other", now=5)
    assert limiter.allow("ip", now=10)


def test_unexpected_error_returns_500_without_leaking_details(client, auth, caplog, monkeypatch):
    from app.services import task_service

    def boom(*_args, **_kwargs):
        raise RuntimeError("segredo-do-usuario")

    monkeypatch.setattr(task_service.TaskService, "get", boom)
    with caplog.at_level(logging.ERROR, logger="taskflow_api"):
        res = client.get("/api/v1/tasks/1", headers=auth)
    assert res.status_code == 500
    assert res.json() == {"error": "Erro interno no servidor", "path": "/api/v1/tasks/1"}
    assert "segredo-do-usuario" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_api_key_is_not_logged(client, auth, caplog):
    with caplog.at_level(logging.DEBUG):
        client.get("/api/v1/tasks", headers=auth)
        client.get("/api/v1/tasks", headers={"X-API-Key": "chave-errada-xyz"})
    assert auth["X-API-Key"] not in caplog.text
    assert "chave-errada-xyz" not in caplog.text


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("API_SECRET_KEY", "x" * 32)
    monkeypatch.setenv("CORS_ORIGINS", "https://a.com, https://b.com,")
    monkeypatch.setenv("RATE_LIMIT_MAX_REQUESTS", "5")
    settings = Settings.from_env()
    assert settings.cors_origins == ["https://a.com", "https://b.com"]
    assert settings.rate_limit_max_requests == 5
    assert "x" * 32 not in repr(settings)


@pytest.mark.parametrize(
    "env",
    [
        {"ENVIRONMENT": "production"},
        {"API_SECRET_KEY": "curta"},
        {"RATE_LIMIT_MAX_REQUESTS": "abc"},
        {"RATE_LIMIT_WINDOW_SECONDS": "0"},
    ],
)
def test_settings_reject_invalid_config(monkeypatch, env):
    monkeypatch.delenv("API_SECRET_KEY", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(ConfigError):
        Settings.from_env()


def test_default_dev_key_allowed_outside_production(monkeypatch):
    monkeypatch.delenv("API_SECRET_KEY", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    assert Settings.from_env().api_secret_key == DEFAULT_DEV_API_KEY


def test_cors_wildcard_disables_credentials(client):
    res = client.options(
        "/api/v1/tasks",
        headers={"Origin": "https://qualquer.com", "Access-Control-Request-Method": "GET"},
    )
    assert res.headers.get("access-control-allow-origin") == "*"
    assert "access-control-allow-credentials" not in res.headers
