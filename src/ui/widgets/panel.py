from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass
class PanelStyle:
    width: float = 0.4
    height: float = 0.3


class NeonPanel:
    def __init__(self, title: str = "", style: PanelStyle | None = None, parent=None):
        self.title = title
        self.style = style or PanelStyle()
        self.parent = parent
        self.position: Tuple[float, float, float] = (0, 0, 0)

    def create(self, pos: Tuple[float, float, float] = (0, 0, 0)):
        self.position = pos
        return self
