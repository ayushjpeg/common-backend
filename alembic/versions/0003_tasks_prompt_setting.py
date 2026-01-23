"""Add app_settings for task prompt

Revision ID: 0003_tasks_prompt_setting
Revises: 0002_gym_normalization
Create Date: 2026-01-23
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0003_tasks_prompt_setting"
down_revision = "0002_gym_normalization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=128), primary_key=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
