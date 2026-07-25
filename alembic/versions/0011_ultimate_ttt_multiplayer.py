from alembic import op
import sqlalchemy as sa

revision = "0011_ultimate_ttt_multiplayer"
down_revision = "0010_budget_reset_dev_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ultimate_ttt_games",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("player_x_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("player_o_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("bot_symbol", sa.String(length=1), nullable=True),
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="human"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("winner", sa.String(length=8), nullable=True),
        sa.Column("current_player", sa.String(length=1), nullable=False, server_default="X"),
        sa.Column("next_board_row", sa.Integer(), nullable=True),
        sa.Column("next_board_col", sa.Integer(), nullable=True),
        sa.Column("board_state", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("subgrid_state", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("last_move_json", sa.JSON(), nullable=True),
        sa.Column("move_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_ultimate_ttt_games_created_by_user_id", "ultimate_ttt_games", ["created_by_user_id"])
    op.create_index("ix_ultimate_ttt_games_player_x_user_id", "ultimate_ttt_games", ["player_x_user_id"])
    op.create_index("ix_ultimate_ttt_games_player_o_user_id", "ultimate_ttt_games", ["player_o_user_id"])

    op.create_table(
        "ultimate_ttt_moves",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("game_id", sa.String(length=36), sa.ForeignKey("ultimate_ttt_games.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("symbol", sa.String(length=1), nullable=False),
        sa.Column("board_row", sa.Integer(), nullable=False),
        sa.Column("board_col", sa.Integer(), nullable=False),
        sa.Column("cell_row", sa.Integer(), nullable=False),
        sa.Column("cell_col", sa.Integer(), nullable=False),
        sa.Column("move_index", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_ultimate_ttt_moves_game_id", "ultimate_ttt_moves", ["game_id"])
    op.create_index("ix_ultimate_ttt_moves_user_id", "ultimate_ttt_moves", ["user_id"])

    op.create_table(
        "ultimate_ttt_invites",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("from_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("to_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("game_id", sa.String(length=36), sa.ForeignKey("ultimate_ttt_games.id", ondelete="SET NULL"), nullable=True),
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="human"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("responded_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("code", name="uq_ultimate_ttt_invites_code"),
    )
    op.create_index("ix_ultimate_ttt_invites_code", "ultimate_ttt_invites", ["code"], unique=True)
    op.create_index("ix_ultimate_ttt_invites_from_user_id", "ultimate_ttt_invites", ["from_user_id"])
    op.create_index("ix_ultimate_ttt_invites_to_user_id", "ultimate_ttt_invites", ["to_user_id"])
    op.create_index("ix_ultimate_ttt_invites_game_id", "ultimate_ttt_invites", ["game_id"])

    op.create_table(
        "ultimate_ttt_presence",
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_ultimate_ttt_presence_last_seen_at", "ultimate_ttt_presence", ["last_seen_at"])


def downgrade() -> None:
    op.drop_index("ix_ultimate_ttt_presence_last_seen_at", table_name="ultimate_ttt_presence")
    op.drop_table("ultimate_ttt_presence")

    op.drop_index("ix_ultimate_ttt_invites_game_id", table_name="ultimate_ttt_invites")
    op.drop_index("ix_ultimate_ttt_invites_to_user_id", table_name="ultimate_ttt_invites")
    op.drop_index("ix_ultimate_ttt_invites_from_user_id", table_name="ultimate_ttt_invites")
    op.drop_index("ix_ultimate_ttt_invites_code", table_name="ultimate_ttt_invites")
    op.drop_table("ultimate_ttt_invites")

    op.drop_index("ix_ultimate_ttt_moves_user_id", table_name="ultimate_ttt_moves")
    op.drop_index("ix_ultimate_ttt_moves_game_id", table_name="ultimate_ttt_moves")
    op.drop_table("ultimate_ttt_moves")

    op.drop_index("ix_ultimate_ttt_games_player_o_user_id", table_name="ultimate_ttt_games")
    op.drop_index("ix_ultimate_ttt_games_player_x_user_id", table_name="ultimate_ttt_games")
    op.drop_index("ix_ultimate_ttt_games_created_by_user_id", table_name="ultimate_ttt_games")
    op.drop_table("ultimate_ttt_games")
