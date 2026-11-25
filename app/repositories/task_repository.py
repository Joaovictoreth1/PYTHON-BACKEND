"""Acesso a dados de tarefas."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models import CLOSED_STATUSES, TaskModel, TaskPriority, TaskStatus


@dataclass(frozen=True)
class TaskFilters:
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    project_id: int | None = None
    assignee: str | None = None
    search: str | None = None


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class TaskRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, task_id: int) -> TaskModel | None:
        return self.db.get(TaskModel, task_id)

    def _apply_filters(self, stmt: Select[Any], filters: TaskFilters) -> Select[Any]:
        if filters.status:
            stmt = stmt.where(TaskModel.status == filters.status)
        if filters.priority:
            stmt = stmt.where(TaskModel.priority == filters.priority)
        if filters.project_id is not None:
            stmt = stmt.where(TaskModel.project_id == filters.project_id)
        if filters.assignee:
            stmt = stmt.where(
                TaskModel.assignee.ilike(f"%{_escape_like(filters.assignee)}%", escape="\\")
            )
        if filters.search:
            stmt = stmt.where(
                TaskModel.title.ilike(f"%{_escape_like(filters.search)}%", escape="\\")
            )
        return stmt

    def list(self, filters: TaskFilters, skip: int, limit: int) -> tuple[int, list[TaskModel]]:
        total_stmt = self._apply_filters(select(func.count(TaskModel.id)), filters)
        total = self.db.scalar(total_stmt) or 0
        items_stmt = (
            self._apply_filters(select(TaskModel), filters)
            .order_by(TaskModel.created_at.desc(), TaskModel.id.desc())
            .offset(skip)
            .limit(limit)
        )
        return total, list(self.db.scalars(items_stmt).all())

    def count(self) -> int:
        return self.db.scalar(select(func.count(TaskModel.id))) or 0

    def count_overdue(self, now: datetime) -> int:
        stmt = select(func.count(TaskModel.id)).where(
            TaskModel.due_date.is_not(None),
            TaskModel.due_date < now,
            TaskModel.status.not_in(CLOSED_STATUSES),
        )
        return self.db.scalar(stmt) or 0

    def count_by_status(self) -> dict[str, int]:
        stmt = select(TaskModel.status, func.count(TaskModel.id)).group_by(TaskModel.status)
        return {row[0].value: row[1] for row in self.db.execute(stmt).all()}

    def count_by_priority(self) -> dict[str, int]:
        stmt = select(TaskModel.priority, func.count(TaskModel.id)).group_by(TaskModel.priority)
        return {row[0].value: row[1] for row in self.db.execute(stmt).all()}

    def add(self, **data: Any) -> TaskModel:
        task = TaskModel(**data)
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def update(self, task: TaskModel, data: dict[str, Any]) -> TaskModel:
        for field, value in data.items():
            setattr(task, field, value)
        self.db.commit()
        self.db.refresh(task)
        return task

    def delete(self, task: TaskModel) -> None:
        self.db.delete(task)
        self.db.commit()
