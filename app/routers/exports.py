from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Path, Query, Request, Response, status

from app.routers.deps import CurrentUser, DbSession
from app.schemas.export import ExportCreate, ExportResponse
from app.services.export_service import ExportService, run_export_job

router = APIRouter(prefix="/api/v1/exports", tags=["Exportações"])


def get_export_service(db: DbSession) -> ExportService:
    return ExportService(db)


Service = Annotated[ExportService, Depends(get_export_service)]
ExportId = Annotated[int, Path(ge=1)]


@router.post("", response_model=ExportResponse, status_code=status.HTTP_202_ACCEPTED)
def request_export(
    payload: ExportCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    service: Service,
) -> ExportResponse:
    job = service.create(current_user.id, payload.format)
    background_tasks.add_task(
        run_export_job, request.app.state.session_factory, job.id, current_user.id
    )
    return job


@router.get("", response_model=list[ExportResponse])
def list_exports(
    current_user: CurrentUser,
    service: Service,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[ExportResponse]:
    return service.list(current_user.id, skip, limit)


@router.get("/{export_id}", response_model=ExportResponse)
def get_export(
    export_id: ExportId, current_user: CurrentUser, service: Service
) -> ExportResponse:
    return service.get(current_user.id, export_id)


@router.get("/{export_id}/download")
def download_export(
    export_id: ExportId, current_user: CurrentUser, service: Service
) -> Response:
    media_type, filename, content = service.download(current_user.id, export_id)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
