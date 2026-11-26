import secrets
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock

import httpx2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from task_manager_api import create_app, get_db
from taskflow_config import Settings


@pytest.fixture
def config(tmp_path: Path) -> Settings:
    return Settings(
        api_secret_key=secrets.token_hex(32), database_url=f"sqlite:///{tmp_path}/api.db"
    )


@pytest.fixture
def client(config: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(config), headers={"X-API-Key": config.api_secret_key}) as client:
        yield client


def test_health_and_auth(config: Settings) -> None:
    with TestClient(create_app(config)) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["database"] == "conectado"
        assert float(health.headers["X-Process-Time-Ms"]) >= 0
        for headers in (
            httpx2.Headers(),
            httpx2.Headers({"X-API-Key": "wrong"}),
            httpx2.Headers([(b"X-API-Key", b"\xff")]),
        ):
            denied = client.get("/api/v1/tasks", headers=headers)
            assert denied.status_code == 401
            assert denied.headers["WWW-Authenticate"] == "APIKey"
        assert client.get("/api/v1/tasks", headers={"X-API-Key": config.api_secret_key}).is_success


def test_project_lifecycle_stats_count_and_cascade(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json={"name": "  Plataforma Core  "})
    assert project.status_code == 201
    assert project.json()["name"] == "Plataforma Core"
    project_id = project.json()["id"]
    assert client.post("/api/v1/projects", json={"name": "Ops"}).status_code == 201

    task = client.post(
        "/api/v1/tasks",
        json={
            "title": "Configurar pipeline CI/CD",
            "priority": "urgente",
            "assignee": "  João  ",
            "project_id": project_id,
            "due_date": "2000-01-01T00:00:00Z",
        },
    )
    assert task.status_code == 201
    assert task.json()["assignee"] == "João"
    task_id = task.json()["id"]
    task_url = f"/api/v1/tasks/{task_id}"
    project_counts = {p["name"]: p["task_count"] for p in client.get("/api/v1/projects").json()}
    assert project_counts == {"Plataforma Core": 1, "Ops": 0}

    stats = client.get("/api/v1/stats")
    assert stats.status_code == 200
    assert stats.json() == {
        "total_projects": 2,
        "total_tasks": 1,
        "overdue_tasks": 1,
        "by_status": {"pendente": 1},
        "by_priority": {"urgente": 1},
    }
    complete = client.patch(task_url, json={"status": "concluida"})
    assert complete.status_code == 200
    assert complete.json()["status"] == "concluida"
    assert client.get("/api/v1/stats").json()["overdue_tasks"] == 0
    removed = client.delete(f"/api/v1/projects/{project_id}")
    assert removed.status_code == 204
    assert removed.content == b""
    assert client.get(task_url).status_code == 404


def test_conflicting_project_creates(client: TestClient) -> None:
    def create() -> int:
        return client.post("/api/v1/projects", json={"name": "Shared Name"}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(create), pool.submit(create)]
        assert sorted(result.result() for result in results) == [201, 409]
    assert len(client.get("/api/v1/projects").json()) == 1


@pytest.mark.parametrize("name", ["   ", " a "])
def test_project_name_must_be_valid_after_trimming(client: TestClient, name: str) -> None:
    assert client.post("/api/v1/projects", json={"name": name}).status_code == 422


def test_task_project_validation_and_nullable_fields(client: TestClient) -> None:
    assert (
        client.post("/api/v1/tasks", json={"title": "Valid Task", "project_id": 101}).status_code
        == 404
    )
    assert client.post("/api/v1/tasks", json={"title": " x "}).status_code == 422
    project_id = client.post("/api/v1/projects", json={"name": "Operations"}).json()["id"]
    task = client.post(
        "/api/v1/tasks",
        json={"title": "Valid Task", "project_id": project_id, "assignee": "João"},
    ).json()
    task_url = f"/api/v1/tasks/{task['id']}"
    assert client.patch(task_url, json={"project_id": 101}).status_code == 404
    assert client.get(task_url).json()["project_id"] == project_id
    assert client.patch(task_url, json={}).json() == task
    changed = client.patch(task_url, json={"project_id": None, "assignee": None})
    assert changed.status_code == 200
    assert changed.json()["project_id"] is None
    assert changed.json()["assignee"] is None
    assert client.delete(task_url).status_code == 204
    assert client.delete(task_url).status_code == 404


@pytest.mark.parametrize(
    "payload",
    [{"title": None}, {"title": "   "}, {"status": None}, {"priority": None}, {"project_id": 0}],
)
def test_task_patch_rejects_invalid_values(client: TestClient, payload: dict[str, object]) -> None:
    task = client.post("/api/v1/tasks", json={"title": "Valid Task"}).json()
    response = client.patch(f"/api/v1/tasks/{task['id']}", json=payload)
    assert response.status_code == 422
    assert client.get(f"/api/v1/tasks/{task['id']}").json() == task


def test_pagination_and_combined_filters(client: TestClient) -> None:
    for title, priority in (
        ("Cut 10% costs", "alta"),
        ("Cut 15% costs", "alta"),
        ("Other", "baixa"),
    ):
        assert client.post("/api/v1/tasks", json={"title": title, "priority": priority}).is_success
    filtered = client.get(
        "/api/v1/tasks", params={"search": "Cut 1", "priority": "alta", "limit": 1}
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 2
    assert len(filtered.json()["items"]) == 1
    literal = client.get("/api/v1/tasks", params={"search": "0%"})
    assert [item["title"] for item in literal.json()["items"]] == ["Cut 10% costs"]
    assert client.get("/api/v1/tasks", params={"limit": 101}).status_code == 422


def test_sqlite_enforces_foreign_keys(config: Settings) -> None:
    app = create_app(config)
    with TestClient(app), app.state.sessions() as db, pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO tasks (project_id, title, status, priority, created_at, updated_at) "
                "VALUES (99, 'Orphan', 'PENDENTE', 'MEDIA', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )


def test_database_health_failure_is_sanitized(config: Settings) -> None:
    db = Mock(spec=Session)
    db.execute.side_effect = OperationalError(None, None, ValueError("internal details"))

    def broken_session() -> Session:
        return db

    app = create_app(config)
    app.dependency_overrides[get_db] = broken_session
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"detail": "Banco de dados indisponível."}


def test_rate_limit_and_cors() -> None:
    app = create_app(
        Settings(
            api_secret_key=secrets.token_hex(32),
            database_url="sqlite://",
            cors_allowed_origins=("https://frontend.example",),
            rate_limit_max_requests=1,
        )
    )
    with TestClient(app) as client:
        options = {
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-API-Key",
        }
        allowed = client.options(
            "/api/v1/tasks", headers={"Origin": "https://frontend.example", **options}
        )
        assert allowed.headers["Access-Control-Allow-Origin"] == "https://frontend.example"
        denied = client.options(
            "/api/v1/tasks", headers={"Origin": "https://other.example", **options}
        )
        assert denied.status_code == 400
        assert "Access-Control-Allow-Origin" not in denied.headers
        assert client.get("/api/v1/tasks").status_code == 401
        throttled = client.get("/api/v1/tasks", headers={"Origin": "https://frontend.example"})
        assert throttled.status_code == 429
        assert "X-Process-Time-Ms" in throttled.headers
        assert throttled.headers["Access-Control-Allow-Origin"] == "https://frontend.example"
        assert client.get("/health").status_code == 200
