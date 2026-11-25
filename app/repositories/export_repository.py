"""Acesso a dados de exportações assíncronas de tarefas."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.types import utcnow
from app.models import ExportFormat, ExportStatus, TaskExportModel


class ExportRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, user_id: int, export_format: ExportFormat) -> TaskExportModel:
        job = TaskExportModel(
            user_id=user_id,
            export_format=export_format,
            status=ExportStatus.PENDING,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def get(self, user_id: int, export_id: int) -> TaskExportModel | None:
        stmt = select(TaskExportModel).where(
            TaskExportModel.id == export_id, TaskExportModel.user_id == user_id
        )
        return self.db.scalar(stmt)

    def list(self, user_id: int, skip: int, limit: int) -> list[TaskExportModel]:
        stmt = (
            select(TaskExportModel)
            .where(TaskExportModel.user_id == user_id)
            .order_by(TaskExportModel.created_at.desc(), TaskExportModel.id.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def mark_completed(self, job: TaskExportModel, content: str) -> TaskExportModel:
        job.status = ExportStatus.COMPLETED
        job.content = content
        job.completed_at = utcnow()
        self.db.commit()
        self.db.refresh(job)
        return job

    def mark_failed(self, job: TaskExportModel) -> TaskExportModel:
        job.status = ExportStatus.FAILED
        job.completed_at = utcnow()
        self.db.commit()
        self.db.refresh(job)
        return job
