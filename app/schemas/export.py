from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import ExportFormat, ExportStatus


class ExportCreate(BaseModel):
    format: ExportFormat = ExportFormat.CSV


class ExportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    export_format: ExportFormat
    status: ExportStatus
    created_at: datetime
    completed_at: datetime | None
