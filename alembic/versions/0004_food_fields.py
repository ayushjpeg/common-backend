from alembic import op
import sqlalchemy as sa

revision = "0004_food_fields"
down_revision = "0003_tasks_prompt_setting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("meal_entries", sa.Column("meal_slot", sa.String(length=64), nullable=False, server_default="Breakfast"))
    op.add_column("meal_entries", sa.Column("recipe", sa.Text(), nullable=True))
    op.add_column("meal_entries", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column(
        "meal_entries",
        sa.Column("ingredients", sa.JSON(), nullable=True, server_default=sa.text("'[]'")),
    )
    op.add_column("meal_entries", sa.Column("last_made", sa.Date(), nullable=True))
    op.add_column("meal_entries", sa.Column("image_url", sa.String(length=512), nullable=True))

    op.add_column("food_images", sa.Column("recorded_at", sa.Date(), nullable=True))
    op.add_column("food_images", sa.Column("caption", sa.Text(), nullable=True))

    op.alter_column("meal_entries", "meal_slot", server_default=None)
    op.alter_column("meal_entries", "ingredients", server_default=None)


def downgrade() -> None:
    op.drop_column("food_images", "caption")
    op.drop_column("food_images", "recorded_at")
    op.drop_column("meal_entries", "image_url")
    op.drop_column("meal_entries", "last_made")
    op.drop_column("meal_entries", "ingredients")
    op.drop_column("meal_entries", "notes")
    op.drop_column("meal_entries", "recipe")
    op.drop_column("meal_entries", "meal_slot")
