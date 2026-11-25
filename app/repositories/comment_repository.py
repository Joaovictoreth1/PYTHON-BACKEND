"""Acesso a dados de comentários em tarefas."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TaskCommentModel


class CommentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, comment_id: int) -> TaskCommentModel | None:
        return self.db.get(TaskCommentModel, comment_id)

    def list_by_task(self, task_id: int, skip: int, limit: int) -> list[TaskCommentModel]:
        stmt = (
            select(TaskCommentModel)
            .where(TaskCommentModel.task_id == task_id)
            .order_by(TaskCommentModel.created_at.asc(), TaskCommentModel.id.asc())
            .offset(skip)
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def add(self, task_id: int, author: str, body: str) -> TaskCommentModel:
        comment = TaskCommentModel(task_id=task_id, author=author, body=body)
        self.db.add(comment)
        self.db.commit()
        self.db.refresh(comment)
        return comment

    def delete(self, comment: TaskCommentModel) -> None:
        self.db.delete(comment)
        self.db.commit()
