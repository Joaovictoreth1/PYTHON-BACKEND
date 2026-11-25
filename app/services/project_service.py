"""Regras de negócio de projetos com isolamento por usuário."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.models import ProjectModel
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate

logger = get_logger("projects")


def _to_response(project: ProjectModel, task_count: int) -> ProjectResponse:
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        created_at=project.created_at,
        task_count=task_count,
    )


class ProjectService:
    def __init__(self, db: Session) -> None:
        self.repo = ProjectRepository(db)

    def _get_or_404(self, user_id: int, project_id: int) -> ProjectModel:
        project = self.repo.get(user_id, project_id)
        if project is None:
            raise NotFoundError("Projeto não encontrado.")
        return project

    def _ensure_unique_name(self, user_id: int, name: str, current_id: int | None = None) -> None:
        existing = self.repo.get_by_name(user_id, name)
        if existing is not None and existing.id != current_id:
            raise ConflictError(f"Já existe um projeto chamado '{name}'.")

    def create(self, user_id: int, data: ProjectCreate) -> ProjectResponse:
        self._ensure_unique_name(user_id, data.name)
        project = self.repo.add(user_id, **data.model_dump())
        logger.info("Projeto criado | id=%d | user_id=%d", project.id, user_id)
        return _to_response(project, 0)

    def list(self, user_id: int, skip: int, limit: int) -> list[ProjectResponse]:
        return [
            _to_response(p, c) for p, c in self.repo.list_with_task_counts(user_id, skip, limit)
        ]

    def get(self, user_id: int, project_id: int) -> ProjectResponse:
        project = self._get_or_404(user_id, project_id)
        return _to_response(project, self.repo.task_count(user_id, project.id))

    def update(self, user_id: int, project_id: int, data: ProjectUpdate) -> ProjectResponse:
        project = self._get_or_404(user_id, project_id)
        changes = data.model_dump(exclude_unset=True)
        if "name" in changes:
            self._ensure_unique_name(user_id, changes["name"], current_id=project.id)
        project = self.repo.update(project, changes)
        logger.info("Projeto atualizado | id=%d | user_id=%d", project.id, user_id)
        return _to_response(project, self.repo.task_count(user_id, project.id))

    def delete(self, user_id: int, project_id: int) -> None:
        project = self._get_or_404(user_id, project_id)
        self.repo.delete(project)
        logger.info("Projeto removido | id=%d | user_id=%d", project_id, user_id)
