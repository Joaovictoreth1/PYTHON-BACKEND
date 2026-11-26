"""TaskFlow REST API for projects, tasks, and metrics."""

import logging
import secrets
import sqlite3
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager
from typing import Annotated, cast

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Path, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.security import APIKeyHeader
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from taskflow_config import Settings
from taskflow_models import (
    Base,
    HealthResponse,
    PaginatedTaskResponse,
    ProjectCreate,
    ProjectModel,
    ProjectResponse,
    StatsResponse,
    TaskCreate,
    TaskModel,
    TaskPriority,
    TaskResponse,
    TaskStatus,
    TaskUpdate,
    utc_now,
)
from taskflow_rate_limit import RateLimiter

logger = logging.getLogger("uvicorn.error").getChild("taskflow")
router = APIRouter()
PathId = Annotated[int, Path(gt=0)]


def get_db(request: Request) -> Iterator[Session]:
    sessions = cast("sessionmaker[Session]", request.app.state.sessions)
    with sessions() as db:
        yield db


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(request: Request, key: Annotated[str | None, Depends(api_key_header)]) -> None:
    configured_key = cast("bytes", request.app.state.api_secret_key)
    if key is None or not secrets.compare_digest(key.encode("utf-8"), configured_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chave de API (X-API-Key) ausente ou inválida.",
            headers={"WWW-Authenticate": "APIKey"},
        )


DbSession = Annotated[Session, Depends(get_db)]
protected = APIRouter(prefix="/api/v1", dependencies=[Depends(verify_api_key)])


@router.get("/health", tags=["Monitoramento"])
def health_check(db: DbSession) -> HealthResponse:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.warning("database_health_check_failed")
        raise HTTPException(status_code=503, detail="Banco de dados indisponível.") from None
    return HealthResponse(
        status="online", version="2.0.0", database="conectado", timestamp=utc_now()
    )


@protected.get("/stats", tags=["Monitoramento"])
def get_dashboard_stats(db: DbSession) -> StatsResponse:
    total_projects = db.scalar(select(func.count(ProjectModel.id))) or 0
    total_tasks = db.scalar(select(func.count(TaskModel.id))) or 0
    overdue_tasks = (
        db.scalar(
            select(func.count(TaskModel.id)).where(
                TaskModel.due_date < utc_now(),
                TaskModel.status.notin_([TaskStatus.CONCLUIDA, TaskStatus.CANCELADA]),
            )
        )
        or 0
    )
    statuses = db.execute(
        select(TaskModel.status, func.count(TaskModel.id)).group_by(TaskModel.status)
    )
    priorities = db.execute(
        select(TaskModel.priority, func.count(TaskModel.id)).group_by(TaskModel.priority)
    )
    return StatsResponse(
        total_projects=total_projects,
        total_tasks=total_tasks,
        overdue_tasks=overdue_tasks,
        by_status={task_status.value: count for task_status, count in statuses},
        by_priority={priority.value: count for priority, count in priorities},
    )


@protected.post("/projects", status_code=status.HTTP_201_CREATED, tags=["Projetos"])
def create_project(project_in: ProjectCreate, db: DbSession) -> ProjectResponse:
    project = ProjectModel(**project_in.model_dump())
    db.add(project)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if db.scalar(select(ProjectModel.id).where(ProjectModel.name == project_in.name)) is None:
            raise
        raise HTTPException(
            status_code=409, detail=f"Já existe um projeto chamado '{project_in.name}'."
        ) from None
    db.refresh(project)
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        created_at=project.created_at,
        task_count=0,
    )


@protected.get("/projects", tags=["Projetos"])
def list_projects(db: DbSession) -> list[ProjectResponse]:
    counts = (
        select(TaskModel.project_id, func.count(TaskModel.id).label("task_count"))
        .where(TaskModel.project_id.is_not(None))
        .group_by(TaskModel.project_id)
        .subquery()
    )
    projects = db.execute(
        select(ProjectModel, func.coalesce(counts.c.task_count, 0))
        .outerjoin(counts, ProjectModel.id == counts.c.project_id)
        .order_by(ProjectModel.created_at.desc(), ProjectModel.id.desc())
    )
    return [
        ProjectResponse(
            id=project.id,
            name=project.name,
            description=project.description,
            created_at=project.created_at,
            task_count=count,
        )
        for project, count in projects
    ]


