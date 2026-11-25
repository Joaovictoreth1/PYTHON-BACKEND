from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


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
