"""Acesso a dados de refresh tokens com suporte a rotação e revogação por família."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.types import utcnow
from app.models import RefreshTokenModel


class RefreshTokenRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_hash(self, token_hash: str) -> RefreshTokenModel | None:
        return self.db.scalar(
            select(RefreshTokenModel).where(RefreshTokenModel.token_hash == token_hash)
        )

    def add(
        self,
        *,
        user_id: int,
        token_hash: str,
        family_id: str,
        expires_at: datetime,
    ) -> RefreshTokenModel:
        record = RefreshTokenModel(
            user_id=user_id,
            token_hash=token_hash,
            family_id=family_id,
            expires_at=expires_at,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def revoke(self, token: RefreshTokenModel) -> None:
        token.revoked_at = utcnow()
        self.db.commit()

    def revoke_family(self, family_id: str) -> None:
        stmt = (
            update(RefreshTokenModel)
            .where(
                RefreshTokenModel.family_id == family_id,
                RefreshTokenModel.revoked_at.is_(None),
            )
            .values(revoked_at=utcnow())
        )
        self.db.execute(stmt)
        self.db.commit()
