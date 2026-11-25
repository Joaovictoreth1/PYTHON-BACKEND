from __future__ import annotations

import pytest


def test_tag_crud_and_task_association(client, auth, create_task):
    res = client.post(
        "/api/v1/tags", json={"name": "  BackEnd  ", "color": "#FF00AA"}, headers=auth
    )
    assert res.status_code == 201
    tag = res.json()
    assert tag["name"] == "backend"
    assert tag["color"] == "#ff00aa"

    # Nome duplicado (case-insensitive) -> 409
    dup = client.post("/api/v1/tags", json={"name": "BACKEND"}, headers=auth)
    assert dup.status_code == 409
    assert dup.json()["code"] == "conflict"

    # Associa na criação da tarefa (deduplica ids repetidos)
    task = create_task("API v2", tag_ids=[tag["id"], tag["id"]])
    assert [t["name"] for t in task["tags"]] == ["backend"]

    # Filtro por tag (case-insensitive)
    filtered = client.get("/api/v1/tasks?tag=BACKEND", headers=auth).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["id"] == task["id"]

    # Lista e remove tag (remove associação sem apagar a tarefa)
    assert len(client.get("/api/v1/tags", headers=auth).json()) == 1
    assert client.delete(f"/api/v1/tags/{tag['id']}", headers=auth).status_code == 204
    assert client.delete(f"/api/v1/tags/{tag['id']}", headers=auth).status_code == 404

    task_after = client.get(f"/api/v1/tasks/{task['id']}", headers=auth).json()
    assert task_after["tags"] == []


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "a"},
        {"name": "ok", "color": "red"},
        {"name": "ok", "color": "#12345"},
        {"name": "ok", "color": "#gggggg"},
    ],
)
def test_tag_validation_errors(client, auth, payload):
    assert client.post("/api/v1/tags", json=payload, headers=auth).status_code == 422


def test_task_with_unknown_tag_returns_404(client, auth, create_task):
    res = client.post(
        "/api/v1/tasks", json={"title": "Com tag ruim", "tag_ids": [999]}, headers=auth
    )
    assert res.status_code == 404

    task = create_task("Existente")
    patch = client.patch(f"/api/v1/tasks/{task['id']}", json={"tag_ids": [999]}, headers=auth)
    assert patch.status_code == 404


def test_task_update_replaces_tags(client, auth, create_task):
    t1 = client.post("/api/v1/tags", json={"name": "bug"}, headers=auth).json()
    t2 = client.post("/api/v1/tags", json={"name": "urgent"}, headers=auth).json()

    task = create_task("Corrigir", tag_ids=[t1["id"]])
    updated = client.patch(
        f"/api/v1/tasks/{task['id']}", json={"tag_ids": [t2["id"]]}, headers=auth
    ).json()
    assert [t["name"] for t in updated["tags"]] == ["urgent"]

    cleared = client.patch(f"/api/v1/tasks/{task['id']}", json={"tag_ids": []}, headers=auth).json()
    assert cleared["tags"] == []


def test_comments_crud_and_cascade(client, auth, create_task):
    task1 = create_task("Tarefa 1")
    task2 = create_task("Tarefa 2")

    res = client.post(
        f"/api/v1/tasks/{task1['id']}/comments",
        json={"author": "  João  ", "body": "  Revisar índices  "},
        headers=auth,
    )
    assert res.status_code == 201
    comment = res.json()
    assert comment["author"] == "João"
    assert comment["body"] == "Revisar índices"
    assert comment["task_id"] == task1["id"]

    listed = client.get(f"/api/v1/tasks/{task1['id']}/comments", headers=auth).json()
    assert len(listed) == 1

    # Comentário de outra tarefa não pode ser deletado via task2
    wrong_task = client.delete(
        f"/api/v1/tasks/{task2['id']}/comments/{comment['id']}", headers=auth
    )
    assert wrong_task.status_code == 404

    # Deleta comentário pela tarefa correta
    ok = client.delete(f"/api/v1/tasks/{task1['id']}/comments/{comment['id']}", headers=auth)
    assert ok.status_code == 204
    assert client.get(f"/api/v1/tasks/{task1['id']}/comments", headers=auth).json() == []


def test_comments_on_missing_task_return_404(client, auth):
    assert client.get("/api/v1/tasks/999/comments", headers=auth).status_code == 404
    res = client.post(
        "/api/v1/tasks/999/comments", json={"author": "Ana", "body": "Oi"}, headers=auth
    )
    assert res.status_code == 404
    assert client.delete("/api/v1/tasks/999/comments/1", headers=auth).status_code == 404
