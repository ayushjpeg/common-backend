from __future__ import annotations

from pathlib import Path
import logging
import os
import random
import re
import threading
import tempfile

from .ultimate_ttt_logic import legal_moves, legal_values_for_subgrid

logger = logging.getLogger(__name__)

ACTION_SPACE_SIZE = 9 * 9 * 9
_MODEL_LOCK = threading.Lock()
_POLICY_MODELS: dict[str, object | None] = {}
_LOAD_ATTEMPTED: set[str] = set()

DEFAULT_MODEL_VERSION = "v1"


def _models_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "model_artifacts" / "ultimate_ttt"


def _normalize_model_version(model_version: str | None) -> str:
    version = (model_version or "").strip() or DEFAULT_MODEL_VERSION
    if re.fullmatch(r"[A-Za-z0-9_.-]+", version) is None:
        return DEFAULT_MODEL_VERSION
    return version


def list_available_model_versions() -> list[str]:
    model_dir = _models_dir()
    if not model_dir.exists():
        return [DEFAULT_MODEL_VERSION]

    versions = [path.stem for path in model_dir.glob("*.pt") if path.is_file()]
    if not versions:
        return [DEFAULT_MODEL_VERSION]

    def _sort_key(value: str) -> tuple[int, int | str]:
        match = re.fullmatch(r"v(\d+)", value.lower())
        if match:
            return (0, int(match.group(1)))
        return (1, value)

    return sorted(set(versions), key=_sort_key)


def _default_model_path() -> Path:
    # Inside common-backend app package: /app/app/model_artifacts/ultimate_ttt/v1.pt
    return _models_dir() / f"{DEFAULT_MODEL_VERSION}.pt"


def _model_path_for_version(model_version: str) -> Path:
    return _models_dir() / f"{model_version}.pt"


def _legacy_dev_model_path() -> Path:
    return Path(__file__).resolve().parents[3] / "NumberTTT-Training" / "artifacts" / "latest.pt"


def _download_model_if_needed(target_path: Path) -> None:
    model_url = os.getenv("UTTT_MODEL_URL", "").strip()
    if not model_url:
        return
    if target_path.exists():
        return

    try:
        import requests

        target_path.parent.mkdir(parents=True, exist_ok=True)
        with requests.get(model_url, timeout=60, stream=True) as response:
            response.raise_for_status()
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pt") as tmp:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        tmp.write(chunk)
                temp_path = Path(tmp.name)

        temp_path.replace(target_path)
        logger.info("Downloaded Ultimate TTT model from UTTT_MODEL_URL to %s", target_path)
    except Exception as exc:  # pragma: no cover - runtime network resilience
        logger.warning("Failed downloading model from UTTT_MODEL_URL (%s)", exc)


def _resolve_model_path(model_version: str | None = None) -> Path:
    explicit = os.getenv("UTTT_MODEL_PATH", "").strip()
    if explicit:
        return Path(explicit)

    normalized = _normalize_model_version(model_version)
    version_path = _model_path_for_version(normalized)
    if version_path.exists():
        return version_path

    container_default = _default_model_path()
    if container_default.exists():
        return container_default

    latest_path = _models_dir() / "latest.pt"
    if latest_path.exists():
        return latest_path

    legacy = _legacy_dev_model_path()
    if legacy.exists():
        return legacy

    return version_path


def _action_to_index(board_row: int, board_col: int, cell_row: int, cell_col: int, value: int) -> int:
    board_idx = board_row * 3 + board_col
    cell_idx = cell_row * 3 + cell_col
    value_idx = value - 1
    return board_idx * 81 + cell_idx * 9 + value_idx


def _encode_state(
    board_state: list,
    subgrid_state: list,
    current_player: str,
    next_board_row: int | None,
    next_board_col: int | None,
) -> list[float]:
    board_values: list[float] = []
    for board_row in range(3):
        for board_col in range(3):
            for cell_row in range(3):
                for cell_col in range(3):
                    value = board_state[board_row][board_col][cell_row][cell_col]
                    board_values.append(float(value or 0) / 9.0)

    status_values: list[float] = []
    for row in subgrid_state:
        for cell in row:
            status_values.extend(
                [
                    1.0 if cell == "X" else 0.0,
                    1.0 if cell == "O" else 0.0,
                    1.0 if cell == "D" else 0.0,
                    1.0 if cell is None else 0.0,
                ]
            )

    current_player_value = [1.0 if current_player == "X" else 0.0]
    target_values = [0.0] * 9
    if next_board_row is not None and next_board_col is not None:
        target_values[next_board_row * 3 + next_board_col] = 1.0

    return board_values + status_values + current_player_value + target_values