def require_project(db: Session, project_id: int) -> ProjectModel:
    project = db.get(ProjectModel, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Projeto ID {project_id} não encontrado.")
    return project


@protected.delete(
    "/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Projetos"]
)
def delete_project(project_id: PathId, db: DbSession) -> None:
    db.delete(require_project(db, project_id))
    db.commit()


@protected.post(
    "/tasks", status_code=status.HTTP_201_CREATED, response_model=TaskResponse, tags=["Tarefas"]
)
def create_task(task_in: TaskCreate, db: DbSession) -> TaskModel:
    if task_in.project_id is not None:
        require_project(db, task_in.project_id)
    task = TaskModel(**task_in.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@protected.get("/tasks", tags=["Tarefas"])
def list_tasks(
    db: DbSession,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    status_filter: Annotated[TaskStatus | None, Query(alias="status")] = None,
    priority_filter: Annotated[TaskPriority | None, Query(alias="priority")] = None,
    project_id: Annotated[int | None, Query(gt=0)] = None,
    assignee: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    search: Annotated[str | None, Query(min_length=2, max_length=150)] = None,
) -> PaginatedTaskResponse:
    query = select(TaskModel)
    if status_filter is not None:
        query = query.where(TaskModel.status == status_filter)
    if priority_filter is not None:
        query = query.where(TaskModel.priority == priority_filter)
    if project_id is not None:
        query = query.where(TaskModel.project_id == project_id)
    if assignee is not None:
        query = query.where(TaskModel.assignee.icontains(assignee, autoescape=True))
    if search is not None:
        query = query.where(TaskModel.title.icontains(search, autoescape=True))

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.order_by(TaskModel.created_at.desc(), TaskModel.id.desc()).offset(skip).limit(limit)
    )
    return PaginatedTaskResponse(
        total=total,
        skip=skip,
        limit=limit,
        items=[TaskResponse.model_validate(item) for item in items],
    )


@protected.get("/tasks/{task_id}", response_model=TaskResponse, tags=["Tarefas"])
def get_task(task_id: PathId, db: DbSession) -> TaskModel:
    task = db.get(TaskModel, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Tarefa {task_id} não encontrada.")
    return task


@protected.patch("/tasks/{task_id}", response_model=TaskResponse, tags=["Tarefas"])
def update_task(task_id: PathId, task_in: TaskUpdate, db: DbSession) -> TaskModel:
    task = get_task(task_id, db)
    project_id = task_in.get("project_id")
    if project_id is not None:
        require_project(db, project_id)
    if task_in:
        for field, value in task_in.items():
            setattr(task, field, value)
        db.commit()
        db.refresh(task)
    return task


@protected.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Tarefas"])
def delete_task(task_id: PathId, db: DbSession) -> None:
    db.delete(get_task(task_id, db))
    db.commit()


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings if settings is not None else Settings.from_env()
    limiter = RateLimiter(config.rate_limit_max_requests, config.rate_limit_window_seconds)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        url = make_url(config.database_url)
        sqlite = url.get_backend_name() == "sqlite"
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False} if sqlite else {},
            poolclass=StaticPool if sqlite and url.database in (None, "", ":memory:") else None,
        )
        if sqlite:

            @event.listens_for(engine, "connect")
            def enable_foreign_keys(connection: sqlite3.Connection, _record: object) -> None:
                connection.execute("PRAGMA foreign_keys = ON").close()

        try:
            Base.metadata.create_all(engine)
            app.state.sessions = sessionmaker(engine)
            yield
        finally:
            engine.dispose()

    app = FastAPI(title="TaskFlow Backend API", version="2.0.0", lifespan=lifespan)
    app.state.api_secret_key = config.api_secret_key.encode("ascii")
    app.include_router(router)
    app.include_router(protected)

    @app.middleware("http")
    async def observe_and_throttle(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start = time.monotonic()
        client = request.client.host if request.client else "unknown"
        if request.url.path != "/health" and not limiter.allow(client, start):
            response: Response = JSONResponse(
                status_code=429, content={"detail": "Limite de requisições excedido."}
            )
        else:
            response = await call_next(request)
        elapsed_ms = (time.monotonic() - start) * 1000
        response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"
        logger.info(
            "request method=%s status=%d duration_ms=%.2f",
            request.method,
            response.status_code,
            elapsed_ms,
        )
        return response

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error("request_failed method=%s exception=%s", request.method, type(exc).__name__)
        return JSONResponse(status_code=500, content={"detail": "Erro interno no servidor"})

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.cors_allowed_origins),
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["X-API-Key", "Content-Type"],
    )
    return app
