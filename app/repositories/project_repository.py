"""Acesso a dados de projetos."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ProjectModel, TaskModel


class ProjectRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, project_id: int) -> ProjectModel | None:
        return self.db.get(ProjectModel, project_id)

    def get_by_name(self, name: str) -> ProjectModel | None:
        return self.db.scalar(select(ProjectModel).where(ProjectModel.name == name))

    def exists(self, project_id: int) -> bool:
        return self.get(project_id) is not None

    def count(self) -> int:
        return self.db.scalar(select(func.count(ProjectModel.id))) or 0

    def task_count(self, project_id: int) -> int:
        stmt = select(func.count(TaskModel.id)).where(TaskModel.project_id == project_id)
        return self.db.scalar(stmt) or 0

    def list_with_task_counts(self, skip: int, limit: int) -> list[tuple[ProjectModel, int]]:
        task_counts = (
            select(TaskModel.project_id, func.count(TaskModel.id).label("task_count"))
            .group_by(TaskModel.project_id)
            .subquery()
        )
        stmt = (
            select(ProjectModel, func.coalesce(task_counts.c.task_count, 0))
            .outerjoin(task_counts, task_counts.c.project_id == ProjectModel.id)
            .order_by(ProjectModel.created_at.desc(), ProjectModel.id.desc())
            .offset(skip)
            .limit(limit)
        )
        return [(project, int(count)) for project, count in self.db.execute(stmt).all()]

    def add(self, **data: Any) -> ProjectModel:
        project = ProjectModel(**data)
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
