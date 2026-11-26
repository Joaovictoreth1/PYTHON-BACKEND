import asyncio
from datetime import UTC, datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from taskflow.config import Settings
from taskflow.main import create_app

pytestmark = pytest.mark.anyio

PROJECTS = "/api/v1/projects"
TASKS = "/api/v1/tasks"
STATS = "/api/v1/stats"


async def test_health_and_auth(app: FastAPI, client: AsyncClient) -> None:
    result = await client.get("/health", headers={"X-API-Key": ""})
    assert result.status_code == 200
    assert result.json()["database"] == "conectado"
    assert float(result.headers["X-Process-Time-Ms"]) >= 0
    assert result.headers["X-Content-Type-Options"] == "nosniff"
    assert result.headers["X-Frame-Options"] == "DENY"
    assert result.headers["Referrer-Policy"] == "no-referrer"
    assert result.headers["Cache-Control"] == "no-store"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anonymous:
        for path in (PROJECTS, TASKS, STATS):
            result = await anonymous.get(path)
            assert result.status_code == 401
            assert result.headers["WWW-Authenticate"] == "APIKey"
            assert result.json()["error"] == {"code": "unauthorized", "path": path}
        assert (await anonymous.get("/not-found")).status_code == 404

    wrong_key = await client.get(TASKS, headers={"X-API-Key": "chave-errada"})
    assert wrong_key.status_code == 401
    assert (await client.get("/openapi.json")).json()["components"]["securitySchemes"][
        "APIKeyHeader"
    ]["name"] == "X-API-Key"


async def test_project_task_lifecycle(client: AsyncClient) -> None:
    invalid = await client.post(PROJECTS, json={"name": "   "})
    assert invalid.status_code == 422
    assert invalid.json()["detail"][0]["loc"] == ["body", "name"]
    assert (await client.post(TASKS, json={"title": "  a "})).status_code == 422

    result = await client.post(PROJECTS, json={"name": "  Plataforma Core ", "description": "Core"})
    assert result.status_code == 201
    project = result.json()
    assert project["name"] == "Plataforma Core"
    assert project["task_count"] == 0
    assert (await client.post(PROJECTS, json={"name": project["name"]})).status_code == 409

    result = await client.post(
        TASKS, json={"title": "Configurar CI/CD", "project_id": project["id"]}
    )
    assert result.status_code == 201
    task = result.json()
    task_path = f"{TASKS}/{task['id']}"
    assert task["project_id"] == project["id"]
    assert task["status"] == "pendente"
    assert task["priority"] == "media"
    assert (await client.get(task_path)).headers["ETag"] == result.headers["ETag"]
    assert (await client.get(PROJECTS)).json()[0]["task_count"] == 1

    stats = (await client.get(STATS)).json()
    assert stats == {
        "total_projects": 1,
        "total_tasks": 1,
        "overdue_tasks": 0,
        "by_status": {"pendente": 1},
        "by_priority": {"media": 1},
    }
    patch = await client.patch(task_path, json={"title": "  Pipeline  ", "status": "concluida"})
    assert patch.status_code == 200
    assert patch.json()["title"] == "Pipeline"
    assert patch.json()["status"] == "concluida"
    assert patch.json()["description"] is None

    project_path = f"{PROJECTS}/{project['id']}"
    deleted = await client.delete(project_path)
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert (await client.get(task_path)).status_code == 404
    assert (await client.delete(project_path)).status_code == 404
    assert (await client.delete(task_path)).status_code == 404


async def test_task_validation_and_removal(client: AsyncClient) -> None:
    assert (
        await client.post(TASKS, json={"title": "Invalid project", "project_id": 999})
    ).status_code == 404
    project = (await client.post(PROJECTS, json={"name": "Plataforma Core"})).json()
    task = (
        await client.post(
            TASKS,
            json={"title": "Task to update", "description": "Text", "project_id": project["id"]},
        )
    ).json()
    task_path = f"{TASKS}/{task['id']}"
    for field in ("title", "status", "priority"):
        response = await client.patch(task_path, json={field: None})
        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"] == ["body", field]
    assert (await client.patch(task_path, json={"project_id": 999})).status_code == 404
    assert (await client.patch(f"{TASKS}/999", json={"description": "new"})).status_code == 404
    assert (await client.patch(f"{TASKS}/999", json={"project_id": None})).status_code == 404
    assert (
        await client.patch(task_path, json={}, headers={"If-Match": "invalid"})
    ).status_code == 422
    cleared = await client.patch(task_path, json={"description": None, "project_id": None})
    assert cleared.json()["project_id"] is None
    assert cleared.json()["description"] is None
    assert (await client.delete(task_path)).status_code == 204


