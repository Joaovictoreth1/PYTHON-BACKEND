from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import SQLColumnExpression, delete, func, select, update
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from taskflow.models import Project, Task, TaskPriority, TaskStatus, utcnow
from taskflow.schemas import ProjectResponse, Sort, StatsResponse


@dataclass(frozen=True)
class TaskFilters:
    skip: int
    limit: int
    sort: Sort
    status: TaskStatus | None
    priority: TaskPriority | None
    project_id: int | None
    assignee: str | None
    search: str | None


def list_projects(
    db: Session, skip: int, limit: int | None, sort: Sort, search: str | None
) -> list[ProjectResponse]:
    order = _order(Project.created_at, Project.id, sort)
    page = select(Project).order_by(*order).offset(skip)
    if search:
        page = page.where(Project.name.icontains(search, autoescape=True))
    if limit is not None:
        page = page.limit(limit)
    projects = page.subquery()
    statement = (
        select(
            projects.c.id,
            projects.c.name,
            projects.c.description,
            projects.c.created_at,
            func.count(Task.id).label("task_count"),
        )
        .outerjoin(Task, Task.project_id == projects.c.id)
        .group_by(projects.c.id, projects.c.name, projects.c.description, projects.c.created_at)
        .order_by(*_order(projects.c.created_at, projects.c.id, sort))
    )
    return [ProjectResponse.model_validate(dict(row)) for row in db.execute(statement).mappings()]


def _order(
    created: SQLColumnExpression[datetime], identifier: SQLColumnExpression[int], sort: Sort
) -> tuple[SQLColumnExpression[datetime], SQLColumnExpression[int]]:
    if sort == "newest":
        return created.desc(), identifier.desc()
    return created, identifier


def remove_project(db: Session, project_id: int) -> bool:
    return (
        db.scalar(delete(Project).where(Project.id == project_id).returning(Project.id)) is not None
    )


def list_tasks(db: Session, filters: TaskFilters) -> tuple[int, list[Task]]:
    conditions: list[ColumnElement[bool]] = []
    if filters.status is not None:
        conditions.append(Task.status == filters.status)
    if filters.priority is not None:
        conditions.append(Task.priority == filters.priority)
    if filters.project_id is not None:
        conditions.append(Task.project_id == filters.project_id)
    if filters.assignee:
        conditions.append(Task.assignee.icontains(filters.assignee, autoescape=True))
    if filters.search:
        conditions.append(Task.title.icontains(filters.search, autoescape=True))

    order = _order(Task.created_at, Task.id, filters.sort)
    page = (
        select(Task).where(*conditions).order_by(*order).offset(filters.skip).limit(filters.limit)
    )
    total = db.scalar(select(func.count()).select_from(Task).where(*conditions)) or 0
    return total, list(db.scalars(page))


def patch_task(
    db: Session, task_id: int, changes: dict[str, object], expected: datetime | None
) -> Task | None:
    query = update(Task).where(Task.id == task_id)
    if expected is not None:
        query = query.where(Task.updated_at == expected)
    query = query.values(**changes, updated_at=utcnow()).returning(Task)
    return db.scalar(query, execution_options={"populate_existing": True})


def remove_task(db: Session, task_id: int) -> bool:
    return db.scalar(delete(Task).where(Task.id == task_id).returning(Task.id)) is not None


def stats(db: Session) -> StatsResponse:
    status = {
        key.value: count
        for key, count in db.execute(select(Task.status, func.count()).group_by(Task.status))
    }
    priority = {
        key.value: count
        for key, count in db.execute(select(Task.priority, func.count()).group_by(Task.priority))
    }
    overdue = (
        select(func.count())
        .select_from(Task)
        .where(
            Task.due_date < utcnow(),
            Task.status.not_in((TaskStatus.CONCLUIDA, TaskStatus.CANCELADA)),
        )
    )
    return StatsResponse(
        total_projects=db.scalar(select(func.count()).select_from(Project)) or 0,
        total_tasks=sum(status.values()),
        overdue_tasks=db.scalar(overdue) or 0,
        by_status=status,
        by_priority=priority,
    )
