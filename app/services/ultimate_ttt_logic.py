from __future__ import annotations

from copy import deepcopy

Symbol = str | None
Move = tuple[int, int, int, int]


def initial_board_state() -> list[list[list[list[Symbol]]]]:
    return [[[[None for _ in range(3)] for _ in range(3)] for _ in range(3)] for _ in range(3)]


def initial_subgrid_state() -> list[list[Symbol]]:
    return [[None for _ in range(3)] for _ in range(3)]


def _winner_of_grid(grid: list[list[Symbol]]) -> Symbol:
    lines = []
    lines.extend(grid)
    lines.extend([[grid[0][col], grid[1][col], grid[2][col]] for col in range(3)])
    lines.append([grid[0][0], grid[1][1], grid[2][2]])
    lines.append([grid[0][2], grid[1][1], grid[2][0]])
    for line in lines:
        if line[0] is not None and line[0] == line[1] == line[2]:
            return line[0]
    return None


def _is_grid_full(grid: list[list[Symbol]]) -> bool:
    return all(cell is not None for row in grid for cell in row)


def _is_subgrid_open(
    board_state: list[list[list[list[Symbol]]]],
    subgrid_state: list[list[Symbol]],
    board_row: int,
    board_col: int,
) -> bool:
    if subgrid_state[board_row][board_col] is not None:
        return False
    return not _is_grid_full(board_state[board_row][board_col])


def legal_moves(
    board_state: list[list[list[list[Symbol]]]],
    subgrid_state: list[list[Symbol]],
    next_board_row: int | None,
    next_board_col: int | None,
) -> list[Move]:
    candidates: list[tuple[int, int]] = []
    if next_board_row is not None and next_board_col is not None:
        if _is_subgrid_open(board_state, subgrid_state, next_board_row, next_board_col):
            candidates = [(next_board_row, next_board_col)]

    if not candidates:
        for board_row in range(3):
            for board_col in range(3):
                if _is_subgrid_open(board_state, subgrid_state, board_row, board_col):
                    candidates.append((board_row, board_col))

    moves: list[Move] = []
    for board_row, board_col in candidates:
        subgrid = board_state[board_row][board_col]
        for cell_row in range(3):
            for cell_col in range(3):
                if subgrid[cell_row][cell_col] is None:
                    moves.append((board_row, board_col, cell_row, cell_col))
    return moves


def _compute_subgrid_status(
    board_state: list[list[list[list[Symbol]]]],
    subgrid_state: list[list[Symbol]],
    board_row: int,
    board_col: int,
) -> None:
    subgrid = board_state[board_row][board_col]
    winner = _winner_of_grid(subgrid)
    if winner:
        subgrid_state[board_row][board_col] = winner
    elif _is_grid_full(subgrid):
        subgrid_state[board_row][board_col] = "D"


def _compute_match_winner(subgrid_state: list[list[Symbol]]) -> Symbol:
    projected = [[None if cell == "D" else cell for cell in row] for row in subgrid_state]
    return _winner_of_grid(projected)


def apply_move(
    board_state: list[list[list[list[Symbol]]]],
    subgrid_state: list[list[Symbol]],
    move: Move,
    symbol: str,
) -> dict:
    board_row, board_col, cell_row, cell_col = move
    next_board = deepcopy(board_state)
    next_subgrid = deepcopy(subgrid_state)

    next_board[board_row][board_col][cell_row][cell_col] = symbol
    _compute_subgrid_status(next_board, next_subgrid, board_row, board_col)

    winner = _compute_match_winner(next_subgrid)
    if winner:
        return {
            "board_state": next_board,
            "subgrid_state": next_subgrid,
            "winner": winner,
            "is_finished": True,
            "next_board_row": None,
            "next_board_col": None,
        }

    all_closed = all(cell is not None for row in next_subgrid for cell in row)
    if all_closed:
        return {
            "board_state": next_board,
            "subgrid_state": next_subgrid,
            "winner": "D",
            "is_finished": True,
            "next_board_row": None,
            "next_board_col": None,
        }

    target_row, target_col = cell_row, cell_col
    if _is_subgrid_open(next_board, next_subgrid, target_row, target_col):
        next_row, next_col = target_row, target_col
    else:
        next_row, next_col = None, None

    return {
        "board_state": next_board,
        "subgrid_state": next_subgrid,
        "winner": None,
        "is_finished": False,
        "next_board_row": next_row,
        "next_board_col": next_col,
    }
