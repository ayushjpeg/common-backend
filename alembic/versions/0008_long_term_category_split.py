from alembic import op
import sqlalchemy as sa

revision = "0008_long_term_category_split"
down_revision = "0007_task_categories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("UPDATE task_templates SET category = 'long_term_goal' WHERE category = 'long_term'"))


def downgrade() -> None:
    op.execute(sa.text("UPDATE task_templates SET category = 'long_term' WHERE category = 'long_term_goal'"))