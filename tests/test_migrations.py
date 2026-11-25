from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command
from app.core.config import Settings
from app.main import create_app


def test_alembic_upgrade_and_downgrade(tmp_path: Path, monkeypatch):
    db_file = tmp_path / "migrated.db"
    url = f"sqlite:///{db_file}"
    monkeypatch.setenv("DATABASE_URL", url)

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")

    engine = create_engine(url)
    tables = set(inspect(engine).get_table_names())
    expected = {
        "users",
        "refresh_tokens",
        "projects",
        "tasks",
        "tags",
        "task_tags",
        "task_comments",
        "task_exports",
        "alembic_version",
    }
    assert expected <= tables
    engine.dispose()

    app = create_app(
        Settings(
            database_url=url,
            secret_key="test-jwt-secret-key-0123456789abcdef",
            auto_create_tables=False,
            log_level="WARNING",
        )
    )
    app.state.engine.dispose()

    command.downgrade(cfg, "base")
    engine = create_engine(url)
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    engine.dispose()
