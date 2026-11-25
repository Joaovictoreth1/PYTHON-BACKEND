from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status

from app.core.security import verify_api_key
from app.routers.deps import get_project_service
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate
from app.services.project_service import ProjectService

router = APIRouter(
    prefix="/api/v1/projects", tags=["Projetos"], dependencies=[Depends(verify_api_key)]
)

Service = Annotated[ProjectService, Depends(get_project_service)]
ProjectId = Annotated[int, Path(ge=1)]


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(project_in: ProjectCreate, service: Service) -> ProjectResponse:
    return service.create(project_in)


@router.get("", response_model=list[ProjectResponse])
def list_projects(
    service: Service,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> list[ProjectResponse]:
    return service.list(skip, limit)


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: ProjectId, service: Service) -> ProjectResponse:
    return service.get(project_id)


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: ProjectId, project_in: ProjectUpdate, service: Service
) -> ProjectResponse:
    return service.update(project_id, project_in)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: ProjectId, service: Service) -> Response:
    service.delete(project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
