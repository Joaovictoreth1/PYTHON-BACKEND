from typing import Annotated

from fastapi import APIRouter, Query, Response

from taskflow import services
from taskflow.database import DB
from taskflow.schemas import ProjectCreate, ProjectResponse, Sort

router = APIRouter(prefix="/projects", tags=["Projetos"])


@router.post("", status_code=201)
def create_project(data: ProjectCreate, db: DB) -> ProjectResponse:
    return services.create_project(db, data)


@router.get("")
def list_projects(
    db: DB,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
    sort: Sort = "newest",
    search: Annotated[str | None, Query(min_length=2, max_length=120)] = None,
) -> list[ProjectResponse]:
    return services.list_projects(db, skip, limit, sort, search)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: int, db: DB) -> Response:
    services.delete_project(db, project_id)
    return Response(status_code=204)
