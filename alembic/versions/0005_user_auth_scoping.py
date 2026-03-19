from datetime import datetime

from alembic import op
import sqlalchemy as sa

revision = "0005_user_auth_scoping"
down_revision = "0004_food_fields"
branch_labels = None
depends_on = None

AYUSH_USER_ID = "b0c53a8a-5ec4-4fa6-a1fb-d6a46b0f16cb"
AYUSH_EMAIL = "ayushjpeg@gmail.com"


def _add_user_fk(table_name: str, fk_name: str) -> None:
    op.create_foreign_key(fk_name, table_name, "users", ["user_id"], ["id"], ondelete="CASCADE")
    op.create_index(f"ix_{table_name}_user_id", table_name, ["user_id"])


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("google_sub", sa.String(length=255), nullable=True),
        sa.Column("picture_url", sa.String(length=512), nullable=True),
        sa.Column("preferences_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("google_sub", name="uq_users_google_sub"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_google_sub", "users", ["google_sub"], unique=True)

    users_table = sa.table(
        "users",
        sa.column("id", sa.String(length=36)),
        sa.column("email", sa.String(length=255)),
        sa.column("full_name", sa.String(length=255)),
        sa.column("google_sub", sa.String(length=255)),
        sa.column("picture_url", sa.String(length=512)),
        sa.column("preferences_json", sa.JSON()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
        sa.column("last_login_at", sa.DateTime()),
    )
    now = datetime.utcnow()
    op.bulk_insert(
        users_table,
        [
            {
                "id": AYUSH_USER_ID,
                "email": AYUSH_EMAIL,
                "full_name": "Ayush",
                "google_sub": None,
                "picture_url": None,
                "preferences_json": {},
                "created_at": now,
                "updated_at": now,
                "last_login_at": None,
            }
        ],
    )

    for table_name in [
        "task_templates",
        "task_history",
        "meal_entries",
        "food_images",
        "gym_exercises",
        "gym_day_assignments",
        "gym_exercise_history",
    ]:
        op.add_column(table_name, sa.Column("user_id", sa.String(length=36), nullable=True))
        op.execute(sa.text(f"UPDATE {table_name} SET user_id = :user_id WHERE user_id IS NULL").bindparams(user_id=AYUSH_USER_ID))
        op.alter_column(table_name, "user_id", nullable=False)

    _add_user_fk("task_templates", "fk_task_templates_user_id_users")
    _add_user_fk("task_history", "fk_task_history_user_id_users")
    _add_user_fk("meal_entries", "fk_meal_entries_user_id_users")
    _add_user_fk("food_images", "fk_food_images_user_id_users")
    _add_user_fk("gym_exercises", "fk_gym_exercises_user_id_users")
    _add_user_fk("gym_day_assignments", "fk_gym_day_assignments_user_id_users")
    _add_user_fk("gym_exercise_history", "fk_gym_exercise_history_user_id_users")


def downgrade() -> None:
    for table_name, fk_name in [
        ("gym_exercise_history", "fk_gym_exercise_history_user_id_users"),
        ("gym_day_assignments", "fk_gym_day_assignments_user_id_users"),
        ("gym_exercises", "fk_gym_exercises_user_id_users"),
        ("food_images", "fk_food_images_user_id_users"),
        ("meal_entries", "fk_meal_entries_user_id_users"),
        ("task_history", "fk_task_history_user_id_users"),
        ("task_templates", "fk_task_templates_user_id_users"),
    ]:
        op.drop_constraint(fk_name, table_name, type_="foreignkey")
        op.drop_index(f"ix_{table_name}_user_id", table_name=table_name)
        op.drop_column(table_name, "user_id")

    op.drop_index("ix_users_google_sub", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")