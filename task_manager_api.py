"""
TaskFlow Backend API v2.0
=========================
API RESTful profissional construída com FastAPI, SQLAlchemy (SQLite) e Pydantic v2.

Recursos incluídos:
- Arquitetura relacional (Projetos 1:N Tarefas) com exclusão em cascata.
- Segurança via X-API-Key com comparação em tempo constante (secrets.compare_digest).
- Middleware de Rate Limiting por IP e Observabilidade (tempo de resposta nos headers).
- Paginação, filtros combinados, busca textual e endpoint de métricas (/api/v1/stats).
- Suíte de testes automatizados integrada (roda ao executar `python task_manager_api.py`).
"""

import logging
import os
import secrets
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Generator, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import (
    Column,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    func,
    text,
)
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

# ==============================================================================
# 1. LOGGING E CONFIGURAÇÕES GERAIS
# ==============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("taskflow_api")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./taskflow_v2.db")
API_SECRET_KEY = os.getenv("API_SECRET_KEY", "dev-secret-key-2026")
RATE_LIMIT_MAX_REQUESTS = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "120"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ==============================================================================
# 2. ENUMS E MODELOS RELACIONAIS (ORM)
# ==============================================================================

class TaskStatus(str, Enum):
    PENDENTE = "pendente"
    EM_ANDAMENTO = "em_andamento"
    REVISAO = "revisao"
    CONCLUIDA = "concluida"
    CANCELADA = "cancelada"


class TaskPriority(str, Enum):
    BAIXA = "baixa"
    MEDIA = "media"
    ALTA = "alta"
    URGENTE = "urgente"


class ProjectModel(Base):
    """Tabela de projetos que agrupam múltiplas tarefas (Relacionamento 1:N)."""
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(120), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    tasks = relationship(
        "TaskModel",
        back_populates="project",
        cascade="all, delete-orphan",
    )


class TaskModel(Base):
    """Tabela principal de tarefas."""
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    title = Column(String(150), nullable=False, index=True)
    description = Column(Text, nullable=True)
    status = Column(
        SQLEnum(TaskStatus),
        default=TaskStatus.PENDENTE,
        nullable=False,
        index=True,
    )
    priority = Column(
        SQLEnum(TaskPriority),
        default=TaskPriority.MEDIA,
        nullable=False,
        index=True,
    )
    assignee = Column(String(100), nullable=True, index=True)
    due_date = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    project = relationship("ProjectModel", back_populates="tasks")


Base.metadata.create_all(bind=engine)


# ==============================================================================
# 3. SCHEMAS PYDANTIC v2 (VALIDAÇÃO E SERIALIZAÇÃO)
# ==============================================================================

class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=120, description="Nome único do projeto")
    description: Optional[str] = Field(None, max_length=1000, description="Descrição do escopo")

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        return v.strip()


class ProjectResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    created_at: datetime
    task_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class TaskBase(BaseModel):
    title: str = Field(..., min_length=3, max_length=150, description="Título da tarefa")
    description: Optional[str] = Field(None, max_length=2000, description="Detalhes técnicos")
    status: TaskStatus = Field(default=TaskStatus.PENDENTE)
    priority: TaskPriority = Field(default=TaskPriority.MEDIA)
    assignee: Optional[str] = Field(None, max_length=100, description="Responsável")
    due_date: Optional[datetime] = Field(None, description="Prazo final em formato ISO 8601")
    project_id: Optional[int] = Field(None, description="ID do projeto associado")

    @field_validator("title", "assignee")
    @classmethod
    def strip_whitespace(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if isinstance(v, str) else v


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=150)
    description: Optional[str] = Field(None, max_length=2000)
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    assignee: Optional[str] = Field(None, max_length=100)
    due_date: Optional[datetime] = None
    project_id: Optional[int] = None


class TaskResponse(TaskBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaginatedTaskResponse(BaseModel):
    total: int
    skip: int
    limit: int
    items: List[TaskResponse]


class StatsResponse(BaseModel):
    total_projects: int
    total_tasks: int
    overdue_tasks: int
    by_status: Dict[str, int]
    by_priority: Dict[str, int]


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    timestamp: datetime


# ==============================================================================
# 4. DEPENDÊNCIAS (SESSÃO DB E SEGURANÇA)
# ==============================================================================

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def verify_api_key(x_api_key: str = Header(..., description="Chave secreta X-API-Key")):
    """Valida a chave da API em tempo constante para prevenir timing attacks."""
    if not secrets.compare_digest(x_api_key, API_SECRET_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chave de API (X-API-Key) inválida.",
        )
    return x_api_key


# ==============================================================================
# 5. APLICAÇÃO FASTAPI E MIDDLEWARES (OBSERVABILIDADE + RATE LIMIT)
# ==============================================================================

app = FastAPI(
    title="TaskFlow Backend API",
    description="API RESTful corporativa com projetos, tarefas, métricas e rate limiting.",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_request_history: Dict[str, List[float]] = defaultdict(list)


@app.middleware("http")
async def observability_and_rate_limit_middleware(request: Request, call_next):
    """Controla limite de requisições por IP e mede tempo de resposta."""
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()

    # Limpa registros fora da janela de tempo
    _request_history[client_ip] = [
        ts for ts in _request_history[client_ip] if now - ts < RATE_LIMIT_WINDOW_SECONDS
    ]

    if len(_request_history[client_ip]) >= RATE_LIMIT_MAX_REQUESTS:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Limite de requisições excedido. Tente novamente em instantes."},
        )

    _request_history[client_ip].append(now)

    start_time = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start_time) * 1000

    response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"
    logger.info(
        "%s %s | Status: %d | IP: %s | Tempo: %.2fms",
        request.method,
        request.url.path,
        response.status_code,
        client_ip,
        elapsed_ms,
    )
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Erro não tratado em %s: %s", request.url.path, str(exc))
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Erro interno no servidor", "path": request.url.path},
    )


