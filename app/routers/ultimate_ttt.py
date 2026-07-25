from __future__ import annotations

from datetime import datetime, timedelta
import random
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.security import get_current_user, require_api_key
from ..models.ultimate_ttt import UltimateTicTacToeGame, UltimateTicTacToeInvite, UltimateTicTacToeMove, UltimateTicTacToePresence
from ..models.user import User
from ..schemas.ultimate_ttt import ActivePlayerRead, GameCreateBot, GamePoint, GameRead, InviteCreate, InviteRead, MoveCreate, PresenceAck
from ..services.ultimate_ttt_logic import apply_move, initial_board_state, initial_subgrid_state, legal_moves, legal_values_for_subgrid

router = APIRouter(prefix="/ultimate-ttt", tags=["ultimate-ttt"], dependencies=[Depends(require_api_key)])

ACTIVE_PLAYER_WINDOW_SECONDS = 120


def _player_payload(user: User | None) -> dict | None:
    if user is None:
        return None
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "picture_url": user.picture_url,
    }


def _get_player_symbol(game: UltimateTicTacToeGame, user_id: str) -> str | None:
    if game.player_x_user_id == user_id:
        return "X"
    if game.player_o_user_id == user_id:
        return "O"
    return None


def _invite_url(request: Request, code: str) -> str:
    return f"{request.base_url}api/ultimate-ttt/invites/{code}".replace("//api", "/api")


def _serialize_invite(db: Session, request: Request, invite: UltimateTicTacToeInvite) -> InviteRead:
    from_user = db.get(User, invite.from_user_id)
    to_user = db.get(User, invite.to_user_id) if invite.to_user_id else None
    return InviteRead(
        id=invite.id,
        code=invite.code,
        from_user=_player_payload(from_user),
        to_user=_player_payload(to_user),
        game_id=invite.game_id,
        mode=invite.mode,
        status=invite.status,
        expires_at=invite.expires_at,
        created_at=invite.created_at,
        responded_at=invite.responded_at,
        invite_url=_invite_url(request, invite.code),
    )


def _serialize_game(db: Session, game: UltimateTicTacToeGame, current_user_id: str) -> GameRead:
    player_x = db.get(User, game.player_x_user_id) if game.player_x_user_id else None
    player_o = db.get(User, game.player_o_user_id) if game.player_o_user_id else None
    moves = legal_moves(game.board_state, game.subgrid_state, game.next_board_row, game.next_board_col) if game.status == "active" else []
    return GameRead(
        id=game.id,
        mode=game.mode,
        status=game.status,
        winner=game.winner,
        current_player=game.current_player,
        you_symbol=_get_player_symbol(game, current_user_id),
        bot_symbol=game.bot_symbol,
        next_board_row=game.next_board_row,
        next_board_col=game.next_board_col,
        board_state=game.board_state,
        subgrid_state=game.subgrid_state,
        last_move_json=game.last_move_json,
        move_count=game.move_count,
        created_at=game.created_at,
        updated_at=game.updated_at,
        player_x=_player_payload(player_x),
        player_o=_player_payload(player_o),
        legal_moves=[
            GamePoint(board_row=board_row, board_col=board_col, cell_row=cell_row, cell_col=cell_col)
            for board_row, board_col, cell_row, cell_col in moves
        ],
    )


def _ensure_game_access(game: UltimateTicTacToeGame | None, user_id: str) -> UltimateTicTacToeGame:
    if not game:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")
    if user_id not in {game.player_x_user_id, game.player_o_user_id, game.created_by_user_id}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not part of this game")
    return game


def _apply_recorded_move(
    db: Session,
    game: UltimateTicTacToeGame,
    symbol: str,
    user_id: str | None,
    move: tuple[int, int, int, int],
    value: int,
) -> None:
    result = apply_move(game.board_state, game.subgrid_state, move, symbol, value)
    board_row, board_col, cell_row, cell_col = move

    game.board_state = result["board_state"]
    game.subgrid_state = result["subgrid_state"]
    game.next_board_row = result["next_board_row"]
    game.next_board_col = result["next_board_col"]
    game.move_count += 1
    game.last_move_json = {
        "symbol": symbol,
        "value": value,
        "board_row": board_row,
        "board_col": board_col,
        "cell_row": cell_row,
        "cell_col": cell_col,
    }

    if result["is_finished"]:
        game.status = "finished"
        game.winner = result["winner"]
        game.finished_at = datetime.utcnow()
    else:
        game.current_player = "O" if symbol == "X" else "X"

    db.add(
        UltimateTicTacToeMove(
            game_id=game.id,
            user_id=user_id,
            symbol=symbol,
            board_row=board_row,
            board_col=board_col,
            cell_row=cell_row,
            cell_col=cell_col,
            value=value,
            move_index=game.move_count,
        )
    )


