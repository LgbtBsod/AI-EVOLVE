"""NPC entity model."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NPC:
    npc_id: str
    name: str
    health: float = 100.0
    dialogue: list[str] = field(default_factory=list)

    def is_alive(self) -> bool:
        return self.health > 0
