import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String

from ..core.database import Base


def _default_board_state() -> list:
    return [[[[None for _ in range(3)] for _ in range(3)] for _ in range(3)] for _ in range(3)]


def _default_subgrid_state() -> list:
    return [[None for _ in range(3)] for _ in range(3)]


class UltimateTicTacToeGame(Base):
    __tablename__ = "ultimate_ttt_games"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    player_x_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    player_o_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    bot_symbol = Column(String(1), nullable=True)
    mode = Column(String(16), nullable=False, default="human")
    status = Column(String(16), nullable=False, default="active")
    winner = Column(String(8), nullable=True)
    current_player = Column(String(1), nullable=False, default="X")
    next_board_row = Column(Integer, nullable=True)
    next_board_col = Column(Integer, nullable=True)
    board_state = Column(JSON, nullable=False, default=_default_board_state)
    subgrid_state = Column(JSON, nullable=False, default=_default_subgrid_state)
    last_move_json = Column(JSON, nullable=True)
    move_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)


class UltimateTicTacToeMove(Base):
    __tablename__ = "ultimate_ttt_moves"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    game_id = Column(String(36), ForeignKey("ultimate_ttt_games.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    symbol = Column(String(1), nullable=False)
    board_row = Column(Integer, nullable=False)
    board_col = Column(Integer, nullable=False)
    cell_row = Column(Integer, nullable=False)
    cell_col = Column(Integer, nullable=False)
    move_index = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class UltimateTicTacToeInvite(Base):
    __tablename__ = "ultimate_ttt_invites"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(64), nullable=False, unique=True, index=True)
    from_user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    to_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    game_id = Column(String(36), ForeignKey("ultimate_ttt_games.id", ondelete="SET NULL"), nullable=True, index=True)
    mode = Column(String(16), nullable=False, default="human")
    status = Column(String(16), nullable=False, default="pending")
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    responded_at = Column(DateTime, nullable=True)


class UltimateTicTacToePresence(Base):
    __tablename__ = "ultimate_ttt_presence"

    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    last_seen_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
