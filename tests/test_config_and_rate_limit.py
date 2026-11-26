import secrets

import pytest

from task_manager_api import create_app
from taskflow_config import Settings
from taskflow_rate_limit import RateLimiter


@pytest.mark.parametrize("value", ["", "too-short", "a" * 32 + " ", "é" * 32])
def test_missing_or_bad_key_fails_fast(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("API_SECRET_KEY", value)
    with pytest.raises(ValueError, match="API_SECRET_KEY"):
        create_app()


@pytest.mark.parametrize("value", ["0", "-5", "invalid"])
def test_invalid_rate_limit(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("API_SECRET_KEY", secrets.token_hex(32))
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", value)
    with pytest.raises(ValueError, match="RATE_LIMIT_WINDOW_SECONDS"):
        Settings.from_env()


def test_wildcard_cors_is_not_allowed() -> None:
    with pytest.raises(ValueError, match="CORS_ALLOWED_ORIGINS"):
        Settings(api_secret_key=secrets.token_hex(32), cors_allowed_origins=("*",))


def test_rate_limits_expire_and_are_independent() -> None:
    limiter = RateLimiter(max_requests=2, window=10)
    assert limiter.allow("a", 0)
    assert limiter.allow("a", 1)
    assert not limiter.allow("a", 2)
    assert limiter.allow("b", 2)
    assert limiter.allow("a", 10)
    assert not limiter.allow("a", 10.5)
    assert limiter.allow("c", 12)
    assert "b" not in limiter.history
    assert limiter.allow("a", 12)
