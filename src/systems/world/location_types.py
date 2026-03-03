from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WorldLocation:
    x: float
    y: float
    z: float = 0.0
