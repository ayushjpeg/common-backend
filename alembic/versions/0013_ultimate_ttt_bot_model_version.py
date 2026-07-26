from alembic import op
import sqlalchemy as sa

revision = "0013_utt_bot_model_version"
down_revision = "0012_ultimate_ttt_move_value"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ultimate_ttt_games",
        sa.Column("bot_model_version", sa.String(length=32), nullable=True, server_default="v1"),
    )


def downgrade() -> None:
    op.drop_column("ultimate_ttt_games", "bot_model_version")
