from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ProgressBarStyle:
    width: float = 0.3
    height: float = 0.02


class NeonProgressBar:
    def __init__(self, title: str = "", style: ProgressBarStyle | None = None, parent=None):
        self.title = title
        self.style = style or ProgressBarStyle()
        self.parent = parent
        self.current_value = 0.0
        self.max_value = 100.0

    def create(self, pos=(0, 0, 0)):
        _ = pos
        return self

    def set_value(self, value: float, max_value: float | None = None):
        self.current_value = value
        if max_value is not None:
            self.max_value = max_value
