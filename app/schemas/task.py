from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import TaskPriority, TaskStatus
from app.schemas.tag import TagResponse

_STRIP = ConfigDict(str_strip_whitespace=True)


class TaskSortField(str, Enum):
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    DUE_DATE = "due_date"
    PRIORITY = "priority"
    TITLE = "title"


class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"


def _validate_tag_ids(value: list[int]) -> list[int]:
    if any(tag_id < 1 for tag_id in value):
        raise ValueError("tag_ids deve conter apenas inteiros positivos")
    return list(dict.fromkeys(value))


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
    tag_ids: list[int] = Field(default_factory=list, max_length=20)

    @field_validator("tag_ids")
    @classmethod
    def check_tag_ids(cls, v: list[int]) -> list[int]:
        return _validate_tag_ids(v)


class TaskUpdate(BaseModel):
    """Atualização parcial; campos obrigatórios não aceitam `null`.

    Se `version` for informado, ativa optimistic locking (retorna 409 em caso de conflito).
    """

    model_config = _STRIP

    title: str | None = Field(None, min_length=3, max_length=150)
    description: str | None = Field(None, max_length=2000)
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    assignee: str | None = Field(None, max_length=100)
    due_date: datetime | None = None
    project_id: int | None = Field(None, ge=1)
    tag_ids: list[int] | None = Field(None, max_length=20)
    version: int | None = Field(None, ge=1, description="Versão esperada para optimistic locking")

    @field_validator("title", "status", "priority", "tag_ids", "version")
    @classmethod
    def required_not_null(cls, v: object) -> object:
        if v is None:
            raise ValueError("campo não pode ser nulo")
        return v

    @field_validator("tag_ids")
    @classmethod
    def check_tag_ids(cls, v: list[int] | None) -> list[int] | None:
        return _validate_tag_ids(v) if v is not None else None


class TaskResponse(TaskBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version: int
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    tags: list[TagResponse] = Field(default_factory=list)


class PaginatedTaskResponse(BaseModel):
    total: int
    skip: int
    limit: int
    items: list[TaskResponse]
