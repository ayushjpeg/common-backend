from alembic import op
import sqlalchemy as sa


revision = "0009_budget_categories"
down_revision = "0008_long_term_category_split"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "budget_categories",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "name", name="uq_budget_categories_user_name"),
    )
    op.create_index("ix_budget_categories_user_id", "budget_categories", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_budget_categories_user_id", table_name="budget_categories")
    op.drop_table("budget_categories")