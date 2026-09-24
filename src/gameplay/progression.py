"""Прогрессия: уровни, очки характеристик, перки, опыт за активности.

Правила - lua_content/world.lua (progression), перки - lua_content/perks.lua,
перевод характеристик в статы - lua_content/effect_rules.lua (attributes).

* Герой получает опыт только за активности (убийства, трюки, сундуки, квесты,
  подсказки, выход с уровня ...): xp_for(activity).
* За уровень (выше 1-го) герой получает 5 очков и сам их распределяет -
  HeroGrowth: веса класса + сдвиг к живучести, если его часто доводят до низкого HP.
* Враги: 10 очков за уровень (элиты 15), распределение по форме тела;
  боссы +10 к каждой характеристике за уровень.
* Уровень врага = уровень мира + бонус за пройденные циклы + 1 за каждые N минут сессии.
* Перки: каждые `every` очков характеристики открывают эффект (EffectManager.set_perks).
"""
from __future__ import annotations

import copy
import logging
import math
from functools import lru_cache
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

ATTRIBUTES = ("strength", "agility", "intelligence", "vitality", "wisdom", "endurance", "luck", "charisma")
DEFAULT_PROGRESSION = {
    "hero_points_per_level": 5, "enemy_points_per_level": {"normal": 10, "elite": 15},
    "boss_points_per_attribute": 10, "minutes_per_enemy_level": 5, "cycle_level_bonus": 20, "exp_growth": 0.12,
    "xp": {"chest": 50, "trap_disarm": 15, "hint": 10, "exit": 120, "boss_kill": 300, "trick_dodge": 25,
           "trick_multikill": 30, "trick_clutch": 40, "trick_overkill": 10, "quest": 150, "craft": 12, "caravan": 80},
}
HERO_WEIGHTS = {
    "warrior": {"strength": 0.4, "vitality": 0.35, "endurance": 0.25},
    "mage": {"intelligence": 0.45, "wisdom": 0.25, "vitality": 0.3},
    "rogue": {"agility": 0.45, "strength": 0.25, "luck": 0.15, "vitality": 0.15},
}


@lru_cache(maxsize=1)
def progression() -> dict:
    from ..content import lua_bridge
    rules = copy.deepcopy(DEFAULT_PROGRESSION)
    try:
        data = lua_bridge.load(lua_bridge.CONTENT / "world.lua", cache=True).get("progression") or {}
    except Exception as exc:
        logger.warning("progression: world.lua not loaded: %s", exc)
        data = {}
    for k, v in data.items():
        if isinstance(v, dict) and isinstance(rules.get(k), dict):
            rules[k].update(v)
        else:
            rules[k] = v
    return rules


def xp_for(activity: str) -> int:
    return int(progression()["xp"].get(activity, 0))


# ---------------------------------------------------------------- points
def allocate(points: int, weights: dict[str, float], current: Optional[dict[str, float]] = None) -> dict[str, float]:
    """Раздать очки так, чтобы доли характеристик шли к весам (largest deficit first)."""
    out = dict(current or {})
    total_w = sum(w for w in weights.values() if w > 0) or 1.0
    for _ in range(int(points)):
        total = sum(out.get(a, 0.0) for a in weights) + 1
        attr = max(weights, key=lambda a: weights[a] / total_w * total - out.get(a, 0.0))
        out[attr] = out.get(attr, 0.0) + 1
    return out


def enemy_attributes(kind: str, level: int, weights: dict[str, float]) -> dict[str, float]:
    """Очки врага за уровень: normal 10, elite 15 (по весам); boss/final/miniboss +10 к каждой."""
    rules = progression()
    lvl = max(0, int(level) - 1)
    if kind in ("boss", "final", "miniboss"):
        per = float(rules["boss_points_per_attribute"])
        return {a: per * lvl for a in ATTRIBUTES if a != "charisma"}
    per = int(rules["enemy_points_per_level"].get(kind, 10))
    return allocate(per * lvl, weights or {"strength": 0.5, "vitality": 0.5})


def enemy_level(world_level: int, cycle: int = 0, session_seconds: float = 0.0) -> int:
    rules = progression()
    minutes = float(rules["minutes_per_enemy_level"]) or 5.0
    return int(world_level + int(rules["cycle_level_bonus"]) * max(0, cycle)
               + math.floor(max(0.0, session_seconds) / (60.0 * minutes)))


def exp_reward(base: float, level: int) -> int:
    return int(float(base) * (1.0 + float(progression()["exp_growth"]) * (max(1, level) - 1)))


class HeroGrowth:
    """Как герой тратит очки: веса класса, а если его часто доводят до <30% HP -
    часть очков уходит в живучесть (герой «учится» на своих ранах)."""

    def __init__(self, character_class: str = "warrior"):
        self.weights = dict(HERO_WEIGHTS.get(character_class, HERO_WEIGHTS["warrior"]))
        self.close_calls = 0

    def note_close_call(self) -> None:
        self.close_calls += 1

    def spend(self, entity) -> dict[str, float]:
        """Потратить entity.attribute_points; -> сколько вложено в каждую характеристику."""
        points = int(getattr(entity, "attribute_points", 0) or 0)
        if points <= 0:
            return {}
        weights = dict(self.weights)
        if self.close_calls:
            weights["vitality"] = weights.get("vitality", 0.0) + min(0.4, 0.05 * self.close_calls)
        before = dict(getattr(entity, "attributes", {}) or {})
        entity.attributes = allocate(points, weights, before)
        entity.attribute_points = 0
        return {a: entity.attributes[a] - before.get(a, 0.0) for a in entity.attributes
                if entity.attributes[a] != before.get(a, 0.0)}


# ---------------------------------------------------------------- perks
@lru_cache(maxsize=1)
def perks() -> list[dict]:
    from ..content import lua_bridge
    try:
        return list(lua_bridge.load(lua_bridge.CONTENT / "perks.lua", cache=True).get("perks") or [])
    except Exception as exc:
        logger.warning("perks: not loaded: %s", exc)
        return []


def perk_effects(attributes: dict[str, float], catalog: Optional[Iterable[dict]] = None) -> list[dict]:
    """Эффекты перков, открытых очками характеристик (ранг - в meta)."""
    out = []
    for perk in catalog if catalog is not None else perks():
        have = float((attributes or {}).get(perk["attribute"], 0.0))
        every = float(perk.get("every", 15))
        if have >= every:
            ef = copy.deepcopy(perk["effect"])
            ef["id"] = f"perk.{perk['id']}"
            ef["meta"] = {"name": perk.get("name", perk["id"]), "rank": int(have // every)}
            out.append(ef)
    return out
