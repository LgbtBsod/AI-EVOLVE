"""Game states and state transitions."""
from __future__ import annotations

from enum import Enum, auto


class GameState(Enum):
    MENU = auto()
    LOADING = auto()
    RUNNING = auto()
    PAUSED = auto()
    GAME_OVER = auto()
    EXITING = auto()
