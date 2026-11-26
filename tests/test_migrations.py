from pathlib import Path
from sqlite3 import connect

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from taskflow.config import Settings
from taskflow.database import make_engine
from taskflow.migrate import migrate

LEGACY_TASKFLOW = """
CREATE TABLE projects (
    id INTEGER NOT NULL PRIMARY KEY, name VARCHAR(120) NOT NULL, description TEXT,
    created_at DATETIME NOT NULL
);
CREATE TABLE tasks (
    id INTEGER NOT NULL PRIMARY KEY, project_id INTEGER, title VARCHAR(150) NOT NULL,
    description TEXT, status VARCHAR(12) NOT NULL, priority VARCHAR(7) NOT NULL,
    assignee VARCHAR(100), due_date DATETIME, created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL, FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);
CREATE INDEX ix_projects_id ON projects(id);
CREATE UNIQUE INDEX ix_projects_name ON projects(name);
CREATE INDEX ix_tasks_id ON tasks(id);
CREATE INDEX ix_tasks_project_id ON tasks(project_id);
CREATE INDEX ix_tasks_title ON tasks(title);
CREATE INDEX ix_tasks_status ON tasks(status);
CREATE INDEX ix_tasks_priority ON tasks(priority);
CREATE INDEX ix_tasks_assignee ON tasks(assignee);
INSERT INTO projects VALUES (5, 'Legacy project', 'retain me', '2024-01-01 00:00:00.000000');
INSERT INTO tasks VALUES (
    7, 5, 'Legacy task', NULL, 'REVISAO', 'URGENTE', NULL, NULL,
    '2024-01-01 00:00:00.000000', '2024-01-01 00:00:00.000000'
);
"""


@pytest.fixture
def legacy(tmp_path: Path) -> tuple[Settings, Path]:
    db = tmp_path / "legacy.db"
    with connect(db) as connection:
        connection.executescript(LEGACY_TASKFLOW)
    return Settings(_env_file=None, database_url=f"sqlite:///{db}"), db


def test_adopt_preserves_existing_data_and_cascade(legacy: tuple[Settings, Path]) -> None:
    settings, path = legacy
    with pytest.raises(ValueError, match="unversioned"):
        migrate(settings)
    migrate(settings, adopt_legacy=True)
    migrate(settings)

    engine = make_engine(settings.database_url)
    try:
        with engine.begin() as connection:
            assert connection.scalar(text("PRAGMA foreign_keys")) == 1
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "0002_task_indexes"
            )
            assert connection.execute(text("SELECT id, project_id, title FROM tasks")).one() == (
                7,
                5,
                "Legacy task",
            )
            assert (
                connection.scalar(text("SELECT description FROM projects WHERE id = 5"))
                == "retain me"
            )
            assert "ix_tasks_created_at_id" in {
                index["name"] for index in inspect(connection).get_indexes("tasks")
            }
            connection.execute(text("DELETE FROM projects WHERE id = 5"))
            assert connection.scalar(text("SELECT count(*) FROM tasks")) == 0
    finally:
        engine.dispose()
    with connect(path) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    with pytest.raises(ValueError, match="unversioned"):
        migrate(settings, adopt_legacy=True)


@pytest.mark.parametrize(
    ("sql", "reason"),
    [
        ("UPDATE tasks SET project_id = 999", "missing projects"),
        ("UPDATE tasks SET status = 'bad'", "unknown status"),
        ("DROP INDEX ix_projects_name", "missing original TaskFlow indexes"),
        ("ALTER TABLE projects ADD COLUMN extra TEXT", "original TaskFlow schema"),
    ],
)
def test_reject_unrecognized_legacy(legacy: tuple[Settings, Path], sql: str, reason: str) -> None:
    settings, path = legacy
    with connect(path) as connection:
        connection.execute(sql)
    with pytest.raises(ValueError, match=reason):
        migrate(settings, adopt_legacy=True)
    with connect(path) as connection:
        assert not connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'alembic_version'"
        ).fetchone()
        assert connection.execute("SELECT count(*) FROM tasks").fetchone() == (1,)


def test_fresh_install_and_downgrade(settings: Settings) -> None:
    migrate(settings)
    engine = make_engine(settings.database_url)
    try:
        with engine.begin() as connection:
            config = Config("alembic.ini", attributes={"connection": connection})
            command.check(config)
            command.downgrade(config, "0001_baseline")
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "0001_baseline"
            )
            command.upgrade(config, "head")
    finally:
        engine.dispose()
