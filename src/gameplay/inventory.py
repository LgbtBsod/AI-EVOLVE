"""Инвентарь сущности и то, как ИИ им пользуется (герой, враги, элиты, боссы).

Inventory: сумка + слоты экипировки + золото. Надеть/снять - через менеджер
эффектов (EffectManager.equip): статы и эффекты предметов начинают/перестают
действовать. Выпить зелье - EffectManager.use_item: тот же конвейер эффектов.

InventoryBrain - решения без участия игрока:
  * зелье лечения при HP ниже порога (порог сдвигают эмоции героя),
  * зелья маны/выносливости, когда ресурса мало,
  * надеть предмет, если он сильнее надетого (оценка по весам класса),
  * прочитать карту (знание о мире), надеть артефакт.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

from .items import EQUIP_SLOTS, RARITY_ORDER, ItemDef

logger = logging.getLogger(__name__)

# вес стата при оценке предмета, по «роли» сущности
STAT_WEIGHTS: dict[str, dict[str, float]] = {
    "warrior": {"attack_damage": 3.0, "defense": 2.5, "max_hp": 0.3, "aspd": 20, "crit_chance": 1.5, "crit_dmg": 0.5,
                "lifesteal": 2.0, "strength": 1.5, "vitality": 1.5, "endurance": 1.0, "move_speed": 3.0, "hp_regen": 4.0},
    "mage": {"spell_power": 3.0, "max_mana": 0.5, "mana_regen": 6.0, "intelligence": 1.5, "wisdom": 1.5,
             "defense": 1.5, "max_hp": 0.3, "move_speed": 3.0, "crit_chance": 1.0},
    "rogue": {"attack_damage": 2.5, "crit_chance": 2.5, "crit_dmg": 1.0, "aspd": 25, "agility": 2.0, "dodge": 2.0,
              "defense": 1.5, "max_hp": 0.3, "move_speed": 4.0, "luck": 1.0},
    "monster": {"attack_damage": 3.0, "defense": 2.5, "max_hp": 0.4, "aspd": 20, "crit_chance": 1.0},
}
EFFECT_VALUE = {"common": 6.0, "rare": 14.0, "epic": 26.0, "legendary": 45.0}


def item_power(item: Optional[ItemDef], role: str = "warrior") -> float:
    """Сколько предмет стоит для роли: статы по весам + эффекты по редкости."""
    if item is None:
        return 0.0
    weights = STAT_WEIGHTS.get(role, STAT_WEIGHTS["warrior"])
    power = sum(weights.get(k, 0.5) * v for k, v in item.stats.items())
    if item.effects:
        power += EFFECT_VALUE.get(item.rarity, 6.0) * min(3, len(item.effects))
    if item.knowledge:
        power += 10.0
    return power


@dataclass
class Inventory:
    owner: object
    capacity: int = 16
    gold: int = 0
    bag: list[ItemDef] = field(default_factory=list)
    equipped: dict[str, ItemDef] = field(default_factory=dict)
    on_change: Optional[Callable[["Inventory"], None]] = None   # менеджер эффектов: пересчитать статы
    log: list[str] = field(default_factory=list)                # что сделал ИИ (для HUD)

    # ---------------------------------------------------------------- basics
    def add(self, item: ItemDef) -> bool:
        if len(self.bag) >= self.capacity:
            return False
        self.bag.append(item)
        return True

    def remove(self, item: ItemDef) -> bool:
        if item in self.bag:
            self.bag.remove(item)
            return True
        return False

    def count(self, item_id: str) -> int:
        return sum(1 for it in self.bag if it.id == item_id)

    def all_items(self) -> list[ItemDef]:
        return list(self.equipped.values()) + list(self.bag)

    def _changed(self) -> None:
        if self.on_change:
            self.on_change(self)

    def equip(self, item: ItemDef) -> Optional[ItemDef]:
        """Надеть из сумки; прошлый предмет слота уходит в сумку. -> снятый предмет."""
        if not item.equippable or item not in self.bag:
            return None
        self.bag.remove(item)
        old = self.equipped.pop(item.slot, None)
        self.equipped[item.slot] = item
        if old is not None:
            self.bag.append(old)
        self.log.append(f"надел {item.name}" + (f" вместо {old.name}" if old else ""))
        self._changed()
        return old

    def unequip(self, slot: str) -> Optional[ItemDef]:
        item = self.equipped.pop(slot, None)
        if item is not None:
            self.bag.append(item)
            self._changed()
        return item

    def drop_all(self) -> list[ItemDef]:
        """Всё содержимое (при смерти: выпадает на землю)."""
        items = self.all_items()
        self.bag.clear()
        self.equipped.clear()
        return items

    def summary(self) -> dict:
        return {"gold": self.gold, "equipped": {s: it.name for s, it in self.equipped.items()},
                "bag": [it.name for it in self.bag]}


class InventoryBrain:
    """Решения по инвентарю без игрока. Пороги - атрибуты, их меняют эмоции героя."""

    def __init__(self, inventory: Inventory, role: str = "warrior", heal_at: float = 0.35,
                 resource_at: float = 0.2, equip_interval: float = 2.0, potion_cooldown: float = 3.0):
        self.inv = inventory
        self.role = role
        self.heal_at = heal_at
        self.resource_at = resource_at
        self.equip_interval = equip_interval
        self.potion_cooldown = potion_cooldown
        self._equip_timer = 0.0
        self._potion_ready_at = 0.0
        self.now = 0.0

    def update(self, dt: float, use_item: Callable[[ItemDef], bool],
               learn: Optional[Callable[[ItemDef], None]] = None) -> Optional[str]:
        """Одно решение за вызов (или None). use_item - менеджер эффектов, learn - знания о мире."""
        self.now += dt
        e = self.inv.owner
        if self.now >= self._potion_ready_at:
            hp_frac = float(getattr(e, "health", 0)) / max(1.0, float(getattr(e, "max_health", 1)))
            if hp_frac <= self.heal_at and self._drink("hp", use_item):
                return "potion:hp"
            for res in ("mana", "stamina"):
                cap = float(getattr(e, f"max_{res}", 0) or 0)
                if cap > 0 and float(getattr(e, res, cap)) / cap <= self.resource_at and self._drink(res, use_item):
                    return f"potion:{res}"
        for item in [it for it in self.inv.bag if it.kind == "map"]:
            self.inv.remove(item)
            if learn:
                learn(item)
            self.inv.log.append(f"прочитал {item.name}")
            return f"read:{item.id}"
        self._equip_timer -= dt
        if self._equip_timer <= 0:
            self._equip_timer = self.equip_interval
            best = self.best_upgrade()
            if best is not None:
                self.inv.equip(best)
                if best.kind == "artifact" and learn:
                    learn(best)
                return f"equip:{best.id}"
        return None

    def _drink(self, res: str, use_item) -> bool:
        potions = [it for it in self.inv.bag if it.usable and res in it.restores()]
        if not potions:
            return False
        # сначала слабое зелье: большое - на чёрный день
        potion = min(potions, key=lambda it: RARITY_ORDER.get(it.rarity, 0))
        if use_item(potion):
            self.inv.remove(potion)
            self.inv.log.append(f"выпил {potion.name}")
            self._potion_ready_at = self.now + self.potion_cooldown
            return True
        return False

    def best_upgrade(self) -> Optional[ItemDef]:
        best, gain = None, 0.5
        for it in self.inv.bag:
            if not it.equippable or it.slot not in EQUIP_SLOTS:
                continue
            g = item_power(it, self.role) - item_power(self.inv.equipped.get(it.slot), self.role)
            if g > gain:
                best, gain = it, g
        return best
