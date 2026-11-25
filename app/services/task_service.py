"""Regras de negócio de tarefas."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.db.types import utcnow
from app.models import TagModel, TaskModel, TaskStatus
from app.repositories.project_repository import ProjectRepository
from app.repositories.tag_repository import TagRepository
from app.repositories.task_repository import TaskFilters, TaskRepository
from app.schemas.task import PaginatedTaskResponse, TaskCreate, TaskResponse, TaskUpdate

logger = get_logger("tasks")


class TaskService:
    def __init__(self, db: Session) -> None:
        self.repo = TaskRepository(db)
        self.projects = ProjectRepository(db)
        self.tags = TagRepository(db)

    def _get_or_404(self, task_id: int) -> TaskModel:
        task = self.repo.get(task_id)
        if task is None:
            raise NotFoundError(f"Tarefa {task_id} não encontrada.")
        return task

    def _ensure_project_exists(self, project_id: int | None) -> None:
        if project_id is not None and not self.projects.exists(project_id):
            raise NotFoundError(f"Projeto ID {project_id} não encontrado.")

    def _resolve_tags(self, tag_ids: list[int]) -> list[TagModel]:
        if not tag_ids:
            return []
        found = self.tags.get_many(tag_ids)
        found_ids = {t.id for t in found}
        missing = [tid for tid in tag_ids if tid not in found_ids]
        if missing:
            raise NotFoundError(f"Tag(s) não encontrada(s): {missing}.")
        return found

    def create(self, data: TaskCreate) -> TaskResponse:
        self._ensure_project_exists(data.project_id)
        tags = self._resolve_tags(data.tag_ids)
        payload = data.model_dump(exclude={"tag_ids"})
        if payload.get("status") == TaskStatus.CONCLUIDA:
            payload["completed_at"] = utcnow()
        task = self.repo.add(tags=tags, **payload)
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

        expected_version = changes.pop("version", None)
        if expected_version is not None and task.version != expected_version:
            raise ConflictError(
                f"Conflito de versão: esperado {expected_version}, atual {task.version}."
            )

        if "project_id" in changes:
            self._ensure_project_exists(changes["project_id"])

        new_tags: list[TagModel] | None = None
        if "tag_ids" in changes:
            new_tags = self._resolve_tags(changes.pop("tag_ids"))

        if "status" in changes:
            new_status = changes["status"]
            if new_status == TaskStatus.CONCLUIDA and task.status != TaskStatus.CONCLUIDA:
                changes["completed_at"] = utcnow()
            elif new_status != TaskStatus.CONCLUIDA and task.status == TaskStatus.CONCLUIDA:
                changes["completed_at"] = None

        task = self.repo.update(task, changes, tags=new_tags)
        logger.info("Tarefa atualizada | id=%d | versao=%d", task.id, task.version)
        return TaskResponse.model_validate(task)

    def delete(self, task_id: int) -> None:
        task = self._get_or_404(task_id)
        self.repo.delete(task)
        logger.info("Tarefa removida | id=%d", task_id)
