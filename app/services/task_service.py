"""Regras de negócio de tarefas."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.models import TaskModel
from app.repositories.project_repository import ProjectRepository
from app.repositories.task_repository import TaskFilters, TaskRepository
from app.schemas.task import PaginatedTaskResponse, TaskCreate, TaskResponse, TaskUpdate

logger = get_logger("tasks")


class TaskService:
    def __init__(self, db: Session) -> None:
        self.repo = TaskRepository(db)
        self.projects = ProjectRepository(db)

    def _get_or_404(self, task_id: int) -> TaskModel:
        task = self.repo.get(task_id)
        if task is None:
            raise NotFoundError(f"Tarefa {task_id} não encontrada.")
        return task

    def _ensure_project_exists(self, project_id: int | None) -> None:
        if project_id is not None and not self.projects.exists(project_id):
            raise NotFoundError(f"Projeto ID {project_id} não encontrado.")

    def create(self, data: TaskCreate) -> TaskResponse:
        self._ensure_project_exists(data.project_id)
        task = self.repo.add(**data.model_dump())
        logger.info("Tarefa criada | id=%d", task.id)
        return TaskResponse.model_validate(task)

    def list(self, filters: TaskFilters, skip: int, limit: int) -> PaginatedTaskResponse:
        total, items = self.repo.list(filters, skip, limit)
        return PaginatedTaskResponse(
            total=total,
            skip=skip,
            limit=limit,
            items=[TaskResponse.model_validate(t) for t in items],
        )

    def get(self, task_id: int) -> TaskResponse:
        return TaskResponse.model_validate(self._get_or_404(task_id))

    def update(self, task_id: int, data: TaskUpdate) -> TaskResponse:
        task = self._get_or_404(task_id)
        changes = data.model_dump(exclude_unset=True)
        if "project_id" in changes:
            self._ensure_project_exists(changes["project_id"])
        task = self.repo.update(task, changes)
        logger.info("Tarefa atualizada | id=%d | campos=%s", task.id, sorted(changes))
        return TaskResponse.model_validate(task)

    def delete(self, task_id: int) -> None:
        task = self._get_or_404(task_id)
        self.repo.delete(task)
        logger.info("Tarefa removida | id=%d", task_id)
