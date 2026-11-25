from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.security import verify_api_key
from app.routers.deps import get_stats_service
from app.schemas.common import StatsResponse
from app.services.stats_service import StatsService

router = APIRouter(prefix="/api/v1", tags=["Monitoramento"], dependencies=[Depends(verify_api_key)])


@router.get("/stats", response_model=StatsResponse)
def get_dashboard_stats(
    service: Annotated[StatsService, Depends(get_stats_service)],
) -> StatsResponse:
    """Retorna indicadores consolidados de projetos e tarefas."""
    return service.dashboard()
