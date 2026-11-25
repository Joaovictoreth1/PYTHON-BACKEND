from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CommentCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    author: str = Field(..., min_length=2, max_length=100, description="Autor do comentário")
    body: str = Field(..., min_length=1, max_length=2000, description="Conteúdo do comentário")


class CommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    author: str
    body: str
    created_at: datetime
