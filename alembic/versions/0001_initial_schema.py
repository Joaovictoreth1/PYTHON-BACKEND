"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-25 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TASK_STATUS = sa.Enum(
    "PENDENTE", "EM_ANDAMENTO", "REVISAO", "CONCLUIDA", "CANCELADA", name="taskstatus"
)
_TASK_PRIORITY = sa.Enum("BAIXA", "MEDIA", "ALTA", "URGENTE", name="taskpriority")


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_projects_id", "projects", ["id"])
    op.create_index("ix_projects_name", "projects", ["name"], unique=True)

    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tags_id", "tags", ["id"])
    op.create_index("ix_tags_name", "tags", ["name"], unique=True)

    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", _TASK_STATUS, nullable=False),
        sa.Column("priority", _TASK_PRIORITY, nullable=False),
        sa.Column("assignee", sa.String(length=100), nullable=True),
        sa.Column("due_date", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tasks_id", "tasks", ["id"])
    op.create_index("ix_tasks_project_id", "tasks", ["project_id"])
    op.create_index("ix_tasks_title", "tasks", ["title"])
    op.create_index("ix_tasks_status", "tasks", ["status"])
    op.create_index("ix_tasks_priority", "tasks", ["priority"])
    op.create_index("ix_tasks_assignee", "tasks", ["assignee"])
    op.create_index("ix_tasks_project_status", "tasks", ["project_id", "status"])
    op.create_index("ix_tasks_status_due_date", "tasks", ["status", "due_date"])

    op.create_table(
        "task_tags",
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("task_id", "tag_id"),
    )

    op.create_table(
        "task_comments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("author", sa.String(length=100), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_comments_id", "task_comments", ["id"])
    op.create_index("ix_task_comments_task_id", "task_comments", ["task_id"])


def downgrade() -> None:
    op.drop_table("task_comments")
    op.drop_table("task_tags")
    op.drop_table("tasks")
    op.drop_table("tags")
    op.drop_table("projects")
