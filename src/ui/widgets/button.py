from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Tuple


@dataclass
class ButtonStyle:
    width: float = 0.2
    height: float = 0.08


class NeonButton:
    def __init__(self, text: str, pos: Tuple[float, float, float] = (0, 0, 0),
                 command: Callable | None = None, style: ButtonStyle | None = None, parent=None):
        self.text = text
        self.pos = pos
        self.command = command
        self.style = style or ButtonStyle()
        self.parent = parent

    def create(self):
        return self

    def click(self):
        if self.command:
            self.command()
