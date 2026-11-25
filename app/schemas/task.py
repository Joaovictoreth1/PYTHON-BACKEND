from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import TaskPriority, TaskStatus

_STRIP = ConfigDict(str_strip_whitespace=True)


class TaskBase(BaseModel):
    model_config = _STRIP

    title: str = Field(..., min_length=3, max_length=150, description="Título da tarefa")
    description: str | None = Field(None, max_length=2000, description="Detalhes técnicos")
    status: TaskStatus = Field(default=TaskStatus.PENDENTE)
    priority: TaskPriority = Field(default=TaskPriority.MEDIA)
    assignee: str | None = Field(None, max_length=100, description="Responsável")
    due_date: datetime | None = Field(None, description="Prazo final em formato ISO 8601")
    project_id: int | None = Field(None, ge=1, description="ID do projeto associado")


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    """Atualização parcial; campos obrigatórios não aceitam `null`."""

    model_config = _STRIP

    title: str | None = Field(None, min_length=3, max_length=150)
    description: str | None = Field(None, max_length=2000)
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    assignee: str | None = Field(None, max_length=100)
    due_date: datetime | None = None
    project_id: int | None = Field(None, ge=1)

    @field_validator("title", "status", "priority")
    @classmethod
    def required_not_null(cls, v: object) -> object:
        if v is None:
            raise ValueError("campo não pode ser nulo")
        return v


class TaskResponse(TaskBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class PaginatedTaskResponse(BaseModel):
    total: int
    skip: int
    limit: int
    items: list[TaskResponse]
