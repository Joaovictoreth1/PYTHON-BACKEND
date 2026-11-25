from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.core.config import DEFAULT_DEV_SECRET_KEY, ConfigError, Settings
from app.core.logging import JsonFormatter
from app.core.middleware import RateLimiter
from app.main import create_app
from tests.conftest import make_settings


def test_health_has_timing_header(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "online"
    assert "X-Process-Time-Ms" in res.headers


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer token-invalido"}, {"Authorization": "Basic abc"}],
)
def test_protected_routes_require_bearer_jwt(client, headers):
    for path in ("/api/v1/tasks", "/api/v1/projects", "/api/v1/stats", "/api/v1/auth/me"):
        res = client.get(path, headers=headers)
        assert res.status_code == 401, path
        assert res.headers["WWW-Authenticate"] == "Bearer"


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
    body = res.json()
    assert body["code"] == "internal_error"
    assert body["error"] == "Erro interno no servidor"
    assert body["path"] == "/api/v1/tasks/1"
    assert len(body["request_id"]) == 32
    assert "segredo-do-usuario" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_bearer_token_is_not_logged(client, auth, caplog):
    with caplog.at_level(logging.DEBUG):
        client.get("/api/v1/tasks", headers=auth)
        client.get("/api/v1/tasks", headers={"Authorization": "Bearer segredo-invalido-xyz"})
    assert auth["Authorization"] not in caplog.text
    assert "segredo-invalido-xyz" not in caplog.text


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    monkeypatch.setenv("CORS_ORIGINS", "https://a.com, https://b.com,")
    monkeypatch.setenv("RATE_LIMIT_MAX_REQUESTS", "5")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
    monkeypatch.setenv("REFRESH_TOKEN_EXPIRE_DAYS", "14")
    settings = Settings.from_env()
    assert settings.cors_origins == ["https://a.com", "https://b.com"]
    assert settings.rate_limit_max_requests == 5
    assert settings.access_token_expire_minutes == 30
    assert settings.refresh_token_expire_days == 14
    assert "x" * 40 not in repr(settings)


@pytest.mark.parametrize(
    "env",
    [
        {"ENVIRONMENT": "production"},
        {"SECRET_KEY": "curta-demais"},
        {"RATE_LIMIT_MAX_REQUESTS": "abc"},
        {"RATE_LIMIT_WINDOW_SECONDS": "0"},
        {"ACCESS_TOKEN_EXPIRE_MINUTES": "0"},
        {"REFRESH_TOKEN_EXPIRE_DAYS": "-1"},
    ],
)
def test_settings_reject_invalid_config(monkeypatch, env):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(ConfigError):
        Settings.from_env()


def test_default_dev_key_allowed_outside_production(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    assert Settings.from_env().secret_key == DEFAULT_DEV_SECRET_KEY


def test_cors_wildcard_disables_credentials(client):
    res = client.options(
        "/api/v1/tasks",
        headers={"Origin": "https://qualquer.com", "Access-Control-Request-Method": "GET"},
    )
    assert res.headers.get("access-control-allow-origin") == "*"
    assert "access-control-allow-credentials" not in res.headers


def test_liveness_and_readiness_probes(client, monkeypatch):
    live = client.get("/health/live")
    assert live.status_code == 200
    assert live.json()["status"] == "alive"

    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["database"] == "conectado"

    from sqlalchemy.exc import OperationalError
    from sqlalchemy.orm import Session

    def fail_execute(*_args, **_kwargs):
        raise OperationalError("SELECT 1", {}, Exception("down"))

    monkeypatch.setattr(Session, "execute", fail_execute)
    down = client.get("/health/ready")
    assert down.status_code == 503
    assert down.json()["code"] == "service_unavailable"
    assert "request_id" in down.json()


def test_request_id_and_security_headers(client, auth):
    res = client.get("/api/v1/tasks", headers={**auth, "X-Request-ID": "req-abc_123"})
    assert res.status_code == 200
    assert res.headers["X-Request-ID"] == "req-abc_123"
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "DENY"
    assert res.headers["Referrer-Policy"] == "no-referrer"
    assert res.headers["Cache-Control"] == "no-store"
    assert "X-RateLimit-Limit" in res.headers
    assert "X-RateLimit-Remaining" in res.headers
    assert "X-RateLimit-Reset" in res.headers

    bad = client.get("/health/live", headers={"X-Request-ID": "bad\nheader"})
    assert bad.headers["X-Request-ID"] != "bad\nheader"
    assert len(bad.headers["X-Request-ID"]) == 32


def test_trust_proxy_headers_isolates_rate_limit():
    app = create_app(make_settings(rate_limit_max_requests=1, trust_proxy_headers=True))
    with TestClient(app) as c:
        assert c.get("/health/live", headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 200
        assert c.get("/health/live", headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 429
        assert c.get("/health/live", headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 200


def test_rate_limiter_evicts_stale_keys():
    limiter = RateLimiter(max_requests=2, window_seconds=10)
    assert limiter.allow("old-ip", now=0)
    assert limiter.allow("new-ip", now=20)
    assert "old-ip" not in limiter._history


def test_json_log_formatter():
    record = logging.LogRecord(
        name="taskflow_api.http",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="GET /health | Status: %d",
        args=(200,),
        exc_info=None,
    )
    parsed = json.loads(JsonFormatter().format(record))
    assert parsed["level"] == "INFO"
    assert parsed["message"] == "GET /health | Status: 200"
    assert "request_id" in parsed
    assert "timestamp" in parsed


def test_settings_extra_validation(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "xml")
    with pytest.raises(ConfigError):
        Settings.from_env()

    monkeypatch.setenv("LOG_FORMAT", "json")
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "maybe")
    with pytest.raises(ConfigError):
        Settings.from_env()

    monkeypatch.setenv("TRUST_PROXY_HEADERS", "true")
    monkeypatch.setenv("AUTO_CREATE_TABLES", "false")
    s = Settings.from_env()
    assert s.log_format == "json"
    assert s.trust_proxy_headers is True
    assert s.auto_create_tables is False