async def test_task_filters_sort_and_utc_stats(client: AsyncClient) -> None:
    project = (await client.post(PROJECTS, json={"name": "Plataforma Core"})).json()
    overdue = datetime.now(UTC) - timedelta(days=1)
    utc_minus_four = overdue.astimezone(timezone(timedelta(hours=-4)))
    matching = {
        "title": "100% CI pipeline",
        "assignee": "João Victor",
        "project_id": project["id"],
        "priority": "urgente",
        "status": "em_andamento",
        "due_date": utc_minus_four.isoformat(),
    }
    first = (await client.post(TASKS, json=matching)).json()
    second = (await client.post(TASKS, json={**matching, "title": "A second CI task"})).json()
    await client.post(TASKS, json={**matching, "title": "Closed CI task", "status": "cancelada"})
    assert datetime.fromisoformat(first["due_date"]) == overdue
    filters = {
        "assignee": "VICTOR",
        "priority": "urgente",
        "status": "em_andamento",
        "project_id": project["id"],
        "limit": 1,
        "sort": "oldest",
    }
    page = (await client.get(TASKS, params=filters)).json()
    assert page == {"total": 2, "skip": 0, "limit": 1, "items": [first]}
    page = (await client.get(TASKS, params={**filters, "skip": 1, "search": "CI"})).json()
    assert page["items"] == [second]
    assert (await client.get(TASKS, params={"search": "0%"})).json()["items"] == [first]
    assert (await client.get(TASKS, params={"limit": 101})).status_code == 422
    stats = (await client.get(STATS)).json()
    assert stats["overdue_tasks"] == 2
    assert stats["by_priority"] == {"urgente": 3}


async def test_project_count_uses_a_single_query(
    client: AsyncClient, sessions: sessionmaker[Session]
) -> None:
    names = ["Alfa", "Beta", "Core"]
    for name in names:
        await client.post(PROJECTS, json={"name": name})

    queries: list[str] = []

    def collect(*args: object) -> None:
        queries.append(str(args[2]))

    engine = sessions.kw["bind"]
    assert isinstance(engine, Engine)
    event.listen(engine, "before_cursor_execute", collect)
    try:
        result = await client.get(PROJECTS, params={"sort": "oldest", "limit": 1, "skip": 1})
        assert [item["name"] for item in result.json()] == ["Beta"]
        assert len(queries) == 1
    finally:
        event.remove(engine, "before_cursor_execute", collect)

    filtered = await client.get(PROJECTS, params={"search": "OR"})
    assert [item["name"] for item in filtered.json()] == ["Core"]


async def test_concurrent_project_create_and_conditional_patch(client: AsyncClient) -> None:
    attempts = await asyncio.gather(
        *(client.post(PROJECTS, json={"name": "Shared"}) for _ in range(8))
    )
    assert sorted(attempt.status_code for attempt in attempts) == [201] + [409] * 7
    assert len((await client.get(PROJECTS)).json()) == 1

    created = await client.post(TASKS, json={"title": "Original"})
    path = f"{TASKS}/{created.json()['id']}"
    changes = await asyncio.gather(
        *(
            client.patch(path, json={"title": title}, headers={"If-Match": created.headers["ETag"]})
            for title in ("First", "Second")
        )
    )
    assert sorted(change.status_code for change in changes) == [200, 412]
    current = await client.get(path)
    assert current.headers["ETag"] != created.headers["ETag"]
    assert current.json() == next(change.json() for change in changes if change.status_code == 200)


async def test_cors_and_rate_limit(settings: Settings, client: AsyncClient) -> None:
    common = {
        "Access-Control-Request-Method": "PATCH",
        "Access-Control-Request-Headers": "If-Match",
    }
    approved = await client.options(TASKS, headers={**common, "Origin": settings.cors_origins[0]})
    assert approved.headers["Access-Control-Allow-Origin"] == settings.cors_origins[0]
    assert "Access-Control-Allow-Credentials" not in approved.headers
    denied = await client.options(TASKS, headers={**common, "Origin": "https://unknown.example"})
    assert denied.status_code == 400
    assert "Access-Control-Allow-Origin" not in denied.headers

    app = create_app(settings.model_copy(update={"rate_limit_max_requests": 1}))
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as limited,
    ):
        assert (await limited.get(TASKS)).status_code == 401
        result = await limited.get(TASKS, headers={"Origin": settings.cors_origins[0]})
        assert result.status_code == 429
        assert int(result.headers["Retry-After"]) >= 1
        assert result.headers["X-Content-Type-Options"] == "nosniff"
        assert result.headers["Access-Control-Allow-Origin"] == settings.cors_origins[0]
        assert (await limited.get("/health")).status_code == 200


async def test_unmigrated_health_and_generic_error(settings: Settings) -> None:
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={
                "X-API-Key": settings.api_secret_key.get_secret_value()
                if settings.api_secret_key
                else ""
            },
        ) as unready,
    ):
        assert (await unready.get("/health")).status_code == 503
        response = await unready.get(TASKS)
        assert response.status_code == 500
        assert response.json() == {
            "detail": "Erro interno no servidor",
            "error": {"code": "internal_server_error", "path": TASKS},
        }
        assert "X-Process-Time-Ms" in response.headers
