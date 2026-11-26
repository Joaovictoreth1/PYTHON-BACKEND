from secrets import compare_digest
from typing import Annotated

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader

from taskflow.config import Settings

api_key = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(request: Request, supplied: Annotated[str | None, Security(api_key)]) -> None:
    settings: Settings = request.app.state.settings
    expected = settings.api_secret_key
    if (
        supplied is None
        or expected is None
        or not expected.get_secret_value()
        or not compare_digest(supplied.encode("utf-8"), expected.get_secret_value().encode("ascii"))
    ):
        raise HTTPException(
            401,
            "Chave de API (X-API-Key) inválida.",
            headers={"WWW-Authenticate": "APIKey"},
        )
