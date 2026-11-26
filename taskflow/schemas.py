from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints, field_validator

from taskflow.database import as_utc
from taskflow.models import TaskPriority, TaskStatus

ProjectName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=120)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=150)]
Assignee = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]
ProjectDescription = Annotated[str, StringConstraints(max_length=1000)]
TaskDescription = Annotated[str, StringConstraints(max_length=2000)]
DueDate = Annotated[datetime, AfterValidator(as_utc)]
Sort = Literal["newest", "oldest"]


class ProjectCreate(BaseModel):
    name: ProjectName
    description: ProjectDescription | None = None


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
    due_date: DueDate | None = None
    project_id: int | None = None


class TaskUpdate(BaseModel):
    title: Title | None = None
    description: TaskDescription | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    assignee: Assignee | None = None
    due_date: DueDate | None = None
    project_id: int | None = None

    @field_validator("title", "status", "priority", mode="before")
    @classmethod
    def reject_explicit_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("O campo não pode ser nulo.")
        return value


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    assignee: str | None
    due_date: datetime | None
    project_id: int | None
    created_at: datetime
    updated_at: datetime


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
