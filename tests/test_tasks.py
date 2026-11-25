from __future__ import annotations

from datetime import datetime, timedelta, timezone


def test_create_task_defaults(client, auth):
    res = client.post("/api/v1/tasks", json={"title": "  Configurar CI  "}, headers=auth)
    assert res.status_code == 201
    body = res.json()
    assert body["title"] == "Configurar CI"
    assert body["status"] == "pendente"
    assert body["priority"] == "media"


def test_create_task_unknown_project_returns_404(client, auth):
    res = client.post("/api/v1/tasks", json={"title": "Orfã", "project_id": 999}, headers=auth)
    assert res.status_code == 404


def test_create_task_validation_errors(client, auth):
    for payload in (
        {"title": "ab"},
        {"title": "Válido", "status": "invalido"},
        {"title": "Válido", "priority": "maxima"},
        {"title": "Válido", "project_id": 0},
        {"title": "Válido", "due_date": "amanhã"},
    ):
        assert client.post("/api/v1/tasks", json=payload, headers=auth).status_code == 422, payload


def test_due_date_is_normalized_to_utc(client, auth, create_task):
    task = create_task(due_date="2030-01-01T12:00:00-03:00")
    due = datetime.fromisoformat(task["due_date"].replace("Z", "+00:00"))
    assert due == datetime(2030, 1, 1, 15, 0, tzinfo=timezone.utc)


def test_get_task_not_found(client, auth):
    assert client.get("/api/v1/tasks/999", headers=auth).status_code == 404


def test_update_task_partial(client, auth, create_task):
    task = create_task(priority="baixa")
    res = client.patch(f"/api/v1/tasks/{task['id']}", json={"status": "concluida"}, headers=auth)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "concluida"
    assert body["priority"] == "baixa"
    assert body["updated_at"] >= task["updated_at"]


def test_update_task_null_required_field_returns_422(client, auth, create_task):
    task = create_task()
    for field in ("title", "status", "priority"):
        res = client.patch(f"/api/v1/tasks/{task['id']}", json={field: None}, headers=auth)
        assert res.status_code == 422, field


def test_update_task_clear_optional_fields(client, auth, create_project, create_task):
    project = create_project()
    task = create_task(assignee="Ana", project_id=project["id"])
    res = client.patch(
        f"/api/v1/tasks/{task['id']}", json={"assignee": None, "project_id": None}, headers=auth
    )
    assert res.status_code == 200
    assert res.json()["assignee"] is None
    assert res.json()["project_id"] is None


def test_update_task_unknown_project_returns_404(client, auth, create_task):
    task = create_task()
    res = client.patch(f"/api/v1/tasks/{task['id']}", json={"project_id": 999}, headers=auth)
    assert res.status_code == 404


def test_update_task_not_found(client, auth):
    assert (
        client.patch("/api/v1/tasks/999", json={"title": "Nada"}, headers=auth).status_code == 404
    )


def test_delete_task(client, auth, create_task):
    task = create_task()
    assert client.delete(f"/api/v1/tasks/{task['id']}", headers=auth).status_code == 204
    assert client.delete(f"/api/v1/tasks/{task['id']}", headers=auth).status_code == 404


def test_list_tasks_filters_and_pagination(client, auth, create_project, create_task):
    project = create_project()
    create_task(
        "Deploy produção", priority="urgente", assignee="João Victor", project_id=project["id"]
    )
    create_task("Revisar PR", status="revisao", assignee="Ana")
    create_task("Deploy staging", priority="alta")

    def query(params: str) -> dict:
        res = client.get(f"/api/v1/tasks?{params}", headers=auth)
        assert res.status_code == 200, res.text
        return res.json()

    assert query("")["total"] == 3
    assert query("search=deploy")["total"] == 2
    assert query("priority=urgente")["total"] == 1
    assert query("status=revisao")["items"][0]["title"] == "Revisar PR"
    assert query(f"project_id={project['id']}")["total"] == 1
    assert query("assignee=joão")["total"] == 1

    page = query("skip=1&limit=1")
    assert page["total"] == 3 and len(page["items"]) == 1 and page["skip"] == 1


def test_list_tasks_like_wildcards_are_escaped(client, auth, create_task):
    create_task("Tarefa comum")
    create_task("Progresso 100%")
    res = client.get("/api/v1/tasks?search=0%25", headers=auth).json()
    assert [t["title"] for t in res["items"]] == ["Progresso 100%"]


def test_list_tasks_invalid_query_params(client, auth):
    for params in ("limit=0", "limit=101", "skip=-1", "search=a", "status=x"):
        assert client.get(f"/api/v1/tasks?{params}", headers=auth).status_code == 422, params


def test_stats(client, auth, create_project, create_task):
    project = create_project()
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    create_task("Atrasada", due_date=past, project_id=project["id"])
    create_task("Concluída atrasada", due_date=past, status="concluida")
    create_task("No prazo", due_date=future, priority="alta")

    res = client.get("/api/v1/stats", headers=auth)
    assert res.status_code == 200
    assert res.json() == {
        "total_projects": 1,
        "total_tasks": 3,
        "overdue_tasks": 1,
        "by_status": {"pendente": 2, "concluida": 1},
        "by_priority": {"media": 2, "alta": 1},
    }
