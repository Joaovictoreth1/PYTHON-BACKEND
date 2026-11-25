from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import VERSION
from app.db.types import utcnow
from app.routers.deps import DbSession
from app.schemas.common import HealthResponse

router = APIRouter(tags=["Monitoramento"])


@router.get("/health", response_model=HealthResponse)
def health_check(db: DbSession) -> HealthResponse:
    """Verifica disponibilidade da API e conexão com o banco."""
    db.execute(text("SELECT 1"))
    return HealthResponse(
        status="online", version=VERSION, database="conectado", timestamp=utcnow()
    )
