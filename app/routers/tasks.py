from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status

from app.core.security import verify_api_key
from app.models import TaskPriority, TaskStatus
from app.repositories.task_repository import TaskFilters
from app.routers.deps import get_task_service
from app.schemas.task import PaginatedTaskResponse, TaskCreate, TaskResponse, TaskUpdate
from app.services.task_service import TaskService

router = APIRouter(prefix="/api/v1/tasks", tags=["Tarefas"], dependencies=[Depends(verify_api_key)])

Service = Annotated[TaskService, Depends(get_task_service)]
TaskId = Annotated[int, Path(ge=1)]


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(task_in: TaskCreate, service: Service) -> TaskResponse:
    return service.create(task_in)


@router.get("", response_model=PaginatedTaskResponse)
def list_tasks(
    service: Service,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    status_filter: Annotated[TaskStatus | None, Query(alias="status")] = None,
    priority_filter: Annotated[TaskPriority | None, Query(alias="priority")] = None,
    project_id: Annotated[int | None, Query(ge=1)] = None,
    assignee: Annotated[str | None, Query(max_length=100)] = None,
    search: Annotated[str | None, Query(min_length=2, max_length=150)] = None,
) -> PaginatedTaskResponse:
    filters = TaskFilters(
        status=status_filter,
        priority=priority_filter,
        project_id=project_id,
        assignee=assignee,
        search=search,
    )
    return service.list(filters, skip, limit)


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: TaskId, service: Service) -> TaskResponse:
    return service.get(task_id)


@router.patch("/{task_id}", response_model=TaskResponse)
def update_task(task_id: TaskId, task_in: TaskUpdate, service: Service) -> TaskResponse:
    return service.update(task_id, task_in)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: TaskId, service: Service) -> Response:
    service.delete(task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
