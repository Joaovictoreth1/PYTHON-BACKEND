"""Middlewares de rate limiting por IP e observabilidade."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

logger = get_logger("http")


class RateLimiter:
    """Janela deslizante em memória (por processo)."""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._history: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        history = self._history[key]
        while history and now - history[0] >= self.window_seconds:
            history.popleft()
        if len(history) >= self.max_requests:
            return False
        history.append(now)
        return True


def build_http_middleware(
    limiter: RateLimiter,
) -> Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]:
    async def middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        client_ip = request.client.host if request.client else "unknown"

        if not limiter.allow(client_ip):
            logger.warning("Rate limit excedido | %s %s", request.method, request.url.path)
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Limite de requisições excedido. Tente novamente em instantes."},
                headers={"Retry-After": str(limiter.window_seconds)},
            )

        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"
        logger.info(
            "%s %s | Status: %d | Tempo: %.2fms",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response

    return middleware
