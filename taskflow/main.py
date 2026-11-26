from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware

from taskflow import errors, services
from taskflow.config import Settings
from taskflow.database import DB, make_engine
from taskflow.middleware import RateLimitPolicy, ResponsePolicy
from taskflow.models import Project, Task, utcnow
from taskflow.routers import projects, tasks
from taskflow.schemas import HealthResponse, StatsResponse
from taskflow.security import verify_api_key

VERSION = "2.0.0"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings()
    engine = make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            engine.dispose()

    app = FastAPI(title="TaskFlow Backend API", version=VERSION, lifespan=lifespan)
    app.state.settings = settings
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    app.add_exception_handler(StarletteHTTPException, errors.http_error)
    app.add_exception_handler(RequestValidationError, errors.validation_error)
    app.add_exception_handler(IntegrityError, errors.integrity_error)
    app.add_middleware(RateLimitPolicy, settings=settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["X-API-Key", "Content-Type", "If-Match"],
        expose_headers=["X-Process-Time-Ms", "ETag", "Retry-After"],
    )
    app.add_middleware(ResponsePolicy, settings=settings)

    @app.get("/health", tags=["Monitoramento"])
    def health(db: DB) -> HealthResponse:
        try:
            db.execute(select(Project.id).limit(1))
            db.execute(select(Task.id).limit(1))
        except SQLAlchemyError:
            raise HTTPException(503, "Banco de dados indisponível.") from None
        return HealthResponse(
            status="online", database="conectado", version=VERSION, timestamp=utcnow()
        )

    protected = APIRouter(prefix="/api/v1", dependencies=[Depends(verify_api_key)])
    protected.include_router(projects.router)
    protected.include_router(tasks.router)

    @protected.get("/stats", tags=["Monitoramento"])
    def stats(db: DB) -> StatsResponse:
        return services.stats(db)

    app.include_router(protected)
    return app