# ==============================================================================
# 6. ROTAS DE MONITORAMENTO E MÉTRICAS
# ==============================================================================

@app.get("/health", response_model=HealthResponse, tags=["Monitoramento"])
def health_check(db: Session = Depends(get_db)):
    """Verifica disponibilidade da API e conexão com o banco."""
    db.execute(text("SELECT 1"))
    return HealthResponse(
        status="online",
        version="2.0.0",
        database="conectado",
        timestamp=datetime.now(timezone.utc),
    )


@app.get(
    "/api/v1/stats",
    response_model=StatsResponse,
    tags=["Monitoramento"],
    dependencies=[Depends(verify_api_key)],
)
def get_dashboard_stats(db: Session = Depends(get_db)):
    """Retorna indicadores consolidados de projetos e tarefas."""
    total_projects = db.query(func.count(ProjectModel.id)).scalar() or 0
    total_tasks = db.query(func.count(TaskModel.id)).scalar() or 0

    now_utc = datetime.now(timezone.utc)
    overdue_tasks = (
        db.query(func.count(TaskModel.id))
        .filter(
            TaskModel.due_date.isnot(None),
            TaskModel.due_date < now_utc,
            TaskModel.status.notin_([TaskStatus.CONCLUIDA, TaskStatus.CANCELADA]),
        )
        .scalar()
        or 0
    )

    status_rows = (
        db.query(TaskModel.status, func.count(TaskModel.id))
        .group_by(TaskModel.status)
        .all()
    )
    priority_rows = (
        db.query(TaskModel.priority, func.count(TaskModel.id))
        .group_by(TaskModel.priority)
        .all()
    )

    return StatsResponse(
        total_projects=total_projects,
        total_tasks=total_tasks,
        overdue_tasks=overdue_tasks,
        by_status={row[0].value: row[1] for row in status_rows},
        by_priority={row[0].value: row[1] for row in priority_rows},
    )


# ==============================================================================
# 7. ROTAS DE PROJETOS (CRUD)
# ==============================================================================

@app.post(
    "/api/v1/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Projetos"],
    dependencies=[Depends(verify_api_key)],
)
def create_project(project_in: ProjectCreate, db: Session = Depends(get_db)):
    existing = db.query(ProjectModel).filter(ProjectModel.name == project_in.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Já existe um projeto chamado '{project_in.name}'.",
        )

    project = ProjectModel(**project_in.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)

    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        created_at=project.created_at,
        task_count=0,
    )


@app.get(
    "/api/v1/projects",
    response_model=List[ProjectResponse],
    tags=["Projetos"],
    dependencies=[Depends(verify_api_key)],
)
def list_projects(db: Session = Depends(get_db)):
    projects = db.query(ProjectModel).order_by(ProjectModel.created_at.desc()).all()
    return [
        ProjectResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            created_at=p.created_at,
            task_count=len(p.tasks),
        )
        for p in projects
    ]


@app.delete(
    "/api/v1/projects/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Projetos"],
    dependencies=[Depends(verify_api_key)],
)
def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
    db.delete(project)
    db.commit()
    return None


# ==============================================================================
# 8. ROTAS DE TAREFAS (CRUD + FILTROS + PAGINAÇÃO)
# ==============================================================================

@app.post(
    "/api/v1/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Tarefas"],
    dependencies=[Depends(verify_api_key)],
)
def create_task(task_in: TaskCreate, db: Session = Depends(get_db)):
    if task_in.project_id is not None:
        project = db.query(ProjectModel).filter(ProjectModel.id == task_in.project_id).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Projeto ID {task_in.project_id} não encontrado.",
            )

    new_task = TaskModel(**task_in.model_dump())
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    return new_task


