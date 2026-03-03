"""Basic item entities."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ItemRarity(Enum):
    COMMON = "common"
    RARE = "rare"
    EPIC = "epic"


@dataclass
class Item:
    item_id: str
    name: str
    value: int = 0
    rarity: ItemRarity = ItemRarity.COMMON
