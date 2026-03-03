from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass
class TextStyle:
    color: Tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
    scale: float = 0.05


class NeonText:
    def __init__(self, text: str, pos: Tuple[float, float], style: TextStyle | None = None, parent=None):
        self.text = text
        self.pos = pos
        self.style = style or TextStyle()
        self.parent = parent

    def create(self):
        return self

    def set_text(self, text: str) -> None:
        self.text = text

    def set_position(self, pos: Tuple[float, float]) -> None:
        self.pos = pos