@app.get(
    "/api/v1/tasks",
    response_model=PaginatedTaskResponse,
    tags=["Tarefas"],
    dependencies=[Depends(verify_api_key)],
)
def list_tasks(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    status_filter: Optional[TaskStatus] = Query(None, alias="status"),
    priority_filter: Optional[TaskPriority] = Query(None, alias="priority"),
    project_id: Optional[int] = Query(None),
    assignee: Optional[str] = Query(None),
    search: Optional[str] = Query(None, min_length=2),
    db: Session = Depends(get_db),
):
    query = db.query(TaskModel)

    if status_filter:
        query = query.filter(TaskModel.status == status_filter)
    if priority_filter:
        query = query.filter(TaskModel.priority == priority_filter)
    if project_id is not None:
        query = query.filter(TaskModel.project_id == project_id)
    if assignee:
        query = query.filter(TaskModel.assignee.ilike(f"%{assignee}%"))
    if search:
        query = query.filter(TaskModel.title.ilike(f"%{search}%"))

    total = query.count()
    items = query.order_by(TaskModel.created_at.desc()).offset(skip).limit(limit).all()

    return PaginatedTaskResponse(total=total, skip=skip, limit=limit, items=items)


@app.get(
    "/api/v1/tasks/{task_id}",
    response_model=TaskResponse,
    tags=["Tarefas"],
    dependencies=[Depends(verify_api_key)],
)
def get_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Tarefa {task_id} não encontrada.")
    return task


@app.patch(
    "/api/v1/tasks/{task_id}",
    response_model=TaskResponse,
    tags=["Tarefas"],
    dependencies=[Depends(verify_api_key)],
)
def update_task(task_id: int, task_in: TaskUpdate, db: Session = Depends(get_db)):
    task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Tarefa {task_id} não encontrada.")

    update_data = task_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(task, field, value)

    task.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(task)
    return task


@app.delete(
    "/api/v1/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Tarefas"],
    dependencies=[Depends(verify_api_key)],
)
def delete_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Tarefa {task_id} não encontrada.")
    db.delete(task)
    db.commit()
    return None


# ==============================================================================
# 9. SUÍTE DE TESTES AUTOMATIZADOS INTEGRADA
# ==============================================================================

def run_integration_tests():
    from fastapi.testclient import TestClient

    print("\n=== Executando Suíte de Testes TaskFlow API v2.0 ===\n")
    client = TestClient(app)
    headers = {"X-API-Key": API_SECRET_KEY}

    # 1. Health Check
    res = client.get("/health")
    assert res.status_code == 200
    assert "X-Process-Time-Ms" in res.headers
    print(f"[OK] 1. Health Check operacional (Tempo: {res.headers['X-Process-Time-Ms']}ms)")

    # 2. Bloqueio de segurança
    res_unauth = client.get("/api/v1/tasks", headers={"X-API-Key": "chave-errada"})
    assert res_unauth.status_code == 401
    print("[OK] 2. Segurança X-API-Key validada.")

    # 3. Criação de Projeto
    proj_name = f"Plataforma Core {int(time.time())}"
    res_proj = client.post(
        "/api/v1/projects",
        json={"name": proj_name, "description": "Infraestrutura backend"},
        headers=headers,
    )
    assert res_proj.status_code == 201
    project_id = res_proj.json()["id"]
    print(f"[OK] 3. Projeto criado (ID: {project_id} | Nome: '{proj_name}')")

    # 4. Criação de Tarefa associada ao Projeto
    res_task = client.post(
        "/api/v1/tasks",
        json={
            "title": "Configurar pipeline CI/CD",
            "priority": "urgente",
            "assignee": "João Victor",
            "project_id": project_id,
        },
        headers=headers,
    )
    assert res_task.status_code == 201
    task_id = res_task.json()["id"]
    print(f"[OK] 4. Tarefa criada no projeto (ID: {task_id})")

    # 5. Endpoint de Métricas
    res_stats = client.get("/api/v1/stats", headers=headers)
    assert res_stats.status_code == 200
    print(f"[OK] 5. Dashboard de métricas: {res_stats.json()}")

    # 6. Atualização parcial
    res_patch = client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"status": "concluida"},
        headers=headers,
    )
    assert res_patch.status_code == 200
    assert res_patch.json()["status"] == "concluida"
    print("[OK] 6. Tarefa atualizada para 'concluida'.")

    # 7. Exclusão em cascata do Projeto
    res_del = client.delete(f"/api/v1/projects/{project_id}", headers=headers)
    assert res_del.status_code == 204
    res_check = client.get(f"/api/v1/tasks/{task_id}", headers=headers)
    assert res_check.status_code == 404
    print("[OK] 7. Exclusão em cascata (Projeto -> Tarefas) validada.")

    print("\nTodos os 7 testes passaram! Para iniciar o servidor web:")
    print("uvicorn task_manager_api:app --reload\n")


if __name__ == "__main__":
    try:
        run_integration_tests()
    except ImportError as exc:
        print(f"Erro: dependência ausente ({exc}). Instale com: pip install -r requirements.txt")
        sys.exit(1)
