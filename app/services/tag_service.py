"""Regras de negócio de tags."""

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

    def create(self, data: TagCreate) -> TagResponse:
        if self.repo.get_by_name(data.name) is not None:
            raise ConflictError(f"Já existe uma tag chamada '{data.name}'.")
        tag = self.repo.add(name=data.name, color=data.color)
        logger.info("Tag criada | id=%d", tag.id)
        return TagResponse.model_validate(tag)

    def list(self, skip: int, limit: int) -> list[TagResponse]:
        return [TagResponse.model_validate(t) for t in self.repo.list(skip, limit)]

    def delete(self, tag_id: int) -> None:
        tag = self.repo.get(tag_id)
        if tag is None:
            raise NotFoundError(f"Tag {tag_id} não encontrada.")
        self.repo.delete(tag)
        logger.info("Tag removida | id=%d", tag_id)
