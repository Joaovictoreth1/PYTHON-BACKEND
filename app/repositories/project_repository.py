"""Acesso a dados de projetos com isolamento por usuário."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ProjectModel, TaskModel


class ProjectRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, user_id: int, project_id: int) -> ProjectModel | None:
        stmt = select(ProjectModel).where(
            ProjectModel.id == project_id, ProjectModel.user_id == user_id
        )
        return self.db.scalar(stmt)

    def get_by_name(self, user_id: int, name: str) -> ProjectModel | None:
        stmt = select(ProjectModel).where(
            ProjectModel.user_id == user_id, ProjectModel.name == name
        )
        return self.db.scalar(stmt)

    def exists(self, user_id: int, project_id: int) -> bool:
        return self.get(user_id, project_id) is not None

    def count(self, user_id: int) -> int:
        stmt = select(func.count(ProjectModel.id)).where(ProjectModel.user_id == user_id)
        return self.db.scalar(stmt) or 0

    def task_count(self, user_id: int, project_id: int) -> int:
        stmt = select(func.count(TaskModel.id)).where(
            TaskModel.user_id == user_id, TaskModel.project_id == project_id
        )
        return self.db.scalar(stmt) or 0

    def list_with_task_counts(
        self, user_id: int, skip: int, limit: int
    ) -> list[tuple[ProjectModel, int]]:
        task_counts = (
            select(TaskModel.project_id, func.count(TaskModel.id).label("task_count"))
            .where(TaskModel.user_id == user_id)
            .group_by(TaskModel.project_id)
            .subquery()
        )
        stmt = (
            select(ProjectModel, func.coalesce(task_counts.c.task_count, 0))
            .outerjoin(task_counts, task_counts.c.project_id == ProjectModel.id)
            .where(ProjectModel.user_id == user_id)
            .order_by(ProjectModel.created_at.desc(), ProjectModel.id.desc())
            .offset(skip)
            .limit(limit)
        )
        return [(project, int(count)) for project, count in self.db.execute(stmt).all()]

    def add(self, user_id: int, **data: Any) -> ProjectModel:
        project = ProjectModel(user_id=user_id, **data)
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)
        return project

    def update(self, project: ProjectModel, data: dict[str, Any]) -> ProjectModel:
        for field, value in data.items():
            setattr(project, field, value)
        self.db.commit()
        self.db.refresh(project)
        return project

    def delete(self, project: ProjectModel) -> None:
        self.db.delete(project)
        self.db.commit()
