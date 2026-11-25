"""Regras de negócio de tags com isolamento por usuário."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.repositories.tag_repository import TagRepository
from app.schemas.tag import TagCreate, TagResponse

logger = get_logger("tags")


class TagService:
    def __init__(self, db: Session) -> None:
        self.repo = TagRepository(db)

    def create(self, user_id: int, data: TagCreate) -> TagResponse:
        if self.repo.get_by_name(user_id, data.name) is not None:
            raise ConflictError(f"Já existe uma tag chamada '{data.name}'.")
        tag = self.repo.add(user_id=user_id, name=data.name, color=data.color)
        logger.info("Tag criada | id=%d | user_id=%d", tag.id, user_id)
        return TagResponse.model_validate(tag)

    def list(self, user_id: int, skip: int, limit: int) -> list[TagResponse]:
        return [TagResponse.model_validate(t) for t in self.repo.list(user_id, skip, limit)]

    def delete(self, user_id: int, tag_id: int) -> None:
        tag = self.repo.get(user_id, tag_id)
        if tag is None:
            raise NotFoundError(f"Tag {tag_id} não encontrada.")
        self.repo.delete(tag)
        logger.info("Tag removida | id=%d | user_id=%d", tag_id, user_id)
