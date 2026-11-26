"""Create the original TaskFlow schema."""

import sqlalchemy as sa
from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_projects_id", "projects", ["id"])
    op.create_index("ix_projects_name", "projects", ["name"], unique=True)
    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE")),
        sa.Column("title", sa.String(150), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column(
            "status",
            sa.Enum(
                "PENDENTE", "EM_ANDAMENTO", "REVISAO", "CONCLUIDA", "CANCELADA", name="taskstatus"
            ),
            nullable=False,
        ),
        sa.Column(
            "priority",
            sa.Enum("BAIXA", "MEDIA", "ALTA", "URGENTE", name="taskpriority"),
            nullable=False,
        ),
        sa.Column("assignee", sa.String(100)),
        sa.Column("due_date", sa.DateTime),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    for column in ("id", "project_id", "title", "status", "priority", "assignee"):
        op.create_index(f"ix_tasks_{column}", "tasks", [column])


def downgrade() -> None:
    op.drop_table("tasks")
    op.drop_table("projects")
    if op.get_bind().dialect.name == "postgresql":
        sa.Enum(name="taskstatus").drop(op.get_bind(), checkfirst=True)
        sa.Enum(name="taskpriority").drop(op.get_bind(), checkfirst=True)
