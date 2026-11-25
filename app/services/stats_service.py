"""Indicadores consolidados."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.types import utcnow
from app.repositories.project_repository import ProjectRepository
from app.repositories.task_repository import TaskRepository
from app.schemas.common import StatsResponse


class StatsService:
    def __init__(self, db: Session) -> None:
        self.projects = ProjectRepository(db)
        self.tasks = TaskRepository(db)

    def dashboard(self) -> StatsResponse:
        return StatsResponse(
            total_projects=self.projects.count(),
            total_tasks=self.tasks.count(),
            overdue_tasks=self.tasks.count_overdue(utcnow()),
            by_status=self.tasks.count_by_status(),
            by_priority=self.tasks.count_by_priority(),
        )
