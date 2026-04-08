from alembic import op
import sqlalchemy as sa

revision = "0006_budget_entries"
down_revision = "0005_user_auth_scoping"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "budget_entries",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("spent_on", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_budget_entries_user_id", "budget_entries", ["user_id"])
    op.create_index("ix_budget_entries_category", "budget_entries", ["category"])
    op.create_index("ix_budget_entries_spent_on", "budget_entries", ["spent_on"])


def downgrade() -> None:
    op.drop_index("ix_budget_entries_spent_on", table_name="budget_entries")
    op.drop_index("ix_budget_entries_category", table_name="budget_entries")
    op.drop_index("ix_budget_entries_user_id", table_name="budget_entries")
    op.drop_table("budget_entries")