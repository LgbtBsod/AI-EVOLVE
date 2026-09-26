"""Добыча из lua_content/loot.lua: сундуки, снаряжение и выпадение с врагов."""
from __future__ import annotations

import logging
import random
from functools import lru_cache
from typing import Optional

from .inventory import Inventory
from .items import ItemCatalog, ItemDef, catalog

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def loot_tables() -> dict:
    from ..content import lua_bridge
    try:
        return lua_bridge.load(lua_bridge.CONTENT / "loot.lua", cache=True)
    except Exception as exc:  # без таблиц игра идёт без добычи
        logger.warning("loot: not loaded: %s", exc)
        return {"chest": {}, "enemies": {}}


def roll_loot(table: dict, rng: random.Random, cat: Optional[ItemCatalog] = None) -> tuple[int, list[ItemDef]]:
    """(золото, предметы) по одной строке таблицы."""
    cat = catalog() if cat is None else cat        # пустой ItemCatalog (len 0) - тоже каталог, а не «не передали»
    lo, hi = (table.get("gold") or [0, 0])[:2] if table.get("gold") else (0, 0)
    gold = rng.randint(int(lo), int(hi)) if hi else 0
    items = []
    for _ in range(int(table.get("rolls", 0) or 0)):
        if rng.random() <= float(table.get("drop_chance", 1.0)):
            item = cat.roll(rng, kinds=tuple(table.get("kinds") or ("consumable",)),
                            max_rarity=table.get("max_rarity", "legendary"))
            if item is not None:
                items.append(item)
    return gold, items


def outfit(inv: Inventory, enemy_type: str, rng: random.Random, cat: Optional[ItemCatalog] = None) -> None:
    """Снарядить врага: то, что он носит в сумке, и надетые предметы."""
    cat = catalog() if cat is None else cat        # пустой ItemCatalog (len 0) - тоже каталог, а не «не передали»
    table = (loot_tables().get("enemies") or {}).get(enemy_type) or {}
    for item_id in table.get("carries") or []:
        item = cat.get(item_id)
        if item is not None:
            inv.add(item)
    for slot, options in (table.get("equip") or {}).items():
        choices = [cat.get(i) for i in options if cat.get(i) is not None]
        if choices:
            item = rng.choice(choices)
            inv.add(item)
            inv.equip(item)


def enemy_drop(inv: Inventory, enemy_type: str, rng: random.Random) -> tuple[int, list[ItemDef]]:
    """При смерти: золото и предметы из таблицы + всё, что было у врага (кроме выпитого)."""
    table = (loot_tables().get("enemies") or {}).get(enemy_type) or {}
    gold, items = roll_loot(table, rng)
    return gold + inv.gold, items + inv.drop_all()
