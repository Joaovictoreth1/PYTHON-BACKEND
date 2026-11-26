import argparse
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Connection

from taskflow.config import Settings
from taskflow.database import make_engine
from taskflow.models import Base, TaskPriority, TaskStatus


def _validate_legacy(connection: Connection) -> None:
    if connection.dialect.name != "sqlite":
        raise ValueError("Legacy adoption is only supported for SQLite.")
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    if "alembic_version" in tables or not {"projects", "tasks"} <= tables:
        raise ValueError("Adoption requires the original unversioned projects and tasks tables.")

    for name, table in Base.metadata.tables.items():
        actual = {
            (column["name"], str(column["type"]).upper(), column["nullable"])
            for column in inspector.get_columns(name)
        }
        expected = {
            (column.name, column.type.compile(dialect=connection.dialect).upper(), column.nullable)
            for column in table.columns
        }
        if actual != expected or inspector.get_pk_constraint(name)["constrained_columns"] != ["id"]:
            raise ValueError(f"The {name} table does not match the original TaskFlow schema.")
        indexes = {
            (index["name"], tuple(index["column_names"]), bool(index["unique"]))
            for index in inspector.get_indexes(name)
        }
        baseline = {
            (index.name, tuple(column.name for column in index.columns), bool(index.unique))
            for index in table.indexes
            if index.name not in {"ix_tasks_created_at_id", "ix_tasks_due_date"}
        }
        if not baseline <= indexes:
            raise ValueError(f"The {name} table is missing original TaskFlow indexes.")

    foreign_keys = inspector.get_foreign_keys("tasks")
    if not any(
        key["constrained_columns"] == ["project_id"]
        and key["referred_table"] == "projects"
        and key["referred_columns"] == ["id"]
        and key.get("options", {}).get("ondelete") == "CASCADE"
        for key in foreign_keys
    ):
        raise ValueError("The original task-project cascade constraint is missing.")
    if connection.exec_driver_sql("PRAGMA foreign_key_check(tasks)").first() is not None:
        raise ValueError("Legacy tasks reference missing projects. Repair the orphaned rows first.")
    for field, enum in (("status", TaskStatus), ("priority", TaskPriority)):
        stored = set(connection.exec_driver_sql(f"SELECT DISTINCT {field} FROM tasks").scalars())
        if not stored <= {member.name for member in enum}:
            raise ValueError(f"Legacy tasks contain unknown {field} values.")


def migrate(settings: Settings, *, adopt_legacy: bool = False) -> None:
    ini = Path(__file__).resolve().parent.parent / "alembic.ini"
    config = Config(str(ini))
    engine = make_engine(settings.database_url)
    try:
        with engine.begin() as connection:
            if connection.dialect.name == "sqlite":
                connection.exec_driver_sql("BEGIN IMMEDIATE")
            config.attributes["connection"] = connection
            if adopt_legacy:
                _validate_legacy(connection)
                command.stamp(config, "0001_baseline")
            else:
                tables = set(inspect(connection).get_table_names())
                if "alembic_version" not in tables and tables & {"projects", "tasks"}:
                    raise ValueError("Existing unversioned data; back up and use --adopt-legacy.")
            command.upgrade(config, "head")
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply TaskFlow database migrations.")
    parser.add_argument("--adopt-legacy", action="store_true")
    args = parser.parse_args()
    try:
        migrate(Settings(), adopt_legacy=args.adopt_legacy)
    except ValueError as exc:
        parser.exit(1, f"Migration refused: {exc}\n")


if __name__ == "__main__":
    main()
