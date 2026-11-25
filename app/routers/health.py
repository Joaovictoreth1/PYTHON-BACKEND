from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import VERSION
from app.core.errors import ServiceUnavailableError
from app.db.types import utcnow
from app.routers.deps import DbSession
from app.schemas.common import HealthResponse, LivenessResponse

router = APIRouter(tags=["Monitoramento"])


def _check_database(db: DbSession) -> HealthResponse:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise ServiceUnavailableError("Banco de dados indisponível.") from exc
    return HealthResponse(
        status="online",
        version=VERSION,
        database="conectado",
        timestamp=utcnow(),
    )


@router.get("/health", response_model=HealthResponse)
def health_check(db: DbSession) -> HealthResponse:
    """Verifica disponibilidade da API e conexão com o banco."""
    return _check_database(db)


@router.get("/health/live", response_model=LivenessResponse)
def liveness_check() -> LivenessResponse:
    """Probe de liveness: confirma que o processo está respondendo (sem tocar no banco)."""
    return LivenessResponse(status="alive", version=VERSION, timestamp=utcnow())


@router.get("/health/ready", response_model=HealthResponse)
def readiness_check(db: DbSession) -> HealthResponse:
    """Probe de readiness: retorna 503 se o banco estiver inacessível."""
    return _check_database(db)
