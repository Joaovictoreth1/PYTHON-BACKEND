"""Autenticação via header X-API-Key."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Header, Request

from app.core.errors import UnauthorizedError


def verify_api_key(
    request: Request,
    x_api_key: Annotated[str | None, Header(description="Chave secreta X-API-Key")] = None,
) -> None:
    """Valida a chave em tempo constante para prevenir timing attacks."""
    expected: str = request.app.state.settings.api_secret_key
    if not x_api_key or not secrets.compare_digest(x_api_key.encode(), expected.encode()):
        raise UnauthorizedError("Chave de API (X-API-Key) ausente ou inválida.")
