from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


class TagCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=2, max_length=40, description="Nome único da tag")
    color: str = Field(default="#64748b", description="Cor hexadecimal (#RRGGBB)")

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        return v.lower()

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str) -> str:
        if not _HEX_COLOR.match(v):
            raise ValueError("cor deve estar no formato hexadecimal #RRGGBB")
        return v.lower()


class TagResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: str
    created_at: datetime
