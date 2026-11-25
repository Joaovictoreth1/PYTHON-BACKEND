from __future__ import annotations

import pytest


def test_create_project_returns_201(client, auth):
    res = client.post(
        "/api/v1/projects", json={"name": "  Core  ", "description": "Infra"}, headers=auth
    )
    assert res.status_code == 201
    body = res.json()
    assert body["name"] == "Core"
    assert body["task_count"] == 0
    assert body["created_at"].endswith("Z") or "+00:00" in body["created_at"]


def test_create_project_duplicate_name_returns_409(client, auth, create_project):
    create_project("Duplicado")
    res = client.post("/api/v1/projects", json={"name": "Duplicado"}, headers=auth)
    assert res.status_code == 409


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": "ab"},
        {"name": "   ab   "},
        {"name": "x" * 121},
        {"name": "ok!", "description": "d" * 1001},
    ],
)
def test_create_project_validation_errors(client, auth, payload):
    res = client.post("/api/v1/projects", json=payload, headers=auth)
    assert res.status_code == 422
    assert isinstance(res.json()["detail"], list)


def test_get_project_includes_task_count(client, auth, create_project, create_task):
    project = create_project()
    create_task(project_id=project["id"])
    create_task(project_id=project["id"])
    res = client.get(f"/api/v1/projects/{project['id']}", headers=auth)
    assert res.status_code == 200
    assert res.json()["task_count"] == 2


def test_get_project_not_found(client, auth):
    assert client.get("/api/v1/projects/999", headers=auth).status_code == 404


def test_get_project_invalid_id(client, auth):
    assert client.get("/api/v1/projects/0", headers=auth).status_code == 422


def test_list_projects_with_counts_and_pagination(client, auth, create_project, create_task):
    first = create_project("Primeiro")
    create_project("Segundo")
    create_task(project_id=first["id"])

    res = client.get("/api/v1/projects", headers=auth)
    assert res.status_code == 200
    counts = {p["name"]: p["task_count"] for p in res.json()}
    assert counts == {"Primeiro": 1, "Segundo": 0}

    page = client.get("/api/v1/projects?skip=1&limit=1", headers=auth).json()
    assert len(page) == 1
    assert client.get("/api/v1/projects?limit=0", headers=auth).status_code == 422


def test_update_project(client, auth, create_project):
    project = create_project("Antigo", description="v1")
    res = client.patch(
        f"/api/v1/projects/{project['id']}", json={"name": "Novo Nome"}, headers=auth
    )
    assert res.status_code == 200
    assert res.json()["name"] == "Novo Nome"
    assert res.json()["description"] == "v1"


def test_update_project_same_name_is_allowed(client, auth, create_project):
    project = create_project("Mesmo")
    res = client.patch(f"/api/v1/projects/{project['id']}", json={"name": "Mesmo"}, headers=auth)
    assert res.status_code == 200


def test_update_project_clear_description(client, auth, create_project):
    project = create_project("Com desc", description="algo")
    res = client.patch(
        f"/api/v1/projects/{project['id']}", json={"description": None}, headers=auth
    )
    assert res.status_code == 200
    assert res.json()["description"] is None


def test_update_project_conflict(client, auth, create_project):
    create_project("Ocupado")
    other = create_project("Livre")
    res = client.patch(f"/api/v1/projects/{other['id']}", json={"name": "Ocupado"}, headers=auth)
    assert res.status_code == 409


def test_update_project_null_name_rejected(client, auth, create_project):
    project = create_project()
    res = client.patch(f"/api/v1/projects/{project['id']}", json={"name": None}, headers=auth)
    assert res.status_code == 422


def test_update_project_not_found(client, auth):
    res = client.patch("/api/v1/projects/999", json={"name": "Qualquer"}, headers=auth)
    assert res.status_code == 404


def test_delete_project_cascades_tasks(client, auth, create_project, create_task):
    project = create_project()
    task = create_task(project_id=project["id"])
    assert client.delete(f"/api/v1/projects/{project['id']}", headers=auth).status_code == 204
    assert client.get(f"/api/v1/projects/{project['id']}", headers=auth).status_code == 404
    assert client.get(f"/api/v1/tasks/{task['id']}", headers=auth).status_code == 404


def test_delete_project_not_found(client, auth):
    assert client.delete("/api/v1/projects/999", headers=auth).status_code == 404
