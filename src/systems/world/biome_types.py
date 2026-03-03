from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BiomeType(Enum):
    PLAINS = "plains"
    FOREST = "forest"
    DESERT = "desert"


@dataclass
class BiomeInfo:
    biome: BiomeType
    difficulty: float = 1.0