def _execute_bot_turn_if_needed(db: Session, game: UltimateTicTacToeGame) -> None:
    if game.mode != "bot" or game.status != "active" or not game.bot_symbol:
        return
    if game.current_player != game.bot_symbol:
        return

    valid_moves = legal_moves(game.board_state, game.subgrid_state, game.next_board_row, game.next_board_col)
    if not valid_moves:
        game.status = "finished"
        game.winner = "D"
        game.finished_at = datetime.utcnow()
        return

    chosen_move = random.choice(valid_moves)
    board_row, board_col, _, _ = chosen_move
    values = legal_values_for_subgrid(game.board_state, board_row, board_col)
    if not values:
        game.status = "finished"
        game.winner = "D"
        game.finished_at = datetime.utcnow()
        return
    chosen_value = random.choice(values)
    _apply_recorded_move(db, game, game.bot_symbol, None, chosen_move, chosen_value)


def _generate_invite_code() -> str:
    return secrets.token_urlsafe(9).replace("-", "").replace("_", "")[:12]


@router.post("/presence/heartbeat", response_model=PresenceAck)
def heartbeat_presence(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    now = datetime.utcnow()
    presence = db.get(UltimateTicTacToePresence, current_user.id)
    if presence is None:
        presence = UltimateTicTacToePresence(user_id=current_user.id, last_seen_at=now)
    else:
        presence.last_seen_at = now
    db.add(presence)
    db.commit()
    return PresenceAck(seen_at=now)


@router.get("/players/active", response_model=list[ActivePlayerRead])
def active_players(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    cutoff = datetime.utcnow() - timedelta(seconds=ACTIVE_PLAYER_WINDOW_SECONDS)
    rows = (
        db.query(UltimateTicTacToePresence, User)
        .join(User, User.id == UltimateTicTacToePresence.user_id)
        .filter(UltimateTicTacToePresence.last_seen_at >= cutoff)
        .order_by(UltimateTicTacToePresence.last_seen_at.desc())
        .all()
    )

    payload: list[ActivePlayerRead] = []
    for presence, user in rows:
        payload.append(
            ActivePlayerRead(
                user=_player_payload(user),
                last_seen_at=presence.last_seen_at,
                is_self=user.id == current_user.id,
            )
        )
    return payload


@router.post("/invites", response_model=InviteRead, status_code=status.HTTP_201_CREATED)
def create_invite(
    payload: InviteCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.target_user_id and payload.target_user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot invite yourself")

    target_user = None
    if payload.target_user_id:
        target_user = db.get(User, payload.target_user_id)
        if target_user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target user not found")

    invite = UltimateTicTacToeInvite(
        code=_generate_invite_code(),
        from_user_id=current_user.id,
        to_user_id=target_user.id if target_user else None,
        mode="human",
        status="pending",
        expires_at=datetime.utcnow() + timedelta(minutes=payload.expires_minutes),
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return _serialize_invite(db, request, invite)


@router.get("/invites/incoming", response_model=list[InviteRead])
def list_incoming_invites(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    now = datetime.utcnow()
    invites = (
        db.query(UltimateTicTacToeInvite)
        .filter(
            UltimateTicTacToeInvite.status == "pending",
            UltimateTicTacToeInvite.expires_at > now,
            UltimateTicTacToeInvite.from_user_id != current_user.id,
            or_(UltimateTicTacToeInvite.to_user_id.is_(None), UltimateTicTacToeInvite.to_user_id == current_user.id),
        )
        .order_by(UltimateTicTacToeInvite.created_at.desc())
        .all()
    )
    return [_serialize_invite(db, request, invite) for invite in invites]


@router.get("/invites/outgoing", response_model=list[InviteRead])
def list_outgoing_invites(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    invites = (
        db.query(UltimateTicTacToeInvite)
        .filter(UltimateTicTacToeInvite.from_user_id == current_user.id)
        .order_by(UltimateTicTacToeInvite.created_at.desc())
        .limit(50)
        .all()
    )
    return [_serialize_invite(db, request, invite) for invite in invites]


@router.get("/invites/{code}", response_model=InviteRead)
def get_invite(code: str, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    invite = db.query(UltimateTicTacToeInvite).filter(UltimateTicTacToeInvite.code == code).first()
    if not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")
    return _serialize_invite(db, request, invite)


@router.post("/invites/{code}/accept", response_model=GameRead)
def accept_invite(code: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    invite = (
        db.query(UltimateTicTacToeInvite)
        .filter(UltimateTicTacToeInvite.code == code)
        .with_for_update()
        .first()
    )
    if not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")
    if invite.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invite is no longer pending")
    if invite.expires_at <= datetime.utcnow():
        invite.status = "expired"
        db.add(invite)
        db.commit()
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Invite expired")
    if invite.from_user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot accept your own invite")
    if invite.to_user_id and invite.to_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invite is assigned to another player")

    game = UltimateTicTacToeGame(
        created_by_user_id=invite.from_user_id,
        player_x_user_id=invite.from_user_id,
        player_o_user_id=current_user.id,
        mode="human",
        status="active",
        current_player="X",
        board_state=initial_board_state(),
        subgrid_state=initial_subgrid_state(),
        started_at=datetime.utcnow(),
    )
    db.add(game)
    db.flush()

    invite.status = "accepted"
    invite.responded_at = datetime.utcnow()
    invite.to_user_id = current_user.id
    invite.game_id = game.id
    db.add(invite)

    db.commit()
    db.refresh(game)
    return _serialize_game(db, game, current_user.id)


@router.post("/invites/{invite_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
def cancel_invite(invite_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    invite = db.get(UltimateTicTacToeInvite, invite_id)
    if not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")
    if invite.from_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the sender can cancel invite")
    if invite.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only pending invite can be cancelled")

    invite.status = "cancelled"
    invite.responded_at = datetime.utcnow()
    db.add(invite)
    db.commit()


@router.post("/games/bot", response_model=GameRead, status_code=status.HTTP_201_CREATED)
def create_bot_game(payload: GameCreateBot, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if payload.human_symbol == "X":
        player_x_user_id = current_user.id
        player_o_user_id = None
        bot_symbol = "O"
    else:
        player_x_user_id = None
        player_o_user_id = current_user.id
        bot_symbol = "X"

    game = UltimateTicTacToeGame(
        created_by_user_id=current_user.id,
        player_x_user_id=player_x_user_id,
        player_o_user_id=player_o_user_id,
        mode="bot",
        status="active",
        bot_symbol=bot_symbol,
        current_player="X",
        board_state=initial_board_state(),
        subgrid_state=initial_subgrid_state(),
        started_at=datetime.utcnow(),
    )
    db.add(game)
    db.flush()

    _execute_bot_turn_if_needed(db, game)

    db.commit()
    db.refresh(game)
    return _serialize_game(db, game, current_user.id)


@router.get("/games", response_model=list[GameRead])
def list_games(state: str = "active", db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = db.query(UltimateTicTacToeGame).filter(
        or_(
            UltimateTicTacToeGame.player_x_user_id == current_user.id,
            UltimateTicTacToeGame.player_o_user_id == current_user.id,
            UltimateTicTacToeGame.created_by_user_id == current_user.id,
        )
    )

    if state == "active":
        query = query.filter(UltimateTicTacToeGame.status == "active")
    elif state == "finished":
        query = query.filter(UltimateTicTacToeGame.status == "finished")

    games = query.order_by(UltimateTicTacToeGame.updated_at.desc()).limit(50).all()
    return [_serialize_game(db, game, current_user.id) for game in games]


@router.get("/games/{game_id}", response_model=GameRead)
def get_game(game_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    game = db.get(UltimateTicTacToeGame, game_id)
    game = _ensure_game_access(game, current_user.id)
    return _serialize_game(db, game, current_user.id)


@router.post("/games/{game_id}/moves", response_model=GameRead)
def make_move(game_id: str, payload: MoveCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    game = db.get(UltimateTicTacToeGame, game_id)
    game = _ensure_game_access(game, current_user.id)
    if game.status != "active":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Game is not active")

    symbol = _get_player_symbol(game, current_user.id)
    if not symbol:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are a spectator in this game")

    if game.current_player != symbol:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Not your turn")

    candidate_move = (payload.board_row, payload.board_col, payload.cell_row, payload.cell_col)
    valid_moves = legal_moves(game.board_state, game.subgrid_state, game.next_board_row, game.next_board_col)
    if candidate_move not in valid_moves:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Illegal move for current board state")

    valid_values = legal_values_for_subgrid(game.board_state, payload.board_row, payload.board_col)
    if payload.value not in valid_values:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Value already used in this subgrid")

    _apply_recorded_move(db, game, symbol, current_user.id, candidate_move, payload.value)
    _execute_bot_turn_if_needed(db, game)

    db.add(game)
    db.commit()
    db.refresh(game)
    return _serialize_game(db, game, current_user.id)
