from alembic import op
import sqlalchemy as sa


revision = "0010_budget_reset_dev_data"
down_revision = "0009_budget_categories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("DELETE FROM budget_entries"))
    op.execute(sa.text("DELETE FROM budget_categories"))


def downgrade() -> None:
    pass