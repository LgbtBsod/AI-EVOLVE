from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class InventoryWidget:
    title: str = "Inventory"
    items: List[str] = field(default_factory=list)

    def add_item(self, item_name: str) -> None:
        self.items.append(item_name)

    def remove_item(self, item_name: str) -> None:
        if item_name in self.items:
            self.items.remove(item_name)
