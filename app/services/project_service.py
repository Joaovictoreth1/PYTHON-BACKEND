"""Regras de negócio de projetos."""

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

    def _get_or_404(self, project_id: int) -> ProjectModel:
        project = self.repo.get(project_id)
        if project is None:
            raise NotFoundError("Projeto não encontrado.")
        return project

    def _ensure_unique_name(self, name: str, current_id: int | None = None) -> None:
        existing = self.repo.get_by_name(name)
        if existing is not None and existing.id != current_id:
            raise ConflictError(f"Já existe um projeto chamado '{name}'.")

    def create(self, data: ProjectCreate) -> ProjectResponse:
        self._ensure_unique_name(data.name)
        project = self.repo.add(**data.model_dump())
        logger.info("Projeto criado | id=%d", project.id)
        return _to_response(project, 0)

    def list(self, skip: int, limit: int) -> list[ProjectResponse]:
        return [_to_response(p, c) for p, c in self.repo.list_with_task_counts(skip, limit)]

    def get(self, project_id: int) -> ProjectResponse:
        project = self._get_or_404(project_id)
        return _to_response(project, self.repo.task_count(project.id))

    def update(self, project_id: int, data: ProjectUpdate) -> ProjectResponse:
        project = self._get_or_404(project_id)
        changes = data.model_dump(exclude_unset=True)
        if "name" in changes:
            self._ensure_unique_name(changes["name"], current_id=project.id)
        project = self.repo.update(project, changes)
        logger.info("Projeto atualizado | id=%d | campos=%s", project.id, sorted(changes))
        return _to_response(project, self.repo.task_count(project.id))

    def delete(self, project_id: int) -> None:
        project = self._get_or_404(project_id)
        self.repo.delete(project)
        logger.info("Projeto removido | id=%d", project_id)
