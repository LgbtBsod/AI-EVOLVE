"""Fallback lightweight game scene."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GameScene:
    name: str = "game"

    def initialize(self) -> bool:
        return True

    def update(self, dt: float) -> None:
        _ = dt

    def cleanup(self) -> None:
        return None
