"""Exceções de domínio e handlers centralizados de erro."""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.logging import get_logger

logger = get_logger("errors")


class AppError(Exception):
    status_code: int = status.HTTP_400_BAD_REQUEST

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT


class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED


async def app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    logger.info("%s em %s: %s", type(exc).__name__, request.url.path, exc.message)
    headers = {"WWW-Authenticate": "ApiKey"} if isinstance(exc, UnauthorizedError) else None
    return JSONResponse(
        status_code=exc.status_code, content={"detail": exc.message}, headers=headers
    )


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors = [
        {"loc": list(err.get("loc", ())), "msg": err.get("msg", ""), "type": err.get("type", "")}
        for err in exc.errors()
    ]
    logger.info("Validação falhou em %s: %d erro(s)", request.url.path, len(errors))
    return JSONResponse(status_code=422, content={"detail": errors})


async def integrity_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.warning("Violação de integridade em %s", request.url.path)
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "Operação viola uma restrição de integridade dos dados."},
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Apenas o tipo da exceção é registrado: mensagens de drivers podem conter dados do usuário.
    logger.error("Erro não tratado em %s: %s", request.url.path, type(exc).__name__)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Erro interno no servidor", "path": request.url.path},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(IntegrityError, integrity_error_handler)
    app.add_exception_handler(SQLAlchemyError, unhandled_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
