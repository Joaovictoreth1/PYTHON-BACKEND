"""Index task ordering and the overdue dashboard."""

from alembic import op

revision = "0002_task_indexes"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_tasks_created_at_id", "tasks", ["created_at", "id"])
    op.create_index("ix_tasks_due_date", "tasks", ["due_date"])


def downgrade() -> None:
    op.drop_index("ix_tasks_due_date", table_name="tasks")
    op.drop_index("ix_tasks_created_at_id", table_name="tasks")
