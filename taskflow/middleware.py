import logging
import math
import time
from collections import OrderedDict, deque

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from taskflow.config import Settings
from taskflow.errors import error_response, internal_error

logger = logging.getLogger("taskflow")


class RateLimiter:
    def __init__(self, limit: int, window: int, max_clients: int) -> None:
        self.limit = limit
        self.window = window
        self.max_clients = max_clients
        self.clients: OrderedDict[str, deque[float]] = OrderedDict()

    def retry_after(self, client: str, now: float) -> int:
        cutoff = now - self.window
        while self.clients and next(iter(self.clients.values()))[-1] <= cutoff:
            self.clients.popitem(last=False)

        history = self.clients.get(client)
        if history is None:
            if len(self.clients) >= self.max_clients:
                retry = next(iter(self.clients.values()))[-1] + self.window - now
                return max(1, math.ceil(retry))
            history = self.clients[client] = deque()
        while history and history[0] <= cutoff:
            history.popleft()
        if len(history) >= self.limit:
            return max(1, math.ceil(history[0] + self.window - now))

        history.append(now)
        self.clients.move_to_end(client)
        return 0


class RateLimitPolicy(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        super().__init__(app)
        self.limiter = RateLimiter(
            settings.rate_limit_max_requests,
            settings.rate_limit_window_seconds,
            settings.rate_limit_max_clients,
        )

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        client = request.client.host if request.client else "unknown"
        retry = (
            0
            if request.url.path == "/health"
            else self.limiter.retry_after(client, time.monotonic())
        )
        if retry:
            return error_response(
                request,
                429,
                "Limite de requisições excedido. Tente novamente em instantes.",
                {"Retry-After": str(retry)},
            )
        try:
            return await call_next(request)
        except Exception as exc:
            return internal_error(request, exc)


class ResponsePolicy(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        super().__init__(app)
        self.log_level = getattr(logging, settings.log_level)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        started = time.monotonic()
        response = await call_next(request)
        elapsed = (time.monotonic() - started) * 1000
        response.headers["X-Process-Time-Ms"] = f"{elapsed:.2f}"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        if self.log_level <= logging.INFO:
            logger.info(
                "request method=%s status=%d elapsed_ms=%.2f",
                request.method,
                response.status_code,
                elapsed,
            )
        return response
