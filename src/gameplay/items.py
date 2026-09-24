"""Предметы игры: определения из Lua (lua_content/items/*.lua) и каталог.

Файл предметов возвращает либо один предмет (как сгенерированный билдером
sorrow_of_berserk.lua), либо { items = { ... } }. Поля - в шапке
lua_content/items/game_items.lua. Каталог грузится один раз и кэшируется
(lua_bridge: JSON-кэш по хэшу файла).
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Optional

logger = logging.getLogger(__name__)

EQUIP_SLOTS = ("weapon", "armor", "amulet", "ring", "trinket")
KINDS = ("equipment", "consumable", "map", "artifact", "material")
RARITY_ORDER = {"common": 0, "rare": 1, "epic": 2, "legendary": 3}


@dataclass(frozen=True)
class ItemDef:
    id: str
    name: str
    kind: str = "equipment"
    slot: Optional[str] = None
    rarity: str = "common"
    value: int = 10
    stats: dict[str, float] = field(default_factory=dict)       # статы схемы, пока надет
    effects: tuple[dict, ...] = ()                              # эффекты схемы
    knowledge: Optional[dict] = None                            # что открывает (карты, артефакты)
    description: str = ""

    @property
    def equippable(self) -> bool:
        return self.kind in ("equipment", "artifact") and self.slot in EQUIP_SLOTS

    @property
    def usable(self) -> bool:
        return self.kind == "consumable"

    def restores(self) -> set[str]:
        """Какие ресурсы лечит расходник (hp/mana/stamina) - для решений ИИ."""
        out = set()
        for ef in self.effects:
            if (ef.get("trigger") or {}).get("event") != "use":
                continue
            for o in ef.get("ops") or []:
                if o.get("kind") == "heal" and o.get("target", "self") == "self":
                    out.add(o.get("stat") or "hp")
        return out

    @staticmethod
    def from_lua(d: dict) -> "ItemDef":
        effects = d.get("effects") or []
        kind = d.get("kind") or ("equipment" if effects or d.get("stats") else "material")
        slot = d.get("slot") or ("amulet" if kind == "equipment" else None)
        return ItemDef(
            id=str(d.get("id") or d.get("name")),
            name=str(d.get("name") or d.get("id")),
            kind=kind, slot=slot,
            rarity=str(d.get("rarity") or "common"),
            value=int(d.get("value") or 10),
            stats={k: float(v) for k, v in (d.get("stats") or {}).items()},
            effects=tuple(effects),
            knowledge=d.get("knowledge") or None,
            description=str(d.get("description") or ""),
        )


class ItemCatalog:
    """Все предметы игры по id."""

    def __init__(self, items: dict[str, ItemDef]):
        self.items = items

    def get(self, item_id: str) -> Optional[ItemDef]:
        return self.items.get(item_id)

    def __contains__(self, item_id: str) -> bool:
        return item_id in self.items

    def __len__(self) -> int:
        return len(self.items)

    def by_kind(self, *kinds: str) -> list[ItemDef]:
        return [it for it in self.items.values() if it.kind in kinds]

    def roll(self, rng: random.Random, kinds=("equipment", "consumable", "artifact", "map"),
             min_rarity: str = "common", max_rarity: str = "legendary") -> Optional[ItemDef]:
        """Случайный предмет: редкие выпадают реже (вес 8/3/1/0.3)."""
        lo, hi = RARITY_ORDER[min_rarity], RARITY_ORDER[max_rarity]
        pool = [it for it in self.items.values() if it.kind in kinds and lo <= RARITY_ORDER.get(it.rarity, 0) <= hi]
        if not pool:
            return None
        weights = [(8, 3, 1, 0.3)[RARITY_ORDER.get(it.rarity, 0)] for it in pool]
        return rng.choices(pool, weights=weights)[0]


def _items_from(data: Any) -> list[dict]:
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return data["items"]
    if isinstance(data, dict) and (data.get("effects") or data.get("id") or data.get("name")):
        slug = str(data.get("name", "item")).lower().replace(" ", "_")
        return [{"id": data.get("id") or slug, **data}]
    return []


@lru_cache(maxsize=1)
def catalog() -> ItemCatalog:
    """Каталог из lua_content/items/*.lua (без Lua-бэкенда - пустой, игра работает без предметов)."""
    from ..content import lua_bridge
    items: dict[str, ItemDef] = {}
    for path in sorted((lua_bridge.CONTENT / "items").glob("*.lua")):
        try:
            data = lua_bridge.load(path, cache=True)
        except Exception as exc:  # битый файл не должен ронять игру
            logger.warning("items: %s not loaded: %s", path.name, exc)
            continue
        for raw in _items_from(data):
            item = ItemDef.from_lua(raw)
            items[item.id] = item
    logger.info("items: %d loaded", len(items))
    return ItemCatalog(items)
