"""Acesso a dados de tags com isolamento por usuário."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TagModel


class TagRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, user_id: int, tag_id: int) -> TagModel | None:
        stmt = select(TagModel).where(TagModel.id == tag_id, TagModel.user_id == user_id)
        return self.db.scalar(stmt)

    def get_by_name(self, user_id: int, name: str) -> TagModel | None:
        stmt = select(TagModel).where(TagModel.user_id == user_id, TagModel.name == name)
        return self.db.scalar(stmt)

    def get_many(self, user_id: int, tag_ids: list[int]) -> list[TagModel]:
        if not tag_ids:
            return []
        stmt = select(TagModel).where(TagModel.user_id == user_id, TagModel.id.in_(tag_ids))
        return list(self.db.scalars(stmt).all())

    def list(self, user_id: int, skip: int, limit: int) -> list[TagModel]:
        stmt = (
            select(TagModel)
            .where(TagModel.user_id == user_id)
            .order_by(TagModel.name.asc())
            .offset(skip)
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def add(self, user_id: int, name: str, color: str) -> TagModel:
        tag = TagModel(user_id=user_id, name=name, color=color)
        self.db.add(tag)
        self.db.commit()
        self.db.refresh(tag)
        return tag

    def delete(self, tag: TagModel) -> None:
        self.db.delete(tag)
        self.db.commit()
