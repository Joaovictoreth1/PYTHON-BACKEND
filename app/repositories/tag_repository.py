"""Acesso a dados de tags."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TagModel


class TagRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, tag_id: int) -> TagModel | None:
        return self.db.get(TagModel, tag_id)

    def get_by_name(self, name: str) -> TagModel | None:
        return self.db.scalar(select(TagModel).where(TagModel.name == name))

    def get_many(self, tag_ids: list[int]) -> list[TagModel]:
        if not tag_ids:
            return []
        stmt = select(TagModel).where(TagModel.id.in_(tag_ids))
        return list(self.db.scalars(stmt).all())

    def list(self, skip: int, limit: int) -> list[TagModel]:
        stmt = select(TagModel).order_by(TagModel.name.asc()).offset(skip).limit(limit)
        return list(self.db.scalars(stmt).all())

    def add(self, name: str, color: str) -> TagModel:
        tag = TagModel(name=name, color=color)
        self.db.add(tag)
        self.db.commit()
        self.db.refresh(tag)
        return tag

    def delete(self, tag: TagModel) -> None:
        self.db.delete(tag)
        self.db.commit()
