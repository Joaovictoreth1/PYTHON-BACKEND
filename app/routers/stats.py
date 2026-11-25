from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.routers.deps import CurrentUser, get_stats_service
from app.schemas.common import StatsResponse
from app.services.stats_service import StatsService

router = APIRouter(prefix="/api/v1", tags=["Monitoramento"])


@router.get("/stats", response_model=StatsResponse)
def get_dashboard_stats(
    current_user: CurrentUser,
    service: Annotated[StatsService, Depends(get_stats_service)],
) -> StatsResponse:
    """Retorna indicadores consolidados de projetos e tarefas do usuário autenticado."""
    return service.dashboard(current_user.id)
