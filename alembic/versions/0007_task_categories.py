from alembic import op
import sqlalchemy as sa

revision = "0007_task_categories"
down_revision = "0006_budget_entries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "task_templates",
        sa.Column("category", sa.String(length=32), nullable=True, server_default="occasional"),
    )
    op.execute(sa.text("UPDATE task_templates SET category = 'occasional' WHERE category IS NULL"))
    op.alter_column("task_templates", "category", nullable=False, server_default=None)
    op.create_index("ix_task_templates_category", "task_templates", ["category"])


def downgrade() -> None:
    op.drop_index("ix_task_templates_category", table_name="task_templates")
    op.drop_column("task_templates", "category")