"""Regras de negócio de comentários em tarefas."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.repositories.comment_repository import CommentRepository
from app.repositories.task_repository import TaskRepository
from app.schemas.comment import CommentCreate, CommentResponse

logger = get_logger("comments")


class CommentService:
    def __init__(self, db: Session) -> None:
        self.repo = CommentRepository(db)
        self.tasks = TaskRepository(db)

    def _ensure_task_exists(self, task_id: int) -> None:
        if self.tasks.get(task_id) is None:
            raise NotFoundError(f"Tarefa {task_id} não encontrada.")

    def create(self, task_id: int, data: CommentCreate) -> CommentResponse:
        self._ensure_task_exists(task_id)
        comment = self.repo.add(task_id=task_id, author=data.author, body=data.body)
        logger.info("Comentário criado | id=%d | task_id=%d", comment.id, task_id)
        return CommentResponse.model_validate(comment)

    def list_by_task(self, task_id: int, skip: int, limit: int) -> list[CommentResponse]:
        self._ensure_task_exists(task_id)
        return [
            CommentResponse.model_validate(c)
            for c in self.repo.list_by_task(task_id, skip=skip, limit=limit)
        ]

    def delete(self, task_id: int, comment_id: int) -> None:
        self._ensure_task_exists(task_id)
        comment = self.repo.get(comment_id)
        if comment is None or comment.task_id != task_id:
            raise NotFoundError(f"Comentário {comment_id} não encontrado na tarefa {task_id}.")
        self.repo.delete(comment)
        logger.info("Comentário removido | id=%d | task_id=%d", comment_id, task_id)