def _build_policy_net(input_dim: int, hidden_dim: int, hidden_layers: int):
    import torch.nn as nn

    if hidden_layers < 1:
        hidden_layers = 1

    layers: list[nn.Module] = [nn.Linear(input_dim, hidden_dim), nn.ReLU()]
    for _ in range(hidden_layers - 1):
        layers.extend([nn.Linear(hidden_dim, hidden_dim), nn.ReLU()])
    layers.append(nn.Linear(hidden_dim, ACTION_SPACE_SIZE))

    class _PolicyNet(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.net = nn.Sequential(*layers)

        def forward(self, x):
            return self.net(x)

    return _PolicyNet()


def _load_policy_model(model_version: str | None = None):
    model_path = _resolve_model_path(model_version)
    _download_model_if_needed(model_path)

    if not model_path.exists():
        logger.warning(
            "Ultimate TTT model not found at %s; set UTTT_MODEL_PATH or UTTT_MODEL_URL; bot will use random fallback",
            model_path,
        )
        return None

    try:
        import torch
    except Exception as exc:  # pragma: no cover - runtime dependency guard
        logger.warning("torch import failed (%s); bot will use random fallback", exc)
        return None

    try:
        payload = torch.load(str(model_path), map_location="cpu")
        model = _build_policy_net(
            input_dim=int(payload["input_dim"]),
            hidden_dim=int(payload.get("hidden_dim", 384)),
            hidden_layers=int(payload.get("hidden_layers", 2)),
        )
        model.load_state_dict(payload["model_state_dict"])
        model.eval()
        logger.info("Loaded Ultimate TTT model from %s", model_path)
        return model
    except Exception as exc:  # pragma: no cover - startup resilience
        logger.warning("Failed to load Ultimate TTT model from %s (%s); using random fallback", model_path, exc)
        return None


def _get_policy_model(model_version: str | None = None):
    normalized = _normalize_model_version(model_version)
    if normalized in _LOAD_ATTEMPTED:
        return _POLICY_MODELS.get(normalized)

    with _MODEL_LOCK:
        if normalized not in _LOAD_ATTEMPTED:
            _POLICY_MODELS[normalized] = _load_policy_model(normalized)
            _LOAD_ATTEMPTED.add(normalized)
    return _POLICY_MODELS.get(normalized)


def choose_bot_move(
    board_state: list,
    subgrid_state: list,
    current_player: str,
    next_board_row: int | None,
    next_board_col: int | None,
    model_version: str | None = None,
) -> tuple[tuple[int, int, int, int], int, str] | None:
    legal_cells = legal_moves(board_state, subgrid_state, next_board_row, next_board_col)
    if not legal_cells:
        return None

    options: list[tuple[tuple[int, int, int, int], int, int]] = []
    for board_row, board_col, cell_row, cell_col in legal_cells:
        values = legal_values_for_subgrid(board_state, board_row, board_col)
        for value in values:
            idx = _action_to_index(board_row, board_col, cell_row, cell_col, value)
            options.append(((board_row, board_col, cell_row, cell_col), value, idx))

    if not options:
        return None

    model = _get_policy_model(model_version)
    if model is None:
        move, value, _ = random.choice(options)
        return move, value, "random_fallback"

    try:
        import torch

        encoded = _encode_state(board_state, subgrid_state, current_player, next_board_row, next_board_col)
        x = torch.tensor(encoded, dtype=torch.float32).unsqueeze(0)

        with torch.no_grad():
            logits = model(x).squeeze(0)

        indices = torch.tensor([idx for _, _, idx in options], dtype=torch.long)
        option_logits = logits[indices]
        best_option_idx = int(torch.argmax(option_logits).item())
        move, value, _ = options[best_option_idx]
        return move, value, "model"
    except Exception as exc:  # pragma: no cover - runtime resilience
        logger.warning("Model inference failed (%s); using random fallback", exc)
        move, value, _ = random.choice(options)
        return move, value, "random_fallback"
