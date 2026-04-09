from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa


revision = "0009_budget_categories"
down_revision = "0008_long_term_category_split"
branch_labels = None
depends_on = None


DEFAULT_CATEGORIES = ["Investments", "Rusty", "Household", "Extra"]


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

    bind = op.get_bind()
    user_ids = [row[0] for row in bind.execute(sa.text("SELECT id FROM users"))]
    distinct_entries = bind.execute(sa.text("SELECT DISTINCT user_id, category FROM budget_entries")).fetchall()

    seen: set[tuple[str, str]] = set()
    rows: list[dict[str, str]] = []

    for user_id in user_ids:
        for name in DEFAULT_CATEGORIES:
            key = (user_id, name.lower())
            if key in seen:
                continue
            seen.add(key)
            rows.append({"id": str(uuid.uuid4()), "user_id": user_id, "name": name})

    for user_id, name in distinct_entries:
        normalized = " ".join(str(name or "").split()).strip()
        if not normalized:
            continue
        key = (user_id, normalized.lower())
        if key in seen:
            continue
        seen.add(key)
        rows.append({"id": str(uuid.uuid4()), "user_id": user_id, "name": normalized})

    if rows:
        budget_categories = sa.table(
            "budget_categories",
            sa.column("id", sa.String(length=36)),
            sa.column("user_id", sa.String(length=36)),
            sa.column("name", sa.String(length=64)),
        )
        op.bulk_insert(budget_categories, rows)


def downgrade() -> None:
    op.drop_index("ix_budget_categories_user_id", table_name="budget_categories")
    op.drop_table("budget_categories")