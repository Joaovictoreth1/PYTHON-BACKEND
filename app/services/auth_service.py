"""Regras de negócio de autenticação (JWT + rotação de refresh token com detecção de reuso)."""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ConflictError, UnauthorizedError
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.db.types import utcnow
from app.models import UserModel
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import TokenPairResponse, UserLogin, UserRegister, UserResponse

logger = get_logger("auth")

# Hash dummy para manter o tempo de resposta semelhante quando o e-mail não existe.
_DUMMY_HASH = hash_password("DummyPassword123!")


class AuthService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.users = UserRepository(db)
        self.tokens = RefreshTokenRepository(db)
        self.settings = settings

    def _issue_pair(self, user: UserModel, family_id: str | None = None) -> TokenPairResponse:
        access_token = create_access_token(user, self.settings)
        raw_refresh = generate_refresh_token()
        expires_at = utcnow() + timedelta(days=self.settings.refresh_token_expire_days)
        self.tokens.add(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            family_id=family_id or uuid.uuid4().hex,
            expires_at=expires_at,
        )
        return TokenPairResponse(
            access_token=access_token,
            refresh_token=raw_refresh,
            expires_in=self.settings.access_token_expire_minutes * 60,
        )

    def register(self, data: UserRegister) -> UserResponse:
        if self.users.get_by_email(data.email) is not None:
            raise ConflictError("Já existe uma conta cadastrada com este e-mail.")
        user = self.users.add(
            email=data.email,
            hashed_password=hash_password(data.password),
            full_name=data.full_name,
        )
        logger.info("Usuário registrado | id=%d", user.id)
        return UserResponse.model_validate(user)

    def login(self, data: UserLogin) -> TokenPairResponse:
        user = self.users.get_by_email(data.email)
        if user is None:
            verify_password(data.password, _DUMMY_HASH)
            raise UnauthorizedError("Credenciais inválidas.")
        if not verify_password(data.password, user.hashed_password):
            raise UnauthorizedError("Credenciais inválidas.")
        if not user.is_active:
            raise UnauthorizedError("Usuário inativo.")
        logger.info("Login efetuado | user_id=%d", user.id)
        return self._issue_pair(user)

    def refresh(self, raw_refresh_token: str) -> TokenPairResponse:
        token_hash = hash_refresh_token(raw_refresh_token)
        stored = self.tokens.get_by_hash(token_hash)
        if stored is None:
            raise UnauthorizedError("Refresh token inválido.")

        if stored.revoked_at is not None:
            # Detecção de reuso (replay attack): revoga toda a família do token.
            self.tokens.revoke_family(stored.family_id)
            logger.warning(
                "Reuso de refresh token detectado; família revogada | user_id=%d",
                stored.user_id,
            )
            raise UnauthorizedError("Refresh token já utilizado ou revogado.")

        if stored.expires_at <= utcnow():
            self.tokens.revoke(stored)
            raise UnauthorizedError("Refresh token expirado.")

        user = self.users.get(stored.user_id)
        if user is None or not user.is_active:
            self.tokens.revoke_family(stored.family_id)
            raise UnauthorizedError("Usuário inativo ou inexistente.")

        self.tokens.revoke(stored)
        logger.info("Refresh token rotacionado | user_id=%d", user.id)
        return self._issue_pair(user, family_id=stored.family_id)

    def logout(self, raw_refresh_token: str, user_id: int) -> None:
        stored = self.tokens.get_by_hash(hash_refresh_token(raw_refresh_token))
        if stored is None or stored.user_id != user_id:
            raise UnauthorizedError("Refresh token inválido.")
        if stored.revoked_at is None:
            self.tokens.revoke(stored)
            logger.info("Logout efetuado | user_id=%d", user_id)
