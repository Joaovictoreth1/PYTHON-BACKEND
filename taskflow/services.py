from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from taskflow import repositories
from taskflow.models import Project, Task
from taskflow.repositories import TaskFilters
from taskflow.schemas import (
    PaginatedTaskResponse,
    ProjectCreate,
    ProjectResponse,
    Sort,
    StatsResponse,
    TaskCreate,
    TaskResponse,
    TaskUpdate,
)


def list_projects(
    db: Session, skip: int, limit: int | None, sort: Sort, search: str | None
) -> list[ProjectResponse]:
    return repositories.list_projects(db, skip, limit, sort, search)


def list_tasks(db: Session, filters: TaskFilters) -> PaginatedTaskResponse:
    total, items = repositories.list_tasks(db, filters)
    return PaginatedTaskResponse(
        total=total,
        skip=filters.skip,
        limit=filters.limit,
        items=[TaskResponse.model_validate(task) for task in items],
    )


def stats(db: Session) -> StatsResponse:
    return repositories.stats(db)


def create_project(db: Session, data: ProjectCreate) -> ProjectResponse:
    project = Project(**data.model_dump())
    db.add(project)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"Já existe um projeto chamado '{data.name}'.") from None
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        created_at=project.created_at,
        task_count=0,
    )


def delete_project(db: Session, project_id: int) -> None:
    if not repositories.remove_project(db, project_id):
        raise HTTPException(404, "Projeto não encontrado.")
    db.commit()


def check_project(db: Session, project_id: int | None) -> None:
    if project_id is not None and db.get(Project, project_id) is None:
        raise HTTPException(404, f"Projeto ID {project_id} não encontrado.")


def create_task(db: Session, data: TaskCreate) -> Task:
    check_project(db, data.project_id)
    task = Task(**data.model_dump())
    db.add(task)
    db.commit()
    return task


def get_task(db: Session, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(404, f"Tarefa {task_id} não encontrada.")
    return task


def update_task(db: Session, task_id: int, data: TaskUpdate, expected: datetime | None) -> Task:
    changes = data.model_dump(exclude_unset=True)
    if "project_id" in changes:
        get_task(db, task_id)
        check_project(db, data.project_id)
    updated = repositories.patch_task(db, task_id, changes, expected)
    if updated is None:
        get_task(db, task_id)
        raise HTTPException(412, "A tarefa foi alterada desde a versão informada.")
    db.commit()
    return updated


def delete_task(db: Session, task_id: int) -> None:
    if not repositories.remove_task(db, task_id):
        raise HTTPException(404, f"Tarefa {task_id} não encontrada.")
    db.commit()
