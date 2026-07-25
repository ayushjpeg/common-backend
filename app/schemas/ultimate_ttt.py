from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


GameMode = Literal["human", "bot"]
GameStatus = Literal["active", "finished", "cancelled"]


class PlayerMini(BaseModel):
    id: str
    email: str
    full_name: str | None = None
    picture_url: str | None = None

    class Config:
        from_attributes = True


class ActivePlayerRead(BaseModel):
    user: PlayerMini
    last_seen_at: datetime
    is_self: bool = False


class InviteCreate(BaseModel):
    target_user_id: str | None = None
    expires_minutes: int = Field(default=30, ge=5, le=60 * 24 * 7)


class GameCreateBot(BaseModel):
    human_symbol: Literal["X", "O"] = "X"


class MoveCreate(BaseModel):
    board_row: int = Field(ge=0, le=2)
    board_col: int = Field(ge=0, le=2)
    cell_row: int = Field(ge=0, le=2)
    cell_col: int = Field(ge=0, le=2)
    value: int = Field(ge=1, le=9)


class MoveRead(BaseModel):
    id: str
    game_id: str
    user_id: str | None = None
    symbol: str
    board_row: int
    board_col: int
    cell_row: int
    cell_col: int
    value: int
    move_index: int
    created_at: datetime

    class Config:
        from_attributes = True


class GamePoint(BaseModel):
    board_row: int
    board_col: int
    cell_row: int
    cell_col: int


class InviteRead(BaseModel):
    id: str
    code: str
    from_user: PlayerMini
    to_user: PlayerMini | None = None
    game_id: str | None = None
    mode: GameMode = "human"
    status: str
    expires_at: datetime
    created_at: datetime
    responded_at: datetime | None = None
    invite_url: str


class GameRead(BaseModel):
    id: str
    mode: GameMode = "human"
    status: GameStatus
    winner: str | None = None
    current_player: Literal["X", "O"]
    you_symbol: Literal["X", "O"] | None = None
    bot_symbol: Literal["X", "O"] | None = None
    next_board_row: int | None = None
    next_board_col: int | None = None
    board_state: list
    subgrid_state: list
    last_move_json: dict | None = None
    move_count: int
    created_at: datetime
    updated_at: datetime
    player_x: PlayerMini | None = None
    player_o: PlayerMini | None = None
    legal_moves: list[GamePoint] = Field(default_factory=list)
    number_range: list[int] = Field(default_factory=lambda: [1, 2, 3, 4, 5, 6, 7, 8, 9])


class PresenceAck(BaseModel):
    ok: bool = True
    seen_at: datetime
