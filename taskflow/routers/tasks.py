from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query, Response

from taskflow import services
from taskflow.database import DB, as_utc
from taskflow.models import Task, TaskPriority, TaskStatus
from taskflow.repositories import TaskFilters
from taskflow.schemas import PaginatedTaskResponse, Sort, TaskCreate, TaskResponse, TaskUpdate

router = APIRouter(prefix="/tasks", tags=["Tarefas"])


def _version(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        if len(value) < 2 or not (value.startswith('"') and value.endswith('"')):
            raise ValueError
        return as_utc(datetime.fromisoformat(value[1:-1]))
    except (ValueError, OverflowError):
        raise HTTPException(422, "Informe o ETag da tarefa no cabeçalho If-Match.") from None


def _task_response(task: Task, response: Response) -> TaskResponse:
    response.headers["ETag"] = f'"{task.updated_at.isoformat()}"'
    return TaskResponse.model_validate(task)


@router.post("", status_code=201)
def create_task(data: TaskCreate, db: DB, response: Response) -> TaskResponse:
    return _task_response(services.create_task(db, data), response)


@router.get("")
def list_tasks(
    db: DB,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    project_id: int | None = None,
    assignee: Annotated[str | None, Query(max_length=100)] = None,
    search: Annotated[str | None, Query(min_length=2, max_length=150)] = None,
    sort: Sort = "newest",
) -> PaginatedTaskResponse:
    filters = TaskFilters(skip, limit, sort, status, priority, project_id, assignee, search)
    return services.list_tasks(db, filters)


@router.get("/{task_id}")
def get_task(task_id: int, db: DB, response: Response) -> TaskResponse:
    return _task_response(services.get_task(db, task_id), response)


@router.patch("/{task_id}")
def update_task(
    task_id: int,
    data: TaskUpdate,
    db: DB,
    response: Response,
    if_match: Annotated[str | None, Header()] = None,
) -> TaskResponse:
    return _task_response(services.update_task(db, task_id, data, _version(if_match)), response)


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: int, db: DB) -> Response:
    services.delete_task(db, task_id)
    return Response(status_code=204)
