from __future__ import annotations


def test_full_tenant_isolation(client, register_and_login):
    _, alice = register_and_login("alice@tenant.com", "StrongPass123", "Alice")
    _, bob = register_and_login("bob@tenant.com", "StrongPass123", "Bob")

    # Alice cria projeto, tag, tarefa e comentário
    a_proj = client.post("/api/v1/projects", json={"name": "Core"}, headers=alice).json()
    a_tag = client.post("/api/v1/tags", json={"name": "backend"}, headers=alice).json()
    a_task = client.post(
        "/api/v1/tasks",
        json={"title": "Segredo da Alice", "project_id": a_proj["id"], "tag_ids": [a_tag["id"]]},
        headers=alice,
    ).json()
    a_comment = client.post(
        f"/api/v1/tasks/{a_task['id']}/comments",
        json={"author": "Alice", "body": "Privado"},
        headers=alice,
    ).json()

    # Bob pode criar projeto e tag com os MESMOS nomes (unicidade por tenant)
    b_proj = client.post("/api/v1/projects", json={"name": "Core"}, headers=bob)
    assert b_proj.status_code == 201
    b_tag = client.post("/api/v1/tags", json={"name": "backend"}, headers=bob)
    assert b_tag.status_code == 201

    # Bob não vê nenhum recurso da Alice
    assert client.get("/api/v1/tasks", headers=bob).json()["total"] == 0
    assert client.get("/api/v1/stats", headers=bob).json()["total_tasks"] == 0
    assert client.get(f"/api/v1/projects/{a_proj['id']}", headers=bob).status_code == 404
    assert (
        client.patch(
            f"/api/v1/projects/{a_proj['id']}", json={"name": "Hack"}, headers=bob
        ).status_code
        == 404
    )
    assert client.delete(f"/api/v1/projects/{a_proj['id']}", headers=bob).status_code == 404

    assert client.get(f"/api/v1/tasks/{a_task['id']}", headers=bob).status_code == 404
    assert (
        client.patch(
            f"/api/v1/tasks/{a_task['id']}", json={"title": "Hack"}, headers=bob
        ).status_code
        == 404
    )
    assert client.delete(f"/api/v1/tasks/{a_task['id']}", headers=bob).status_code == 404

    # Bob não pode associar tarefa ao projeto ou tag da Alice
    assert (
        client.post(
            "/api/v1/tasks",
            json={"title": "Cross", "project_id": a_proj["id"]},
            headers=bob,
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/tasks",
            json={"title": "Cross", "tag_ids": [a_tag["id"]]},
            headers=bob,
        ).status_code
        == 404
    )
    assert client.delete(f"/api/v1/tags/{a_tag['id']}", headers=bob).status_code == 404

    # Bob não pode ler, criar ou apagar comentários na tarefa da Alice
    assert client.get(f"/api/v1/tasks/{a_task['id']}/comments", headers=bob).status_code == 404
    assert (
        client.post(
            f"/api/v1/tasks/{a_task['id']}/comments",
            json={"author": "Bob", "body": "Oi"},
            headers=bob,
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/api/v1/tasks/{a_task['id']}/comments/{a_comment['id']}", headers=bob
        ).status_code
        == 404
    )
