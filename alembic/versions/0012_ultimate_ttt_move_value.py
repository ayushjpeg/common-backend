from alembic import op
import sqlalchemy as sa

revision = "0012_ultimate_ttt_move_value"
down_revision = "0011_ultimate_ttt_multiplayer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ultimate_ttt_moves", sa.Column("value", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("ultimate_ttt_moves", "value")
