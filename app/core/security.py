"""Hashing Argon2id, JWT (access token) e tokens de refresh opacos."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import timedelta
from typing import Annotated, Any

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import UnauthorizedError
from app.db.session import get_db
from app.db.types import utcnow
from app.models import UserModel

_JWT_ALGORITHM = "HS256"
_password_hasher = PasswordHash.recommended()
_bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return str(_password_hasher.hash(password))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bool(_password_hasher.verify(plain_password, hashed_password))


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_access_token(user: UserModel, settings: Settings) -> str:
    now = utcnow()
    payload: dict[str, Any] = {
        "sub": str(user.id),
        "role": user.role.value,
        "type": "access",
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_expire_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_JWT_ALGORITHM)


def decode_access_token(token: str, settings: Settings) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[_JWT_ALGORITHM],
            options={"require": ["sub", "exp", "iat", "type"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Token de acesso expirado.") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Token de acesso inválido.") from exc

    if payload.get("type") != "access":
        raise UnauthorizedError("Tipo de token inválido.")
    return payload


def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> UserModel:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthorizedError("Autenticação Bearer obrigatória.")

    settings: Settings = request.app.state.settings
    payload = decode_access_token(credentials.credentials, settings)
    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError) as exc:
        raise UnauthorizedError("Token de acesso inválido.") from exc

    user = db.get(UserModel, user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Usuário inativo ou inexistente.")
    return user
