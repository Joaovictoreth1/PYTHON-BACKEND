from datetime import datetime, timezone
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from typing_extensions import TypedDict


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


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
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    tasks: Mapped[list["TaskModel"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )


class TaskModel(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(150), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[TaskStatus] = mapped_column(
        SQLEnum(TaskStatus), default=TaskStatus.PENDENTE, index=True
    )
    priority: Mapped[TaskPriority] = mapped_column(
        SQLEnum(TaskPriority), default=TaskPriority.MEDIA, index=True
    )
    assignee: Mapped[str | None] = mapped_column(String(100), index=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    project: Mapped[ProjectModel | None] = relationship(back_populates="tasks")


Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=150)]
Assignee = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]
TaskDescription = Annotated[str, Field(max_length=2000)]
PositiveId = Annotated[int, Field(gt=0)]


class ProjectCreate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=120)]
    description: str | None = Field(None, max_length=1000)


class ProjectResponse(BaseModel):
    id: int
    name: str
    description: str | None
    created_at: datetime
    task_count: int


class TaskCreate(BaseModel):
    title: Title
    description: TaskDescription | None = None
    status: TaskStatus = TaskStatus.PENDENTE
    priority: TaskPriority = TaskPriority.MEDIA
    assignee: Assignee | None = None
    due_date: datetime | None = None
    project_id: PositiveId | None = None


class TaskUpdate(TypedDict, total=False):
    title: Title
    description: TaskDescription | None
    status: TaskStatus
    priority: TaskPriority
    assignee: Assignee | None
    due_date: datetime | None
    project_id: PositiveId | None


class TaskResponse(TaskCreate):
    title: str
    project_id: int | None = None
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaginatedTaskResponse(BaseModel):
    total: int
    skip: int
    limit: int
    items: list[TaskResponse]


class StatsResponse(BaseModel):
    total_projects: int
    total_tasks: int
    overdue_tasks: int
    by_status: dict[str, int]
    by_priority: dict[str, int]


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    timestamp: datetime
