from alembic import op
import sqlalchemy as sa

revision = "0002_gym_normalization"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gym_exercises",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("equipment", sa.String(length=255), nullable=True),
        sa.Column("primary_muscle", sa.String(length=64), nullable=True),
        sa.Column("secondary_muscle", sa.String(length=64), nullable=True),
        sa.Column("muscle_groups", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("rest_seconds", sa.Integer(), nullable=True),
        sa.Column("target_notes", sa.Text(), nullable=True),
        sa.Column("cues", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("mistakes", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("swap_suggestions", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("extra_metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "gym_day_assignments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("day_key", sa.String(length=16), nullable=False),
        sa.Column("slot_id", sa.String(length=64), nullable=False),
        sa.Column("slot_name", sa.String(length=255), nullable=False),
        sa.Column("slot_subtitle", sa.String(length=255), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("default_exercise_id", sa.String(length=64), sa.ForeignKey("gym_exercises.id", ondelete="SET NULL"), nullable=True),
        sa.Column("selected_exercise_id", sa.String(length=64), sa.ForeignKey("gym_exercises.id", ondelete="SET NULL"), nullable=True),
        sa.Column("options", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_gym_day_assignments_day_key", "gym_day_assignments", ["day_key"])

    op.create_table(
        "gym_exercise_history",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("exercise_id", sa.String(length=64), sa.ForeignKey("gym_exercises.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("day_key", sa.String(length=16), nullable=True),
        sa.Column("slot_id", sa.String(length=64), nullable=True),
        sa.Column("sets", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_gym_exercise_history_exercise_id", "gym_exercise_history", ["exercise_id"])

    op.drop_table("workout_sessions")


def downgrade() -> None:
    op.create_table(
        "workout_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(), nullable=False),
        sa.Column("duration_minutes", sa.Float(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="planned"),
    )

    op.drop_index("ix_gym_exercise_history_exercise_id", table_name="gym_exercise_history")
    op.drop_table("gym_exercise_history")
    op.drop_index("ix_gym_day_assignments_day_key", table_name="gym_day_assignments")
    op.drop_table("gym_day_assignments")
    op.drop_table("gym_exercises")
