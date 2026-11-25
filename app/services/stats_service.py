"""Indicadores consolidados por usuário."""

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

    def dashboard(self, user_id: int) -> StatsResponse:
        return StatsResponse(
            total_projects=self.projects.count(user_id),
            total_tasks=self.tasks.count(user_id),
            overdue_tasks=self.tasks.count_overdue(user_id, utcnow()),
            by_status=self.tasks.count_by_status(user_id),
            by_priority=self.tasks.count_by_priority(user_id),
        )
