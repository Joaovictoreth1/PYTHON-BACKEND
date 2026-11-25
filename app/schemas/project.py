from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

_STRIP = ConfigDict(str_strip_whitespace=True)


class ProjectCreate(BaseModel):
    model_config = _STRIP

    name: str = Field(..., min_length=3, max_length=120, description="Nome único do projeto")
    description: str | None = Field(None, max_length=1000, description="Descrição do escopo")


class ProjectUpdate(BaseModel):
    model_config = _STRIP

    name: str | None = Field(None, min_length=3, max_length=120)
    description: str | None = Field(None, max_length=1000)

    @field_validator("name")
    @classmethod
    def name_not_null(cls, v: str | None) -> str:
        if v is None:
            raise ValueError("name não pode ser nulo")
        return v


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    created_at: datetime
    task_count: int = 0
