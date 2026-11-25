from __future__ import annotations

import json
from unittest.mock import MagicMock

import redis

from app.core.middleware import RedisRateLimiter, build_rate_limiter
from app.models import ExportStatus, TaskExportModel
from tests.conftest import make_settings


def test_background_csv_and_json_exports(client, register_and_login):
    _, alice = register_and_login("alice@export.com", "StrongPass123", "Alice")
    _, bob = register_and_login("bob@export.com", "StrongPass123", "Bob")

    tag = client.post("/api/v1/tags", json={"name": "ops"}, headers=alice).json()
    client.post(
        "/api/v1/tasks",
        json={"title": "Tarefa CSV", "priority": "alta", "tag_ids": [tag["id"]]},
        headers=alice,
    )

    # Exportação CSV (202 Accepted; TestClient executa BackgroundTasks antes de retornar)
    csv_res = client.post("/api/v1/exports", json={"format": "csv"}, headers=alice)
    assert csv_res.status_code == 202
    csv_id = csv_res.json()["id"]

    status_res = client.get(f"/api/v1/exports/{csv_id}", headers=alice)
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "completed"

    dl_csv = client.get(f"/api/v1/exports/{csv_id}/download", headers=alice)
    assert dl_csv.status_code == 200
    assert "text/csv" in dl_csv.headers["content-type"]
    assert "Tarefa CSV" in dl_csv.text
    assert "ops" in dl_csv.text

    # Exportação JSON
    json_res = client.post("/api/v1/exports", json={"format": "json"}, headers=alice)
    assert json_res.status_code == 202
    json_id = json_res.json()["id"]
    dl_json = client.get(f"/api/v1/exports/{json_id}/download", headers=alice)
    assert dl_json.status_code == 200
    rows = json.loads(dl_json.text)
    assert len(rows) == 1 and rows[0]["title"] == "Tarefa CSV"

    # Listagem
    assert len(client.get("/api/v1/exports", headers=alice).json()) == 2

    # Isolamento multi-tenant
    assert client.get(f"/api/v1/exports/{csv_id}", headers=bob).status_code == 404
    assert client.get(f"/api/v1/exports/{csv_id}/download", headers=bob).status_code == 404
    assert client.get("/api/v1/exports/999", headers=alice).status_code == 404

    # Exportação ainda pendente retorna 409 no download
    db = client.app.state.session_factory()
    try:
        job = db.get(TaskExportModel, csv_id)
        assert job is not None
        job.status = ExportStatus.PENDING
        db.commit()
    finally:
        db.close()
    assert client.get(f"/api/v1/exports/{csv_id}/download", headers=alice).status_code == 409


def test_redis_rate_limiter_allows_blocks_and_falls_back():
    mock_redis = MagicMock()
    read_pipe = MagicMock()
    write_pipe = MagicMock()
    read_pipe.execute.return_value = [0, 0]
    mock_redis.pipeline.side_effect = [read_pipe, write_pipe]

    limiter = RedisRateLimiter(mock_redis, max_requests=2, window_seconds=60)
    r1 = limiter.check("10.0.0.1")
    assert r1.allowed is True
    assert r1.remaining == 1

    # Limite atingido no Redis
    full_pipe = MagicMock()
    full_pipe.execute.return_value = [0, 2]
    mock_redis.pipeline.side_effect = [full_pipe]
    r2 = limiter.check("10.0.0.1")
    assert r2.allowed is False
    assert r2.remaining == 0

    # Redis fora do ar -> fallback automático em memória
    failing_pipe = MagicMock()
    failing_pipe.execute.side_effect = redis.ConnectionError("redis down")
    mock_redis.pipeline.side_effect = [failing_pipe]
    r3 = limiter.check("10.0.0.1")
    assert r3.allowed is True


def test_build_rate_limiter_selects_redis_when_configured():
    limiter = build_rate_limiter(make_settings(redis_url="redis://localhost:6379/0"))
    assert isinstance(limiter, RedisRateLimiter)
