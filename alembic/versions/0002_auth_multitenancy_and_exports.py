"""add users, refresh tokens, task exports, and multi-tenancy ownership

Revision ID: 0002_auth_multitenancy
Revises: 0001_initial_schema
Create Date: 2026-11-25 01:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_auth_multitenancy"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_USER_ROLE = sa.Enum("USER", "ADMIN", name="userrole")
_EXPORT_FORMAT = sa.Enum("CSV", "JSON", name="exportformat")
_EXPORT_STATUS = sa.Enum("PENDING", "COMPLETED", "FAILED", name="exportstatus")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("role", _USER_ROLE, nullable=False, server_default="USER"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("family_id", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_refresh_tokens_id", "refresh_tokens", ["id"])
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])

    op.create_table(
        "task_exports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("export_format", _EXPORT_FORMAT, nullable=False),
        sa.Column("status", _EXPORT_STATUS, nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_exports_id", "task_exports", ["id"])
    op.create_index("ix_task_exports_user_id", "task_exports", ["user_id"])
    op.create_index("ix_task_exports_status", "task_exports", ["status"])

    with op.batch_alter_table("projects") as batch:
        batch.drop_index("ix_projects_name")
        batch.add_column(sa.Column("user_id", sa.Integer(), nullable=False))
        batch.create_foreign_key(
            "fk_projects_user_id", "users", ["user_id"], ["id"], ondelete="CASCADE"
        )
        batch.create_index("ix_projects_user_id", ["user_id"])
        batch.create_index("ix_projects_name", ["name"])
        batch.create_unique_constraint("uq_projects_user_name", ["user_id", "name"])

    with op.batch_alter_table("tags") as batch:
        batch.drop_index("ix_tags_name")
        batch.add_column(sa.Column("user_id", sa.Integer(), nullable=False))
        batch.create_foreign_key(
            "fk_tags_user_id", "users", ["user_id"], ["id"], ondelete="CASCADE"
        )
        batch.create_index("ix_tags_user_id", ["user_id"])
        batch.create_index("ix_tags_name", ["name"])
        batch.create_unique_constraint("uq_tags_user_name", ["user_id", "name"])

    with op.batch_alter_table("tasks") as batch:
        batch.add_column(sa.Column("user_id", sa.Integer(), nullable=False))
        batch.create_foreign_key(
            "fk_tasks_user_id", "users", ["user_id"], ["id"], ondelete="CASCADE"
        )
        batch.create_index("ix_tasks_user_id", ["user_id"])
        batch.create_index("ix_tasks_user_status", ["user_id", "status"])

    with op.batch_alter_table("task_comments") as batch:
        batch.add_column(sa.Column("user_id", sa.Integer(), nullable=False))
        batch.create_foreign_key(
            "fk_task_comments_user_id", "users", ["user_id"], ["id"], ondelete="CASCADE"
        )
        batch.create_index("ix_task_comments_user_id", ["user_id"])


def downgrade() -> None:
    with op.batch_alter_table("task_comments") as batch:
        batch.drop_index("ix_task_comments_user_id")
        batch.drop_constraint("fk_task_comments_user_id", type_="foreignkey")
        batch.drop_column("user_id")

    with op.batch_alter_table("tasks") as batch:
        batch.drop_index("ix_tasks_user_status")
        batch.drop_index("ix_tasks_user_id")
        batch.drop_constraint("fk_tasks_user_id", type_="foreignkey")
        batch.drop_column("user_id")

    with op.batch_alter_table("tags") as batch:
        batch.drop_constraint("uq_tags_user_name", type_="unique")
        batch.drop_index("ix_tags_name")
        batch.drop_index("ix_tags_user_id")
        batch.drop_constraint("fk_tags_user_id", type_="foreignkey")
        batch.drop_column("user_id")
        batch.create_index("ix_tags_name", ["name"], unique=True)

    with op.batch_alter_table("projects") as batch:
        batch.drop_constraint("uq_projects_user_name", type_="unique")
        batch.drop_index("ix_projects_name")
        batch.drop_index("ix_projects_user_id")
        batch.drop_constraint("fk_projects_user_id", type_="foreignkey")
        batch.drop_column("user_id")
        batch.create_index("ix_projects_name", ["name"], unique=True)

    op.drop_table("task_exports")
    op.drop_table("refresh_tokens")
    op.drop_table("users")
