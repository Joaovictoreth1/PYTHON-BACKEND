"""Acesso a dados de tarefas."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db.types import utcnow
from app.models import CLOSED_STATUSES, TagModel, TaskModel, TaskPriority, TaskStatus
from app.schemas.task import SortOrder, TaskSortField

_PRIORITY_RANK = case(
    (TaskModel.priority == TaskPriority.BAIXA, 1),
    (TaskModel.priority == TaskPriority.MEDIA, 2),
    (TaskModel.priority == TaskPriority.ALTA, 3),
    (TaskModel.priority == TaskPriority.URGENTE, 4),
    else_=0,
)


@dataclass(frozen=True)
class TaskFilters:
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    project_id: int | None = None
    assignee: str | None = None
    search: str | None = None
    tag: str | None = None
    overdue: bool | None = None
    due_before: datetime | None = None
    due_after: datetime | None = None
    sort_by: TaskSortField = TaskSortField.CREATED_AT
    sort_order: SortOrder = SortOrder.DESC


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _order_clauses(sort_by: TaskSortField, sort_order: SortOrder) -> list[Any]:
    asc = sort_order == SortOrder.ASC
    if sort_by == TaskSortField.PRIORITY:
        primary: Any = _PRIORITY_RANK.asc() if asc else _PRIORITY_RANK.desc()
        return [primary, TaskModel.id.desc()]
    if sort_by == TaskSortField.DUE_DATE:
        col = TaskModel.due_date.asc() if asc else TaskModel.due_date.desc()
        # Tarefas sem prazo ficam sempre por último.
        return [TaskModel.due_date.is_(None).asc(), col, TaskModel.id.desc()]

    column_map = {
        TaskSortField.CREATED_AT: TaskModel.created_at,
        TaskSortField.UPDATED_AT: TaskModel.updated_at,
        TaskSortField.TITLE: func.lower(TaskModel.title),
    }
    target = column_map[sort_by]
    return [target.asc() if asc else target.desc(), TaskModel.id.desc()]


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
        if filters.tag:
            stmt = stmt.where(TaskModel.tags.any(TagModel.name == filters.tag.strip().lower()))
        if filters.due_before is not None:
            stmt = stmt.where(
                TaskModel.due_date.is_not(None), TaskModel.due_date <= filters.due_before
            )
        if filters.due_after is not None:
            stmt = stmt.where(
                TaskModel.due_date.is_not(None), TaskModel.due_date >= filters.due_after
            )
        if filters.overdue is True:
            now = utcnow()
            stmt = stmt.where(
                TaskModel.due_date.is_not(None),
                TaskModel.due_date < now,
                TaskModel.status.not_in(CLOSED_STATUSES),
            )
        elif filters.overdue is False:
            now = utcnow()
            stmt = stmt.where(
                or_(
                    TaskModel.due_date.is_(None),
                    TaskModel.due_date >= now,
                    TaskModel.status.in_(CLOSED_STATUSES),
                )
            )
        return stmt

    def list(self, filters: TaskFilters, skip: int, limit: int) -> tuple[int, list[TaskModel]]:
        total_stmt = self._apply_filters(select(func.count(TaskModel.id)), filters)
        total = self.db.scalar(total_stmt) or 0
        items_stmt = (
            self._apply_filters(select(TaskModel).options(selectinload(TaskModel.tags)), filters)
            .order_by(*_order_clauses(filters.sort_by, filters.sort_order))
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

    def add(self, tags: Sequence[TagModel], **data: Any) -> TaskModel:
        task = TaskModel(**data)
        task.tags = list(tags)
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def update(
        self,
        task: TaskModel,
        data: dict[str, Any],
        tags: Sequence[TagModel] | None = None,
    ) -> TaskModel:
        for field, value in data.items():
            setattr(task, field, value)
        if tags is not None:
            task.tags = list(tags)
        task.version += 1
        self.db.commit()
        self.db.refresh(task)
        return task

    def delete(self, task: TaskModel) -> None:
        self.db.delete(task)
        self.db.commit()
