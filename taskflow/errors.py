import logging
from collections.abc import Mapping
from http import HTTPStatus

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException

logger = logging.getLogger("taskflow")


def error_response(
    request: Request,
    status: int,
    detail: object,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    try:
        code = HTTPStatus(status).name.lower()
    except ValueError:
        code = "http_error"
    payload = {"detail": detail, "error": {"code": code, "path": request.url.path}}
    return JSONResponse(payload, status_code=status, headers=headers)


async def http_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, HTTPException)
    return error_response(request, exc.status_code, exc.detail, exc.headers)


async def validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors = [{key: error[key] for key in ("loc", "type", "msg")} for error in exc.errors()]
    return error_response(request, 422, errors)


async def integrity_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, IntegrityError)
    return error_response(request, 409, "A alteração conflita com o estado atual dos dados.")


def internal_error(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_error method=%s type=%s", request.method, type(exc).__name__)
    return error_response(request, 500, "Erro interno no servidor")
