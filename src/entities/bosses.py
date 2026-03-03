"""Boss entity model."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BossType(Enum):
    BASIC = "basic"
    ELITE = "elite"


@dataclass
class Boss:
    boss_id: str
    boss_type: BossType = BossType.BASIC
    health: float = 500.0
