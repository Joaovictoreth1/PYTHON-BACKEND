"""Fábrica da aplicação FastAPI."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import VERSION, Settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RateLimiter, build_http_middleware
from app.db.session import build_engine, build_session_factory, init_db
from app.routers import health, projects, stats, tasks

logger = get_logger()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.validate()
    configure_logging(settings.log_level)

    engine = build_engine(settings.database_url)
    init_db(engine)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info("TaskFlow API v%s iniciada | ambiente=%s", VERSION, settings.environment)
        yield
        engine.dispose()

    app = FastAPI(
        title="TaskFlow Backend API",
        description="API RESTful corporativa com projetos, tarefas, métricas e rate limiting.",
        version=VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = build_session_factory(engine)

    allow_all = "*" in settings.cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=not allow_all,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-API-Key"],
        expose_headers=["X-Process-Time-Ms"],
    )
    limiter = RateLimiter(settings.rate_limit_max_requests, settings.rate_limit_window_seconds)
    app.middleware("http")(build_http_middleware(limiter))

    register_exception_handlers(app)
    for router in (health.router, stats.router, projects.router, tasks.router):
        app.include_router(router)

    return app
