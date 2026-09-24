"""План мира: 80 уровней, 8 актов (lua_content/world.lua), бестиарий и боссы.

WorldPlan отвечает на вопросы сцены про уровень: какой акт и биом, кто
водится, кто босс, какая погода, есть ли город, как сильны враги.
make_enemy() создаёт врага из бестиария или босса с масштабом по уровню.
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_ACT = {"id": "midgard", "name": "Мидгард", "levels": [1, 80], "biome": "forest",
               "enemies": ["basic"], "elites": ["elite"], "weather": ["clear"], "towns": [], "lore": []}


@dataclass
class LevelInfo:
    level: int
    act: dict
    name: str
    biome: str
    boss: Optional[str]
    boss_role: Optional[str]      # "miniboss" | "boss" | "final"
    has_town: bool
    is_final: bool


class WorldPlan:
    def __init__(self, world: dict, bestiary: dict, bosses: dict):
        self.max_level = int(world.get("max_level", 80))
        self.acts = world.get("acts") or [DEFAULT_ACT]
        self.bestiary = bestiary.get("enemies") or {}
        self.attribute_weights = bestiary.get("attribute_weights") or {}
        self.bosses = bosses

    # ---------------------------------------------------------------- levels
    def act_for(self, level: int) -> dict:
        for act in self.acts:
            lo, hi = act["levels"][:2]
            if lo <= level <= hi:
                return act
        return self.acts[-1] if level > 1 else self.acts[0]

    def info(self, level: int) -> LevelInfo:
        level = max(1, min(self.max_level, int(level)))
        act = self.act_for(level)
        lo, hi = act["levels"][:2]
        boss, role = None, None
        if level == hi and act.get("boss"):
            boss = act["boss"]
            role = (self.bosses.get(boss) or {}).get("role", "boss")
        elif level == lo + 4 and act.get("miniboss"):
            boss, role = act["miniboss"], "miniboss"
        circles = act.get("circles") or {}
        circle = circles.get(level) or circles.get(str(level))
        name = f"{act['name']} - {circle}" if circle else f"{act['name']}, уровень {level - lo + 1}"
        towns = {lo + int(t) - 1 for t in act.get("towns") or []}
        return LevelInfo(level, act, name, act.get("biome", "forest"), boss, role, level in towns,
                         level >= self.max_level)

    def final_sequence(self, level: int) -> list[str]:
        """Боссы финального уровня по очереди (Люцифер - первый из них)."""
        info = self.info(level)
        if not info.is_final:
            return [info.boss] if info.boss else []
        return list(info.act.get("final_sequence") or ([info.boss] if info.boss else []))

    def rank(self, enemy_type: str) -> str:
        """normal | elite | miniboss | boss | final - сколько очков за уровень."""
        boss = self.bosses.get(enemy_type)
        if boss:
            return boss.get("role", "boss")
        spec = self.bestiary.get(enemy_type) or {}
        return "elite" if spec.get("loot") == "elite" else "normal"

    # ---------------------------------------------------------------- enemies
    @staticmethod
    def elite_chance(enemy_level: int) -> float:
        """Элита редка в начале (2% на 1-м уровне) и растёт на 1% за уровень до 30%."""
        return min(0.30, 0.02 + 0.01 * max(0, int(enemy_level) - 1))

    def pick_enemy(self, level: int, rng: random.Random, elite_chance: Optional[float] = None) -> str:
        act = self.act_for(level)
        if elite_chance is None:
            elite_chance = self.elite_chance(level)
        pool = act.get("elites") if rng.random() < elite_chance and act.get("elites") else act.get("enemies")
        return rng.choice(pool or ["basic"])

    def spec(self, enemy_type: str) -> Optional[dict]:
        return self.bestiary.get(enemy_type) or self.bosses.get(enemy_type)

    def weather_for(self, level: int, rng: random.Random) -> str:
        return rng.choice(self.act_for(level).get("weather") or ["clear"])

    def lore_line(self, level: int, rng: random.Random) -> str:
        lines = self.act_for(level).get("lore") or []
        return rng.choice(lines) if lines else ""


@lru_cache(maxsize=1)
def world_plan() -> WorldPlan:
    from ..content import lua_bridge
    from ..effects.abilities import load_bosses

    def load(name):
        try:
            return lua_bridge.load(lua_bridge.CONTENT / name, cache=True)
        except Exception as exc:
            logger.warning("world: %s not loaded: %s", name, exc)
            return {}
    return WorldPlan(load("world.lua") or {"acts": [DEFAULT_ACT]}, load("bestiary.lua"), load_bosses())


def make_enemy(game, enemy_type: str, level: int, x: float, y: float, plan: Optional[WorldPlan] = None):
    """Враг/босс из бестиария с масштабом по уровню. Неизвестный тип - старые типы из config."""
    from ..entities.enemy import EnhancedEnemy
    plan = plan or world_plan()
    spec = plan.spec(enemy_type)
    enemy = EnhancedEnemy(game, x, y, 0.5, enemy_type if spec is None else "basic")
    if spec is None:  # старые типы из config/*.json: прежнее масштабирование
        enemy.apply_level_bonus(max(0, int(level) - int(enemy.level)))
        return enemy
    enemy.enemy_type = enemy_type
    enemy.display_name = spec.get("name", enemy_type)
    from .progression import enemy_attributes, exp_reward
    rank = plan.rank(enemy_type)
    enemy.level = level
    enemy.rank = rank
    # база бестиария - это 1-й уровень; рост - очками характеристик за уровень
    # (обычный 10, элита 15, босс +10 к каждой), их в статы переводит менеджер эффектов
    enemy.max_health = enemy.health = float(spec.get("health", 50))
    enemy.physical_damage = float(spec.get("damage", 8))
    enemy.defense = float(spec.get("defense", 1))
    enemy.move_speed = float(spec.get("speed", 4.0))
    enemy.attributes = enemy_attributes(rank, level, plan.attribute_weights.get(spec.get("shape", "humanoid"), {}))
    enemy.experience_reward = exp_reward(spec.get("exp_reward", 20), level)
    enemy.size = float(spec.get("size", 1.0))
    enemy.color = tuple(spec.get("color") or (1, 0, 0, 1))
    enemy.shape = spec.get("shape", "humanoid")
    enemy.skills = list(spec.get("skills") or [])
    enemy.loot_class = "boss" if spec.get("role") else spec.get("loot", "basic")
    enemy.dialog = spec.get("dialog") or {}
    enemy.tactics_pool = list(spec.get("tactics") or [])
    enemy.ranged = bool(spec.get("ranged"))
    enemy.role = spec.get("role")                     # miniboss / boss / final
    enemy.rooted = bool(spec.get("rooted"))
    enemy.attack_range = float(spec.get("attack_range", 2.0))
    enemy.vision_range = float(spec.get("vision", 20.0))
    if enemy.role:
        enemy.vision_range = float(spec.get("vision", 30.0))
        enemy.attack_range = float(spec.get("attack_range", 3.0 + enemy.size * 0.4))
    hc = getattr(enemy, "_health_component", None)
    if hc is not None and hasattr(hc, "sync"):
        hc.sync(enemy.health, enemy.max_health)
    return enemy
