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
    assert {"projects", "tasks", "tags", "task_tags", "task_comments", "alembic_version"} <= tables
    engine.dispose()

    # A aplicação sobe normalmente com auto_create_tables=False sobre o banco migrado
    app = create_app(
        Settings(
            database_url=url,
            api_secret_key="test-secret-key-0123456789",
            auto_create_tables=False,
            log_level="WARNING",
        )
    )
    app.state.engine.dispose()

    command.downgrade(cfg, "base")
    engine = create_engine(url)
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    engine.dispose()
