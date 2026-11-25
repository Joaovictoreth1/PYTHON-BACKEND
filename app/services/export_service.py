"""Serviço de exportação de tarefas em background (CSV / JSON)."""

from __future__ import annotations

import csv
import io
import json

from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.models import ExportFormat, ExportStatus, TaskModel
from app.repositories.export_repository import ExportRepository
from app.repositories.task_repository import TaskRepository
from app.schemas.export import ExportResponse

logger = get_logger("exports")


def _serialize_tasks(tasks: list[TaskModel], fmt: ExportFormat) -> str:
    rows = [
        {
            "id": t.id,
            "project_id": t.project_id,
            "title": t.title,
            "description": t.description or "",
            "status": t.status.value,
            "priority": t.priority.value,
            "assignee": t.assignee or "",
            "due_date": t.due_date.isoformat() if t.due_date else "",
            "completed_at": t.completed_at.isoformat() if t.completed_at else "",
            "tags": ",".join(sorted(tag.name for tag in t.tags)),
            "version": t.version,
        }
        for t in tasks
    ]
    if fmt == ExportFormat.JSON:
        return json.dumps(rows, ensure_ascii=False)

    buf = io.StringIO()
    fieldnames = [
        "id",
        "project_id",
        "title",
        "description",
        "status",
        "priority",
        "assignee",
        "due_date",
        "completed_at",
        "tags",
        "version",
    ]
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def run_export_job(
    session_factory: sessionmaker[Session], export_id: int, user_id: int
) -> None:
    """Executa geração da exportação em sessão própria (background task)."""
    db = session_factory()
    try:
        exports = ExportRepository(db)
        job = exports.get(user_id, export_id)
        if job is None:
            return
        tasks = TaskRepository(db).list_all_for_user(user_id)
        content = _serialize_tasks(tasks, job.export_format)
        exports.mark_completed(job, content)
        logger.info("Exportação concluída | id=%d | tarefas=%d", export_id, len(tasks))
    except Exception:
        db.rollback()
        job = ExportRepository(db).get(user_id, export_id)
        if job is not None:
            ExportRepository(db).mark_failed(job)
        logger.error("Falha na exportação em background | id=%d", export_id)
    finally:
        db.close()


class ExportService:
    def __init__(self, db: Session) -> None:
        self.repo = ExportRepository(db)

    def create(self, user_id: int, fmt: ExportFormat) -> ExportResponse:
        job = self.repo.create(user_id, fmt)
        logger.info("Exportação enfileirada | id=%d | formato=%s", job.id, fmt.value)
        return ExportResponse.model_validate(job)

    def list(self, user_id: int, skip: int, limit: int) -> list[ExportResponse]:
        return [ExportResponse.model_validate(j) for j in self.repo.list(user_id, skip, limit)]

    def get(self, user_id: int, export_id: int) -> ExportResponse:
        job = self.repo.get(user_id, export_id)
        if job is None:
            raise NotFoundError(f"Exportação {export_id} não encontrada.")
        return ExportResponse.model_validate(job)

    def download(self, user_id: int, export_id: int) -> tuple[str, str, str]:
        job = self.repo.get(user_id, export_id)
        if job is None:
            raise NotFoundError(f"Exportação {export_id} não encontrada.")
        if job.status != ExportStatus.COMPLETED or job.content is None:
            raise ConflictError(f"Exportação {export_id} ainda não está pronta ({job.status.value}).")
        if job.export_format == ExportFormat.JSON:
            return "application/json", f"tasks-{job.id}.json", job.content
        return "text/csv; charset=utf-8", f"tasks-{job.id}.csv", job.content
