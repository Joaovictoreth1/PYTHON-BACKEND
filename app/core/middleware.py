"""Middlewares de Request ID, rate limiting (in-memory ou Redis com fallback) e segurança."""

from __future__ import annotations

import math
import re
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

import redis
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse

from app.core.config import Settings
from app.core.context import reset_request_id, set_request_id
from app.core.logging import get_logger

logger = get_logger("http")

_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_EVICT_THRESHOLD = 1024


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_seconds: int


class RateLimiterProtocol(Protocol):
    def check(self, key: str) -> RateLimitResult: ...


class RateLimiter:
    """Janela deslizante em memória (por processo) com limpeza de chaves expiradas."""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._history: dict[str, deque[float]] = defaultdict(deque)
        self._last_eviction: float = 0.0

    def _evict_stale(self, now: float) -> None:
        if len(self._history) < _EVICT_THRESHOLD and now - self._last_eviction < self.window_seconds:
            return
        self._last_eviction = now
        stale_keys = [
            key
            for key, hist in self._history.items()
            if not hist or now - hist[-1] >= self.window_seconds
        ]
        for key in stale_keys:
            del self._history[key]

    def check(self, key: str, now: float | None = None) -> RateLimitResult:
        now = time.monotonic() if now is None else now
        self._evict_stale(now)

        history = self._history[key]
        while history and now - history[0] >= self.window_seconds:
            history.popleft()

        if len(history) >= self.max_requests:
            retry_after = max(1, math.ceil(self.window_seconds - (now - history[0])))
            return RateLimitResult(
                allowed=False,
                limit=self.max_requests,
                remaining=0,
                reset_seconds=retry_after,
            )

        history.append(now)
        remaining = max(0, self.max_requests - len(history))
        reset_after = max(1, math.ceil(self.window_seconds - (now - history[0])))
        return RateLimitResult(
            allowed=True,
            limit=self.max_requests,
            remaining=remaining,
            reset_seconds=reset_after,
        )

    def allow(self, key: str, now: float | None = None) -> bool:
        return self.check(key, now=now).allowed


class RedisRateLimiter:
    """Rate limiter distribuído em janela deslizante via Redis ZSET com fallback em memória."""

    def __init__(
        self,
        redis_client: redis.Redis,
        max_requests: int,
        window_seconds: int,
        fallback: RateLimiter | None = None,
    ) -> None:
        self._redis = redis_client
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._fallback = fallback or RateLimiter(max_requests, window_seconds)

    def check(self, key: str) -> RateLimitResult:
        now = time.time()
        window_start = now - self.window_seconds
        redis_key = f"taskflow:rl:{key}"
        member = f"{now}:{uuid.uuid4().hex}"
        try:
            pipe = self._redis.pipeline()
            pipe.zremrangebyscore(redis_key, 0, window_start)
            pipe.zcard(redis_key)
            _, current_count = pipe.execute()
            count = int(current_count)
            if count >= self.max_requests:
                return RateLimitResult(
                    allowed=False,
                    limit=self.max_requests,
                    remaining=0,
                    reset_seconds=self.window_seconds,
                )
            write_pipe = self._redis.pipeline()
            write_pipe.zadd(redis_key, {member: now})
            write_pipe.expire(redis_key, self.window_seconds)
            write_pipe.execute()
            return RateLimitResult(
                allowed=True,
                limit=self.max_requests,
                remaining=max(0, self.max_requests - count - 1),
                reset_seconds=self.window_seconds,
            )
        except redis.RedisError:
            logger.warning("Redis indisponível para rate limit; usando fallback em memória")
            return self._fallback.check(key)


def build_rate_limiter(settings: Settings) -> RateLimiterProtocol:
    fallback = RateLimiter(settings.rate_limit_max_requests, settings.rate_limit_window_seconds)
    if not settings.redis_url:
        return fallback
    client = redis.Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=1.0,
        socket_timeout=1.0,
        decode_responses=True,
    )
    logger.info("Rate limiter configurado com Redis (fallback em memória ativo)")
    return RedisRateLimiter(
        redis_client=client,
        max_requests=settings.rate_limit_max_requests,
        window_seconds=settings.rate_limit_window_seconds,
        fallback=fallback,
    )


def _resolve_request_id(request: Request) -> str:
    incoming = request.headers.get("X-Request-ID", "").strip()
    if incoming and _SAFE_REQUEST_ID.match(incoming):
        return incoming
    return uuid.uuid4().hex


def _resolve_client_ip(request: Request, trust_proxy_headers: bool) -> str:
    if trust_proxy_headers:
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            first_hop = forwarded.split(",")[0].strip()
            if first_hop:
                return first_hop
    return request.client.host if request.client else "unknown"


def _apply_common_headers(
    response: Response,
    request_id: str,
    rl: RateLimitResult,
    path: str,
) -> None:
    response.headers["X-Request-ID"] = request_id
    response.headers["X-RateLimit-Limit"] = str(rl.limit)
    response.headers["X-RateLimit-Remaining"] = str(rl.remaining)
    response.headers["X-RateLimit-Reset"] = str(rl.reset_seconds)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"


def build_http_middleware(
    limiter: RateLimiterProtocol,
    trust_proxy_headers: bool = False,
) -> Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]:
    async def middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = _resolve_request_id(request)
        request.state.request_id = request_id
        token = set_request_id(request_id)
        try:
            client_ip = _resolve_client_ip(request, trust_proxy_headers)
            rl = limiter.check(client_ip)

            if not rl.allowed:
                logger.warning("Rate limit excedido | %s %s", request.method, request.url.path)
                resp: Response = JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "code": "rate_limit_exceeded",
                        "detail": "Limite de requisições excedido. Tente novamente em instantes.",
                        "request_id": request_id,
                    },
                    headers={"Retry-After": str(rl.reset_seconds)},
                )
                _apply_common_headers(resp, request_id, rl, request.url.path)
                return resp

            start = time.perf_counter()
            response = await call_next(request)
            elapsed_ms = (time.perf_counter() - start) * 1000
            response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"
            _apply_common_headers(response, request_id, rl, request.url.path)
            logger.info(
                "%s %s | Status: %d | Tempo: %.2fms",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
            )
            return response
        finally:
            reset_request_id(token)

    return middleware
